"use strict";
let controller;
const native = new FirefoxWG.NativeClient(browser, () => controller?.transportLost());
controller = new FirefoxWG.Controller(browser, native, state => {
  const text = !state.desired ? "" : state.phase === "connected" ? "ON" : "!";
  browser.browserAction.setBadgeText({text});
  browser.browserAction.setBadgeBackgroundColor({color: state.phase === "connected" ? "#247653" : "#ad462b"});
  browser.browserAction.setTitle({title: `Firefox WireGuard — ${state.phase}`});
});
browser.proxy.onRequest.addListener(details => controller.route(details), {urls: ["<all_urls>"]});
browser.webRequest.onBeforeRequest.addListener(details => controller.guard(details), {urls: ["<all_urls>"]}, ["blocking"]);
browser.proxy.onError.addListener(() => { if (controller.desired) controller.transportLost(); });
browser.runtime.onMessage.addListener(async (message, sender) => {
  // Only our own popup may send control commands, never a website/content script.
  if (sender.id !== browser.runtime.id || sender.url !== browser.runtime.getURL("popup.html")) return undefined;
  await controller.initialize();
  if (message?.command === "status") return controller.snapshot();
  if (message?.command === "refresh") return controller.refresh();
  if (message?.command === "connect" && typeof message.profileID === "string") return controller.connect(message.profileID);
  if (message?.command === "disconnect") return controller.disconnect();
  return undefined;
});
controller.initialize().then(() => controller.refresh());
setInterval(() => controller.refresh(), 2000);
