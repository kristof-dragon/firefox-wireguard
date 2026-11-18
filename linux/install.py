#!/usr/bin/python3 -I
# SPDX-License-Identifier: MPL-2.0
"""User-local installation; profiles and wallet entries survive install/uninstall."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

BUNDLE = Path(__file__).resolve().parent
sys.path.insert(0, str(BUNDLE))
from firefox_wireguard.protocol import InstanceLock, manifest_path, register, registration_matches
from firefox_wireguard.storage import atomic_write, data_directory, xdg_path
from firefox_wireguard.configuration import UserError


def desktop_quote(value):
    # Desktop Exec quoting is NOT shell quoting. Percent is a desktop field code.
    escaped = str(value).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        escaped = escaped.replace(char, "\\" + char)
    # Backslashes are escaped again for the desktop entry string layer.
    return '"' + escaped.replace("\\", "\\\\") + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if os.getuid() == 0:
        raise UserError("Run this installer as your desktop user, without sudo.")
    destination = Path.home() / ".local/lib/firefox-wireguard"
    desktop = xdg_path("XDG_DATA_HOME", ".local/share") / "applications/org.firefoxwireguard.companion.desktop"
    manifest = manifest_path()
    helper = destination / "firefox-wireguard-bridge"
    ownership = InstanceLock(data_directory())
    try:
        if args.uninstall:
            if registration_matches(helper, manifest):
                manifest.unlink()
            desktop.unlink(missing_ok=True)
            if destination.exists() and not destination.is_symlink():
                marker = destination / ".firefox-wireguard-install"
                if not marker.is_file():
                    raise UserError("Unrecognised installation directory; it has been left intact.")
                shutil.rmtree(destination)
            print("Removed Linux companion and integration. Saved profiles and wallet entries were retained.")
            return
        if not (BUNDLE / "wireproxy").is_file():
            raise UserError("Run scripts/build.sh, then use dist/firefox-wireguard-linux/install.py.")
        if destination.is_symlink() or (destination.exists() and not (destination / ".firefox-wireguard-install").is_file()):
            raise UserError("The destination is not a recognised installation. It has been left intact.")
        if destination.resolve() != BUNDLE:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".fwg-install-", dir=destination.parent) as temporary:
                staged = Path(temporary) / "app"
                shutil.copytree(BUNDLE, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                (staged / ".firefox-wireguard-install").touch(mode=0o600)
                backup = Path(temporary) / "previous"
                if destination.exists():
                    destination.rename(backup)
                try:
                    staged.rename(destination)
                except OSError:
                    if backup.exists():
                        backup.rename(destination)
                    raise
        register(helper)
        desktop.parent.mkdir(parents=True, exist_ok=True)
        launcher = "\n".join(["[Desktop Entry]", "Type=Application", "Name=Firefox WireGuard",
                              "Comment=Manage WireGuard connections for Firefox", "Terminal=false",
                              "Categories=Network;Security;", f"Exec={desktop_quote(destination / 'firefox-wireguard')}",
                              f"Icon={str(destination / 'icon.svg').replace(chr(92), chr(92) * 2)}", ""])
        atomic_write(desktop, launcher.encode())
        print("Installed Firefox WireGuard. Open it from the application launcher, then import a profile.")
    finally:
        ownership.close()


if __name__ == "__main__":
    try:
        main()
    except (UserError, OSError) as error:
        sys.exit(str(error) if isinstance(error, UserError) else "Installation failed. Check directory permissions and retry.")
