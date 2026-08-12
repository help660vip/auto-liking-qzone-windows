@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto install_dependencies

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
    goto check_environment
)

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.9 或更高版本，并勾选 Add Python to PATH。
    exit /b 1
)
python -m venv .venv

:check_environment
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 虚拟环境创建失败。
    exit /b 1
)

:install_dependencies
echo [安装] 正在安装项目依赖...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [完成] 依赖已安装。运行 start.bat 即可启动。
