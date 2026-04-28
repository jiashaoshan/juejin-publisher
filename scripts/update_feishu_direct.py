#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_feishu_direct.py: 直接调用飞书API更新表格（不依赖OpenClaw环境）

Usage:
  python3 update_feishu_direct.py --article-id 7627451787391434788
"""

import sys
import os
import json
import argparse
import subprocess
import re
import urllib.request
import urllib.error
from datetime import datetime

# 颜色输出
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"

def log_info(msg):  print(f"{GREEN}✅ {msg}{NC}")
def log_warn(msg):  print(f"{YELLOW}⚠️  {msg}{NC}")
def log_error(msg): print(f"{RED}❌ {msg}{NC}")
def log_step(msg):  print(f"{BLUE}➡️  {msg}{NC}")

# 配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUERY_SCRIPT = os.path.join(SCRIPT_DIR, "query_article.py")
FEISHU_SHEET_TOKEN = "K58UsKgZWhJirItLkqhc8p7BnFb"
FEISHU_SHEET_ID = "1060cf"

# 从环境变量获取飞书Token（需要配置）
FEISHU_ACCESS_TOKEN = os.environ.get("FEISHU_ACCESS_TOKEN", "")

def query_juejin_article(article_id):
    """调用 query_article.py 获取掘金文章数据"""
    log_step(f"正在查询掘金文章数据: {article_id}")
    
    try:
        result = subprocess.run(
            [sys.executable, QUERY_SCRIPT, article_id, "--format", "json"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            log_error(f"查询脚本执行失败: {result.stderr}")
            return None
        
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
        json_match = re.search(r'\{[\s\S]*\}', clean_output)
        if not json_match:
            log_error("无法从输出中解析 JSON 数据")
            return None
        
        data = json.loads(json_match.group(0))
        log_info(f"成功获取文章数据: {data.get('title', 'Unknown')}")
        return data
        
    except Exception as e:
        log_error(f"查询异常: {e}")
        return None

def append_to_feishu_sheet(row_data):
    """直接调用飞书API追加数据"""
    if not FEISHU_ACCESS_TOKEN:
        log_error("未配置 FEISHU_ACCESS_TOKEN 环境变量")
        log_error("请执行: export FEISHU_ACCESS_TOKEN=你的token")
        return False
    
    log_step("正在写入飞书表格...")
    
    try:
        url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{FEISHU_SHEET_TOKEN}/values_append"
        
        headers = {
            "Authorization": f"Bearer {FEISHU_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "valueRange": {
                "range": f"{FEISHU_SHEET_ID}!A1:N1",
                "values": [row_data]
            }
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('code') == 0:
                log_info("数据成功写入飞书表格")
                return True
            else:
                log_error(f"写入失败: {result.get('msg', '未知错误')}")
                return False
                
    except Exception as e:
        log_error(f"写入异常: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="直接调用飞书API更新表格")
    parser.add_argument("--article-id", required=True, help="掘金文章ID")
    args = parser.parse_args()
    
    print(f"{BLUE}═══════════════════════════════════════════════════{NC}")
    print(f"{BLUE}  掘金文章数据更新工具（Direct API版）{NC}")
    print(f"{BLUE}═══════════════════════════════════════════════════{NC}")
    print()
    
    # 查询掘金文章数据
    article_data = query_juejin_article(args.article_id)
    if not article_data:
        log_error("获取文章数据失败，退出")
        sys.exit(1)
    
    # 准备写入的数据
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    fetch_time = now.strftime("%H:%M")
    
    row_data = [
        today,
        fetch_time,
        article_data.get("title", ""),
        str(article_data.get("article_id", "")),
        article_data.get("view_count", 0),
        article_data.get("like_count", 0),
        article_data.get("comment_count", 0),
        article_data.get("collect_count", 0),
        0,
        "-",
        "-",
        "-",
        "-",
        "API直接写入"
    ]
    
    print()
    
    # 写入飞书表格
    success = append_to_feishu_sheet(row_data)
    
    if not success:
        log_error("更新失败")
        sys.exit(1)
    
    print()
    print(f"{GREEN}✅ 处理完成！{NC}")
    print(f"\n数据已追加到表格: https://www.feishu.cn/sheets/{FEISHU_SHEET_TOKEN}")

if __name__ == "__main__":
    main()
