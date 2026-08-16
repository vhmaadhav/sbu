# Axiom Trace browser-capture checklist

Keep the Axiom Trace backend and extension service-worker consoles visible while testing. Use non-sensitive sample pages.

- [ ] Capture is enabled by default after a fresh extension install.
- [ ] Turning capture off in the popup stops new events on an already-open page.
- [ ] Adding the current hostname to exclusions stops capture before the dwell threshold.
- [ ] Excluding a parent hostname also excludes its subdomains.
- [ ] Removing an exclusion resumes capture without reinstalling the extension.
- [ ] Default webmail exclusions do not capture test content on those hosts.
- [ ] A paragraph visible for less than 1.5 seconds is not captured.
- [ ] A paragraph visible for at least 1.5 cumulative seconds is captured once.
- [ ] Switching tabs pauses dwell; background time is not counted.
- [ ] Hiding and returning to a paragraph resumes cumulative dwell.
- [ ] A paragraph taller than the viewport can still qualify.
- [ ] Rapid scrolling does not create a flood of captures.
- [ ] Infinite-scroll content added after load is observed.
- [ ] Same-document SPA navigation resets document identity and discovers new content.
- [ ] Two tabs maintain independent document IDs and both deliver events.
- [ ] Editable controls and contenteditable regions are not captured.
- [ ] The local receiver page is not captured.
- [ ] With the receiver stopped, events remain in `chrome.storage.local`.
- [ ] After the receiver restarts, queued events are acknowledged and removed.
- [ ] Reloading/terminating the MV3 service worker does not discard queued events.
- [ ] A non-loopback `receiverUrl` value is rejected.

Known Phase 1 limitation: sudden browser/process termination before an event reaches extension storage cannot be made fully reliable by a page teardown signal.
