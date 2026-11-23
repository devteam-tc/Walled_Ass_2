#!/usr/bin/env python3
"""
install_cert.py — Install the mitmproxy CA Certificate (Windows)

The mitmproxy HTTPS proxy needs to present a trusted certificate to the
browser so it can intercept HTTPS traffic. This is standard practice for
corporate DLP proxies (e.g., Zscaler, Palo Alto, Cisco Umbrella all do this).

This script:
1. Runs mitmproxy briefly to generate its CA cert (~/.mitmproxy/mitmproxy-ca-cert.p12)
2. Installs the cert into the Windows Root CA store (requires admin or user consent)

After running this script, browsers that use the system cert store (Chrome,
Edge, IE) will trust mitmproxy's HTTPS interception without warnings.

Note: dlp_app.py uses --ignore-certificate-errors as a development fallback,
so this script is OPTIONAL for local testing.

Usage
-----
    python install_cert.py
"""

import os
import subprocess
import sys
import time
import threading

MITMPROXY_CERT_DIR  = os.path.expanduser("~\\.mitmproxy")
MITMPROXY_CA_CERT   = os.path.join(MITMPROXY_CERT_DIR, "mitmproxy-ca-cert.cer")


def generate_cert():
    """Start mitmdump briefly to generate the CA certificate, then kill it."""
    print("[install_cert] Generating mitmproxy CA certificate...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "mitmproxy.tools.main", "--listen-port", "18080", "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def install_cert_windows():
    """Install the mitmproxy CA cert into the Windows Root store."""
    if not os.path.isfile(MITMPROXY_CA_CERT):
        print(f"[install_cert] CA cert not found at: {MITMPROXY_CA_CERT}")
        print("[install_cert] Generating it now...")
        generate_cert()

    if not os.path.isfile(MITMPROXY_CA_CERT):
        print("[install_cert] ERROR: Could not generate CA cert. Is mitmproxy installed?")
        sys.exit(1)

    print(f"[install_cert] Installing cert from: {MITMPROXY_CA_CERT}")
    result = subprocess.run(
        [
            "certutil",
            "-addstore",
            "-user",          # Install in current user store (no admin needed)
            "Root",
            MITMPROXY_CA_CERT,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("[install_cert] SUCCESS: mitmproxy CA cert installed in user Root store.")
        print("[install_cert] Chrome and Edge will now trust the DLP proxy's HTTPS cert.")
    else:
        print(f"[install_cert] WARNING: certutil returned {result.returncode}")
        print(result.stdout)
        print(result.stderr)
        print("[install_cert] You may need to manually import the cert or run as admin.")
        print(f"[install_cert] Cert location: {MITMPROXY_CA_CERT}")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("[install_cert] This script is for Windows only.")
        sys.exit(1)

    if not os.path.isfile(MITMPROXY_CA_CERT):
        generate_cert()

    if os.path.isfile(MITMPROXY_CA_CERT):
        install_cert_windows()
    else:
        print("[install_cert] Failed to find or generate the mitmproxy CA cert.")
        print("[install_cert] Try running: mitmdump --listen-port 18080")
        print(f"[install_cert] Then look for the cert at: {MITMPROXY_CA_CERT}")
        sys.exit(1)
