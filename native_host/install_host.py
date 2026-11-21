#!/usr/bin/env python3
# install_host.py -- Registers the Walled DLP native messaging host.
#
# Run once after loading the Chrome extension:
#   python install_host.py <EXTENSION_ID>
#
# The extension ID is shown in chrome://extensions once you load the
# unpacked extension.
#
# What this script does (Windows):
#   1. Writes the host manifest JSON to native_host/com.walled.dlp.json
#      with the correct path to native_host.py and the extension ID.
#   2. Creates a wrapper .bat file so Chrome can launch the host.
#   3. Registers the manifest path in the Windows registry under
#      HKCU\Software\Google\Chrome\NativeMessagingHosts\com.walled.dlp

import sys
import os
import json
import winreg

# --- Paths -------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
HOST_SCRIPT  = os.path.join(SCRIPT_DIR, "native_host.py")
MANIFEST_DST = os.path.join(SCRIPT_DIR, "com.walled.dlp.json")
WRAPPER_BAT  = os.path.join(SCRIPT_DIR, "run_host.bat")

REGISTRY_KEY = r"Software\Google\Chrome\NativeMessagingHosts\com.walled.dlp"


def find_python():
    """Return the path to the current Python interpreter."""
    return sys.executable


def write_wrapper_bat(python_exe, host_script, bat_path):
    """Create a .bat launcher (Chrome requires a .bat or .exe on Windows)."""
    content = '@echo off\n"{}" "{}"\n'.format(python_exe, host_script)
    with open(bat_path, "w") as f:
        f.write(content)
    print("  Wrapper BAT written: {}".format(bat_path))


def write_manifest(bat_path, extension_id, manifest_path):
    """Write the native messaging host manifest JSON."""
    manifest = {
        "name": "com.walled.dlp",
        "description": "Walled DLP native messaging host",
        "path": bat_path,
        "type": "stdio",
        "allowed_origins": [
            "chrome-extension://{}/".format(extension_id)
        ],
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print("  Manifest written:    {}".format(manifest_path))


def register_in_registry(manifest_path):
    """Add the manifest path to the Windows registry."""
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, manifest_path)
        winreg.CloseKey(key)
        print("  Registry key set:    HKCU\\{}".format(REGISTRY_KEY))
    except Exception as e:
        print("  ERROR writing registry: {}".format(e), file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python install_host.py <CHROME_EXTENSION_ID>")
        print()
        print("Example:")
        print("  python install_host.py abcdefghijklmnopabcdefghijklmnop")
        sys.exit(1)

    extension_id = sys.argv[1].strip()
    if len(extension_id) != 32 or not extension_id.isalpha():
        print("WARNING: '{}' does not look like a valid Chrome extension ID.".format(extension_id))
        print("Chrome extension IDs are 32 lowercase letters. Proceeding anyway...")

    python_exe = find_python()
    print("\n[Walled DLP] Installing native messaging host...")
    print("  Python interpreter:  {}".format(python_exe))
    print("  Host script:         {}".format(HOST_SCRIPT))
    print("  Extension ID:        {}".format(extension_id))

    write_wrapper_bat(python_exe, HOST_SCRIPT, WRAPPER_BAT)
    write_manifest(WRAPPER_BAT, extension_id, MANIFEST_DST)
    register_in_registry(MANIFEST_DST)

    print()
    print("Installation complete!")
    print("   Restart Chrome if it was already open.")
    print()


if __name__ == "__main__":
    main()
