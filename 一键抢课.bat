@echo off
chcp 65001 >nul
REM 一键抢课 —— 双击即可运行（Windows 版）
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
  echo [错误] 找不到 uv。
  echo 请先安装：https://docs.astral.sh/uv/getting-started/installation/
  echo.
  echo 按任意键关闭窗口...
  pause >nul
  exit /b 1
)

uv run --locked python grab.py
set CODE=%ERRORLEVEL%

echo.
echo ==================================
echo  脚本结束（退出码 %CODE%）
echo  退出码 0 = 全部拿下；1 = 有课没抢到
echo ==================================
echo.
echo 按任意键关闭窗口...
pause >nul
