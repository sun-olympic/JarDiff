# JarDiff 桌面应用（macOS）

把 `jar_diff.py` 的全部能力做成了一个 macOS 原生应用，**内嵌 Monaco 编辑器**（VS Code / Cursor 同款编辑器内核）直接在应用内并排查看代码差异，无需再调用外部编辑器。

支持的能力与命令行版完全一致：

- 本地路径 / HTTP(S) URL / Maven 坐标（`g:a:v[:classifier]`）三种 JAR 来源，自动识别
- 列出新增 / 删除 / 修改文件，显示变更总览
- `.class` 反编译：`javap`（字节码）或 **CFR**（Java 源码，自动下载缓存）
- 路径过滤、忽略 `META-INF`、私服仓库地址与 Basic Auth 认证
- 点击文件即在**应用内嵌的对比编辑器**中并排查看 old / new 代码

---

## 技术栈

| 组件 | 作用 |
|---|---|
| [pywebview](https://pywebview.flowrl.com/) | 原生窗口（macOS 用 WKWebView），桥接 Python ↔ JS |
| [Monaco Editor](https://microsoft.github.io/monaco-editor/) | 内嵌的 diff 编辑器（VS Code 内核） |
| `jar_diff.py` | 复用的核心逻辑（下载 / 反编译 / 分类 / 渲染） |

界面与逻辑解耦：Python 后端（`jardiff_app/backend.py`）暴露 `compare` / `get_diff` 等方法，前端（`jardiff_app/web/`）调用并用 Monaco 渲染。

---

## 目录结构

```
ToolScript/
├── jar_diff.py              # 命令行版（仍可单独使用）
├── jardiff_app/
│   ├── app.py               # 应用入口（创建窗口）
│   ├── backend.py           # pywebview JS API，复用 jar_diff
│   └── web/                 # 前端
│       ├── index.html
│       ├── app.js
│       ├── style.css
│       └── vendor/vs/       # 打包时注入的 Monaco（离线可用）
├── requirements-app.txt     # 应用依赖（pywebview）
├── run_app.sh               # 开发模式启动
└── build_app.sh             # 构建可安装的 JarDiff.app
```

---

## 方式一：开发模式直接运行

适合本机快速使用 / 调试。首次运行会自动创建 venv 并安装依赖。

```bash
./run_app.sh
```

调试模式（打开 Web Inspector）：

```bash
JARDIFF_DEBUG=1 ./run_app.sh
```

---

## 方式二：构建可安装的 .app

```bash
./build_app.sh
```

产物在 `dist/JarDiff.app`，特点：

- **自带 Python venv**（内置 pywebview），双击即用
- **Monaco 已打包进 app**，离线也能渲染（下载失败时运行时回退 CDN）

运行 / 安装：

```bash
open dist/JarDiff.app          # 直接运行
# 或把 dist/JarDiff.app 拖入「应用程序」(/Applications)
```

> 注意：内置 venv 通过 `pyvenv.cfg` 引用本机的 Homebrew Python，因此**请保留该 Python 安装**。
> 如需完全自包含、可分发给其他机器的版本，需进一步用 py2app/PyInstaller 冻结解释器（可按需扩展 `build_app.sh`）。

### 首次打开被 Gatekeeper 拦截

应用未签名，macOS 可能提示「无法打开」。任选其一：

- 右键 App →「打开」→ 在弹窗中再次点「打开」
- 或执行：`xattr -dr com.apple.quarantine dist/JarDiff.app`

---

## 界面使用

1. **顶部**：填写「旧版 JAR」「新版 JAR」（本地路径 / URL / Maven 坐标）
2. 选择**反编译方式**：
   - 不反编译：只对比文本文件（xml/properties/yml 等）
   - javap：`.class` 显示字节码
   - **CFR（默认）**：`.class` 反编译成 Java 源码，首次自动下载 CFR 并缓存
3. 可选：填「过滤路径」、勾选「忽略 META-INF」；点「仓库设置」可改 Maven 仓库与认证
   - 默认使用**公共仓库**（Maven 中央仓库 `https://repo1.maven.org/maven2`）
   - 改完地址点「保存为默认」会记住（下次打开自动填充）；「恢复默认」清除保存值
   - 每次对比也会自动记住当前仓库地址
4. 点 **开始对比**
5. **左侧**按「修改 / 新增 / 删除」分组列出文件，**点击**任一文件
6. **右侧**在内嵌编辑器中并排显示 old / new 代码差异（语法高亮 + 行级 diff）

---

## 常见问题

**Q: 点击 `.class` 文件提示无法文本对比？**
A: 需要在顶部选择 `javap` 或 `CFR` 反编译方式后重新对比。CFR 可读性最佳。

**Q: 编辑器一直加载不出来？**
A: 打包版已内置 Monaco，离线可用；开发模式从 CDN 加载，需联网。可用 `JARDIFF_DEBUG=1 ./run_app.sh` 看控制台报错。

**Q: 下载 JAR 报 401/403？**
A: 私服需认证，在「仓库设置」里填用户名 / 密码。

**Q: 想要纯命令行 / 在编辑器外打开对比？**
A: 用 `jar_diff.py`，详见 `README_jar_diff.md`。
