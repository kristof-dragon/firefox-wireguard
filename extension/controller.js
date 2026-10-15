/* This module is shared by the Firefox background page and the lifecycle tests. */
"use strict";
(function (root) {
  const HOST = "org.firefoxwireguard.bridge";
  const DEAD_PORT = 9;
  const controllable = value => ["controllable_by_this_extension", "controlled_by_this_extension"].includes(value.levelOfControl);

  function isLoopback(url) {
    try {
      const host = new URL(url).hostname.toLowerCase().replace(/\.$/, "");
      return host === "localhost" || host.endsWith(".localhost") || host === "[::1]" || /^127\.\d+\.\d+\.\d+$/.test(host);
    } catch { return false; }
  }

  class NativeClient {
    constructor(browser, onDisconnect, timeout = 7000) {
      this.browser = browser;
      this.onDisconnect = onDisconnect;
      this.port = null;
      this.pending = new Map();
      this.sequence = 0;
      this.timeout = timeout;
    }
    close(port, message, disconnect = true) {
      if (this.port !== port) return;
      this.port = null;
      for (const job of this.pending.values()) {
        clearTimeout(job.timer); job.reject(new Error(message));
      }
      this.pending.clear();
      // Firefox does not notify this end when we call disconnect() ourselves.
      if (disconnect) { try { port.disconnect(); } catch { /* Already closed. */ } }
      this.onDisconnect();
    }
    request(command, clientID, profileID) {
      if (!this.port) {
        const port = this.browser.runtime.connectNative(HOST);
        this.port = port;
        port.onMessage.addListener(message => {
          if (this.port !== port || !message || message.version !== 1) return;
          const job = this.pending.get(message.id);
          if (!job) return;
          clearTimeout(job.timer); this.pending.delete(message.id);
          job.resolve(message);
        });
        port.onDisconnect.addListener(() => {
          this.close(port, "Companion app unavailable. Open it and install Firefox integration.", false);
        });
      }
      const id = String(++this.sequence);
      return new Promise((resolve, reject) => {
        const port = this.port;
        const timer = setTimeout(() => this.close(port,
          "The companion app did not respond. Firefox remains blocked while protection is enabled."), this.timeout);
        this.pending.set(id, {resolve, reject, timer});
        try { this.port.postMessage({version: 1, id, command, clientID, ...(profileID ? {profileID} : {})}); }
        catch {
          this.close(port, "Could not contact the companion app.");
        }
      });
    }
  }

  class Controller {
    constructor(browser, native, changed = () => {}) {
      this.browser = browser; this.native = native; this.changed = changed;
      // Install synchronous request guards before the first asynchronous read.
      this.desired = true; this.blocked = true; this.ready = false;
      this.profileID = null; this.clientID = null; this.proxyPort = null;
      this.profiles = []; this.error = null; this.phase = "starting"; this.busy = false;
      this.tail = Promise.resolve(); this.refreshQueued = false;
      this.initialization = null;
      this.transportEpoch = 0;
    }
    enqueue(operation) {
      const result = this.tail.then(operation);
      this.tail = result.catch(() => {});
      return result;
    }
    snapshot() {
      return {ready: this.ready, desired: this.desired, blocked: this.blocked,
        phase: this.phase, profileID: this.profileID, profiles: this.profiles,
        error: this.error, busy: this.busy};
    }
    notify() { this.changed(this.snapshot()); }
    route(details) {
      if (isLoopback(details.url)) return {type: "direct"};
      if (!this.desired && this.ready) return undefined;
      return [{type: "socks", host: "127.0.0.1", port: this.blocked ? DEAD_PORT : this.proxyPort,
        proxyDNS: true, failoverTimeout: 1}, null];
    }
    guard(details) {
      return {cancel: (!this.ready || (this.desired && this.blocked)) && !isLoopback(details.url)};
    }
    settings() {
      return [this.browser.proxy.settings, this.browser.privacy.network.peerConnectionEnabled,
        this.browser.privacy.network.networkPredictionEnabled];
    }
    async ensurePermissions() {
      if (!await this.browser.extension.isAllowedIncognitoAccess()) {
        throw new Error("Allow this extension in Private Windows in Firefox’s Add-ons settings, then reconnect.");
      }
      for (const setting of this.settings()) {
        if (!setting || !controllable(await setting.get({}))) {
          throw new Error("Another extension or browser policy controls a required network setting. Resolve the conflict before connecting.");
        }
      }
    }
    async protect(port = DEAD_PORT) {
      await this.ensurePermissions();
      await this.browser.privacy.network.peerConnectionEnabled.set({value: false});
      await this.browser.privacy.network.networkPredictionEnabled.set({value: false});
      await this.browser.proxy.settings.set({value: {
        proxyType: "manual", socks: `127.0.0.1:${port}`, socksVersion: 5, proxyDNS: true,
        passthrough: "localhost,127.0.0.0/8,[::1]"
      }});
      await this.verifySettings(port);
    }
    async verifySettings(port) {
      const [proxy, rtc, prediction] = await Promise.all(this.settings().map(s => s.get({})));
      if ([proxy, rtc, prediction].some(s => s.levelOfControl !== "controlled_by_this_extension") ||
          proxy.value.proxyType !== "manual" || proxy.value.socks !== `127.0.0.1:${port}` ||
          proxy.value.socksVersion !== 5 || proxy.value.proxyDNS !== true || rtc.value !== false || prediction.value !== false) {
        throw new Error("Firefox network settings changed or could not be verified. Browsing is blocked; reconnect after resolving the conflict.");
      }
    }
    initialize() {
      if (this.initialization) return this.initialization;
      this.initialization = this.enqueue(async () => {
        try {
          const stored = await this.browser.storage.local.get(["desired", "profileID", "clientID"]);
          this.desired = stored.desired === true;
          this.profileID = stored.profileID || null;
          this.clientID = stored.clientID || crypto.randomUUID();
          await this.browser.storage.local.set({clientID: this.clientID});
          if (this.desired) await this.protect();
          else await this.releaseSettings();
          this.phase = this.desired ? "blocked" : "idle";
        } catch (error) {
          this.desired = true; this.error = error.message; this.phase = "blocked";
        } finally { this.ready = true; this.notify(); }
      });
      return this.initialization;
    }
    async releaseSettings() {
      // clear() releases our layer, restoring Firefox's underlying user/extension
      // preferences. It does not overwrite somebody else's current settings.
      const results = await Promise.allSettled(this.settings().map(async setting => {
        const current = await setting.get({});
        if (current.levelOfControl === "controlled_by_this_extension") await setting.clear({});
      }));
      if (results.some(result => result.status === "rejected")) throw new Error("Could not restore all Firefox settings. Keep the extension enabled and retry Disconnect.");
    }
    connect(profileID) {
      return this.enqueue(async () => {
        this.desired = true; this.blocked = true; this.proxyPort = null;
        this.profileID = profileID; this.phase = "connecting"; this.error = null; this.notify();
        try {
          if (!this.clientID) throw new Error("Reload the extension before connecting.");
          await this.browser.storage.local.set({desired: true, profileID});
          await this.protect();
          await this.accept(await this.native.request("connect", this.clientID, profileID));
        } catch (error) { await this.fail(error.message); }
        return this.snapshot();
      });
    }
    disconnect() {
      return this.enqueue(async () => {
        // Keep the guard active until settings and durable intent are restored.
        this.blocked = true; this.phase = "disconnecting"; this.notify();
        try { if (this.clientID) await this.native.request("disconnect", this.clientID); } catch { /* A stopped companion must not prevent an explicit opt-out. */ }
        try {
          await this.releaseSettings();
          await this.browser.storage.local.set({desired: false});
          this.desired = false; this.proxyPort = null; this.phase = "idle"; this.error = null; this.busy = false;
        } catch (error) { await this.fail(error.message); }
        this.notify(); return this.snapshot();
      });
    }
    refresh() {
      if (this.refreshQueued || !this.clientID) return Promise.resolve(this.snapshot());
      this.refreshQueued = true;
      return this.enqueue(async () => {
        try { await this.accept(await this.native.request("status", this.clientID)); }
        catch (error) {
          if (this.desired) await this.fail(error.message);
          else { this.error = error.message; this.notify(); }
        } finally { this.refreshQueued = false; }
        return this.snapshot();
      });
    }
    async accept(response) {
      const epoch = this.transportEpoch;
      if (!response || response.version !== 1 || !response.ok) throw new Error(response?.error || "Invalid response from the companion app.");
      if (!Array.isArray(response.profiles) || !response.state) throw new Error("The companion response is incomplete.");
      this.profiles = response.profiles.filter(p => typeof p.id === "string" && typeof p.name === "string").map(p => ({id: p.id, name: p.name}));
      this.busy = response.busy === true;
      if (!this.desired) { this.error = this.busy ? "Another Firefox profile is using the tunnel." : null; this.notify(); return; }
      const state = response.state;
      if (!this.busy && state.phase === "connected" && state.profileID === this.profileID &&
          Number.isInteger(state.proxyPort) && state.proxyPort > 0 && state.proxyPort <= 65535) {
        if (this.blocked || this.proxyPort !== state.proxyPort) await this.protect(state.proxyPort);
        else await this.verifySettings(state.proxyPort);
        if (epoch !== this.transportEpoch) throw new Error("Companion connection lost during setup. Reconnect to retry.");
        this.proxyPort = state.proxyPort; this.blocked = false; this.phase = "connected"; this.error = null;
      } else {
        const message = this.busy ? "Another Firefox profile owns the tunnel." : state.error || (state.phase === "connecting" ? null : "Tunnel unavailable. Reconnect or disconnect to return to normal browsing.");
        await this.fail(message, state.phase === "connecting" ? "connecting" : "blocked");
      }
      this.notify();
    }
    async fail(message, phase = "blocked") {
      this.blocked = true; this.proxyPort = null; this.phase = phase; this.error = message; this.notify();
      // The synchronous request guard is already closed even if Firefox refuses
      // the settings API or the companion never starts.
      if (this.desired) {
        try { await this.protect(); } catch (error) { this.error = error.message; }
      }
      this.notify();
    }
    transportLost() {
      this.transportEpoch++;
      if (this.desired) {
        this.blocked = true; this.proxyPort = null; this.phase = "blocked";
        this.error = "Companion connection lost. Reconnect or disconnect to resume browsing.";
        this.notify();
        this.enqueue(() => this.fail(this.error));
      }
    }
  }
  root.FirefoxWG = {Controller, NativeClient, isLoopback};
  if (typeof module !== "undefined") module.exports = root.FirefoxWG;
})(globalThis);
