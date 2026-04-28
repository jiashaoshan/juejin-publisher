#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_feishu_sheet.py: 自动更新掘金文章数据到飞书表格

Usage:
  # 在 OpenClaw 外部运行（仅测试模式）
  python3 update_feishu_sheet.py --article-id 7627451787391434788 --dry-run
  
  # 在 OpenClaw 内部运行（实际写入）
  openclaw tools feishu_sheet --action append ...
  
功能:
  1. 调用 query_article.py 获取掘金文章数据
  2. 将数据追加写入飞书表格"掘金文章数据监控看板"
  3. 自动计算日增数据（与上一条记录对比）

注意:
  - 此脚本设计为在 OpenClaw 环境内执行，使用 feishu_sheet 工具
  - 在 OpenClaw 外部运行时，只能使用 --dry-run 模式测试
"""

import sys
import os
import json
import argparse
import subprocess
import re
from datetime import datetime

# ─── 颜色输出 ────────────────────────────────────────────────
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"

def log_info(msg):  print(f"{GREEN}✅ {msg}{NC}")
def log_warn(msg):  print(f"{YELLOW}⚠️  {msg}{NC}")
def log_error(msg): print(f"{RED}❌ {msg}{NC}")
def log_step(msg):  print(f"{BLUE}➡️  {msg}{NC}")

# ─── 路径配置 ────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
QUERY_SCRIPT = os.path.join(SCRIPT_DIR, "query_article.py")

# 飞书表格配置
FEISHU_SHEET_TOKEN = "K58UsKgZWhJirItLkqhc8p7BnFb"
FEISHU_SHEET_ID = "1060cf"

# 表头定义（用于显示和参考）
HEADERS = [
    "日期", "获取时间", "文章标题", "文章ID", "阅读量", "点赞数", 
    "评论数", "收藏数", "分享数", "日增阅读", "日增点赞", 
    "日增评论", "日增收藏", "备注"
]

# ─── 掘金数据查询 ────────────────────────────────────────────
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


# ─── 飞书表格数据获取 ───────────────────────────────────────
def get_last_record_from_sheet():
    """从飞书表格获取最后一条数据记录"""
    log_step("正在获取表格历史数据...")
    
    # 检查是否在 OpenClaw 环境中
    if not os.environ.get("OPENCLAW_SESSION"):
        log_warn("不在 OpenClaw 环境中，跳过历史数据获取")
        log_warn("如需获取历史数据，请在 OpenClaw 中运行此脚本")
        return None
    
    try:
        # 使用 openclaw 命令行工具读取数据
        cmd = [
            "openclaw", "tools", "feishu_sheet",
            "--action", "read",
            "--spreadsheet_token", FEISHU_SHEET_TOKEN,
            "--range", f"{FEISHU_SHEET_ID}!A:N"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            log_warn(f"读取表格失败: {result.stderr}")
            return None
        
        # 解析输出中的JSON数据
        output = result.stdout
        json_match = re.search(r'\{[\s\S]*\}', output)
        if not json_match:
            log_warn("无法解析表格数据")
            return None
        
        data = json.loads(json_match.group(0))
        values = data.get("values", [])
        
        if len(values) < 2:
            log_warn("表格中没有历史数据")
            return None
        
        # 找到最后一条有效数据（跳过表头和空行）
        last_record = None
        for row in reversed(values[1:]):
            if len(row) >= 7 and row[2] and row[2].strip():
                last_record = {
                    "date": row[0] if len(row) > 0 else "",
                    "fetch_time": row[1] if len(row) > 1 else "",
                    "title": row[2] if len(row) > 2 else "",
                    "article_id": row[3] if len(row) > 3 else "",
                    "view_count": int(row[4]) if len(row) > 4 and row[4] and str(row[4]).isdigit() else 0,
                    "like_count": int(row[5]) if len(row) > 5 and row[5] and str(row[5]).isdigit() else 0,
                    "comment_count": int(row[6]) if len(row) > 6 and row[6] and str(row[6]).isdigit() else 0,
                    "collect_count": int(row[7]) if len(row) > 7 and row[7] and str(row[7]).isdigit() else 0,
                }
                break
        
        if last_record:
            log_info(f"找到历史记录: {last_record['date']} 阅读量={last_record['view_count']}")
        return last_record
        
    except Exception as e:
        log_warn(f"获取历史记录异常: {e}")
        return None


def calculate_daily_increase(current, last):
    """计算日增数据"""
    if not last:
        return {"view_increase": "-", "like_increase": "-", 
                "comment_increase": "-", "collect_increase": "-"}
    
    if str(current.get("article_id")) != str(last.get("article_id")):
        log_warn("文章ID不一致，日增数据标记为'-'")
        return {"view_increase": "-", "like_increase": "-", 
                "comment_increase": "-", "collect_increase": "-"}
    
    return {
        "view_increase": current.get("view_count", 0) - last.get("view_count", 0),
        "like_increase": current.get("like_count", 0) - last.get("like_count", 0),
        "comment_increase": current.get("comment_count", 0) - last.get("comment_count", 0),
        "collect_increase": current.get("collect_count", 0) - last.get("collect_count", 0)
    }


def append_to_feishu_sheet(row_data, dry_run=False, force_write=False):
    """将数据追加到飞书表格"""
    if dry_run:
        log_warn("【测试模式】数据不会实际写入表格")
        print(f"\n将要写入的数据:")
        for i, label in enumerate(HEADERS):
            if i < len(row_data):
                print(f"  {label}: {row_data[i]}")
        return True
    
    # 检查是否在 OpenClaw 环境中（force_write模式下跳过检查）
    if not force_write and not os.environ.get("OPENCLAW_SESSION"):
        log_error("不在 OpenClaw 环境中，无法写入表格")
        log_error("请在 OpenClaw 中运行此脚本，或使用 --dry-run 模式测试")
        return False
    
    log_step("正在写入飞书表格...")
    
    try:
        # 使用 openclaw 命令行工具的 append 功能
        values_json = json.dumps([row_data])
        
        cmd = [
            "openclaw", "tools", "feishu_sheet",
            "--action", "append",
            "--spreadsheet_token", FEISHU_SHEET_TOKEN,
            "--sheet_id", FEISHU_SHEET_ID,
            "--values", values_json
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            log_error(f"写入表格失败: {result.stderr}")
            return False
        
        log_info("数据成功写入飞书表格")
        return True
        
    except Exception as e:
        log_error(f"写入异常: {e}")
        return False


# ─── 主流程 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="自动更新掘金文章数据到飞书表格",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试模式（不写入数据）
  python3 update_feishu_sheet.py --article-id 7627451787391434788 --dry-run
  
  # 实际写入（需在 OpenClaw 环境中运行）
  openclaw exec python3 update_feishu_sheet.py --article-id 7627451787391434788
        """
    )
    parser.add_argument("--article-id", required=True, help="掘金文章ID")
    parser.add_argument("--dry-run", action="store_true", help="测试模式，不实际写入数据")
    parser.add_argument("--force-write", action="store_true", help="强制写入模式，不检测OpenClaw环境")
    args = parser.parse_args()
    
    print(f"{BLUE}═══════════════════════════════════════════════════{NC}")
    print(f"{BLUE}  掘金文章数据更新工具{NC}")
    print(f"{BLUE}═══════════════════════════════════════════════════{NC}")
    print()
        
    # 检查运行环境
    in_openclaw = os.environ.get("OPENCLAW_SESSION") is not None
    if not in_openclaw and not args.dry_run and not args.force_write:
        log_warn("检测到不在 OpenClaw 环境中，自动切换到测试模式")
        args.dry_run = True
    
    # 1. 查询掘金文章数据
    article_data = query_juejin_article(args.article_id)
    if not article_data:
        log_error("获取文章数据失败，退出")
        sys.exit(1)
    
    print()
    
    # 2. 获取历史记录（用于计算日增）
    last_record = get_last_record_from_sheet()
    
    # 3. 计算日增数据
    increase = calculate_daily_increase(article_data, last_record)
    
    # 4. 准备写入的数据
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    fetch_time = now.strftime("%H:%M")  # 获取时间，格式：小时:分钟
    
    row_data = [
        today,                                    # A: 日期
        fetch_time,                               # B: 获取时间
        article_data.get("title", ""),            # C: 文章标题
        str(article_data.get("article_id", "")),  # D: 文章ID
        article_data.get("view_count", 0),        # E: 阅读量
        article_data.get("like_count", 0),        # F: 点赞数
        article_data.get("comment_count", 0),     # G: 评论数
        article_data.get("collect_count", 0),     # H: 收藏数
        0,                                        # I: 分享数（暂无数据）
        increase["view_increase"],                # J: 日增阅读
        increase["like_increase"],                # K: 日增点赞
        increase["comment_increase"],             # L: 日增评论
        increase["collect_increase"],             # M: 日增收藏
        "自动更新"                                # N: 备注
    ]
    
    print()
    
    # 5. 写入飞书表格
    success = append_to_feishu_sheet(row_data, dry_run=args.dry_run, force_write=args.force_write)
    
    if not success and not args.dry_run:
        log_error("更新失败")
        sys.exit(1)
    
    print()
    print(f"{GREEN}✅ 处理完成！{NC}")
    
    if not args.dry_run:
        print(f"\n数据已追加到表格: https://www.feishu.cn/sheets/{FEISHU_SHEET_TOKEN}")


if __name__ == "__main__":
    main()
