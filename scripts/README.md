# 掘金文章数据自动更新脚本

## 脚本说明

`update_feishu_sheet.py` - 自动从掘金获取文章数据并更新到飞书表格

## 功能特性

- ✅ 自动查询掘金文章数据（阅读量、点赞数、评论数、收藏数）
- ✅ 追加写入飞书表格"掘金文章数据监控看板"
- ✅ 自动计算日增数据（与上一条记录对比）
- ✅ 支持测试模式（--dry-run）预览数据
- ✅ 优雅的错误处理

## 使用方法

### 1. 测试模式（不实际写入）

```bash
python3 update_feishu_sheet.py --article-id 7627451787391434788 --dry-run
```

### 2. 正式更新

```bash
python3 update_feishu_sheet.py --article-id 7627451787391434788
```

## 配置说明

脚本需要飞书访问令牌才能写入表格。配置方式：

### 方式一：环境变量

```bash
export FEISHU_ACCESS_TOKEN="your_feishu_access_token_here"
python3 update_feishu_sheet.py --article-id 7627451787391434788
```

### 方式二：配置文件

1. 复制示例配置文件：
```bash
cp ../feishu.env.example ../feishu.env
```

2. 编辑 `feishu.env`，填入你的访问令牌：
```bash
export FEISHU_ACCESS_TOKEN="your_feishu_access_token_here"
```

## 获取飞书访问令牌

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建应用并获取 `user_access_token`
3. 确保应用有 `sheets:spreadsheet:write` 权限

## 表格字段说明

| 列 | 字段名 | 说明 |
|---|---|---|
| A | 日期 | 数据记录日期 |
| B | 文章标题 | 掘金文章标题 |
| C | 文章ID | 掘金文章唯一标识 |
| D | 阅读量 | 文章阅读次数 |
| E | 点赞数 | 文章点赞数 |
| F | 评论数 | 文章评论数 |
| G | 收藏数 | 文章收藏数 |
| H | 分享数 | 文章分享数（预留）|
| I | 日增阅读 | 相比上次的阅读量增长 |
| J | 日增点赞 | 相比上次的点赞数增长 |
| K | 日增评论 | 相比上次的评论数增长 |
| L | 日增收藏 | 相比上次的收藏数增长 |
| M | 备注 | 数据来源说明 |

## 自动化定时任务

可以配合 cron 每小时自动执行：

```bash
# 编辑 crontab
crontab -e

# 每小时执行一次
0 * * * * cd /Users/jiashaoshan/.openclaw/workspace/skills/juejin-publisher/scripts && python3 update_feishu_sheet.py --article-id 7627451787391434788 >> /tmp/juejin_update.log 2>&1
```

## 依赖

- Python 3.7+
- 标准库：`urllib`, `json`, `re`, `subprocess`, `argparse`, `datetime`

## 相关脚本

- `query_article.py` - 掘金文章数据查询脚本
