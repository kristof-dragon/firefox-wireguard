"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {Controller, isLoopback} = require("../controller.js");
const PROFILE = "11111111-1111-4111-8111-111111111111";
function fixture(stored = {}) {
  const data = {...stored}, events = [];
  function setting(initial) {
    return {value: initial, initial, levelOfControl: "controllable_by_this_extension",
      async get() { return {value: this.value, levelOfControl: this.levelOfControl}; },
      async set({value}) { this.value = value; this.levelOfControl = "controlled_by_this_extension"; events.push("setting"); },
      async clear() { this.value = this.initial; this.levelOfControl = "controllable_by_this_extension"; events.push("clear"); }};
  }
  const browser = {extension: {isAllowedIncognitoAccess: async () => true},
    storage: {local: {get: async () => ({...data}), set: async value => { Object.assign(data, value); events.push("persist"); }}},
    proxy: {settings: setting({proxyType: "system"})},
    privacy: {network: {peerConnectionEnabled: setting(true), networkPredictionEnabled: setting(true)}}};
  let response = {version: 1, ok: true, profiles: [{id: PROFILE, name: "Test"}], state: {phase: "connected", profileID: PROFILE, proxyPort: 34567}};
  const native = {request: async command => { events.push(command); return response; }};
  const controller = new Controller(browser, native);
  return {controller, browser, native, data, events, setResponse: value => { response = value; }};
}
test("loopback stays local, private destinations do not bypass", () => {
  for (const url of ["http://localhost/", "http://localhost./", "http://name.localhost/", "http://127.0.0.2/", "http://[::1]/"]) assert.equal(isLoopback(url), true);
  for (const url of ["http://localhost.example.invalid/", "http://192.0.2.1/", "https://example.com/", "http://10.1.2.3/"]) assert.equal(isLoopback(url), false);
});
test("guards are closed before asynchronous initialization", async () => {
  const {controller} = fixture();
  assert.equal(controller.guard({url: "https://example.com"}).cancel, true);
  assert.equal(controller.guard({url: "http://localhost"}).cancel, false);
  await controller.initialize();
  assert.equal(controller.guard({url: "https://example.com"}).cancel, false);
  assert.equal(controller.route({url: "https://example.com"}), undefined);
});
test("connect persists intent and installs protection before starting native tunnel", async () => {
  const {controller, events, browser, data} = fixture();
  await controller.initialize(); events.length = 0;
  await controller.connect(PROFILE);
  assert.equal(events[0], "persist");
  assert.ok(events.indexOf("setting") < events.indexOf("connect"));
  assert.equal(data.desired, true); assert.equal(controller.blocked, false);
  assert.equal(browser.privacy.network.peerConnectionEnabled.value, false);
  const routes = controller.route({url: "https://example.com"});
  assert.equal(routes[0].port, 34567); assert.equal(routes[0].proxyDNS, true); assert.equal(routes[1], null);
});
test("native connect failure remains blocked and never clears settings", async () => {
  const {controller, native, events, browser} = fixture();
  await controller.initialize(); events.length = 0;
  native.request = async () => { throw new Error("offline"); };
  await controller.connect(PROFILE);
  assert.equal(controller.blocked, true); assert.equal(controller.desired, true);
  assert.equal(events.includes("clear"), false);
  assert.equal(controller.guard({url: "https://example.com"}).cancel, true);
  assert.equal(browser.proxy.settings.value.socks, "127.0.0.1:9");
});
test("missing private-window permission never starts backend", async () => {
  const {controller, browser, events} = fixture();
  await controller.initialize(); events.length = 0;
  browser.extension.isAllowedIncognitoAccess = async () => false;
  await controller.connect(PROFILE);
  assert.equal(events.includes("connect"), false); assert.equal(controller.blocked, true);
  assert.match(controller.error, /Private Windows/);
});
test("first install without private-window permission leaves ordinary browsing alone", async () => {
  const {controller, browser, events} = fixture();
  browser.extension.isAllowedIncognitoAccess = async () => false;
  browser.proxy.settings.clear = async () => { throw new Error("private permission required"); };
  await controller.initialize();
  assert.equal(controller.desired, false);
  assert.equal(controller.guard({url: "https://example.com"}).cancel, false);
  assert.equal(events.includes("clear"), false);
});
test("browser restart with desired protection blocks before status recovery", async () => {
  const {controller} = fixture({desired: true, profileID: PROFILE});
  await controller.initialize(); assert.equal(controller.blocked, true);
  await controller.refresh(); assert.equal(controller.blocked, false);
});
test("transport loss blocks synchronously", async () => {
  const {controller} = fixture(); await controller.initialize(); await controller.connect(PROFILE);
  controller.transportLost();
  assert.equal(controller.guard({url: "https://example.com"}).cancel, true);
  await controller.tail; assert.equal(controller.phase, "blocked");
});
test("stale readiness cannot reopen the guard after transport loss", async () => {
  const {controller, browser} = fixture(); await controller.initialize();
  const original = browser.proxy.settings.set.bind(browser.proxy.settings);
  browser.proxy.settings.set = async options => {
    await original(options);
    if (options.value.socks.endsWith(":34567")) controller.transportLost();
  };
  await controller.connect(PROFILE); await controller.tail;
  assert.equal(controller.blocked, true);
});
test("wrong profile and another client's tunnel cannot be adopted", async () => {
  const {controller, setResponse} = fixture(); await controller.initialize();
  setResponse({version: 1, ok: true, profiles: [], state: {phase: "connected", profileID: "other", proxyPort: 4444}});
  await controller.connect(PROFILE); assert.equal(controller.blocked, true);
});
test("explicit disconnect works when the companion is gone and restores user settings", async () => {
  const {controller, browser, native, data} = fixture(); await controller.initialize(); await controller.connect(PROFILE);
  native.request = async () => { throw new Error("offline"); };
  await controller.disconnect();
  assert.equal(controller.desired, false); assert.equal(data.desired, false);
  assert.equal(browser.privacy.network.peerConnectionEnabled.value, true);
  assert.deepEqual(browser.proxy.settings.value, {proxyType: "system"});
});
test("settings takeover closes the guard", async () => {
  const {controller, browser} = fixture(); await controller.initialize(); await controller.connect(PROFILE);
  browser.proxy.settings.levelOfControl = "controlled_by_other_extensions";
  await controller.refresh(); assert.equal(controller.blocked, true);
});
test("state storage failure prevents backend launch", async () => {
  const {controller, browser, events} = fixture(); await controller.initialize(); events.length = 0;
  browser.storage.local.set = async () => { throw new Error("storage failure"); };
  await controller.connect(PROFILE);
  assert.equal(events.includes("connect"), false); assert.equal(controller.blocked, true);
});
