@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ============================================================
REM  Trae 账号信息一键采集（Windows 免安装版）
REM  在「已登录目标账号的 Trae/TraeWork 桌面客户端」的电脑上
REM  直接双击运行即可：免安装、免配置。
REM  运行后把窗口输出的 5 个值复制到飞书多维表格
REM  （粘贴到哪一列，见同目录 使用说明.txt）
REM ============================================================

set "PYTHONIOENCODING=utf-8"

if not exist "python\python.exe" (
  echo [错误] 找不到 python\python.exe，请确认已完整下载/解压本目录
  pause
  exit /b 1
)

"python\python.exe" collect_account_info.py

echo.
echo ============ 运行结束，请把上面 5 个值复制到飞书表格 ============
pause
