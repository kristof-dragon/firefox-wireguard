#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build a relocatable Linux preview with the same pinned userspace backend."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if platform.system() != "Linux":
        raise SystemExit("Build the Linux companion on Linux.")
    backend = Path(os.environ.get("FWG_BACKEND_DIR", ROOT / "vendor/bin")).resolve()
    if "FWG_BACKEND_DIR" not in os.environ:
        subprocess.run([sys.executable, str(ROOT / "scripts/fetch_backend.py")], check=True)
    output = Path(os.environ.get("FWG_OUTPUT_DIR", ROOT / "dist")).resolve() / "firefox-wireguard-linux"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "linux/firefox_wireguard", output / "firefox_wireguard", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("firefox-wireguard", "firefox-wireguard-bridge", "install.py"):
        shutil.copyfile(ROOT / "linux" / name, output / name)
        (output / name).chmod(0o755)
    for name in ("wireproxy", "wireproxy-LICENSE"):
        shutil.copyfile(backend / name, output / name)
    (output / "wireproxy").chmod(0o755)
    shutil.copyfile(ROOT / "extension/icon.svg", output / "icon.svg")
    for name in ("LICENSE", "THIRD_PARTY.md"):
        shutil.copyfile(ROOT / name, output / name)
    shutil.copytree(ROOT / "docs", output / "docs", dirs_exist_ok=True)
    (output / "README.md").write_text(
        "# Firefox WireGuard — Linux preview\n\n"
        "Run `./install.py` without sudo, then open Firefox WireGuard from your application launcher.\n\n"
        "Requires Python 3, python3-pyqt6, libsecret-tools, curl, and a Secret Service wallet.\n\n"
        "See [Linux setup and limitations](docs/linux-support.md).\n")
    # This is a local development preview, not the audited macOS public release.
    subprocess.run([sys.executable, str(ROOT / "scripts/package_extension.py")], check=True)
    print(f"Built {output}. Run its install.py for a user-local installation.")


if __name__ == "__main__":
    main()
