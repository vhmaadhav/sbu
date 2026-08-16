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

assert.deepEqual(AxiomTraceSettings.normalizeDomains([
  " HTTPS://Mail.Example.com/inbox ",
  "*.example.org",
  "mail.example.com",
  "not a domain",
]), ["example.org", "mail.example.com"]);

assert.equal(
  AxiomTraceSettings.isExcludedLocation("https://private.mail.example.com/message", ["mail.example.com"]),
  true,
);
assert.equal(
  AxiomTraceSettings.isExcludedLocation("https://example.com/article", ["mail.example.com"]),
  false,
);
assert.equal(AxiomTraceSettings.isExcludedLocation("not a URL", []), true);

console.log("Axiom Trace extension settings tests passed");
