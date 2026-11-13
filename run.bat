@echo off
chcp 936 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Curviva

REM ---- 环境自检：虚拟环境不存在则提示先安装 ----
if not exist "venv\Scripts\python.exe" (
    echo.
    echo   [未找到虚拟环境]
    echo.
    echo   请先双击运行 first_run.bat 完成一键环境安装，
    echo   安装完成后再双击本文件启动 Curviva。
    echo.
    pause
    exit /b 1
)

set "VPY=%CD%\venv\Scripts\python.exe"

REM ---- 依赖自检 ----
"%VPY%" -c "import PySide6, matplotlib, numpy, openpyxl" 2>nul
if errorlevel 1 (
    echo.
    echo   [依赖不完整] 缺少 PySide6 / matplotlib / numpy / openpyxl。
    echo   请重新运行 first_run.bat 安装依赖。
    echo.
    pause
    exit /b 1
)

REM ---- 启动（使用 pythonw，无控制台窗口）----
if exist "venv\Scripts\pythonw.exe" (
    start "" "%CD%\venv\Scripts\pythonw.exe" "main.py"
) else (
    "%VPY%" "main.py"
)
exit /b 0
