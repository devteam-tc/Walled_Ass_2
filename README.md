# Walled DLP — Desktop Data Loss Prevention for ChatGPT & Perplexity

A lightweight **Chrome Extension + Native Messaging Host** that:

- 🔍 Monitors text prompts and file uploads on **ChatGPT** and **Perplexity**
- 🚨 Shows a **native OS dialog** whenever `WALLED_SENSITIVE` is detected
- 🎨 Changes the **color of all AI-generated responses** to blue on both platforms

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Chrome Browser                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Content Script (content_chatgpt.js / content_perplexity)  │ │
│  │  - Hooks Enter key + Send button (prompt interception)     │ │
│  │  - Hooks file <input> + fetch (file upload interception)   │ │
│  │  - Scans text / PDF / image for WALLED_SENSITIVE           │ │
│  │  - Colors AI response containers via MutationObserver      │ │
│  └────────────────────┬───────────────────────────────────────┘ │
│                       │ chrome.runtime.sendMessage              │
│  ┌────────────────────▼───────────────────────────────────────┐ │
│  │  Background Service Worker (background.js)                 │ │
│  │  - Receives CHECK_SENSITIVE from content scripts           │ │
│  │  - Forwards via Chrome Native Messaging to Python host     │ │
│  └────────────────────┬───────────────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────────────┘
                        │ stdin / stdout (4-byte length-prefixed JSON)
         ┌──────────────▼────────────────────────┐
         │  Python Native Host (native_host.py)   │
         │  - Receives message, shows tkinter     │
         │    dialog with Continue / Cancel       │
         │  - Returns { allowed: true|false }     │
         └───────────────────────────────────────┘
```

---

## Project Structure

```
walledai_assign2/
├── extension/                  ← Chrome Extension (load unpacked)
│   ├── manifest.json           ← MV3 manifest
│   ├── background.js           ← Service worker & native messaging bridge
│   ├── common_dlp.js           ← Shared DLP utilities (marker detection, PDF, file scan)
│   ├── content_chatgpt.js      ← ChatGPT content script
│   ├── content_perplexity.js   ← Perplexity content script
│   ├── icons/                  ← Extension icons (16, 48, 128 px)
│   └── lib/
│       ├── pdf.min.js          ← PDF.js (text extraction from PDFs)
│       └── pdf.worker.min.js   ← PDF.js worker
│
├── native_host/
│   ├── native_host.py          ← Python native messaging host (tkinter dialog)
│   ├── install_host.py         ← Registers host in Windows registry
│   └── com.walled.dlp.json     ← Native messaging manifest (auto-updated by installer)
│
├── install.ps1                 ← One-click PowerShell installer
├── generate_icons.py           ← Icon generator (already run)
└── README.md                   ← This file
```

---

## Setup Instructions

### Prerequisites
- **Windows 10/11**
- **Google Chrome** (or Chromium-based browser)
- **Python 3.8+** (must be on PATH — download from https://python.org)
- Python built-in `tkinter` (included in standard Windows Python install)

### Step 1 — Load the Chrome Extension

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (toggle top-right)
3. Click **Load unpacked**
4. Select the `extension/` folder inside this project
5. Note the **Extension ID** shown under the extension name (32-character string, e.g. `abcdefghijklmnopabcdefghijklmnop`)

### Step 2 — Install the Native Messaging Host

Open **PowerShell** in the project root and run:

```powershell
.\install.ps1 -ExtensionId YOUR_EXTENSION_ID_HERE
```

Replace `YOUR_EXTENSION_ID_HERE` with the ID from Step 1.

This script:
- Creates `native_host/run_host.bat` (Chrome-launchable wrapper)
- Updates `native_host/com.walled.dlp.json` with the correct paths
- Writes the registry key `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.walled.dlp`

### Step 3 — Restart Chrome

Close and reopen Chrome to pick up the registry change.

### Step 4 — Test

1. Go to [https://chatgpt.com](https://chatgpt.com) or [https://www.perplexity.ai](https://www.perplexity.ai)
2. Type a message containing `WALLED_SENSITIVE` and press Enter → native dialog appears
3. Upload a `.txt`, `.pdf`, or image file containing `WALLED_SENSITIVE` → native dialog appears
4. Observe that AI response text is colored **blue**

---

## How It Works

### Prompt Interception
- The content script attaches a **capture-phase** `keydown` listener for the Enter key on the prompt composer, and a `click` listener for the Send button.
- Before the event propagates to ChatGPT/Perplexity's own handlers, we check if `WALLED_SENSITIVE` is in the text.
- If found, `preventDefault()` + `stopImmediatePropagation()` pause the submission while the native dialog is shown.
- **Continue** → re-dispatch the original event so the site processes it normally.
- **Cancel** → do nothing; the user can edit and retry.

### File Upload Interception
- All `<input type="file">` elements are hooked via a MutationObserver.
- On `change`, each file is read with the FileReader API and scanned:
  - **Text files** → `FileReader.readAsText()`
  - **PDFs** → parsed with **PDF.js** (bundled) to extract text layers
  - **Images** → raw bytes scanned as latin-1 string (catches embedded text markers)
- A `fetch` wrapper also intercepts `multipart/form-data` POSTs for drag-drop uploads.

### Native Desktop Dialog
- The background service worker uses **Chrome Native Messaging** to spawn/communicate with `native_host.py` via stdin/stdout (4-byte length-prefixed JSON protocol).
- `native_host.py` uses Python's built-in **tkinter** to show a styled desktop window — not a browser popup.
- The dialog clearly labels whether the detection was in a prompt or file, and names the source platform.

### Response Coloring
- A `MutationObserver` watches the DOM for new AI response containers.
- Matching elements get `color: #0d6efd !important` applied inline.
- Selectors target the actual prose containers used by each platform's current UI.

---

## Supported File Formats

| Format | Detection Method |
|--------|-----------------|
| `.txt`, `.csv`, etc. | FileReader text read |
| `.pdf` | PDF.js text layer extraction |
| `.png`, `.jpg`, `.gif`, `.webp`, `.bmp` | Raw byte scan for embedded ASCII marker |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Native dialog doesn't appear | Re-run `install.ps1` with the correct Extension ID; check `chrome://extensions` for the ID |
| "Native host has exited" in console | Confirm Python is on PATH; check that `run_host.bat` path is correct |
| PDF not scanned | Ensure `lib/pdf.min.js` and `lib/pdf.worker.min.js` exist in `extension/lib/` |
| Response color not applied | The site may have updated its DOM structure; check browser console for `[Walled DLP]` logs |
| Registry key missing | Run PowerShell as your user (not admin) — the key goes under `HKCU`, not `HKLM` |

---

## Security Notes

- The marker `WALLED_SENSITIVE` is intentionally simple and literal. In production, this would be replaced by regex patterns, ML classification, or integration with a DLP policy engine.
- The native host is scoped to the specific Chrome extension ID — other extensions cannot trigger it.
- File content is inspected **client-side** (in the browser); no content is sent to any external service.
