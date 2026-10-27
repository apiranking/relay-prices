#!/usr/bin/env python3
"""从 data/*.json 生成 GitHub Pages 静态页到 docs/。

纯标准库，本地直接跑：
  python3 scripts/generate_pages.py
"""
from __future__ import annotations

import json
import re
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
# IndexNow key：key 文件放在 /relay-prices/ 下，只能提交本路径下的 URL（每日脚本推送后提交）
INDEXNOW_KEY = "ef63afa7fff4fbac9097d652b448074c"

NAV = [
    ("ai", "AI 中转站"), ("api", "API 中转站"), ("recommend", "中转站推荐"),
    ("claude", "Claude"), ("claude-code", "Claude Code"), ("gpt", "GPT"), ("codex", "Codex"),
    ("gemini", "Gemini"), ("grok", "Grok"), ("deepseek", "DeepSeek"),
    ("jiangzhi", "降智怎么测"), ("rate-explained", "倍率怎么算"),
]
VENDOR_SLUGS = ["claude", "claude-code", "gpt", "codex", "gemini", "grok", "deepseek"]
# 客户端专题页：型号表挂在父厂商页下，不单出型号页
CLIENT_PARENT = {"claude-code": "claude", "codex": "gpt"}
FAMILY_SLUG = {"claude": "claude", "openai": "gpt", "gemini": "gemini", "grok": "grok", "deepseek": "deepseek"}
# 页面 slug → 主站对应排行页
MAIN_PAGE = {
    "claude": "/rankings/claude-api", "claude-code": "/rankings/claude-api",
    "gpt": "/rankings/gpt-api", "codex": "/rankings/codex-api", "gemini": "/rankings/gemini-api",
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
ol.rank{list-style:none;padding:0;margin:12px 0}
ol.rank>li{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:10px 14px;margin:0 0 10px}
.rk-h{font-size:1.08em;font-weight:600}.rk-h .no{display:inline-block;min-width:1.8em;color:#888}
.tg{display:inline-block;font-size:.8em;font-weight:500;padding:1px 7px;border-radius:10px;margin-left:6px;background:#eef0f3;color:#555}
.tg.ok{background:#e6f6ec;color:#17803d}.tg.warn{background:#fff4e0;color:#a35b00}.tg.bad{background:#fde8e8;color:#b42318}
.rk ul{margin:6px 0 4px;padding-left:1.2em}.rk li{margin:2px 0}
.more{font-size:.92em}.upd{color:#666;font-size:.9em;margin:-.2em 0 .6em}
.pel{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:12px 0}
.pel figure{margin:0;background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:8px}
.pel img{width:100%;aspect-ratio:1/1;object-fit:contain;background:#fff}.pel figcaption{font-size:.92em;margin-top:4px}
details{margin:14px 0}summary{cursor:pointer;font-weight:600;padding:6px 0}
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


def alias(label: str) -> str:
    """型号连写词形（搜索常见写法）：Claude Opus 5.5 → opus5.5，GPT-6 Astra → gpt6 astra。"""
    s = label.lower().replace("claude ", "").replace("-", "")
    return re.sub(r"(?<=[a-z]) (?=\d)", "", s)


def current_links(slug: str, tables: list[dict]) -> str:
    """现役型号单页直达（锚文本用连写词形）。"""
    cur = [t for t in tables if t.get("current") and t["own_page"]]
    if not cur:
        return ""
    return ("<p>现役型号直达：" + " · ".join(
        f'<a href="{model_url(slug, t)}">{escape(alias(t["label"]))}中转站</a>' for t in cur) + "</p>")


def top_names_plain(rows: list[dict], n: int = 3) -> str:
    return "、".join(escape(r["name"]) for r in rows[:n])


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
{body.replace("</h1>", f'</h1><p class="upd">更新于 {updated}</p>', 1)}
<footer>
<p>数据更新：{updated}。价格单位：人民币元 / 每百万 tokens，按 1 元 = 1 美元额度充值折算。</p>
<p>各站真假检测、稳定性和站方公告见 <a href="{MAIN}/?{UTM}">API Ranking</a>。</p>
</footer>
</body>
</html>
"""


# ---------- 厂商页 ----------

def times(r: float) -> str:
    """倍率换成访客读得懂的话：低于官方价说几折，高于说几倍。"""
    if 0.99 <= r <= 1.01:
        return "和官方价持平"
    if r < 1:
        z = round(r * 10, 1)
        return f"官方价 {z:g} 折"
    return f"官方价 {round(r, 2):g} 倍"


def site_url(slug: str) -> str:
    return f"{MAIN}/p/{escape(slug)}?{UTM}"


TONE = {"good": "ok", "info": "ok", "warn": "warn", "bad": "bad"}


def cheapest(cards: list[dict]) -> tuple[str, dict] | None:
    """推荐站里最便宜的（并列的一起列出）：返回（站名串, 价格）。"""
    priced = [c for c in cards if c.get("price")]
    if not priced:
        return None
    low = min(c["price"]["in"] for c in priced)
    tied = [c for c in priced if abs(c["price"]["in"] - low) < 1e-9]
    names = "、".join(escape(c["name"]) for c in tied)
    return (f"{names} {len(tied)} 家并列" if len(tied) > 1 else names), tied[0]["price"]


def cheap_phrase(cards: list[dict], flag: str) -> str:
    hit = cheapest(cards)
    if not hit:
        return ""
    who, pr = hit
    return (f"推荐站里 {flag} 最便宜的是 {who}，输入 ¥{pr['in']:.2f} / 百万 tokens"
            f"（{times(pr['rate'])}）。")


def rank_card(i: int, c: dict, flagship: str, show_bench: bool = True) -> str:
    name = escape(c["name"])
    head = f'<a href="{site_url(c["slug"])}">{name}</a>' if c.get("slug") else name
    tags = ""
    if c.get("water"):
        tone = "ok" if c["water"] == "模型为真" else ("warn" if c["water"] == "真假存疑" else "bad")
        tags += f'<span class="tg {tone}">{"✓ " if tone == "ok" else ""}{escape(c["water"])}</span>'
    facts = []
    if c.get("price"):
        pr = c["price"]
        facts.append(f"{escape(flagship)}：输入 ¥{pr['in']:.2f} / 输出 ¥{pr['out']:.2f} 每百万 tokens，"
                     f"{times(pr['rate'])}")
    b = c.get("bench") if show_bench else None
    if b:
        bits = [f'<span class="tg {TONE.get(b["billing_color"], "")}">扣费{escape(b["billing"].removeprefix("扣费"))}</span>']
        if b.get("cache"):
            bits.append(f'<span class="tg {TONE.get(b["cache_color"], "")}">{escape(b["cache"])}</span>')
        if b.get("wait_s") is not None:
            bits.append(f'<span class="tg">首字约 {b["wait_s"]:g} 秒</span>')
        facts.append(f"真付费实测（{escape(b['model'])}）：" + "".join(bits))
    biz = []
    if c.get("min_topup"):
        biz.append(f"起充 {escape(c['min_topup'])}")
    if c.get("bonus") and c["bonus"] not in ("$0", "¥0", "0"):
        biz.append(f"赠送 {escape(c['bonus'])}")
    if c.get("invoice") == "yes":
        biz.append("可开票")
    elif c.get("invoice") == "no":
        biz.append("不开票")
    if c.get("refund"):
        biz.append(f"退款{escape(c['refund'])}")
    if biz:
        facts.append(" · ".join(biz))
    if c.get("anomaly"):
        facts.append(f'<span class="tg warn">{escape(c["anomaly"])}</span>')
    more = (f'<div class="more"><a href="{site_url(c["slug"])}">看 {name} 的用户评价、实测明细和优惠 →</a></div>'
            if c.get("slug") else "")
    return (f'<li class="rk"><div class="rk-h"><span class="no">{i}</span>{head}{tags}</div>'
            f'<ul>{"".join(f"<li>{f}</li>" for f in facts)}</ul>{more}</li>')


def ranking_block(d: dict, slug: str, v: str) -> str:
    rk = d.get("ranking") or []
    top = [c for c in rk if c["tier"] in ("S", "A")]
    rest = [c for c in rk if c["tier"] == "B"]
    if not top:
        return ""
    flag = d.get("flagship") or ""
    out = [f'<h2 id="ranking">{escape(v)} 中转站排行榜（推荐 {len(top)} 家）</h2>',
           f'<p>排序与 {main_link(slug, f"API Ranking {v.replace(" Code", "")} 排行榜")} 一致。'
           f"价格按现役 {escape(flag)} 算，点站名看这家站的完整信息。</p>",
           '<ol class="rank">' + "".join(rank_card(i, c, flag) for i, c in enumerate(top, 1)) + "</ol>"]
    if rest:
        out.append(f"<h3>其他收录站（{escape(flag)} 价格）</h3>"
                   '<div class="wrap"><table><thead><tr><th scope="col">中转站</th><th scope="col">输入价</th>'
                   '<th scope="col">输出价</th><th scope="col">相当于</th></tr></thead><tbody>')
        for c in rest:
            pr = c["price"]
            out.append(f'<tr><td>{site_name(c, True)}</td><td class="n">¥{pr["in"]:.2f}</td>'
                       f'<td class="n">¥{pr["out"]:.2f}</td><td>{times(pr["rate"])}</td></tr>')
        out.append("</tbody></table></div>"
                   "<p>这些站还没进推荐档：没做真假检测或实测，只能看价格，选之前先自己小额试用。</p>")
    return "\n".join(out)


def summary_lead(d: dict, v: str) -> str:
    """首屏结论：推荐前几名 + 各自最突出的一点 + 最便宜的推荐站。"""
    top = [c for c in (d.get("ranking") or []) if c["tier"] in ("S", "A")]
    if not top:
        return ""
    flag = escape(d.get("flagship") or "")
    names = "、".join(escape(c["name"]) for c in top[:3])
    benched = [c for c in top if c.get("bench") and c["bench"]["billing_color"] in ("good", "info")]
    s = f"想省心直接选排行榜前三：{names}。"
    if benched:
        s += (f"这 {len(top)} 家都由我们自己掏钱实测过，扣费和标价对得上。" if len(benched) == len(top)
              else f"推荐的 {len(top)} 家里有 {len(benched)} 家我们自己掏钱实测过，扣费和标价对得上。")
    s += cheap_phrase(top, flag)
    return f'<p class="lead">{s}</p>'


HOW_TO_PICK = """<h2>怎么选 {v} 中转站</h2>
<ol>
<li><b>先看真假。</b>标「模型为真」的站，调用到的才是真 {v}；便宜但掺了别的模型，用起来更亏。</li>
<li><b>再看扣费和缓存。</b>同样的标价，扣费偷偷多算、缓存不命中，实际花的钱能差一大截。带「真付费实测」的站这两项我们自己验过。</li>
<li><b>最后比价格。</b>前两项都过了，剩下的差别基本就是价格，按你常用的型号挑便宜的。</li>
<li><b>先小额充值试用。</b>起充低、退款无手续费的站，试错成本最低。</li>
</ol>"""


def vendor_body(d: dict, slug: str) -> tuple[str, str, str, list[dict]]:
    v, n = d["vendor"], d["site_count"]
    tables = d["tables"]
    head_models = "、".join(t["label"].replace("Claude ", "") for t in tables[:2])
    bench = d.get("bench") or []
    if slug == "claude-code":
        title = (f"Claude Code 中转站推荐排行榜 {YEAR}：真付费实测 + {approx(n)} 家价格对比" if bench
                 else f"Claude Code 中转站推荐 {YEAR}：{approx(n)} 家价格倍率对比")
        h1 = "Claude Code 中转站推荐排行榜"
        desc = (f"Claude Code 中转站 {YEAR} 对比：{head_models} 现役型号，收录 {approx(n)} 家价格倍率，"
                + (f"{len(bench)} 家真付费实测缓存命中、扣费和标价对得上，" if bench else "")
                + "附接入配置方法，每日更新。")
    elif slug == "codex":
        title = f"Codex 中转站推荐排行榜 {YEAR}：真付费实测 + {approx(n)} 家价格对比"
        h1 = "Codex 中转站推荐排行榜"
        desc = (f"Codex 中转站 {YEAR} 推荐：用 Codex 真实付费实测扣费和缓存，{head_models} 现役型号，"
                f"收录 {approx(n)} 家价格倍率，附 Codex 接入中转站配置方法，每日更新。")
    elif slug == "claude" and bench:
        title = f"Claude 中转站推荐排行榜 {YEAR}：{approx(n)} 家价格对比 + 真付费实测"
        h1 = "Claude 中转站推荐排行榜"
        desc = (f"收录 {approx(n)} 家 Claude 中转站，按现役 {head_models} 等模型对比倍率和输入/输出价，"
                f"多数站在 {mid(d['median_rate'])} 倍上下；{len(bench)} 家 Claude Code 真付费实测缓存和扣费合格，每日更新。")
    else:
        title = f"{v} 中转站推荐排行榜 {YEAR}：{approx(n)} 家价格倍率对比，哪家便宜"
        h1 = f"{v} 中转站推荐排行榜"
        desc = (f"收录 {approx(n)} 家 {v} 中转站，对比 {head_models} 等模型的倍率和输入/输出价，"
                f"多数站在 {mid(d['median_rate'])} 倍上下，每日更新。")

    sites = d["sites"]
    lead = summary_lead(d, v) or (
        f'<p class="lead">共 {n} 家中转站支持 {escape(v.replace(" Code", ""))}。最便宜的是 {top_names(sites)}；'
        f"多数站在 {mid(d['median_rate'])} 倍上下。</p>")
    parts = [f"<h1>{escape(h1)}</h1>", lead, ranking_block(d, slug, v)]
    if slug == "claude":
        parts.append(f'<p>用 Claude Code？看 <a href="{BASE}/claude-code/">Claude Code 中转站推荐排行榜</a>。</p>')
    if slug == "gpt":
        parts.append(f'<p>用 Codex？看 <a href="{BASE}/codex/">Codex 中转站推荐排行榜</a>。</p>')
    if bench:
        parts.append(f'<p>实测方法和每家的逐轮扣费明细见 <a href="{MAIN}/benchmark?{UTM}">API Ranking 真付费实测</a>。</p>')
    parts.append(HOW_TO_PICK.format(v=escape({"claude-code": "Claude", "codex": "GPT"}.get(slug, v))))

    if slug == "claude-code":
        parts.append(f'<p>想看全部 Claude 型号（含 Fable、Haiku）？看 <a href="{BASE}/claude/">Claude 中转站推荐排行榜</a>。</p>')
        parts.append("""<h2>Claude Code 怎么接中转站</h2>
<p>在中转站后台创建 key，然后设置两个环境变量再启动 <code>claude</code>：</p>
<pre>export ANTHROPIC_BASE_URL=https://中转站地址
export ANTHROPIC_AUTH_TOKEN=中转站的 key
claude</pre>
<p>Windows PowerShell 用 <code>$env:ANTHROPIC_BASE_URL="https://中转站地址"</code>。Claude Code 日常主要跑 Sonnet，难题切 Opus，所以下面只比这两款现役型号。</p>""")
    if slug == "codex":
        parts.append(f'<p>想看全部 GPT 型号？看 <a href="{BASE}/gpt/">GPT 中转站推荐排行榜</a>。</p>')
        parts.append("""<h2>Codex 怎么接中转站</h2>
<p>在中转站后台创建 key，然后编辑 <code>~/.codex/config.toml</code>（Windows 在 <code>%USERPROFILE%\\.codex\\config.toml</code>）：</p>
<pre>model = "站里给你用的模型名"
model_provider = "relay"

[model_providers.relay]
name = "relay"
base_url = "https://中转站地址/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"</pre>
<p>再 <code>export OPENAI_API_KEY="中转站的 key"</code> 启动 <code>codex</code>。地址末尾的 <code>/v1</code> 别漏，漏了会请求到站点网页上。下面只比 Codex 常用的现役型号。</p>""")

    parts.append(f"<h2>{escape(v)} 全部中转站价格（{n} 家）</h2>"
                 + cards([("家中转站", str(n)), ("最低倍率", rate(d["min_rate"])),
                          ("多数站倍率", mid(d["median_rate"])),
                          (f"{tables[0]['label']} 官方输入价", f"${tables[0]['official_in']:g}")]))
    if slug not in CLIENT_PARENT:
        parts.append(current_links(slug, tables))
    parts.append(f'<details><summary>展开：{escape(v)} 中转站最低倍率总表</summary>')
    # 一站一行总表：该厂商下每站的最低倍率
    parts.append('<div class="wrap" id="all"><table><caption>按最低倍率从低到高</caption><thead><tr>'
                 '<th scope="col">#</th><th scope="col">中转站</th><th scope="col">最低倍率</th>'
                 '<th scope="col">对应模型</th></tr></thead><tbody>')
    for i, r in enumerate(sites, 1):
        parts.append(f'<tr><td>{i}</td><td>{site_name(r, i <= TOP_LINKS)}</td>'
                     f'<td class="n">{rate(r["rate"])}</td><td>{escape(r["model"])}</td></tr>')
    parts.append("</tbody></table></div>")

    # 分模型：有独立页的只列前 10 + 链接；没有独立页的列全表
    parts.append(f"</details><details><summary>展开：按模型看 {escape(v)} 中转站价格</summary>")
    for t in tables:
        own = t["own_page"] and slug not in CLIENT_PARENT
        rows = t["rows"][:TOP_PER_MODEL] if own else t["rows"]
        parts.append(f'<h3 id="{escape(t["price_slug"])}">{escape(t["label"])} 中转站价格（{len(t["rows"])} 家）</h3>'
                     f'<p>官方价：输入 ${t["official_in"]:g} / 输出 ${t["official_out"]:g} 每百万 tokens；'
                     f'多数站在 {mid(t["median_rate"])} 倍上下。</p>')
        parts.append(price_table(f"{t['label']} 中转站价格" + ("前 10" if own else ""), rows, linked_top=0))
        if own:
            parts.append(f'<p><a href="{model_url(slug, t)}">看全部 {len(t["rows"])} 家 {escape(t["label"])} 中转站价格 →</a></p>')
        elif slug in CLIENT_PARENT and t["own_page"]:
            parts.append(f'<p><a href="{model_url(CLIENT_PARENT[slug], t)}">{escape(t["label"])} 中转站价格单页 →</a></p>')
    parts.append("</details>")

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
        if bench:
            qas.append(("claudecode中转站哪家好？",
                        f"价格看上面的倍率表；缓存和扣费靠不靠谱，看真付费实测：{top_names_plain(bench)} 等 {len(bench)} 家"
                        "缓存都能正常命中、扣费和标价对得上。"))
    elif slug == "codex":
        qas.append(("Codex 能用中转站吗？",
                    "能。在 ~/.codex/config.toml 里加一个自定义提供方，base_url 填中转站地址（带 /v1）、"
                    "wire_api 设成 responses，key 放环境变量即可。"))
        top = [c for c in d.get("ranking") or [] if c["tier"] in ("S", "A")]
        if top:
            qas.append(("codex中转站哪家好？",
                        f"先看排行榜前几名：{top_names_plain(top)}。这些站真假检测都过了，"
                        "带「真付费实测」的我们用 Codex 自己掏钱跑过，扣费和标价对得上。"))
    else:
        qas.append((f"{v} 中转站有多少家？", f"本页收录 {n} 家支持 {escape(v)} 模型的中转站，每天更新价格。"))
    faq_html, faq_ld = faq_block(qas)
    parts.append(faq_html)
    return title, desc, "\n".join(parts), [faq_ld]


def model_body(d: dict, vendor_slug: str, t: dict) -> tuple[str, str, str, list[dict]]:
    label, rows = t["label"], t["rows"]
    n = len(rows)
    al = alias(label)
    title = f"{label} 中转站推荐 {YEAR}：{approx(n)} 家价格倍率对比，{al} 哪家便宜"
    desc = (f"{al}中转站：收录 {approx(n)} 家 {label} 中转站，按倍率从低到高排，对比输入/输出价。"
            f"官方价 ${t['official_in']:g}/${t['official_out']:g}，多数站在 {mid(t['median_rate'])} 倍上下，每日更新。")
    siblings = [x for x in d["tables"] if x["own_page"] and x["model_key"] != t["model_key"]]
    by_name = {r["name"]: r for r in rows}
    rec = []  # 推荐站（S/A，主站排序）里提供这个型号的，价格换成这个型号的
    for c in d.get("ranking") or []:
        r = by_name.get(c["name"])
        if c["tier"] in ("S", "A") and r:
            rec.append(dict(c, price={"in": r["in"], "out": r["out"], "rate": r["rate"]}))
    if rec:
        lead = (f'<p class="lead">{escape(label)} 想省心就从推荐站里挑：{"、".join(escape(c["name"]) for c in rec[:3])}。'
                f"{cheap_phrase(rec, escape(label))}只看价格，全部 {n} 家在下面的表里。</p>")
    else:
        lead = (f'<p class="lead">共 {n} 家中转站提供 {escape(label)}。最便宜的是 {top_names(rows)}；'
                f"多数站在 {mid(t['median_rate'])} 倍上下。</p>")
    parts = [f"<h1>{escape(label)} 中转站价格对比</h1>", lead]
    if rec:
        parts.append(f'<h2 id="ranking">{escape(label)} 推荐中转站（{len(rec)} 家）</h2>'
                     f"<p>排序与 {main_link(vendor_slug, f'API Ranking {d['vendor']} 排行榜')} 一致，点站名看这家站的完整信息。</p>"
                     '<ol class="rank">' + "".join(rank_card(i, c, label, show_bench=False) for i, c in enumerate(rec, 1)) + "</ol>")
    parts += [
        f"<h2>{escape(label)} 全部中转站价格（{n} 家）</h2>",
        cards([("家中转站", str(n)), ("最低倍率", rate(rows[0]["rate"])), ("多数站倍率", mid(t["median_rate"])),
               ("官方输入/输出", f"${t['official_in']:g}/${t['official_out']:g}")]),
        price_table(f"{label} 中转站价格（按倍率从低到高）", rows),
        "<p>表里没进推荐的站还没做真假检测或实测，只能看价格，选之前先自己小额试用。</p>",
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
    return " · ".join(f'<a href="{BASE}/{s}/">{l} 中转站</a>' for s, l in NAV if s in VENDOR_SLUGS)


def ai_body(d: dict, vendors: dict) -> tuple[str, str, str, list[dict]]:
    n = d["site_count"]
    title = f"AI 中转站推荐排行榜 {YEAR}：{approx(n)} 家价格倍率一表看完"
    desc = (f"AI 中转站排行榜：推荐站逐家看真假、起充、开票、退款，"
            f"收录 {approx(n)} 家对比 Claude、GPT、Gemini、Grok、DeepSeek 最低倍率，每日更新。")
    rates = {r["name"]: r["rates"] for r in d["rows"]}
    fams = d["families"]
    top = [c for c in d.get("ranking") or [] if c["tier"] in ("S", "A")]
    for c in top:  # 综合榜没有单一旗舰型号：价格行换成「各厂商最低倍率」
        r = rates.get(c["name"]) or {}
        c["price"] = None
        c["vendors"] = " · ".join(f"{escape(f['label'])} {times(r[f['key']]).replace('官方价 ', '').replace('和官方价持平', '原价')}"
                                  for f in fams if f["key"] in r)
    full = sum(1 for r in d["rows"] if len(r["rates"]) == len(fams))
    chips = " · ".join(f'<a href="{BASE}/{s}/">{escape(vendors[s]["vendor"])} 排行榜（{vendors[s]["site_count"]} 家）</a>'
                       for s in ("claude", "gpt", "gemini", "grok", "deepseek"))
    names = "、".join(escape(c["name"]) for c in top[:3])
    body = [f"<h1>AI 中转站推荐排行榜</h1>",
            f'<p class="lead">不知道选哪家，直接从排行榜前三里挑：{names}。'
            f"这几家主流模型都能用、真假检测都过了。只用某一家模型的，看对应厂商的排行榜更准。</p>",
            f"<p>按厂商看：{chips}</p>"]
    if top:
        items = []
        for i, c in enumerate(top, 1):
            card = rank_card(i, c, "")
            if c["vendors"]:
                card = card.replace("<ul>", f"<ul><li>各厂商最低价（相对官方价）：{c['vendors']}</li>", 1)
            items.append(card)
        body.append(f'<h2 id="ranking">AI 中转站排行榜（推荐 {len(top)} 家）</h2>'
                    f'<p>排序与 <a href="{MAIN}/?{UTM}">API Ranking 首页排行榜</a> 一致，点站名看这家站的完整信息。</p>'
                    '<ol class="rank">' + "".join(items) + "</ol>")
    body.append(HOW_TO_PICK.format(v="AI 模型").replace("真 AI 模型", "官方原版模型"))
    body.append(f"<h2>全部 {n} 家 AI 中转站倍率</h2>"
                f"<p>其中 {full} 家五大厂商模型全都有。每格是该站这个厂商模型的最低倍率（官方价的几倍），越小越便宜；“—”表示没有。</p>"
                + cards([(f"家支持 {vendors[s]['vendor']}", str(vendors[s]["site_count"])) for s in ("claude", "gpt", "gemini", "grok", "deepseek")])
                + "<details><summary>展开：全部中转站 × 五大厂商倍率总表</summary>"
                + overview_table(fams, d["rows"], numbered=False) + "</details>")
    return title, desc, "\n".join(body), []


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


def _picks(cards: list[dict], flag: str | None, k: int = 3) -> str:
    return "".join(rank_card(i, c, flag or "") for i, c in enumerate(cards[:k], 1))


def recommend_body(d: dict, pages: dict) -> tuple[str, str, str, list[dict]]:
    n = len(d["rows"])
    title = f"中转站推荐 {YEAR}：{n} 家靠谱 API 中转站价格对比"
    desc = (f"中转站推荐：写代码用 Claude Code、Codex 选哪家，预算有限选哪家，要开票选哪家，"
            f"按需求直接给答案；附 API Ranking 综合排名前 {n} 家价格倍率，每日更新。")

    def top(slug):
        return [c for c in pages[slug].get("ranking") or [] if c["tier"] in ("S", "A")]

    cl, gp = top("claude"), top("gpt")
    cflag, gflag = pages["claude"].get("flagship"), pages["gpt"].get("flagship")
    cheap = sorted((c for c in cl if c.get("price")), key=lambda c: c["price"]["rate"])
    trial = [c for c in cl if (c.get("min_topup") or "").replace(" ", "") in ("¥1", "1元", "￥1")
             and "无手续费" in (c.get("refund") or "")]
    inv = [c for c in cl if c.get("invoice") == "yes"]
    sec = []
    if cl:
        sec.append(("写代码用 Claude Code", f"Claude 排行榜前三，真假检测都过了：{'、'.join(escape(c['name']) for c in cl[:3])}。",
                    _picks(cl, cflag), f"{BASE}/claude-code/", "Claude Code 中转站推荐排行榜"))
    if gp:
        sec.append(("用 Codex / GPT", f"GPT 排行榜前三：{'、'.join(escape(c['name']) for c in gp[:3])}。",
                    _picks(gp, gflag), f"{BASE}/codex/", "Codex 中转站推荐排行榜"))
    if cheap:
        sec.append(("预算优先", f"推荐站里 {escape(cflag or 'Claude')} 最便宜的三家，便宜但不是来路不明的低价站。",
                    _picks(cheap, cflag), f"{BASE}/claude/", "Claude 全部中转站价格"))
    if trial:
        sec.append(("先充一点试试", "起充 ¥1、退款无手续费，试了不满意损失最小。",
                    _picks(trial, cflag), None, None))
    if inv:
        sec.append(("公司报销要开票", "这些推荐站能开票，开票要求点站名看详情。",
                    _picks(inv, cflag), None, None))
    body = [f"<h1>中转站推荐：按需求直接挑</h1>",
            '<p class="lead">不想看长表格，就按你的情况找下面对应的一节，每节直接给三家。'
            "这些站都在 API Ranking 推荐档：真假检测通过，多数我们自己掏钱实测过扣费。</p>"]
    for h, lead, cards_html, url, txt in sec:
        body.append(f"<h2>{escape(h)}</h2><p>{lead}</p><ol class=\"rank\">{cards_html}</ol>")
        if url:
            body.append(f'<p class="more"><a href="{url}">看{escape(txt)} →</a></p>')
    body.append(f"<h2>综合排名前 {n} 家价格倍率</h2>"
                f"<p>每格是该厂商模型的最低倍率（官方价的几倍），越小越便宜。完整排名见 {main_link('', 'API Ranking')}。</p>"
                "<details><summary>展开：综合排名前 {n} 家 × 五大厂商倍率</summary>".replace("{n}", str(n))
                + overview_table(d["families"], d["rows"], numbered=True, linked_top=10) + "</details>"
                + f"<p>按厂商看：{vendor_links()}</p>")
    return title, desc, "\n".join(body), []


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


def pelican_img(i: int, alt: str) -> str:
    # 图挂主站原地址（主站入库前已白名单清洗 + CSP），不拷进本仓库：图的出处留在主站
    return f'<img src="{MAIN}/jiangzhi-test/pelican/{i}.svg" alt="{escape(alt)}" loading="lazy" width="200" height="200">'


def jiangzhi_body(d: dict) -> tuple[str, str, str, list[dict]]:
    st, ref = d["stations"], d.get("ref")
    model = escape(ref["model"]) if ref else "GPT"
    title = f"中转站降智怎么测 {YEAR}：鹈鹕测试方法（鹈鹕骑自行车）"
    desc = ("中转站降智怎么测？让模型用代码画一只骑自行车的鹈鹕，和官方同档画的对比，"
            "图明显变糙就是降智。附官方参考图和测试步骤。")
    test = f'{MAIN}/jiangzhi-test?{UTM}'
    parts = ["<h1>中转站降智怎么测：鹈鹕测试</h1>",
             '<p class="lead">让模型用代码画「一只骑自行车的鹈鹕」，再和官方渠道同一个型号、同一个推理档位画的对比。'
             f'画得明显差一截，就是被降智了。不想自己比，<a href="{test}">在 API Ranking 填地址和 key 在线测</a>。</p>',
             "<h2>什么是降智</h2>"
             "<p>模型名没变，但推理档位被偷偷调低、或换成了更便宜的型号。它不报错，只会让你觉得模型今天变笨了。"
             "用 Codex、Claude Code 写代码的人最容易吃亏：同样的钱，拿到的是低档模型。</p>",
             "<h2>为什么用鹈鹕骑自行车</h2>"
             "<p>题目短，但要同时画对鹈鹕和自行车、还要让它真的骑在车上，强模型和被降档的模型画出来差别一眼可见，"
             "也没法靠背答案过关。</p>",
             "<h2>测试步骤</h2><ol>"
             "<li><b>选同一个型号和推理档位。</b>中转站和官方用一样的型号、一样的档位，档位不同没法比。</li>"
             "<li><b>用同一个提示词各画几张。</b>一张可能碰运气，多画几张看整体水平。"
             f'提示词在 <a href="{test}">API Ranking 鹈鹕测试</a>，可以一键复制。</li>'
             "<li><b>和官方的图对比。</b>鹈鹕和自行车画不全、比例乱、人车分离，明显比官方差，就要警惕。</li>"
             "</ol>"]
    if ref:
        parts.append(f"<h2>官方画出来是什么样</h2><p>官方渠道 {model}（{escape(ref['tier'])}）画的鹈鹕骑自行车：</p>"
                     f'<div class="pel"><figure>{pelican_img(ref["image"], f"{ref['model']} 官方 鹈鹕骑自行车")}'
                     "<figcaption>官方参考</figcaption></figure></div>")
    if d.get("cases"):
        figs = "".join(f'<figure>{pelican_img(c["image"], f"中转站降智案例 {c['model']} 鹈鹕骑自行车")}'
                       "<figcaption>某中转站</figcaption></figure>" for c in d["cases"])
        parts.append("<h2>降智的站画出来什么样</h2>"
                     f"<p>同一个提示词、同样标着 {model}，某中转站画出来是这样。跟上面官方的比，差别一眼可见。</p>"
                     f'<div class="pel">{figs}</div>')
    if st:
        figs = []
        for c in st:
            name = (f'<a href="{site_url(c["slug"])}">{escape(c["name"])}</a>' if c.get("slug") else escape(c["name"]))
            figs.append(f'<figure>{pelican_img(c["image"], f"{c['name']} {c['model']} 鹈鹕测试")}'
                        f'<figcaption>{name}</figcaption></figure>')
        parts.append("<h2>没降智的站画出来什么样</h2>"
                     "<p>下面几家我们测过，画出来和官方一个水平。点站名看这家站的价格、真假检测和扣费实测。</p>"
                     f'<div class="pel">{"".join(figs)}</div>')
    parts.append("<h2>怀疑自己用的站降智了？</h2>"
                 f'<p>用自己的 key 在线测一次：填中转站地址和 key，和官方同档对比。'
                 f'<a href="{test}">去 API Ranking 测降智 →</a></p>')
    qas = [("中转站降智怎么判断？",
            "同一道题、同一个推理档位，在官方和中转站各画几张：中转站的图明显比官方糙，就是降智了。"),
           ("鹈鹕测试是什么？",
            "让模型用代码画一只骑自行车的鹈鹕，和官方同档画的对比，用来看中转站有没有偷降推理档位或换便宜型号。"),
           ("鹈鹕测试提示词在哪？",
            f'提示词和官方参考图都在 <a href="{test}">API Ranking 鹈鹕测试</a>，可以一键复制。')]
    faq_html, faq_ld = faq_block(qas)
    parts.append(faq_html)
    return title, desc, "\n".join(parts), [faq_ld]


def rec_low(cards: list[dict], flag: str | None) -> str:
    """首页厂商表「推荐站最低价」格：站名链主站详情 + 旗舰型号 ¥ 输入价 + 折扣。"""
    priced = [c for c in cards if c.get("price")]
    if not priced:
        return "—"
    low = min(c["price"]["in"] for c in priced)
    tied = [c for c in priced if abs(c["price"]["in"] - low) < 1e-9]
    who = "、".join(f'<a href="{site_url(c["slug"])}">{escape(c["name"])}</a>' if c.get("slug") else escape(c["name"])
                   for c in tied)
    pr = tied[0]["price"]
    return f"{who}（{escape(flag or '')} 输入 ¥{pr['in']:.2f}，{times(pr['rate'])}）"


def index_body(pages: dict) -> tuple[str, str, str, list[dict]]:
    title = f"AI API 中转站推荐 {YEAR}：Claude、GPT、Gemini 价格倍率对比"
    desc = (f"收录 {approx(pages['ai']['site_count'])} 家 AI API 中转站，按模型对比 Claude、GPT、Gemini、Grok、DeepSeek "
            "的倍率和输入/输出价，每日更新。")
    top = [c for c in pages["ai"].get("ranking") or [] if c["tier"] in ("S", "A")]
    names = "、".join(escape(c["name"]) for c in top[:3])
    sa = {s: [c for c in pages[s].get("ranking") or [] if c["tier"] in ("S", "A")] for s in VENDOR_SLUGS}
    prices = "".join(cheap_phrase(sa[s], escape(pages[s].get("flagship") or "")) for s in ("claude", "gpt") if sa[s])
    parts = ["<h1>AI API 中转站价格对比</h1>",
             f'<p class="lead">不知道选哪家，先从 API Ranking 排行榜前三里挑：{names}，真假检测都过了。{prices}'
             f'用 Claude Code 看 <a href="{BASE}/claude-code/">Claude Code 中转站排行榜</a>，'
             f'用 Codex 看 <a href="{BASE}/codex/">Codex 中转站排行榜</a>；'
             f'按需求挑看 <a href="{BASE}/recommend/">中转站推荐</a>，'
             f'怕降智看 <a href="{BASE}/jiangzhi/">降智怎么测</a>。</p>',
             f'<p>共收录 {pages["ai"]["site_count"]} 家 AI API 中转站，按模型分好、按价格排好。</p>',
             '<div class="wrap"><table><caption>各厂商中转站排行榜</caption><thead><tr><th scope="col">排行榜</th>'
             '<th scope="col">中转站数</th><th scope="col">推荐站最低价</th><th scope="col">最便宜的 3 家</th></tr></thead><tbody>']
    for s in VENDOR_SLUGS:
        d = pages[s]
        parts.append(f'<tr><td><a href="{BASE}/{s}/">{escape(d["vendor"])} 中转站排行榜</a></td><td class="n">{d["site_count"]}</td>'
                     f'<td>{rec_low(sa[s], d.get("flagship"))}</td><td>{top_names(d["sites"])}</td></tr>')
    parts.append("</tbody></table></div>")
    models = [(s, t) for s in ("claude", "gpt", "gemini") for t in pages[s]["tables"] if t["own_page"]]
    cur = [(s, t) for s, t in models if t.get("current")]
    old = [(s, t) for s, t in models if not t.get("current")]
    parts.append("<h2>热门模型中转站价格</h2><p>"
                 + " · ".join(f'<a href="{model_url(s, t)}">{escape(alias(t["label"]))}中转站</a>' for s, t in cur) + "</p>")
    if old:
        parts.append("<p>旧型号：" + " · ".join(f'<a href="{model_url(s, t)}">{escape(t["label"])}</a>' for s, t in old) + "</p>")
    parts.append(f'<h2>更多</h2><ul><li><a href="{BASE}/api/">API 中转站哪家便宜：各厂商前 10</a></li>'
                 f'<li><a href="{BASE}/recommend/">中转站推荐：综合排名前 30</a></li>'
                 f'<li><a href="{BASE}/jiangzhi/">中转站降智怎么测（鹈鹕测试）</a></li>'
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
        if slug in CLIENT_PARENT:
            continue
        for t in d["tables"]:
            if t["own_page"]:
                path = f"{slug}/{t['price_slug']}/"
                emit(path, model_body(d, slug, t), d["updated"],
                     [(f"{nav_label[slug]} 中转站", f"{BASE}/{slug}/"), (t["label"], f"{BASE}/{path}")])
    emit("ai/", ai_body(pages["ai"], pages), pages["ai"]["updated"], [("AI 中转站", f"{BASE}/ai/")])
    emit("api/", api_body(pages["api"]), pages["api"]["updated"], [("API 中转站", f"{BASE}/api/")])
    emit("recommend/", recommend_body(pages["recommend"], pages), pages["recommend"]["updated"],
         [("中转站推荐", f"{BASE}/recommend/")])
    if pages.get("jiangzhi", {}).get("stations"):
        emit("jiangzhi/", jiangzhi_body(pages["jiangzhi"]), pages["jiangzhi"]["updated"],
             [("降智怎么测", f"{BASE}/jiangzhi/")])
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
    # Google Search Console 网址前缀资源验证文件；docs 每次整份重建，必须在这里重写，删了认领就失效
    (DOCS / "googlea4abb33f6ca136fb.html").write_text(
        "google-site-verification: googlea4abb33f6ca136fb.html", encoding="utf-8")
    (DOCS / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    print(f"生成 {len(out)} 页 → {DOCS}")


if __name__ == "__main__":
    main()
