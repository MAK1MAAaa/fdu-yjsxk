@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
uv run --locked python -m fdu_yjsxk.catalog_server
pause
