"use strict";

globalThis.GleanSettings = (() => {
  const ENABLED_KEY = "captureEnabled";
  const EXCLUSIONS_KEY = "excludedDomains";
  const DEFAULT_EXCLUDED_DOMAINS = Object.freeze([
    "mail.google.com",
    "mail.yahoo.com",
    "outlook.live.com",
    "outlook.office.com",
    "outlook.office365.com",
    "proton.me",
  ]);

  function normalizeDomain(value) {
    let candidate = String(value || "").trim().toLocaleLowerCase();
    if (!candidate) return null;
    try {
      if (candidate.includes("://")) candidate = new URL(candidate).hostname;
    } catch {
      return null;
    }
    candidate = candidate.replace(/^\*\./, "").split("/")[0].replace(/^\.+|\.+$/g, "");
    if (!candidate || !/^[a-z0-9.-]+$/.test(candidate) || candidate.includes("..")) return null;
    return candidate;
  }

  function normalizeDomains(values) {
    return [...new Set((values || []).map(normalizeDomain).filter(Boolean))].sort();
  }

  function isExcludedLocation(rawUrl, domains) {
    let hostname;
    try {
      hostname = new URL(rawUrl).hostname.toLocaleLowerCase();
    } catch {
      return true;
    }
    return normalizeDomains(domains).some(
      (domain) => hostname === domain || hostname.endsWith(`.${domain}`),
    );
  }

  async function read() {
    const stored = await chrome.storage.local.get([ENABLED_KEY, EXCLUSIONS_KEY]);
    return {
      enabled: stored[ENABLED_KEY] !== false,
      excludedDomains: Array.isArray(stored[EXCLUSIONS_KEY])
        ? normalizeDomains(stored[EXCLUSIONS_KEY])
        : [...DEFAULT_EXCLUDED_DOMAINS],
    };
  }

  async function ensureDefaults() {
    const stored = await chrome.storage.local.get([ENABLED_KEY, EXCLUSIONS_KEY]);
    const defaults = {};
    if (typeof stored[ENABLED_KEY] !== "boolean") defaults[ENABLED_KEY] = true;
    if (!Array.isArray(stored[EXCLUSIONS_KEY])) {
      defaults[EXCLUSIONS_KEY] = [...DEFAULT_EXCLUDED_DOMAINS];
    }
    if (Object.keys(defaults).length > 0) await chrome.storage.local.set(defaults);
  }

  return Object.freeze({
    ENABLED_KEY,
    EXCLUSIONS_KEY,
    DEFAULT_EXCLUDED_DOMAINS,
    normalizeDomain,
    normalizeDomains,
    isExcludedLocation,
    read,
    ensureDefaults,
  });
})();
