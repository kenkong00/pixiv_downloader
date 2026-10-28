@echo off
title Pixiv 图片批量下载器

cd /d "%~dp0"

if not exist "main.py" (
    echo [错误] 未找到 main.py，请确认本启动文件位于项目根目录。
    pause
    exit /b 1
)

set "PYTHON_BIN="
call :try "C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe"
if not defined PYTHON_BIN call :try python
if not defined PYTHON_BIN call :try py
if not defined PYTHON_BIN call :try python3

if not defined PYTHON_BIN (
    echo [错误] 未找到可用的 Python 环境（需要已安装 PyQt6 / requests / Pillow）。
    echo 请先在命令提示符中执行： python -m pip install -r requirements.txt
    echo 或直接用命令启动： python main.py
    pause
    exit /b 1
)

echo 正在启动 Pixiv 图片批量下载器 ...
"%PYTHON_BIN%" main.py 2>"%~dp0_error.log"
if errorlevel 1 (
    echo.
    echo [错误] 程序启动失败，最近的错误信息如下：
    echo ----------------------------------------
    type "%~dp0_error.log" 2>nul
    echo ----------------------------------------
    echo 完整日志已保存到 _error.log
    pause
    exit /b 1
)

del "%~dp0_error.log" 2>nul
exit /b 0

:try
"%~1" -c "import PyQt6, requests, PIL" >nul 2>&1
if not errorlevel 1 set "PYTHON_BIN=%~1"
exit /b
