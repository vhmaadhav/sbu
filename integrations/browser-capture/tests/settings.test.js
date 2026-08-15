"use strict";

const assert = require("node:assert/strict");

global.chrome = {
  storage: {
    local: {
      get: async () => ({}),
      set: async () => {},
    },
  },
};

require("../settings.js");

assert.deepEqual(GleanSettings.normalizeDomains([
  " HTTPS://Mail.Example.com/inbox ",
  "*.example.org",
  "mail.example.com",
  "not a domain",
]), ["example.org", "mail.example.com"]);

assert.equal(
  GleanSettings.isExcludedLocation("https://private.mail.example.com/message", ["mail.example.com"]),
  true,
);
assert.equal(
  GleanSettings.isExcludedLocation("https://example.com/article", ["mail.example.com"]),
  false,
);
assert.equal(GleanSettings.isExcludedLocation("not a URL", []), true);

console.log("Glean extension settings tests passed");
