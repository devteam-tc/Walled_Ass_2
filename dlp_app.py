#!/usr/bin/env python3
"""
dlp_app.py — Walled DLP Desktop Application Launcher

This is the main entry point for the Walled DLP standalone desktop app.

What it does
------------
1. Starts a local mitmproxy HTTPS proxy (port 8080) as a background thread.
   The proxy addon (dlp_proxy.py) intercepts all traffic from the browser
   and enforces DLP policy — no browser extension required.
2. Launches Google Chrome (or Chromium) configured to use that proxy, with
   the mitmproxy CA cert trusted, pre-navigated to chatgpt.com.
3. Shows a native tkinter control panel (system-tray-style launcher window)
   where the user can:
     - See proxy status
     - Open ChatGPT or Perplexity directly
     - Quit (terminates the proxy and the managed browser)

Usage
-----
    python dlp_app.py [--port 8080] [--no-browser]

Requirements
------------
- Python 3.8+ with tkinter (standard on Windows)
- mitmproxy 6+  (pip install mitmproxy)
- Google Chrome or Chromium on PATH or at standard install paths
- mitmproxy CA cert installed (run: python install_cert.py)
"""

import argparse
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import time
import signal

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_PORT  = 8080
PROXY_HOST    = "127.0.0.1"
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
ADDON_PATH    = os.path.join(SCRIPT_DIR, "dlp_proxy.py")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
        os.environ.get("USERNAME", "")
    ),
    # Chromium fallback
    r"C:\Program Files\Chromium\Application\chrome.exe",
]

CHATGPT_URL    = "https://chatgpt.com"
PERPLEXITY_URL = "https://www.perplexity.ai"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_chrome() -> str | None:
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    # Try PATH
    try:
        result = subprocess.run(
            ["where", "chrome"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def launch_chrome(proxy_port: int, url: str = CHATGPT_URL) -> subprocess.Popen | None:
    """
    Launch Chrome with the DLP proxy configured.
    Uses a dedicated user-data-dir so it does not inherit the user's
    extensions or existing proxy settings.
    """
    chrome = find_chrome()
    if not chrome:
        return None

    user_data_dir = os.path.join(SCRIPT_DIR, ".dlp_chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)

    proxy_arg = f"--proxy-server=http://{PROXY_HOST}:{proxy_port}"

    # Accept the mitmproxy self-signed cert for HTTPS interception
    cert_arg = "--ignore-certificate-errors"  # dev convenience; see install_cert.py for production

    args = [
        chrome,
        proxy_arg,
        cert_arg,
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    try:
        proc = subprocess.Popen(args)
        return proc
    except Exception as e:
        print(f"[WalledDLP] Failed to launch Chrome: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Proxy runner (mitmdump in a background thread)
# ---------------------------------------------------------------------------

class ProxyRunner:
    """Runs mitmdump programmatically in a background thread."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port    = port
        self._thread: threading.Thread | None = None
        self._master  = None
        self.running  = False

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name="WalledDLP-Proxy", daemon=True
        )
        self._thread.start()
        # Give mitmproxy a moment to start listening
        time.sleep(1.5)
        self.running = True

    def _run(self):
        """Run mitmproxy's async loop inside this thread."""
        try:
            from mitmproxy.tools.main import mitmdump
            # Build sys.argv for mitmdump
            orig_argv = sys.argv[:]
            sys.argv = [
                "mitmdump",
                "--listen-host", PROXY_HOST,
                "--listen-port", str(self.port),
                "--quiet",
                "-s", ADDON_PATH,
            ]
            try:
                mitmdump()
            finally:
                sys.argv = orig_argv
        except SystemExit:
            pass
        except Exception as e:
            print(f"[WalledDLP] Proxy error: {e}", file=sys.stderr)

    def stop(self):
        self.running = False
        # mitmdump terminates when the daemon thread's process exits


# ---------------------------------------------------------------------------
# Control Panel (tkinter GUI)
# ---------------------------------------------------------------------------

class ControlPanel:
    """
    Main desktop window — shows proxy status and quick-launch buttons.
    This is the 'face' of the standalone desktop application.
    """

    def __init__(self, proxy: ProxyRunner, chrome_proc: subprocess.Popen | None):
        self.proxy       = proxy
        self.chrome_proc = chrome_proc

        self.root = tk.Tk()
        self.root.title("Walled DLP — Data Loss Prevention")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", False)
        self._build_ui()
        self._center()
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        hdr = tk.Frame(self.root, bg="#1a1a2e", padx=20, pady=14)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="🔒  Walled DLP",
            font=("Segoe UI", 16, "bold"),
            bg="#1a1a2e",
            fg="#e94560",
        ).pack(anchor="w")
        tk.Label(
            hdr,
            text="Standalone Desktop Data Loss Prevention",
            font=("Segoe UI", 10),
            bg="#1a1a2e",
            fg="#aaaaaa",
        ).pack(anchor="w")

        # Status section
        status_frame = tk.Frame(self.root, padx=20, pady=14)
        status_frame.pack(fill="x")

        tk.Label(
            status_frame,
            text="Proxy Status:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self._status_var = tk.StringVar(value="Starting…")
        self._status_label = tk.Label(
            status_frame,
            textvariable=self._status_var,
            font=("Segoe UI", 10),
            fg="#aaaaaa",
        )
        self._status_label.grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(
            status_frame,
            text="Proxy Address:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            status_frame,
            text=f"http://{PROXY_HOST}:{self.proxy.port}",
            font=("Segoe UI", 10),
            fg="#0d6efd",
        ).grid(row=1, column=1, sticky="w", padx=8, pady=(4, 0))

        tk.Label(
            status_frame,
            text="DLP Marker:",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            status_frame,
            text="WALLED_SENSITIVE",
            font=("Consolas", 10),
            fg="#e94560",
        ).grid(row=2, column=1, sticky="w", padx=8, pady=(4, 0))

        # Separator
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=20)

        # Feature list
        feat_frame = tk.Frame(self.root, padx=20, pady=10)
        feat_frame.pack(fill="x")
        tk.Label(
            feat_frame,
            text="Active Protections:",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        features = [
            "✅  Prompt interception (text containing WALLED_SENSITIVE)",
            "✅  File upload interception (text, PDF, image files)",
            "✅  Native OS dialog for user confirmation",
            "✅  AI response text colored blue on ChatGPT & Perplexity",
            "✅  No browser extension required",
        ]
        for f in features:
            tk.Label(
                feat_frame,
                text=f,
                font=("Segoe UI", 9),
                fg="#333333",
            ).pack(anchor="w", pady=1)

        # Separator
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=20)

        # Action buttons
        btn_frame = tk.Frame(self.root, padx=20, pady=14)
        btn_frame.pack(fill="x")

        tk.Button(
            btn_frame,
            text="Open ChatGPT",
            command=lambda: self._open_url(CHATGPT_URL),
            bg="#10a37f",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=14, pady=6,
            relief="flat",
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Open Perplexity",
            command=lambda: self._open_url(PERPLEXITY_URL),
            bg="#20b2d4",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=14, pady=6,
            relief="flat",
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Quit",
            command=self._on_quit,
            bg="#dc3545",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=14, pady=6,
            relief="flat",
            cursor="hand2",
        ).pack(side="right")

        # Footer note
        tk.Label(
            self.root,
            text="Standalone desktop app — no browser extension required",
            font=("Segoe UI", 8),
            fg="#999999",
        ).pack(pady=(0, 10))

    def _center(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _open_url(self, url: str):
        """Open the URL in the DLP-managed Chrome window."""
        if self.chrome_proc and self.chrome_proc.poll() is None:
            # Chrome is running — open a new tab via command line
            chrome = find_chrome()
            if chrome:
                user_data_dir = os.path.join(SCRIPT_DIR, ".dlp_chrome_profile")
                proxy_arg = f"--proxy-server=http://{PROXY_HOST}:{self.proxy.port}"
                subprocess.Popen([
                    chrome,
                    proxy_arg,
                    "--ignore-certificate-errors",
                    f"--user-data-dir={user_data_dir}",
                    url,
                ])
        else:
            # Launch Chrome fresh
            self.chrome_proc = launch_chrome(self.proxy.port, url)

    def _update_status(self):
        """Poll proxy status and update label."""
        if self.proxy.running:
            self._status_var.set("● Running")
            self._status_label.config(fg="#28a745")
        else:
            self._status_var.set("● Starting…")
            self._status_label.config(fg="#ffc107")
        self.root.after(1000, self._update_status)

    def _on_quit(self):
        if messagebox.askyesno("Quit", "Stop Walled DLP and close the browser?"):
            if self.chrome_proc:
                try:
                    self.chrome_proc.terminate()
                except Exception:
                    pass
            self.root.destroy()
            os._exit(0)

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self):
        self.root.after(1200, self._update_status)
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Walled DLP — Standalone Desktop Data Loss Prevention"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Proxy listen port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Start proxy only; do not launch Chrome"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Walled DLP — Standalone Desktop Application")
    print("=" * 60)
    print(f"  Proxy:  http://{PROXY_HOST}:{args.port}")
    print(f"  Addon:  {ADDON_PATH}")
    print("=" * 60)

    # 1. Start the mitmproxy HTTPS interception proxy
    proxy = ProxyRunner(port=args.port)
    proxy.start()
    print(f"[WalledDLP] Proxy listening on port {args.port}")

    # 2. Launch Chrome (unless --no-browser)
    chrome_proc = None
    if not args.no_browser:
        chrome_proc = launch_chrome(args.port)
        if chrome_proc:
            print(f"[WalledDLP] Chrome launched (PID {chrome_proc.pid})")
        else:
            print(
                "[WalledDLP] WARNING: Chrome not found. "
                "Configure your browser proxy manually: "
                f"http://{PROXY_HOST}:{args.port}"
            )

    # 3. Show the control panel
    panel = ControlPanel(proxy, chrome_proc)
    panel.run()


if __name__ == "__main__":
    main()
