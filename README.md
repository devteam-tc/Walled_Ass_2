# Walled DLP — Standalone Desktop Data Loss Prevention

A **standalone Python desktop application** that monitors and enforces DLP (Data Loss Prevention) policy on **ChatGPT** and **Perplexity** — with **no browser extension required**.

> [!IMPORTANT]
> This solution is a pure desktop application. It does **not** use and does **not** require any browser extension, plugin, or add-on (Chrome, Edge, Firefox or otherwise).

---

## What It Does

| Feature | Detail |
|---------|--------|
| 🔍 **Prompt interception** | Detects `WALLED_SENSITIVE` in text prompts before they reach the AI platform |
| 📎 **File upload interception** | Detects the marker in uploaded files (text, PDF, images) at the network level |
| 🚨 **Native OS dialog** | Shows a native tkinter desktop dialog — Continue or Cancel |
| 🎨 **Response coloring** | Colors AI-generated response text blue on both platforms |
| 🔒 **No browser extension** | Works by running a local HTTPS proxy (mitmproxy) — no extension installed |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Walled DLP Desktop Application (dlp_app.py)                       │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Control Panel (tkinter window)                              │  │
│  │  - Shows proxy status and address                           │  │
│  │  - Open ChatGPT / Open Perplexity buttons                   │  │
│  │  - Quit button (terminates everything cleanly)              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  ProxyRunner (background thread)                             │  │
│  │  - Runs mitmdump on port 8080                                │  │
│  │  - Loads dlp_proxy.py addon                                  │  │
│  └───────────────────────┬─────────────────────────────────────┘  │
└──────────────────────────┼─────────────────────────────────────────┘
                           │  HTTP/S proxy (port 8080)
           ┌───────────────▼────────────────────────┐
           │  WalledDLPAddon (dlp_proxy.py)           │
           │                                          │
           │  request() hook:                         │
           │    ├─ Check host ∈ {chatgpt.com, ...}    │
           │    ├─ Scan body for WALLED_SENSITIVE      │
           │    │    ├─ JSON prompt body               │
           │    │    ├─ Multipart file upload          │
           │    │    └─ Raw binary / text              │
           │    ├─ Show native tkinter dialog          │
           │    │    ├─ Continue → forward request     │
           │    │    └─ Cancel  → return 403 Forbidden │
           │                                          │
           │  response() hook:                        │
           │    └─ Inject CSS into HTML responses     │
           │       → colors AI replies blue           │
           └──────────────┬───────────────────────────┘
                          │  HTTPS traffic (port 443)
           ┌──────────────▼────────────────────────────┐
           │  Google Chrome (--proxy-server=127.0.0.1:8080) │
           │  Dedicated profile — no extensions needed  │
           └───────────────────────────────────────────┘
```

---

## Project Structure

```
walledai_assign2/
├── dlp_app.py              ← Main desktop application launcher (tkinter + mitmproxy)
├── dlp_proxy.py            ← mitmproxy addon: DLP request/response hooks
├── install_cert.py         ← One-time CA cert installer (optional — for production)
│
├── test_local.py           ← Unit tests (marker detection, CSS injection, host matching)
├── test_e2e_automated.py   ← End-to-end automated tests (mocked flows, full pipeline)
│
├── test_clean.txt          ← Test file: clean content (no marker)
├── test_sensitive.txt      ← Test file: contains WALLED_SENSITIVE
├── test_sensitive.pdf      ← Test file: contains WALLED_SENSITIVE
├── test_sensitive.png      ← Test file: contains WALLED_SENSITIVE
│
├── native_host/            ← [Legacy] Original native messaging host (kept for reference)
└── extension/              ← [Legacy] Original Chrome extension (kept for reference)
```

---

## Setup & Usage

### Prerequisites

- **Windows 10/11**
- **Python 3.8+** (must be on PATH)
- **mitmproxy** — `pip install mitmproxy`
- **Google Chrome** (or Chromium)

### Step 1 — Run the Application

```powershell
python dlp_app.py
```

This will:
1. Start the local HTTPS proxy on port 8080
2. Launch Chrome configured to route traffic through it
3. Open the Walled DLP control panel window

### Step 2 — (Optional) Install the CA Certificate

For production use, install the mitmproxy CA certificate so Chrome trusts the proxy's HTTPS interception without warnings:

```powershell
python install_cert.py
```

> For local testing, `dlp_app.py` already passes `--ignore-certificate-errors` to Chrome, so this step is not required.

### Step 3 — Test

1. Chrome opens to [https://chatgpt.com](https://chatgpt.com)
2. Type a message containing `WALLED_SENSITIVE` and press Enter → native dialog appears
3. Upload a file containing `WALLED_SENSITIVE` → native dialog appears
4. Observe that AI response text is colored **blue**

### CLI Options

```
python dlp_app.py --port 8080       # Custom proxy port (default: 8080)
python dlp_app.py --no-browser      # Start proxy only; configure Chrome manually
```

---

## Running Tests

### Unit Tests

```powershell
python test_local.py
```

Runs 28 tests covering:
- Marker detection (UTF-8, latin-1, binary, JSON, edge cases)
- File asset scanning
- CSS injection logic
- JSON prompt body parsing
- Target host detection
- Chrome path finding

### End-to-End Automated Tests

```powershell
python test_e2e_automated.py
```

Runs 15 tests covering the full DLP pipeline with mocked dialogs:
- Asset file verification
- DLP proxy addon structure
- Native messaging protocol framing
- Request blocking when user cancels
- Request forwarding when user continues
- Clean prompt passthrough (no dialog)
- Non-target host ignored
- CSS injection for ChatGPT and Perplexity HTML responses

---

## How It Works

### Why mitmproxy (No Browser Extension Needed)

mitmproxy is an **HTTPS interception proxy** — the same technology used by enterprise DLP solutions (Zscaler, Palo Alto Prisma, Cisco Umbrella). The browser is configured to send all traffic through `127.0.0.1:8080`. The proxy:

1. **Decrypts** the HTTPS traffic (using its locally-trusted CA certificate)
2. **Inspects** the request body for `WALLED_SENSITIVE`
3. **Shows a native OS dialog** via tkinter
4. Either **forwards** the request or **returns a 403** to block it
5. **Injects CSS** into HTML responses to color AI replies

This approach is completely transparent to the browser — no extension installation required.

### Prompt Interception

When a user submits a prompt on ChatGPT or Perplexity, the browser makes a POST request to the platform's API (e.g., `https://chatgpt.com/backend-api/conversation`). The proxy intercepts this request, parses the JSON body, and checks whether any message content contains `WALLED_SENSITIVE`. If found, the native dialog is shown before the request is forwarded.

### File Upload Interception

File uploads are sent as `multipart/form-data` POST requests. The proxy scans the entire request body (raw bytes) for the marker, covering text files, PDFs (which embed text in binary format), and images with embedded metadata or text.

### Native Desktop Dialog

The `_DialogManager` class in `dlp_proxy.py` runs tkinter on a dedicated daemon thread. When the proxy's request hook detects the marker, it posts a dialog request to the manager's queue and blocks (using `threading.Event`) until the user responds. This ensures the HTTP request is held in place while the user decides.

### Response Coloring

The `response()` hook in `WalledDLPAddon` checks if the response from a target host is `text/html`. If so, it injects a `<style>` block containing CSS selectors for ChatGPT's and Perplexity's AI response containers, setting their color to `#0d6efd` (blue).

---

## Supported Content Types

| Type | Detection Method |
|------|-----------------|
| JSON prompt body | Parse JSON → extract message content → byte scan |
| Form-encoded body | Raw byte scan |
| Multipart file upload (`.txt`, `.csv`) | Raw byte scan |
| Multipart file upload (`.pdf`) | Raw byte scan (PDF embeds text in binary stream) |
| Multipart file upload (images) | Raw byte scan (catches embedded metadata/EXIF text) |
| Binary uploads | Raw byte scan |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Chrome shows certificate warning | Run `python install_cert.py`, or use `--ignore-certificate-errors` (already set by dlp_app.py) |
| Proxy doesn't start | Check that mitmproxy is installed: `pip install mitmproxy` |
| Chrome not found | Install Chrome, or run `python dlp_app.py --no-browser` and set your browser's proxy to `127.0.0.1:8080` |
| Dialog doesn't appear | Check that `dlp_proxy.py` is in the same folder as `dlp_app.py` |
| Port 8080 in use | Use `python dlp_app.py --port 8081` |
| AI responses not blue | The platform may have changed its DOM structure; the CSS selectors in `dlp_proxy.py` → `RESPONSE_COLOR_CSS` can be updated |

---

## Security Notes

- The marker `WALLED_SENSITIVE` is intentionally simple and literal. In production, it would be replaced by regex patterns, ML classification, or integration with a DLP policy engine.
- The mitmproxy CA certificate is scoped to the local machine and must be explicitly trusted. It is generated fresh on first run.
- File content is inspected **at the network level** — the proxy sees the same bytes that the browser sends, without any client-side script injection.
- The proxy only inspects traffic from `chatgpt.com`, `chat.openai.com`, `perplexity.ai`, and `www.perplexity.ai`. All other traffic passes through unmodified.
