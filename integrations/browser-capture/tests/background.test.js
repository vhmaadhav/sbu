"use strict";

const assert = require("node:assert/strict");

const stored = {};
let messageListener;
let scheduledTimer;
let clearedTimer = null;
const deliveredBatches = [];

global.importScripts = () => {
  global.GleanSettings = { ensureDefaults: async () => {} };
};
global.setTimeout = (callback, delay) => {
  scheduledTimer = { callback, delay, id: 1 };
  return 1;
};
global.clearTimeout = (id) => {
  clearedTimer = id;
  scheduledTimer = null;
};
global.chrome = {
  storage: {
    local: {
      get: async (key) => ({ [key]: stored[key] }),
      set: async (values) => Object.assign(stored, values),
    },
  },
  runtime: {
    onInstalled: { addListener: () => {} },
    onStartup: { addListener: () => {} },
    onMessage: { addListener: (listener) => { messageListener = listener; } },
  },
  alarms: {
    create: () => {},
    onAlarm: { addListener: () => {} },
  },
};
global.fetch = async (_url, options) => {
  const batch = JSON.parse(options.body).events;
  deliveredBatches.push(batch);
  return {
    ok: true,
    json: async () => ({ accepted_event_ids: batch.map((event) => event.event_id) }),
  };
};

require("../background.js");

function send(message) {
  return new Promise((resolve) => {
    messageListener(message, {}, resolve);
  });
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  throw new Error("timed out waiting for background operation");
}

(async () => {
  await send({ type: "capture:enqueue", event: { event_id: "one" } });
  const firstTimer = scheduledTimer;
  await send({ type: "capture:enqueue", event: { event_id: "two" } });

  assert.equal(deliveredBatches.length, 0);
  assert.equal(firstTimer, scheduledTimer);
  assert.equal(scheduledTimer.delay, 750);

  scheduledTimer.callback();
  await waitFor(() => deliveredBatches.length === 1);
  assert.deepEqual(deliveredBatches[0].map((event) => event.event_id), ["one", "two"]);

  await send({ type: "capture:enqueue", event: { event_id: "three" } });
  assert.notEqual(scheduledTimer, null);
  await send({ type: "capture:flush" });
  await waitFor(() => deliveredBatches.length === 2);
  assert.equal(clearedTimer, 1);
  assert.deepEqual(deliveredBatches[1].map((event) => event.event_id), ["three"]);

  console.log("Glean extension background batching tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
