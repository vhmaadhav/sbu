"use strict";

importScripts("settings.js");

const DEFAULT_RECEIVER_URL = "http://127.0.0.1:8010/api/captures";
const QUEUE_KEY = "captureQueue";
const RECEIVER_KEY = "receiverUrl";
const FLUSH_ALARM = "flushCaptureQueue";
const MAX_QUEUE_EVENTS = 1000;
const MAX_BATCH_EVENTS = 50;
const FLUSH_COALESCE_MS = 750;

let queueOperation = Promise.resolve();
let flushTimerId = null;

function serialized(operation) {
  queueOperation = queueOperation.then(operation, operation);
  return queueOperation;
}

async function readQueue() {
  const stored = await chrome.storage.local.get(QUEUE_KEY);
  return Array.isArray(stored[QUEUE_KEY]) ? stored[QUEUE_KEY] : [];
}

async function writeQueue(queue) {
  await chrome.storage.local.set({ [QUEUE_KEY]: queue });
}

function isAllowedReceiver(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return (
      url.protocol === "http:" &&
      (url.hostname === "127.0.0.1" || url.hostname === "localhost") &&
      url.port === "8010"
    );
  } catch {
    return false;
  }
}

async function getReceiverUrl() {
  const stored = await chrome.storage.local.get(RECEIVER_KEY);
  const candidate = stored[RECEIVER_KEY] || DEFAULT_RECEIVER_URL;
  if (!isAllowedReceiver(candidate)) {
    console.warn("Axiom Trace rejected a non-loopback receiver URL; using the default.");
    return DEFAULT_RECEIVER_URL;
  }
  return candidate;
}

async function enqueue(event) {
  const queue = await readQueue();
  if (queue.some((queued) => queued.event_id === event.event_id)) {
    return { queued: true, duplicate: true };
  }

  queue.push(event);
  let dropped = 0;
  if (queue.length > MAX_QUEUE_EVENTS) {
    dropped = queue.length - MAX_QUEUE_EVENTS;
    queue.splice(0, dropped);
    console.warn(`Axiom Trace capture queue reached its limit; dropped ${dropped} oldest event(s).`);
  }
  await writeQueue(queue);
  return { queued: true, duplicate: false, dropped };
}

async function flush() {
  const queue = await readQueue();
  if (queue.length === 0) {
    return { sent: 0, remaining: 0 };
  }

  const batch = queue.slice(0, MAX_BATCH_EVENTS);
  const response = await fetch(await getReceiverUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ events: batch }),
  });

  if (!response.ok) {
    throw new Error(`capture receiver returned HTTP ${response.status}`);
  }

  const result = await response.json();
  const accepted = new Set(result.accepted_event_ids || []);
  if (accepted.size === 0) {
    throw new Error("capture receiver acknowledged no event IDs");
  }

  const remaining = queue.filter((event) => !accepted.has(event.event_id));
  await writeQueue(remaining);
  return { sent: queue.length - remaining.length, remaining: remaining.length };
}

function requestFlush() {
  return serialized(async () => {
    try {
      const result = await flush();
      if (result.sent > 0) {
        console.info("Axiom Trace capture batch delivered", result);
      }
      return result;
    } catch (error) {
      console.warn("Axiom Trace capture delivery deferred", error.message);
      return { sent: 0, deferred: true };
    }
  });
}

function cancelScheduledFlush() {
  if (flushTimerId !== null) {
    clearTimeout(flushTimerId);
    flushTimerId = null;
  }
}

function scheduleFlush() {
  if (flushTimerId !== null) return;
  flushTimerId = setTimeout(() => {
    flushTimerId = null;
    void requestFlush();
  }, FLUSH_COALESCE_MS);
}

function requestImmediateFlush() {
  cancelScheduledFlush();
  return requestFlush();
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(FLUSH_ALARM, { periodInMinutes: 0.5 });
  void GleanSettings.ensureDefaults();
  void requestImmediateFlush();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(FLUSH_ALARM, { periodInMinutes: 0.5 });
  void requestImmediateFlush();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === FLUSH_ALARM) {
    void requestImmediateFlush();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "capture:flush") {
    void requestImmediateFlush();
    sendResponse({ requested: true });
    return false;
  }

  if (!message || message.type !== "capture:enqueue" || !message.event) {
    return false;
  }

  serialized(() => enqueue(message.event))
    .then((result) => {
      sendResponse(result);
      scheduleFlush();
    })
    .catch((error) => sendResponse({ queued: false, error: error.message }));
  return true;
});
