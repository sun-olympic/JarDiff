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


def _check_webview2_on_windows() -> bool:
    """检查 Windows 上是否安装了 Microsoft Edge WebView2 Runtime。"""
    if sys.platform != "win32":
        return True
    try:
        import winreg
    except ImportError:
        return True

    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    paths = [
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\\" + guid,
        r"SOFTWARE\Microsoft\EdgeUpdate\Clients\\" + guid,
    ]
    
    for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in paths:
            for flags in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ | flags) as key:
                        pv, _ = winreg.QueryValueEx(key, "pv")
                        if pv and str(pv).strip():
                            return True
                except OSError:
                    continue
    return False


def _show_confirm_message_win(title: str, message: str) -> bool:
    """在 Windows 上显示带有 确定/取消 的警告对话框。确定返回 True，取消返回 False。"""
    try:
        import ctypes
        # MB_OKCANCEL = 0x1 | MB_ICONWARNING = 0x30
        res = ctypes.windll.user32.MessageBoxW(0, message, title, 0x1 | 0x30)
        return res == 1
    except Exception:
        return True


def main():
    if os.environ.get("JARDIFF_SELFCHECK") == "1":
        sys.exit(_selfcheck())

    if sys.platform == "win32":
        if not _check_webview2_on_windows():
            msg = (
                "检测到您的系统未安装 Microsoft Edge WebView2 运行时，JarDiff 启动可能白屏或闪退。\n\n"
                "建议前往微软官网下载并安装 WebView2 Runtime（常青引导程序）后重试：\n"
                "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
                "是否仍要尝试启动？"
            )
            if not _show_confirm_message_win("缺少 WebView2 运行时", msg):
                sys.exit(0)

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
