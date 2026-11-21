/**
 * content_chatgpt.js — DLP content script for https://chatgpt.com
 *
 * Responsibilities:
 *  1. Intercept text prompt submission (Enter key / Send button)
 *  2. Intercept file uploads before they reach the server
 *  3. Color all AI-generated response text
 */

(function () {
  "use strict";

  const SOURCE = "ChatGPT";
  const { containsMarker, scanFile, askBackground, observeResponses } = window.__walledDLP;

  // ── 1. Response Coloring ────────────────────────────────────────────────────
  // ChatGPT renders assistant messages inside markdown prose containers.
  // Selectors are ordered from most specific to broadest fallback.
  const RESPONSE_SELECTORS = [
    // Main response prose container (GPT-4o / latest UI)
    ".markdown.prose",
    // Fallback: any assistant turn container
    "[data-message-author-role='assistant'] .prose",
    "[data-message-author-role='assistant']",
  ];

  observeResponses(RESPONSE_SELECTORS);

  // ── 2. Prompt Interception ──────────────────────────────────────────────────

  /**
   * Get the current text from the ChatGPT prompt textarea / contenteditable.
   */
  function getPromptText() {
    // ChatGPT uses a <div contenteditable> as its composer
    const composer =
      document.querySelector("#prompt-textarea") ||
      document.querySelector("div[contenteditable='true'][data-id]") ||
      document.querySelector("div[contenteditable='true']");
    return composer ? (composer.innerText || composer.textContent || "") : "";
  }

  /**
   * Intercept prompt submission.
   * We hook both the Enter keydown and the send button click.
   * Returns true (don't block) or false (block).
   */
  async function handlePromptSubmit(event) {
    const text = getPromptText().trim();
    if (!text) return; // empty — let it through

    if (!containsMarker(text)) return; // no marker — allow

    // Marker found: ask the native host
    event.preventDefault();
    event.stopImmediatePropagation();

    const label   = text.length > 120 ? text.slice(0, 120) + "…" : text;
    const allowed = await askBackground({ contentType: "prompt", label, source: SOURCE });

    if (allowed) {
      // Re-dispatch the original event so ChatGPT processes it normally
      event.target.dispatchEvent(new event.constructor(event.type, event));
    }
    // If !allowed: do nothing — user stays in the composer
  }

  // ── Keyboard hook ──────────────────────────────────────────────────────────
  document.addEventListener(
    "keydown",
    async (e) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      const active = document.activeElement;
      if (!active) return;
      const isComposer =
        active.id === "prompt-textarea" ||
        (active.contentEditable === "true" && active.closest("form"));
      if (!isComposer) return;
      await handlePromptSubmit(e);
    },
    true // capture phase — before ChatGPT's own handlers
  );

  // ── Send button hook ───────────────────────────────────────────────────────
  document.addEventListener(
    "click",
    async (e) => {
      const btn = e.target.closest(
        "button[data-testid='send-button'], button[aria-label='Send prompt'], button[aria-label='Send message']"
      );
      if (!btn) return;
      await handlePromptSubmit(e);
    },
    true
  );

  // ── 3. File Upload Interception ─────────────────────────────────────────────

  /**
   * Hook a file <input> element to scan files before ChatGPT processes them.
   */
  function hookFileInput(input) {
    if (input.__walledHooked) return;
    input.__walledHooked = true;

    input.addEventListener(
      "change",
      async (e) => {
        const files = Array.from(input.files || []);
        if (!files.length) return;

        for (const file of files) {
          const hasSensitive = await scanFile(file);
          if (hasSensitive) {
            // Stop change propagation so ChatGPT does not upload yet
            e.stopImmediatePropagation();

            const allowed = await askBackground({
              contentType: "file",
              label:       file.name,
              source:      SOURCE,
            });

            if (allowed) {
              // Re-fire the change event so ChatGPT picks up the file
              input.dispatchEvent(new Event("change", { bubbles: true }));
            } else {
              // Reset the input so the file is dropped
              input.value = "";
            }
            return; // Handle one sensitive file at a time
          }
        }
      },
      true
    );
  }

  // Observe DOM for dynamically added file inputs
  function hookAllFileInputs() {
    document.querySelectorAll("input[type='file']").forEach(hookFileInput);
  }

  hookAllFileInputs();

  const fileInputObserver = new MutationObserver(hookAllFileInputs);
  fileInputObserver.observe(document.body, { childList: true, subtree: true });

  // ── DataTransfer / XHR intercept for drag-drop uploads ────────────────────
  // Some ChatGPT drag-drop flows bypass the input element. We also hook
  // the native fetch/XHR to block uploads of sensitive files at network level.
  const _fetch = window.fetch;
  window.fetch = async function (resource, init) {
    // We only need to inspect multipart form data POSTs
    if (init && init.method === "POST" && init.body instanceof FormData) {
      for (const [, value] of init.body.entries()) {
        if (value instanceof File) {
          const hasSensitive = await scanFile(value);
          if (hasSensitive) {
            const allowed = await askBackground({
              contentType: "file",
              label:       value.name,
              source:      SOURCE,
            });
            if (!allowed) {
              // Return a fake aborted response
              return new Response(null, { status: 0, statusText: "Blocked by Walled DLP" });
            }
          }
        }
      }
    }
    return _fetch.apply(this, arguments);
  };

  console.log("[Walled DLP] ChatGPT content script active.");
})();
