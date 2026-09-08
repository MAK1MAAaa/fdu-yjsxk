@echo off
chcp 65001 >nul
REM 开抢前先跑这个做自检（Windows 版）
REM 检查 Cookie 是否有效、课程代码是否正确，不会提交任何选课请求
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

uv run --locked python grab.py --dry-run

echo.
echo 按任意键关闭窗口...
pause >nul
