"""JarDiff 桌面应用入口：用 pywebview 创建原生窗口并加载内嵌 Monaco diff 界面。"""

import os
import sys

import webview

from jardiff_app import APP_NAME, __version__
from jardiff_app.backend import JarDiffApi


def _web_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _index_path() -> str:
    return os.path.join(_web_dir(), "index.html")


def _icon_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.icns")


def _set_dock_icon(*_args):
    """在 macOS Dock / 程序坞中显示应用自带图标（覆盖默认 Python 图标）。"""
    try:
        from AppKit import NSApplication, NSImage  # type: ignore
        icon = _icon_path()
        if not os.path.isfile(icon):
            return
        app = NSApplication.sharedApplication()
        image = NSImage.alloc().initWithContentsOfFile_(icon)
        if image is not None:
            app.setApplicationIconImage_(image)
    except Exception:
        pass


def _selfcheck() -> int:
    """打包后自检：校验资源与依赖是否完整（不启动窗口）。"""
    ok = True
    idx = _index_path()
    loader = os.path.join(_web_dir(), "vendor", "vs", "loader.js")
    icon = _icon_path()
    print("index.html:", os.path.isfile(idx))
    print("monaco(vendor):", os.path.isfile(loader))
    print("icon.icns:", os.path.isfile(icon))
    try:
        from jardiff_app.backend import JarDiffApi as _Api
        print("backend:", _Api().default_repo())
    except Exception as e:
        ok = False
        print("backend 导入失败:", e)
    try:
        import webview  # noqa: F401
        print("pywebview: ok")
    except Exception as e:
        ok = False
        print("pywebview 导入失败:", e)
    print("SELFCHECK:", "PASS" if (ok and os.path.isfile(idx)) else "FAIL")
    return 0 if ok else 1


def main():
    if os.environ.get("JARDIFF_SELFCHECK") == "1":
        sys.exit(_selfcheck())

    api = JarDiffApi()
    index = _index_path()
    if not os.path.isfile(index):
        print(f"找不到前端页面: {index}", file=sys.stderr)
        sys.exit(1)

    window = webview.create_window(
        title=f"{APP_NAME} {__version__} — JAR 包代码对比",
        url=index,
        js_api=api,
        width=1280,
        height=820,
        min_size=(960, 600),
    )
    # 窗口显示后设置 Dock 图标（此时 NSApplication 已就绪，最可靠）
    try:
        window.events.shown += _set_dock_icon
    except Exception:
        pass

    # gui=None 时 pywebview 在 macOS 自动使用 WKWebView（Cocoa）
    # http_server=True：用内置 HTTP 服务加载本地页面，避免 file:// 下 Monaco 资源/worker 受限
    _set_dock_icon()
    webview.start(
        http_server=True,
        debug=os.environ.get("JARDIFF_DEBUG") == "1",
    )


if __name__ == "__main__":
    main()
