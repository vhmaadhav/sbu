# Axiom Trace Reading Evidence

This unpacked Chrome extension is Axiom Trace's attention-aware reading-evidence adapter. It records eligible text only after 1.5 cumulative foreground
seconds, stores unsent events durably in `chrome.storage.local`, and delivers
batches to `http://127.0.0.1:8010/api/captures`.

## Demo setup

1. Start the Axiom Trace backend on port 8010.
2. Open `chrome://extensions`, enable developer mode, and choose **Load unpacked**.
3. Select this directory.
4. Keep capture enabled and browse a non-sensitive learning page.
5. Open **Adaptive path** in Axiom Trace to see the resulting evidence.

The extension accepts only loopback HTTP receivers. Capture can be paused at any
time, and domains can be excluded from the popup. Dwell time is a reading signal,
not proof of attention or understanding; only assessed responses update mastery.
