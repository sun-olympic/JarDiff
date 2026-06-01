"""PyInstaller 打包入口：启动 JarDiff 桌面应用。"""

import os
import sys
import traceback

def show_error_message(title: str, message: str) -> None:
    """在启动失败时展示友好的错误对话框，避免闪退无提示。"""
    if sys.platform == "win32":
        try:
            import ctypes
            # MB_ICONERROR = 0x10 | MB_OK = 0x0
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)
        except Exception:
            print(f"[{title}] {message}", file=sys.stderr)
    elif sys.platform == "darwin":
        try:
            import subprocess
            escaped_msg = message.replace('"', '\\"').replace('\n', '\\r')
            escaped_title = title.replace('"', '\\"')
            applescript = f'display dialog "{escaped_msg}" with title "{escaped_title}" buttons {{"OK"}} default button "OK" with icon stop'
            subprocess.run(["osascript", "-e", applescript])
        except Exception:
            print(f"[{title}] {message}", file=sys.stderr)
    else:
        print(f"[{title}] {message}", file=sys.stderr)


def unblock_directory(directory: str) -> None:
    """递归清除目录中所有 .dll 和 .pyd 文件的 Zone.Identifier（Mark of the Web），
    解决 Windows 绿色版从网络下载解压后，由于系统安全拦截导致的 Python.Runtime.dll 加载失败问题。
    """
    if sys.platform != "win32":
        return
    try:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith((".dll", ".pyd")):
                    filepath = os.path.join(root, file)
                    try:
                        # 尝试删除 NTFS 备用数据流 Zone.Identifier
                        os.remove(filepath + ":Zone.Identifier")
                    except OSError:
                        pass
    except Exception:
        pass


# 针对 Windows 绿色版从网络下载解压后，各 DLL 被系统标记 Zone.Identifier 导致加载失败的问题，
# 在载入任何 pywebview / pythonnet 依赖前，递归清除解压目录中所有 DLL 的 Zone.Identifier。
if getattr(sys, "frozen", False) and sys.platform == "win32":
    unblock_directory(os.path.dirname(sys.executable))

# 针对 Python 3.8+ Windows 平台打包，需将 sys._MEIPASS 加进 DLL 搜索路径，
# 否则 pythonnet 和 clr_loader 将无法正确加载 ClrLoader.dll 和 Python.Runtime.dll
if getattr(sys, "frozen", False):
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(sys._MEIPASS)
        except Exception:
            pass

from jardiff_app.app import main

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        show_error_message(
            "JarDiff 启动失败",
            f"应用程序启动时发生错误：\n{str(e)}\n\n详细堆栈信息：\n{tb}"
        )
        sys.exit(1)
