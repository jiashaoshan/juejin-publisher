#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
juejin-query-article: 查询掘金文章互动数据
Usage:
  python3 query_article.py <article_id>

输出格式:
  {
    "article_id": "7627451787391434788",
    "title": "文章标题",
    "view_count": 1000,
    "like_count": 50,
    "comment_count": 20,
    "collect_count": 30,
    "update_time": "2026-04-13 16:00:00"
  }
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error
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
SKILL_ROOT  = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(SKILL_ROOT, "juejin.env")

# 掘金 API 基础 URL
API_BASE = "https://api.juejin.cn"

# ─── 配置加载 ────────────────────────────────────────────────
def load_config():
    """
    加载配置：
      1. 环境变量 JUEJIN_COOKIE
      2. juejin.env 配置文件
    """
    config = {}

    # 优先级 2：从 juejin.env 文件加载
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                line = line.removeprefix("export").strip()
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                config[key.strip()] = val

    # 优先级 1：环境变量覆盖文件配置
    env_cookie = os.environ.get("JUEJIN_COOKIE", "")
    if env_cookie:
        config["JUEJIN_COOKIE"] = env_cookie

    return config

# ─── HTTP 请求封装 ───────────────────────────────────────────
def api_post(path, data, cookie):
    """发送 POST 请求到掘金 API"""
    url = f"{API_BASE}{path}"
    payload = json.dumps(data).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://juejin.cn/",
        "Origin": "https://juejin.cn",
        "Accept": "application/json, text/plain, */*",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"err_no": e.code, "err_msg": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"err_no": -1, "err_msg": str(e)}

# ─── 掘金 API 操作 ───────────────────────────────────────────
def get_article_detail(article_id, cookie):
    """
    获取文章详情
    使用掘金 content_api/v1/article/query_list 接口获取用户文章列表
    然后从中筛选出目标文章
    """
    log_step(f"正在查询文章: {article_id}")
    
    # 掘金文章ID需要转为整数
    try:
        article_id_int = int(article_id)
    except ValueError:
        return {"error": f"无效的文章ID格式: {article_id}", "code": -1}
    
    # 使用 query_list 接口获取文章列表
    # 由于掘金没有单独的查询文章详情接口，我们通过列表查询获取
    data = {
        "cursor": "0",
        "sort_type": 2,  # 按时间排序
        "limit": 100     # 获取足够多的文章
    }
    resp = api_post("/content_api/v1/article/query_list", data, cookie)
    
    if resp.get("err_no") != 0:
        err_msg = resp.get("err_msg", "未知错误")
        err_no = resp.get("err_no", -1)
        return {"error": f"API错误: {err_msg} (code={err_no})", "code": err_no}
    
    # 从列表中查找目标文章
    articles = resp.get("data", [])
    target_article = None
    for article in articles:
        if str(article.get("article_id")) == str(article_id_int):
            target_article = article
            break
    
    if not target_article:
        return {"error": "文章不存在或无权访问", "code": 404}
    
    return {"success": True, "data": target_article}

def extract_article_stats(article_data):
    """
    从文章详情中提取互动数据
    """
    article_info = article_data.get("article_info", {})
    
    # 提取关键数据
    stats = {
        "article_id": str(article_info.get("article_id", "")),
        "title": article_info.get("title", ""),
        "view_count": article_info.get("view_count", 0),
        "like_count": article_info.get("digg_count", 0),  # 掘金用 digg_count 表示点赞
        "comment_count": article_info.get("comment_count", 0),
        "collect_count": article_info.get("collect_count", 0),
        "update_time": format_timestamp(article_info.get("mtime", 0)),
    }
    
    return stats

def format_timestamp(timestamp):
    """
    将时间戳格式化为可读字符串
    掘金返回的是秒级时间戳（可能是字符串）
    """
    if not timestamp:
        return ""
    try:
        # 转换为整数（掘金返回的可能是字符串）
        ts = int(timestamp)
        # 掘金时间戳是秒级的
        if ts < 1e10:
            dt = datetime.fromtimestamp(ts)
        else:
            dt = datetime.fromtimestamp(ts / 1000)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return str(timestamp)

# ─── 主流程 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="查询掘金文章互动数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 query_article.py 7627451787391434788
  python3 query_article.py 7627451787391434788 --format pretty
        """
    )
    parser.add_argument("article_id", help="文章ID（从掘金URL中获取）")
    parser.add_argument("--format", choices=["json", "pretty"], default="json",
                        help="输出格式：json（默认）或 pretty（美化打印）")
    parser.add_argument("--cookie", help="掘金 Cookie（可选，默认从配置文件读取）")
    args = parser.parse_args()

    # 加载配置
    config = load_config()
    cookie = args.cookie or config.get("JUEJIN_COOKIE", "").strip()
    
    if not cookie or cookie in ("请填入你的掘金Cookie", "sessionid=your_session_id_here; ..."):
        log_error("未找到有效的掘金 Cookie，请通过以下方式配置：")
        print()
        print("  方式一：环境变量")
        print("    export JUEJIN_COOKIE='你的Cookie'")
        print()
        print("  方式二：配置文件")
        print(f"    编辑 {CONFIG_FILE}，填入 JUEJIN_COOKIE")
        print()
        print("  如何获取 Cookie：登录 juejin.cn → F12 → Network → 任意请求 → Request Headers → Cookie")
        sys.exit(1)

    # 查询文章
    result = get_article_detail(args.article_id, cookie)
    
    if "error" in result:
        log_error(result["error"])
        sys.exit(1)
    
    # 提取统计数据
    stats = extract_article_stats(result["data"])
    
    # 输出结果
    if args.format == "pretty":
        log_info("查询成功！")
        print()
        print(f"  📄 文章ID:   {stats['article_id']}")
        print(f"  📋 标题:     {stats['title']}")
        print()
        print(f"  👁️  阅读量:   {stats['view_count']:,}")
        print(f"  👍 点赞数:   {stats['like_count']:,}")
        print(f"  💬 评论数:   {stats['comment_count']:,}")
        print(f"  ⭐ 收藏数:   {stats['collect_count']:,}")
        print()
        print(f"  🕒 更新时间: {stats['update_time']}")
    else:
        # JSON格式输出（默认）
        output = {
            "article_id": stats["article_id"],
            "title": stats["title"],
            "view_count": stats["view_count"],
            "like_count": stats["like_count"],
            "comment_count": stats["comment_count"],
            "collect_count": stats["collect_count"],
            "update_time": stats["update_time"],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
