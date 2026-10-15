#!/usr/bin/env python3
"""Download only a pinned, checksum-verified upstream backend into ignored storage."""
import hashlib
import io
import os
from pathlib import Path
import platform
import tarfile
import urllib.request

VERSION = "1.1.3"
SHA256 = {
    "arm64": "28d34342c48c309b628d9c06ab4efc05b82fba49821f360605c02139c02547a5",
    "x86_64": "5d89742a0f381d9508d3ad828a0d300dceee24fa49015427eaff42a23f7a50bd",
}
root = Path(__file__).resolve().parents[1]
cache = root / "vendor" / "bin"
cache.mkdir(parents=True, exist_ok=True)
arch = platform.machine()
if platform.system() != "Darwin" or arch not in SHA256:
    raise SystemExit("This build requires an Apple Silicon or Intel Mac.")
asset = f"wireproxy_darwin_{'amd64' if arch == 'x86_64' else arch}.tar.gz"
archive = cache / f"v{VERSION}-{asset}"
if not archive.exists():
    url = f"https://github.com/windtf/wireproxy/releases/download/v{VERSION}/{asset}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(40 * 1024 * 1024 + 1)
    if len(data) > 40 * 1024 * 1024:
        raise SystemExit("Backend archive exceeds the permitted size.")
else:
    data = archive.read_bytes()
if hashlib.sha256(data).hexdigest() != SHA256[arch]:
    raise SystemExit("Backend checksum mismatch. Refusing to extract or execute it.")
archive.write_bytes(data)
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as package:
    for wanted, destination in [("wireproxy", "wireproxy")]:
        matches = [entry for entry in package.getmembers() if Path(entry.name).name == wanted and entry.isfile()]
        if len(matches) != 1:
            raise SystemExit(f"Expected one {wanted} file in the upstream archive.")
        entry = matches[0]
        if entry.size > 40 * 1024 * 1024:
            raise SystemExit("Backend archive member exceeds the permitted size.")
        output = cache / destination
        output.write_bytes(package.extractfile(entry).read())
        os.chmod(output, 0o755 if wanted == "wireproxy" else 0o644)
licence = cache / "wireproxy-LICENSE"
if licence.exists():
    licence_data = licence.read_bytes()
else:
    with urllib.request.urlopen(f"https://raw.githubusercontent.com/windtf/wireproxy/v{VERSION}/LICENSE", timeout=30) as response:
        licence_data = response.read(65_536)
if hashlib.sha256(licence_data).hexdigest() != "12e05cf70e2876d0cfd1c649e1c0032f82a370b365dcccd7d5a03feee17f2625":
    raise SystemExit("Backend licence checksum mismatch.")
licence.write_bytes(licence_data)
print(f"Verified wireproxy {VERSION} for {arch}.")
