# JarDiff Windows 打包与安装指南

> ⚠️ **必须在 Windows 电脑上打包**。PyInstaller 不支持跨平台交叉编译，macOS 上**无法**直接生成
> Windows 的 `.exe`/安装包。本仓库已把代码、图标、打包脚本、安装脚本全部备好，
> 你只需把整个 `jardiff/` 目录拷到一台 Windows 机器上执行下面步骤即可。

---

## 一、两种角色，依赖不同

| 角色 | 需要装什么 |
| --- | --- |
| **打包者**（在 Windows 上编译出包的人） | Python 3.10+、Inno Setup 6.1+（做安装包用）；JDK 可选 |
| **终端用户**（双击安装程序的人） | **无需手动装任何依赖**：安装程序会自动检测并安装 WebView2 Runtime，并可选自动安装 JDK |

> ✅ **安装即自动装依赖**：`packaging\jardiff_inno.iss` 在安装阶段会：
> 1. 检测 **Edge WebView2 Runtime**（运行必需），缺失则静默联网安装；
> 2. 若用户勾选"自动安装 JDK 17"任务，则自动下载安装 JDK（反编译 `.class` 用）。
> 所以终端用户拿到 `Setup.exe` 双击下一步即可，不用关心运行时依赖。

### 打包者机器准备

1. **Python 3.10+**（建议 3.11/3.12），安装时勾选 **Add Python to PATH**。
2. **Inno Setup 6.1+**（生成带自动装依赖的安装程序）：<https://jrsoftware.org/isdl.php>
   - 必须 6.1+，安装脚本用到内置的联网下载函数 `DownloadTemporaryFile`。
3. （可选）**JDK 8+**：若打包机也想本地跑测试反编译，可装；不装不影响出包。

---

## 二、一键打包（生成绿色版目录）

把 `jardiff/` 拷到 Windows 后，在该目录打开 CMD 或 PowerShell，执行：

```bat
build_windows.bat
```

脚本会自动：
1. 创建虚拟环境 `.venv-win`；
2. 安装 `packaging\requirements-windows.txt` 里的依赖（pywebview / pyinstaller / pillow）；
3. 若缺 `icon.ico` 则用 `make_icon.py` 重新生成；
4. 用 `jardiff.spec` 执行 PyInstaller 打包。

成功后产物在：

```
dist\JarDiff\JarDiff.exe
```

整个 `dist\JarDiff\` 目录就是**自包含绿色版**（内置 Python、pywebview、Monaco 编辑器），
双击 `JarDiff.exe` 即可运行；拷贝整个目录到别的 Windows 也能直接用。

---

## 三、生成安装程序（可选，便于分发）

绿色版目录适合自己用；要做成"双击安装、带开始菜单/桌面快捷方式、可卸载"的安装包，用 Inno Setup：

**方式 A：图形界面**
1. 打开 Inno Setup，`File → Open` 选择 `packaging\jardiff_inno.iss`；
2. 点击 **Build**（绿色 ▶）。

**方式 B：命令行**

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\jardiff_inno.iss
```

产物：

```
dist_installer\JarDiff-Setup-1.0.0.exe
```

把这个 `Setup.exe` 发给同事，双击安装即可。

---

## 四、常见问题

| 现象 | 原因 / 解决 |
| --- | --- |
| 启动闪退 / 白屏 | 缺少 **WebView2 Runtime**，安装后重试 |
| `.class` 显示字节码而非 Java 源码 | 未装 JDK，或首次需联网自动下载 CFR 反编译器 |
| 杀毒软件/SmartScreen 拦截 | 未做代码签名的自编译 exe 常见，点"更多信息 → 仍要运行"；如需消除告警需购买代码签名证书对 exe/installer 签名 |
| 下载 Maven 包失败 | 检查公司网络/仓库地址；可在"高级"里改默认仓库并保存 |
| 打包报缺 `clr`/pythonnet | 重新执行 `python -m pip install -r packaging\requirements-windows.txt` |

---

## 五、配置 / 缓存目录（Windows）

- 用户设置：`%APPDATA%\JarDiff\settings.json`
- 反编译器缓存（CFR）：`%LOCALAPPDATA%\JarDiff\cache\`
- 下载的临时 JAR：系统临时目录下 `jardiff_app_*`（退出/启动自动清理）

> macOS 对应路径分别为 `~/.config/jardiff/`、`~/.cache/jar_diff/`，互不影响。

---

## 六、产物一览

| 平台 | 打包命令 | 产物 |
| --- | --- | --- |
| Windows | `build_windows.ps1`（或 `build_windows.bat`）+ Inno Setup | `JarDiff.exe` / `JarDiff-Setup-*.exe` |
| macOS | `pyinstaller --noconfirm jardiff.spec` | `JarDiff.app` |

源码跨平台共用（`jar_diff.py` + `jardiff_app/` + 内置 Monaco），功能一致。
macOS 的签名 / 公证 / DMG 发布流程为内部流程，不在本公开仓库中。

---

## 七、CI 自动出 Windows 包

仓库内置 GitHub Actions 流水线 `.github/workflows/build.yml`，在云端自动产出
Windows 安装包与绿色版，无需本地准备打包环境。

### 触发方式

- **手动**：GitHub 仓库 → Actions → "Build JarDiff (windows)" → Run workflow。
- **打 tag 自动发布 Release**：

```bash
git tag v1.0.0
git push origin v1.0.0
```

会自动构建并把以下产物上传到 Release：
- `JarDiff-Setup-1.0.0.exe`（Windows 安装程序，安装时自动装依赖）
- `JarDiff-portable.zip`（Windows 免安装绿色版）

### 各 Job 做了什么

| Job | Runner | 步骤 |
| --- | --- | --- |
| `build-windows` | `windows-latest` | 装依赖 → `make_icon.py` 生成 ico → PyInstaller 打包 → choco 装 Inno Setup → 编译安装程序 → 上传 exe/zip |
| `release` | `ubuntu-latest` | 仅打 tag 时：汇总产物发布到 GitHub Release |

### ⚠️ 重要：workflow 必须位于"仓库根"

GitHub Actions 只识别**仓库根目录**下的 `.github/workflows/*.yml`。本文件放在
`jardiff/.github/workflows/build.yml`，工作流里的相对路径（`build_windows.bat`、
`packaging\...`）都假设**`jardiff/` 就是仓库根**。

- **推荐做法**：把 `jardiff/` 目录作为一个独立 Git 仓库推送到 GitHub
  （此时 `.github/` 正好在根，开箱即用）。
- 若你坚持让 `jardiff/` 作为大仓库的**子目录**，需要：
  1. 把 `jardiff/.github` 移到大仓库根的 `.github`；
  2. 给每个 Job 的步骤加上 `working-directory: jardiff`（或在 job 层用
     `defaults: { run: { working-directory: jardiff } }`），并把
     artifact 的 `path` 前面也加上 `jardiff/`。
