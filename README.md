# JarDiff — 跨平台 JAR 包变更对比工具 (GUI & CLI)

对比两个 JAR 文件变化（主要针对相同包不同版本之间的差异）。

#### 界面效果图
<img width="1281" height="821" alt="image" src="https://github.com/user-attachments/assets/cc002d67-9383-40ec-b956-3fe7390256ef" />

`JarDiff` 是一个功能强大、美观且易用的 JAR 包差异对比工具，旨在解决 Java 开发人员在版本升级、依赖变更或排查问题时，需要精确对比两个 JAR 包代码差异的痛点。

它包含**桌面图形界面 (GUI)** 与 **命令行工具 (CLI)** 两个版本，支持本地 JAR、远程 URL 以及 Maven 坐标三种来源。

---

## 🌟 核心特性

- **多源智能识别**：支持**本地路径**、**HTTP(S) URL**、**Maven 坐标**（`g:a:v[:classifier]`）三种 JAR 包来源，自动下载并缓存。
- **高保真反编译**：
  - 默认集成 **CFR 反编译器**（首次运行自动联网下载并缓存，输出干净的 Java 源码，可读性极佳）。
  - 支持 `javap` 输出原始字节码。
  - 支持 Procyon 和 Fernflower 等其他反编译器。
- **Monaco 强力驱动 (GUI)**：GUI 版内嵌 Monaco Editor（VS Code/Cursor 同款编辑器内核），直接在应用内并排展示代码高亮与行级 Diff，免去跳转外部编辑器的烦恼。
- **外部编辑器桥接 (CLI)**：CLI 版支持自动探测并调用 `Cursor` 或 `VS Code` 的 `--diff` 视图，实现无缝的本地代码审查。
- **高级定制**：
  - 支持忽略 `META-INF` 目录。
  - 支持路径包含过滤（如 `com/example`）。
  - 支持自定义私服仓库地址与 Basic Auth 账户密码认证。
  - 默认开启 **忽略 SSL 校验** 选项，解决企业 CA/自签名内网仓库证书报错问题。

---

## 🖥️ 桌面图形界面 (GUI)

GUI 版本基于 `pywebview` 与 Monaco Editor 构建，提供原生窗口体验。

### 1. 双击运行（打包版下载）
您可以在本项目的 **GitHub Releases** 页面下载打包好的可执行文件：
* **macOS (`.dmg`)**：自包含 App，匿名 Ad-hoc 签名。
  > ⚠️ **首次打开提示损坏/拦截？**
  > 由于未进行苹果付费公证，首次双击可能会被拦截。请按照 DMG 镜像中附带的《双击打不开看这里.txt》操作：
  > * **方法 A**：将 App 拖入应用程序后，**右键**点击 `JarDiff.app` 选择“打开”，在弹出的警告中确认打开。
  > * **方法 B**：打开终端，执行 `xattr -cr /Applications/JarDiff.app` 即可解锁。
* **Windows 安装版 (`-Setup.exe`)**：双击一键安装，安装程序会在后台自动检测并静默安装运行所必需的 **Edge WebView2 Runtime**，并提供自动下载安装 JDK 17 的选项。
* **Windows 绿色版 (`-portable.zip`)**：解压即可直接双击运行 `JarDiff.exe`。
  > 💡 **绿色版优化**：
  > 绿色版已集成**自动解封（Mark of the Web）**与 **DLL 自动搜索** 机制。若从网络下载解压后由于系统拦截导致 DLL 载入失败，程序会在最前端自动清除 NTFS 的 Zone.Identifier 安全标记，开箱即用；若系统缺少 WebView2，程序会弹出确认对话框并提供微软官网常青引导程序下载链接。

### 2. 开发模式直接启动 (Python)
适合本地调试或源码运行。首次启动会自动创建 `.venv` 虚拟环境并补全依赖：

* **macOS / Linux**：
  ```bash
  ./run_app.sh
  ```
  *调试模式（带网页审查元素）*：`JARDIFF_DEBUG=1 ./run_app.sh`
* **Windows (CMD/PowerShell)**：
  ```bat
  python -m venv .venv
  .venv\Scripts\pip install -r requirements-app.txt
  .venv\Scripts\python -m jardiff_app.app
  ```

---

## ⌨️ 命令行工具 (CLI)

命令行工具 `jar_diff.py` 仅依赖 **Python 3 标准库**，在无需安装任何第三方依赖的情况下即可独立运行。

### 1. 快速上手
```bash
# 对比两个本地 JAR 包，列出变更文件总览
python3 jar_diff.py old.jar new.jar

# 打印具体的 unified diff 代码差异（终端彩色高亮）
python3 jar_diff.py old.jar new.jar --diff

# 自动调用本地的 Cursor/VS Code，逐个文件打开并排对比视图
python3 jar_diff.py old.jar new.jar --editor
```

### 2. 命令参数说明
```text
位置参数:
  old_jar               旧版 JAR：本地路径 / URL / Maven 坐标(g:a:v[:classifier])
  new_jar               新版 JAR：本地路径 / URL / Maven 坐标(g:a:v[:classifier])

可选参数:
  --diff                在终端打印每个变更文件的 unified diff（彩色）
  --decompile           使用 javap 反编译 .class 后再对比（指定 --editor/--export 时自动开启）
  --decompiler JAR      指定反编译器 jar（CFR/Procyon/Fernflower），反编译为 Java 源码
  --editor [CMD]        在对比编辑器中打开。可选值如 cursor, code，不指定则自动探测
  --export DIR          将变更前后内容导出到 DIR/old 与 DIR/new 两个目录树中
  --max-open N          编辑器模式下最多打开的对比标签页数量，默认 20
  --filter STR          只处理路径包含指定字符串的文件（如 com/example）
  --ignore-meta         忽略 META-INF/ 目录下的所有文件
  --repo URL            Maven 仓库基址，用于解析坐标
  --user USER           仓库 Basic Auth 认证用户名
  --password PWD        仓库 Basic Auth 认证密码
  --insecure            跳过 HTTPS 证书校验（用于自签名 / 企业内网仓库）
  --keep-downloads      保留下载的临时 JAR 文件（默认运行结束后自动清理）
```

### 3. CLI 经典使用场景
* **Maven 坐标对比**：
  ```bash
  python3 jar_diff.py org.apache.commons:commons-lang3:3.11 org.apache.commons:commons-lang3:3.12.0 --diff
  ```
* **私服仓库 Basic Auth 对比**：
  ```bash
  python3 jar_diff.py org.example:demo:1.0 org.example:demo:1.1 \
    --repo https://repo.example.com/repository/maven-public/ \
    --user admin --password secret --insecure
  ```
* **导出源码并用 Beyond Compare 或 Meld 等工具大范围对比**：
  ```bash
  python3 jar_diff.py old.jar new.jar --export ./diff_out --decompiler cfr
  # 然后对比这两个导出的目录
  cursor --diff ./diff_out/old ./diff_out/new
  ```

---

## 🛠️ 打包构建说明（开发者专用）

如果您想自己打包分发应用，可以按以下说明在对应平台上执行构建。**请务必在对应平台的物理机/虚拟机上构建**，不支持跨平台交叉编译。

### Windows 环境打包
1. 准备 **Python 3.10+** 及 **Inno Setup 6.1+**（若需生成安装包）。
2. 在项目根目录执行打包脚本：
   ```bat
   build_windows.bat
   ```
   它会自动生成虚拟环境 `.venv-win`，拉取 `packaging/requirements-windows.txt` 中的打包依赖，并使用 `jardiff.spec` 完成 PyInstaller 打包。
3. 绿色版产物位于 `dist/JarDiff/`。
4. 如需编译安装程序，使用 Inno Setup 编译 `packaging/jardiff_inno.iss` 即可。

### macOS 环境打包
1. 准备 **Python 3.10+**。
2. 运行打包命令：
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install pywebview pyinstaller pillow
   .venv/bin/python make_icon.py
   .venv/bin/python -m PyInstaller --noconfirm jardiff.spec
   ```
3. 产物为 `dist_pyinstaller/JarDiff.app`。可通过磁盘工具或脚本将其封装为 `.dmg`。

---

## 🙋 常见问题 FAQ

#### Q：为什么 macOS 下不开启“忽略 SSL”经常报错，而 Windows 下不需要？
**A**：
1. **Windows** 会自动读取操作系统的受信任根证书库。若公司内网私服通过 Active Directory 或组策略统一分发了企业自签名 CA，Windows 上的 Python 和 .NET 运行时能够自动无缝信任它。
2. **macOS** 上的 Python 独立于系统 Keychain，默认不加载系统钥匙串中的任何根证书。即使您的 macOS 系统信任了自签名 CA，Python 也会因为缺少根证书而抛出 `SSL: CERTIFICATE_VERIFY_FAILED`。因此，在 macOS 上我们默认开启了“忽略 SSL 校验”来保证内网和公网连接顺畅。

#### Q：为什么修改过的 `.class` 文件没有显示代码 diff？
**A**：二进制的 `.class` 字节码无法以纯文本方式直接对比。请确保在顶部反编译选项中选择了 `javap`（字节码）或 `CFR`（推荐，还原为 Java 源码）。

#### Q：Monaco 编辑器界面一直处于加载状态？
**A**：打包生成的应用已在本地内置了 Monaco 核心库，完全支持离线运行。如果您是在**开发模式下通过源码启动**，它会默认从 CDN 加载 Monaco 编辑器，需要保持网络连接。

---

## 📝 许可证

本项目采用 [MIT License](LICENSE) 授权许可。
