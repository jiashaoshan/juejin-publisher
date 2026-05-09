# 掘金全栈运营技能 (juejin-publisher)

[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/jiashaoshan/juejin-publisher)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

AI 驱动的掘金平台全自动化运营工具。从文章生成到评论区获客，一条指令全搞定。

---

## ✨ 功能

| 模块 | 脚本 | 功能 |
|------|------|------|
| 📝 **AI 文章生成+发布** | `juejin-article-publisher.py` | LLM 读产品网站 → 生成技术文章 → API 直发发布到掘金 |
| 💬 **评论区获客** | `juejin_acquisition.py` | 搜索文章 → AI 四维评分 → LLM 生成评论 → 自动评论+私信 |
| 🔍 **掘金搜索** | `search_juejin.py` | 独立搜索 + 筛选工具 |
| 🏷️ **标签查询** | `query_tags.py` | 查询掘金分类/标签 ID |

---

## 🏗️ 架构设计

### 文章发布流程

```
产品 URL (https://ai.hcrzx.com/)
        │
        ▼
┌─────────────────────────┐
│  步骤1: LLM 生成文章     │  ← article-prompt.md 模板
│  读取网站 → 提取信息     │     zhihu_llm.py 模块
│  生成标题(3选1) + 正文   │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  步骤2: 保存草稿         │  → data/juejin_draft_*.md
│  人工确认 / auto-confirm │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  步骤3: 封面图片         │  → Pexels API 搜索
│  下载到本地              │     ~/juejin_cover_images/
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  步骤4: API 直发发布     │  → create_draft → publish
│  掘金 Content API        │     POST /content_api/v1/...
└─────────────────────────┘
```

### 评论区获客流程

```
产品 URL
    │
    ▼
LLM 动态生成 6 个关键词  ← 种子池降级
    │
    ▼
搜索掘金文章 (3 关键词 × 20 篇)
    │
    ▼
AI 四维评分 (热度40+互动30+时效20+质量10)
    │
    ▼
筛选 Top 10 → LLM 逐篇生成评论 (4种风格)
    │
    ▼
自动发表 + 历史去重 + 反爬保护
    │
    ▼
LLM 生成私信 → 自动发送
```

### AI 四维评分模型

| 维度 | 权重 | 评分逻辑 |
|------|------|---------|
| **热度** | 40% | 阅读量 (log10 归一化) |
| **互动** | 30% | 评论+点赞+收藏 加权 |
| **时效** | 20% | 发布日期衰减 (牛顿冷却) |
| **质量** | 10% | 标题长度、内容长度、关键词匹配 |

### 评论风格多样性

LLM 随机选择以下 4 种评论风格之一：

| 风格 | 示例 |
|------|------|
| 赞同补充 | "说实话，这篇文章挺到位的。我之前也..." |
| 提问讨论 | "有个疑问想请教下，关于XX这块..." |
| 实战分享 | "我们团队最近也在搞这块，踩了几个坑..." |
| 案例分析 | "看了这个案例，让我想起之前做的一个项目..." |

### 反爬策略

```
工作时段: 8:00-23:00
├── 每日上限: 20 评论 / 10 私信
├── 每小时上限: 5 评论 / 3 私信
├── 评论间隔: 随机 30-90s
├── 私信间隔: 随机 60-120s
├── 搜索间隔: 随机 3-8s
├── 关键词切换: 随机 5-15s
└── 错误重试: 3次 × 20s 退避
```

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- `requests` 库（`pip3 install requests`）
- 掘金账号 + 登录 Cookie

### 安装

```bash
# 克隆仓库
git clone https://github.com/jiashaoshan/juejin-publisher.git
cd juejin-publisher

# 安装依赖
pip3 install requests

# 配置 Cookie（见下方）
cp juejin.env.example juejin.env
# 编辑 juejin.env，填入你的 Cookie
```

### 配置 Cookie

1. 登录 [juejin.cn](https://juejin.cn)
2. F12 → Application → Cookies → 复制所有 Cookie
3. 写入 `juejin.env`：

```bash
JUEJIN_COOKIE="sessionid=xxx; uid_tt=xxx; passport_csrf_token=xxx; ..."
```

> ⚠️ Cookie 约 30 天过期，失效后需重新获取。脚本会提示 `err_no=403 must login`。

### LLM 配置

共用 `zhihu-campaign` 技能的 `zhihu_llm.py` 模块。确保该模块在以下路径之一：

```
./scripts/zhihu_llm.py
../zhihu-campaign/scripts/zhihu_llm.py
../../zhihu-campaign/scripts/zhihu_llm.py
~/.openclaw/workspace/skills/zhihu-campaign/scripts/zhihu_llm.py
```

或设置环境变量：
```bash
export OPENAI_API_KEY="sk-xxx"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

---

## 📖 使用指南

### 一、AI 生成+发布文章

```bash
# 测试模式（只生成不发布）
python3 scripts/juejin-article-publisher.py \
  --product-url "https://ai.hcrzx.com/" \
  --dry-run

# 交互确认发布
python3 scripts/juejin-article-publisher.py \
  --product-url "https://ai.hcrzx.com/"

# 自动发布（CI/CD/定时任务）
python3 scripts/juejin-article-publisher.py \
  --product-url "https://ai.hcrzx.com/" \
  --auto-confirm

# 指定草稿输出路径
python3 scripts/juejin-article-publisher.py \
  --product-url "https://ai.hcrzx.com/" \
  --output ./my-article.md

# 详细日志
python3 scripts/juejin-article-publisher.py \
  --product-url "https://ai.hcrzx.com/" \
  --verbose
```

**输出示例**：
```
✓ Cookie 已加载 (1562 字符)
✓ LLM 生成文章: 开发者福音：一个Key调用10+主流大模型...
✓ 草稿已保存: data/juejin_draft_20260428_165648.md
✓ 封面已下载: ~/juejin_cover_images/cover_20260428.jpg
✓ 草稿创建成功: draft_id=7633600050702417926
✓ 发布成功！https://juejin.cn/post/7633624945063493672
```

### 二、评论区获客

```bash
# 全自动模式
python3 scripts/juejin_acquisition.py auto \
  --product-url "https://ai.hcrzx.com/"

# 控制数量
python3 scripts/juejin_acquisition.py auto \
  --product-url "https://ai.hcrzx.com/" \
  --max-comments 5 \
  --max-messages 2

# Dry-run（不实际发表）
python3 scripts/juejin_acquisition.py auto \
  --product-url "https://ai.hcrzx.com/" \
  --dry-run

# 单独搜索
python3 scripts/juejin_acquisition.py search --keyword "AI大模型"

# 单独评论
python3 scripts/juejin_acquisition.py comment \
  --article-id 7241064852331692090 \
  --topic "大模型"
```

### 三、Markdown 直接发布

```bash
# 发布 Markdown 文件（使用 frontmatter）
python3 scripts/publish.py my-article.md

# 指定分类和标签
python3 scripts/publish.py my-article.md \
  --category "6809637769959178254" \
  --tags "6809640445233070096,6809640407484334093"

# 仅创建草稿
python3 scripts/publish.py my-article.md --draft-only
```

Markdown frontmatter 示例：
```markdown
---
title: 我的技术文章
description: 文章摘要 50-100 字
cover: https://example.com/cover.jpg
category_id: "6809637769959178254"
tag_ids: "6809640445233070096"
---

# 正文开始
```

---

## 📁 文件结构

```
juejin-publisher/
├── README.md                          # 本文件
├── SKILL.md                           # OpenClaw 技能定义
├── .gitignore
├── juejin_acquisition_config.json     # 获客策略配置
├── example.md                         # Markdown 示例
│
├── scripts/                           # 核心脚本
│   ├── juejin-article-publisher.py    # ★ AI 文章生成+发布
│   ├── juejin_acquisition.py          # ★ 评论区获客 v2.0
│   ├── publish.py                     # Markdown 直发
│   ├── query_tags.py                  # 标签查询
│   └── search_juejin.py               # 独立搜索
│
├── templates/                         # 文章生成模板
│   └── article-prompt.md              # 掘金文章生成提示词
│
├── references/                        # 参考数据
│   ├── category_ids.md                # 常用分类 ID
│   └── tag_ids.md                     # 常用标签 ID
│
└── data/                              # 运行时数据 (gitignore)
    ├── commented-history.json         # 评论历史
    ├── messaged-history.json          # 私信历史
    ├── published-articles.json        # 发布记录
    └── juejin_draft_*.md              # 文章草稿
```

---

## ⚙️ 配置参考

### juejin_acquisition_config.json

```json
{
  "keywords": ["OpenClaw", "AI大模型", "DeepSeek"],
  "scoring": {
    "view_weight": 40,
    "interaction_weight": 30,
    "timeliness_weight": 20,
    "quality_weight": 10
  },
  "anti_crawl": {
    "work_hours": {"start": 8, "end": 23},
    "daily": {"max_comments": 20, "max_messages": 10},
    "hourly": {"max_comments": 5, "max_messages": 3},
    "delays": {
      "between_comments": {"min": 30, "max": 90},
      "between_messages": {"min": 60, "max": 120},
      "between_searches": {"min": 3, "max": 8}
    }
  }
}
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JUEJIN_COOKIE` | 掘金登录 Cookie | 从 `juejin.env` 读取 |
| `JUEJIN_DEFAULT_CATEGORY_ID` | 默认文章分类 ID | `6809637769959178254` (后端) |
| `JUEJIN_DEFAULT_TAG_IDS` | 默认标签 ID (逗号分隔) | `6809640408797167623` (Python) |
| `OPENAI_API_KEY` | LLM API Key | 从 `zhihu_llm.py` 读取 |
| `OPENAI_API_BASE` | LLM API 地址 | `https://api.openai.com/v1` |

---

## 🔧 故障排查

| 现象 | 原因 | 解决方案 |
|------|------|---------|
| `err_no=403: must login` | Cookie 过期 | 重新登录掘金获取 Cookie |
| 评论返回空body | 使用了 `api.juejin.cn` | 改用 `juejin.cn` 代理 |
| `err_no=4005: 评论内容为空` | 字段名错误 | 用 `comment_content` 不用 `content` |
| `err_no=2: 参数错误` | 字段格式错误 | 检查 tag_ids 是否为字符串数组 |
| LLM 不可用 | zhihu_llm.py 未找到 | 检查模块搜索路径配置 |
| 文章发布 `err_no=2` | 摘要长度不符 | 摘要需 50-100 字 |

---

## 📊 API 端点参考

| API | 端点 | 说明 |
|-----|------|------|
| 搜索文章 | `POST /search_api/v1/search` | `item_type=2` |
| 评论列表 | `POST /interact_api/v1/comment/list` | |
| 发表评论 | `POST /interact_api/v1/comment/publish` | `comment_content` 字段 |
| 创建草稿 | `POST /content_api/v1/article_draft/create` | `edit_type=10` (Markdown) |
| 发布草稿 | `POST /content_api/v1/article/publish` | 传入 `draft_id` |
| 用户信息 | `GET /user_api/v1/user/get` | Cookie 有效性验证 |

> **注意**：评论 API 需通过 `juejin.cn` 代理（非 `api.juejin.cn`），后者会返回空响应。文章发布 API 两个域名均可。

---

## 📚 常用分类/标签

| 分类 | ID |
|------|----|
| 前端 | `6809637767543259144` |
| 后端 | `6809637769959178254` |
| AI | `6809637773935378440` |
| Android | `6809635626879549454` |
| iOS | `6809635627209637895` |
| 工具 | `6809637771511070734` |

| 标签 | ID |
|------|----|
| AI | `6809640445233070096` |
| Python | `6809640408797167623` |
| JavaScript | `6809640407484334093` |
| Vue.js | `6809640445233070094` |
| React | `6809640407484334100` |
| Go | `6809640408797167624` |
| 自动化 | `6809637772874219534` |

---

## 🤖 集成到定时任务

```bash
# 每天 10:00 自动发布一篇文章
0 10 * * * cd /path/to/juejin-publisher && \
  python3 scripts/juejin-article-publisher.py \
  --product-url "https://ai.hcrzx.com/" --auto-confirm >> publish.log 2>&1

# 每天 14:00 自动获客（5评论 + 2私信）
0 14 * * * cd /path/to/juejin-publisher && \
  python3 scripts/juejin_acquisition.py auto \
  --product-url "https://ai.hcrzx.com/" \
  --max-comments 5 --max-messages 2 >> acquisition.log 2>&1
```

---

## 📄 License

MIT

---

*Made with ❤️ by AI 智能团队*
