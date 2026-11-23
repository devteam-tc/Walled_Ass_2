# Architecture Overview — Walled DLP (Standalone Desktop App)

> [!IMPORTANT]
> This solution is a **standalone desktop application**. It does not use, and does not require, any browser extension, plugin, or add-on.

---

## High-Level Design

Walled DLP is implemented as a single Python process with two cooperating subsystems:

| Component | Technology | Role |
|-----------|-----------|------|
| **Control Panel** (`dlp_app.py`) | Python 3 + tkinter | Desktop GUI launcher; starts proxy; launches Chrome |
| **DLP Proxy Addon** (`dlp_proxy.py`) | Python 3 + mitmproxy | Intercepts HTTPS traffic; enforces DLP; shows dialogs; injects CSS |

They run in the same OS process. The proxy addon is loaded by `mitmdump` (mitmproxy's CLI) which is started programmatically as a background thread.

---

## Component Detail

### 1. `dlp_app.py` — Desktop Application Launcher

**Entry point.** Responsibilities:

- **`ProxyRunner`**: Runs `mitmdump` (mitmproxy) on `127.0.0.1:8080` as a daemon thread, loading `dlp_proxy.py` as the addon.
- **`find_chrome()` / `launch_chrome()`**: Locates the Chrome executable and launches it with `--proxy-server=http://127.0.0.1:8080` and a dedicated user data directory (no existing extensions or settings interfere).
- **`ControlPanel`**: A tkinter window showing proxy status, the proxy address, active protections, and buttons to open ChatGPT, Perplexity, or quit.

```
dlp_app.py
  ├─ ProxyRunner.start()
  │    └─ thread: mitmdump --listen-port 8080 -s dlp_proxy.py
  ├─ launch_chrome(port=8080)
  │    └─ chrome.exe --proxy-server=... --user-data-dir=.dlp_chrome_profile
  └─ ControlPanel.run()
       └─ tkinter mainloop (control panel window)
```

### 2. `dlp_proxy.py` — mitmproxy DLP Addon

The core DLP engine. mitmproxy calls its hooks for every intercepted HTTP flow.

#### `_contains_marker(data: bytes) → bool`

Scans raw bytes for `WALLED_SENSITIVE` using both UTF-8 and latin-1 encodings. This covers:
- Plain text prompts
- JSON API request bodies
- Multipart file uploads (all file types)
- Binary files with embedded text metadata

#### `_target_host(flow) → str | None`

Returns `"ChatGPT"`, `"Perplexity"`, or `None` based on the request hostname. Only flows to target hosts are processed; all other traffic passes through completely unmodified.

#### `_extract_text_snippets(content_type, body) → list`

Determines what kind of content the request carries (JSON, multipart, form-encoded, binary) and extracts a human-readable label for the dialog.

#### `WalledDLPAddon.request(flow)`

```
Incoming request to chatgpt.com / perplexity.ai
  │
  ├─ _target_host() → not targeted? → pass through
  ├─ body empty? → pass through
  ├─ _contains_marker(body)? → no? → pass through
  │
  ├─ _extract_text_snippets() → label
  ├─ _DialogManager.ask(msg_type, label, source)
  │    ├─ Posts dialog request to queue (non-blocking)
  │    └─ Blocks on threading.Event until user clicks
  │
  ├─ User clicks Continue → event set, allowed=True → forward request normally
  └─ User clicks Cancel  → event set, allowed=False
       └─ flow.response = HTTP 403 Forbidden (JSON error body)
              → browser receives 403, never reaches the AI platform
```

#### `WalledDLPAddon.response(flow)`

```
Incoming response from chatgpt.com / perplexity.ai
  │
  ├─ _target_host() → not targeted? → pass through
  ├─ content-type: text/html? → no? → pass through
  │
  └─ Inject <style id="walled-dlp-style"> before </head>
       CSS targets AI response containers on both platforms
       → el { color: #0d6efd !important }
```

#### `_DialogManager`

Tkinter must run on the main thread. Since mitmproxy's request hooks run on its async event loop thread, a dedicated dialog manager thread is used:

```
_DialogManager
  ├─ __init__: starts _tk_loop() on a daemon thread
  ├─ _tk_loop(): creates hidden Tk root; starts _poll() timer
  ├─ _poll(): every 100ms, drains queue and calls _show() for each item
  ├─ _show(): builds and displays one Toplevel dialog window
  └─ ask(msg_type, label, source):
       ├─ Puts dialog request on queue (called from proxy thread)
       └─ Blocks on threading.Event until dialog closed → returns bool
```

### 3. `install_cert.py` — CA Certificate Installer

One-time setup for production use:

1. Briefly runs mitmdump to generate `~/.mitmproxy/mitmproxy-ca-cert.cer`
2. Calls `certutil -addstore -user Root <cert>` to install it in the Windows user certificate store
3. After this, Chrome trusts the proxy's HTTPS interception without warnings

> `dlp_app.py` uses `--ignore-certificate-errors` as a development convenience so this step is optional for local testing.

---

## Data Flow: Prompt with WALLED_SENSITIVE

```
User types "Hello WALLED_SENSITIVE" in ChatGPT composer
  │
  ▼
User presses Enter / Send button
  │
  ▼
Chrome → POST https://chatgpt.com/backend-api/conversation
  │      {"model":"gpt-4o","messages":[{"content":"Hello WALLED_SENSITIVE"}]}
  │
  ▼  (routed through 127.0.0.1:8080)
  │
mitmproxy intercepts → WalledDLPAddon.request()
  │  _target_host() → "ChatGPT"
  │  _contains_marker(body) → True
  │  _extract_text_snippets() → ("prompt", "Hello WALLED_SENSITIVE")
  │
  ▼
_DialogManager.ask("prompt", "Hello WALLED_SENSITIVE", "ChatGPT")
  │  → tkinter Toplevel window appears on the desktop
  │
  ├─ User clicks "Continue"
  │    allowed = True
  │    request forwarded to ChatGPT servers → normal AI response ✓
  │
  └─ User clicks "Cancel"
       allowed = False
       flow.response = HTTP 403 {"error": "Blocked by Walled DLP"}
       Chrome receives 403 → prompt never reaches ChatGPT ✓
```

## Data Flow: File Upload with WALLED_SENSITIVE

```
User selects sensitive.pdf in ChatGPT's file picker
  │
  ▼
Chrome → POST https://chatgpt.com/backend-api/files
  │      Content-Type: multipart/form-data
  │      [binary PDF bytes containing WALLED_SENSITIVE]
  │
  ▼  (routed through 127.0.0.1:8080)
  │
mitmproxy intercepts → WalledDLPAddon.request()
  │  _target_host() → "ChatGPT"
  │  _contains_marker(body) → True  (raw byte scan finds the marker)
  │  _extract_text_snippets() → ("file", "<multipart upload>")
  │
  ▼
_DialogManager.ask("file", "<multipart upload>", "ChatGPT")
  │  → tkinter Toplevel window appears
  │
  ├─ Continue → file forwarded → ChatGPT processes it normally ✓
  └─ Cancel   → 403 returned  → file never reaches ChatGPT ✓
```

## Data Flow: AI Response Coloring

```
ChatGPT servers → HTTP 200 text/html (page load)
  │
  ▼  (through proxy)
  │
WalledDLPAddon.response()
  │  _target_host() → "ChatGPT"
  │  content-type: text/html → yes
  │
  └─ Inject before </head>:
       <style id="walled-dlp-style">
         .markdown.prose { color: #0d6efd !important; }
         [data-message-author-role='assistant'] .prose { color: #0d6efd !important; }
         /* ... Perplexity selectors ... */
       </style>

Browser renders page → AI response text appears in blue ✓
```

---

## Why This Architecture?

### Why mitmproxy instead of a browser extension?

The requirement is a **standalone desktop application**. Browser extensions run inside the browser sandbox and cannot be the solution. mitmproxy is an industry-standard HTTPS proxy used by security tools, corporate DLP appliances, and QA automation. It operates entirely as an OS-level process, completely independent of the browser.

### Why a local proxy instead of a system hook or VPN?

A local HTTPS proxy is the minimal, cross-platform, least-privileged approach:
- **No kernel drivers** required (unlike full VPN or OS-level packet inspection)
- **No admin rights** required at runtime (cert install uses `-user` store)
- **No network changes** persist after the app exits
- **Deterministic** — only traffic explicitly routed through the proxy is inspected

### Why tkinter for dialogs?

tkinter is Python's standard, built-in GUI toolkit. It produces genuine native OS windows (using the platform's window manager), not browser popups. It requires no additional installation and works on Windows 10/11 out of the box.

### Why a dedicated thread for tkinter?

mitmproxy's request hooks execute on asyncio's event loop thread. tkinter's `mainloop()` must run on the **main thread** (or its own dedicated thread on Windows). The `_DialogManager` resolves this by owning its own thread and using a `queue.Queue` + `threading.Event` to safely bridge the two concurrency domains.

---

## Test Coverage

| Test file | Tests | Coverage |
|-----------|-------|----------|
| `test_local.py` | 28 | Marker detection, CSS injection, host matching, file scanning, Chrome detection |
| `test_e2e_automated.py` | 15 | Full pipeline: addon structure, request blocking, response coloring, mock dialogs |
| **Total** | **43** | **Full DLP pipeline** |
