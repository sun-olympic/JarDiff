"""pywebview 后端 API：复用 jar_diff.py 的核心逻辑，向前端暴露比较与取 diff 的方法。"""

import atexit
import contextlib
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import traceback
from pathlib import Path

# 让本模块无论从源码还是打包后的 .app 都能找到 jar_diff
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
for _p in (_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import jar_diff as jd  # noqa: E402


# 应用默认使用公共 Maven 仓库（中央仓库）；用户可在页面上修改并保存
DEFAULT_PUBLIC_REPO = "https://repo1.maven.org/maven2"

# 设置持久化到磁盘（localStorage 在 pywebview 随机端口下不可靠）
if sys.platform == "win32":
    SETTINGS_DIR = os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), "JarDiff")
else:
    SETTINGS_DIR = os.path.expanduser("~/.config/jardiff")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

# 下载的临时 JAR 统一放在此前缀目录下，便于退出/启动时清理
TMP_PREFIX = "jardiff_app_"

# 出于安全考虑不落盘的字段
_SECRET_KEYS = {"password"}


# 文件扩展名 → Monaco 语言标识
_LANG_MAP = {
    ".java": "java",
    ".xml": "xml",
    ".properties": "ini",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".js": "javascript",
    ".ts": "typescript",
    ".sql": "sql",
    ".md": "markdown",
    ".txt": "plaintext",
    ".factories": "ini",
}


def _cleanup_orphan_tmp(exclude: str | None = None):
    """清理临时目录下所有 jardiff_app_* 残留目录（上次运行或崩溃遗留）。"""
    pattern = os.path.join(tempfile.gettempdir(), TMP_PREFIX + "*")
    for d in glob.glob(pattern):
        if exclude and os.path.abspath(d) == os.path.abspath(exclude):
            continue
        shutil.rmtree(d, ignore_errors=True)


def _guess_language(display_name: str) -> str:
    name = display_name.lower()
    if name.endswith(".bytecode.txt"):
        return "plaintext"
    suffix = Path(name).suffix
    return _LANG_MAP.get(suffix, "plaintext")


class JarDiffApi:
    """暴露给前端 JS 的 API。所有 public 方法会被 window.pywebview.api 调用。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._old_entries: dict[str, bytes] = {}
        self._new_entries: dict[str, bytes] = {}
        self._decompile = False
        self._decompiler_jar: str | None = None
        self._tmp_dir: str | None = None
        # 启动时清理历史遗留的临时目录（上次/崩溃残留），并注册退出清理
        _cleanup_orphan_tmp(exclude=None)
        atexit.register(self._cleanup_tmp)

    # ---------- 内部辅助 ----------

    def _cleanup_tmp(self):
        if self._tmp_dir:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None

    def _resolve_decompiler(self, mode: str, repo: str,
                            user: str | None, password: str | None,
                            insecure: bool = False):
        """根据前端选择返回 (decompile?, decompiler_jar)。
        mode: none | javap | cfr | <自定义路径>"""
        mode = (mode or "none").strip()
        if mode == "none":
            return False, None
        if mode == "javap":
            return True, None
        # cfr / auto / 自定义路径 → 交给 jar_diff 解析（cfr 会自动下载）
        jar = jd.resolve_decompiler(mode, repo, user, password, insecure)
        return True, jar

    # ---------- 暴露给前端的方法 ----------

    def ping(self) -> dict:
        return {"ok": True, "version": jd.__dict__.get("__version__", ""),
                "python": sys.version.split()[0]}

    def compare(self, payload: dict) -> dict:
        """比较两个 JAR。payload 字段见前端 app.js。
        返回 {ok, summary, files, log, error}。"""
        log_buf = io.StringIO()
        try:
            old_src = (payload.get("old") or "").strip()
            new_src = (payload.get("new") or "").strip()
            if not old_src or not new_src:
                return {"ok": False, "error": "请填写两个 JAR 来源（本地路径 / URL / Maven 坐标）"}

            repo = (payload.get("repo") or DEFAULT_PUBLIC_REPO).strip()
            user = (payload.get("user") or "").strip() or None
            password = (payload.get("password") or "").strip() or None
            decompiler_mode = payload.get("decompiler") or "none"
            filter_str = (payload.get("filter") or "").strip()
            ignore_meta = bool(payload.get("ignoreMeta"))
            insecure = bool(payload.get("insecure"))

            with self._lock:
                self._cleanup_tmp()
                self._tmp_dir = tempfile.mkdtemp(prefix=TMP_PREFIX)

                with contextlib.redirect_stdout(log_buf):
                    decompile, decompiler_jar = self._resolve_decompiler(
                        decompiler_mode, repo, user, password, insecure)

                    old_path = jd.resolve_to_local_jar(
                        old_src, self._tmp_dir, "old", repo, user, password, insecure)
                    new_path = jd.resolve_to_local_jar(
                        new_src, self._tmp_dir, "new", repo, user, password, insecure)

                    old_entries = jd.read_jar_entries(old_path)
                    new_entries = jd.read_jar_entries(new_path)

                if ignore_meta:
                    old_entries = {k: v for k, v in old_entries.items()
                                   if not k.startswith("META-INF/")}
                    new_entries = {k: v for k, v in new_entries.items()
                                   if not k.startswith("META-INF/")}
                if filter_str:
                    old_entries = {k: v for k, v in old_entries.items() if filter_str in k}
                    new_entries = {k: v for k, v in new_entries.items() if filter_str in k}

                added, removed, modified = jd.classify_entries(
                    old_entries, new_entries, decompile=decompile, decompiler_jar=decompiler_jar
                )

                self._old_entries = old_entries
                self._new_entries = new_entries
                self._decompile = decompile
                self._decompiler_jar = decompiler_jar

            files = (
                [{"path": f, "status": "modified"} for f in modified]
                + [{"path": f, "status": "added"} for f in added]
                + [{"path": f, "status": "removed"} for f in removed]
            )
            unchanged = len(set(old_entries) & set(new_entries)) - len(modified)
            summary = {
                "oldCount": len(old_entries),
                "newCount": len(new_entries),
                "added": len(added),
                "removed": len(removed),
                "modified": len(modified),
                "unchanged": unchanged,
            }
            return {"ok": True, "summary": summary, "files": files,
                    "log": log_buf.getvalue()}
        except Exception as e:
            return {"ok": False,
                    "error": f"{e}",
                    "log": log_buf.getvalue() + "\n" + traceback.format_exc()}

    def get_diff(self, path: str) -> dict:
        """返回某个文件的旧/新文本，用于 Monaco 对比。"""
        try:
            with self._lock:
                old_data = self._old_entries.get(path)
                new_data = self._new_entries.get(path)
                decompile = self._decompile
                decompiler_jar = self._decompiler_jar

            if old_data is None and new_data is None:
                return {"ok": False, "error": "找不到该文件，请重新比较"}

            old_text, suffix = jd.render_entry_text(path, old_data, decompile, decompiler_jar)
            new_text, _ = jd.render_entry_text(path, new_data, decompile, decompiler_jar)

            renderable = not (old_text is None and new_text is None)
            display_name = path + (suffix or "")

            if not renderable:
                note = ("（二进制内容或未启用反编译，无法显示文本对比。"
                        "如为 .class，请在上方选择 javap 或 CFR 反编译方式后重新比较）")
                return {"ok": True, "renderable": False,
                        "old": "", "new": "", "language": "plaintext",
                        "note": note, "displayName": display_name}

            return {
                "ok": True,
                "renderable": True,
                "old": old_text or "",
                "new": new_text or "",
                "language": _guess_language(display_name),
                "displayName": display_name,
            }
        except Exception as e:
            return {"ok": False, "error": f"{e}"}

    def default_repo(self) -> str:
        return DEFAULT_PUBLIC_REPO

    def load_settings(self) -> dict:
        """读取已保存的页面设置（旧/新 JAR、仓库、反编译方式、过滤等）。"""
        data: dict = {}
        try:
            if os.path.isfile(SETTINGS_PATH):
                with open(SETTINGS_PATH, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}
        # 仓库地址缺省回落到公共仓库
        if not data.get("repo"):
            data["repo"] = DEFAULT_PUBLIC_REPO
        # 默认勾选忽略 SSL 校验（如果设置中无此项，则默认设为 True）
        if "insecure" not in data:
            data["insecure"] = True
        return {"ok": True, "settings": data}

    def save_settings(self, settings: dict) -> dict:
        """保存页面设置到磁盘。密码等敏感字段不落盘。"""
        try:
            data = {k: v for k, v in dict(settings or {}).items()
                    if k not in _SECRET_KEYS}
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            tmp = SETTINGS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SETTINGS_PATH)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
