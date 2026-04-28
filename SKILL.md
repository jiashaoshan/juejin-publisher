---
name: juejin-publisher
version: 2.0.0
license: MIT
description: 掘金全栈运营技能。AI文章生成+发布 + 评论区获客(搜索→评分→LLM评论→私信) + 文章查询。
metadata:
  openclaw:
    emoji: "⛏️"
    category: publishing
  clawdbot:
    emoji: "⛏️"
    requires:
      bins: ["python3", "curl"]
    install: []
---

# 掘金全栈运营技能 v2.0

## 功能总览

| 功能 | 脚本 | 说明 |
|------|------|------|
| 📝 **文章生成+发布** | `juejin-article-publisher.py` | LLM生成技术文章 → 人工确认 → BW发布 |
| 💬 **评论区获客** | `juejin_acquisition.py` | 搜索 → AI四维评分 → LLM评论 → LLM私信 |
| 📊 **文章查询** | `publish.py` | Markdown文章一键发布（API方式） |

---

## 模块一：AI 文章生成+发布

### 架构

```
产品链接 → LLM读取网站 → 生成技术文章(标题+正文) 
→ 保存草稿(.md) → 人工确认 → Pexels封面 → BrowserWing发布
```

### 快速使用

```bash
# 测试模式（只生成文章，不发布）
python3 scripts/juejin-article-publisher.py --product-url "https://ai.hcrzx.com/" --dry-run

# 交互确认发布
python3 scripts/juejin-article-publisher.py --product-url "https://ai.hcrzx.com/"

# 自动发布（非交互）
python3 scripts/juejin-article-publisher.py --product-url "https://ai.hcrzx.com/" --auto-confirm
```

### 流程

1. **LLM生成** — 读取产品网站 → 按 `templates/article-prompt.md` 模板生成
2. **保存草稿** — 草稿保存到 `data/juejin_draft_*.md`
3. **人工确认** — 交互式确认（`y/n`），支持 `--auto-confirm` 跳过
4. **封面图片** — Pexels自动搜索 → 下载到 `~/juejin_cover_images/`
5. **BW发布** — 调用BrowserWing脚本发布到掘金编辑器

### 前置条件

- **BrowserWing 脚本**: 需要录制一个掘金文章发布脚本（变量：`${标题}`、`${正文}`、`${封面}`）
- 录制完成后将脚本ID写入环境变量 `JUEJIN_BW_SCRIPT_ID` 或修改脚本中的 `PUBLISH_SCRIPT_ID`

---

## 模块二：评论区获客 v2.0

### 架构

```
产品链接 → LLM生成关键词(6个) → 搜索掘金文章 
→ AI四维评分(热度40+互动30+时效20+质量10) 
→ 筛选Top10 → LLM逐篇生成评论(4种风格) → 自动发表
→ LLM生成私信 → 自动发送
```

### 快速使用

```bash
# 全自动获客
python3 scripts/juejin_acquisition.py auto --product-url "https://ai.hcrzx.com/"

# 测试模式（不真实发表）
python3 scripts/juejin_acquisition.py auto --product-url "https://ai.hcrzx.com/" --dry-run

# 控制数量
python3 scripts/juejin_acquisition.py auto \
  --product-url "https://ai.hcrzx.com/" \
  --max-comments 5 \
  --max-messages 2

# 单独搜索
python3 scripts/juejin_acquisition.py search --keyword "AI大模型"
```

### AI 能力

| 能力 | 实现 |
|------|------|
| **关键词生成** | LLM从产品链接动态生成6个搜索词 + 种子池降级 |
| **四维评分** | 热度(40) + 互动(30) + 时效(20) + 质量(10) |
| **评论生成** | LLM读完整文章 → 4种风格随机(赞同补充/提问讨论/实战分享/案例分析) |
| **私信生成** | LLM读文章后生成真诚交流私信 |
| **反爬保护** | 时段8-23 + 日/小时上限 + 加权随机延迟 + 历史去重 |

### 评论API关键点

- 端点: `POST /interact_api/v1/comment/publish`
- 基础URL: `https://juejin.cn`（不可用 `api.juejin.cn`，会返回空响应）
- 字段名: `comment_content`（不是 `content`）
- 请求体: `{"item_id": "...", "item_type": 2, "comment_content": "..."}`

---

## 📚 常用分类/标签 ID

| 分类 | category_id |
|------|-------------|
| 前端 | `6809637767543259144` |
| 后端 | `6809637769959178254` |
| AI | `6809637773935378440` |
| 工具 | `6809637771511070734` |

| 标签 | tag_id |
|------|--------|
| AI | `6809640445233070096` |
| Python | `6809640408797167623` |
| JavaScript | `6809640407484334093` |
| 自动化 | `6809637772874219534` |

---

## 🛠️ 故障排查

| 现象 | 原因 | 解决方案 |
|------|------|---------|
| 评论返回空body | api.juejin.cn域名 | 改用 juejin.cn 代理 |
| 评论err_no=4005 | 字段名错误 | 用 `comment_content` 不用 `content` |
| 评论err_no=1 | Cookie失效 | 重新登录掘金获取Cookie |
| 搜索返回空 | 搜索API不需要auth | 检查关键词和网络 |
| LLM不可用 | zhihu_llm.py未找到 | 检查模块搜索路径 |
