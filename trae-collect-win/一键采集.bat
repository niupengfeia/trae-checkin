@echo off
cd /d "%~dp0"

REM ============================================================
REM  Trae 账号信息一键采集并推送（Windows 免安装版）
REM  在已登录目标账号的 Trae/TraeWork 桌面客户端的电脑上，
REM  直接双击运行：自动采集并写回飞书多维表格（按用户ID匹配行）。
REM  首次使用前：把 feishu_config.example.json 复制一份并改名
REM  为 feishu_config.json，填入 4 个参数（详见 使用说明.txt）。
REM  注意：本文件为 GBK 编码，勿用编辑器转存为其他编码。
REM ============================================================

if not exist "python\python.exe" (
  echo [错误] 找不到 python\python.exe，请确认解压完整目录
  pause
  exit /b 1
)

if not exist "feishu_config.json" (
  echo [提示] 未找到 feishu_config.json，本次只显示凭证、不写入飞书表格
  echo        配置方法：复制 feishu_config.example.json 为 feishu_config.json 并填入 4 个参数
  echo.
)

echo 开始采集账号登录信息...
echo.
"python\python.exe" collect_account_info.py

echo.
echo ============ 运行结束，窗口可关闭 ============
pause
