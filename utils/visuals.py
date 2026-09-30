"""参考書と日報で共用する視覚アセット。

Plotly の Figure を返すだけで streamlit に依存しない
（us_market_figures.py と同じ方針）。色は web/board.css の :root と揃えてある。
"""

import json
import os
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import timezone as _timezone

import plotly.graph_objects as go

SECTOR_JA = {
    "Technology": "テクノロジー",
    "Consumer Cyclical": "一般消費財",
    "Communication Services": "通信サービス",
    "Financial Services": "金融",
    "Industrials": "資本財・産業",
    "Basic Materials": "素材",
    "Energy": "エネルギー",
    "Real Estate": "不動産",
    "Healthcare": "ヘルスケア",
    "Consumer Defensive": "生活必需品",
    "Utilities": "公益（インフラ）",
}

HV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge", "historical_visuals.json",
)

# 系列色。カテゴリ2色は CVD 分離を検証済み（ΔE 30.5 / 通常視 33.7）
CAT = ["#1f6feb", "#bf6516"]
DOWN = "#c62828"
UP = "#2e7d32"
REF = "#9aa4ae"
def _dark_mode():
    """いまのStreamlitのテーマ（ライト/ダーク）を見て、チャートの地色・文字色を選ぶための判定。

    2026-09-24: 背景・文字色を白固定(#ffffff・#1f2328)にしていたため、ダークモードだと
    チャートだけ白い板のまま浮いて見える不具合があった（本人からの指摘で発覚）。
    st.context.theme.type（Streamlit 1.64で利用可能）で判定する。このモジュールは
    build_static.py 等、Streamlitのスクリプト実行文脈の外から使われることもあるため、
    取得できない場合は例外を握りつぶしてライト側にフォールバックする。
    """
    try:
        import streamlit as st
        return st.context.theme.get("type") == "dark"
    except Exception:
        return False


def INK():
    return "#e8eaed" if _dark_mode() else "#1f2328"


def MUTED():
    return "rgba(154,164,174,0.95)" if _dark_mode() else "#62696f"


def GRID():
    return "rgba(255,255,255,0.16)" if _dark_mode() else "#e3e6ea"


def SURFACE():
    # 地色は常に透明にして、ページの背景（ライト/ダーク）にそのまま乗せる。
    # テーブルのセル背景など「板」が要る箇所だけ、ダークモードでは薄い灰、
    # ライトモードでは白にする（_TABLE_FILL を使う）。
    return "rgba(0,0,0,0)"


def _table_fill():
    return "rgba(255,255,255,0.06)" if _dark_mode() else "#ffffff"

FONT = 'system-ui, -apple-system, "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif'


def fig_price_series(bars, ref, kind="daily", offset=0, height=220):
    """指数・コモディティの値動き（ToolDockの株価カードに寄せた面グラフ）。

    kind="intraday" は当日の5分足（xは時刻）、kind="daily" は日足（xは日付）。
    期間の起点（intradayなら前日終値、それ以外は期間の最初の値）を破線の基準線にし、
    いま値がそれより上なら緑、下なら赤で塗る。カーソルを合わせると縦の目安線と
    その地点の値が出るようにしてある（1点ずつ数字を追える最小限のインタラクション）。
    """
    if kind == "intraday":
        xs = [_datetime.fromtimestamp(b["ts"] + offset, tz=_timezone.utc) for b in bars]
        hover = "%{x|%H:%M}  %{y:,.2f}<extra></extra>"
        tick = dict(tickformat="%H:%M", nticks=6)
    else:
        xs = [b["date"] for b in bars]
        hover = "%{x|%Y-%m-%d}  %{y:,.2f}<extra></extra>"
        tick = dict(nticks=6)
    values = [b["value"] for b in bars]
    up = values[-1] >= ref
    color = UP if up else DOWN
    fill = "rgba(46,125,50,0.12)" if up else "rgba(198,40,40,0.12)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=[ref] * len(xs), mode="lines",
        line=dict(color=REF, width=1, dash="dash"),
        hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=xs, y=values, mode="lines",
        line=dict(color=color, width=2),
        fill="tonexty", fillcolor=fill,
        hovertemplate=hover, showlegend=False,
    ))
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor",
                     spikethickness=1, spikedash="dot", spikecolor=MUTED(), **tick)
    fig.update_yaxes(tickformat=",.0f")
    fig.update_layout(hovermode="x unified")
    return _base(fig, height=height, margin=dict(l=8, r=8, t=8, b=8))


def load_visuals():
    with open(HV_PATH, encoding="utf-8") as f:
        return json.load(f)


def _base(fig, height=340, legend=False, margin=None):
    fig.update_layout(
        height=height,
        margin=margin or dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SURFACE(),
        plot_bgcolor=SURFACE(),
        font=dict(family=FONT, size=13, color=INK()),
        hoverlabel=dict(font_family=FONT),
        showlegend=legend,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID(), ticks="outside",
                     tickcolor=GRID(), tickfont=dict(color=MUTED()))
    fig.update_yaxes(gridcolor=GRID(), zeroline=False, linecolor=SURFACE(),
                     tickfont=dict(color=MUTED()))
    return fig


# ── 過去の弱気相場（表） ──────────────────────────
def fig_bear_markets(hv):
    v = hv["v_bear_markets"]
    rows = v["rows"]
    cells = [
        [r.get("name", "") for r in rows],
        [r["peak"] for r in rows],
        [f"{r['decline_pct']:.1f}%" for r in rows],
        [f"{r['decline_months']}か月" for r in rows],
        [f"{r['recovery_months']}か月" for r in rows],
    ]
    fig = go.Figure(go.Table(
        columnwidth=[34, 16, 16, 17, 17],
        header=dict(values=["局面", "ピーク", "下落率", "下落期間", "回復まで"],
                    fill_color=_table_fill(), line_color=GRID(), align="left",
                    font=dict(family=FONT, size=13, color=MUTED()), height=30),
        cells=dict(values=cells, fill_color=_table_fill(), line_color=GRID(), align="left",
                   font=dict(family=FONT, size=13, color=INK()), height=28),
    ))
    return _base(fig, height=30 + 28 * len(rows) + 20)


# ── 長期（戦後以降）の実質価格（対数） ────────────────────────
def fig_longterm_log(hv):
    v = hv["v_longterm_log"]
    years = [p["year"] for p in v["series"]]
    vals = [p["real"] for p in v["series"]]
    fig = go.Figure(go.Scatter(
        x=years, y=vals, mode="lines", line=dict(color=CAT[0], width=2),
        hovertemplate="%{x}年<br>実質価格 %{y:,.0f}<extra></extra>"))
    fig.update_yaxes(type="log", dtick=1, title_text="実質価格（対数）",
                     title_font=dict(color=MUTED(), size=12))
    fig.update_layout(hovermode="x unified")
    return _base(fig, height=320)


# ── 最高値で買った場合 vs いつでも買った場合 ──────────────
def fig_alltime_high(hv):
    d = hv["v_alltime_high"]["data"]
    hz = [f"{h['horizon_years']}年後" for h in d["horizons"]]
    ath = [h["ath_avg"] for h in d["horizons"]]
    allv = [h["all_avg"] for h in d["horizons"]]
    fig = go.Figure()
    fig.add_bar(x=hz, y=ath, name="最高値で買った", marker_color=CAT[0],
                marker_line=dict(color=SURFACE(), width=2),
                text=[f"{v:+.1f}%" for v in ath], textposition="outside",
                textfont=dict(color=MUTED(), size=12),
                hovertemplate="最高値で買った<br>%{x} %{y:+.1f}%<extra></extra>")
    fig.add_bar(x=hz, y=allv, name="いつでも買った", marker_color=CAT[1],
                marker_line=dict(color=SURFACE(), width=2),
                text=[f"{v:+.1f}%" for v in allv], textposition="outside",
                textfont=dict(color=MUTED(), size=12),
                hovertemplate="いつでも買った<br>%{x} %{y:+.1f}%<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.42, bargroupgap=0.05,
                      legend=dict(orientation="h", y=1.14, x=0,
                                  font=dict(color=MUTED(), size=12)))
    fig.update_traces(marker_cornerradius=4)
    fig.update_yaxes(title_text="その後の平均リターン", range=[0, max(allv) * 1.2],
                     ticksuffix="%", title_font=dict(color=MUTED(), size=12))
    return _base(fig, height=360, legend=True,
                 margin=dict(l=8, r=16, t=44, b=8))


# ── 上昇の最良の数日を逃した場合 ──────────────────────
def fig_missing_best_days(hv):
    d = hv["v_missing_best_days"]["data"]
    items = list(reversed(d["items"]))
    labels = [i["label"] for i in items]
    vals = [i["value"] for i in items]
    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h", marker_color=CAT[0],
        marker_line=dict(color=SURFACE(), width=2),
        text=[f"{v:+.1f}%" if abs(v) >= 0.05 else "±0.0%" for v in vals],
        textposition="outside", textfont=dict(color=MUTED(), size=12),
        hovertemplate="%{y}<br>%{x:+.1f}%<extra></extra>"))
    fig.update_layout(bargap=0.45)
    fig.update_traces(marker_cornerradius=4)
    fig.update_xaxes(title_text=f"累積リターン（{d['period']}）", range=[0, max(vals) * 1.18],
                     ticksuffix="%", title_font=dict(color=MUTED(), size=12))
    return _base(fig, height=300, margin=dict(l=8, r=24, t=8, b=8))


# ── 今の下落幅と、これまでの最大 ────────────────────
# 横軸の言い方。実験は月次、本番は営業日
UNIT_LABEL = {"month": ("経過月数", "か月目"), "day": ("経過営業日数", "営業日目")}


def fig_drawdown(timeline, month, unit="month"):
    x_title, x_suffix = UNIT_LABEL.get(unit, UNIT_LABEL["month"])
    months, dds = [], []
    for m in timeline:
        if m["month"] > month:
            break
        months.append(m["month"])
        dds.append(m["market_context"]["drawdown"]["current"])
    worst = min(dds) if dds else 0.0
    now = dds[-1] if dds else 0.0

    fig = go.Figure(go.Scatter(
        x=months, y=dds, mode="lines", fill="tozeroy",
        line=dict(color=DOWN, width=2), fillcolor="rgba(198,40,40,0.10)",
        hovertemplate="%{x}" + x_suffix + "<br>下落幅 %{y:.1f}%<extra></extra>"))
    # 今が過去最大と同値なら基準線は引かない（注記が重なるため）
    if abs(now - worst) >= 0.05:
        fig.add_hline(y=worst, line=dict(color=MUTED(), width=1, dash="dot"),
                      annotation_text=f"これまでの最大 {worst:.1f}%",
                      annotation_position="bottom left",
                      annotation_font=dict(color=MUTED(), size=12))
    if months:
        label = (f"今 {now:.1f}%（過去最大と同水準）"
                 if abs(now - worst) < 0.05 else f"今 {now:.1f}%")
        fig.add_scatter(x=[months[-1]], y=[now], mode="markers+text",
                        marker=dict(color=DOWN, size=9,
                                    line=dict(color=SURFACE(), width=2)),
                        text=[label], textposition="top left",
                        textfont=dict(color=INK(), size=13), hoverinfo="skip")
    fig.update_xaxes(title_text=x_title, title_font=dict(color=MUTED(), size=12),
                     range=[months[0] - 0.5, months[-1] + 0.8] if months else None)
    fig.update_yaxes(title_text="最高値からの下落幅",
                     title_font=dict(color=MUTED(), size=12), ticksuffix="%")
    fig.update_layout(hovermode="x unified")
    return _base(fig, height=400)


# ── 直近の実際の下落局面と、今の下落の重ね合わせ ────────────
# ── これまでの指数の推移 ────────────────────────
def fig_index_path(timeline, month, unit="month"):
    x_title, x_suffix = UNIT_LABEL.get(unit, UNIT_LABEL["month"])
    months, level, lv = [0], [100.0], 100.0
    for m in timeline:
        if m["month"] > month:
            break
        lv *= (1 + m["return"])
        months.append(m["month"])
        level.append(lv)

    peak_i = max(range(len(level)), key=lambda i: level[i])
    now = level[-1]

    fig = go.Figure(go.Scatter(
        x=months, y=level, mode="lines", line=dict(color=CAT[0], width=2),
        hovertemplate="%{x}" + x_suffix + "<br>指数 %{y:.1f}（開始時=100）<extra></extra>"))
    if peak_i not in (0, len(level) - 1):
        fig.add_scatter(x=[months[peak_i]], y=[level[peak_i]], mode="markers+text",
                        marker=dict(color=MUTED(), size=7,
                                    line=dict(color=SURFACE(), width=2)),
                        text=[f"最高値 {level[peak_i]:.0f} "], textposition="top left",
                        textfont=dict(color=MUTED(), size=12), hoverinfo="skip",
                        showlegend=False)
    fig.add_scatter(x=[months[-1]], y=[now], mode="markers+text",
                    marker=dict(color=CAT[0], size=9,
                                line=dict(color=SURFACE(), width=2)),
                    text=[f" 今 {now:.0f}（開始から{now - 100:+.1f}%）"],
                    textposition="middle left" if months[-1] > 40 else "middle right",
                    textfont=dict(color=INK(), size=13), hoverinfo="skip",
                    showlegend=False)
    fig.update_xaxes(title_text=x_title, range=[-1, max(months) + 2],
                     title_font=dict(color=MUTED(), size=12))
    fig.update_yaxes(title_text="指数（開始時＝100）",
                     title_font=dict(color=MUTED(), size=12))
    fig.update_layout(hovermode="x unified")
    return _base(fig, height=400, margin=dict(l=8, r=20, t=12, b=8))


# ── 投資家心理の推移 ────────────────────────
FG_BANDS = [(0, 25, "極度の恐怖", "#c62828"), (25, 45, "恐怖", "#ef9a9a"),
            (45, 55, "中立", "#fbc02d"), (55, 75, "強欲", "#9ccc65"),
            (75, 100, "極度の強欲", "#2e7d32")]


def fig_fear_greed(timeline, month, unit="month"):
    x_title, x_suffix = UNIT_LABEL.get(unit, UNIT_LABEL["month"])
    months = [m["month"] for m in timeline if m["month"] <= month]
    vals = [m["market_context"]["fear_greed"]["value"] for m in timeline
            if m["month"] <= month]
    if not months:
        return None

    fig = go.Figure()
    for lo, hi, label, col in FG_BANDS:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=col, opacity=0.10, line_width=0,
                      annotation_text=label, annotation_position="right",
                      annotation_font=dict(color=MUTED(), size=11))
    fig.add_scatter(x=months, y=vals, mode="lines",
                    line=dict(color=INK(), width=2),
                    hovertemplate="%{x}" + x_suffix +
                                  "<br>Fear &amp; Greed %{y}<extra></extra>")
    now = vals[-1]
    fig.add_scatter(x=[months[-1]], y=[now], mode="markers+text",
                    marker=dict(color=INK(), size=9, line=dict(color=SURFACE(), width=2)),
                    text=[f" 今 {now}"], textposition="middle left",
                    textfont=dict(color=INK(), size=13), hoverinfo="skip",
                    showlegend=False)
    fig.update_xaxes(title_text=x_title, title_font=dict(color=MUTED(), size=12))
    fig.update_yaxes(title_text="Fear & Greed", range=[0, 100],
                     title_font=dict(color=MUTED(), size=12))
    return _base(fig, height=300, margin=dict(l=8, r=60, t=12, b=8))


def select_recent(episodes, worst, n=2):
    """今の下落幅に近い局面を n 件選ぶ。図とプロンプトで同じ結果を使う。"""
    if worst is None or worst >= -0.05:
        return list(episodes)
    picked = sorted(episodes, key=lambda e: abs(e["decline_pct"] - worst))[:n]
    return sorted(picked, key=lambda e: e["peak"])


def fig_recent_drawdowns(hv, timeline=None, month=None, unit="month"):
    eps = hv["v_recent_drawdowns"]["data"]["episodes"]

    # 今の下落幅に近い局面だけを出す。全部並べるとラベルが重なって読めない
    now = None
    if timeline and month:
        seg = [m for m in timeline if m["month"] <= month]
        if seg:
            now = min(m["market_context"]["drawdown"]["current"] for m in seg)
    eps = select_recent(eps, now)

    # 灰色で揃えるので、識別は線種と凡例で行う（ラベルを置くと重なって読めない）
    DASH = ["solid", "dash"]

    fig = go.Figure()
    xmax = 0
    for k, e in enumerate(eps):
        xs = [p["m"] for p in e["path"]]
        ys = [p["dd"] for p in e["path"]]
        xmax = max(xmax, xs[-1] if xs else 0)
        rec = e.get("recovery_months")
        label = f"{e['name']}（{rec}か月で回復）" if rec else f"{e['name']}（未回復）"
        fig.add_scatter(x=xs, y=ys, mode="lines", name=label,
                        line=dict(color=REF, width=1.5, dash=DASH[k % len(DASH)]),
                        hovertemplate=f"{e['name']}<br>ピークから %{{x:.1f}}か月"
                                      "<br>下落幅 %{y:.1f}%<extra></extra>")

    # 今の局面（直近でドローダウンが0だった月から現在まで）
    if timeline and month:
        seg = [m for m in timeline if m["month"] <= month]
        start = 0
        for i, m in enumerate(seg):
            if m["market_context"]["drawdown"]["current"] >= -0.05:
                start = i
        cur = seg[start:]
        if len(cur) > 1:
            # 実データ（unit="day"）の timeline は "month" が営業日の連番でしかなく、
            # 過去局面（hv側、暦月単位）とそのまま突き合わせると「23営業日」が「23か月」と
            # 表示されてしまう（暦1か月強の下落が2年近い下落に見えるバグがあった）。
            # date が取れる場合は暦日数から月換算し、両者の軸を揃える
            if unit == "day" and cur[0].get("date") and all(m.get("date") for m in cur):
                d0 = _date.fromisoformat(cur[0]["date"])
                xs = [round((_date.fromisoformat(m["date"]) - d0).days / 30.44, 2) for m in cur]
            else:
                xs = [m["month"] - cur[0]["month"] for m in cur]
            ys = [m["market_context"]["drawdown"]["current"] for m in cur]
            xmax = max(xmax, xs[-1])
            fig.add_scatter(x=xs, y=ys, mode="lines", name="今回",
                            line=dict(color=DOWN, width=2.5),
                            hovertemplate="今回<br>ピークから %{x}か月"
                                          "<br>下落幅 %{y:.1f}%<extra></extra>")
            fig.add_scatter(x=[xs[-1]], y=[ys[-1]], mode="markers+text",
                            marker=dict(color=DOWN, size=9,
                                        line=dict(color=SURFACE(), width=2)),
                            text=[f" 今回 {ys[-1]:.1f}%"], textposition="middle right",
                            textfont=dict(color=INK(), size=13), hoverinfo="skip",
                            showlegend=False)

    fig.update_xaxes(title_text="ピークからの経過月数", range=[-0.4, xmax * 1.05 + 1.6],
                     title_font=dict(color=MUTED(), size=12))
    fig.update_yaxes(title_text="最高値からの下落幅", ticksuffix="%",
                     title_font=dict(color=MUTED(), size=12))
    # 凡例をチャート上部(y=1.13)に置いていたが、ラベルが長く(例:「2018年2月の急落
    # （6.5か月で回復）」)、横並びの凡例が折り返して2〜3行になるとチャート本体の
    # 折れ線に重なって読めなくなる不具合があった(2026-09-24、本人指摘)。
    # チャート下部に置き、下マージンを広めに取って折り返し分の余白を確保する。
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.22, x=0,
                                  font=dict(color=MUTED(), size=12)))
    return _base(fig, height=400, legend=True, margin=dict(l=8, r=16, t=16, b=70))


# ── セクター別騰落（対象日の内訳） ──────────────────
def fig_sector_performance(timeline, month):
    """対象日（timeline[month-1]）のセクター別騰落を横棒で見せる。

    timeline は他の図と同じものを受け取るが、この図が使うのは対象日ぶんの
    market_context.sectors だけ（LiveProvider.timeline() が最後のエントリにだけ
    載せている）。無ければ描かない。
    """
    if not timeline or not month:
        return None
    entry = next((m for m in timeline if m["month"] == month), None)
    if not entry:
        return None
    sectors = entry["market_context"].get("sectors")
    if not sectors:
        return None

    rows = sorted(sectors, key=lambda s: s["change_pct"])   # 下から上に正の順で並ぶよう昇順
    labels = [SECTOR_JA.get(s["sector"], s["sector"]) for s in rows]
    vals = [s["change_pct"] for s in rows]
    colors = ["#2e7d32" if v >= 0 else DOWN for v in vals]

    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h", marker_color=colors,
        text=[f"{v:+.1f}%" for v in vals], textposition="outside",
        textfont=dict(color=MUTED(), size=12),
        hovertemplate="%{y} %{x:+.1f}%<extra></extra>"))
    span = max(abs(min(vals)), abs(max(vals)), 1.0)
    fig.update_xaxes(title_text="騰落率", ticksuffix="%",
                     range=[-span * 1.35, span * 1.35],
                     title_font=dict(color=MUTED(), size=12), zeroline=True,
                     zerolinecolor=GRID(), zerolinewidth=1)
    return _base(fig, height=32 * len(rows) + 40, margin=dict(l=8, r=32, t=8, b=8))


# ── 為替・金利の直近の推移 ──────────────────────────
def fig_trend(values, title_y, suffix="", digits=1, color=None):
    """直近の推移を簡単な折れ線で見せる。history() は日付を持たないので、
    横軸は「直近n営業日」とだけ言う（他の図のような実際の日付ラベルは付けない）。
    """
    if not values or len(values) < 2:
        return None
    n = len(values)
    xs = list(range(1, n + 1))
    color = color or CAT[0]
    now = values[-1]
    fig = go.Figure(go.Scatter(
        x=xs, y=values, mode="lines", line=dict(color=color, width=2),
        hovertemplate="%{y:." + str(digits) + "f}" + suffix + "<extra></extra>"))
    fig.add_scatter(x=[xs[-1]], y=[now], mode="markers+text",
                    marker=dict(color=color, size=9, line=dict(color=SURFACE(), width=2)),
                    text=[f" 今 {now:.{digits}f}{suffix}"], textposition="middle left",
                    textfont=dict(color=INK(), size=13), hoverinfo="skip", showlegend=False)
    fig.update_xaxes(title_text=f"直近{n}営業日", title_font=dict(color=MUTED(), size=12),
                     showticklabels=False)
    fig.update_yaxes(title_text=title_y, ticksuffix=suffix,
                     title_font=dict(color=MUTED(), size=12))
    return _base(fig, height=280, margin=dict(l=8, r=64, t=12, b=8))


# ── 年初来ドローダウンの年比較（本番のみ・常時表示。LLMには選ばせない）────
_PREV_YEAR_COLORS = ["#9aa5b1", "#c3c9cf", "#dadfe3"]
_MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
_MONTH_LABELS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月",
                "8月", "9月", "10月", "11月", "12月"]


def fig_ytd_drawdown_yoy(data):
    """年ごとの『年初からの最高値に対する下落率』を重ねて描く。

    年が変わるたびに基準をリセットして測っているので、「今年はどのくらい下げているか、
    去年の同時期・去年の年間と比べてどうか」がひと目で分かる。直近年は実線・赤で塗りつぶし、
    それ以前の年は破線・グレーで重ねる。LiveProvider.ytd_drawdown_years() の戻り値をそのまま渡す。
    """
    if not data:
        return None
    years = sorted(y for y in data if data[y])
    if not years:
        return None
    latest = years[-1]

    fig = go.Figure()
    prev_i = 0
    for y in years:
        series = data[y]
        xs = [_date.fromisoformat(s["date"]).timetuple().tm_yday for s in series]
        ys = [s["dd"] for s in series]
        if y == latest:
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", name=f"{y}年",
                line=dict(color=DOWN, width=2.4),
                fill="tozeroy", fillcolor="rgba(198,40,40,0.10)",
                hovertemplate=f"{y}年 " + "%{y:.1f}%<extra></extra>"))
        else:
            color = _PREV_YEAR_COLORS[min(prev_i, len(_PREV_YEAR_COLORS) - 1)]
            prev_i += 1
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", name=f"{y}年",
                line=dict(color=color, width=1.6, dash="dash"),
                hovertemplate=f"{y}年 " + "%{y:.1f}%<extra></extra>"))

    fig.update_xaxes(tickvals=_MONTH_STARTS, ticktext=_MONTH_LABELS, range=[1, 366],
                     title_font=dict(color=MUTED(), size=12))
    fig.update_yaxes(title_text="年初来ドローダウン", ticksuffix="%",
                     title_font=dict(color=MUTED(), size=12))
    fig.update_layout(hovermode="x unified",
                      legend=dict(orientation="h", x=0, y=1.12,
                                  font=dict(color=MUTED(), size=12)))
    return _base(fig, height=420, margin=dict(l=8, r=16, t=44, b=8), legend=True)


def ytd_drawdown_summary(data):
    """年ごとの最大下落幅とその日付を返す（キャプション用。図の外で使う）。"""
    out = []
    for y in sorted(data or {}):
        series = data[y]
        if not series:
            continue
        worst = min(series, key=lambda s: s["dd"])
        out.append({"year": y, "dd": worst["dd"], "date": worst["date"]})
    return out


def fig_fx_trend(history):
    if not history:
        return None
    return fig_trend(history.get("fx"), "ドル円", suffix="円", digits=2)


def fig_rates_trend(history):
    if not history:
        return None
    return fig_trend(history.get("rates"), "米10年債利回り", suffix="%", digits=2)


def fig_relation(history):
    """関係が最近変わった二つの指標を、左右2軸で重ねて描く。

    LiveProvider.history() の "relation"（utils/relations.py が用意した直近の推移）を使う。
    二つの線の高さを比べる図ではなく、動く向きが揃っているか離れているかを見る図なので、
    軸はそれぞれの目盛りのまま、直近 n_recent 営業日を薄く塗って『ここからの動き』を示す。
    """
    r = (history or {}).get("relation")
    if not r or not r.get("dates"):
        return None
    a, b = r["a"], r["b"]
    n = len(r["dates"])
    xs = list(range(1, n + 1))
    nr = min(r.get("n_recent", 20), n)

    def hover(s):
        d, u = s.get("digits", 2), s.get("unit", "")
        head = "$" if u == "$" else ""
        tail = "" if u == "$" else u
        return f"{s['name']} {head}%{{y:.{d}f}}{tail}<extra></extra>"

    fig = go.Figure()
    fig.add_vrect(x0=n - nr + 0.5, x1=n + 0.5, fillcolor=REF, opacity=0.15, line_width=0,
                  annotation_text=f"直近{nr}営業日", annotation_position="top left",
                  annotation_font=dict(color=MUTED(), size=12))
    fig.add_trace(go.Scatter(x=xs, y=a["values"], mode="lines", name=a["name"],
                             line=dict(color=CAT[0], width=2), hovertemplate=hover(a)))
    fig.add_trace(go.Scatter(x=xs, y=b["values"], mode="lines", name=b["name"], yaxis="y2",
                             line=dict(color=CAT[1], width=2), hovertemplate=hover(b)))
    ticks = list(range(1, n + 1, 10))
    fig.update_xaxes(tickvals=ticks, ticktext=[r["dates"][i - 1][5:] for i in ticks],
                     title_text=f"直近{n}営業日", title_font=dict(color=MUTED(), size=12))
    fig.update_yaxes(title_text=f"{a['name']}（左軸）", ticksuffix=a.get("unit", "") if a.get("unit") != "$" else "",
                     tickprefix="$" if a.get("unit") == "$" else "",
                     title_font=dict(color=CAT[0], size=12))
    fig.update_layout(
        yaxis2=dict(title=dict(text=f"{b['name']}（右軸）", font=dict(color=CAT[1], size=12)),
                    overlaying="y", side="right", showgrid=False,
                    ticksuffix=b.get("unit", ""), tickfont=dict(color=MUTED())),
        hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.12, font=dict(color=MUTED(), size=12)))
    return _base(fig, height=340, margin=dict(l=8, r=8, t=44, b=8), legend=True)


BUILDERS = {
    "v_bear_markets": lambda hv, tl, mo, u, hist: fig_bear_markets(hv),
    "v_longterm_log": lambda hv, tl, mo, u, hist: fig_longterm_log(hv),
    "v_alltime_high": lambda hv, tl, mo, u, hist: fig_alltime_high(hv),
    "v_missing_best_days": lambda hv, tl, mo, u, hist: fig_missing_best_days(hv),
    "v_drawdown": lambda hv, tl, mo, u, hist: fig_drawdown(tl, mo, u),
    "v_index_path": lambda hv, tl, mo, u, hist: fig_index_path(tl, mo, u),
    "v_fear_greed": lambda hv, tl, mo, u, hist: fig_fear_greed(tl, mo, u),
    "v_recent_drawdowns": lambda hv, tl, mo, u, hist: fig_recent_drawdowns(hv, tl, mo, u),
    "v_sector_performance": lambda hv, tl, mo, u, hist: fig_sector_performance(tl, mo),
    "v_fx_trend": lambda hv, tl, mo, u, hist: fig_fx_trend(hist),
    "v_rates_trend": lambda hv, tl, mo, u, hist: fig_rates_trend(hist),
    "v_relation": lambda hv, tl, mo, u, hist: fig_relation(hist),
}

NOTES = {
    "v_bear_markets": "Shiller 長期データ（月次終値・名目価格、配当を含まない）。"
                      "配当を再投資し物価を調整すると、実際に回復した時期はこれよりかなり早い。"
                      "特に世界恐慌の267か月は名目・配当なしゆえの数字であり、当時の投資家の体験とは大きく異なる。",
    "v_longterm_log": "Shiller 長期データ（実質価格・配当を除く、1945年以降）。対数スケール。",
    "v_alltime_high": "1950年以降・配当込み。最高値の日に投資した場合と、任意の日に投資した場合の平均。",
    "v_missing_best_days": "FRED 日次データ。上昇率の大きかった日を保有していなかった場合の試算。",
    "v_drawdown": "この相場での、最高値からの下落幅の推移。",
    "v_index_path": "この相場の指数の推移。開始時を100として、これまでの歩みと今の位置を示す。",
    "v_fear_greed": "市場参加者がどれだけ怖がっているかの推移。数字が低いほど恐怖が強い。他人の心理であって、自分の判断の根拠ではない。",
    "v_recent_drawdowns": "直近10年に実際に起きた下落局面（FRED日次・配当を含まない価格ベース）。灰色が過去の実例、赤が今回。同じ規模の下落が現実には数か月で回復してきたことが分かる。",
    "v_sector_performance": "対象日のセクター別騰落率。指数はひとつの塊ではなく、業種ごとに強弱が入れ替わりながら全体の動きを作っている。",
    "v_fx_trend": "直近の実勢レート（Yahoo Finance）。為替は資産の中身（企業の数・稼ぐ力）を変えるものではなく、気にしなくてよい。",
    "v_rates_trend": "直近の米10年債利回り（FRED）。金利が上がると、将来の利益を今の価値に割り引く際の割引率が上がり、特に成長株が値段の付け替えで動きやすくなる。",
    "v_relation": "見るのは線の高さではなく、動く向きが揃っているか離れているか。左右の軸は別々の目盛りで、灰色の帯が直近の期間。"
                  "二つの関係は時期によって変わり、ここで見えている変化が今後も続くとは限らない（因果を示す図でもない）。",
}

TITLES = {
    "v_bear_markets": "過去の主要な弱気相場と、その後の回復",
    "v_longterm_log": "戦後(1945年)以降の実質価格（対数スケール）",
    "v_alltime_high": "「最高値」で買っても、その後のリターンはほぼ変わらない",
    "v_missing_best_days": "上昇の「最良の数日」を逃すと、リターンは大きく削られる",
    "v_drawdown": "今の下落幅と、これまでに経験した最大の下落幅",
    "v_index_path": "ここまでの指数の歩みと、今いる場所",
    "v_fear_greed": "いま市場はどれだけ怖がっているか",
    "v_recent_drawdowns": "同じくらい下げた過去の局面は、どれくらいで戻ったか",
    "v_sector_performance": "今日、どの業種が強くてどの業種が弱かったか",
    "v_fx_trend": "ドル円の直近の動き",
    "v_rates_trend": "米10年債利回りの直近の動き",
    "v_relation": "最近、関係が変わって見える二つの指標",
}


# 台本の推移を使う図。timeline が無ければ描けない
NEEDS_TIMELINE = {"v_drawdown", "v_index_path", "v_fear_greed", "v_sector_performance"}
# LiveProvider.history() の直近n営業日の数値配列を使う図。実験（ScriptedProvider）には無いので、
# 本番だけで描かれる（無ければ描かない＝取れなければ埋めないという既存原則のとおり）
NEEDS_HISTORY = {"v_fx_trend", "v_rates_trend", "v_relation"}


def build(chart_id, hv=None, timeline=None, month=None, unit="month", history=None):
    """(Figure, タイトル, 注記) を返す。描けないなら (None, None, None)。

    unit は横軸の言い方だけを変える。実験は "month"、本番は "day"。
    history は LiveProvider.history() と同じ形（{"fx": [...], "rates": [...], ...}）。
    """
    if chart_id not in BUILDERS:
        return None, None, None
    if chart_id in NEEDS_TIMELINE and not timeline:
        return None, None, None
    if chart_id in NEEDS_HISTORY and not history:
        return None, None, None
    hv = hv or load_visuals()
    return (BUILDERS[chart_id](hv, timeline, month, unit, history),
            TITLES[chart_id], NOTES[chart_id])
