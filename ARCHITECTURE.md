# Architecture Overview — Walled DLP

## High-Level Design

Walled DLP is implemented as two cooperating components:

| Component | Technology | Role |
|-----------|-----------|------|
| Chrome Extension (MV3) | JavaScript | Intercepts user actions in the browser |
| Native Messaging Host | Python 3 + tkinter | Shows native OS dialogs |

They communicate via **Chrome Native Messaging** — a secure, process-isolated IPC channel using stdin/stdout with a 4-byte length-prefixed JSON protocol.

---

## Component Detail

### 1. `manifest.json` (Extension Manifest v3)

Declares:
- `content_scripts` for `chatgpt.com` and `perplexity.ai`
- `nativeMessaging` permission
- `background` service worker

### 2. `background.js` (Service Worker)

- Maintains a persistent **NativePort** to `native_host.py`
- Receives `CHECK_SENSITIVE` messages from content scripts
- Forwards to native host and returns `{ allowed: true|false }`
- Uses a `requestId` map to match async responses

### 3. `common_dlp.js` (Shared Library)

Provides all shared logic, loaded before each site's content script:

```
containsMarker(text)       → boolean
scanFile(file)             → Promise<boolean>
  ├─ readTextFile()        → FileReader text
  ├─ extractPdfText()      → pdf.js text layers
  └─ scanImageFile()       → raw byte scan
askBackground(opts)        → Promise<boolean>
observeResponses(selectors) → MutationObserver
```

### 4. `content_chatgpt.js` / `content_perplexity.js`

Each site-specific script:

**Prompt Interception:**
```
capture-phase keydown (Enter)
   └─ getPromptText()
      └─ containsMarker() → askBackground()
         ├─ allowed → re-dispatch event
         └─ blocked → swallow event
capture-phase click (Send button)
   └─ same flow
```

**File Interception:**
```
MutationObserver → hooks new <input type="file">
onChange:
  forEach file:
    scanFile() → containsMarker()
       └─ askBackground()
          ├─ allowed → re-dispatch 'change'
          └─ blocked → reset input.value

fetch wrapper → intercepts multipart FormData POSTs
  forEach File in FormData:
    scanFile() → same flow → returns fake Response if blocked
```

**Response Coloring:**
```
MutationObserver (childList, subtree: true)
  → querySelectorAll(".prose, [data-message-author-role='assistant']")
  → el.style.setProperty("color", "#0d6efd", "important")
```

### 5. `native_host.py`

```
stdin → struct.unpack("<I") → 4-byte message length
      → json.loads(raw)     → { requestId, type, label, source }
      → show_dialog()       → tkinter Toplevel window
        ├─ "Continue" → { requestId, allowed: true }
        └─ "Cancel"   → { requestId, allowed: false }
      → struct.pack("<I") + json.dumps() → stdout
```

### 6. `install_host.py`

One-time setup:
1. Writes `run_host.bat` (Chrome requires `.exe` or `.bat` on Windows)
2. Writes `com.walled.dlp.json` with absolute paths + extension ID
3. Sets `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.walled.dlp`

---

## Data Flow: Prompt with WALLED_SENSITIVE

```
User presses Enter
  │
  ▼
content_chatgpt.js (capture phase)
  │  getPromptText() → "Hello WALLED_SENSITIVE world"
  │  containsMarker() → true
  │  event.preventDefault() + stopImmediatePropagation()
  │
  ▼
chrome.runtime.sendMessage({ type: "CHECK_SENSITIVE", ... })
  │
  ▼
background.js
  │  nativePort.postMessage({ requestId: 1, type: "prompt", ... })
  │
  ▼
native_host.py (Python)
  │  show_dialog() → tkinter window appears
  │
  ├─ User clicks "Continue"
  │    send_message({ requestId: 1, allowed: true })
  │    background → sendResponse({ allowed: true })
  │    content script: re-dispatch original event
  │    ChatGPT processes prompt normally ✓
  │
  └─ User clicks "Cancel"
       send_message({ requestId: 1, allowed: false })
       background → sendResponse({ allowed: false })
       content script: does nothing — user stays in composer ✓
```

## Data Flow: File Upload with WALLED_SENSITIVE

```
User selects file → <input type="file"> change event
  │
  ▼
hookFileInput handler (capture phase)
  │  scanFile(file):
  │    .pdf  → extractPdfText() via pdf.js → containsMarker()
  │    .txt  → readTextFile() → containsMarker()
  │    image → scanImageFile() (raw bytes) → containsMarker()
  │  → true
  │  event.stopImmediatePropagation()
  │
  ▼
askBackground({ contentType: "file", label: "secret.pdf", ... })
  │
  ▼
  ├─ Continue → re-dispatch 'change' → site uploads file normally ✓
  └─ Cancel   → input.value = ""     → file dropped silently ✓
```

---

## Why Native Messaging?

The spec requires a **native desktop dialog** (not a browser popup). Chrome's `chrome.windows.create` or `alert()` are browser UI — not native OS windows. Native Messaging is the standard, secure mechanism to bridge from a Chrome Extension to a local process that can call OS-level APIs (`tkinter`, Win32, etc.).

## Why PDF.js?

PDF files are binary; reading them as text would not extract the text layer. PDF.js (the same library used by Firefox's built-in PDF viewer) extracts the text layer from PDFs entirely in the browser — no server round-trip, no native process needed.

## Why Raw Byte Scan for Images?

True OCR would require a large model or external API — inappropriate for a lightweight DLP tool. Instead, we scan the raw file bytes as an ASCII string. This catches:
- Files mislabeled as images but containing text
- EXIF comments or metadata fields containing the marker
- Test scenarios where the marker is embedded in the binary

In production, an OCR step (e.g., Tesseract) or a dedicated DLP SDK would replace this.
