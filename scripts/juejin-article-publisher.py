#!/usr/bin/env python3
"""
掘金文章发布模块
功能：
  1. 读取 article-prompt.md 模板
  2. 调用 LLM 根据产品链接生成技术文章
  3. 默认走人工确认流程
  4. 确认后调用 BrowserWing 脚本发布到掘金
  5. 记录发布历史到 data/published-articles.json

架构参考：
  参考 zhihu-article-publisher.py，共用 zhihu_llm.py 模块
  BrowserWing 脚本需要事先录制（掘金编辑器页面）

依赖:
  - zhihu_llm.py (LLM 调用模块)
  - BrowserWing 服务 (http://127.0.0.1:8080)
  - BrowserWing 脚本（掘金文章发布，需录制）
"""

import argparse
import json
import logging
import os
import sys
import time
import random
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import ssl

# ─── 模块路径 ─────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# 导入共享 LLM 模块
_LLM_SEARCH_PATHS = [
    os.path.join(SCRIPT_DIR, "zhihu_llm.py"),
    
    
]
_LLM_MODULE_PATH = None
for p in _LLM_SEARCH_PATHS:
    if os.path.exists(p):
        _LLM_MODULE_PATH = p
        break
if _LLM_MODULE_PATH:
    import importlib.util
    spec = importlib.util.spec_from_file_location("zhihu_llm", _LLM_MODULE_PATH)
    _LLM_MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_LLM_MODULE)
    call_llm_json = _LLM_MODULE.call_llm_json
    call_llm = _LLM_MODULE.call_llm
    get_api_key = _LLM_MODULE.get_api_key
else:
    raise ImportError("zhihu_llm.py 未找到，请确认技能目录结构")

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)
if requests is None:
    logger.error("requests 库未安装，无法使用 BrowserWing 发布。请执行: pip3 install requests")

# ─── 路径定义 ─────────────────────────────────────────────
TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
ARTICLE_PROMPT_FILE = TEMPLATES_DIR / "article-prompt.md"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"

# ─── 掘金配置 ─────────────────────────────────────────────
# 掘金编辑器页面 URL
JUEJIN_EDITOR_URL = "https://juejin.cn/editor/drafts/new"

# BrowserWing 配置
BROWSERWING_URL = os.environ.get("BROWSERWING_EXECUTOR_URL", "http://127.0.0.1:8080")

# BrowserWing 脚本 ID — 需要录制后填写
# 录制步骤：
#   1. 登录掘金 → 打开 https://juejin.cn/editor/drafts/new
#   2. 在标题栏输入 ${标题}
#   3. 在正文区输入 ${正文}
#   4. 上传封面图 ${封面}
#   5. 选择分类和标签
#   6. 点击发布按钮
#   7. 保存脚本
PUBLISH_SCRIPT_ID = os.environ.get("JUEJIN_BW_SCRIPT_ID", "<<待录制>>>")

# Pexels API (与知乎共用)
PEXELS_API_KEY = "ogysj3gEKHiYFCgRdzo7PiDGyvgxRwxPldwkiANpAOvepyHrNa9q71lR"


# ═══════════════════════════════════════════════════════════
#  数据管理
# ═══════════════════════════════════════════════════════════

def ensure_data_dir():
    """确保 data 目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_template() -> str:
    """加载文章生成提示词模板"""
    if not ARTICLE_PROMPT_FILE.exists():
        raise FileNotFoundError(f"模板文件不存在: {ARTICLE_PROMPT_FILE}")
    with open(ARTICLE_PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_published_history() -> List[Dict[str, Any]]:
    """加载已发布文章历史"""
    ensure_data_dir()
    if PUBLISHED_FILE.exists():
        try:
            with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"读取发布历史失败: {e}，使用空记录")
    return []


def save_published_record(record: Dict[str, Any]):
    """保存发布记录"""
    ensure_data_dir()
    history = load_published_history()
    history.append(record)
    with open(PUBLISHED_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    logger.info(f"✓ 发布记录已保存: {PUBLISHED_FILE}")


# ═══════════════════════════════════════════════════════════
#  LLM 生成文章
# ═══════════════════════════════════════════════════════════

def generate_article(product_url: str) -> Dict[str, Any]:
    """
    调用 LLM 生成掘金技术文章

    Args:
        product_url: 产品链接

    Returns:
        dict: {"titles": [...], "recommended_title_index": int, "body": str}
    """
    logger.info(f"⎿ 正在为 {product_url} 生成掘金文章...")

    template = load_template()
    prompt = template.replace("{{product_url}}", product_url)

    system_prompt = (
        "你是一位掘金技术内容专家，擅长将产品信息转化为高互动的掘金技术文章。"
        "风格：技术干货+实战体验，广告感=0。"
        "请严格按照输出格式返回 JSON。"
    )

    try:
        result = call_llm_json(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.8,
            max_tokens=8192,
        )

        # 验证关键字段
        if "body" not in result:
            raise ValueError("LLM 返回缺少 body 字段")
        if "titles" not in result:
            raise ValueError("LLM 返回缺少 titles 字段")

        logger.info(f"✓ 文章生成完成: {result.get('titles', ['未知'])[0][:40]}...")
        return result

    except Exception as e:
        logger.error(f"生成文章失败: {e}")
        raise


# ═══════════════════════════════════════════════════════════
#  草稿管理
# ═══════════════════════════════════════════════════════════

def save_draft(article_data: Dict[str, Any], product_url: str, output_path: Optional[str] = None) -> str:
    """
    将生成的文章保存为草稿文件，供人工确认

    Returns:
        str: 草稿文件路径
    """
    ensure_data_dir()

    if output_path:
        draft_path = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        draft_path = DATA_DIR / f"juejin_draft_{timestamp}.md"

    titles = article_data.get("titles", [])
    recommended_idx = article_data.get("recommended_title_index", 0)
    body = article_data.get("body", "")

    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(f"# 掘金文章草稿\n\n")
        f.write(f"## 产品链接\n{product_url}\n\n")
        f.write(f"## 标题选项\n\n")
        for i, t in enumerate(titles):
            marker = " ← 【推荐】" if i == recommended_idx else ""
            f.write(f"{i+1}. {t}{marker}\n")
        f.write(f"\n## 推荐标题\n{titles[recommended_idx] if titles else '无'}\n\n")
        f.write(f"## 正文\n\n{body}\n\n")
        f.write(f"---\n")
        f.write(f"*草稿生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
        f.write(f"*产品链接: {product_url}*\n")
        f.write(f"*目标平台: 掘金*\n")

    logger.info(f"✓ 草稿已保存: {draft_path}")
    return str(draft_path)


def confirm_publish(draft_path: str, dry_run: bool) -> bool:
    """
    人工确认是否发布文章

    Args:
        draft_path: 草稿文件路径
        dry_run: 测试模式下跳过确认

    Returns:
        bool: 是否确认发布
    """
    if dry_run:
        logger.info("[DRY-RUN] 测试模式，跳过人工确认，直接模拟发布")
        return True

    print("\n" + "=" * 60)
    print("📝 掘金文章草稿已生成")
    print(f"   文件: {draft_path}")
    print("=" * 60)
    print()
    print("请查看草稿内容，确认是否发布到掘金。")
    print()

    while True:
        response = input("确认发布？(y/n): ").strip().lower()
        if response in ("y", "yes", "是"):
            return True
        elif response in ("n", "no", "否"):
            return False
        print("请输入 y 或 n")


# ═══════════════════════════════════════════════════════════
#  封面图片（Pexels）
# ═══════════════════════════════════════════════════════════

def extract_cover_keyword(title: str, body: str) -> str:
    """从文章标题和正文提取Pexels搜索关键词"""
    topic_keywords = [
        ("AI", "AI technology"),
        ("人工智能", "AI technology"),
        ("大模型", "AI model"),
        ("API", "API"),
        ("编程", "coding"),
        ("开发", "developer"),
        ("架构", "architecture"),
        ("前端", "frontend development"),
        ("后端", "backend development"),
        ("开源", "open source"),
    ]
    for cn, en in topic_keywords:
        if cn.lower() in title.lower() or cn.lower() in body[:500].lower():
            return en
    return "technology"


def fetch_cover_image(keyword: str, platform: str = "juejin") -> Optional[str]:
    """
    从Pexels获取封面图片，下载到本地

    Returns:
        本地图片路径或None
    """
    try:
        search_url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(keyword)}&per_page=5&size=large&orientation=landscape"
        headers = {"Authorization": PEXELS_API_KEY}

        resp = requests.get(search_url, headers=headers, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        photos = data.get("photos", [])

        if not photos:
            logger.warning("Pexels未找到相关图片，使用备用关键词")
            fallback_url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote('technology')}&per_page=3&size=large"
            resp2 = requests.get(fallback_url, headers=headers, timeout=10)
            resp2.raise_for_status()
            photos = resp2.json().get("photos", [])

        if photos:
            # 随机选一张
            photo = random.choice(photos)
            image_url = photo["src"]["large"]

            # 下载到本地
            covers_dir = Path.home() / "juejin_cover_images"
            covers_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = covers_dir / f"cover_{timestamp}.jpg"

            logger.info(f"⎿ 下载封面: {image_url[:60]}...")
            img_resp = requests.get(image_url, timeout=15)
            img_resp.raise_for_status()

            with open(local_path, "wb") as f:
                f.write(img_resp.content)

            logger.info(f"✓ 封面已下载到本地: {local_path}")
            logger.info(f"  Photographer: {photo.get('photographer', 'unknown')}")
            return str(local_path)

        logger.warning("Pexels未找到任何图片")
        return None

    except Exception as e:
        logger.warning(f"封面获取失败: {e}，将不带封面发布")
        return None


# ═══════════════════════════════════════════════════════════
#  标题提取
# ═══════════════════════════════════════════════════════════

def extract_title(titles: List[str], recommended_idx: int) -> str:
    """
    从标题列表中提取最终的发布标题（掘金标题建议 ≤30 字）
    """
    if recommended_idx < len(titles):
        raw = titles[recommended_idx]
    elif titles:
        raw = titles[0]
    else:
        return "无标题"

    title = raw
    for prefix in ["选项", "Option", "标题"]:
        if title.startswith(prefix) and ":" in title:
            title = title.split(":", 1)[-1].strip()

    title = title.replace("【推荐】", "").strip()
    return title[:40]


# ═══════════════════════════════════════════════════════════
#  发布方法（API 直发 + BW 备用）
# ═══════════════════════════════════════════════════════════

# ── API 发布 ───────────────────────────────────────────
JUEJIN_API_BASE = "https://juejin.cn"
DEFAULT_CATEGORY_ID = "6809637769959178254"
DEFAULT_TAG_IDS = ["6809640445233070096"]


def _api_post(path: str, data: dict, cookie: str) -> dict:
    """发送 POST 请求到掘金 API（使用 urllib 保持与 publish.py 兼容）"""
    import urllib.request, urllib.error
    url = f"{JUEJIN_API_BASE}{path}"
    payload = json.dumps(data).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://juejin.cn/",
        "Origin": "https://juejin.cn",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"err_no": e.code, "err_msg": body[:300]}
    except Exception as e:
        return {"err_no": -1, "err_msg": str(e)}


def create_draft_api(title: str, content: str, brief: str, category_id: str, tag_ids: list, cover_image: str, cookie: str) -> Optional[str]:
    """通过 API 创建文章草稿，返回 draft_id"""
    logger.info(f"⎿ 创建草稿: {title[:40]}...")
    data = {
        "category_id": category_id,
        "tag_ids": tag_ids,
        "link_url": "",
        "cover_image": cover_image or "",
        "title": title,
        "brief_content": brief,
        "edit_type": 10,  # 10 = Markdown 模式
        "html_content": "deprecated",
        "mark_content": content,
        "theme_ids": [],
    }
    resp = _api_post("/content_api/v1/article_draft/create", data, cookie)
    if resp.get("err_no") != 0:
        logger.error(f"创建草稿失败: {resp.get('err_msg', '未知错误')} (err_no={resp.get('err_no')})")
        return None
    draft_id = resp["data"].get("id") or resp["data"].get("draft_id")
    logger.info(f"✓ 草稿创建成功，draft_id: {draft_id}")
    return draft_id


def publish_draft_api(draft_id: str, cookie: str) -> Optional[str]:
    """通过 API 发布草稿，返回 article_id"""
    logger.info(f"⎿ 发布草稿: {draft_id}...")
    data = {
        "draft_id": draft_id,
        "sync_to_org": False,
        "column_ids": [],
        "theme_ids": [],
    }
    resp = _api_post("/content_api/v1/article/publish", data, cookie)
    if resp.get("err_no") != 0:
        logger.error(f"发布失败: {resp.get('err_msg', '未知错误')} (err_no={resp.get('err_no')})")
        return None
    article_id = resp["data"].get("article_id", draft_id)
    logger.info(f"✓ 发布成功！文章 ID: {article_id}")
    return article_id


def publish_via_api(article_data: Dict[str, Any], cover_path: Optional[str], cookie: str, title: str, body: str, dry_run: bool = False) -> Optional[str]:
    """
    通过掘金 API 发布文章（创建草稿 → 发布草稿）
    返回文章链接或 None
    """
    if dry_run:
        logger.info("[DRY-RUN] 模拟 API 发布成功")
        return "https://juejin.cn/post/dry-run-xxxxxxxx"

    # 生成摘要（50-100字）
    import re
    plain = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    plain = re.sub(r"[#*`>\[\]!]", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) >= 50:
        brief = plain[:100]
    else:
        brief = plain.ljust(50)[:100]

    # 草稿
    draft_id = create_draft_api(title, body, brief, DEFAULT_CATEGORY_ID, DEFAULT_TAG_IDS, cover_path or "", cookie)
    if not draft_id:
        return None

    # 发布
    article_id = publish_draft_api(draft_id, cookie)
    if not article_id:
        logger.info(f"草稿已创建: https://juejin.cn/editor/drafts/{draft_id} (发布失败，请手动发布)")
        return None

    return f"https://juejin.cn/post/{article_id}"


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def _load_juejin_cookie() -> str:
    """加载掘金登录 Cookie（从 juejin.env）"""
    config_file = SKILL_DIR / "juejin.env"
    if not config_file.exists():
        raise FileNotFoundError(f"Cookie 配置文件不存在: {config_file}")
    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
    # 提取双引号内的 Cookie 值
    marker = 'JUEJIN_COOKIE="'
    if marker in content:
        cookie = content.split(marker)[1].split('"')[0]
    else:
        # 降级：按 key=value 解析
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            if key.strip() == "JUEJIN_COOKIE" and val and "your_session_id" not in val:
                cookie = val
                break
        else:
            cookie = ""
    if not cookie or "your_session_id" in cookie:
        raise ValueError("JUEJIN_COOKIE 未配置，请检查 juejin.env 文件")
    logger.info(f"✓ Cookie 已加载 ({len(cookie)} 字符)")
    return cookie


def run(product_url: str,
        output_path: Optional[str] = None,
        dry_run: bool = False,
        auto_confirm: bool = False) -> Dict[str, Any]:
    """
    执行掘金文章发布流程

    Args:
        product_url: 产品链接
        output_path: 草稿输出路径（可选）
        dry_run: 测试模式
        auto_confirm: 自动确认发布（跳过人工确认）

    Returns:
        dict: {"success": bool, "title": str, "draft_path": str, ...}
    """
    # 加载掘金 Cookie
    cookie = _load_juejin_cookie()

    logger.info("=" * 60)
    logger.info("掘金文章发布模块启动")
    logger.info(f"产品链接: {product_url}")
    if dry_run:
        logger.info("[DRY-RUN MODE] 测试模式，不会实际发布")
    logger.info("=" * 60)

    # 步骤1: 生成文章
    logger.info("\n【步骤1】LLM 生成掘金文章")
    article_data = generate_article(product_url)

    # 步骤2: 保存草稿
    logger.info("\n【步骤2】保存草稿")
    draft_path = save_draft(article_data, product_url, output_path)

    # 步骤3: 人工确认
    logger.info("\n【步骤3】确认发布")
    should_publish = auto_confirm or confirm_publish(draft_path, dry_run)

    if not should_publish:
        logger.info("✗ 用户取消发布")
        return {
            "success": False,
            "reason": "cancelled",
            "draft_path": draft_path,
        }

    # 步骤4: 获取封面 → 发布
    logger.info("\n【步骤4】发布到掘金")
    titles = article_data.get("titles", [])
    recommended_idx = article_data.get("recommended_title_index", 0)
    final_title = extract_title(titles, recommended_idx)
    body = article_data.get("body", "")
    cover_keyword = extract_cover_keyword(final_title, body)
    cover_path = fetch_cover_image(cover_keyword)

    article_url = publish_via_api(article_data, cover_path, cookie, final_title, body, dry_run)

    if article_url:
        record = {
            "timestamp": datetime.now().isoformat(),
            "platform": "juejin",
            "product_url": product_url,
            "title": final_title,
            "body_length": len(body),
            "published": not dry_run,
            "draft_path": draft_path,
            "article_url": article_url if not dry_run else "",
        }
        if not dry_run:
            save_published_record(record)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"✓ 掘金文章发布完成")
        logger.info(f"   标题: {final_title}")
        logger.info(f"   草稿: {draft_path}")
        logger.info(f"{'=' * 60}")

        return {"success": True, "title": final_title, "draft_path": draft_path}

    else:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"✗ 发布未完成")
        logger.info(f"   草稿已保存: {draft_path}")
        logger.info(f"   可手动发布到: {JUEJIN_EDITOR_URL}")
        logger.info(f"{'=' * 60}")

        return {"success": False, "reason": "publish_failed", "draft_path": draft_path}


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="掘金文章发布模块 — AI 生成技术文章 + BrowserWing 自动发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成文章并保存草稿（不发布）
  python3 juejin-article-publisher.py --product-url "https://ai.hcrzx.com/" --dry-run
  
  # 生成并交互确认发布
  python3 juejin-article-publisher.py --product-url "https://ai.hcrzx.com/"
  
  # 自动确认发布（非交互模式）
  python3 juejin-article-publisher.py --product-url "https://ai.hcrzx.com/" --auto-confirm

前置条件:
  1. BrowserWing 已启动
  2. 已录制掘金文章发布脚本（设置 PUBLISH_SCRIPT_ID）
  3. 掘金登录态有效
        """
    )
    parser.add_argument("--product-url", required=True, help="产品链接")
    parser.add_argument("--output", help="草稿输出路径")
    parser.add_argument("--dry-run", action="store_true", help="测试模式（生成文章但不发布）")
    parser.add_argument("--auto-confirm", action="store_true", help="自动确认发布（跳过人工确认）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    try:
        result = run(
            product_url=args.product_url,
            output_path=args.output,
            dry_run=args.dry_run,
            auto_confirm=args.auto_confirm,
        )
        sys.exit(0 if result["success"] else 1)
    except Exception as e:
        logger.error(f"执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
