#!/usr/bin/env bash
# 构建可对外分发的 JarDiff：自包含打包 → Developer ID 签名 → 公证 → 打 DMG
#
# 前置（需你自己在 Apple 准备好）：
#   1. 加入 Apple Developer Program
#   2. 钥匙串安装「Developer ID Application」证书
#   3. 一个用于公证的 App 专用密码（或 notarytool keychain profile）
#
# 用法（环境变量传入凭据）：
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
#   APPLE_ID="you@example.com" \
#   TEAM_ID="TEAMID" \
#   APP_PASSWORD="abcd-efgh-ijkl-mnop" \
#   ./build_dmg.sh
#
#   # 或使用已保存的 notarytool 凭据档（推荐）：
#   #   xcrun notarytool store-credentials jardiff-profile --apple-id ... --team-id ... --password ...
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
#   NOTARY_PROFILE="jardiff-profile" \
#   ./build_dmg.sh
#
#   # 只想跑通打包+签名、暂不公证：
#   SIGN_IDENTITY="..." SKIP_NOTARIZE=1 ./build_dmg.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

APP_NAME="JarDiff"
DIST="$ROOT/dist_pyinstaller"
APP="$DIST/$APP_NAME.app"
ENTITLEMENTS="$ROOT/packaging/entitlements.plist"
DMG="$ROOT/dist_pyinstaller/$APP_NAME.dmg"
VENV_PY="$ROOT/.venv/bin/python"

ADHOC="${ADHOC:-0}"
if [[ "$ADHOC" == "1" ]]; then
  SIGN_IDENTITY="-"   # ad-hoc 签名，无需任何证书
else
  : "${SIGN_IDENTITY:?请设置 SIGN_IDENTITY（Developer ID Application 证书名），或用 ADHOC=1 做未公证分发}"
fi

echo "==> 1/5 自包含打包（PyInstaller）"
"$VENV_PY" -m PyInstaller --noconfirm --distpath "$DIST" "$ROOT/jardiff.spec" >/dev/null
[[ -d "$APP" ]] || { echo "打包失败：未找到 $APP" >&2; exit 1; }

if [[ "$ADHOC" == "1" ]]; then
  echo "==> 2/5 Ad-hoc 签名（未公证分发，保证 Apple Silicon 不报“已损坏”）"
  codesign --force --deep --sign - "$APP"
  codesign --verify --deep --verbose=2 "$APP" || true
else
  echo "==> 2/5 代码签名（Hardened Runtime + 时间戳）"
  # 先签所有内嵌的二进制（.dylib/.so/可执行），再签主程序与 .app
  while IFS= read -r -d '' f; do
    codesign --force --options runtime --timestamp \
      --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$f" 2>/dev/null || true
  done < <(find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" \) -print0)

  codesign --force --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" \
    "$APP/Contents/MacOS/$APP_NAME"

  codesign --force --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$APP"

  echo "    校验签名…"
  codesign --verify --deep --strict --verbose=2 "$APP"
fi

echo "==> 3/5 制作 DMG"
STAGING="$(mktemp -d)"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
# 放入面向用户的使用说明
DMG_README="$ROOT/packaging/DMG_README.txt"
if [[ -f "$DMG_README" ]]; then
  cp "$DMG_README" "$STAGING/使用说明.txt"
fi
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING" \
  -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGING"
echo "    生成 $DMG"

if [[ "$ADHOC" == "1" || "${SKIP_NOTARIZE:-0}" == "1" ]]; then
  echo "==> 4/5 跳过公证"
  echo ""
  echo "✅ 已生成（未公证）: $DMG"
  echo ""
  echo "分发到其他 Mac 的用法："
  echo "  1) 把 $APP_NAME.dmg 发给对方（U盘/网盘/AirDrop 均可）"
  echo "  2) 对方打开 DMG，把 $APP_NAME 拖入「应用程序」"
  echo "  3) 对方首次运行前执行一次（去掉隔离属性，否则会被拦/提示已损坏）："
  echo "       xattr -dr com.apple.quarantine /Applications/$APP_NAME.app"
  echo "     或：右键 $APP_NAME → 打开 → 在弹窗里再点「打开」"
  exit 0
fi

echo "==> 4/5 公证（notarytool，等待 Apple 处理）"
if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
else
  : "${APPLE_ID:?请设置 APPLE_ID 或 NOTARY_PROFILE}"
  : "${TEAM_ID:?请设置 TEAM_ID}"
  : "${APP_PASSWORD:?请设置 APP_PASSWORD（App 专用密码）}"
  xcrun notarytool submit "$DMG" \
    --apple-id "$APPLE_ID" --team-id "$TEAM_ID" --password "$APP_PASSWORD" --wait
fi

echo "==> 5/5 装订公证票据（stapler）"
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"

echo ""
echo "✅ 完成并已公证: $DMG"
echo "   分发后，用户双击 DMG → 拖入「应用程序」即可，无 Gatekeeper 拦截。"
