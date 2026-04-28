#!/bin/bash
# 掘金文章数据自动监控脚本（修复版）
# 使用openclaw exec在OpenClaw环境中执行

set -e

# 配置
ARTICLE_ID="7627451787391434788"
SCRIPT_DIR="/Users/jiashaoshan/.openclaw/workspace/skills/juejin-publisher/scripts"
DATE=$(date +"%Y-%m-%d")
TIME=$(date +"%H:%M:%S")

echo "[$DATE $TIME] 开始采集掘金文章数据..."

# 使用openclaw exec在OpenClaw环境中执行
echo "[$DATE $TIME] 正在通过OpenClaw执行更新..."
openclaw exec -- python3 "$SCRIPT_DIR/update_feishu_sheet.py" --article-id "$ARTICLE_ID" --force-write 2>&1 | tee -a /tmp/juejin_monitor.log

if [ $? -eq 0 ]; then
    echo "[$DATE $TIME] 数据已成功更新到飞书表格"
else
    echo "[$DATE $TIME] 飞书表格更新失败"
    exit 1
fi
