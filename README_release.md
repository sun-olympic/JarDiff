# JarDiff 发布指南（Developer ID 签名 + 公证 DMG）

把 JarDiff 打包成**自包含、已签名、已公证**的 `.dmg`，分发给任意 Mac 用户双击安装，不被 Gatekeeper 拦截。这条路**保留全部功能**（下载 jar、调 java/CFR 反编译），不进 App Store、不需要沙盒。

> 为什么不上 Mac App Store：应用会「运行时下载并执行 jar/CFR」，违反 App Store 审核（禁止下载可执行代码），且沙盒禁止调用系统 `java`/`javap`。改造成本极高。Developer ID + 公证是开发者工具的主流分发方式。

---

## 一、一次性准备（你需要在 Apple 侧完成）

1. **加入 Apple Developer Program**（个人/公司，约 ¥688/年）：<https://developer.apple.com/programs/>
2. **创建并安装「Developer ID Application」证书**到钥匙串：
   - Xcode → Settings → Accounts → 登录 Apple ID → Manage Certificates → ＋ → **Developer ID Application**
   - 或开发者后台 Certificates 页面手动创建后双击导入钥匙串
   - 验证：`security find-identity -v -p codesigning` 应出现
     `Developer ID Application: 你的名字 (TEAMID)`
3. **准备公证凭据**（二选一）：
   - **App 专用密码**：appleid.apple.com → 登录与安全 → App 专用密码，生成一个（形如 `abcd-efgh-ijkl-mnop`）
   - **或** 保存 notarytool 凭据档（推荐，免每次输密码）：
     ```bash
     xcrun notarytool store-credentials jardiff-profile \
       --apple-id "you@example.com" --team-id "TEAMID" --password "abcd-efgh-ijkl-mnop"
     ```

> 当前本机检测：尚无 Developer ID 证书（只有公司内网 CA 证书，不可用于公证）。完成上面第 2 步后即可正式发布。

---

## 二、一键构建发布包

脚本：`build_dmg.sh`，自动完成「自包含打包 → 签名 → 公证 → 打 DMG」。

```bash
# 方式 A：用 App 专用密码
SIGN_IDENTITY="Developer ID Application: 你的名字 (TEAMID)" \
APPLE_ID="you@example.com" \
TEAM_ID="TEAMID" \
APP_PASSWORD="abcd-efgh-ijkl-mnop" \
./build_dmg.sh

# 方式 B：用已保存的 notarytool 凭据档（推荐）
SIGN_IDENTITY="Developer ID Application: 你的名字 (TEAMID)" \
NOTARY_PROFILE="jardiff-profile" \
./build_dmg.sh

# 方式 C：先只验证打包+签名，暂不公证
SIGN_IDENTITY="Developer ID Application: 你的名字 (TEAMID)" \
SKIP_NOTARIZE=1 ./build_dmg.sh
```

产物：`dist_pyinstaller/JarDiff.dmg`（已公证、已 staple）。用户双击 → 拖入「应用程序」即可。

---

## 二之二、未公证的内部分发（无需任何证书）⭐

还没有 Apple Developer ID 证书、但想先把变更打包发给同事/其他电脑用，可用 **ad-hoc 签名**模式（无需证书、不公证）：

```bash
ADHOC=1 ./build_dmg.sh
```

这会：自包含打包 → ad-hoc 签名（保证 Apple Silicon 上不报「已损坏」）→ 打成 `dist_pyinstaller/JarDiff.dmg`（不公证）。

**分发到其他 Mac 的步骤：**
1. 把 `JarDiff.dmg` 发给对方（U盘 / 网盘 / AirDrop 均可；**用 DMG，不要用 zip**，zip 易丢失签名属性）
2. 对方打开 DMG，把 `JarDiff` 拖入「应用程序」
3. 对方**首次运行前**执行一次去隔离命令（否则会被 Gatekeeper 拦或提示「已损坏」）：

```bash
xattr -dr com.apple.quarantine /Applications/JarDiff.app
```

或：右键 `JarDiff` → 打开 → 在弹窗里再点「打开」（命令法最稳）。

> 说明：ad-hoc 版适合**内部/小范围**分发，每台机器首次需手动放行一次。正式对外发布仍建议拿到 Developer ID 证书后走公证流程（方式 A/B），用户双击即用、无需放行。DMG 内已附带「使用说明.txt」，对方照做即可。

---

## 三、构建产物与机制说明

| 文件 | 作用 |
|---|---|
| `jardiff.spec` | PyInstaller 配置：把 Python、pywebview、前端、Monaco、图标全部冻结进 `.app` |
| `jardiff_main.py` | 打包入口 |
| `packaging/entitlements.plist` | Hardened Runtime 所需权限（冻结的 CPython 需要 JIT / 未签名内存 / 关闭库校验） |
| `build_dmg.sh` | 一键：打包 → 签名 → 公证 → DMG |
| `dist_pyinstaller/JarDiff.app` | 自包含应用（**不依赖系统 Python/Homebrew**） |

已验证（用本机证书演练）：
- 自包含 `.app` 不链接外部 Python，独立启动正常
- 内置 Monaco（离线可用）、图标、后端逻辑自检通过
- 深度签名 + Hardened Runtime + entitlements 校验通过（`valid on disk` / `satisfies its Designated Requirement`）
- DMG 正常生成

仅「公证」一步需等你的 Developer ID 证书到位。

---

## 四、常见问题

**Q: 公证失败，提示 "The signature does not include a secure timestamp" / "not signed with a Developer ID"？**
A: 确认用的是 `Developer ID Application` 证书（不是 Apple Development / 内网 CA），脚本已带 `--timestamp --options runtime`。

**Q: 公证返回 Invalid，如何看原因？**
A: `xcrun notarytool log <submission-id> --keychain-profile jardiff-profile`。常见是某个内嵌 dylib 未签名或缺 hardened runtime。

**Q: 用户打开仍提示「已损坏」？**
A: 多为未 staple 或下载丢失扩展属性。确认脚本最后 `stapler staple` 成功；或让用户执行 `xattr -dr com.apple.quarantine /Applications/JarDiff.app`。

**Q: 想分发给公司内部、不想买 Apple 账号？**
A: 可只做 `SKIP_NOTARIZE=1` 的本地签名版，但其他人首次打开需右键「打开」绕过 Gatekeeper；正式对外仍建议公证。

---

## 五、版本与体积

- 应用自包含整个 CPython 3.14 + pyobjc + Monaco，`.app` 约几十 MB 属正常
- 升级版本：改 `jardiff.spec` 与 `jardiff_app/__init__.py` 的版本号后重跑 `build_dmg.sh`
