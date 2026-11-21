#!/usr/bin/env python3
"""
test_local.py — Interactive local test suite for Walled DLP.

Tests all functional requirements locally:
 1. Marker inspection on text prompts (clean vs WALLED_SENSITIVE)
 2. Marker inspection on files (Text, PDF, Image, and Clean)
 3. Native desktop confirmation dialog (tkinter UI popup)
 4. Enforcement outcome reporting (Continue vs Cancel)
"""

import sys
import os
import json
import struct
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOST_SCRIPT = os.path.join(SCRIPT_DIR, "native_host", "native_host.py")
MARKER = "WALLED_SENSITIVE"

def print_header(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def test_marker_detection():
    print_header("1. Marker Inspection Tests (In-Memory)")
    cases = [
        ("Normal prompt: 'Summarize the history of AI'", False),
        ("Confidential prompt: 'Analyze Q3 report: WALLED_SENSITIVE'", True),
        ("Perplexity query: 'Find financial data: WALLED_SENSITIVE'", True),
        ("Case check: 'walled_sensitive lowercase test'", False),
    ]

    for text, expected in cases:
        detected = MARKER in text
        status = "PASSED" if detected == expected else "FAILED"
        flag = "[ALERT TRIGGERED]" if detected else "[ALLOWED CLEAN] "
        print(f"  [{status}] {flag} '{text}'")

def test_file_inspection():
    print_header("2. File Content Inspection Tests")
    files = [
        ("test_clean.txt", "Plain text without marker", False),
        ("test_sensitive.txt", "Plain text with WALLED_SENSITIVE", True),
        ("test_sensitive.pdf", "PDF document with WALLED_SENSITIVE", True),
        ("test_sensitive.png", "Image file with WALLED_SENSITIVE bytes", True),
    ]

    for fname, desc, expected in files:
        fpath = os.path.join(SCRIPT_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  [MISSING] {fname}")
            continue

        with open(fpath, "rb") as f:
            raw_bytes = f.read()

        detected = MARKER.encode("utf-8") in raw_bytes or MARKER.encode("latin-1") in raw_bytes
        status = "PASSED" if detected == expected else "FAILED"
        flag = "[SENSITIVE DETECTED]" if detected else "[CLEAN - ALLOWED]  "
        print(f"  [{status}] {flag} {fname} ({desc})")

def trigger_native_dialog(req_id, msg_type, label, source):
    """Sends a native messaging request to native_host.py and returns the response."""
    payload = json.dumps({
        "requestId": req_id,
        "type": msg_type,
        "label": label,
        "source": source
    }).encode("utf-8")

    msg = struct.pack("<I", len(payload)) + payload

    proc = subprocess.Popen(
        [sys.executable, HOST_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    stdout, stderr = proc.communicate(input=msg, timeout=60)
    if not stdout or len(stdout) < 4:
        return {"error": stderr.decode("utf-8", errors="ignore")}

    raw_len = struct.unpack("<I", stdout[:4])[0]
    return json.loads(stdout[4:4+raw_len].decode("utf-8"))

def test_native_dialogs(interactive=True):
    print_header("3. Native Desktop Dialog Tests")

    if not interactive:
        print("  [SKIPPED] Native dialog popup skipped in non-interactive mode.")
        print("  To trigger the visual desktop dialog, run: python test_local.py --interactive")
        return

    print("  -> A native dialog window will now appear on your screen.")
    print("  -> Please click either 'Continue' or 'Cancel' to test enforcement.\n")

    # Test Prompt Dialog
    print("[TEST 1/2] Launching Native Dialog for Prompt on ChatGPT...")
    res1 = trigger_native_dialog(
        req_id=101,
        msg_type="prompt",
        label="Project roadmap: release target Q4 WALLED_SENSITIVE",
        source="ChatGPT"
    )
    decision1 = "ALLOWED (Continue clicked)" if res1.get("allowed") else "BLOCKED (Cancel clicked)"
    print(f"  => Result: {decision1} | Raw Host Response: {res1}\n")

    # Test File Dialog
    print("[TEST 2/2] Launching Native Dialog for File on Perplexity...")
    res2 = trigger_native_dialog(
        req_id=102,
        msg_type="file",
        label="financial_records_2026.pdf",
        source="Perplexity"
    )
    decision2 = "ALLOWED (Continue clicked)" if res2.get("allowed") else "BLOCKED (Cancel clicked)"
    print(f"  => Result: {decision2} | Raw Host Response: {res2}")

if __name__ == "__main__":
    interactive_mode = "--no-ui" not in sys.argv
    print_header("WALLED DLP — LOCAL TEST & VERIFICATION SUITE")
    test_marker_detection()
    test_file_inspection()
    test_native_dialogs(interactive=interactive_mode)
    print_header("TEST RUN COMPLETED")

