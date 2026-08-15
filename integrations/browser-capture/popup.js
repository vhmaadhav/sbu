"use strict";

const enabledInput = document.querySelector("#capture-enabled");
const exclusionsInput = document.querySelector("#excluded-domains");
const saveButton = document.querySelector("#save");
const status = document.querySelector("#status");

async function loadSettings() {
  const settings = await GleanSettings.read();
  enabledInput.checked = settings.enabled;
  exclusionsInput.value = settings.excludedDomains.join("\n");
}

async function saveSettings() {
  const excludedDomains = GleanSettings.normalizeDomains(exclusionsInput.value.split(/\r?\n/));
  await chrome.storage.local.set({
    [GleanSettings.ENABLED_KEY]: enabledInput.checked,
    [GleanSettings.EXCLUSIONS_KEY]: excludedDomains,
  });
  exclusionsInput.value = excludedDomains.join("\n");
  status.textContent = enabledInput.checked ? "Settings saved." : "Capture paused.";
}

saveButton.addEventListener("click", () => {
  saveButton.disabled = true;
  saveSettings()
    .catch(() => {
      status.textContent = "Could not save settings.";
    })
    .finally(() => {
      saveButton.disabled = false;
    });
});

loadSettings().catch(() => {
  status.textContent = "Could not load settings.";
});
