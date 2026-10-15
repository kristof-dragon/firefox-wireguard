// SPDX-License-Identifier: MPL-2.0
"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {sanitize, countryFlag, byteLabel} = require("../details.js");

test("formats country flags and connection byte totals", () => {
  assert.equal(countryFlag("GB"), "🇬🇧"); assert.equal(countryFlag(null), "🌐");
  assert.equal(countryFlag("<script>"), "🌐");
  assert.equal(byteLabel(0), "0 B"); assert.equal(byteLabel(1_000_000), "1 MB");
  for (const value of [null, undefined, -1, NaN, Infinity, 2 ** 64]) assert.equal(byteLabel(value), "—");
});
test("keeps only validated display fields from native state", () => {
  const result = sanitize({connectionID: "fixture", clientIPs: ["192.0.2.2", "2001:db8::2", "::ffff:192.0.2.3", "bad"],
    dnsServers: ["192.0.2.1", "999.0.0.1", "<script>"], publicIP: "203.0.113.8", countryCode: "GB",
    downloadedBytes: 0, uploadedBytes: -1, statsUpdatedAt: Infinity, exitStatus: "ready", privateKey: "not-a-key"});
  assert.deepEqual(result.clientIPs, ["192.0.2.2", "2001:db8::2", "::ffff:192.0.2.3"]);
  assert.deepEqual(result.dnsServers, ["192.0.2.1"]);
  assert.equal(result.downloadedBytes, 0); assert.equal(result.uploadedBytes, null);
  assert.equal(result.statsUpdatedAt, null); assert.equal(result.privateKey, undefined);
  assert.equal(result.publicIP, "203.0.113.8");
  assert.equal(sanitize(null), null); assert.equal(sanitize({}), null);
});
