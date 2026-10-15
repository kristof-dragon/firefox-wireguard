"use strict";
(function (root) {
  function ip(value) {
    if (typeof value !== "string" || value.length > 45) return false;
    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(value)) return value.split(".").every(n => Number(n) <= 255);
    if (!/^[\da-f:.]+$/i.test(value) || !value.includes(":")) return false;
    try { return new URL(`http://[${value}]/`).hostname.startsWith("["); } catch { return false; }
  }
  function sanitize(value) {
    if (!value || typeof value.connectionID !== "string" || value.connectionID.length > 80) return null;
    const count = n => Number.isSafeInteger(n) && n >= 0 ? n : null;
    const stamp = n => typeof n === "number" && Number.isFinite(n) && n > 0 ? n : null;
    const addresses = list => Array.isArray(list) ? list.filter(ip) : [];
    // Copy only display fields. Neither configurations nor extra native fields
    // belong in the popup or extension storage.
    return {connectionID: value.connectionID, clientIPs: addresses(value.clientIPs), dnsServers: addresses(value.dnsServers),
      downloadedBytes: count(value.downloadedBytes), uploadedBytes: count(value.uploadedBytes),
      statsUpdatedAt: stamp(value.statsUpdatedAt), publicIP: ip(value.publicIP) ? value.publicIP : null,
      countryCode: /^[A-Z]{2}$/.test(value.countryCode || "") ? value.countryCode : null,
      exitStatus: ["waiting", "checking", "ready", "unavailable"].includes(value.exitStatus) ? value.exitStatus : "waiting"};
  }
  function countryFlag(code) {
    return /^[A-Z]{2}$/.test(code || "") ? String.fromCodePoint(...[...code].map(c => c.charCodeAt(0) + 127397)) : "🌐";
  }
  function byteLabel(bytes) {
    if (!Number.isSafeInteger(bytes) || bytes < 0) return "—";
    const units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"];
    let value = bytes, unit = 0;
    while (value >= 1000 && unit < units.length - 1) { value /= 1000; unit++; }
    return `${value.toLocaleString(undefined, {maximumFractionDigits: 1})} ${units[unit]}`;
  }
  root.FirefoxWGDetails = {sanitize, countryFlag, byteLabel};
  if (typeof module !== "undefined") module.exports = root.FirefoxWGDetails;
})(globalThis);
