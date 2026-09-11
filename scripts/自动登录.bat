@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
uv run --locked --extra login python -m fdu_yjsxk.selenium_login --export-courses
set "FDU_EXIT=%ERRORLEVEL%"
echo 登录入口结束，按任意键关闭。
pause >nul
exit /b %FDU_EXIT%
