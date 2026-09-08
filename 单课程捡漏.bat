@echo off
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 exit /b 1

where uv >nul 2>&1
if errorlevel 1 (
  echo 找不到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)

uv run --locked python grab.py --single
set "FDU_EXIT=%ERRORLEVEL%"
echo.
echo 单课程捡漏结束（退出码 %FDU_EXIT%）
echo 0 = 成功、已选或未开始就取消；1 = 未选上或发生错误；130 = 手动中止。
echo 请到选课系统的已选课程页核对结果。按任意键关闭...
pause >nul
exit /b %FDU_EXIT%
