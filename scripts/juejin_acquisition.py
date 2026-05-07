#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
掘金评论区获客脚本（v2.0）
功能：搜索文章 → AI四维评分筛选 → LLM生成评论 → 自动评论/私信

升级内容（参考知乎获客技能 v1.0）：
  - AI动态生成评论/私信（替换固定话术模板）
  - AI四维评分筛选（热度40 + 互动30 + 时效20 + 质量10）
  - 精细反爬策略（时段/日上限/小时上限/随机延迟）
  - 评论/私信历史持久化（去重保护）
  - LLM动态生成搜索关键词 + 种子池降级
"""

import sys
import os
import json
import re
import argparse
import urllib.request
import urllib.error
import time
import random
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# ─── 模块路径 ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)

# 尝试导入共享 LLM 模块
_LLM_MODULE = None
# 优先从 zhihu-campaign 共享模块导入
_LLM_SEARCH_PATHS = [
    os.path.join(SCRIPT_DIR, "zhihu_llm.py"),
    
    
    
]
_LLM_MODULE_PATH = None
for p in _LLM_SEARCH_PATHS:
    if os.path.exists(p):
        _LLM_MODULE_PATH = p
        break
if _LLM_MODULE_PATH and os.path.exists(_LLM_MODULE_PATH):
    import importlib.util
    spec = importlib.util.spec_from_file_location("zhihu_llm", _LLM_MODULE_PATH)
    _LLM_MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_LLM_MODULE)
    call_llm = _LLM_MODULE.call_llm
    call_llm_json = _LLM_MODULE.call_llm_json
    get_api_key = _LLM_MODULE.get_api_key
else:
    # 降级：使用本地固定话术
    call_llm = None
    call_llm_json = None
    get_api_key = None

# ─── 路径配置 ─────────────────────────────────────────────
CONFIG_FILE = os.path.join(SKILL_ROOT, "juejin.env")
ACQUISITION_CONFIG = os.path.join(SKILL_ROOT, "juejin_acquisition_config.json")
DATA_DIR = os.path.join(SKILL_ROOT, "data")
COMMENTED_FILE = os.path.join(DATA_DIR, "commented-history.json")
MESSAGED_FILE = os.path.join(DATA_DIR, "messaged-history.json")
COMMENT_TEMPLATE_FILE = os.path.join(SKILL_ROOT, "templates", "comment-strategic.md")
KEYWORD_TEMPLATE_FILE = os.path.join(SKILL_ROOT, "templates", "keyword-generation.md")

# 掘金 API 基础 URL
API_BASE = "https://juejin.cn"

# 确保 data 目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# ─── 日志配置 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(SKILL_ROOT, "juejin_acquisition.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class Article:
    """掘金文章数据结构"""
    article_id: str
    title: str
    brief_content: str = ""
    view_count: int = 0
    comment_count: int = 0
    digg_count: int = 0
    collect_count: int = 0
    ctime: int = 0
    author_id: str = ""
    author_name: str = ""
    url: str = ""
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "brief_content": self.brief_content[:200] if self.brief_content else "",
            "view_count": self.view_count,
            "comment_count": self.comment_count,
            "digg_count": self.digg_count,
            "collect_count": self.collect_count,
            "ctime": self.ctime,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "url": self.url,
            "score": self.score,
        }


@dataclass
class CommentRecord:
    """评论记录"""
    article_id: str
    title: str
    author_id: str
    author_name: str
    comment: str
    timestamp: str
    keyword: str = ""


@dataclass
class MessageRecord:
    """私信记录"""
    user_id: str
    user_name: str
    message: str
    timestamp: str
    article_id: str = ""
    keyword: str = ""


# ═══════════════════════════════════════════════════════════
#  配置加载
# ═══════════════════════════════════════════════════════════

def load_env(cli_cookie: Optional[str] = None) -> dict:
    """加载掘金配置"""
    config = {}

    # 从 juejin.env 文件加载
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                line = line.strip()
                if line.startswith("export"):
                    line = line[6:].strip()
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                config[key.strip()] = val

    # 环境变量覆盖
    for env_key in ("JUEJIN_COOKIE",):
        env_val = os.environ.get(env_key, "")
        if env_val:
            config[env_key] = env_val

    # 命令行参数覆盖
    if cli_cookie:
        config["JUEJIN_COOKIE"] = cli_cookie

    cookie = config.get("JUEJIN_COOKIE", "").strip()
    if not cookie or "your_session_id" in cookie:
        logger.error("未找到有效的掘金 Cookie")
        raise ValueError("JUEJIN_COOKIE 未配置，请检查 juejin.env 文件")

    return config


def load_json_config(path: str, default: dict) -> dict:
    """加载 JSON 配置文件"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载配置失败 {path}: {e}")
    return default


def load_acquisition_config() -> dict:
    """加载获客配置"""
    default = {
        "keywords": ["OpenClaw", "AI大模型", "Token", "DeepSeek", "阿里云百炼"],
        "scoring": {
            "view_weight": 40,
            "interaction_weight": 30,
            "timeliness_weight": 20,
            "quality_weight": 10,
        },
        "filters": {
            "min_view_count": 0,
            "min_comment_count": 0,
            "max_days_old": 365,
            "top_n": 10,
        },
        "anti_crawl": {
            "work_hours": {"start": 8, "end": 23},
            "daily": {"max_comments": 20, "max_messages": 10},
            "hourly": {"max_comments": 5, "max_messages": 3},
            "delays": {
                "between_comments": {"min": 30, "max": 90},
                "between_messages": {"min": 60, "max": 120},
                "between_searches": {"min": 3, "max": 8},
                "between_keywords": {"min": 5, "max": 15},
            },
            "retry": {"max_attempts": 3, "base_delay": 20},
        },
        "comment_templates": [],
        "message_templates": [],
    }
    user_config = load_json_config(ACQUISITION_CONFIG, default)
    # 深度合并
    for key in default:
        if key not in user_config:
            user_config[key] = default[key]
        elif isinstance(default[key], dict) and isinstance(user_config[key], dict):
            for subkey in default[key]:
                if subkey not in user_config[key]:
                    user_config[key][subkey] = default[key][subkey]
    return user_config


def load_history(path: str) -> list:
    """加载历史记录"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []
    return []


def save_history(path: str, records: list):
    """保存历史记录"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"保存历史记录失败: {e}")


# ═══════════════════════════════════════════════════════════
#  HTTP 请求封装（掘金 API）
# ═══════════════════════════════════════════════════════════

def api_request(path: str, data: dict = None, cookie: str = None, method: str = "POST") -> dict:
    """发送 HTTP 请求到掘金 API"""
    # 通过 juejin.cn 代理访问（api.juejin.cn 会返回空响应）
    url = f"{API_BASE}{path}"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://juejin.cn/",
        "Origin": "https://juejin.cn",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    if data is None:
        data = {}

    payload = json.dumps(data).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"HTTP {e.code}: {body[:200]}")
        return {"err_no": e.code, "err_msg": body[:200]}
    except Exception as e:
        logger.error(f"请求失败: {e}")
        return {"err_no": -1, "err_msg": str(e)}


# ═══════════════════════════════════════════════════════════
#  反爬策略（参考知乎获客）
# ═══════════════════════════════════════════════════════════

def is_work_hours(ac_config: dict) -> bool:
    """检查当前是否在工作时段内"""
    now = datetime.now()
    anti_crawl = ac_config.get("anti_crawl", {})
    work_hours = anti_crawl.get("work_hours", {"start": 8, "end": 23})
    start = work_hours.get("start", 8)
    end = work_hours.get("end", 23)

    if start <= now.hour < end:
        return True
    logger.warning(f"当前时间 {now.hour}:00 不在工作时段 ({start}:00-{end}:00)，跳过")
    return False


def wait_random(min_sec: float = 5, max_sec: float = 15, reason: str = "操作间隔"):
    """随机等待"""
    delay = random.uniform(min_sec, max_sec)
    logger.info(f"⏳ {reason}，等待 {int(delay)}s...")
    time.sleep(delay)


def check_rate_limits(history: list, today_key: str, daily_max: int, hourly_max: int) -> Tuple[bool, str]:
    """检查每日/每小时速率限制"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    this_hour_str = now.strftime("%Y-%m-%d %H:00")

    today_count = sum(1 for r in history if r.get("timestamp", "").startswith(today_str))
    hour_count = sum(1 for r in history if r.get("timestamp", "").startswith(this_hour_str))

    if today_count >= daily_max:
        return False, f"今日 {today_key} {today_count}/{daily_max}，已达上限"
    if hour_count >= hourly_max:
        return False, f"本小时 {today_key} {hour_count}/{hourly_max}，已达上限"

    return True, f"余量 {today_key}: 今日 {daily_max - today_count}，本小时 {hourly_max - hour_count}"


# ═══════════════════════════════════════════════════════════
#  AI 内容生成（参考知乎获客）
# ═══════════════════════════════════════════════════════════

def generate_keywords(product_url: str = "", seed_keywords: list = None) -> list:
    """
    LLM 生成搜索关键词，种子池降级
    Returns:
        list of keywords
    """
    if call_llm_json is None:
        logger.warning("LLM 模块不可用，使用种子池关键词")
        return (seed_keywords or [])[:6]

    try:
        prompt = f"""根据以下产品信息，生成6个掘金搜索关键词。
关键词需要覆盖：用户痛点、技术领域、竞品对比、使用场景、行业趋势。

产品信息：{product_url or "AI API 聚合/中转服务，接入多家大模型"}

要求：
- 每个关键词简洁（2-8字），贴合掘金开发者用户群
- 覆盖不同搜索意图（技术选型、成本对比、实践案例）
- 避免重复和过于宽泛

返回 JSON 格式：
{{"keywords": ["关键词1", "关键词2", ...], "reasoning": "选择说明"}}"""

        result = call_llm_json(
            system_prompt="你是一位掘金内容策略分析师，擅长从产品信息中提炼技术关键词。",
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=1024,
        )

        keywords = result.get("keywords", [])
        if isinstance(keywords, list) and len(keywords) >= 3:
            logger.info(f"✓ LLM 生成 {len(keywords)} 个关键词")
            return keywords[:10]

        logger.warning("LLM 返回关键词不足，使用种子池")
    except Exception as e:
        logger.warning(f"LLM 生成关键词失败: {e}，使用种子池")

    return (seed_keywords or [])[:6]


def generate_comment(article: Article, product_url: str = "") -> str:
    """
    LLM 生成自然评论（参考知乎获客的 comment-strategic.md）
    Returns:
        str: 评论内容
    """
    if call_llm is None:
        # 降级：返回简单评论
        return generate_fallback_comment(article)

    try:
        system_prompt = (
            "你是一位掘金资深用户，也是该领域的从业者。"
            "擅长用「圈内人」的身份自然参与讨论。"
            "回复风格：口语化、有具体细节、看起来像是真实用户有感而发。"
            "产品链接要自然融入正文中间，像分享经历附带链接，不要单独放末尾。"
        )

        # 随机选择评论类型
        comment_type = random.choice(["赞同补充", "提问讨论", "实战分享", "案例分析"])

        user_prompt = f"""
你正在阅读一篇掘金文章，打算发表一条自然评论。

## 文章信息
标题：{article.title}
摘要：{article.brief_content[:200] if article.brief_content else ""}

## 要求的评论类型：{comment_type}

## 产品链接（必须自然融入正文，像分享经验附带链接）
- 名称：{product_url}

## 评论要求
- 字数：60-150字
- 口语化，带语气词（"说实话"、"有一说一"、"学到了"）
- 与文章内容高度相关
- 产品链接放在正文中间，如"我之前用过XX(链接)，感觉…"
- 不要单独一行放链接
- 禁用：广告腔、排比句

## 输出
直接返回评论文本。"""

        comment = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,
            max_tokens=300,
        ).strip()

        # 限制长度
        if len(comment) > 200:
            comment = comment[:197] + "..."

        logger.info(f"✓ LLM 生成评论 ({comment_type}): {comment[:60]}...")
        return comment

    except Exception as e:
        logger.warning(f"LLM 生成评论失败: {e}，使用兜底评论")
        return generate_fallback_comment(article)


def generate_message(article: Article, product_url: str = "") -> str:
    """
    LLM 生成自然私信
    Returns:
        str: 私信内容
    """
    if call_llm is None:
        return generate_fallback_message(article)

    try:
        system_prompt = (
            "你是一位技术从业者，想在掘金上结识同行交流经验。"
            "私信内容看起来真诚、有内容，不是群发的营销消息。"
        )

        user_prompt = f"""
你读完一位掘金作者的文章后，想给他发私信交流。

## 对方文章信息
标题：{article.title}
作者：{article.author_name}

## 私信要求
- 字数：80-200字
- 表明认真读过对方文章（提到1-2个具体观点）
- 分享自己相关的实践经验或困惑
- 自然地引出交流邀请（不是硬要微信）
- 语气真诚、同行间切磋的感觉

## 输出
直接返回私信文本，不要任何标记。"""

        message = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,
            max_tokens=300,
        ).strip()

        if len(message) > 300:
            message = message[:297] + "..."

        logger.info(f"✓ LLM 生成私信: {message[:60]}...")
        return message

    except Exception as e:
        logger.warning(f"LLM 生成私信失败: {e}，使用兜底私信")
        return generate_fallback_message(article)


def generate_fallback_comment(article: Article) -> str:
    """兜底评论（LLM 不可用时使用）"""
    templates = [
        "感谢分享，{topic}这块确实值得深入探讨。最近也在研究相关方向，收获很大。",
        "文章写得不错，{topic}是当前的热门方向，我们团队也在做相关实践。",
        "干货满满！{topic}确实是开发者关注的焦点，期待更多深度内容。",
        "分析得很到位，{topic}这块的实践经验很宝贵。",
        "学到了，{topic}的思路很清晰，正好最近在调研这个方向。",
    ]
    topic = article.title[:10] if len(article.title) > 10 else article.title
    return random.choice(templates).format(topic=topic or "这个话题")


def generate_fallback_message(article: Article) -> str:
    """兜底私信（LLM 不可用时使用）"""
    templates = [
        "你好！读了你的文章《{title}》，收获很大。特别是文中提到的观点很有启发。"
        "我们团队也在做相关方向，想和你交流一下，方便吗？",
        "你好！关注了你的文章《{title}》，感觉方向很契合。我们也在做类似实践，"
        "有机会可以互相交流学习。",
        "您好！拜读了你的《{title}》，分析得很透彻。这块我们有些实践经验，"
        "希望能和你深入交流一下。",
    ]
    title = article.title[:20]
    return random.choice(templates).format(title=title or "相关文章")


# ═══════════════════════════════════════════════════════════
#  AI 四维评分（参考知乎获客）
# ═══════════════════════════════════════════════════════════

def score_article(article: Article, config: dict) -> float:
    """
    AI 四维评分
    Returns:
        0-100 总分
    """
    now = datetime.now()
    ac_config = config.get("anti_crawl", {})
    scoring = config.get("scoring", {})

    view_weight = scoring.get("view_weight", 40)
    interaction_weight = scoring.get("interaction_weight", 30)
    timeliness_weight = scoring.get("timeliness_weight", 20)
    quality_weight = scoring.get("quality_weight", 10)

    # 1. 热度分 (view_weight)
    view_count = article.view_count or 0
    heat_score = min(view_count / 1000 * view_weight, view_weight) if view_weight > 0 else 0

    # 2. 互动分 (interaction_weight)
    digg_count = article.digg_count or 0
    comment_count = article.comment_count or 0
    interaction_score = min((digg_count + comment_count * 3) / 50 * interaction_weight / 30, interaction_weight) if interaction_weight > 0 else 0

    # 3. 时效分 (timeliness_weight)
    days_old = 0
    if article.ctime:
        try:
            ts = int(article.ctime)
            days_old = (now - datetime.fromtimestamp(ts)).days
        except (ValueError, TypeError, OSError):
            days_old = 0
    timeliness_score = max(0, timeliness_weight - max(0, days_old - 7) * timeliness_weight / 180) if timeliness_weight > 0 else 0

    # 4. 质量分 (quality_weight)
    content_len = len(article.brief_content or "")
    quality_score = min(content_len / 100 * quality_weight / 10, quality_weight) if quality_weight > 0 else 0

    total = heat_score + interaction_score + timeliness_score + quality_score
    return total


# ═══════════════════════════════════════════════════════════
#  模块1：搜索 + AI 评分
# ═══════════════════════════════════════════════════════════

class ArticleSearcher:
    """文章搜索 + AI 评分筛选"""

    def __init__(self, cookie: str, config: dict):
        self.cookie = cookie
        self.config = config

    def search(self, keyword: str, limit: int = 20) -> List[Article]:
        """搜索文章"""
        logger.info(f"⎿ 搜索: \"{keyword}\" (limit={limit})")

        path = "/search_api/v1/search"
        data = {
            "key_word": keyword,
            "cursor": "0",
            "limit": limit,
            "search_type": 0,
            "sort_type": 0,
        }

        resp = api_request(path, data, self.cookie)

        if resp.get("err_no") != 0:
            logger.error(f"搜索失败: {resp.get('err_msg', '未知错误')}")
            return []

        articles = []
        data_list = resp.get("data", [])

        for item in data_list:
            article_info = item.get("result_model", {}).get("article_info", {})
            author_info = item.get("result_model", {}).get("author_user_info", {})

            if not article_info:
                continue

            article_id = article_info.get("article_id", "")
            article = Article(
                article_id=article_id,
                title=article_info.get("title", ""),
                brief_content=article_info.get("brief_content", ""),
                view_count=article_info.get("view_count", 0),
                comment_count=article_info.get("comment_count", 0),
                digg_count=article_info.get("digg_count", 0),
                collect_count=article_info.get("collect_count", 0),
                ctime=article_info.get("ctime", 0),
                author_id=author_info.get("user_id"),
                author_name=author_info.get("user_name", ""),
                url=f"https://juejin.cn/post/{article_id}" if article_id else "",
            )
            articles.append(article)

        logger.info(f"✓ 搜索到 {len(articles)} 篇文章")
        return articles

    def score_and_filter(self, articles: List[Article]) -> List[Article]:
        """AI 四维评分 + 筛选 Top N"""
        filters = self.config.get("filters", {})
        top_n = filters.get("top_n", 10)
        max_days_old = filters.get("max_days_old", 365)
        min_view_count = filters.get("min_view_count", 0)
        min_comment_count = filters.get("min_comment_count", 0)

        now = datetime.now()

        scored = []
        for article in articles:
            # 基本过滤
            if min_view_count > 0 and (article.view_count or 0) < min_view_count:
                continue
            if min_comment_count > 0 and (article.comment_count or 0) < min_comment_count:
                continue

            days_old = 0
            if article.ctime:
                try:
                    ts = int(article.ctime)
                    days_old = (now - datetime.fromtimestamp(ts)).days
                except (ValueError, TypeError, OSError):
                    days_old = 0
            if days_old > max_days_old:
                continue

            # AI 评分
            article.score = score_article(article, self.config)
            scored.append(article)

        # 按分数降序排列
        scored.sort(key=lambda a: a.score, reverse=True)

        top = scored[:top_n]

        logger.info(f"✓ 评分筛选完成: {len(articles)} 篇 → Top {len(top)} 篇")
        for i, a in enumerate(top[:5], 1):
            logger.info(f"  [{i}] {a.title[:40]:<42} score={a.score:.1f} views={a.view_count}")
        if len(top) > 5:
            logger.info(f"  ... 还有 {len(top) - 5} 篇")

        return top

    def display_articles(self, articles: List[Article]):
        """展示文章列表"""
        print("\n" + "=" * 100)
        print(f"{'序号':<6}{'标题':<50}{'分数':<8}{'阅读':<8}{'评论':<6}{'作者':<12}")
        print("=" * 100)

        for i, a in enumerate(articles[:20], 1):
            title = (a.title[:45] + "..") if len(a.title) > 45 else a.title
            print(f"{i:<6}{title:<50}{a.score:<8.1f}{a.view_count:<8}{a.comment_count:<6}{a.author_name[:10]:<12}")

        print("=" * 100)


# ═══════════════════════════════════════════════════════════
#  模块2：AI 评论
# ═══════════════════════════════════════════════════════════

class ArticleCommenter:
    """AI 驱动的文章评论器"""

    def __init__(self, cookie: str, config: dict, product_url: str = ""):
        self.cookie = cookie
        self.config = config
        self.product_url = product_url
        self.history = self._load_history()
        self.dry_run = False

    def _load_history(self) -> list:
        return load_history(COMMENTED_FILE)

    def _save_history(self):
        save_history(COMMENTED_FILE, self.history)

    def _is_commented(self, article_id: str, author_id: str) -> Tuple[bool, str]:
        """检查是否已评论（URL和作者双重去重）"""
        for record in self.history:
            if record.get("article_id") == article_id:
                return True, "URL 已评论"
            if record.get("author_id") and record.get("author_id") == author_id:
                # 同一作者只评论1篇
                return True, f"作者 {record.get('author_name', '')} 已评论过"
        return False, ""

    def comment(self, article: Article, keyword: str = "") -> Tuple[bool, str]:
        """对文章发表 AI 评论"""
        # Dry-run 模式跳过实际发表
        if self.dry_run:
            logger.info(f"[DRY-RUN] 模拟评论: {article.title[:40]}...")
            return True, "dry-run"

        # 去重检查
        is_dup, reason = self._is_commented(article.article_id, article.author_id)
        if is_dup:
            logger.info(f"    跳过（{reason}）: {article.title[:40]}...")
            return False, f"skip: {reason}"

        # 反爬检查
        anti_crawl = self.config.get("anti_crawl", {})
        daily_max = anti_crawl.get("daily", {}).get("max_comments", 20)
        hourly_max = anti_crawl.get("hourly", {}).get("max_comments", 5)
        ok, msg = check_rate_limits(self.history, "评论", daily_max, hourly_max)
        if not ok:
            logger.warning(f"    {msg}")
            return False, f"rate_limit: {msg}"

        # LLM 生成评论
        comment_text = generate_comment(article, self.product_url)

        # 实际评论
        logger.info(f"⎿ 发表评论: {article.title[:40]}...")
        logger.debug(f"   评论内容: {comment_text[:100]}...")

        path = "/interact_api/v1/comment/publish"
        data = {
            "item_id": article.article_id,
            "item_type": 2,
            "comment_content": comment_text,
        }

        resp = api_request(path, data, self.cookie)

        if resp.get("err_no") != 0:
            err_msg = resp.get("err_msg", "未知错误")
            logger.error(f"❌ 评论失败: {err_msg}")
            return False, f"api_error: {err_msg}"

        # 记录成功
        record = CommentRecord(
            article_id=article.article_id,
            title=article.title,
            author_id=article.author_id or "",
            author_name=article.author_name,
            comment=comment_text[:200],
            timestamp=datetime.now().isoformat(),
            keyword=keyword,
        )
        self.history.append(record.__dict__)
        self._save_history()

        logger.info(f"✓ 评论成功: {article.title[:40]}...")
        return True, "success"


# ═══════════════════════════════════════════════════════════
#  模块3：AI 私信
# ═══════════════════════════════════════════════════════════

class UserMessenger:
    """AI 驱动的用户私信器"""

    def __init__(self, cookie: str, config: dict, product_url: str = ""):
        self.cookie = cookie
        self.config = config
        self.product_url = product_url
        self.history = self._load_history()
        self.dry_run = False

    def _load_history(self) -> list:
        return load_history(MESSAGED_FILE)

    def _save_history(self):
        save_history(MESSAGED_FILE, self.history)

    def _is_messaged(self, user_id: str) -> bool:
        for record in self.history:
            if record.get("user_id") == user_id:
                return True
        return False

    def send_message(self, article: Article, keyword: str = "") -> Tuple[bool, str]:
        """给文章作者发送 AI 私信"""
        # Dry-run 模式跳过
        if self.dry_run:
            logger.info(f"[DRY-RUN] 模拟私信: {article.author_name}...")
            return True, "dry-run"

        user_id = article.author_id
        if not user_id:
            return False, "no_author_id"

        # 去重
        if self._is_messaged(user_id):
            logger.info(f"    跳过（已私信过该作者）: {article.author_name}")
            return False, "skip: already messaged"

        # 反爬检查
        anti_crawl = self.config.get("anti_crawl", {})
        daily_max = anti_crawl.get("daily", {}).get("max_messages", 10)
        hourly_max = anti_crawl.get("hourly", {}).get("max_messages", 3)
        ok, msg = check_rate_limits(self.history, "私信", daily_max, hourly_max)
        if not ok:
            logger.warning(f"    {msg}")
            return False, f"rate_limit: {msg}"

        # LLM 生成私信
        message_text = generate_message(article, self.product_url)

        # 实际发送
        logger.info(f"⎿ 私信用户: {article.author_name} ({user_id[:8]}...)")
        logger.debug(f"   私信内容: {message_text[:100]}...")

        path = "/interact_api/v1/message/send"
        data = {
            "receiver_id": user_id,
            "content": message_text,
        }

        resp = api_request(path, data, self.cookie)

        if resp.get("err_no") != 0:
            err_msg = resp.get("err_msg", "未知错误")
            logger.error(f"❌ 私信失败: {err_msg}")
            return False, f"api_error: {err_msg}"

        # 记录成功
        record = MessageRecord(
            user_id=user_id,
            user_name=article.author_name,
            message=message_text[:200],
            timestamp=datetime.now().isoformat(),
            article_id=article.article_id,
            keyword=keyword,
        )
        self.history.append(record.__dict__)
        self._save_history()

        logger.info(f"✓ 私信成功: {article.author_name}")
        return True, "success"


# ═══════════════════════════════════════════════════════════
#  全自动获客模式
# ═══════════════════════════════════════════════════════════

class AutoAcquisition:
    """全自动获客（参考知乎获客 v1.0 架构）"""

    def __init__(self, cookie: str, config: dict, product_url: str = ""):
        self.cookie = cookie
        self.config = config
        self.product_url = product_url
        self.searcher = ArticleSearcher(cookie, config)
        self.commenter = ArticleCommenter(cookie, config, product_url)
        self.messenger = UserMessenger(cookie, config, product_url)

    def run(self, max_comments: int = 5, max_messages: int = 3, dry_run: bool = False):
        """执行全自动获客流程"""
        self.dry_run = dry_run
        self.commenter.dry_run = dry_run
        self.messenger.dry_run = dry_run
        logger.info("=" * 60)
        logger.info("🎯 掘金评论区获客启动")
        logger.info(f"  产品: {self.product_url or '未指定'}")
        logger.info(f"  模式: {'DRY-RUN' if dry_run else 'LIVE'}")
        logger.info("=" * 60)

        # 时段检查
        if not dry_run and not is_work_hours(self.config):
            return {"success": False, "reason": "not_work_hours"}

        # 获取关键词
        seed_keywords = self.config.get("keywords", [])
        keywords = generate_keywords(self.product_url, seed_keywords)
        # 随机选 3 个
        selected_keywords = random.sample(keywords, min(3, len(keywords)))
        logger.info(f"✓ 选定关键词: {selected_keywords}")

        comments_posted = 0
        messages_sent = 0
        all_articles_found = 0
        debug_info = []

        # 遍历关键词
        for kw in selected_keywords:
            if comments_posted >= max_comments and messages_sent >= max_messages:
                break

            # 搜索
            ac_config = self.config.get("anti_crawl", {})
            articles = self.searcher.search(kw, limit=20)
            all_articles_found += len(articles)

            if not articles:
                continue

            # AI 评分筛选 Top N
            top_articles = self.searcher.score_and_filter(articles)

            for article in top_articles:
                if comments_posted >= max_comments and messages_sent >= max_messages:
                    break

                # AI 评论
                if comments_posted < max_comments:
                    success, msg = self.commenter.comment(article, kw)
                    if success:
                        comments_posted += 1
                        debug_info.append({
                            "action": "comment",
                            "keyword": kw,
                            "title": article.title,
                            "author": article.author_name,
                            "score": article.score,
                            "status": "posted",
                        })

                        # 评论间隔
                        delays = ac_config.get("delays", {}).get("between_comments", {"min": 30, "max": 90})
                        wait_random(delays["min"], delays["max"], "评论间隔")
                    else:
                        debug_info.append({
                            "action": "comment",
                            "keyword": kw,
                            "title": article.title,
                            "author": article.author_name,
                            "score": article.score,
                            "status": f"failed: {msg}",
                        })

                # AI 私信
                if messages_sent < max_messages and article.author_id:
                    success, msg = self.messenger.send_message(article, kw)
                    if success:
                        messages_sent += 1
                        debug_info.append({
                            "action": "message",
                            "keyword": kw,
                            "author": article.author_name,
                            "status": "sent",
                        })

                        # 私信间隔
                        delays = ac_config.get("delays", {}).get("between_messages", {"min": 60, "max": 120})
                        wait_random(delays["min"], delays["max"], "私信间隔")

            # 关键词间隔
            delays = ac_config.get("delays", {}).get("between_keywords", {"min": 5, "max": 15})
            wait_random(delays["min"], delays["max"], "切换关键词")

        # 汇总
        logger.info("\n" + "=" * 60)
        logger.info("✅ 执行完成")
        logger.info("=" * 60)
        logger.info(f"  搜索关键词: {len(selected_keywords)} 个")
        logger.info(f"  找到文章:   {all_articles_found} 篇")
        logger.info(f"  评论成功:   {comments_posted} 条")
        logger.info(f"  私信成功:   {messages_sent} 条")
        logger.info(f"  模式:       {'DRY-RUN' if dry_run else 'LIVE'}")

        return {
            "success": True,
            "stats": {
                "keywords_used": len(selected_keywords),
                "articles_found": all_articles_found,
                "comments_posted": comments_posted,
                "messages_sent": messages_sent,
                "dry_run": dry_run,
            },
            "details": debug_info,
        }


# ═══════════════════════════════════════════════════════════
#  命令行接口
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="掘金评论区获客脚本 v2.0 — AI 驱动 | 四维评分 | 反爬保护",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 全自动获客
  python3 juejin_acquisition.py auto --product-url "https://example.com"
  
  # 测试模式
  python3 juejin_acquisition.py auto --product-url "https://example.com" --dry-run

  # 搜索文章
  python3 juejin_acquisition.py search --keyword "AI大模型"
  
  # 评论文章
  python3 juejin_acquisition.py comment --article-id xxx --topic "大模型"
  
  # 私信用户
  python3 juejin_acquisition.py message --user-id xxx
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 搜索命令
    search_parser = subparsers.add_parser("search", help="搜索文章")
    search_parser.add_argument("--keyword", required=True, help="搜索关键词")
    search_parser.add_argument("--limit", type=int, default=20, help="搜索数量限制")
    search_parser.add_argument("--cookie", help="掘金 Cookie")

    # 评论命令
    comment_parser = subparsers.add_parser("comment", help="评论文章")
    comment_parser.add_argument("--article-id", required=True, help="文章ID")
    comment_parser.add_argument("--topic", default="", help="话题关键词")
    comment_parser.add_argument("--cookie", help="掘金 Cookie")

    # 私信命令
    message_parser = subparsers.add_parser("message", help="私信用户")
    message_parser.add_argument("--user-id", required=True, help="用户ID")
    message_parser.add_argument("--topic", default="", help="话题关键词")
    message_parser.add_argument("--cookie", help="掘金 Cookie")

    # 全自动命令
    auto_parser = subparsers.add_parser("auto", help="全自动获客")
    auto_parser.add_argument("--product-url", default="", help="产品链接（用于生成关键词和评论）")
    auto_parser.add_argument("--max-comments", type=int, default=5, help="本次最大评论数")
    auto_parser.add_argument("--max-messages", type=int, default=3, help="本次最大私信数")
    auto_parser.add_argument("--dry-run", action="store_true", help="测试模式")
    auto_parser.add_argument("--cookie", help="掘金 Cookie")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        # 加载配置
        base_config = load_env(cli_cookie=getattr(args, "cookie", None))
        cookie = base_config["JUEJIN_COOKIE"]
        acquisition_config = load_acquisition_config()

        if args.command == "search":
            searcher = ArticleSearcher(cookie, acquisition_config)
            articles = searcher.search(args.keyword, limit=args.limit)
            if articles:
                top = searcher.score_and_filter(articles)
                searcher.display_articles(top)
                # 保存结果
                output_file = os.path.join(SKILL_ROOT, f"search_results_{args.keyword}.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump([a.to_dict() for a in top], f, ensure_ascii=False, indent=2)
                logger.info(f"✓ 结果已保存: {output_file}")

        elif args.command == "comment":
            # 构造一个精简的 Article 对象
            article = Article(
                article_id=args.article_id,
                title=args.topic or "未知文章",
                author_id="",
                author_name="",
            )
            commenter = ArticleCommenter(cookie, acquisition_config)
            success, msg = commenter.comment(article)
            sys.exit(0 if success else 1)

        elif args.command == "message":
            article = Article(
                article_id="",
                title=args.topic or "未知话题",
                author_id=args.user_id,
                author_name="未知用户",
            )
            messenger = UserMessenger(cookie, acquisition_config)
            success, msg = messenger.send_message(article)
            sys.exit(0 if success else 1)

        elif args.command == "auto":
            auto = AutoAcquisition(cookie, acquisition_config, args.product_url)
            result = auto.run(
                max_comments=args.max_comments,
                max_messages=args.max_messages,
                dry_run=args.dry_run,
            )
            sys.exit(0 if result.get("success") else 1)

    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"执行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
