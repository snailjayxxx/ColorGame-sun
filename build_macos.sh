#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="ColorGame"
BUNDLE_ID="com.snailjayxxx.colorgame"
ZIP_NAME="ColorGame-macOS-Apple-Silicon.zip"
DMG_NAME="ColorGame-macOS-Apple-Silicon.dmg"
CHECKSUM_NAME="SHA256SUMS-macOS.txt"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "错误：macOS .app 必须在 macOS 上构建。" >&2
  exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "错误：此脚本用于 Apple Silicon（arm64），当前架构为 $ARCH。" >&2
  exit 1
fi

if [[ "${SKIP_INSTALL:-0}" != "1" ]]; then
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -e ".[dev]"
fi

"$PYTHON_BIN" -m pytest

rm -rf build dist ColorGame.spec

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --target-arch arm64 \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --collect-all pynput \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pynput.mouse._darwin \
  run.py

APP_PATH="dist/${APP_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "错误：未生成 $APP_PATH。" >&2
  exit 1
fi

# 使用固定 Bundle ID 进行 ad-hoc 签名。正式公证发布时可替换为 Developer ID。
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

BINARY_INFO="$(file "$APP_PATH/Contents/MacOS/$APP_NAME")"
echo "$BINARY_INFO"
if [[ "$BINARY_INFO" != *"arm64"* ]]; then
  echo "错误：生成的程序不是 arm64。" >&2
  exit 1
fi

rm -f "dist/$ZIP_NAME" "dist/$DMG_NAME" "dist/$CHECKSUM_NAME"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "dist/$ZIP_NAME"

DMG_ROOT="build/macos-dmg"
rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
cp -R "$APP_PATH" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_ROOT" \
  -ov \
  -format UDZO \
  "dist/$DMG_NAME"

(
  cd dist
  shasum -a 256 "$ZIP_NAME" "$DMG_NAME" > "$CHECKSUM_NAME"
)

echo
echo "构建完成："
echo "  $APP_PATH"
echo "  dist/$ZIP_NAME"
echo "  dist/$DMG_NAME"
echo "  dist/$CHECKSUM_NAME"
