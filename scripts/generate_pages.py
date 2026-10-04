#!/usr/bin/env python3
"""从 data/*.json 生成 GitHub Pages 静态页到 docs/。

纯标准库，GitHub Actions 与本地都能直接跑：
  python3 scripts/generate_pages.py
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
BASE = "/relay-prices"
SITE = "https://apiranking.github.io" + BASE
MAIN = "https://www.apiranking.com"
UTM = "utm_source=github&utm_medium=referral&utm_campaign=relay-prices"

NAV = [
    ("ai", "AI 中转站"), ("api", "API 中转站"), ("recommend", "中转站推荐"),
    ("claude", "Claude"), ("claude-code", "Claude Code"), ("gpt", "GPT"),
    ("gemini", "Gemini"), ("grok", "Grok"), ("deepseek", "DeepSeek"),
    ("rate-explained", "倍率怎么算"),
]
# 页面 slug → 主站对应排行页（页脚唯一回链）
MAIN_PAGE = {
    "claude": "/rankings/claude-api", "claude-code": "/rankings/claude-api",
    "gpt": "/rankings/gpt-api", "gemini": "/rankings/gemini-api",
    "grok": "/rankings/grok-api", "deepseek": "/rankings/deepseek-api",
}

CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.6;max-width:1080px;margin:0 auto;padding:16px;color:#222;background:#fafafa}
h1{font-size:1.6em;margin:.6em 0 .3em}h2{font-size:1.25em;margin:1.6em 0 .4em}
.lead{background:#eef6ff;border-left:4px solid #2f7de1;padding:10px 14px;margin:12px 0}
nav{font-size:.92em;margin-bottom:8px}nav a{margin-right:12px;white-space:nowrap}
table{width:100%;border-collapse:collapse;background:#fff;margin:8px 0 20px;font-size:.95em}
th,td{padding:7px 10px;border-bottom:1px solid #e5e5e5;text-align:left}
th{background:#f0f2f5;font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:#2f7de1;text-decoration:none}a:hover{text-decoration:underline}
footer{margin-top:32px;padding-top:12px;border-top:1px solid #ddd;color:#666;font-size:.9em}
.wrap{overflow-x:auto}
"""


def money(v: float) -> str:
    return f"¥{v:.4f}".rstrip("0").rstrip(".") if v < 1 else f"¥{v:.2f}".rstrip("0").rstrip(".")


def rate(v: float | None) -> str:
    return "—" if v is None else f"{v:g}"


def page(slug: str, title: str, desc: str, body: str, updated: str) -> str:
    url = f"{SITE}/" if slug == "" else f"{SITE}/{slug}/"
    nav = " ".join(f'<a href="{BASE}/{s}/">{escape(l)}</a>' for s, l in NAV)
    main_link = MAIN + MAIN_PAGE.get(slug, "/") + "?" + UTM + (f"&utm_content={slug}" if slug else "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{url}">
<style>{CSS}</style>
</head>
<body>
<nav><a href="{BASE}/">首页</a> {nav}</nav>
{body}
<footer>
<p>数据更新：{updated}。价格按人民币 1:1 充值折算，每百万 tokens。</p>
<p>想看各站真假检测和稳定性，去 <a href="{main_link}" rel="nofollow">API Ranking</a>。</p>
</footer>
</body>
</html>
"""


def vendor_body(d: dict, slug: str) -> tuple[str, str, str]:
    v = d["vendor"]
    if slug == "claude-code":
        title = "Claude Code 中转站价格对比：哪家便宜"
        intro = (f"Claude Code 主要跑 Sonnet 和 Opus。下表是 {d['site_count']} 家中转站这两类模型的价格，"
                 "按倍率从低到高排。接入时把 <code>ANTHROPIC_BASE_URL</code> 换成中转站地址、"
                 "<code>ANTHROPIC_AUTH_TOKEN</code> 换成中转站 key 即可。")
    else:
        title = f"{v} 中转站价格对比：{d['site_count']} 家哪家便宜"
        intro = f"{d['site_count']} 家中转站支持 {v}，最低 {rate(d['min_rate'])} 倍官方价。每个模型单独列表，按倍率从低到高排。"
    desc = f"{d['site_count']} 家 {v} 中转站价格与倍率对比，最低 {rate(d['min_rate'])} 倍官方价。"
    parts = [f"<h1>{escape(title)}</h1>", f'<p class="lead">{intro}</p>']
    toc = " · ".join(f'<a href="#{escape(t["model_key"])}">{escape(t["label"])}</a>' for t in d["tables"])
    if len(d["tables"]) > 1:
        parts.append(f"<p>跳到：{toc}</p>")
    for t in d["tables"]:
        parts.append(
            f'<h2 id="{escape(t["model_key"])}">{escape(t["label"])} 中转站价格（{len(t["rows"])} 家）</h2>'
            f'<p>官方价：输入 ${t["official_in"]:g} / 输出 ${t["official_out"]:g} 每百万 tokens。</p>'
            '<div class="wrap"><table><thead><tr><th>#</th><th>中转站</th><th>倍率</th>'
            '<th>输入价</th><th>输出价</th></tr></thead><tbody>'
        )
        for i, r in enumerate(t["rows"], 1):
            parts.append(f'<tr><td>{i}</td><td>{escape(r["name"])}</td><td class="n">{rate(r["rate"])}</td>'
                         f'<td class="n">{money(r["in"])}</td><td class="n">{money(r["out"])}</td></tr>')
        parts.append("</tbody></table></div>")
    parts.append(f'<p>倍率是什么、怎么换算成实际花费，见 <a href="{BASE}/rate-explained/">中转站倍率怎么算</a>。</p>')
    return title, desc, "\n".join(parts)


def overview_table(fams: list[dict], rows: list[dict], numbered: bool) -> str:
    head = "".join(f"<th>{escape(f['label'])}</th>" for f in fams)
    out = ['<div class="wrap"><table><thead><tr>' + ("<th>#</th>" if numbered else "")
           + f"<th>中转站</th>{head}</tr></thead><tbody>"]
    for i, r in enumerate(rows, 1):
        cells = "".join(f'<td class="n">{rate(r["rates"].get(f["key"]))}</td>' for f in fams)
        out.append("<tr>" + (f"<td>{i}</td>" if numbered else "") + f"<td>{escape(r['name'])}</td>{cells}</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def ai_body(d: dict) -> tuple[str, str, str]:
    n = d["site_count"]
    title = f"AI 中转站大全：{n} 家价格倍率一表看完"
    desc = f"{n} 家 AI 中转站的 Claude、GPT、Gemini、Grok、DeepSeek 最低倍率对比。"
    body = (f"<h1>{escape(title)}</h1>"
            f'<p class="lead">{n} 家 AI 中转站，每格是该站这个厂商模型的最低倍率（官方价的几倍），越小越便宜；“—”表示没有。'
            "支持厂商多的排前面。</p>"
            + overview_table(d["families"], d["rows"], numbered=False)
            + f'<p>想看单个模型的具体价格：{" · ".join(f"""<a href="{BASE}/{s}/">{l}</a>""" for s, l in NAV[3:9])}</p>')
    return title, desc, body


def api_body(d: dict) -> tuple[str, str, str]:
    title = "API 中转站哪家便宜：各模型最低倍率前 10"
    desc = "Claude、GPT、Gemini、Grok、DeepSeek API 中转站最低倍率前 10 名。"
    parts = [f"<h1>{escape(title)}</h1>",
             f'<p class="lead">从 {d["site_count"]} 家 API 中转站里，按厂商挑出倍率最低的 10 家。倍率 = 官方价的几倍，越小越便宜。</p>']
    slug_of = {"claude": "claude", "openai": "gpt", "gemini": "gemini", "grok": "grok", "deepseek": "deepseek"}
    for f in d["families"]:
        parts.append(f'<h2>{escape(f["label"])} API 中转站最便宜前 10（共 {f["count"]} 家）</h2>'
                     '<table><thead><tr><th>#</th><th>中转站</th><th>最低倍率</th></tr></thead><tbody>')
        for i, r in enumerate(f["rows"], 1):
            parts.append(f'<tr><td>{i}</td><td>{escape(r["name"])}</td><td class="n">{rate(r["rate"])}</td></tr>')
        parts.append(f'</tbody></table><p><a href="{BASE}/{slug_of[f["key"]]}/">看全部 {f["count"]} 家 {escape(f["label"])} 中转站价格 →</a></p>')
    return title, desc, "\n".join(parts)


def recommend_body(d: dict) -> tuple[str, str, str]:
    n = len(d["rows"])
    title = f"中转站推荐：{n} 家靠谱 API 中转站"
    desc = f"{n} 家推荐的 AI API 中转站，附 Claude、GPT、Gemini、Grok、DeepSeek 最低倍率。"
    body = (f"<h1>{escape(title)}</h1>"
            f'<p class="lead">按 API Ranking 综合排序取前 {n} 家，每格是该厂商模型的最低倍率，越小越便宜。</p>'
            + overview_table(d["families"], d["rows"], numbered=True))
    return title, desc, body


def rate_body(official: list[dict], updated: str) -> tuple[str, str, str]:
    title = "中转站倍率怎么算：一看就懂的换算方法"
    desc = "中转站倍率是什么、怎么换算成人民币价格、为什么低倍率不一定省钱。"
    ex = next((o for o in official if o["family"] == "claude" and "Sonnet" in o["label"]), official[0])
    a, b = 0.5, 1.2
    rows = "".join(
        f'<tr><td>{escape(o["label"])}</td><td class="n">${o["in"]:g} / ${o["out"]:g}</td>'
        + "".join(f'<td class="n">{money(o["in"] * k)} / {money(o["out"] * k)}</td>' for k in (0.3, 0.5, 1))
        + "</tr>"
        for o in official
    )
    body = f"""<h1>{escape(title)}</h1>
<p class="lead">倍率 = 中转站价格 ÷ 官方价格。0.5 倍就是官方价的一半，数字越小越便宜。</p>
<h2>怎么换算成人民币</h2>
<p>多数中转站充值按 1 元 = 1 美元额度算，所以：<strong>每百万 tokens 实际花费（元）= 官方美元价 × 倍率</strong>。</p>
<p>以 {escape(ex["label"])} 为例，官方价输入 ${ex["in"]:g} / 输出 ${ex["out"]:g} 每百万 tokens：</p>
<ul>
<li>{a} 倍的站：输入 {money(ex["in"] * a)}，输出 {money(ex["out"] * a)}</li>
<li>{b} 倍的站：输入 {money(ex["in"] * b)}，输出 {money(ex["out"] * b)}</li>
</ul>
<p>如果某站充值是按真实汇率（约 7 元换 1 美元）算的，要再乘上汇率才能和别家比。本站表格已经统一折算好，可以直接比。</p>
<h2>看倍率时注意三点</h2>
<ol>
<li><strong>同一家站，不同分组倍率不同。</strong>便宜分组和稳定分组可能差好几倍，本站列的是每家最低的那个。</li>
<li><strong>同一家站，不同模型倍率也可能不同。</strong>Claude 便宜不代表 GPT 也便宜，要按你用的模型看。</li>
<li><strong>倍率低不等于花得少。</strong>缓存计费、分组稳定性都会影响实际账单，先小额充值试一下最稳。</li>
</ol>
<h2>主流模型不同倍率下的价格</h2>
<p>单位：每百万 tokens，输入 / 输出。</p>
<div class="wrap"><table><thead><tr><th>模型</th><th>官方价</th><th>0.3 倍</th><th>0.5 倍</th><th>1 倍</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<h2>各模型中转站价格</h2>
<p>{" · ".join(f'<a href="{BASE}/{s}/">{escape(l)} 中转站</a>' for s, l in NAV[3:9])}</p>
"""
    return title, desc, body


def index_body(pages: dict) -> tuple[str, str, str]:
    title = "AI API 中转站价格对比 | Claude、GPT、Gemini、Grok、DeepSeek"
    desc = "AI API 中转站价格与倍率对比，覆盖 Claude、GPT、Gemini、Grok、DeepSeek。"
    items = []
    for s, l in NAV:
        d = pages.get(s, {})
        n = d.get("site_count")
        items.append(f'<li><a href="{BASE}/{s}/">{escape(l)}{" 中转站价格" if s in MAIN_PAGE else ""}</a>'
                     + (f"（{n} 家）" if n else "") + "</li>")
    body = (f"<h1>AI API 中转站价格对比</h1>"
            '<p class="lead">各家中转站的 Claude、GPT、Gemini、Grok、DeepSeek 价格和倍率，按模型分好、按价格排好。</p>'
            f"<ul>{''.join(items)}</ul>")
    return title, desc, body


def write(slug: str, html: str) -> None:
    d = DOCS / slug if slug else DOCS
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    pages = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in DATA.glob("*.json") if p.stem != "official"}
    official = json.loads((DATA / "official.json").read_text(encoding="utf-8"))
    updated = max(d["updated"] for d in pages.values())

    builders = {"ai": ai_body, "api": api_body, "recommend": recommend_body}
    for slug, _ in NAV:
        if slug == "rate-explained":
            title, desc, body = rate_body(official, updated)
        elif slug in builders:
            title, desc, body = builders[slug](pages[slug])
        else:
            title, desc, body = vendor_body(pages[slug], slug)
        write(slug, page(slug, title, desc, body, updated))
    title, desc, body = index_body(pages)
    write("", page("", title, desc, body, updated))

    urls = [f"{SITE}/"] + [f"{SITE}/{s}/" for s, _ in NAV]
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{u}</loc><lastmod>{updated}</lastmod></url>\n" for u in urls)
        + "</urlset>\n", encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"生成 {len(urls)} 页 → {DOCS}")


if __name__ == "__main__":
    main()
