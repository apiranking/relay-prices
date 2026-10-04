#!/usr/bin/env python3
"""从 data/*.json 生成 GitHub Pages 静态页到 docs/。

纯标准库，本地直接跑：
  python3 scripts/generate_pages.py
"""
from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
BASE = "/relay-prices"
SITE = "https://apiranking.github.io" + BASE
MAIN = "https://apiranking.com"
UTM = "utm_source=github&utm_medium=referral&utm_campaign=relay-prices"
YEAR = "2026"
TOP_LINKS = 5      # 每张榜只给前几名加主站详情链接，长表站名不链
TOP_PER_MODEL = 10  # 厂商页每个模型列前几名

NAV = [
    ("ai", "AI 中转站"), ("api", "API 中转站"), ("recommend", "中转站推荐"),
    ("claude", "Claude"), ("claude-code", "Claude Code"), ("gpt", "GPT"),
    ("gemini", "Gemini"), ("grok", "Grok"), ("deepseek", "DeepSeek"),
    ("rate-explained", "倍率怎么算"),
]
VENDOR_SLUGS = ["claude", "claude-code", "gpt", "gemini", "grok", "deepseek"]
FAMILY_SLUG = {"claude": "claude", "openai": "gpt", "gemini": "gemini", "grok": "grok", "deepseek": "deepseek"}
# 页面 slug → 主站对应排行页
MAIN_PAGE = {
    "claude": "/rankings/claude-api", "claude-code": "/rankings/claude-api",
    "gpt": "/rankings/gpt-api", "gemini": "/rankings/gemini-api",
    "grok": "/rankings/grok-api", "deepseek": "/rankings/deepseek-api",
}

CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.6;max-width:1080px;margin:0 auto;padding:16px;color:#222;background:#fafafa}
h1{font-size:1.6em;margin:.6em 0 .3em}h2{font-size:1.25em;margin:1.6em 0 .4em}h3{font-size:1.05em;margin:1.2em 0 .3em}
.lead{background:#eef6ff;border-left:4px solid #2f7de1;padding:10px 14px;margin:12px 0}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.card{flex:1 1 170px;background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px 12px}
.card b{display:block;font-size:1.35em}.card span{color:#666;font-size:.88em}
nav{font-size:.92em;margin-bottom:8px}nav a{margin-right:12px;white-space:nowrap}
.crumb{font-size:.88em;color:#666}
table{width:100%;border-collapse:collapse;background:#fff;margin:8px 0 20px;font-size:.95em}
caption{text-align:left;font-weight:600;padding:4px 0}
th,td{padding:7px 10px;border-bottom:1px solid #e5e5e5;text-align:left}
th{background:#f0f2f5;font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:#2f7de1;text-decoration:none}a:hover{text-decoration:underline}
pre{background:#f0f2f5;padding:10px 12px;overflow-x:auto}
footer{margin-top:32px;padding-top:12px;border-top:1px solid #ddd;color:#666;font-size:.9em}
.wrap{overflow-x:auto}
"""


# ---------- 小工具 ----------

def money(v: float) -> str:
    return f"¥{v:.4f}".rstrip("0").rstrip(".") if v < 1 else f"¥{v:.2f}".rstrip("0").rstrip(".")


def rate(v: float | None) -> str:
    return "—" if v is None else f"{v:g}"


def mid(v: float | None) -> str:
    """「多数站在 X 倍上下」用两位小数，别写成 0.249 这种假精确。"""
    return "—" if v is None else f"{round(v, 2):g}"


def approx(n: int) -> str:
    """title/description 用的取整家数：每天增减一两家不让 title 跟着变。"""
    return f"{n // 10 * 10}+" if n >= 50 else str(n)


def site_name(r: dict, linked: bool) -> str:
    name = escape(r["name"])
    if linked and r.get("slug"):
        return f'<a href="{MAIN}/p/{escape(r["slug"])}?{UTM}">{name}</a>'
    return name


def main_link(slug: str, text: str) -> str:
    return f'<a href="{MAIN}{MAIN_PAGE.get(slug, "/")}?{UTM}">{escape(text)}</a>'


def model_url(vendor_slug: str, t: dict) -> str:
    return f"{BASE}/{vendor_slug}/{t['price_slug']}/"


def cards(items: list[tuple[str, str]]) -> str:
    return '<div class="cards">' + "".join(
        f'<div class="card"><b>{v}</b><span>{escape(k)}</span></div>' for k, v in items) + "</div>"


def price_table(caption: str, rows: list[dict], linked_top: int = TOP_LINKS) -> str:
    out = [f'<div class="wrap"><table><caption>{escape(caption)}</caption><thead><tr>'
           '<th scope="col">#</th><th scope="col">中转站</th><th scope="col">倍率</th>'
           '<th scope="col">输入价</th><th scope="col">输出价</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        out.append(f'<tr><td>{i}</td><td>{site_name(r, i <= linked_top)}</td><td class="n">{rate(r["rate"])}</td>'
                   f'<td class="n">{money(r["in"])}</td><td class="n">{money(r["out"])}</td></tr>')
    out.append("</tbody></table></div>")
    return "\n".join(out)


def faq_block(qas: list[tuple[str, str]]) -> tuple[str, dict]:
    html = "<h2>常见问题</h2>" + "".join(f"<h3>{escape(q)}</h3><p>{a}</p>" for q, a in qas)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q,
         "acceptedAnswer": {"@type": "Answer", "text": _strip_tags(a)}} for q, a in qas]}
    return html, ld


def _strip_tags(s: str) -> str:
    out, inside = [], False
    for ch in s:
        if ch == "<":
            inside = True
        elif ch == ">":
            inside = False
        elif not inside:
            out.append(ch)
    return "".join(out)


def top_names(rows: list[dict], n: int = 3) -> str:
    return "、".join(f"{escape(r['name'])}（{rate(r['rate'])} 倍）" for r in rows[:n])


# ---------- 页面骨架 ----------

def page(path: str, title: str, desc: str, body: str, updated: str,
         crumbs: list[tuple[str, str]] | None = None, ld: list[dict] | None = None) -> str:
    url = f"{SITE}/{path}" if path else f"{SITE}/"
    nav = " ".join(f'<a href="{BASE}/{s}/">{escape(l)}</a>' for s, l in NAV)
    crumbs = crumbs or []
    lds = list(ld or [])
    crumb_html = ""
    if crumbs:
        chain = [("首页", f"{BASE}/")] + crumbs
        crumb_html = '<p class="crumb">' + " › ".join(
            f'<a href="{u}">{escape(n)}</a>' for n, u in chain[:-1]) + f" › {escape(chain[-1][0])}</p>"
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": "https://apiranking.github.io" + u}
            for i, (n, u) in enumerate(chain, 1)]})
    ld_html = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>\n'
                      for x in lds)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<style>{CSS}</style>
{ld_html}</head>
<body>
<nav><a href="{BASE}/">首页</a> {nav}</nav>
{crumb_html}
{body}
<footer>
<p>数据更新：{updated}。价格单位：人民币元 / 每百万 tokens，按 1 元 = 1 美元额度充值折算。</p>
<p>各站真假检测、稳定性和站方公告见 <a href="{MAIN}/?{UTM}">API Ranking</a>。</p>
</footer>
</body>
</html>
"""


# ---------- 厂商页 ----------

def vendor_body(d: dict, slug: str) -> tuple[str, str, str, list[dict]]:
    v, n = d["vendor"], d["site_count"]
    tables = d["tables"]
    head_models = "、".join(t["label"].replace("Claude ", "") for t in tables[:2])
    if slug == "claude-code":
        title = f"Claude Code 中转站推荐 {YEAR}：{approx(n)} 家价格倍率对比"
        h1 = "Claude Code 中转站价格对比"
        desc = (f"收录 {approx(n)} 家 Claude Code 中转站，对比 Sonnet、Opus 的倍率和输入/输出价，"
                f"多数站在 {mid(d['median_rate'])} 倍上下，附接入配置方法，每日更新。")
    else:
        title = f"{v} 中转站推荐 {YEAR}：{approx(n)} 家价格倍率对比，哪家便宜"
        h1 = f"{v} 中转站价格对比"
        desc = (f"收录 {approx(n)} 家 {v} 中转站，对比 {head_models} 等模型的倍率和输入/输出价，"
                f"多数站在 {mid(d['median_rate'])} 倍上下，每日更新。")

    sites = d["sites"]
    parts = [f"<h1>{escape(h1)}</h1>",
             f'<p class="lead">共 {n} 家中转站支持 {escape(v.replace(" Code", ""))}。最便宜的是 {top_names(sites)}；'
             f"多数站在 {mid(d['median_rate'])} 倍上下。综合排名见 {main_link(slug, f'API Ranking {v} 中转站排行')}。</p>",
             cards([("家中转站", str(n)), ("最低倍率", rate(d["min_rate"])),
                    ("多数站倍率", mid(d["median_rate"])), (f"{tables[0]['label']} 官方输入价", f"${tables[0]['official_in']:g}")])]

    if slug == "claude-code":
        parts.append("""<h2>Claude Code 怎么接中转站</h2>
<p>在中转站后台创建 key，然后设置两个环境变量再启动 <code>claude</code>：</p>
<pre>export ANTHROPIC_BASE_URL=https://中转站地址
export ANTHROPIC_AUTH_TOKEN=中转站的 key
claude</pre>
<p>Windows PowerShell 用 <code>$env:ANTHROPIC_BASE_URL="https://中转站地址"</code>。Claude Code 日常主要跑 Sonnet，难题切 Opus，所以下面只比这两类模型。</p>""")

    # 一站一行总表：该厂商下每站的最低倍率
    parts.append(f'<h2 id="all">{escape(v)} 中转站最低倍率总表（{n} 家）</h2>'
                 '<div class="wrap"><table><caption>按最低倍率从低到高</caption><thead><tr>'
                 '<th scope="col">#</th><th scope="col">中转站</th><th scope="col">最低倍率</th>'
                 '<th scope="col">对应模型</th></tr></thead><tbody>')
    for i, r in enumerate(sites, 1):
        parts.append(f'<tr><td>{i}</td><td>{site_name(r, i <= TOP_LINKS)}</td>'
                     f'<td class="n">{rate(r["rate"])}</td><td>{escape(r["model"])}</td></tr>')
    parts.append("</tbody></table></div>")

    # 分模型：有独立页的只列前 10 + 链接；没有独立页的列全表
    parts.append(f"<h2>按模型看 {escape(v)} 中转站价格</h2>")
    for t in tables:
        own = t["own_page"] and slug != "claude-code"
        rows = t["rows"][:TOP_PER_MODEL] if own else t["rows"]
        parts.append(f'<h3 id="{escape(t["price_slug"])}">{escape(t["label"])} 中转站价格（{len(t["rows"])} 家）</h3>'
                     f'<p>官方价：输入 ${t["official_in"]:g} / 输出 ${t["official_out"]:g} 每百万 tokens；'
                     f'多数站在 {mid(t["median_rate"])} 倍上下。</p>')
        parts.append(price_table(f"{t['label']} 中转站价格" + ("前 10" if own else ""), rows, linked_top=0))
        if own:
            parts.append(f'<p><a href="{model_url(slug, t)}">看全部 {len(t["rows"])} 家 {escape(t["label"])} 中转站价格 →</a></p>')
        elif slug == "claude-code" and t["own_page"]:
            parts.append(f'<p><a href="{model_url("claude", t)}">{escape(t["label"])} 中转站价格单页 →</a></p>')

    t0 = tables[0]
    qas = [
        (f"{v} 中转站哪家便宜？",
         f"按最低倍率，目前最便宜的是 {top_names(sites)}。多数站在 {mid(d['median_rate'])} 倍上下，"
         f"同一家站不同模型、不同分组倍率也不一样，按你要用的模型看对应表格。"),
        (f"{v} 中转站价格怎么算？",
         f"实际价格 = 官方价 × 倍率。以 {escape(t0['label'])} 为例，官方输入 ${t0['official_in']:g} / 输出 ${t0['official_out']:g} 每百万 tokens，"
         f"0.5 倍的站就是输入 {money(t0['official_in'] * 0.5)}、输出 {money(t0['official_out'] * 0.5)}。"
         f'详见 <a href="{BASE}/rate-explained/">中转站倍率怎么算</a>。'),
    ]
    if slug == "claude-code":
        qas.append(("Claude Code 能用中转站吗？",
                    "能。把 ANTHROPIC_BASE_URL 设成中转站地址、ANTHROPIC_AUTH_TOKEN 设成中转站的 key 即可，"
                    "和直连官方用法一样。"))
    else:
        qas.append((f"{v} 中转站有多少家？", f"本页收录 {n} 家支持 {escape(v)} 模型的中转站，每天更新价格。"))
    faq_html, faq_ld = faq_block(qas)
    parts.append(faq_html)
    return title, desc, "\n".join(parts), [faq_ld]


def model_body(d: dict, vendor_slug: str, t: dict) -> tuple[str, str, str, list[dict]]:
    label, rows = t["label"], t["rows"]
    n = len(rows)
    title = f"{label} 中转站推荐 {YEAR}：{approx(n)} 家价格倍率对比，哪家便宜"
    desc = (f"收录 {approx(n)} 家 {label} 中转站，按倍率从低到高排，对比输入/输出价。"
            f"官方价 ${t['official_in']:g}/${t['official_out']:g}，多数站在 {mid(t['median_rate'])} 倍上下，每日更新。")
    siblings = [x for x in d["tables"] if x["own_page"] and x["model_key"] != t["model_key"]]
    parts = [
        f"<h1>{escape(label)} 中转站价格对比</h1>",
        f'<p class="lead">共 {n} 家中转站提供 {escape(label)}。最便宜的是 {top_names(rows)}；'
        f"多数站在 {mid(t['median_rate'])} 倍上下。综合排名见 {main_link(vendor_slug, f'API Ranking {d['vendor']} 中转站排行')}。</p>",
        cards([("家中转站", str(n)), ("最低倍率", rate(rows[0]["rate"])), ("多数站倍率", mid(t["median_rate"])),
               ("官方输入/输出", f"${t['official_in']:g}/${t['official_out']:g}")]),
        price_table(f"{label} 中转站价格（按倍率从低到高）", rows),
    ]
    if siblings:
        parts.append(f"<h2>其他 {escape(d['vendor'])} 模型中转站价格</h2><p>"
                     + " · ".join(f'<a href="{model_url(vendor_slug, x)}">{escape(x["label"])}</a>' for x in siblings)
                     + f' · <a href="{BASE}/{vendor_slug}/">{escape(d["vendor"])} 全部</a></p>')
    qas = [
        (f"{label} 中转站哪家便宜？",
         f"目前最便宜的是 {top_names(rows)}。多数站在 {mid(t['median_rate'])} 倍上下。"),
        (f"{label} 中转站价格怎么算？",
         f"官方价输入 ${t['official_in']:g} / 输出 ${t['official_out']:g} 每百万 tokens，实际价格 = 官方价 × 倍率。"
         f"例如 0.5 倍的站：输入 {money(t['official_in'] * 0.5)}、输出 {money(t['official_out'] * 0.5)}。"),
        (f"哪些中转站支持 {label}？", f"本页收录 {n} 家，完整名单见上表，每天更新。"),
    ]
    faq_html, faq_ld = faq_block(qas)
    parts.append(faq_html)
    return title, desc, "\n".join(parts), [faq_ld]


# ---------- 综合页 ----------

def overview_table(fams: list[dict], rows: list[dict], numbered: bool, linked_top: int = 0) -> str:
    head = "".join(f'<th scope="col">{escape(f["label"])}</th>' for f in fams)
    out = ['<div class="wrap"><table><thead><tr>' + ('<th scope="col">#</th>' if numbered else "")
           + f'<th scope="col">中转站</th>{head}</tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        cells = "".join(f'<td class="n">{rate(r["rates"].get(f["key"]))}</td>' for f in fams)
        out.append("<tr>" + (f"<td>{i}</td>" if numbered else "")
                   + f"<td>{site_name(r, i <= linked_top)}</td>{cells}</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def vendor_links() -> str:
    return " · ".join(f'<a href="{BASE}/{s}/">{l} 中转站</a>' for s, l in NAV[3:9])


def ai_body(d: dict, vendors: dict) -> tuple[str, str, str, list[dict]]:
    n = d["site_count"]
    title = f"AI 中转站推荐 {YEAR}：{approx(n)} 家价格倍率一表看完"
    desc = f"收录 {approx(n)} 家 AI 中转站，一表对比 Claude、GPT、Gemini、Grok、DeepSeek 各家最低倍率，每日更新。"
    full = sum(1 for r in d["rows"] if len(r["rates"]) == len(d["families"]))
    body = (f"<h1>AI 中转站大全：价格倍率对比</h1>"
            f'<p class="lead">共 {n} 家 AI 中转站，其中 {full} 家五大厂商模型全都有。每格是该站这个厂商模型的最低倍率'
            "（官方价的几倍），越小越便宜；“—”表示没有。支持厂商多的排前面。</p>"
            + cards([(f"家支持 {vendors[s]['vendor']}", str(vendors[s]["site_count"])) for s in ("claude", "gpt", "gemini", "grok", "deepseek")])
            + overview_table(d["families"], d["rows"], numbered=False)
            + f"<p>按模型看具体价格：{vendor_links()}</p>")
    return title, desc, body, []


def api_body(d: dict) -> tuple[str, str, str, list[dict]]:
    title = f"API 中转站推荐 {YEAR}：Claude、GPT、Gemini 最便宜前 10"
    desc = f"从 {approx(d['site_count'])} 家 API 中转站里挑出 Claude、GPT、Gemini、Grok、DeepSeek 各自倍率最低的 10 家，每日更新。"
    parts = [f"<h1>API 中转站哪家便宜：各厂商最低倍率前 10</h1>",
             f'<p class="lead">从 {d["site_count"]} 家 API 中转站里，按厂商挑出倍率最低的 10 家。倍率 = 官方价的几倍，越小越便宜。</p>']
    for f in d["families"]:
        parts.append(f'<h2>{escape(f["label"])} API 中转站最便宜前 10（共 {f["count"]} 家）</h2>'
                     f'<table><caption>{escape(f["label"])} 最低倍率前 10</caption><thead><tr><th scope="col">#</th>'
                     '<th scope="col">中转站</th><th scope="col">最低倍率</th></tr></thead><tbody>')
        for i, r in enumerate(f["rows"], 1):
            parts.append(f'<tr><td>{i}</td><td>{site_name(r, i <= 3)}</td><td class="n">{rate(r["rate"])}</td></tr>')
        parts.append(f'</tbody></table><p><a href="{BASE}/{FAMILY_SLUG[f["key"]]}/">看全部 {f["count"]} 家 '
                     f'{escape(f["label"])} 中转站价格 →</a></p>')
    return title, desc, "\n".join(parts), []


def recommend_body(d: dict) -> tuple[str, str, str, list[dict]]:
    n = len(d["rows"])
    title = f"中转站推荐 {YEAR}：{n} 家靠谱 API 中转站价格对比"
    desc = f"API Ranking 综合排名前 {n} 的 AI API 中转站，附 Claude、GPT、Gemini、Grok、DeepSeek 最低倍率，每日更新。"
    body = (f"<h1>中转站推荐：综合排名前 {n} 家</h1>"
            f'<p class="lead">按 API Ranking 综合排名取前 {n} 家，第一名是 {escape(d["rows"][0]["name"])}。'
            f"每格是该厂商模型的最低倍率，越小越便宜。完整排名见 {main_link('', 'API Ranking')}。</p>"
            + overview_table(d["families"], d["rows"], numbered=True, linked_top=10)
            + f"<p>只看价格：{vendor_links()}</p>")
    return title, desc, body, []


def rate_body(official: list[dict]) -> tuple[str, str, str, list[dict]]:
    title = f"中转站倍率怎么算？{YEAR} 价格换算方法与各模型价格表"
    desc = "中转站倍率是什么、怎么换算成人民币价格，附 Claude、GPT、Gemini 等主流模型 0.3/0.5/1 倍价格对照表。"
    ex = next((o for o in official if o["family"] == "claude" and "Sonnet" in o["label"]), official[0])
    a, b = 0.5, 1.2
    rows = "".join(
        f'<tr><td>{escape(o["label"])}</td><td class="n">${o["in"]:g} / ${o["out"]:g}</td>'
        + "".join(f'<td class="n">{money(o["in"] * k)} / {money(o["out"] * k)}</td>' for k in (0.3, 0.5, 1))
        + "</tr>"
        for o in official
    )
    qas = [
        ("中转站倍率是什么意思？", "倍率 = 中转站价格 ÷ 官方价格。0.5 倍就是官方价的一半，1 倍等于官方价，数字越小越便宜。"),
        ("倍率怎么换算成人民币？",
         f"多数中转站 1 元充 1 美元额度，所以每百万 tokens 花费（元）= 官方美元价 × 倍率。"
         f"例如 {escape(ex['label'])} 官方输入 ${ex['in']:g}，0.5 倍的站就是 {money(ex['in'] * a)}。"),
        ("倍率越低越好吗？", "倍率低单价就低，但同一家站不同分组、不同模型倍率不一样，缓存计费也会影响账单，先小额充值试用最稳。"),
    ]
    faq_html, faq_ld = faq_block(qas)
    body = f"""<h1>中转站倍率怎么算</h1>
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
<div class="wrap"><table><caption>单位：每百万 tokens，输入 / 输出</caption><thead><tr><th scope="col">模型</th><th scope="col">官方价</th>
<th scope="col">0.3 倍</th><th scope="col">0.5 倍</th><th scope="col">1 倍</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<h2>各模型中转站价格</h2>
<p>{vendor_links()}</p>
{faq_html}
"""
    return title, desc, body, [faq_ld]


def index_body(pages: dict) -> tuple[str, str, str, list[dict]]:
    title = f"AI API 中转站推荐 {YEAR}：Claude、GPT、Gemini 价格倍率对比"
    desc = (f"收录 {approx(pages['ai']['site_count'])} 家 AI API 中转站，按模型对比 Claude、GPT、Gemini、Grok、DeepSeek "
            "的倍率和输入/输出价，每日更新。")
    parts = ["<h1>AI API 中转站价格对比</h1>",
             f'<p class="lead">收录 {pages["ai"]["site_count"]} 家 AI API 中转站，按模型分好、按价格排好。'
             f'先看 <a href="{BASE}/ai/">全部中转站总表</a>，或直接选你要用的模型。</p>',
             '<div class="wrap"><table><caption>各厂商中转站一览</caption><thead><tr><th scope="col">模型</th>'
             '<th scope="col">中转站数</th><th scope="col">多数站倍率</th><th scope="col">最便宜的 3 家</th></tr></thead><tbody>']
    for s in VENDOR_SLUGS:
        d = pages[s]
        parts.append(f'<tr><td><a href="{BASE}/{s}/">{escape(d["vendor"])} 中转站</a></td><td class="n">{d["site_count"]}</td>'
                     f'<td class="n">{mid(d["median_rate"])}</td><td>{top_names(d["sites"])}</td></tr>')
    parts.append("</tbody></table></div>")
    models = [(s, t) for s in ("claude", "gpt", "gemini") for t in pages[s]["tables"] if t["own_page"]]
    parts.append("<h2>热门模型中转站价格</h2><p>"
                 + " · ".join(f'<a href="{model_url(s, t)}">{escape(t["label"])} 中转站</a>' for s, t in models) + "</p>")
    parts.append(f'<h2>更多</h2><ul><li><a href="{BASE}/api/">API 中转站哪家便宜：各厂商前 10</a></li>'
                 f'<li><a href="{BASE}/recommend/">中转站推荐：综合排名前 30</a></li>'
                 f'<li><a href="{BASE}/rate-explained/">中转站倍率怎么算</a></li></ul>')
    return title, desc, "\n".join(parts), []


# ---------- 输出 ----------

def write(path: str, html: str) -> None:
    d = DOCS / path if path else DOCS
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")


def redirect_stub(path: str, target: str) -> str:
    url = f"{SITE}/{target}"
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="robots" content="noindex,follow"><link rel="canonical" href="{url}">'
            f'<meta http-equiv="refresh" content="0; url={BASE}/{target}"><title>已合并</title></head>'
            f'<body><p>本页已合并到 <a href="{BASE}/{target}">这里</a>。</p></body></html>')


def main() -> None:
    # 型号页随数据自动增减：先记下旧的型号页目录，整份 docs 重建，
    # 掉出门槛/下架的型号写跳转桩（指回厂商页），旧链接不 404
    old_models = {str(d.relative_to(DOCS)) for v in VENDOR_SLUGS if (DOCS / v).is_dir()
                  for d in (DOCS / v).iterdir() if d.is_dir()}
    if DOCS.exists():
        shutil.rmtree(DOCS)
    pages = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in DATA.glob("*.json") if p.stem != "official"}
    official = json.loads((DATA / "official.json").read_text(encoding="utf-8"))
    latest = max(d["updated"] for d in pages.values())
    nav_label = dict(NAV)
    out: list[tuple[str, str]] = []  # (path, lastmod)

    def emit(path, built, updated, crumbs=None):
        title, desc, body, ld = built
        write(path, page(path, title, desc, body, updated, crumbs, ld))
        out.append((path, updated))

    for slug in VENDOR_SLUGS:
        d = pages[slug]
        emit(f"{slug}/", vendor_body(d, slug), d["updated"], [(f"{nav_label[slug]} 中转站", f"{BASE}/{slug}/")])
        if slug == "claude-code":
            continue
        for t in d["tables"]:
            if t["own_page"]:
                path = f"{slug}/{t['price_slug']}/"
                emit(path, model_body(d, slug, t), d["updated"],
                     [(f"{nav_label[slug]} 中转站", f"{BASE}/{slug}/"), (t["label"], f"{BASE}/{path}")])
    emit("ai/", ai_body(pages["ai"], pages), pages["ai"]["updated"], [("AI 中转站", f"{BASE}/ai/")])
    emit("api/", api_body(pages["api"]), pages["api"]["updated"], [("API 中转站", f"{BASE}/api/")])
    emit("recommend/", recommend_body(pages["recommend"]), pages["recommend"]["updated"],
         [("中转站推荐", f"{BASE}/recommend/")])
    emit("rate-explained/", rate_body(official), latest, [("倍率怎么算", f"{BASE}/rate-explained/")])
    emit("", index_body(pages), latest)

    built = {p.rstrip("/") for p, _ in out}
    for gone in sorted(old_models - built):
        write(gone + "/", redirect_stub(gone, gone.split("/")[0] + "/"))
        print(f"型号页下线 → 跳转桩：{gone}")

    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{SITE}/{p}</loc><lastmod>{u}</lastmod></url>\n" for p, u in out)
        + "</urlset>\n", encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"生成 {len(out)} 页 → {DOCS}")


if __name__ == "__main__":
    main()
