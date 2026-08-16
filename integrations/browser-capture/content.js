"use strict";

(() => {
  const DWELL_THRESHOLD_MS = 1500;
  const URL_CHECK_INTERVAL_MS = 500;
  const MUTATION_DEBOUNCE_MS = 250;
  const MIN_TEXT_LENGTH = 40;
  const SELECTOR = "p, blockquote, article li, main li, article h1, article h2, article h3";

  let documentId = crypto.randomUUID();
  let currentUrl = location.href;
  let observer;
  let mutationObserver;
  let mutationTimer;
  let urlCheckTimer = null;
  let captureRunning = false;
  let elementStates = new WeakMap();
  let observedElements = new WeakSet();
  let emittedFingerprints = new Set();
  const pendingMutationRoots = new Set();
  const eligibleStates = new Set();

  function normalizeText(text) {
    return text.replace(/\s+/g, " ").trim();
  }

  function fingerprint(text) {
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16);
  }

  function isCaptureCandidate(element) {
    if (!(element instanceof HTMLElement)) return false;
    if (
      element.closest(
        "nav, footer, aside, form, dialog, input, textarea, [contenteditable='true'], [role='textbox'], [aria-live]",
      )
    ) return false;
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    return normalizeText(element.innerText || element.textContent || "").length >= MIN_TEXT_LENGTH;
  }

  function requiredVisibilityRatio(element) {
    const height = Math.max(element.getBoundingClientRect().height, 1);
    if (height <= window.innerHeight) return 0.5;
    return Math.min(0.5, (window.innerHeight * 0.35) / height);
  }

  function clearTimer(state) {
    if (state.timerId !== null) {
      clearTimeout(state.timerId);
      state.timerId = null;
    }
  }

  function stopInterval(state, now = performance.now()) {
    if (state.startedAt !== null) {
      state.accumulatedMs += Math.max(0, now - state.startedAt);
      state.startedAt = null;
    }
    clearTimer(state);
  }

  function makeCaptureEvent(state) {
    return {
      event_id: crypto.randomUUID(),
      source_type: "browser",
      source_uri: location.href,
      title: document.title || null,
      text: state.text,
      captured_at: new Date().toISOString(),
      dwell_ms: Math.round(state.accumulatedMs),
      metadata: {
        document_id: documentId,
        language: document.documentElement.lang || null,
      },
    };
  }

  function emitIfEligible(state) {
    if (state.emitted || state.accumulatedMs < DWELL_THRESHOLD_MS) return;
    if (emittedFingerprints.has(state.fingerprint)) {
      state.emitted = true;
      return;
    }
    state.emitted = true;
    emittedFingerprints.add(state.fingerprint);
    chrome.runtime.sendMessage({ type: "capture:enqueue", event: makeCaptureEvent(state) }, (response) => {
      if (chrome.runtime.lastError) {
        state.emitted = false;
        emittedFingerprints.delete(state.fingerprint);
        console.warn("Axiom Trace could not queue capture", chrome.runtime.lastError.message);
      } else if (!response?.queued) {
        state.emitted = false;
        emittedFingerprints.delete(state.fingerprint);
        console.warn("Axiom Trace capture queue rejected event", response?.error);
      }
    });
  }

  function scheduleThreshold(state) {
    clearTimer(state);
    const remaining = Math.max(0, DWELL_THRESHOLD_MS - state.accumulatedMs);
    state.timerId = setTimeout(() => {
      state.timerId = null;
      if (!state.isIntersecting || document.visibilityState !== "visible") return;
      stopInterval(state);
      emitIfEligible(state);
      if (!state.emitted) startInterval(state);
    }, remaining);
  }

  function startInterval(state) {
    if (state.emitted || state.startedAt !== null || document.visibilityState !== "visible") return;
    state.startedAt = performance.now();
    scheduleThreshold(state);
  }

  function stateFor(element) {
    let state = elementStates.get(element);
    if (!state) {
      const text = normalizeText(element.innerText || element.textContent || "");
      state = {
        text,
        fingerprint: fingerprint(text),
        accumulatedMs: 0,
        startedAt: null,
        timerId: null,
        isIntersecting: false,
        emitted: emittedFingerprints.has(fingerprint(text)),
      };
      elementStates.set(element, state);
    }
    return state;
  }

  function handleIntersections(entries) {
    const now = performance.now();
    for (const entry of entries) {
      const state = stateFor(entry.target);
      const qualifies = entry.isIntersecting && entry.intersectionRatio >= requiredVisibilityRatio(entry.target);
      state.isIntersecting = qualifies;
      if (qualifies) {
        eligibleStates.add(state);
        startInterval(state);
      } else {
        stopInterval(state, now);
        eligibleStates.delete(state);
        emitIfEligible(state);
      }
    }
  }

  function createObserver() {
    return new IntersectionObserver(handleIntersections, {
      root: null,
      threshold: [0, 0.1, 0.25, 0.5, 0.75],
    });
  }

  function observeCandidate(element) {
    if (observedElements.has(element) || !isCaptureCandidate(element)) return;
    observedElements.add(element);
    observer.observe(element);
  }

  function scan(root = document) {
    if (root instanceof Element && root.matches(SELECTOR)) observeCandidate(root);
    for (const element of root.querySelectorAll?.(SELECTOR) || []) observeCandidate(element);
  }

  function resetForNavigation() {
    if (!captureRunning) return;
    for (const state of eligibleStates) stopInterval(state);
    eligibleStates.clear();
    clearTimeout(mutationTimer);
    pendingMutationRoots.clear();
    observer.disconnect();
    documentId = crypto.randomUUID();
    currentUrl = location.href;
    elementStates = new WeakMap();
    observedElements = new WeakSet();
    emittedFingerprints = new Set();
    observer = createObserver();
    scan();
  }

  document.addEventListener("visibilitychange", () => {
    if (!captureRunning) return;
    if (document.visibilityState === "hidden") {
      const now = performance.now();
      for (const state of eligibleStates) {
        stopInterval(state, now);
        emitIfEligible(state);
      }
      chrome.runtime.sendMessage({ type: "capture:flush" });
    } else {
      for (const state of eligibleStates) startInterval(state);
    }
  });

  window.addEventListener("pagehide", () => {
    if (!captureRunning) return;
    const now = performance.now();
    for (const state of eligibleStates) stopInterval(state, now);
  });

  function handleMutations(mutations) {
    if (!captureRunning) return;
    for (const mutation of mutations) {
      if (mutation.target instanceof Element) pendingMutationRoots.add(mutation.target);
      if (mutation.type === "characterData" && mutation.target.parentElement) {
        pendingMutationRoots.add(mutation.target.parentElement);
      }
      for (const node of mutation.addedNodes) {
        if (node instanceof Element) pendingMutationRoots.add(node);
      }
    }
    clearTimeout(mutationTimer);
    mutationTimer = setTimeout(() => {
      for (const root of pendingMutationRoots) scan(root);
      pendingMutationRoots.clear();
    }, MUTATION_DEBOUNCE_MS);
  }

  function startCapture() {
    if (captureRunning) return;
    captureRunning = true;
    documentId = crypto.randomUUID();
    currentUrl = location.href;
    elementStates = new WeakMap();
    observedElements = new WeakSet();
    emittedFingerprints = new Set();
    observer = createObserver();
    mutationObserver = new MutationObserver(handleMutations);
    scan();
    mutationObserver.observe(document.documentElement, {
      childList: true,
      characterData: true,
      subtree: true,
    });
    if (urlCheckTimer === null) {
      urlCheckTimer = setInterval(() => {
        if (location.href !== currentUrl) void applyCaptureSettings(true);
      }, URL_CHECK_INTERVAL_MS);
    }
  }

  function stopCapture() {
    if (!captureRunning) return;
    captureRunning = false;
    const now = performance.now();
    for (const state of eligibleStates) stopInterval(state, now);
    eligibleStates.clear();
    pendingMutationRoots.clear();
    clearTimeout(mutationTimer);
    observer?.disconnect();
    mutationObserver?.disconnect();
    if (urlCheckTimer !== null) {
      clearInterval(urlCheckTimer);
      urlCheckTimer = null;
    }
  }

  async function applyCaptureSettings(resetForNewLocation = false) {
    const settings = await AxiomTraceSettings.read();
    const excluded = AxiomTraceSettings.isExcludedLocation(location.href, settings.excludedDomains);
    if (settings.enabled && !excluded) {
      if (captureRunning && resetForNewLocation) {
        resetForNavigation();
      } else {
        startCapture();
      }
    } else {
      if (resetForNewLocation) currentUrl = location.href;
      stopCapture();
    }
  }

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (
      areaName === "local" &&
      (changes[AxiomTraceSettings.ENABLED_KEY] || changes[AxiomTraceSettings.EXCLUSIONS_KEY])
    ) {
      void applyCaptureSettings();
    }
  });

  void applyCaptureSettings();
})();
