#!/usr/bin/env python3
# native_host.py -- Walled DLP Native Messaging Host
#
# Receives JSON messages from the Chrome extension via stdin/stdout
# using the Chrome Native Messaging protocol (4-byte little-endian length prefix).
#
# Each incoming message:
#   { "requestId": <int>, "type": "prompt"|"file", "label": "<str>", "source": "<str>" }
#
# For each message it shows a native OS dialog (tkinter) and responds:
#   { "requestId": <int>, "allowed": true|false }

import sys
import json
import struct
import tkinter as tk


# ---------------------------------------------------------------------------
# Native Messaging Protocol helpers
# ---------------------------------------------------------------------------

def read_message():
    """Read one native-messaging message from stdin. Returns dict or None."""
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    msg_len = struct.unpack("<I", raw_len)[0]
    raw_msg = sys.stdin.buffer.read(msg_len)
    if not raw_msg:
        return None
    return json.loads(raw_msg.decode("utf-8"))


def send_message(payload):
    """Write one native-messaging message to stdout."""
    encoded = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# Native Dialog (tkinter)
# ---------------------------------------------------------------------------

def show_dialog(request_id, msg_type, label, source):
    """
    Display a native desktop confirmation dialog.
    Blocks until the user clicks Continue or Cancel.
    Returns True (allow) or False (block).
    """
    result = {"allowed": False}

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    # Build message body
    if msg_type == "prompt":
        body = (
            "Sensitive marker WALLED_SENSITIVE detected in a TEXT PROMPT on {}.\n\n"
            "Prompt excerpt:\n\"{}\"\n\n"
            "Do you want to continue and submit this prompt?"
        ).format(source, label)
    else:
        body = (
            "Sensitive marker WALLED_SENSITIVE detected in an UPLOADED FILE on {}.\n\n"
            "File: {}\n\n"
            "Do you want to continue and upload this file?"
        ).format(source, label)

    # Build dialog window
    dlg = tk.Toplevel(root)
    dlg.title("Walled DLP - Sensitive Content Detected")
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    dlg.grab_set()

    # Center on screen
    dlg.update_idletasks()
    w, h = 500, 260
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    dlg.geometry("{}x{}+{}+{}".format(w, h, x, y))

    # --- Header ---
    hdr = tk.Frame(dlg, bg="#fff3cd", padx=14, pady=10)
    hdr.pack(fill="x")
    tk.Label(
        hdr,
        text="[!]  Sensitive Content Detected",
        font=("Segoe UI", 13, "bold"),
        bg="#fff3cd",
        fg="#856404",
    ).pack(anchor="w")

    # --- Body ---
    body_frame = tk.Frame(dlg, padx=18, pady=12)
    body_frame.pack(fill="both", expand=True)
    tk.Label(
        body_frame,
        text=body,
        wraplength=460,
        justify="left",
        font=("Segoe UI", 10),
        anchor="w",
    ).pack(anchor="w")

    # --- Buttons ---
    btn_frame = tk.Frame(dlg, padx=16, pady=10)
    btn_frame.pack(fill="x", side="bottom")

    def on_continue():
        result["allowed"] = True
        dlg.destroy()
        root.destroy()

    def on_cancel():
        result["allowed"] = False
        dlg.destroy()
        root.destroy()

    tk.Button(
        btn_frame,
        text="  Continue  ",
        command=on_continue,
        bg="#28a745",
        fg="white",
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=5,
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
        padx=12,
        pady=5,
        relief="flat",
        cursor="hand2",
    ).pack(side="right")

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    return result["allowed"]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    while True:
        try:
            message = read_message()
        except Exception:
            break

        if message is None:
            break

        request_id = message.get("requestId", 0)
        msg_type   = message.get("type", "prompt")
        label      = message.get("label", "(unknown)")
        source     = message.get("source", "AI platform")

        allowed = show_dialog(request_id, msg_type, label, source)
        send_message({"requestId": request_id, "allowed": allowed})


if __name__ == "__main__":
    main()
