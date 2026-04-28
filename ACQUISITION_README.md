# 掘金评论区获客脚本使用指南

## 📋 功能概述

掘金评论区获客脚本提供三大核心功能：

1. **搜索文章** - 按关键词搜索掘金文章，筛选高价值目标
2. **评论文章** - 自动对目标文章发表评论
3. **私信用户** - 给文章作者发送私信

## 🔧 安装配置

### 1. 确保已配置掘金 Cookie

在 `juejin.env` 文件中配置你的掘金登录 Cookie：

```bash
# 在 skill 根目录
JUEJIN_COOKIE="sessionid=xxx; ..."
```

获取 Cookie 方法：
1. 登录掘金网站
2. F12 打开开发者工具 → Network 标签
3. 点击任意请求，复制 Request Headers 中的 Cookie

### 2. 配置文件说明

`juejin_acquisition_config.json` 包含以下配置项：

```json
{
  "keywords": ["API中转", "大模型", "AI开发"],
  "min_views": 1000,
  "min_comments": 20,
  "max_days": 7,
  "comment_templates": [...],
  "message_templates": [...],
  "delay_range": [5, 15],
  "daily_comment_limit": 15,
  "daily_message_limit": 8
}
```

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| keywords | 搜索关键词列表 | ["API中转", ...] |
| min_views | 最小阅读量筛选 | 1000 |
| min_comments | 最小评论数筛选 | 20 |
| max_days | 最大发布时间（天） | 7 |
| comment_templates | 评论话术模板 | 8条模板 |
| message_templates | 私信话术模板 | 6条模板 |
| delay_range | 随机延时范围（秒） | [5, 15] |
| daily_comment_limit | 每日评论上限 | 15 |
| daily_message_limit | 每日私信上限 | 8 |

## 🚀 使用方式

### 方式一：搜索文章

```bash
# 基本搜索
python3 scripts/juejin_acquisition.py search --keyword "API中转"

# 带筛选条件的搜索
python3 scripts/juejin_acquisition.py search \
  --keyword "API中转" \
  --min-views 1000 \
  --min-comments 20 \
  --max-days 7 \
  --limit 20
```

搜索结果会显示在终端，并保存到 `search_results_关键词.json` 文件。

### 方式二：评论文章

```bash
# 使用模板自动评论
python3 scripts/juejin_acquisition.py comment --article-id 738xxx

# 指定评论内容
python3 scripts/juejin_acquisition.py comment \
  --article-id 738xxx \
  --message "这篇文章写得真好，学到了很多！"

# 指定话题（用于模板变量替换）
python3 scripts/juejin_acquisition.py comment \
  --article-id 738xxx \
  --topic "API中转"
```

### 方式三：私信用户

```bash
# 使用模板自动私信
python3 scripts/juejin_acquisition.py message --user-id xxx

# 指定私信内容
python3 scripts/juejin_acquisition.py message \
  --user-id xxx \
  --message "你好，对你的文章很感兴趣，想交流一下"

# 指定话题
python3 scripts/juejin_acquisition.py message \
  --user-id xxx \
  --topic "API中转"
```

### 方式四：全自动模式

```bash
# 使用默认配置
python3 scripts/juejin_acquisition.py auto

# 使用自定义配置
python3 scripts/juejin_acquisition.py auto --config my_config.json
```

全自动模式会：
1. 遍历所有关键词搜索文章
2. 筛选高价值文章（阅读量>1000、评论数>20、7天内发布）
3. 自动评论文章
4. 自动私信作者
5. 生成执行报告

## 📝 话术模板变量

模板支持以下变量替换：

- `{topic}` - 话题关键词（从文章标题提取或手动指定）

示例模板：
```
"感谢分享！{topic}确实是当前的热门方向，欢迎交流~"
```

实际输出：
```
"感谢分享！API中转确实是当前的热门方向，欢迎交流~"
```

## ⚠️ 防封号策略

脚本内置以下防封号机制：

1. **随机延时** - 每次操作后随机等待 5-15 秒
2. **话术轮换** - 自动切换不同的话术模板
3. **频率限制** - 默认每日评论上限 15 条，私信上限 8 条
4. **日志记录** - 详细记录每次操作，便于排查问题

**重要提醒**：
- 不要频繁操作，建议每日评论不超过 20 条
- 私信更加敏感，建议每日不超过 10 条
- 如果收到平台警告，请立即停止并降低频率

## 📊 日志查看

所有操作日志保存在 `juejin_acquisition.log` 文件中：

```bash
# 查看实时日志
tail -f juejin_acquisition.log

# 查看错误日志
grep "ERROR" juejin_acquisition.log
```

## 🔍 故障排查

| 现象 | 原因 | 解决方案 |
|------|------|---------|
| Cookie 无效 | Cookie 过期 | 重新登录掘金获取新 Cookie |
| 搜索失败 | API 限制 | 降低搜索频率，等待后重试 |
| 评论失败 | 频率限制 | 降低评论频率，延长延时 |
| 私信失败 | 权限不足 | 确认已关注对方或对方允许私信 |

## 📁 文件结构

```
juejin-publisher/
├── scripts/
│   ├── juejin_acquisition.py      # 获客主脚本
│   └── publish.py                  # 文章发布脚本
├── juejin.env                      # Cookie 配置
├── juejin_acquisition_config.json  # 获客配置
├── juejin_acquisition.log          # 操作日志
├── search_results_*.json           # 搜索结果
└── ACQUISITION_README.md           # 使用说明
```

## 💡 使用建议

1. **先搜索后评论** - 先用 search 命令找到目标文章，确认质量后再评论
2. **话术个性化** - 根据目标受众修改话术模板，提高转化率
3. **分时段执行** - 避免在短时间内集中操作
4. **关注反馈** - 定期查看日志，根据效果调整策略
