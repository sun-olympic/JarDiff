# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把 JarDiff 冻结为自包含程序（不依赖系统 Python）。

跨平台：
- macOS  -> 生成 JarDiff.app（BUNDLE），图标 icon.icns
- Windows -> 生成 dist/JarDiff/JarDiff.exe（onedir），图标 icon.ico
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

datas = [
    ("jardiff_app/web", "jardiff_app/web"),         # 前端 + 内置 Monaco
]
# 按平台带上对应图标资源（运行期 _set_dock_icon 会用到 icns）
if os.path.exists("jardiff_app/icon.icns"):
    datas.append(("jardiff_app/icon.icns", "jardiff_app"))
if os.path.exists("jardiff_app/icon.ico"):
    datas.append(("jardiff_app/icon.ico", "jardiff_app"))

datas += collect_data_files("webview")              # pywebview 自带资源

hiddenimports = []
hiddenimports += collect_submodules("webview")
hiddenimports += ["jar_diff"]
if IS_WIN:
    # Windows 使用 Edge WebView2(EdgeChromium)，依赖 pythonnet(clr)
    hiddenimports += ["clr"]
    try:
        hiddenimports += collect_submodules("clr_loader")
    except Exception:
        pass

ICON = "jardiff_app/icon.ico" if IS_WIN else "jardiff_app/icon.icns"

a = Analysis(
    ["jardiff_main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JarDiff",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if os.path.exists(ICON) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="JarDiff",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="JarDiff.app",
        icon="jardiff_app/icon.icns",
        bundle_identifier="com.example.jardiff",
        version="1.0.0",
        info_plist={
            "CFBundleName": "JarDiff",
            "CFBundleDisplayName": "JarDiff",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
