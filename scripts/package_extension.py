#!/usr/bin/env python3
"""Build an unsigned XPI using an explicit source allowlist."""
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
extension = root / "extension"
version = json.loads((extension / "manifest.json").read_text())["version"]
output = root / "dist" / f"firefox-wireguard-{version}-unsigned.xpi"
output.parent.mkdir(exist_ok=True)
files = ["manifest.json", "controller.js", "background.js", "popup.html", "popup.css", "popup.js", "icon.svg"]
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
    for name in files:
        package.write(extension / name, name)
print(f"Packaged {len(files)} extension files; unsigned development artifact.")
