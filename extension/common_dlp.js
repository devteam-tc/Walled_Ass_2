/**
 * common_dlp.js — Shared DLP utilities
 *
 * Loaded by both content_chatgpt.js and content_perplexity.js.
 * Provides:
 *   - MARKER constant
 *   - containsMarker(text) → boolean
 *   - scanFile(file) → Promise<boolean>   (checks text, PDF, image via OCR-free text extraction)
 *   - askBackground(payload) → Promise<boolean>
 *   - applyResponseColor(rootEl, color)  (colors AI response text)
 *   - observeResponses(selector, color)  (MutationObserver wrapper)
 */

// ─── Constants ────────────────────────────────────────────────────────────────
const WALLED_MARKER = "WALLED_SENSITIVE";
const RESPONSE_COLOR = "#0d6efd"; // Blue — clearly distinguishable

// ─── Text Detection ───────────────────────────────────────────────────────────
function containsMarker(text) {
  return typeof text === "string" && text.includes(WALLED_MARKER);
}

// ─── File Scanning ────────────────────────────────────────────────────────────

/**
 * Read a plain text file as string.
 */
function readTextFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = (e) => resolve(e.target.result);
    reader.onerror = () => reject(new Error("FileReader error"));
    reader.readAsText(file);
  });
}

/**
 * Read file as ArrayBuffer (used for PDF parsing).
 */
function readArrayBuffer(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = (e) => resolve(e.target.result);
    reader.onerror = () => reject(new Error("FileReader error"));
    reader.readAsArrayBuffer(file);
  });
}

/**
 * Extract text from a PDF using pdf.js (bundled as lib/pdf.min.js).
 * Returns all page text concatenated.
 */
async function extractPdfText(file) {
  try {
    const buffer = await readArrayBuffer(file);
    // pdfjsLib is exposed by lib/pdf.min.js
    if (typeof pdfjsLib === "undefined") return "";

    // Set worker source — use bundled worker stub
    pdfjsLib.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL("lib/pdf.worker.min.js");

    const pdf  = await pdfjsLib.getDocument({ data: new Uint8Array(buffer) }).promise;
    let text = "";
    for (let i = 1; i <= pdf.numPages; i++) {
      const page    = await pdf.getPage(i);
      const content = await page.getTextContent();
      text += content.items.map((item) => item.str).join(" ") + "\n";
    }
    return text;
  } catch (err) {
    console.warn("[Walled DLP] PDF extraction error:", err);
    return "";
  }
}

/**
 * For image files: attempt to extract any embedded text metadata / EXIF comment,
 * and also read the raw bytes as latin-1 to catch plaintext marker embedded in
 * the binary (a common steganographic or test scenario).
 * Full OCR is out-of-scope for a lightweight tool; we scan raw bytes instead.
 */
async function scanImageFile(file) {
  try {
    const buffer = await readArrayBuffer(file);
    // Convert bytes to a latin-1 string to look for the ASCII marker
    const bytes = new Uint8Array(buffer);
    let raw = "";
    for (let i = 0; i < bytes.length; i++) {
      raw += String.fromCharCode(bytes[i]);
    }
    return containsMarker(raw);
  } catch (err) {
    console.warn("[Walled DLP] Image scan error:", err);
    return false;
  }
}

/**
 * Scan a file for the WALLED_SENSITIVE marker.
 * Dispatches to the right reader based on MIME type / extension.
 * @param {File} file
 * @returns {Promise<boolean>} true if marker found
 */
async function scanFile(file) {
  const name = (file.name || "").toLowerCase();
  const type = (file.type || "").toLowerCase();

  // ── PDF ──
  if (type === "application/pdf" || name.endsWith(".pdf")) {
    const text = await extractPdfText(file);
    return containsMarker(text);
  }

  // ── Image ──
  if (type.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|tiff?)$/.test(name)) {
    return scanImageFile(file);
  }

  // ── Plain text (default) ──
  try {
    const text = await readTextFile(file);
    return containsMarker(text);
  } catch {
    return false;
  }
}

// ─── Communication with Background ───────────────────────────────────────────

/**
 * Send a CHECK_SENSITIVE request to the background service worker.
 * @param {object} opts
 *   contentType : "prompt" | "file"
 *   label       : string (prompt excerpt or filename)
 *   source      : "ChatGPT" | "Perplexity"
 * @returns {Promise<boolean>} true = user chose Continue
 */
function askBackground(opts) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      {
        type:        "CHECK_SENSITIVE",
        contentType: opts.contentType,
        label:       opts.label,
        source:      opts.source,
      },
      (response) => {
        if (chrome.runtime.lastError) {
          console.warn("[Walled DLP] Background comms error:", chrome.runtime.lastError.message);
          resolve(true); // fail-open
        } else {
          resolve(response?.allowed ?? true);
        }
      }
    );
  });
}

// ─── Response Coloring ────────────────────────────────────────────────────────

/**
 * Apply color to all descendant text nodes / elements inside a response container.
 * We set color on the container itself; CSS cascade handles children.
 * @param {Element} el
 */
function colorResponseElement(el) {
  el.style.setProperty("color", RESPONSE_COLOR, "important");
  el.setAttribute("data-walled-colored", "1");
}

/**
 * Observe the DOM for new AI response containers matching `selectors`
 * and apply the response color whenever they appear.
 * @param {string[]} selectors - CSS selectors for response containers
 */
function observeResponses(selectors) {
  const selectorStr = selectors.join(", ");

  function colorAll() {
    document.querySelectorAll(selectorStr).forEach((el) => {
      if (!el.hasAttribute("data-walled-colored")) {
        colorResponseElement(el);
      }
    });
  }

  // Color anything already in DOM
  colorAll();

  const observer = new MutationObserver(() => colorAll());
  observer.observe(document.body, {
    childList: true,
    subtree:   true,
  });

  return observer;
}

// Expose globals for content scripts
window.__walledDLP = {
  WALLED_MARKER,
  RESPONSE_COLOR,
  containsMarker,
  scanFile,
  askBackground,
  observeResponses,
};
