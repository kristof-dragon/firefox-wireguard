#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build an unsigned XPI using an explicit source allowlist."""
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
extension = root / "extension"
version = json.loads((extension / "manifest.json").read_text())["version"]
output = root / "dist" / f"firefox-wireguard-{version}-unsigned.xpi"
output.parent.mkdir(exist_ok=True)
files = ["manifest.json", "details.js", "controller.js", "background.js", "popup.html", "popup.css", "popup.js", "icon.svg"]
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
    for name in files:
        package.write(extension / name, name)
    package.write(root / "LICENSE", "LICENSE")
    package.write(extension / "SOURCE.txt", "SOURCE.txt")
print(f"Packaged {len(files) + 2} extension files; unsigned submission artifact.")
