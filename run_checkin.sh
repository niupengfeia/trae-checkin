#!/bin/bash
# TraeCode 自动签到 Shell 包装脚本
# 用法: ./run_checkin.sh
# 建议: 将此脚本加入 crontab 实现每日自动签到

# 配置 refresh_token（建议通过环境变量传入）
# export TRAE_REFRESH_TOKEN="your_refresh_token_here"

# 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 日志文件
LOG_FILE="$SCRIPT_DIR/checkin.log"

# 执行签到
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始签到..." >> "$LOG_FILE"
python3 trae_checkin.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 签到完成 ✓" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 签到失败 (exit code: $EXIT_CODE)" >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
exit $EXIT_CODE
