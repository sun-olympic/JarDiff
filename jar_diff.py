#!/usr/bin/env python3
"""比较两个 JAR 包的代码变化，输出新增/删除/修改的文件列表及详细 diff。"""

import argparse
import base64
import difflib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

TEXT_EXTENSIONS = {
    ".java", ".xml", ".properties", ".yml", ".yaml", ".json",
    ".txt", ".md", ".html", ".css", ".js", ".ts", ".sql",
    ".MF", ".SF", ".RSA", ".DSA", ".cfg", ".conf", ".ini",
    ".factories", ".imports", ".handlers",
}

IGNORE_PATTERNS = {
    "META-INF/MANIFEST.MF",
}

DEFAULT_MAVEN_REPO = "https://repo.zhaopin.com/repository/maven-public/"

# 自动下载的反编译器（CFR），缓存到本地后复用
CFR_COORD = "org.benf:cfr:0.152"
if sys.platform == "win32":
    DECOMPILER_CACHE_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "JarDiff", "cache")
else:
    DECOMPILER_CACHE_DIR = os.path.expanduser("~/.cache/jar_diff")

COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"


def colored(text: str, color: str) -> str:
    if sys.stdout.isatty():
        return f"{color}{text}{COLOR_RESET}"
    return text


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def read_jar_entries(jar_path: str) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(jar_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            entries[info.filename] = zf.read(info.filename)
    return entries


def _build_auth_header(user: str | None, password: str | None) -> dict[str, str]:
    if not user:
        return {}
    token = base64.b64encode(f"{user}:{password or ''}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def download_file(url: str, dest_path: str, user: str | None = None,
                  password: str | None = None) -> None:
    """下载远程文件到本地路径。"""
    headers = {"User-Agent": "jar-diff/1.0"}
    headers.update(_build_auth_header(user, password))
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as out:
            shutil.copyfileobj(resp, out)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"下载失败 ({e.code} {e.reason}): {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"下载失败 ({e.reason}): {url}") from e


def maven_coord_to_url(coord: str, repo_base: str) -> str:
    """将 Maven 坐标 groupId:artifactId:version[:classifier] 转为下载 URL。"""
    parts = coord.split(":")
    if len(parts) < 3:
        raise ValueError(f"Maven 坐标格式错误（需 groupId:artifactId:version[:classifier]）: {coord}")
    group_id, artifact_id, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) >= 4 else None

    group_path = group_id.replace(".", "/")
    jar_name = f"{artifact_id}-{version}"
    if classifier:
        jar_name += f"-{classifier}"
    jar_name += ".jar"

    repo_base = repo_base.rstrip("/")
    return f"{repo_base}/{group_path}/{artifact_id}/{version}/{jar_name}"


def looks_like_maven_coord(value: str) -> bool:
    if os.path.isfile(value):
        return False
    if value.startswith(("http://", "https://")):
        return False
    parts = value.split(":")
    return len(parts) in (3, 4) and all(parts[:3])


def resolve_to_local_jar(
    source: str,
    tmp_dir: str,
    prefix: str,
    repo_base: str,
    user: str | None,
    password: str | None,
) -> str:
    """将来源（本地路径 / URL / Maven 坐标）解析为本地 JAR 文件路径。"""
    if os.path.isfile(source):
        return source

    if source.startswith(("http://", "https://")):
        url = source
    elif looks_like_maven_coord(source):
        url = maven_coord_to_url(source, repo_base)
    else:
        raise RuntimeError(f"无法识别的 JAR 来源（不是文件、URL 或 Maven 坐标）: {source}")

    dest = os.path.join(tmp_dir, f"{prefix}.jar")
    print(colored(f"  ↓ 下载 {url}", COLOR_CYAN))
    download_file(url, dest, user, password)
    size_kb = os.path.getsize(dest) / 1024
    print(colored(f"    完成 ({size_kb:.1f} KB) → {dest}", COLOR_CYAN))
    return dest


def resolve_decompiler(value: str, repo_base: str,
                       user: str | None, password: str | None) -> str:
    """解析 --decompiler 参数为可用的反编译器 jar 路径。
    - 已存在的文件：直接使用。
    - 'cfr' / 'auto'：自动下载 CFR 到缓存目录。
    - 不存在但文件名含 'cfr'：自动下载 CFR 到该路径。
    - 其它不存在路径：报错。"""
    if os.path.isfile(value):
        return value

    name = os.path.basename(value).lower()
    want_cfr = value.lower() in ("cfr", "auto") or "cfr" in name
    if not want_cfr:
        raise RuntimeError(f"反编译器 jar 不存在 — {value}"
                           f"（可用 --decompiler cfr 自动下载 CFR）")

    if value.lower() in ("cfr", "auto"):
        os.makedirs(DECOMPILER_CACHE_DIR, exist_ok=True)
        version = CFR_COORD.split(":")[2]
        dest = os.path.join(DECOMPILER_CACHE_DIR, f"cfr-{version}.jar")
    else:
        dest = os.path.expanduser(value)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

    if os.path.isfile(dest):
        return dest

    url = maven_coord_to_url(CFR_COORD, repo_base)
    print(colored(f"  ↓ 自动下载反编译器 CFR: {url}", COLOR_CYAN))
    try:
        download_file(url, dest, user, password)
    except RuntimeError:
        # 私服没有时回退到 Maven 中央仓库
        fallback = maven_coord_to_url(CFR_COORD, "https://repo1.maven.org/maven2")
        print(colored(f"    私服未命中，改用中央仓库: {fallback}", COLOR_YELLOW))
        download_file(fallback, dest, None, None)
    size_kb = os.path.getsize(dest) / 1024
    print(colored(f"    完成 ({size_kb:.1f} KB) → {dest}", COLOR_CYAN))
    return dest


def is_text_file(filename: str) -> bool:
    suffix = Path(filename).suffix
    if suffix in TEXT_EXTENSIONS:
        return True
    name = Path(filename).name
    return name in {"MANIFEST.MF", "spring.factories", "spring.handlers", "spring.schemas"}


def _run_decompiler_jar(decompiler_jar: str, class_path: str) -> str | None:
    """用外部反编译器 jar（CFR / Procyon / Fernflower）反编译为 Java 源码。"""
    name = os.path.basename(decompiler_jar).lower()
    try:
        if "procyon" in name:
            cmd = ["java", "-jar", decompiler_jar, class_path]
        elif "fernflower" in name:
            out_dir = tempfile.mkdtemp(prefix="fernflower_")
            subprocess.run(["java", "-jar", decompiler_jar, class_path, out_dir],
                           capture_output=True, text=True, timeout=30)
            for f in Path(out_dir).glob("*.java"):
                text = f.read_text(encoding="utf-8", errors="replace")
                shutil.rmtree(out_dir, ignore_errors=True)
                return text
            shutil.rmtree(out_dir, ignore_errors=True)
            return None
        else:
            cmd = ["java", "-jar", decompiler_jar, class_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout if result.stdout.strip() else None
    except Exception:
        return None


def decompile_class(class_bytes: bytes, filename: str,
                    decompiler_jar: str | None = None) -> str | None:
    """反编译 .class 字节码为文本。
    指定 decompiler_jar 时输出 Java 源码，否则用 javap 输出字节码。"""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".class", delete=False) as tmp:
            tmp.write(class_bytes)
            tmp_path = tmp.name
        if decompiler_jar:
            text = _run_decompiler_jar(decompiler_jar, tmp_path)
            if text is not None:
                return text
            # 反编译器失败时回退到 javap
        result = subprocess.run(
            ["javap", "-p", "-c", tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# 匹配未被反斜杠转义的 \uXXXX（反编译器/properties 常把中文转义成此形式）
_UNICODE_ESC_RE = re.compile(r"(?<!\\)\\u([0-9a-fA-F]{4})")


def unescape_unicode(text: str | None) -> str | None:
    """把 \\uXXXX 转义还原为对应字符（如中文），便于阅读。
    反编译出的 Java 源码 / .properties 里的中文常被转义成 \\uXXXX。"""
    if not text or "\\u" not in text:
        return text
    return _UNICODE_ESC_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def render_entry_text(filename: str, data: bytes | None, decompile: bool,
                      decompiler_jar: str | None) -> tuple[str | None, str]:
    """把条目内容渲染为可读文本，返回 (文本, 用于展示的文件名后缀)。
    返回的后缀决定导出/编辑器对比时使用的扩展名（旧、新需一致）。"""
    if data is None:
        ext = ".java" if (filename.endswith(".class") and decompile and decompiler_jar) \
            else (".bytecode.txt" if filename.endswith(".class") else "")
        return None, ext

    if filename.endswith(".class") and decompile:
        text = decompile_class(data, filename, decompiler_jar)
        ext = ".java" if decompiler_jar else ".bytecode.txt"
        return unescape_unicode(text), ext
    if is_text_file(filename):
        return unescape_unicode(decode_text(data)), ""
    return None, ""


def decode_text(data: bytes) -> str | None:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def unified_diff(a_text: str, b_text: str, a_label: str, b_label: str) -> str:
    a_lines = a_text.splitlines(keepends=True)
    b_lines = b_text.splitlines(keepends=True)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile=a_label, tofile=b_label, lineterm="")
    return "".join(diff)


def classify_entries(
    old_entries: dict[str, bytes],
    new_entries: dict[str, bytes],
) -> tuple[list[str], list[str], list[str]]:
    old_keys = set(old_entries.keys())
    new_keys = set(new_entries.keys())

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    common = sorted(old_keys & new_keys)

    modified = [f for f in common if md5(old_entries[f]) != md5(new_entries[f])]
    return added, removed, modified


def print_section(title: str, items: list[str], color: str):
    if not items:
        return
    print(colored(f"\n{'='*60}", color))
    print(colored(f" {title} ({len(items)} 个文件)", color))
    print(colored(f"{'='*60}", color))
    for item in items:
        print(f"  {item}")


def print_diff_for_file(
    filename: str,
    old_data: bytes | None,
    new_data: bytes | None,
    show_diff: bool,
    decompile: bool,
    decompiler_jar: str | None = None,
):
    if not show_diff:
        return

    old_text, _ = render_entry_text(filename, old_data, decompile, decompiler_jar)
    new_text, _ = render_entry_text(filename, new_data, decompile, decompiler_jar)

    if old_text is None and new_text is None:
        return

    old_text = old_text or ""
    new_text = new_text or ""

    diff = unified_diff(old_text, new_text, f"a/{filename}", f"b/{filename}")
    if diff.strip():
        print(colored(f"\n--- diff: {filename} ---", COLOR_CYAN))
        for line in diff.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                print(colored(line, COLOR_BOLD))
            elif line.startswith("+"):
                print(colored(line, COLOR_GREEN))
            elif line.startswith("-"):
                print(colored(line, COLOR_RED))
            elif line.startswith("@@"):
                print(colored(line, COLOR_CYAN))
            else:
                print(line)


def detect_editor(preferred: str | None) -> list[str] | None:
    """探测可用的对比编辑器，返回形如 ['cursor', '--diff'] 的命令前缀。"""
    candidates: list[str]
    if preferred and preferred != "auto":
        candidates = [preferred]
    else:
        env = os.environ.get("JAR_DIFF_EDITOR")
        candidates = [env] if env else ["cursor", "code", "code-insiders"]
    for cmd in candidates:
        if cmd and shutil.which(cmd):
            return [cmd, "--diff"]
    return None


def _write_side(base_dir: str, filename: str, text: str, suffix: str) -> str:
    """把渲染后的文本写入 base_dir 下的对应路径，返回写入的文件路径。"""
    rel = filename + suffix
    path = os.path.join(base_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def export_changes(
    out_dir: str,
    added: list[str],
    removed: list[str],
    modified: list[str],
    old_entries: dict[str, bytes],
    new_entries: dict[str, bytes],
    decompile: bool,
    decompiler_jar: str | None,
) -> tuple[str, str, list[tuple[str, str | None, str | None]]]:
    """把变更前后的内容导出到 out_dir/old 与 out_dir/new 两个目录树。
    返回 (old_dir, new_dir, pairs)，pairs 为 [(展示名, 旧文件路径, 新文件路径)]。"""
    old_dir = os.path.join(out_dir, "old")
    new_dir = os.path.join(out_dir, "new")
    pairs: list[tuple[str, str | None, str | None]] = []

    def handle(filename: str, in_old: bool, in_new: bool):
        old_data = old_entries.get(filename) if in_old else None
        new_data = new_entries.get(filename) if in_new else None
        old_text, suffix = render_entry_text(filename, old_data, decompile, decompiler_jar)
        new_text, _ = render_entry_text(filename, new_data, decompile, decompiler_jar)
        if old_text is None and new_text is None:
            return  # 二进制等无法渲染的内容，跳过
        old_path = _write_side(old_dir, filename, old_text or "", suffix) if in_old else None
        new_path = _write_side(new_dir, filename, new_text or "", suffix) if in_new else None
        pairs.append((filename + suffix, old_path, new_path))

    for f in modified:
        handle(f, True, True)
    for f in added:
        handle(f, False, True)
    for f in removed:
        handle(f, True, False)

    return old_dir, new_dir, pairs


def open_in_editor(
    editor_cmd: list[str],
    pairs: list[tuple[str, str | None, str | None]],
    max_open: int,
):
    """对每个变更文件调用编辑器的对比视图。"""
    shown = pairs[:max_open]
    skipped = len(pairs) - len(shown)
    print(colored(f"\n在编辑器中打开 {len(shown)} 个对比"
                  f"（命令: {' '.join(editor_cmd)}）…", COLOR_CYAN))
    for name, old_path, new_path in shown:
        # 新增/删除：用空文件占位，保证 diff 视图可打开
        left = old_path or os.devnull
        right = new_path or os.devnull
        try:
            subprocess.run([*editor_cmd, left, right], timeout=30)
        except Exception as e:
            print(colored(f"  打开失败 {name}: {e}", COLOR_RED))
    if skipped > 0:
        print(colored(f"  （已省略 {skipped} 个，使用 --max-open 调整或加 --filter 缩小范围）",
                      COLOR_YELLOW))


def main():
    parser = argparse.ArgumentParser(
        description="比较两个 JAR 包的代码变化",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 本地文件对比
  %(prog)s old.jar new.jar --diff

  # 直接 URL 下载对比
  %(prog)s https://repo/a-1.0.jar https://repo/a-1.1.jar --diff

  # Maven 坐标对比（默认中央仓库）
  %(prog)s com.google.guava:guava:31.0-jre com.google.guava:guava:32.0-jre --diff

  # 指定私服仓库 + 认证
  %(prog)s g:a:1.0 g:a:1.1 --repo https://repo.zhaopin.com/repository/maven-public/ \\
           --user alice --password secret

  # 混用：本地包 vs 仓库包
  %(prog)s ./old.jar com.google.guava:guava:32.0-jre --diff

  # 在对比编辑器中逐文件查看变更（自动探测 cursor/code）
  %(prog)s old.jar new.jar --editor

  # 用 CFR 反编译成 Java 源码后再对比，并在 Cursor 中打开
  %(prog)s old.jar new.jar --editor cursor --decompiler ~/tools/cfr.jar

  # 把变更前后内容导出到目录树，供任意 diff 工具对比
  %(prog)s old.jar new.jar --export ./diff_out --decompiler ~/tools/cfr.jar
""",
    )
    parser.add_argument("old_jar", help="旧版 JAR：本地路径 / URL / Maven 坐标(g:a:v[:classifier])")
    parser.add_argument("new_jar", help="新版 JAR：本地路径 / URL / Maven 坐标(g:a:v[:classifier])")
    parser.add_argument("--diff", action="store_true", help="显示修改文件的详细 diff")
    parser.add_argument("--decompile", action="store_true",
                        help="使用 javap 反编译 .class 文件再做 diff（较慢）")
    parser.add_argument("--filter", type=str, default=None,
                        help="只显示路径包含指定字符串的文件（如 com/example）")
    parser.add_argument("--ignore-meta", action="store_true",
                        help="忽略 META-INF 目录下的文件")
    parser.add_argument("--repo", type=str, default=DEFAULT_MAVEN_REPO,
                        help=f"Maven 仓库基址（用于解析坐标），默认: {DEFAULT_MAVEN_REPO}")
    parser.add_argument("--user", type=str, default=None, help="仓库认证用户名（Basic Auth）")
    parser.add_argument("--password", type=str, default=None, help="仓库认证密码（Basic Auth）")
    parser.add_argument("--keep-downloads", action="store_true",
                        help="保留下载的临时 JAR 文件（默认运行结束后删除）")
    parser.add_argument("--editor", nargs="?", const="auto", default=None, metavar="CMD",
                        help="在对比编辑器中逐文件打开变更（默认自动探测 cursor/code，"
                             "也可指定命令如 --editor cursor）")
    parser.add_argument("--export", type=str, default=None, metavar="DIR",
                        help="将变更前后的内容导出到 DIR/old 与 DIR/new 两个目录树")
    parser.add_argument("--decompiler", type=str, default=None, metavar="JAR",
                        help="反编译器 jar 路径（CFR/Procyon/Fernflower），用于把 .class "
                             "反编译成 Java 源码；不指定则用 javap 输出字节码。"
                             "传 'cfr' 或 'auto' 可自动下载 CFR；指定不存在的 *cfr*.jar "
                             "路径也会自动下载到该位置")
    parser.add_argument("--max-open", type=int, default=20, metavar="N",
                        help="编辑器模式下最多打开的对比数量，默认 20")

    args = parser.parse_args()

    # --editor / --export 隐含需要反编译 class 才能查看代码
    if (args.editor is not None or args.export) and not args.decompile:
        args.decompile = True

    if args.decompiler:
        try:
            args.decompiler = resolve_decompiler(
                args.decompiler, args.repo, args.user, args.password)
        except (RuntimeError, ValueError) as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

    tmp_dir = tempfile.mkdtemp(prefix="jar_diff_")
    try:
        print(colored(f"旧包来源: {args.old_jar}", COLOR_BOLD))
        print(colored(f"新包来源: {args.new_jar}", COLOR_BOLD))

        try:
            old_path = resolve_to_local_jar(
                args.old_jar, tmp_dir, "old", args.repo, args.user, args.password)
            new_path = resolve_to_local_jar(
                args.new_jar, tmp_dir, "new", args.repo, args.user, args.password)
        except (RuntimeError, ValueError) as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)

        print("正在读取 JAR 内容…")
        old_entries = read_jar_entries(old_path)
        new_entries = read_jar_entries(new_path)

        run_comparison(old_entries, new_entries, args)
    finally:
        if args.keep_downloads:
            if os.path.isdir(tmp_dir) and os.listdir(tmp_dir):
                print(colored(f"\n下载文件已保留于: {tmp_dir}", COLOR_CYAN))
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def run_comparison(old_entries: dict[str, bytes], new_entries: dict[str, bytes], args):

    if args.ignore_meta:
        old_entries = {k: v for k, v in old_entries.items() if not k.startswith("META-INF/")}
        new_entries = {k: v for k, v in new_entries.items() if not k.startswith("META-INF/")}

    if args.filter:
        pat = args.filter
        old_entries = {k: v for k, v in old_entries.items() if pat in k}
        new_entries = {k: v for k, v in new_entries.items() if pat in k}

    added, removed, modified = classify_entries(old_entries, new_entries)

    # 统计
    print(colored(f"\n📊 变更总览", COLOR_BOLD))
    print(f"  旧包文件数: {len(old_entries)}")
    print(f"  新包文件数: {len(new_entries)}")
    print(colored(f"  新增: {len(added)}", COLOR_GREEN))
    print(colored(f"  删除: {len(removed)}", COLOR_RED))
    print(colored(f"  修改: {len(modified)}", COLOR_YELLOW))

    unchanged = len(set(old_entries) & set(new_entries)) - len(modified)
    print(f"  未变: {unchanged}")

    print_section("新增文件", added, COLOR_GREEN)
    print_section("删除文件", removed, COLOR_RED)
    print_section("修改文件", modified, COLOR_YELLOW)

    decompiler = getattr(args, "decompiler", None)

    if args.diff:
        for f in added:
            print_diff_for_file(f, None, new_entries[f], True, args.decompile, decompiler)
        for f in removed:
            print_diff_for_file(f, old_entries[f], None, True, args.decompile, decompiler)
        for f in modified:
            print_diff_for_file(f, old_entries[f], new_entries[f], True, args.decompile, decompiler)

    if not added and not removed and not modified:
        print(colored("\n✅ 两个 JAR 包内容完全一致。", COLOR_GREEN))
        return

    # 导出 / 编辑器对比
    need_export = bool(args.export) or args.editor is not None
    if need_export:
        export_root = args.export or tempfile.mkdtemp(prefix="jar_diff_export_")
        old_dir, new_dir, pairs = export_changes(
            export_root, added, removed, modified,
            old_entries, new_entries, args.decompile, decompiler,
        )
        if args.export:
            print(colored(f"\n已导出变更内容到:", COLOR_CYAN))
            print(f"  旧版本: {old_dir}")
            print(f"  新版本: {new_dir}")
            print(f"  共 {len(pairs)} 个可对比文件")

        if args.editor is not None:
            editor_cmd = detect_editor(args.editor)
            if editor_cmd is None:
                print(colored("\n未找到可用的对比编辑器（cursor/code）。"
                              "可用 --editor <命令> 指定，或设置 JAR_DIFF_EDITOR 环境变量。",
                              COLOR_RED))
                if not args.export:
                    print(colored(f"变更内容已导出到: {export_root}", COLOR_CYAN))
            elif not pairs:
                print(colored("\n没有可在编辑器中对比的文本/源码文件。", COLOR_YELLOW))
            else:
                open_in_editor(editor_cmd, pairs, args.max_open)
                if not args.export:
                    print(colored(f"（临时导出目录: {export_root}）", COLOR_CYAN))


if __name__ == "__main__":
    main()
