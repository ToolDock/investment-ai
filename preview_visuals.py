"""視覚アセットを1枚のHTMLにまとめて確認する。

    python preview_visuals.py            18か月目時点のドローダウンで出力
    python preview_visuals.py 30         30か月目時点で出力
"""

import json
import sys

import plotly.io as pio

from utils.visuals import build, load_visuals, INK, MUTED, FONT

OUT = "visuals_preview.html"
IDS = ["v_index_path", "v_drawdown", "v_recent_drawdowns", "v_bear_markets", "v_longterm_log",
       "v_alltime_high", "v_missing_best_days"]


def main():
    month = int(sys.argv[1]) if len(sys.argv) > 1 else 18
    hv = load_visuals()
    with open("scenario_scripted.json", encoding="utf-8") as f:
        timeline = json.load(f)["timeline"]

    blocks = []
    for i, cid in enumerate(IDS):
        fig, title, note = build(cid, hv, timeline, month)
        html = pio.to_html(fig, include_plotlyjs=("cdn" if i == 0 else False),
                           full_html=False, config={"displayModeBar": False})
        blocks.append(
            f'<section><h2>{title}</h2><p class="id">{cid}</p>'
            f'{html}<p class="note">{note}</p></section>')

    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>視覚アセットのプレビュー</title><style>
body {{ font-family: {FONT}; color: {INK}; background:#fff;
       max-width: 860px; margin: 0 auto; padding: 32px 20px 64px; line-height:1.6; }}
h1 {{ font-size: 20px; }} h2 {{ font-size: 16px; margin: 0 0 2px; }}
section {{ margin: 40px 0; padding-bottom: 24px; border-bottom: 1px solid #e3e6ea; }}
.id {{ color:{MUTED}; font-size:12px; margin:0 0 10px; font-family: ui-monospace, monospace; }}
.note {{ color:{MUTED}; font-size:12px; margin-top:8px; }}
</style></head><body>
<h1>視覚アセットのプレビュー（{month}か月目時点）</h1>
{''.join(blocks)}
</body></html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{len(IDS)} 枚 -> {OUT}")


if __name__ == "__main__":
    main()
