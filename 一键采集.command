#!/bin/bash
# Trae 账号信息一键采集并推送（Mac 版）
# 在已登录目标账号的 Trae/TraeWork 桌面客户端的 Mac 上，
# 直接双击运行：自动采集并写回飞书多维表格（按用户ID匹配行）。
# 依赖：系统自带 python3（缺 AES 库时自动走 openssl 兜底，无需 pip 安装任何包）。
# 配置：feishu_config.json（本目录或 trae-collect-win/ 子目录），含密钥请勿外传。
# 备注：若文件从网络/压缩包传来后双击被拦（"未验证的开发者"），
#       终端执行 xattr -d com.apple.quarantine 一键采集.command 后再双击；
#       若提示无执行权限，先执行 chmod +x 一键采集.command。

cd "$(cd "$(dirname "$0")" && pwd)"

PY="python3"
command -v python3 >/dev/null 2>&1 || PY="/usr/bin/python3"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[错误] 未找到 python3，请先在终端运行 xcode-select --install 安装后重试"
  echo ""
  read -p "按回车键关闭窗口..."
  exit 1
fi

if [ ! -f "feishu_config.json" ] && [ ! -f "trae-collect-win/feishu_config.json" ]; then
  echo "[提示] 未找到 feishu_config.json，本次只显示凭证、不写入飞书表格"
  echo "       配置方法：把 feishu_config.example.json 复制为 feishu_config.json 并填入 4 个参数"
  echo ""
fi

echo "开始采集账号登录信息..."
echo ""
"$PY" collect_account_info.py

echo ""
read -p "============ 运行结束，按回车键关闭窗口 ============"
