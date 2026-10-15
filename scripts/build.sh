#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CLANG_MODULE_CACHE_PATH="$PWD/.build/module-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$CLANG_MODULE_CACHE_PATH"
python3 scripts/fetch_backend.py
swift build --package-path app --scratch-path .build/native --configuration release --disable-sandbox --build-system native
bin_dir="$(swift build --package-path app --scratch-path .build/native --configuration release --show-bin-path --disable-sandbox --build-system native)"
app_dir="$PWD/dist/Firefox WireGuard.app"
mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"
cp "$bin_dir/FirefoxWireGuard" "$app_dir/Contents/MacOS/FirefoxWireGuard"
cp "$bin_dir/firefox-wireguard-bridge" "$app_dir/Contents/MacOS/firefox-wireguard-bridge"
cp vendor/bin/wireproxy "$app_dir/Contents/Resources/wireproxy"
cp vendor/bin/wireproxy-LICENSE "$app_dir/Contents/Resources/wireproxy-LICENSE"
cp THIRD_PARTY.md "$app_dir/Contents/Resources/THIRD_PARTY.md"
cp packaging/Info.plist "$app_dir/Contents/Info.plist"
# Local development signing only; no Apple account, certificate, or personal
# signing identity is embedded. Distributed notarized builds are a later step.
codesign --force --sign - "$app_dir/Contents/Resources/wireproxy"
codesign --force --sign - "$app_dir/Contents/MacOS/firefox-wireguard-bridge"
codesign --force --sign - "$app_dir"
codesign --verify --deep --strict "$app_dir"
python3 scripts/package_extension.py
printf '%s\n' 'Built dist/Firefox WireGuard.app and dist/firefox-wireguard-0.1.0-unsigned.xpi'
