"""Generates telemetry.html. ALL VALUES ARE SYNTHETIC, produced from a fixed seed for layout review.
They are not provider measurements. Usage: python3 build_telemetry.py"""
import math, random

random.seed(7)
HOURS = 24
PAL = {"Bedrock": "#feb101", "Foundry": "#00e9bb", "Vertex AI": "#bcf405", "Vendor API A": "#00fbff", "Vendor API B": "#00fe87"}
DASH = {"Bedrock": "", "Foundry": "6 3", "Vertex AI": "2 3", "Vendor API A": "10 3 2 3", "Vendor API B": "14 4"}
MARK = {"Bedrock": "circle", "Foundry": "square", "Vertex AI": "tri", "Vendor API A": "diamond", "Vendor API B": "circle"}
BASE = {"Bedrock": 310, "Foundry": 120, "Vertex AI": 70, "Vendor API A": 210, "Vendor API B": 90}

def series(base, phase, noise=0.12):
    return [max(5, base * (0.65 + 0.45 * math.sin((h - phase) / 24 * 2 * math.pi) ** 2 + random.uniform(-noise, noise))) for h in range(HOURS)]

DATA = {v: series(b, i * 3) for i, (v, b) in enumerate(BASE.items())}
NOT_YET = 3  # most recent hours not yet reported by providers

def marker(kind, x, y, c):
    if kind == "square": return f'<rect x="{x-3.5}" y="{y-3.5}" width="7" height="7" fill="{c}" stroke="#012639" stroke-width="1"/>'
    if kind == "tri": return f'<path d="M{x},{y-4.5} L{x+4.5},{y+3.5} L{x-4.5},{y+3.5} Z" fill="{c}" stroke="#012639" stroke-width="1"/>'
    if kind == "diamond": return f'<path d="M{x},{y-5} L{x+5},{y} L{x},{y+5} L{x-5},{y} Z" fill="{c}" stroke="#012639" stroke-width="1"/>'
    return f'<circle cx="{x}" cy="{y}" r="3.6" fill="{c}" stroke="#012639" stroke-width="1"/>'

def linechart(w, h):
    ml, mr, mt, mb = 56, 20, 14, 30
    iw, ih = w - ml - mr, h - mt - mb
    top = 400
    X = lambda i: ml + iw * i / (HOURS - 1)
    Y = lambda v: mt + ih * (1 - v / top)
    s = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Input tokens per hour by vendor, synthetic">']
    for t in range(0, top + 1, 100):
        s.append(f'<line x1="{ml}" x2="{w-mr}" y1="{Y(t)}" y2="{Y(t)}" stroke="#dfdcd6"/><text x="{ml-8}" y="{Y(t)+4}" text-anchor="end" font-size="11" fill="#393733">{t}k</text>')
    for i in range(0, HOURS, 3):
        s.append(f'<text x="{X(i)}" y="{h-8}" text-anchor="middle" font-size="11" fill="#393733">{(i-23)%24:02d}:00</text>'.replace(f'{(i-23)%24:02d}', f'{i:02d}'))
    nx = X(HOURS - NOT_YET)
    s.append(f'<defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#393733" stroke-width="1"/></pattern></defs>')
    s.append(f'<rect x="{nx}" y="{mt}" width="{w-mr-nx}" height="{ih}" fill="url(#hatch)" opacity=".18"/><text x="{(nx+w-mr)/2}" y="{mt+14}" text-anchor="middle" font-size="11" font-weight="700" fill="#012639">not yet reported</text>')
    for v, vals in DATA.items():
        pts = " ".join(f"{X(i):.1f},{Y(x):.1f}" for i, x in enumerate(vals[:HOURS - NOT_YET]))
        s.append(f'<polyline points="{pts}" fill="none" stroke="{PAL[v]}" stroke-width="3" stroke-dasharray="{DASH[v]}"/>')
        for i in range(0, HOURS - NOT_YET, 4):
            s.append(marker(MARK[v], round(X(i), 1), round(Y(vals[i]), 1), PAL[v]))
    s.append('</svg>')
    return "".join(s)

def spark(vals, color, w=210, h=44):
    mx = max(vals); pts = " ".join(f"{i*w/(len(vals)-1):.1f},{h-4-(v/mx)*(h-8):.1f}" for i, v in enumerate(vals))
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/></svg>'

def heat():
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ramp = ["#e8fffb", "#a9e8d8", "#4fbfa6", "#009176", "#004d3e"]
    cw, ch, ml, mt = 30, 24, 40, 6
    s = [f'<svg viewBox="0 0 {ml+24*cw+6} {mt+7*ch+30}" width="{ml+24*cw+6}" height="{mt+7*ch+30}" role="img" aria-label="Tokens by hour of day and weekday, synthetic">']
    for d, name in enumerate(days):
        s.append(f'<text x="{ml-8}" y="{mt+d*ch+ch/2+4}" text-anchor="end" font-size="11" fill="#393733">{name}</text>')
        for h in range(24):
            work = 1 if d < 5 else 0.25
            v = work * (math.exp(-((h - 14) ** 2) / 30) + 0.08) + random.uniform(0, 0.12)
            lvl = min(4, int(v * 4.2))
            s.append(f'<rect x="{ml+h*cw+1}" y="{mt+d*ch+1}" width="{cw-2}" height="{ch-2}" rx="5" fill="{ramp[lvl]}"/>')
    for h in range(0, 24, 3):
        s.append(f'<text x="{ml+h*cw+cw/2}" y="{mt+7*ch+18}" text-anchor="middle" font-size="11" fill="#393733">{h:02d}</text>')
    s.append('</svg>')
    return "".join(s)

def sku_chip(kind):
    return {"api": '<span class="chip">API · on-demand</span>', "prov": '<span class="chip">API · provisioned</span>', "sub": '<span class="chip sub">Subscription · seats</span>'}[kind]

def hbar(label, sub, pct, color, kind, val):
    return f'<div class="hb"><div class="hbl"><b>{label}</b> {sku_chip(kind)}<div class="note">{sub}</div></div><div class="hbv"><div class="hbt"><div class="hbf" style="width:{pct}%;background:{color}"></div></div><span>{val}</span></div></div>'

cats = [("Input", "7.22M", [random.uniform(40, 100) for _ in range(24)], "#feb101"),
        ("Output", "1.97M", [random.uniform(20, 70) for _ in range(24)], "#00e9bb"),
        ("Cache read", "4.50M", [random.uniform(30, 90) for _ in range(24)], "#00fbff"),
        ("Cache write", "0.74M", [random.uniform(5, 40) for _ in range(24)], "#bcf405"),
        ("Reasoning", "0.58M", [random.uniform(0, 30) for _ in range(24)], "#00fe87")]
cat_html = "".join(f'<div class="block cat"><div class="eyebrow">{n}</div><div class="num">{v}</div>{spark(s, "#004d3e")}<div class="note">24 h · provider-reported, summed across vendors · {"4 of 5 sources" if n!="Reasoning" else "2 of 5 sources"}</div></div>' for n, v, s, c in cats)

rows = [
 ("Bedrock", "model-a", "api", "Cloud telemetry + app-routed", "✓ Reconciled", "3.10M", "1.20M", "0.88M", "1.9M"),
 ("Bedrock", "model-b", "prov", "Cloud telemetry + app-routed", "~ Partial", "1.25M", "≥ 0.64M", "0.31M", "withheld"),
 ("Foundry", "deployment-x", "api", "Cloud telemetry", "☁ Provider only", "0.47M", "unknown", "0.12M", "unknown"),
 ("Vendor API A", "model-c", "api", "Vendor admin API", "☁ Provider only", "2.40M", "unknown", "0.66M", "unknown"),
 ("Vendor API B", "seat plan", "sub", "Vendor admin API", "— Not token-metered", "not reported", "—", "not reported", "—"),
 ("Vertex AI", "model-d", "api", "App-routed only", "⌂ App only", "not collected", "0.07M", "not collected", "—"),
]
tr = "".join(f'<tr><td><span class="sw" style="background:{PAL.get(r[0],"#dfdcd6")}"></span><b>{r[0]}</b><div class="note">{r[1]}</div></td><td>{sku_chip(r[2])}</td><td>{r[3]}</td><td><span class="chip">{r[4]}</span></td><td class="n">{r[5]}</td><td class="n">{r[6]}</td><td class="n">{r[7]}</td><td class="n">{r[8]}</td></tr>' for r in rows)

hb = "".join([
 hbar("Bedrock", "3 models · 1 account", 38, "#feb101", "api", "3.10M"),
 hbar("Bedrock", "provisioned throughput", 15, "#feb101", "prov", "1.25M"),
 hbar("Vendor API A", "direct, per-key usage", 29, "#00fbff", "api", "2.40M"),
 hbar("Foundry", "1 deployment", 6, "#00e9bb", "api", "0.47M"),
 hbar("Vendor API B", "tokens not provided for seats", 0, "#00fe87", "sub", "not reported"),
])
cons = "".join(f'<tr><td><b>{a}</b><div class="note">{b}</div></td><td><span class="chip">{c}</span></td><td class="n">{d}</td><td class="n">{e}</td></tr>' for a, b, c, d, e in [
 ("search-assistant", "project · Vendor API A key", "✓ Per key (vendor API)", "1.62M", "0.41M"),
 ("claims-summarizer", "resource · Bedrock model-a", "~ Per resource (cloud)", "1.20M", "0.33M"),
 ("internal-copilot", "deployment · Foundry", "~ Per resource (cloud)", "0.47M", "0.12M"),
 ("shared account a", "no key or user correlation", "? Unattributed", "1.91M", "0.52M"),
])
src = "".join(f'<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td><td class="n">{d}</td><td><span class="chip">{e}</span></td></tr>' for a, b, c, d, e in [
 ("Vendor API A admin usage API", "Vendor admin API", "org · per API key", "12 min ago", "✓ Current"),
 ("Bedrock CloudWatch", "Cloud telemetry", "account a · per model", "18 min ago", "✓ Current"),
 ("Foundry Azure Monitor", "Cloud telemetry", "account b · per deployment", "3 h ago", "⚠ Late"),
 ("App-routed requests", "This application", "account a · per request", "live", "✓ Current"),
 ("Vendor API B admin API", "Vendor admin API", "org · seats only", "1 h ago", "~ No token data"),
 ("Vertex AI", "Cloud telemetry", "not connected", "never", "— Not set up"),
])
leg = "".join(f'<span class="lg"><svg width="34" height="12"><line x1="0" x2="34" y1="6" y2="6" stroke="{PAL[v]}" stroke-width="3" stroke-dasharray="{DASH[v]}"/></svg>{v}</span>' for v in PAL)

html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>CFA Tokenomics: telemetry concept</title>
<link rel="stylesheet" href="tokens.css">
<style>
 .brand{{display:flex;gap:14px;align-items:center}} .logo-ph{{width:120px;height:44px;border-radius:10px;background:var(--dark-teal);color:var(--bright-teal);display:grid;place-items:center;font-weight:700;font-size:12px}}
 h1{{font-size:34px;font-weight:400;letter-spacing:-.02em;line-height:1}} .top{{display:grid;grid-template-columns:1fr auto;align-items:center}}
 .filters{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}} .sel{{border:2px solid var(--dark-blue);border-radius:10px;padding:7px 11px;font-size:13px;background:var(--white)}}
 .sel.on{{background:var(--dark-teal);color:var(--white);border-color:var(--dark-teal)}}
 .cats{{display:grid;grid-template-columns:repeat(5,1fr);gap:18px}} .cat .num{{font-size:34px;letter-spacing:-.02em;margin:6px 0 4px}}
 .main{{display:grid;grid-template-columns:1.7fr 1fr;gap:22px}} .two{{display:grid;grid-template-columns:1.1fr 1fr;gap:22px;align-items:start}} .navy .chip{{color:var(--dark-blue)}}
 .tabs{{display:flex;gap:8px;margin:8px 0 10px}} .legend{{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;margin-top:6px}} .lg{{display:inline-flex;gap:6px;align-items:center}}
 table{{width:100%;border-collapse:collapse;font-size:13px}} th{{text-align:left;padding:7px 8px;border-bottom:2px solid var(--dark-blue);font-weight:700}} td{{padding:9px 8px;border-bottom:1px solid var(--gray);vertical-align:middle}} .n{{text-align:right;font-variant-numeric:tabular-nums}} th.n{{text-align:right}}
 .sw{{display:inline-block;width:11px;height:11px;border-radius:4px;margin-right:7px;border:1px solid var(--dark-blue)}}
 .chip.sub{{border-style:dashed}}
 .hb{{display:grid;gap:4px;margin:12px 0}} .hbt{{flex:1;height:14px;background:var(--light-gray);border-radius:8px;border:1px solid var(--gray);overflow:hidden}} .hbf{{height:100%;border-right:1px solid var(--dark-blue)}} .hbv{{display:flex;gap:10px;align-items:center;font-size:13px;font-variant-numeric:tabular-nums}} .hbv span{{min-width:86px;text-align:right}}
 .ramp{{display:flex;gap:6px;align-items:center;font-size:12px;margin-top:8px}} .ramp i{{width:22px;height:12px;border-radius:4px;display:inline-block}}
 .pair{{display:grid;grid-template-columns:120px 1fr;gap:6px 12px;align-items:center;font-size:13px;margin-top:10px}}
 .pb{{height:12px;border-radius:7px;border:1px solid var(--dark-blue)}}
</style></head><body><div class="page" style="width:1440px">
 <span class="concept-flag">CONCEPT · synthetic data · [REVIEW REQUIRED] brand approval pending</span>
 <header class="top"><div class="brand"><div class="logo-ph">logo placeholder</div><div><div class="eyebrow">CFA Tokenomics <span class="note">(working name)</span></div><h1>Token telemetry</h1></div></div>
  <div class="filters"><span class="sel on">Last 24 h</span><span class="sel">7 d</span><span class="sel">30 d</span><span class="sel">Vendor: all (5)</span><span class="sel">SKU: API + Subscription</span><span class="sel">Model: all</span><span class="sel">Project / key: all</span><span class="sel">Source: all</span></div></header>

 <section class="cats">{cat_html}</section>
 <p class="note" style="margin-top:-10px">Token categories are shown separately and are not summed: providers define cache and reasoning tokens differently. Unknown is "not reported", never zero.</p>

 <section class="main">
  <div class="block"><div class="eyebrow">Input tokens per hour, by vendor</div>
   <div class="tabs"><span class="sel on">Input</span><span class="sel">Output</span><span class="sel">Cache read</span><span class="sel">Cache write</span><span class="sel">Reasoning</span></div>
   {linechart(840, 300)}<div class="legend">{leg}</div>
   <p class="note" style="margin-top:8px">Lines are provider-reported figures. Hatched area: the latest hours providers have not reported yet, so those values are not drawn.</p></div>
  <div class="block"><div class="eyebrow">Where input tokens go: vendor and SKU</div>{hb}
   <p class="note">SKU type separates metered API use from subscription seats. Subscription seats are usually not token-metered, so they show "not reported" rather than zero. [VERIFY per vendor]</p></div>
 </section>

 <section class="two">
  <div class="block"><div class="eyebrow">When tokens are spent (input, last 7 days)</div><div style="margin-top:10px">{heat()}</div>
   <div class="ramp">fewer<i style="background:#e8fffb"></i><i style="background:#a9e8d8"></i><i style="background:#4fbfa6"></i><i style="background:#009176"></i><i style="background:#004d3e"></i>more</div></div>
  <div class="block"><div class="eyebrow">Top consumers</div>
   <table><thead><tr><th>Consumer</th><th>How attributed</th><th class="n">Input</th><th class="n">Output</th></tr></thead><tbody>{cons}</tbody></table>
   <p class="note" style="margin-top:8px">Per-user figures appear only where a source provides authenticated correlation. Otherwise usage stays "unattributed".</p></div>
 </section>

 <section class="block"><div class="eyebrow">Breakdown: vendor, SKU, source and token type (24 h)</div>
  <table style="margin-top:8px"><thead><tr><th>Vendor · model</th><th>SKU</th><th>Source</th><th>Reconciliation</th><th class="n">Input (provider)</th><th class="n">Input (routed here)</th><th class="n">Output (provider)</th><th class="n">Unattributed input</th></tr></thead><tbody>{tr}</tbody></table></section>

 <section class="two">
  <div class="block"><div class="eyebrow">Cache activity by model (separate counts)</div>
   <div class="pair"><b>model-a</b><div><div class="pb" style="width:78%;background:#feb101"></div><div class="note">cache read 2.4M · input 3.1M</div></div>
    <b>model-b</b><div><div class="pb" style="width:40%;background:#feb101"></div><div class="note">cache read 0.5M · input 1.25M</div></div>
    <b>model-c</b><div><div class="pb" style="width:66%;background:#00fbff"></div><div class="note">cache read 1.6M · input 2.4M</div></div></div>
   <p class="note" style="margin-top:10px">Bars compare cache-read tokens with input tokens as each vendor defines them. They are not a hit rate: some vendors count cached tokens inside input.</p></div>
  <div class="block navy"><div class="eyebrow">Sources and freshness</div>
   <table style="margin-top:8px;color:var(--white)"><thead><tr><th style="border-color:var(--white)">Source</th><th style="border-color:var(--white)">Type</th><th style="border-color:var(--white)">Scope</th><th class="n" style="border-color:var(--white)">Last sync</th><th style="border-color:var(--white)">Status</th></tr></thead><tbody>{src}</tbody></table></div>
 </section>
 <p class="note">Synthetic values for layout review only. Not measured provider usage or actual cost. Vendor names, SKUs and attribution dimensions are illustrative and unverified.</p>
</div></body></html>'''
open("telemetry.html", "w").write(html)
