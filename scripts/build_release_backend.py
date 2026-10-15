#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build the reviewed Darwin/arm64 backend without local paths or VCS metadata."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".build" / "distribution"
LOCK = json.loads((ROOT / "packaging/backend-release.json").read_text())


def build():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("The reviewed release build currently requires an Apple Silicon Mac.")
    go = os.environ.get("FWG_GO") or shutil.which("go") or str(CACHE / "go/bin/go")
    env = os.environ.copy()
    env.update(GOPATH=str(CACHE / "gopath"), GOCACHE=str(CACHE / "gocache"),
               GOTOOLCHAIN="local", GOENV="off", GOWORK="off", GOFLAGS="",
               CGO_ENABLED="0", GOOS="darwin", GOARCH="arm64", GOARM64="v8.0",
               GOPROXY="https://proxy.golang.org", GOSUMDB="sum.golang.org",
               GOPRIVATE="", GONOSUMDB="", GONOPROXY="", GOEXPERIMENT="")
    env.pop("GOROOT", None)
    version = subprocess.check_output([go, "version"], env=env, text=True).split()[2]
    if version != LOCK["go"]:
        raise SystemExit(f"Release backend requires {LOCK['go']}; set FWG_GO to that Go executable.")
    CACHE.mkdir(parents=True, exist_ok=True)
    module = "github.com/windtf/wireproxy"
    meta = json.loads(subprocess.check_output(
        [go, "mod", "download", "-json", f"{module}@{LOCK['wireproxyVersion']}"], env=env, text=True))
    expected = next(m for m in LOCK["modules"] if m["module"] == module)
    if meta["Sum"] != expected["sum"] or hashlib.sha256(Path(meta["Zip"]).read_bytes()).hexdigest() != LOCK["sourceZipSHA256"]:
        raise SystemExit("Backend source checksum mismatch.")
    for name, digest in LOCK["notices"].items():
        if hashlib.sha256((ROOT / "packaging/third-party" / name).read_bytes()).hexdigest() != digest:
            raise SystemExit(f"Reviewed licence notice changed: {name}")
    subprocess.run([go, "build", "-trimpath", "-buildvcs=false", "-mod=readonly",
                    "-ldflags=-s -w -X main.version=1.1.3 -X main.arch=arm64",
                    "-o", str(CACHE / "wireproxy"), "./cmd/wireproxy"],
                   cwd=meta["Dir"], env=env, check=True)
    info = subprocess.check_output([go, "version", "-m", str(CACHE / "wireproxy")], env=env, text=True)
    actual = sorted(tuple(line.split()[1:4]) for line in info.splitlines() if line.strip().startswith("dep\t"))
    wanted = sorted((m["module"], m["version"], m["sum"]) for m in LOCK["modules"] if m["module"] != module)
    if actual != wanted:
        raise SystemExit("Compiled dependencies differ from the reviewed licence inventory.")
    if b"/Users/" in (CACHE / "wireproxy").read_bytes() or b"/home/" in (CACHE / "wireproxy").read_bytes():
        raise SystemExit("A home-directory path remains in the backend.")
    shutil.copyfile(ROOT / "packaging/third-party/github.com/windtf/wireproxy/LICENSE", CACHE / "wireproxy-LICENSE")
    (CACHE / "backend-build.txt").write_text("wireproxy: " + info.split(": ", 1)[1])
    print("Built wireproxy 1.1.3 from verified source; reviewed dependency inventory matches.")


if __name__ == "__main__":
    build()
