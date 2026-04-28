#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_juejin.py: 掘金文章搜索工具
用于评论区获客，搜索高价值文章

Usage:
    python3 search_juejin.py --keyword "API中转" --min-views 1000 --min-comments 20
    python3 search_juejin.py --keyword "大模型API" --days 7 --output json
    python3 search_juejin.py --keyword "API被封" --min-views 500 --limit 50

输出格式:
    JSON: [{"title": "...", "url": "...", "view_count": 1000, ...}]
    TABLE: 表格格式打印到控制台
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ─── 颜色输出 ────────────────────────────────────────────────
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def log_info(msg): print(f"{GREEN}✅ {msg}{NC}")
def log_warn(msg): print(f"{YELLOW}⚠️  {msg}{NC}")
def log_error(msg): print(f"{RED}❌ {msg}{NC}")
def log_step(msg): print(f"{BLUE}➡️  {msg}{NC}")
def log_highlight(msg): print(f"{CYAN}{msg}{NC}")


# ─── 路径配置 ────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
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


# ─── 掘金搜索 API ────────────────────────────────────────────
def search_articles(keyword, cookie, cursor="0", limit=20):
    """
    搜索掘金文章
    
    Args:
        keyword: 搜索关键词
        cookie: 掘金 Cookie
        cursor: 分页游标，默认"0"
        limit: 每页数量，默认20
    
    Returns:
        dict: API 响应结果
    """
    # 掘金搜索 API 使用 search_api/v1/search
    data = {
        "key_word": keyword,
        "cursor": cursor,
        "limit": limit,
        "search_type": 0,  # 0=综合搜索，包含文章
        "sort_type": 0,    # 0=综合排序，1=最新，2=最热
    }
    return api_post("/search_api/v1/search", data, cookie)


def extract_article_info(search_result):
    """
    从搜索结果中提取文章信息
    
    Args:
        search_result: 单条搜索结果
    
    Returns:
        dict: 提取的文章信息
    """
    # 掘金搜索结果结构
    result_type = search_result.get("result_type", 0)
    
    # result_type: 1=文章(旧版), 2=文章(新版), 3=用户, 其他类型跳过
    # 目前掘金搜索结果中 result_type=2 表示文章
    if result_type not in [1, 2]:
        return None
    
    # 文章信息在 result_model 中
    result_model = search_result.get("result_model", {})
    article_info = result_model.get("article_info", {})
    author_info = result_model.get("author_user_info", {})
    
    # 提取文章数据
    article_id = article_info.get("article_id", "")
    title = article_info.get("title", "")
    
    # 处理 HTML 标签
    title = title.replace("<em>", "").replace("</em>", "")
    
    # 阅读量、评论数等
    view_count = article_info.get("view_count", 0)
    comment_count = article_info.get("comment_count", 0)
    digg_count = article_info.get("digg_count", 0)  # 点赞数
    collect_count = article_info.get("collect_count", 0)
    
    # 发布时间
    ctime = article_info.get("ctime", 0)  # 创建时间（秒级时间戳）
    mtime = article_info.get("mtime", 0)  # 修改时间
    
    # 作者信息
    author_name = author_info.get("user_name", "")
    author_id = author_info.get("user_id", "")
    
    return {
        "article_id": str(article_id),
        "title": title,
        "url": f"https://juejin.cn/post/{article_id}" if article_id else "",
        "view_count": int(view_count) if view_count else 0,
        "comment_count": int(comment_count) if comment_count else 0,
        "like_count": int(digg_count) if digg_count else 0,
        "collect_count": int(collect_count) if collect_count else 0,
        "publish_time": format_timestamp(ctime),
        "update_time": format_timestamp(mtime),
        "author": author_name,
        "author_id": author_id,
    }


def format_timestamp(timestamp):
    """
    将时间戳格式化为可读字符串
    掘金返回的是秒级时间戳
    """
    if not timestamp:
        return ""
    try:
        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return str(timestamp)


def parse_timestamp(timestamp_str):
    """
    解析时间戳字符串为 datetime 对象
    """
    if not timestamp_str:
        return None
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except:
        return None


# ─── 搜索主流程 ──────────────────────────────────────────────
def search_all_articles(keyword, cookie, max_results=100):
    """
    搜索所有文章（处理分页）
    
    Args:
        keyword: 搜索关键词
        cookie: 掘金 Cookie
        max_results: 最大结果数
    
    Returns:
        list: 文章列表
    """
    all_articles = []
    cursor = "0"
    page = 1
    
    while len(all_articles) < max_results:
        log_step(f"正在搜索第 {page} 页...")
        
        resp = search_articles(keyword, cookie, cursor=cursor, limit=20)
        
        if resp.get("err_no") != 0:
            err_msg = resp.get("err_msg", "未知错误")
            err_no = resp.get("err_no", -1)
            log_error(f"API错误: {err_msg} (code={err_no})")
            break
        
        data = resp.get("data", [])
        if not data:
            log_info("没有更多结果了")
            break
        
        # 提取文章信息
        for item in data:
            article = extract_article_info(item)
            if article and article.get("article_id"):
                all_articles.append(article)
        
        # 检查是否还有更多
        has_more = resp.get("has_more", False)
        if not has_more:
            break
        
        # 更新游标
        cursor = resp.get("cursor", "0")
        if cursor == "0" or not cursor:
            break
        
        page += 1
        
        # 达到最大数量限制
        if len(all_articles) >= max_results:
            break
    
    return all_articles[:max_results]


def filter_articles(articles, min_views=0, min_comments=0, days=None):
    """
    筛选文章
    
    Args:
        articles: 文章列表
        min_views: 最小阅读量
        min_comments: 最小评论数
        days: 最近 N 天内发布的文章
    
    Returns:
        list: 筛选后的文章列表
    """
    filtered = []
    cutoff_date = None
    
    if days:
        cutoff_date = datetime.now() - timedelta(days=days)
    
    for article in articles:
        # 检查阅读量
        if min_views > 0 and article.get("view_count", 0) < min_views:
            continue
        
        # 检查评论数
        if min_comments > 0 and article.get("comment_count", 0) < min_comments:
            continue
        
        # 检查发布时间
        if cutoff_date:
            publish_time = parse_timestamp(article.get("publish_time", ""))
            if publish_time and publish_time < cutoff_date:
                continue
        
        filtered.append(article)
    
    return filtered


def sort_articles(articles, sort_by="view_count"):
    """
    排序文章
    
    Args:
        articles: 文章列表
        sort_by: 排序字段 (view_count, comment_count, like_count, publish_time)
    
    Returns:
        list: 排序后的文章列表
    """
    reverse = True  # 默认降序
    
    if sort_by == "publish_time":
        # 按发布时间排序，最新的在前
        return sorted(articles, key=lambda x: x.get("publish_time", ""), reverse=True)
    
    return sorted(articles, key=lambda x: x.get(sort_by, 0), reverse=reverse)


# ─── 输出格式化 ──────────────────────────────────────────────
def format_output_json(articles):
    """格式化为 JSON 输出"""
    # 简化输出字段
    simplified = []
    for article in articles:
        simplified.append({
            "title": article["title"],
            "url": article["url"],
            "view_count": article["view_count"],
            "comment_count": article["comment_count"],
            "like_count": article["like_count"],
            "publish_time": article["publish_time"],
            "author": article["author"],
        })
    return json.dumps(simplified, ensure_ascii=False, indent=2)


def format_output_table(articles):
    """格式化为表格输出"""
    if not articles:
        print("没有找到符合条件的文章")
        return
    
    # 计算列宽
    title_width = min(50, max(len(a["title"]) for a in articles))
    author_width = min(15, max(len(a["author"]) for a in articles))
    
    # 打印表头
    header = f"{'标题':<{title_width}} | {'作者':<{author_width}} | {'阅读量':>8} | {'评论':>6} | {'点赞':>6} | {'发布时间':<19}"
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    
    # 打印数据行
    for article in articles:
        title = article["title"][:title_width-3] + "..." if len(article["title"]) > title_width else article["title"]
        author = article["author"][:author_width-3] + "..." if len(article["author"]) > author_width else article["author"]
        print(f"{title:<{title_width}} | {author:<{author_width}} | {article['view_count']:>8,} | {article['comment_count']:>6,} | {article['like_count']:>6,} | {article['publish_time']:<19}")
    
    print("=" * len(header))
    print(f"\n共找到 {len(articles)} 篇文章")


def format_output_csv(articles, output_file):
    """导出为 CSV 文件"""
    import csv
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["标题", "链接", "作者", "阅读量", "评论数", "点赞数", "发布时间"])
        
        for article in articles:
            writer.writerow([
                article["title"],
                article["url"],
                article["author"],
                article["view_count"],
                article["comment_count"],
                article["like_count"],
                article["publish_time"],
            ])
    
    log_info(f"已导出到: {output_file}")


# ─── 主流程 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="掘金文章搜索工具 - 用于评论区获客",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 搜索关键词，筛选高价值文章
  python3 search_juejin.py --keyword "API中转" --min-views 1000 --min-comments 20
  
  # 搜索最近7天发布的文章
  python3 search_juejin.py --keyword "大模型API" --days 7
  
  # 输出为JSON格式
  python3 search_juejin.py --keyword "API被封" --output json
  
  # 导出为CSV
  python3 search_juejin.py --keyword "ChatGPT" --output csv --output-file results.csv
  
  # 获取更多结果
  python3 search_juejin.py --keyword "AI" --limit 100 --min-views 500
        """
    )
    
    # 搜索参数
    parser.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    parser.add_argument("--limit", "-l", type=int, default=50, help="最大搜索数量 (默认: 50)")
    
    # 筛选参数
    parser.add_argument("--min-views", type=int, default=0, help="最小阅读量")
    parser.add_argument("--min-comments", type=int, default=0, help="最小评论数")
    parser.add_argument("--days", "-d", type=int, default=None, help="最近 N 天内发布的文章")
    
    # 输出参数
    parser.add_argument("--output", "-o", choices=["json", "table", "csv"], default="table",
                        help="输出格式 (默认: table)")
    parser.add_argument("--output-file", "-f", help="输出文件路径 (CSV 格式时使用)")
    parser.add_argument("--sort-by", choices=["view_count", "comment_count", "like_count", "publish_time"],
                        default="view_count", help="排序字段 (默认: view_count)")
    
    # Cookie 参数
    parser.add_argument("--cookie", help="掘金 Cookie (可选，默认从配置文件读取)")
    
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
    
    # 搜索文章
    log_highlight(f"\n🔍 搜索关键词: {args.keyword}")
    log_step(f"筛选条件: 阅读量>={args.min_views}, 评论数>={args.min_comments}" +
             (f", 最近{args.days}天内" if args.days else ""))
    print()
    
    articles = search_all_articles(args.keyword, cookie, max_results=args.limit)
    
    if not articles:
        log_warn("未找到任何文章")
        sys.exit(0)
    
    log_info(f"共搜索到 {len(articles)} 篇文章")
    print()
    
    # 筛选文章
    filtered = filter_articles(
        articles,
        min_views=args.min_views,
        min_comments=args.min_comments,
        days=args.days
    )
    
    # 排序
    sorted_articles = sort_articles(filtered, sort_by=args.sort_by)
    
    # 输出结果
    if args.output == "json":
        print(format_output_json(sorted_articles))
    elif args.output == "csv":
        output_file = args.output_file or f"juejin_search_{args.keyword.replace(' ', '_')}.csv"
        format_output_csv(sorted_articles, output_file)
    else:
        format_output_table(sorted_articles)
        
        # 同时输出JSON格式到文件（可选）
        if len(sorted_articles) > 0:
            json_file = f"juejin_search_{args.keyword.replace(' ', '_')}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                f.write(format_output_json(sorted_articles))
            log_info(f"结果已保存到: {json_file}")


if __name__ == "__main__":
    main()
