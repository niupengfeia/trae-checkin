@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ============================================================
REM  Trae 账号信息一键采集（Windows 免安装版）
REM  在「已登录目标账号的 Trae/TraeWork 桌面客户端」的电脑上
REM  直接双击本文件运行即可，无需安装 Python 等任何环境
REM  首次使用：右键本文件 - 编辑，替换下方 4 个飞书配置的 TOFILL
REM  （4 个配置分别去哪里获取，见同目录 使用说明.txt）
REM ============================================================

REM ---------- 飞书配置（首次使用请替换这 4 行的 TOFILL） ----------
set "FEISHU_APP_ID=cli_TOFILL"
set "FEISHU_APP_SECRET=TOFILL"
set "FEISHU_BITABLE_APP_TOKEN=TOFILL_app_token"
set "FEISHU_BITABLE_ACCOUNT_TABLE=TOFILL_table_id"

REM ---------- 要采集的账号名称 ----------
REM  与多维表格「账号列表」中的账号名称「完全相等」才会覆盖同名行（区分大小写），
REM  不相等会新建一行。例如表格里是 张增辉的traeCode，这里就必须填一模一样的 张增辉的traeCode
set "ACCOUNT_NAME=账号2"

REM ---------- 以下不用动 ----------
set "PYTHONIOENCODING=utf-8"

if not exist "python\python.exe" (
  echo [错误] 找不到 python\python.exe，请确认已完整下载/解压本目录
  pause
  exit /b 1
)

if "%FEISHU_APP_ID%"=="cli_TOFILL" goto needfill
if "%FEISHU_APP_SECRET%"=="TOFILL" goto needfill
if "%FEISHU_BITABLE_APP_TOKEN%"=="TOFILL_app_token" goto needfill
if "%FEISHU_BITABLE_ACCOUNT_TABLE%"=="TOFILL_table_id" goto needfill
goto run

:needfill
echo.
echo [提示] 飞书配置还没填写（上面 4 行里还有 TOFILL 没替换）
echo   1. 右键本文件 - 编辑（或用记事本打开）
echo   2. 把 4 个 FEISHU_* 配置行的 TOFILL 换成真实值
echo   3. 每项配置去哪里获取，见同目录「使用说明.txt」
echo.
pause
exit /b 1

:run
echo 开始采集账号「%ACCOUNT_NAME%」的登录信息并写入多维表格...
echo.
"python\python.exe" collect_account_info.py --push --name "%ACCOUNT_NAME%"

echo.
echo ============ 运行结束，可关闭本窗口 ============
pause
