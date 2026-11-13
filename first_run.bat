@echo off
chcp 936 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Curviva 首次运行环境安装
color 0F

echo ============================================================
echo   Curviva v0.0.0  首次运行环境安装
echo   步骤: [1] 选择 Python  [2] 创建虚拟环境  [3] 安装依赖
echo ============================================================
echo.

REM ============================================================
REM [1] 检测本机已安装的 Python
REM ============================================================
echo [1/3] 正在检测本机 Python 环境...
echo.

set "PYLIST=%TEMP%\curviva_python_list.txt"
if exist "%PYLIST%" del /q "%PYLIST%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$list=@(); foreach($k in @('HKLM:\SOFTWARE\Python\PythonCore\*\InstallPath','HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore\*\InstallPath','HKCU:\SOFTWARE\Python\PythonCore\*\InstallPath')){ foreach($i in (Get-Item -Path $k -ErrorAction SilentlyContinue)){ $e=(Get-ItemProperty -Path $i.PSPath -ErrorAction SilentlyContinue).ExecutablePath; if(-not $e){ $e=Join-Path $i.PSPath 'python.exe' }; if(Test-Path $e){ $list+=$e } } }; if(Get-Command py -ErrorAction SilentlyContinue){ foreach($l in (& py -0p 2>$null)){ if($l -match '([A-Za-z]:\\.*python\.exe)'){ $list+=$matches[1] } } }; foreach($n in @('python','python3')){ $g=Get-Command $n -ErrorAction SilentlyContinue; if($g){ $src=$g.Source; if($n -eq 'python3' -and (Test-Path (Join-Path (Split-Path $src) 'python.exe'))){ continue }; $list+=$src } }; $seen=@{}; foreach($e in $list){ if(-not (Test-Path $e)){ continue }; if($e -like '*\WindowsApps\*'){ continue }; if($e -match 'msys|mingw'){ continue }; if($e -like '*\venv\Scripts\python.exe'){ continue }; $full=(Resolve-Path $e).Path; if($seen.ContainsKey($full)){ continue }; $seen[$full]=1; try { $v = & $full -c 'import sys;print(str(sys.version_info[0])+chr(46)+str(sys.version_info[1])+chr(46)+str(sys.version_info[2]))' 2>$null } catch { continue }; if($v){ $v + '|' + $full } }" < nul > "%PYLIST%" 2>nul

set /a PN=0
for /f "usebackq tokens=1,* delims=|" %%a in ("%PYLIST%") do (
    set /a PN+=1
    echo    [!PN!] Python %%a  -  %%b
)

if %PN%==0 (
    echo.
    echo   [未检测到 Python]
    echo.
    echo   请先安装 Python 3.9 或更高版本，安装时务必勾选
    echo   "Add python.exe to PATH" 选项。
    echo.
    echo   官方下载地址:  https://www.python.org/downloads/
    echo   国内镜像目录:  https://mirrors.tuna.tsinghua.edu.cn/python/
    echo.
    echo   安装完成后重新双击本文件 first_run.bat。
    echo.
    pause
    exit /b 1
)

:pick_python
echo.
set "SEL="
set /p "SEL=请选择要使用的 Python 编号 [1-%PN%] (直接回车 = 1): "
for /f "tokens=* delims= " %%x in ("!SEL!") do set "SEL=%%x"
if "!SEL!"=="" set "SEL=1"
set "PY="
set "PV="
set /a IX=0
for /f "usebackq tokens=1,* delims=|" %%a in ("%PYLIST%") do (
    set /a IX+=1
    if "!IX!"=="!SEL!" (
        set "PV=%%a"
        set "PY=%%b"
    )
)
if not defined PY (
    echo   编号无效，请重新输入。
    goto pick_python
)
echo.
echo   已选择: Python !PV!
echo   路径  : !PY!
"%PY%" -V
if errorlevel 1 (
    echo   [错误] 该 Python 无法运行，请换一个编号重试。
    goto pick_python
)
if exist "%PYLIST%" del /q "%PYLIST%" >nul 2>nul

REM ============================================================
REM [2] 创建虚拟环境
REM ============================================================
echo.
echo [2/3] 准备虚拟环境 venv ...
if exist "venv\Scripts\python.exe" (
    echo   检测到已存在虚拟环境: %CD%\venv
    set "RE="
    set /p "RE=是否删除并重建 [y/N] (回车 = 保留现有): "
    if /i "!RE!"=="y" (
        echo   正在删除旧虚拟环境...
        rmdir /s /q "venv"
    )
)

if not exist "venv\Scripts\python.exe" (
    echo   正在创建虚拟环境...
    "%PY%" -m venv "venv"
    if errorlevel 1 (
        echo.
        echo   [错误] 创建虚拟环境失败。
        echo   可能原因: 该 Python 缺少 venv 模块，或安装目录无写入权限。
        echo   建议: 换一个 Python 版本，或以管理员身份重试。
        pause
        exit /b 1
    )
)
if not exist "venv\Scripts\python.exe" (
    echo   [错误] 未找到 venv\Scripts\python.exe。
    pause
    exit /b 1
)
set "VPY=%CD%\venv\Scripts\python.exe"
echo   虚拟环境就绪:
"%VPY%" -V

REM ============================================================
REM [3] 选择安装源并安装依赖
REM ============================================================
echo.
echo [3/3] 选择 Python 包安装源
echo.
echo    [1] 清华大学 TUNA   https://pypi.tuna.tsinghua.edu.cn/simple
echo    [2] 阿里云          https://mirrors.aliyun.com/pypi/simple/
echo    [3] 中科大 USTC     https://mirrors.ustc.edu.cn/pypi/simple
echo    [4] 官方 PyPI       https://pypi.org/simple
echo    [5] 自定义地址
echo.

:pick_mirror
set "MC="
set "INDEX="
set /p "MC=请选择安装源 [1-5] (直接回车 = 清华源): "
if "!MC!"=="" set "MC=1"
if "!MC!"=="1" set "INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
if "!MC!"=="2" set "INDEX=https://mirrors.aliyun.com/pypi/simple/"
if "!MC!"=="3" set "INDEX=https://mirrors.ustc.edu.cn/pypi/simple"
if "!MC!"=="4" set "INDEX=https://pypi.org/simple"
if "!MC!"=="5" set /p "INDEX=请输入安装源地址: "
if not defined INDEX (
    echo   输入无效，请重新选择。
    goto pick_mirror
)
echo.
echo   使用安装源: !INDEX!
echo.

echo   正在升级 pip ...
"%VPY%" -m pip install --upgrade pip -i "!INDEX!" --timeout 60 --disable-pip-version-check
if errorlevel 1 echo   [提示] pip 升级失败(可忽略)，继续安装依赖...

if not exist "requirements.txt" (
    echo   [错误] 未找到 requirements.txt，无法安装依赖。
    pause
    exit /b 1
)

echo.
echo   正在安装项目依赖 (PySide6 / matplotlib / numpy / openpyxl)...
echo   首次安装需要几分钟，请耐心等待...
echo.
"%VPY%" -m pip install -r "requirements.txt" -i "!INDEX!" --timeout 60 --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo   [错误] 依赖安装失败。
    echo   建议: 换一个安装源重试【重新运行本文件】，或检查网络与代理设置。
    pause
    exit /b 1
)

> "venv\pip.ini" echo [global]
>> "venv\pip.ini" echo index-url = !INDEX!
>> "venv\pip.ini" echo timeout = 60
>> "venv\pip.ini" echo disable-pip-version-check = true

echo.
echo ============================================================
echo   安装完成
echo.
echo   启动软件:
echo       venv\Scripts\python.exe main.py
echo   也可以直接双击 run.bat 启动。
echo.
echo   安装源已记录到 venv\pip.ini，后续该虚拟环境的 pip
echo   默认使用: !INDEX!
echo ============================================================
echo.
pause
endlocal
exit /b 0
