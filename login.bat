@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 尚未安装依赖，请先运行 install.bat。
    exit /b 1
)

".venv\Scripts\python.exe" ck.py --manual %*
