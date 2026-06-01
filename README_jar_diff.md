# jar_diff.py — JAR 包代码变化对比工具

对比两个 JAR 包的内容差异，列出**新增 / 删除 / 修改**的文件，并能：

- 显示具体变更代码（unified diff，终端彩色高亮）
- 在**对比编辑器**（Cursor / VS Code）中逐文件打开 diff 视图
- 将变更前后内容**导出**成两个目录树，供任意 diff 工具使用
- 直接从 **HTTP(S) URL** 或 **Maven 坐标**下载 JAR 后对比
- 对 `.class` 文件用 `javap`（字节码）或外部反编译器（CFR/Procyon/Fernflower，Java 源码）反编译后对比

仅依赖 **Python 3 标准库**，无需安装第三方包。

---

## 环境要求

| 依赖 | 用途 | 是否必须 |
|---|---|---|
| Python 3.10+ | 运行脚本（使用了 `X | None` 类型语法） | 必须 |
| `javap`（JDK 自带） | 反编译 `.class` 为字节码 | 反编译字节码时需要 |
| `java` + 反编译器 jar | 把 `.class` 反编译成 Java 源码 | 仅 `--decompiler` 时需要 |
| `cursor` / `code` 命令 | 在编辑器中打开 diff | 仅 `--editor` 时需要 |

---

## 快速开始

```bash
# 1. 本地两个 jar 对比，列出变更文件
python3 jar_diff.py old.jar new.jar

# 2. 显示具体变更代码（文本文件 / 反编译后的 class）
python3 jar_diff.py old.jar new.jar --diff

# 3. 在 Cursor 中逐文件打开对比视图
python3 jar_diff.py old.jar new.jar --editor
```

---

## 参数说明

### 位置参数

| 参数 | 说明 |
|---|---|
| `old_jar` | 旧版 JAR，可为：**本地路径** / **URL** / **Maven 坐标** |
| `new_jar` | 新版 JAR，同上 |

JAR 来源会被自动识别，优先级：本地文件 → `http(s)://` URL → Maven 坐标。

Maven 坐标格式：`groupId:artifactId:version[:classifier]`，例如
`com.google.guava:guava:32.0-jre`、`org.example:demo:1.0:sources`。

### 可选参数

| 参数 | 说明 |
|---|---|
| `--diff` | 在终端打印每个变更文件的 unified diff（彩色） |
| `--decompile` | 用 `javap -p -c` 反编译 `.class` 后再 diff（指定 `--editor`/`--export` 时自动开启） |
| `--decompiler JAR` | 指定反编译器 jar（CFR/Procyon/Fernflower），把 `.class` 反编译为 **Java 源码**；不指定则用 `javap` 字节码 |
| `--editor [CMD]` | 在对比编辑器中逐文件打开变更。不带值时自动探测 `cursor`/`code`；也可指定如 `--editor cursor` |
| `--export DIR` | 把变更前后内容导出到 `DIR/old` 与 `DIR/new` 两个目录树 |
| `--max-open N` | 编辑器模式下最多打开的对比数量（默认 `20`），防止打开过多标签页 |
| `--filter STR` | 只处理路径包含 `STR` 的文件，如 `--filter "com/example"` |
| `--ignore-meta` | 忽略 `META-INF/` 目录下的文件 |
| `--repo URL` | Maven 仓库基址（解析坐标用），默认智联内网仓库 |
| `--user` / `--password` | 仓库 Basic Auth 认证 |
| `--keep-downloads` | 保留下载的临时 JAR（默认运行结束后删除） |

---

## 使用场景示例

### 列出变更并查看代码 diff

```bash
python3 jar_diff.py old.jar new.jar --diff
```

### 在编辑器中对比（最直观）

```bash
# 自动探测 cursor / code
python3 jar_diff.py old.jar new.jar --editor

# 指定编辑器命令
python3 jar_diff.py old.jar new.jar --editor cursor

# 也可用环境变量指定默认编辑器
export JAR_DIFF_EDITOR=cursor
python3 jar_diff.py old.jar new.jar --editor
```

> 编辑器模式会为每个变更文件打开一个左右对比视图。新增/删除文件会与空文件对比。
> 文件较多时建议配合 `--filter` 缩小范围，或用 `--max-open` 限制数量。

### 反编译成 Java 源码再对比（可读性最佳）

`javap` 输出的是字节码，可读性较差。提供反编译器 jar 可得到接近源码的结果：

```bash
# 下载 CFR（示例）：https://github.com/leibnitz27/cfr/releases
python3 jar_diff.py old.jar new.jar --editor cursor --decompiler ~/tools/cfr.jar
```

支持的反编译器（按文件名自动识别）：

- **CFR** — `cfr.jar`（推荐，输出 `*.java`）
- **Procyon** — `procyon-decompiler-*.jar`
- **Fernflower** — `fernflower.jar`

### 导出到目录树，用外部工具对比

```bash
python3 jar_diff.py old.jar new.jar --export ./diff_out --decompiler ~/tools/cfr.jar

# 然后用任意 diff 工具对比两个目录
cursor --diff ./diff_out/old ./diff_out/new   # 或 meld / Beyond Compare 等
```

导出结构：

```
diff_out/
├── old/
│   └── com/example/Foo.class.java      # 反编译后的旧版本
└── new/
    └── com/example/Foo.class.java      # 反编译后的新版本
```

> `.class` 反编译后会追加后缀：CFR/Procyon 为 `.java`，`javap` 为 `.bytecode.txt`；
> 文本文件（`.xml`/`.properties`/`.yml` 等）保持原名。

### 从仓库下载对比

```bash
# Maven 坐标（默认仓库）
python3 jar_diff.py org.apache.commons:commons-lang3:3.11 org.apache.commons:commons-lang3:3.12.0 --diff

# 指定仓库 + 认证
python3 jar_diff.py g:a:1.0 g:a:1.1 \
  --repo https://repo.example.com/repository/maven-public/ \
  --user alice --password secret

# 直接 URL
python3 jar_diff.py https://repo/a-1.0.jar https://repo/a-1.1.jar --diff

# 混用：本地包 vs 仓库包
python3 jar_diff.py ./old.jar com.google.guava:guava:32.0-jre --diff
```

---

## 输出说明

运行后先打印**变更总览**与文件分类清单：

```
📊 变更总览
  旧包文件数: 120
  新包文件数: 123
  新增: 5
  删除: 2
  修改: 8
  未变: 110

============================================================
 修改文件 (8 个文件)
============================================================
  com/example/service/UserService.class
  ...
```

- 加上 `--diff` 时，逐文件打印彩色 unified diff
- 加上 `--editor` 时，逐文件在编辑器中打开对比视图
- 加上 `--export` 时，把内容写入目录树并打印路径

---

## 常见问题

**Q: 修改文件里看不到 diff？**
A: `.class` 文件需要 `--decompile`（字节码）或 `--decompiler`（源码）才能显示。二进制资源（图片等）无法做文本对比，会被跳过。

**Q: `--editor` 提示找不到编辑器？**
A: 确认 `cursor` 或 `code` 命令在 PATH 中（VS Code 可通过命令面板 “Shell Command: Install 'code' command in PATH” 安装），或用 `--editor <命令>` 指定，或设置 `JAR_DIFF_EDITOR` 环境变量。

**Q: 反编译后的 Java 源码不完全准确？**
A: 反编译是近似还原，泛型、Lambda、内部类等可能与原始源码略有差异，用于对比逻辑变化已足够。

**Q: 下载报 401/403？**
A: 私服需要认证，使用 `--user` / `--password` 传入凭据。
