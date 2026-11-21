/**
 * background.js — Service Worker (Manifest V3)
 *
 * Acts as the bridge between content scripts and the Python native host.
 * Content scripts send a "CHECK_SENSITIVE" message; this worker forwards it
 * to the native host, which shows the OS dialog, and returns the decision.
 *
 * Message flow:
 *   Content Script  →  background (CHECK_SENSITIVE)
 *   background      →  native host (nativeMessaging)
 *   native host     →  OS dialog (tkinter)
 *   native host     →  background  { allowed: true|false }
 *   background      →  Content Script { allowed: true|false }
 */

const NATIVE_HOST = "com.walled.dlp";

// Keep a single persistent port to the native host to avoid repeated spawning.
let nativePort = null;
// Map of pending requests: requestId → { resolve, reject }
const pending = new Map();
let reqCounter = 0;

function getNativePort() {
  if (nativePort) return nativePort;

  nativePort = chrome.runtime.connectNative(NATIVE_HOST);

  nativePort.onMessage.addListener((msg) => {
    // msg = { requestId, allowed }
    const handler = pending.get(msg.requestId);
    if (handler) {
      pending.delete(msg.requestId);
      handler.resolve(msg.allowed);
    }
  });

  nativePort.onDisconnect.addListener(() => {
    console.warn("[Walled DLP] Native host disconnected:", chrome.runtime.lastError?.message);
    nativePort = null;
    // Reject all pending with "allow" so the user is not stuck
    for (const [id, handler] of pending) {
      handler.resolve(true);
    }
    pending.clear();
  });

  return nativePort;
}

/**
 * Ask native host whether to allow this action.
 * @param {object} payload - { type, label, source }
 *   type   : "prompt" | "file"
 *   label  : text snippet or filename
 *   source : "ChatGPT" | "Perplexity"
 * @returns {Promise<boolean>} true = allow, false = block
 */
function askNativeHost(payload) {
  return new Promise((resolve, reject) => {
    const requestId = ++reqCounter;
    pending.set(requestId, { resolve, reject });

    try {
      const port = getNativePort();
      port.postMessage({ requestId, ...payload });
    } catch (err) {
      pending.delete(requestId);
      console.error("[Walled DLP] Failed to send to native host:", err);
      // Fail-open: allow if native host is not reachable
      resolve(true);
    }
  });
}

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CHECK_SENSITIVE") {
    askNativeHost({
      type:   message.contentType,  // "prompt" or "file"
      label:  message.label,
      source: message.source,       // "ChatGPT" or "Perplexity"
    }).then((allowed) => {
      sendResponse({ allowed });
    }).catch(() => {
      sendResponse({ allowed: true });
    });

    // Return true to keep the message channel open for async sendResponse
    return true;
  }
});
