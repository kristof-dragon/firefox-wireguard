// SPDX-License-Identifier: MPL-2.0
"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {NativeClient} = require("../controller.js");

function fixture(timeout = 50) {
  const ports = [];
  let losses = 0;
  const browser = {runtime: {connectNative() {
    const port = {closed: false, sent: [],
      onMessage: {addListener(fn) { port.message = fn; }},
      onDisconnect: {addListener(fn) { port.lost = fn; }},
      postMessage(value) { if (port.closed) throw new Error("closed"); port.sent.push(value); },
      // Deliberately no callback: this matches Firefox's local disconnect API.
      disconnect() { port.closed = true; }};
    ports.push(port); return port;
  }}};
  const client = new NativeClient(browser, () => losses++, timeout);
  return {client, ports, losses: () => losses};
}

test("native timeout rejects pending calls and opens a fresh port for retry", async () => {
  const {client, ports, losses} = fixture();
  const first = client.request("status", "client"), second = client.request("status", "client");
  await Promise.all([assert.rejects(first, /did not respond/), assert.rejects(second, /did not respond/)]);
  assert.equal(losses(), 1); assert.equal(ports[0].closed, true); assert.equal(client.pending.size, 0);
  const retry = client.request("status", "client");
  assert.equal(ports.length, 2);
  ports[1].message({version: 1, id: ports[1].sent[0].id, ok: true});
  assert.equal((await retry).ok, true);
});

test("remote disconnect closes all pending requests and ignores stale replies", async () => {
  const {client, ports, losses} = fixture();
  const first = client.request("status", "client");
  const failed = assert.rejects(first, /unavailable/);
  ports[0].lost(); await failed;
  const retry = client.request("status", "client");
  ports[0].message({version: 1, id: ports[1].sent[0].id, ok: false});
  ports[1].message({version: 1, id: ports[1].sent[0].id, ok: true});
  assert.equal((await retry).ok, true); assert.equal(losses(), 1);
});
