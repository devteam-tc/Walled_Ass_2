#!/usr/bin/env python3
"""
dlp_proxy.py — Walled DLP mitmproxy Addon

This module is loaded by mitmproxy (mitmdump) and runs entirely as a
desktop process. It requires NO browser extension.

Responsibilities
----------------
1. Inspect every outgoing HTTP request body for the WALLED_SENSITIVE marker.
   - Covers text prompts submitted to ChatGPT / Perplexity via their APIs.
   - Covers multipart file uploads (text, PDF, image files).
2. When the marker is detected, pause the request and show a native
   tkinter OS dialog on the desktop (Continue / Cancel).
3. If the user clicks Cancel, return a 403 Forbidden response — the prompt
   or file never reaches the AI platform.
4. Inject a small <style> block into every HTML response from chatgpt.com
   and perplexity.ai that colors AI-generated response text blue.

Communication with the launcher (dlp_app.py)
---------------------------------------------
The mitmproxy addon runs inside mitmdump's async event loop. tkinter must
run on the main thread, so dialog requests are posted to a queue and
processed by a secondary Tkinter manager thread.
"""

import json
import queue
import threading
import tkinter as tk
import logging

from mitmproxy import http, ctx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER = "WALLED_SENSITIVE"

# Hostnames we care about
TARGET_HOSTS = {
    "chatgpt.com",
    "chat.openai.com",
    "perplexity.ai",
    "www.perplexity.ai",
}

# CSS injected into HTML pages from the target hosts to color AI responses
RESPONSE_COLOR_CSS = """
<style id="walled-dlp-style">
/* Walled DLP — color AI responses blue */
/* ChatGPT selectors */
.markdown.prose,
[data-message-author-role='assistant'] .prose,
[data-message-author-role='assistant'] .markdown,
[data-message-author-role='assistant'] p,
/* Perplexity selectors */
.prose-answer,
[data-testid='answer-text'],
.answer-text,
.font-display,
.break-words p,
.col-span-8 .prose
{
    color: #0d6efd !important;
}
</style>
"""

log = logging.getLogger("WalledDLP")

# ---------------------------------------------------------------------------
# Dialog manager — runs tkinter on a dedicated thread
# ---------------------------------------------------------------------------

class _DialogManager:
    """
    Runs a Tk root on a dedicated daemon thread.
    Other threads post dialog requests and block on an Event until answered.
    """

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._tk_loop, name="WalledDLP-TkThread", daemon=True
        )
        self._thread.start()

    def _tk_loop(self):
        """Main loop — runs on the TK thread."""
        self._root = tk.Tk()
        self._root.withdraw()          # hidden root window
        self._root.attributes("-topmost", True)
        self._poll()                   # start polling the queue
        self._root.mainloop()

    def _poll(self):
        """Check queue every 100 ms and dispatch dialogs."""
        try:
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._show(item)
        finally:
            self._root.after(100, self._poll)

    def _show(self, item):
        """Build and display one dialog window (called on TK thread)."""
        msg_type   = item["msg_type"]
        label      = item["label"]
        source     = item["source"]
        result_ref = item["result"]
        event_ref  = item["event"]

        if msg_type == "prompt":
            body = (
                f"Sensitive marker WALLED_SENSITIVE detected in a TEXT PROMPT on {source}.\n\n"
                f"Prompt excerpt:\n\"{label}\"\n\n"
                f"Do you want to continue and submit this prompt?"
            )
        else:
            body = (
                f"Sensitive marker WALLED_SENSITIVE detected in an UPLOADED FILE on {source}.\n\n"
                f"File: {label}\n\n"
                f"Do you want to continue and upload this file?"
            )

        dlg = tk.Toplevel(self._root)
        dlg.title("Walled DLP — Sensitive Content Detected")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        # Center on screen
        dlg.update_idletasks()
        w, h = 520, 270
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(dlg, bg="#fff3cd", padx=14, pady=10)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="⚠  Sensitive Content Detected",
            font=("Segoe UI", 13, "bold"),
            bg="#fff3cd",
            fg="#856404",
        ).pack(anchor="w")

        # Body
        body_frame = tk.Frame(dlg, padx=18, pady=12)
        body_frame.pack(fill="both", expand=True)
        tk.Label(
            body_frame,
            text=body,
            wraplength=478,
            justify="left",
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(anchor="w")

        # Buttons
        btn_frame = tk.Frame(dlg, padx=16, pady=10)
        btn_frame.pack(fill="x", side="bottom")

        def on_continue():
            result_ref["allowed"] = True
            dlg.destroy()
            event_ref.set()

        def on_cancel():
            result_ref["allowed"] = False
            dlg.destroy()
            event_ref.set()

        tk.Button(
            btn_frame,
            text="  Continue  ",
            command=on_continue,
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=12, pady=5,
            relief="flat",
            cursor="hand2",
        ).pack(side="right", padx=(6, 0))

        tk.Button(
            btn_frame,
            text="  Cancel  ",
            command=on_cancel,
            bg="#dc3545",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=12, pady=5,
            relief="flat",
            cursor="hand2",
        ).pack(side="right")

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)

    def ask(self, msg_type: str, label: str, source: str) -> bool:
        """
        Block the calling thread until the user answers the dialog.
        Returns True (allow) or False (block).
        """
        result = {"allowed": False}
        event  = threading.Event()
        self._queue.put({
            "msg_type": msg_type,
            "label":    label,
            "source":   source,
            "result":   result,
            "event":    event,
        })
        event.wait()          # block until dialog closed
        return result["allowed"]


# Module-level singleton — shared by all addon instances
_dialog_mgr: _DialogManager | None = None
_mgr_lock = threading.Lock()


def _get_dialog_mgr() -> _DialogManager:
    global _dialog_mgr
    with _mgr_lock:
        if _dialog_mgr is None:
            _dialog_mgr = _DialogManager()
    return _dialog_mgr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target_host(flow: http.HTTPFlow) -> str | None:
    """Return the display name for a request host, or None if not targeted."""
    host = flow.request.pretty_host
    for t in TARGET_HOSTS:
        if host == t or host.endswith("." + t):
            if "chatgpt" in t or "openai" in t:
                return "ChatGPT"
            if "perplexity" in t:
                return "Perplexity"
            return host
    return None


def _contains_marker(data: bytes) -> bool:
    """Return True if data contains WALLED_SENSITIVE (UTF-8 or latin-1)."""
    try:
        if MARKER.encode("utf-8") in data:
            return True
    except Exception:
        pass
    try:
        if MARKER.encode("latin-1") in data:
            return True
    except Exception:
        pass
    return False


def _extract_text_snippets(content_type: str, body: bytes) -> list[tuple[str, str]]:
    """
    Return a list of (label, snippet) pairs extracted from the request body.
    Each pair describes one piece of content to scan.
    """
    snippets = []
    ct = content_type.lower()

    if "application/json" in ct:
        # JSON body — scan the whole decoded text
        try:
            text = body.decode("utf-8", errors="replace")
            snippets.append(("prompt", text[:200]))
        except Exception:
            pass

    elif "multipart/form-data" in ct:
        # Multipart — scan each part individually
        # We do a quick marker scan on the raw bytes; label as "file upload"
        snippets.append(("file", "<multipart upload>"))

    elif "application/x-www-form-urlencoded" in ct:
        try:
            text = body.decode("utf-8", errors="replace")
            snippets.append(("prompt", text[:200]))
        except Exception:
            pass

    elif "text/" in ct:
        try:
            text = body.decode("utf-8", errors="replace")
            snippets.append(("prompt", text[:200]))
        except Exception:
            pass

    else:
        # Binary / unknown — raw scan
        snippets.append(("file", "<binary upload>"))

    return snippets


# ---------------------------------------------------------------------------
# mitmproxy Addon
# ---------------------------------------------------------------------------

class WalledDLPAddon:
    """
    mitmproxy addon class.
    mitmproxy calls request() for each outgoing HTTP request and
    response() for each incoming HTTP response.
    """

    # ── request hook ────────────────────────────────────────────────────────

    def request(self, flow: http.HTTPFlow):
        source = _target_host(flow)
        if source is None:
            return                     # not a target host — pass through

        body = flow.request.content
        if not body:
            return                     # no body — pass through

        if not _contains_marker(body):
            return                     # no marker — pass through

        # Determine what kind of content this is
        content_type = flow.request.headers.get("content-type", "")
        snippets = _extract_text_snippets(content_type, body)

        for msg_type_hint, raw_label in snippets:
            # Decide label
            if msg_type_hint == "prompt":
                # Try to extract from JSON for a nicer label
                label = raw_label
                try:
                    data = json.loads(body.decode("utf-8", errors="replace"))
                    # ChatGPT sends {"messages": [{"content": "..."}]}
                    msgs = data.get("messages") or []
                    if msgs:
                        last = msgs[-1]
                        content = last.get("content", "")
                        if isinstance(content, str):
                            label = content[:120] + ("…" if len(content) > 120 else "")
                        elif isinstance(content, list):
                            # Content can be array of parts
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    t = part.get("text", "")
                                    label = t[:120] + ("…" if len(t) > 120 else "")
                                    break
                except Exception:
                    pass
                msg_type = "prompt"
            else:
                label = raw_label
                # Try to find a filename in Content-Disposition
                for part_header in flow.request.headers.get("content-disposition", ""):
                    if 'filename="' in part_header:
                        label = part_header.split('filename="')[1].rstrip('"')
                        break
                msg_type = "file"

            log.info(f"[WalledDLP] Sensitive marker found in {msg_type} on {source}: {label!r}")

            mgr = _get_dialog_mgr()
            allowed = mgr.ask(msg_type, label, source)

            if not allowed:
                log.info(f"[WalledDLP] User cancelled — blocking request to {source}")
                flow.response = http.Response.make(
                    403,
                    json.dumps({
                        "error": "Blocked by Walled DLP",
                        "reason": "Sensitive content detected and user chose to cancel."
                    }),
                    {"Content-Type": "application/json"},
                )
                return

        log.info(f"[WalledDLP] User allowed — forwarding request to {source}")

    # ── response hook ───────────────────────────────────────────────────────

    def response(self, flow: http.HTTPFlow):
        source = _target_host(flow)
        if source is None:
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return

        # Inject the CSS that colors AI response text blue
        body = flow.response.content
        if b"</head>" in body:
            body = body.replace(
                b"</head>",
                RESPONSE_COLOR_CSS.encode("utf-8") + b"</head>",
                1,
            )
        elif b"<body" in body:
            # No </head> — inject before <body>
            body = body.replace(
                b"<body",
                RESPONSE_COLOR_CSS.encode("utf-8") + b"<body",
                1,
            )
        else:
            body = RESPONSE_COLOR_CSS.encode("utf-8") + body

        flow.response.content = body


# ---------------------------------------------------------------------------
# mitmproxy entry point
# ---------------------------------------------------------------------------

def load(loader):
    """Called by mitmproxy when the addon is loaded."""
    log.info("[WalledDLP] Addon loaded. Monitoring ChatGPT and Perplexity.")


addons = [WalledDLPAddon()]
