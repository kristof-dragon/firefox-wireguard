#!/bin/bash
# SPDX-License-Identifier: MPL-2.0
set -euo pipefail
cd "$(dirname "$0")/.."
export CLANG_MODULE_CACHE_PATH="$PWD/.build/module-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$CLANG_MODULE_CACHE_PATH"
swift test --package-path app --scratch-path .build/native --disable-sandbox --build-system native
node --test extension/tests/*.test.js
python3 -m py_compile scripts/fetch_backend.py scripts/package_extension.py scripts/firefox_smoke.py scripts/fixtures/native_host.py
plutil -lint packaging/Info.plist
