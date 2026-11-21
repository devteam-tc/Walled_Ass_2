/**
 * content_perplexity.js — DLP content script for https://www.perplexity.ai
 *
 * Responsibilities:
 *  1. Intercept text prompt submission (Enter key / Send button)
 *  2. Intercept file uploads before they reach the server
 *  3. Color all AI-generated response text
 */

(function () {
  "use strict";

  const SOURCE = "Perplexity";
  const { containsMarker, scanFile, askBackground, observeResponses } = window.__walledDLP;

  // ── 1. Response Coloring ────────────────────────────────────────────────────
  // Perplexity renders answer text in prose containers.
  const RESPONSE_SELECTORS = [
    // Primary answer text block
    ".prose",
    // Answer section wrapper
    "[class*='answer'] .prose",
    // Generic fallback
    "[class*='answer-text']",
    "[class*='response-content']",
  ];

  observeResponses(RESPONSE_SELECTORS);

  // ── 2. Prompt Interception ──────────────────────────────────────────────────

  function getPromptText() {
    // Perplexity uses a <textarea> or contenteditable div
    const textarea = document.querySelector("textarea[placeholder]");
    if (textarea) return textarea.value || "";

    const editable = document.querySelector("div[contenteditable='true']");
    return editable ? (editable.innerText || editable.textContent || "") : "";
  }

  async function handlePromptSubmit(event) {
    const text = getPromptText().trim();
    if (!text) return;
    if (!containsMarker(text)) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const label   = text.length > 120 ? text.slice(0, 120) + "…" : text;
    const allowed = await askBackground({ contentType: "prompt", label, source: SOURCE });

    if (allowed) {
      event.target.dispatchEvent(new event.constructor(event.type, event));
    }
  }

  // ── Keyboard hook ──────────────────────────────────────────────────────────
  document.addEventListener(
    "keydown",
    async (e) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      const active = document.activeElement;
      if (!active) return;
      const isComposer =
        active.tagName === "TEXTAREA" ||
        (active.contentEditable === "true");
      if (!isComposer) return;
      await handlePromptSubmit(e);
    },
    true
  );

  // ── Send button hook ───────────────────────────────────────────────────────
  document.addEventListener(
    "click",
    async (e) => {
      // Perplexity uses a submit button or an arrow icon button
      const btn = e.target.closest(
        "button[type='submit'], button[aria-label*='submit' i], button[aria-label*='search' i], button[aria-label*='ask' i], button[aria-label*='send' i]"
      );
      if (!btn) return;
      await handlePromptSubmit(e);
    },
    true
  );

  // ── 3. File Upload Interception ─────────────────────────────────────────────

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
            e.stopImmediatePropagation();

            const allowed = await askBackground({
              contentType: "file",
              label:       file.name,
              source:      SOURCE,
            });

            if (allowed) {
              input.dispatchEvent(new Event("change", { bubbles: true }));
            } else {
              input.value = "";
            }
            return;
          }
        }
      },
      true
    );
  }

  function hookAllFileInputs() {
    document.querySelectorAll("input[type='file']").forEach(hookFileInput);
  }

  hookAllFileInputs();

  const fileInputObserver = new MutationObserver(hookAllFileInputs);
  fileInputObserver.observe(document.body, { childList: true, subtree: true });

  // ── Fetch intercept ────────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (resource, init) {
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
              return new Response(null, { status: 0, statusText: "Blocked by Walled DLP" });
            }
          }
        }
      }
    }
    return _fetch.apply(this, arguments);
  };

  console.log("[Walled DLP] Perplexity content script active.");
})();
