#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Prepare a clean, self-contained Apple Silicon app ZIP. Does not publish it."""
import hashlib
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import plistlib
import shutil
import stat
import subprocess
import tempfile
import zipfile
from build_release_backend import build, CACHE, ROOT


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def package():
    if platform.machine() != "arm64":
        raise SystemExit("Only Apple Silicon releases have been reviewed.")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise SystemExit("Commit the reviewed source before packaging a public release.")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    timestamp = int(subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT))
    zip_date = datetime.fromtimestamp(timestamp, timezone.utc).timetuple()[:6]
    version = plistlib.loads((ROOT / "packaging/Info.plist").read_bytes())["CFBundleShortVersionString"]
    build()
    output = ROOT / "dist" / f"macos-{version}"
    output.mkdir(parents=True, exist_ok=True)
    # A fresh staging directory prevents old resources or local data entering a release.
    with tempfile.TemporaryDirectory(prefix="release-", dir=CACHE) as staging:
        env = os.environ.copy()
        env.update(FWG_BACKEND_DIR=str(CACHE), FWG_OUTPUT_DIR=staging)
        run(str(ROOT / "scripts/build.sh"), env=env, cwd=ROOT)
        app = Path(staging) / "Firefox WireGuard.app"
        resources = app / "Contents/Resources"
        shutil.copytree(ROOT / "packaging/third-party", resources / "ThirdPartyLicenses")
        shutil.copyfile(ROOT / "packaging/backend-release.json", resources / "backend-release.json")
        shutil.copyfile(CACHE / "backend-build.txt", resources / "backend-build.txt")
        source = (f"Firefox WireGuard {version}\nSource revision: {revision}\n"
                  f"https://github.com/kristof-dragon/firefox-wireguard/tree/{revision}\n\n"
                  "Original application and bridge: MPL-2.0 (see LICENSE).\n"
                  "This executable distribution does not restrict your rights to the source.\n"
                  "Backend source and dependency revisions: THIRD_PARTY.md and backend-release.json.\n"
                  "This Apple Silicon preview is ad-hoc signed, not notarized by Apple.\n")
        (resources / "SOURCE.txt").write_text(source)
        run("codesign", "--force", "--sign", "-", str(app))
        run("codesign", "--verify", "--deep", "--strict", str(app))
        forbidden = [str(ROOT).encode(), str(Path.home()).encode(), b"/Users/", b"/home/"]
        for p in app.rglob("*"):
            if p.is_symlink():
                raise SystemExit("Unexpected symlink in release bundle.")
            if p.is_file() and any(term in p.read_bytes() for term in forbidden):
                raise SystemExit(f"Private build path detected in {p.relative_to(app)}")
        for rel in ("MacOS/FirefoxWireGuard", "MacOS/firefox-wireguard-bridge", "Resources/wireproxy"):
            exe = app / "Contents" / rel
            arch = subprocess.check_output(["lipo", "-archs", str(exe)], text=True).strip()
            if arch != "arm64":
                raise SystemExit(f"Unexpected architecture: {arch}")
            libs = subprocess.check_output(["otool", "-L", str(exe)], text=True).splitlines()[1:]
            if any(not line.strip().startswith(("/usr/lib/", "/System/Library/")) for line in libs):
                raise SystemExit("A non-system library dependency would prevent standalone installation.")
        archive = output / f"Firefox-WireGuard-{version}-macOS-arm64.zip"
        # ZIP entries contain only regular file data and Unix modes, with no extended
        # attributes, owner IDs, resource forks, Finder metadata, or absolute paths.
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(app.rglob("*")):
                if p.is_file():
                    entry = zipfile.ZipInfo(str(p.relative_to(app.parent)), zip_date)
                    entry.create_system = 3
                    mode = 0o755 if os.access(p, os.X_OK) else 0o644
                    entry.external_attr = (stat.S_IFREG | mode) << 16
                    z.writestr(entry, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with tempfile.TemporaryDirectory(prefix="verify-", dir=CACHE) as restored:
            run("ditto", "-x", "-k", str(archive), restored)
            unpacked = Path(restored) / app.name
            run("codesign", "--verify", "--deep", "--strict", str(unpacked))
            env["FWG_TEST_APP"] = str(unpacked)
            run("python3", str(ROOT / "scripts/backend_integration.py"), env=env)
        source_archive = output / f"Firefox-WireGuard-{version}-source.zip"
        run("git", "archive", "--format=zip", f"--prefix=firefox-wireguard-{version}/",
            "-o", str(source_archive), revision, cwd=ROOT)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (output / "SHA256SUMS.txt").write_text("".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (archive, source_archive)))
        print(f"Prepared {archive.name}: {digest}")


if __name__ == "__main__":
    package()
