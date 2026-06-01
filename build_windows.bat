@echo off
REM ============================================================
REM  JarDiff Windows 打包脚本
REM  在 Windows 上运行（需已安装 Python 3.10+ 与 JDK，建议 PowerShell/CMD）
REM  产物：dist\JarDiff\JarDiff.exe（onedir 自包含目录）
REM  如需生成安装程序(.exe installer)，再用 Inno Setup 编译 packaging\jardiff_inno.iss
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul 2>nul

echo [1/5] 检查 Python...
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.10+ 并加入 PATH
  exit /b 1
)

echo [2/5] 创建/复用虚拟环境 .venv-win ...
if not exist ".venv-win\Scripts\python.exe" (
  python -m venv .venv-win
  if errorlevel 1 ( echo [错误] 创建虚拟环境失败 & exit /b 1 )
)
call .venv-win\Scripts\activate.bat

echo [3/5] 安装依赖...
python -m pip install --upgrade pip
python -m pip install -r packaging\requirements-windows.txt
if errorlevel 1 ( echo [错误] 依赖安装失败 & exit /b 1 )

echo [4/5] 生成 Windows 图标 icon.ico（若缺失）...
if not exist "jardiff_app\icon.ico" (
  if exist "jardiff_app\icon_1024.png" (
    python make_icon.py
  ) else (
    echo [警告] 缺少 icon.ico 且无 icon_1024.png，可执行文件将使用默认图标
  )
)

echo [5/5] PyInstaller 打包...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
pyinstaller --noconfirm jardiff.spec
if errorlevel 1 ( echo [错误] 打包失败 & exit /b 1 )

echo.
echo ============================================================
echo  打包完成: dist\JarDiff\JarDiff.exe
echo  双击运行即可；如需安装程序，请用 Inno Setup 编译:
echo    packaging\jardiff_inno.iss
echo ============================================================
endlocal
