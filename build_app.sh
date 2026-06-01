#!/usr/bin/env bash
# 构建可安装的 JarDiff.app（自带 venv，可拖入「应用程序」使用）
#
# 用法:
#   ./build_app.sh              # 构建到 dist/JarDiff.app
#   MONACO_VERSION=0.52.2 ./build_app.sh
#
# 说明:
#   - .app 内置一个 Python venv（依赖 pywebview），复用 jar_diff.py 逻辑
#   - venv 通过 pyvenv.cfg 引用系统/Homebrew 的 Python，因此需保留该 Python 安装
#   - 会尽力把 Monaco 编辑器内核打包进 .app 以便离线使用；下载失败则运行时回退 CDN
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

APP_NAME="JarDiff"
DIST="$ROOT/dist"
APP="$DIST/$APP_NAME.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
APPSRC="$RES/app"
VENV="$RES/venv"
MONACO_VERSION="${MONACO_VERSION:-0.52.2}"
PYTHON="${PYTHON:-python3}"

echo "==> 清理旧产物"
rm -rf "$APP"
mkdir -p "$MACOS" "$RES" "$APPSRC"

echo "==> 拷贝应用源码"
cp "$ROOT/jar_diff.py" "$APPSRC/"
rsync -a --exclude '__pycache__' --exclude 'web/vendor' "$ROOT/jardiff_app" "$APPSRC/"

echo "==> 拷贝应用图标"
ICON_SRC="$ROOT/jardiff_app/icon.icns"
HAS_ICON=0
if [[ -f "$ICON_SRC" ]]; then
  cp "$ICON_SRC" "$RES/icon.icns"
  HAS_ICON=1
  echo "    图标已就绪"
else
  echo "    未找到 jardiff_app/icon.icns，使用系统默认图标"
fi

echo "==> 尝试打包 Monaco 编辑器内核 (v$MONACO_VERSION)"
VENDOR_DIR="$APPSRC/jardiff_app/web/vendor"
mkdir -p "$VENDOR_DIR"
TARBALL_URL="https://registry.npmjs.org/monaco-editor/-/monaco-editor-${MONACO_VERSION}.tgz"
TMP_TGZ="$(mktemp -t monaco).tgz"
if curl -fsSL "$TARBALL_URL" -o "$TMP_TGZ" 2>/dev/null; then
  TMP_EXTRACT="$(mktemp -d)"
  tar -xzf "$TMP_TGZ" -C "$TMP_EXTRACT"
  if [[ -d "$TMP_EXTRACT/package/min/vs" ]]; then
    rm -rf "$VENDOR_DIR/vs"
    cp -R "$TMP_EXTRACT/package/min/vs" "$VENDOR_DIR/vs"
    echo "    Monaco 已打包到 $VENDOR_DIR/vs（离线可用）"
  else
    echo "    解压后未找到 min/vs，运行时将回退 CDN"
  fi
  rm -rf "$TMP_EXTRACT" "$TMP_TGZ"
else
  echo "    下载 Monaco 失败，运行时将回退 CDN（需联网）"
fi

echo "==> 创建内置 venv 并安装依赖"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip -q
"$VENV/bin/python" -m pip install --retries 10 --timeout 120 -r "$ROOT/requirements-app.txt"

echo "==> 写入启动器"
cat > "$MACOS/$APP_NAME" <<'LAUNCHER'
#!/bin/bash
# JarDiff 启动器
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"
export PYTHONPATH="$RES/app"
cd "$RES/app"
exec "$RES/venv/bin/python" -m jardiff_app.app "$@"
LAUNCHER
chmod +x "$MACOS/$APP_NAME"

echo "==> 写入 Info.plist"
ICON_KEY=""
if [[ "$HAS_ICON" == "1" ]]; then
  ICON_KEY="  <key>CFBundleIconFile</key><string>icon</string>"
fi
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.zhaopin.tools.jardiff</string>
  <key>CFBundleVersion</key><string>1.0.0</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
$ICON_KEY
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSRequiresAquaSystemAppearance</key><false/>
</dict>
</plist>
PLIST

echo ""
echo "✅ 构建完成: $APP"
echo "   运行:   open \"$APP\""
echo "   安装:   将其拖入 /Applications"
