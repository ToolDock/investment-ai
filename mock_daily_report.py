"""日報の完成イメージを1枚のHTMLにする。

実験画面の並び（市況→ニュース→SNS→AI日報→参考書）を再現し、
AI日報は段落ごとに図を挟んだ形で描く。

    python mock_daily_report.py
"""

import json

import plotly.io as pio

from utils.visuals import build, load_visuals, INK, MUTED, GRID, FONT

RAW = "daily_report_raw.jsonl"
OUT = "mock_daily_report.html"


def latest_by_month():
    rows = {}
    with open(RAW, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("blocks"):
                rows[r["month"]] = r
    return rows


def main():
    rows = latest_by_month()
    hv = load_visuals()
    with open("scenario_scripted.json", encoding="utf-8") as f:
        scenario = json.load(f)
    timeline = scenario["timeline"]
    by_month = {m["month"]: m for m in timeline}

    screens, first = [], True
    for month in sorted(rows):
        m = by_month[month]
        mc = m["market_context"]

        parts = []
        hl = rows[month]["blocks"][0].get("headline", "") if rows[month]["blocks"] else ""
        if hl:
            parts.append(f'<p class="head">{hl}</p>')
        for i, b in enumerate(rows[month]["blocks"]):
            greet = "こんにちは、Friskさん。" if i == 0 else ""
            parts.append(f'<p>{greet}{b["text"]}</p>')
            if b.get("chart"):
                fig, title, note = build(b["chart"], hv, timeline, month)
                if fig is not None:
                    inner = pio.to_html(fig, include_plotlyjs=(True if first else False),
                                        full_html=False, config={"displayModeBar": False})
                    first = False
                    parts.append(f'<div class="fig"><p class="figtitle">{title}</p>'
                                 f'{inner}<p class="note">{note}</p></div>')

        sns = "".join(
            f'<div class="post"><b>@{p["user"]}</b><p>{p["text"]}</p>'
            f'<span class="likes">❤️ {p["likes"]}</span></div>'
            for p in m["sns"])

        screens.append(f'''
<div class="screen">
  <p class="crumb">{month}か月目（全{len(timeline)}か月）／局面：{m['phase']}</p>
  <p class="stat">株価指数 {m['return']*100:+.1f}%　VIX {mc['vix']}　
     Fear &amp; Greed {mc['fear_greed']['value']}（{mc['fear_greed']['classification']}）　
     最高値からの下落幅 {mc['drawdown']['current']:.1f}%</p>

  <h3 class="ttl">📰 市場ニュース</h3>
  <div class="card"><p class="head">{m['news']['headline']}</p><p>{m['news']['body']}</p></div>

  <h3 class="ttl">◎ SNSの反応</h3>
  {sns}

  <h3 class="ttl">🤖 AI日報</h3>
  <div class="card">{''.join(parts)}</div>

  <p class="after">↓ この下に「📘 長期投資の参考書」（図は全群共通でそちらにも並ぶ）と、行動の選択が続く</p>
</div>''')

    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>日報の完成イメージ</title><style>
body {{ font-family:{FONT}; color:{INK}; background:#f6f7f8;
       margin:0; padding:28px 16px 64px; line-height:1.85; }}
h1 {{ font-size:19px; max-width:900px; margin:0 auto 6px; }}
.lead {{ max-width:900px; margin:0 auto 28px; color:{MUTED}; font-size:13px; }}
.screen {{ max-width:900px; margin:0 auto 44px; background:#fff;
          border:1px solid {GRID}; border-radius:10px; padding:24px 26px 20px; }}
.crumb {{ color:{MUTED}; font-size:13px; margin:0 0 4px; }}
.stat {{ color:{MUTED}; font-size:13px; margin:0 0 22px; }}
.ttl {{ font-size:15px; margin:26px 0 10px; }}
.card {{ border:1px solid {GRID}; border-radius:10px; padding:20px 22px; background:#fff; }}
.card p {{ margin:0 0 14px; font-size:15px; }}
.card p:last-child {{ margin-bottom:0; }}
.head {{ font-weight:700; font-size:16px; }}
.post {{ border:1px solid {GRID}; border-radius:10px; padding:12px 16px; margin-bottom:8px; }}
.post p {{ margin:4px 0; font-size:14px; }}
.post b {{ font-size:13px; color:{MUTED}; }}
.likes {{ color:{MUTED}; font-size:12px; }}
.fig {{ margin:18px 0 22px; padding-top:16px; border-top:1px solid {GRID}; }}
.figtitle {{ font-weight:600; font-size:14px; margin:0 0 6px; }}
.note {{ color:{MUTED}; font-size:12px; margin:6px 0 0; }}
.after {{ color:{MUTED}; font-size:12px; margin:18px 0 0; }}
</style></head><body>
<h1>日報の完成イメージ（群2）</h1>
<p class="lead">実験画面の並びを再現したもの。実際に生成した本文と図を使っている。
群3ではAI日報の本文の後ろに、参加者自身の資産状況に触れる一段落が加わる。</p>
{''.join(screens)}
</body></html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{len(screens)} 画面 -> {OUT}")


if __name__ == "__main__":
    main()
