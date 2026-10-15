// SPDX-License-Identifier: MPL-2.0
"use strict";
const byID = id => document.getElementById(id);
let running = false;
async function request(command, extra = {}) {
  return browser.runtime.sendMessage({command, ...extra});
}
function render(state) {
  if (!state) return;
  const select = byID("profile"), selection = select.value || state.profileID;
  const options = state.profiles.map(profile => { const option = document.createElement("option"); option.value = profile.id; option.textContent = profile.name; return option; });
  if (!options.length) { const option = document.createElement("option"); option.value = ""; option.textContent = "Add a profile in the Mac app"; options.push(option); }
  select.replaceChildren(...options);
  if (options.some(option => option.value === selection)) select.value = selection;
  byID("status").textContent = !state.desired ? "Normal browsing" : state.directFallback ? "Browsing directly" : ({connected: "Connected", connecting: "Waiting for handshake…", disconnecting: "Disconnecting…"}[state.phase] || "Browsing blocked");
  byID("dot").className = `dot ${state.desired ? state.phase === "connected" ? "connected" : "blocked" : ""}`;
  byID("error").textContent = state.error || ""; byID("error").hidden = !state.error;
  byID("disconnect").hidden = !state.desired;
  byID("connect").textContent = state.desired ? "Reconnect" : "Connect";
  byID("connect").disabled = running || !select.value || state.busy;
  byID("disconnect").disabled = running;
  select.disabled = running;
  byID("kill-switch").checked = state.killSwitch !== false;
  byID("kill-switch").disabled = running;
  byID("fallback").hidden = !state.directFallback;
  const details = state.desired && state.phase === "connected" ? FirefoxWGDetails.sanitize(state.details) : null;
  byID("connection").hidden = !details;
  byID("details-unavailable").hidden = !state.desired || state.phase !== "connected" || !!details;
  byID("public-ip").textContent = !details ? "—" : details.exitStatus === "ready" && details.publicIP
    ? `${FirefoxWGDetails.countryFlag(details.countryCode)} ${details.publicIP}`
    : details.exitStatus === "unavailable" ? "Unavailable" : "Checking…";
  byID("downloaded").textContent = FirefoxWGDetails.byteLabel(details?.statsUpdatedAt ? details.downloadedBytes : null);
  byID("uploaded").textContent = FirefoxWGDetails.byteLabel(details?.statsUpdatedAt ? details.uploadedBytes : null);
  byID("dns").textContent = details?.dnsServers.join(", ") || "—";
  byID("client-ip").textContent = details?.clientIPs.join(", ") || "—";
}
async function action(command, extra = {}) {
  if (running) return;
  running = true; byID("connect").disabled = true; byID("disconnect").disabled = true; byID("kill-switch").disabled = true;
  try { const result = await request(command, {profileID: byID("profile").value, ...extra}); running = false; render(result); }
  catch { running = false; byID("error").hidden = false; byID("error").textContent = "Extension unavailable. Reopen this panel."; }
}
byID("connect").addEventListener("click", () => action("connect"));
byID("disconnect").addEventListener("click", () => action("disconnect"));
byID("refresh").addEventListener("click", () => action("refresh"));
byID("kill-switch").addEventListener("change", () => action("killSwitch", {enabled: byID("kill-switch").checked}));
request("status").then(render);
setInterval(() => { if (!running) request("status").then(render).catch(() => {}); }, 1000);
