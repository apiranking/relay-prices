# AI API 中转站价格数据

各家 AI API 中转站的 Claude、GPT、Gemini、Grok、DeepSeek 价格和倍率对比，按模型分好、按价格排好。

在线查看：<https://apiranking.github.io/relay-prices/>

## 综合

- [AI 中转站](https://apiranking.github.io/relay-prices/ai/)：所有站各厂商最低倍率一表看完
- [API 中转站](https://apiranking.github.io/relay-prices/api/)：各厂商最便宜的前 10 家
- [中转站推荐](https://apiranking.github.io/relay-prices/recommend/)：综合排序前 30 家

## 按模型

- [Claude 中转站](https://apiranking.github.io/relay-prices/claude/)
- [Claude Code 中转站](https://apiranking.github.io/relay-prices/claude-code/)
- [GPT 中转站](https://apiranking.github.io/relay-prices/gpt/)
- [Gemini 中转站](https://apiranking.github.io/relay-prices/gemini/)
- [Grok 中转站](https://apiranking.github.io/relay-prices/grok/)
- [DeepSeek 中转站](https://apiranking.github.io/relay-prices/deepseek/)

热门型号（如 Claude Opus 5.5、Sonnet 4.6、GPT-5.5）各有单独一页，从对应厂商页进入。

## 倍率怎么算

[中转站倍率怎么算](https://apiranking.github.io/relay-prices/rate-explained/)：倍率 = 中转站价 ÷ 官方价，越小越便宜。

## 数据

`data/*.json` 是原始数据，字段：

- `name`：中转站名
- `slug`：站点标识（可为空）
- `in` / `out`：输入 / 输出价，人民币元每百万 tokens（按 1 元 = 1 美元额度充值折算）
- `rate`：倍率（官方价的几倍）

各站真假检测和稳定性见 [API Ranking](https://apiranking.com)。
