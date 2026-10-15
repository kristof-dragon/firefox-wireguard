#!/bin/bash
# SPDX-License-Identifier: MPL-2.0
set -euo pipefail
cd "$(dirname "$0")/.."
export CLANG_MODULE_CACHE_PATH="$PWD/.build/module-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$CLANG_MODULE_CACHE_PATH"
backend_dir="${FWG_BACKEND_DIR:-$PWD/vendor/bin}"
if [[ -z "${FWG_BACKEND_DIR:-}" ]]; then
    python3 scripts/fetch_backend.py
fi
swift build --package-path app --scratch-path .build/native --configuration release --disable-sandbox --build-system native \
    -Xswiftc -debug-prefix-map -Xswiftc "$PWD=/src/firefox-wireguard" \
    -Xswiftc -file-prefix-map -Xswiftc "$PWD=/src/firefox-wireguard"
bin_dir="$(swift build --package-path app --scratch-path .build/native --configuration release --show-bin-path --disable-sandbox --build-system native)"
app_dir="${FWG_OUTPUT_DIR:-$PWD/dist}/Firefox WireGuard.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"
cp "$bin_dir/FirefoxWireGuard" "$app_dir/Contents/MacOS/FirefoxWireGuard"
cp "$bin_dir/firefox-wireguard-bridge" "$app_dir/Contents/MacOS/firefox-wireguard-bridge"
cp "$backend_dir/wireproxy" "$app_dir/Contents/Resources/wireproxy"
cp "$backend_dir/wireproxy-LICENSE" "$app_dir/Contents/Resources/wireproxy-LICENSE"
cp THIRD_PARTY.md "$app_dir/Contents/Resources/THIRD_PARTY.md"
cp LICENSE "$app_dir/Contents/Resources/LICENSE"
cp packaging/Info.plist "$app_dir/Contents/Info.plist"
strip -S "$app_dir/Contents/MacOS/FirefoxWireGuard" "$app_dir/Contents/MacOS/firefox-wireguard-bridge"
# Local development signing only; no Apple account, certificate, or personal
# signing identity is embedded. Distributed notarized builds are a later step.
codesign --force --sign - "$app_dir/Contents/Resources/wireproxy"
codesign --force --sign - "$app_dir/Contents/MacOS/firefox-wireguard-bridge"
codesign --force --sign - "$app_dir"
codesign --verify --deep --strict "$app_dir"
python3 scripts/package_extension.py
printf 'Built %s and the versioned unsigned XPI in dist/\n' "$app_dir"
