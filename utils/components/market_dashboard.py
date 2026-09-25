import streamlit as st
import plotly.graph_objects as go

from utils.visuals import fig_price_series, _dark_mode, GRID, MUTED, FONT

# 「大きく」見せる指数・コモディティ（ToolDock寄りのカード）。
# ドル円・金利はカード化せず、既存の st.metric（現在値＋前日比）のままにする
BIG_SYMBOLS = [
    ("^GSPC", "S&P500"),
    ("^NDX", "NASDAQ100"),
    ("^NYFANG", "NYSE FANG+"),
    ("^SOX", "SOX（半導体指数）"),
    ("GC=F", "金（ゴールド）"),
    ("BTC-USD", "ビットコイン"),
]

PERIODS = ["1日", "1週間", "1か月", "年初来", "1年", "5年"]

# 騰落率の連続配色（濃い赤→グレー→濃い緑）。ヒートマップ2種で共用。
# 2026-09-24: 中立色をほぼ白(#f5f5f2)にしていたため、ダークモードで中立に近い
# セルだけ白い板のように浮いて見え、「配色が見づらい」という指摘につながった。
# 中立色を白ではない中間グレーにし、cmin/cmaxも±2.5%→±4%に広げた
# （実際の値動きは±5%近くまで出るため、±2.5%だと極端な銘柄が軒並み同じ色に
# 飽和してしまい、差が読み取れなくなっていた）。
_DIVERGING_COLORSCALE = [
    [0.0, "#c62828"],   # 濃い赤（他の画面のDOWNと同じ実色）
    [0.25, "#e57373"],  # 淡い赤
    [0.5, "#6b6f76"],   # 中間グレー（白ではないので、ダークモードでも浮かない）
    [0.75, "#81c784"],  # 淡い緑
    [1.0, "#2e7d32"],   # 濃い緑（他の画面のUPと同じ実色）
]
_CSCALE_RANGE = 4.0  # cmin=-4%, cmax=+4%


def _contrast_text_colors(values):
    """どのセルも白文字で統一する。

    中立色を白から中間グレー(#6b6f76)に変えたので、中立に近いセルでも
    白文字のコントラストが保てるようになった（旧仕様はほぼ白の背景に
    合わせて黒文字に切り替える必要があったが、その分岐は不要になった）。
    """
    return ["#ffffff" for _ in values]

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

# S&P500セクター別の時価総額比率の概算値（2026年9月時点、ChartRow調べ）。
# DBに時価総額データが無いため静的な概算値で代用。数か月に一度見直す想定。
SECTOR_WEIGHT = {
    "Technology": 38.3,
    "Financial Services": 12.1,
    "Communication Services": 10.0,
    "Healthcare": 9.1,
    "Consumer Cyclical": 8.9,
    "Industrials": 8.2,
    "Consumer Defensive": 4.5,
    "Energy": 3.6,
    "Utilities": 2.0,
    "Real Estate": 1.7,
    "Basic Materials": 1.7,
}


def _vix_spark(values):
    """VIXの直近の推移を、メーターの隣に添える折れ線。

    上昇＝警戒が強まっている、として赤、低下＝落ち着いてきている、として緑にする
    （価格系のスパークライン(_spark, reading_board.py)とは上下の意味が逆になる点に注意）。

    2026-09-25: 最初は軸なしの極小チャートにしていたが、「高さと縦軸横軸がないので
    見にくい」と指摘を受けた。数値の目盛り（縦軸）と、期間の目安（横軸）を
    最小限つけて、高さも少し確保する。
    """
    if not values or len(values) < 5:
        return None
    rising = values[-1] > values[0]
    color = "#c62828" if rising else "#2e7d32"
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    n = len(values)
    fig = go.Figure(go.Scatter(
        y=values, mode="lines", line=dict(color=color, width=2),
        hoverinfo="skip", fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.12)"))
    lo, hi = min(values), max(values)
    fig.update_xaxes(
        visible=True, showgrid=False, showline=False, zeroline=False,
        tickmode="array", tickvals=[0, n - 1], ticktext=[f"{n}営業日前", "今日"],
        tickfont=dict(color=MUTED(), size=10))
    fig.update_yaxes(
        visible=True, showline=False, zeroline=False,
        gridcolor=GRID(), tickfont=dict(color=MUTED(), size=10),
        range=[lo * 0.9, hi * 1.1],
        # nticks任せだと範囲によっては目盛りが1本しか出ないことがあったので、
        # 実際の最小・最大を目盛りとして明示する（本人指摘、2026-09-25）
        tickmode="array", tickvals=[round(lo, 1), round(hi, 1)])
    fig.update_layout(height=110, margin=dict(l=32, r=4, t=4, b=24),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False, font=dict(family=FONT))
    return fig


def _fg_gauge(value, classification):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        # domainを明示しないと、数値（number）が中央からずれて右寄りに出ることがあった
        # （本人指摘、2026-09-25）。ゲージ全体を図の中央いっぱいに固定する
        domain={"x": [0, 1], "y": [0, 1]},
        number={"font": {"size": 46}},
        title={"text": f"<span style='font-size:1.15em'>Fear &amp; Greed</span>"
                       f"<br><span style='font-size:1.0em;color:gray'>{classification}</span>"},
        gauge={
            "axis": {"range": [0, 100], "tickvals": [0, 25, 45, 55, 75, 100]},
            "bar": {"color": "rgba(0,0,0,0)"},
            "threshold": {
                "line": {"color": "#111", "width": 4},
                "thickness": 0.85,
                "value": value,
            },
            "steps": [
                {"range": [0, 25], "color": "#c62828"},
                {"range": [25, 45], "color": "#ef9a9a"},
                {"range": [45, 55], "color": "#fbc02d"},
                {"range": [55, 75], "color": "#9ccc65"},
                {"range": [75, 100], "color": "#2e7d32"},
            ],
        },
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=70, b=10),
                      font=dict(size=15))
    return fig


def _tile_colors(c):
    # セクター/指数タイルの色（テーマ非依存の実色で指定）
    if c >= 3:
        return "#2e7d32", "#ffffff"
    if c >= 1:
        return "#66bb6a", "#0b2e13"
    if c >= 0:
        return "#c8e6c9", "#1b5e20"
    if c > -1:
        return "#ffcdd2", "#7f1d1d"
    if c > -3:
        return "#ef9a9a", "#4a0f0f"
    return "#c62828", "#ffffff"


def _heatmap_html(sectors):
    cells = ""
    for s in sectors:
        c = s["change_pct"]
        bg, fg = _tile_colors(c)
        cells += (
            f"<div style='background:{bg};color:{fg};border-radius:8px;"
            f"padding:10px 8px;text-align:center;'>"
            f"<div style='font-size:0.78rem;opacity:0.9'>{SECTOR_JA.get(s['sector'], s['sector'])}</div>"
            f"<div style='font-weight:700;font-size:1.0rem'>{c:+.1f}%</div></div>"
        )
    return (
        "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(115px,1fr));"
        f"gap:6px;margin-top:4px;'>{cells}</div>"
    )


def _indices_html(indices):
    """market_context.indices（S&P500・NASDAQ・GOLD・BTCなど）を簡易タイルで並べる。

    ヒートマップ（セクター）とは別に、指数・コモディティ自体の騰落を数値で
    確認できる場所がどこにもなかった（本番はshow_price_gridのライブカードで
    別途見えるが、実験はこの関数しか呼ばれないため、BTC等の数値がまったく
    画面に出ないというギャップがあった）。indices は実験・本番どちらの
    market_contextにも入っている共通データなので、ここに足すことで両方に効く。
    """
    if not indices:
        return None
    cells = ""
    for i in indices:
        c = i["change_pct"]
        bg, fg = _tile_colors(c)
        cells += (
            f"<div style='background:{bg};color:{fg};border-radius:8px;"
            f"padding:10px 8px;text-align:center;'>"
            f"<div style='font-size:0.78rem;opacity:0.9'>{i['symbol']}</div>"
            f"<div style='font-weight:700;font-size:1.0rem'>{c:+.1f}%</div></div>"
        )
    return (
        "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));"
        f"gap:6px;margin-top:4px;'>{cells}</div>"
    )


def _sector_treemap(sectors):
    """面積＝指数内の比率目安（静的概算）、色＝当日の騰落率のツリーマップ。

    等サイズのグリッドだと、小さいセクターの急変動が大きく見えたり、
    テクノロジーのような主力セクターの小さな変化が軽く見えたりする。
    面積を比率に揃えることで「何が指数を動かしているか」が伝わる。
    """
    labels, values, changes = [], [], []
    for s in sectors:
        w = SECTOR_WEIGHT.get(s["sector"])
        if not w:
            continue
        labels.append(SECTOR_JA.get(s["sector"], s["sector"]))
        values.append(w)
        changes.append(s["change_pct"])
    if not labels:
        return None
    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=[""] * len(labels),
        values=values,
        branchvalues="total",
        marker=dict(
            colors=changes,
            colorscale=_DIVERGING_COLORSCALE,
            cmin=-_CSCALE_RANGE, cmid=0, cmax=_CSCALE_RANGE,
            line=dict(width=0),  # 2026-09-25: セル間の黒縁取りをやめてほしいとの要望で、区切り線自体を無くした
        ),
        text=[f"{c:+.1f}%" for c in changes],
        texttemplate="<b>%{label}</b><br>%{text}",
        textposition="middle center",  # 2026-09-25: ToolDock同様、銘柄名と%を箱の中央に
        textfont=dict(color=_contrast_text_colors(changes), size=15),  # 2026-09-25: 少し大きく
        hovertemplate="%{label} %{text}<br>指数内の比率 目安%{value:.1f}%<extra></extra>",
        pathbar=dict(visible=False),
    ))
    fig.update_layout(margin=dict(l=4, r=4, t=4, b=4), height=320,  # 2026-09-25: 少し大きく
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _stock_treemap(stocks):
    """S&P500の個別銘柄を、セクターでグルーピングした二階層のツリーマップ。

    ToolDock本家と同じ考え方：面積＝時価総額比率の目安、色＝当日の騰落率、
    セクターの見出しセルはグレー（中立）にして、個別銘柄の色だけが目に入るようにする。
    stocks が空（データがまだ揃っていない日）なら None を返し、呼び出し側で
    セクター単位の簡易版にフォールバックしてもらう。
    """
    if not stocks:
        return None
    sectors = sorted({s["sector"] for s in stocks})

    # 見出しセル（セクター名の帯）は colorscale の中立色（0）を使っていたが、
    # ダークモード対応でその中立色を白系からグレーに変えた結果、見出し帯が
    # 灰色になって見づらくなった（本人指摘、2026-09-25）。見出しは数値と無関係な
    # ラベルなので、colorscale を経由させず、常に白で固定する
    # （Plotlyのcolorsは数値とCSS色文字列を混在できる。数値のセルだけcolorscaleが効く）。
    # 2026-09-25: ライトモードでは地色(paper_bgcolor)がそもそも白いため、
    # 見出しセルを常に白固定にすると背景と同化して箱の区切りが消えてしまう。
    # ダークモードは白、ライトモードはGRID()の淡いグレーに出し分ける。
    HEADER_COLOR = "#ffffff" if _dark_mode() else GRID()
    HEADER_TEXT_COLOR = "#2b2f33"
    labels, parents, values, colors, texts, hovers = [], [], [], [], [], []
    for sec in sectors:
        total_w = sum(s["weight_pct"] for s in stocks if s["sector"] == sec)
        labels.append(SECTOR_JA.get(sec, sec))
        parents.append("")
        values.append(total_w)
        colors.append(HEADER_COLOR)
        texts.append("")
        hovers.append(SECTOR_JA.get(sec, sec))
    for s in stocks:
        labels.append(s["symbol"])
        parents.append(SECTOR_JA.get(s["sector"], s["sector"]))
        values.append(s["weight_pct"])
        colors.append(s["change_pct"])
        texts.append(f"{s['change_pct']:+.1f}%")
        hovers.append(f"{s['name']}（{s['symbol']}） {s['change_pct']:+.1f}%")

    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        marker=dict(
            colors=colors,
            colorscale=_DIVERGING_COLORSCALE,
            cmin=-_CSCALE_RANGE, cmid=0, cmax=_CSCALE_RANGE,
            line=dict(width=0),  # 2026-09-25: セル間の黒縁取りをやめてほしいとの要望で、区切り線自体を無くした
        ),
        text=texts,
        texttemplate="<b>%{label}</b><br>%{text}",
        textposition="middle center",  # 2026-09-25: ToolDock同様、銘柄名と%を箱の中央に
        # 2026-09-25: textfont.size を見出し/銘柄で分けようと配列にしたところ、
        # このStreamlit環境のplotly.jsではTreemapの size 配列指定がバグって
        # 全セルが空パスになり、ヒートマップ全体が真っ暗な1色の箱になった
        # （本人からの指摘で発覚、実データで再現確認済み）。size はスカラーに戻す。
        # color の方は配列でも問題なく描画される。
        textfont=dict(
            color=[HEADER_TEXT_COLOR] * len(sectors)
                  + _contrast_text_colors([s["change_pct"] for s in stocks]),
            size=14),
        customdata=hovers,
        hovertemplate="%{customdata}<br>時価総額比率 目安%{value:.2f}%<extra></extra>",
        pathbar=dict(visible=False),
        tiling=dict(pad=2),
    ))
    fig.update_layout(margin=dict(l=4, r=4, t=4, b=4), height=560,  # 2026-09-25: 少し大きく
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _price_card_html(label, price, diff, pct):
    up = diff >= 0
    color = "#2e7d32" if up else "#c62828"
    arrow = "▲" if up else "▼"
    return (
        "<div>"
        f"<div style='font-size:0.85rem;color:#62696f;font-weight:600'>{label}</div>"
        f"<div style='font-size:2.1rem;font-weight:700;line-height:1.25'>{price:,.2f}</div>"
        f"<div style='font-size:1.0rem;font-weight:600;color:{color}'>"
        f"{arrow} {diff:+,.2f}（{pct:+.2f}%）</div>"
        "</div>"
    )


def _hilo_caption(bars, kind="intraday", offset=0):
    import datetime as _dt
    hi = max(bars, key=lambda b: b["value"])
    lo = min(bars, key=lambda b: b["value"])
    if kind == "intraday":
        hi_t = _dt.datetime.fromtimestamp(hi["ts"] + offset, tz=_dt.timezone.utc).strftime("%H:%M")
        lo_t = _dt.datetime.fromtimestamp(lo["ts"] + offset, tz=_dt.timezone.utc).strftime("%H:%M")
    else:
        hi_t, lo_t = hi["date"], lo["date"]
    return f"高値 {hi['value']:,.2f}（{hi_t}）／安値 {lo['value']:,.2f}（{lo_t}）"


def show_price_card(prov, target, symbol, label):
    """指数・コモディティ1銘柄ぶんのカード。ToolDockの株価カード（大きな価格＋
    騰落の矢印＋面グラフ）に、期間切替（1日〜5年）を付けたもの。

    prov は LiveProvider。期間はカードごとの st.pills で選ばせ、選択のたびに
    LiveProvider.price_series() を都度引く（日報生成時に固めた内容ではなく、
    見ているその場でDBから取り直す）。
    """
    period = st.pills(label, PERIODS, default="1日", key=f"period_{symbol}",
                      label_visibility="collapsed")
    period = period or "1日"
    data = prov.price_series(target, symbol, period)
    with st.container(border=True):
        if not data:
            st.caption(label)
            st.write("（この期間のデータがありません）")
            return
        bars = data["bars"]
        price = bars[-1]["value"]
        diff = price - data["ref"]
        pct = diff / data["ref"] * 100 if data["ref"] else 0.0
        st.markdown(_price_card_html(label, price, diff, pct), unsafe_allow_html=True)
        fig = fig_price_series(bars, data["ref"], kind=data["kind"],
                               offset=data.get("offset", 0))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption(_hilo_caption(bars, data["kind"], data.get("offset", 0)))
        if data.get("clipped"):
            st.caption(f"※ データは{bars[0]['date']}以降しか集めていないため、"
                      f"実際はそこまでの分しか出ていません。")


def show_price_grid(prov, target):
    """主要指数・コモディティを2列×3行のカードで並べる。本文より前・一番最初に置き、
    「結局どれだけ動いたのか」がひと目で分かるようにする。
    """
    for i in range(0, len(BIG_SYMBOLS), 2):
        cols = st.columns(2)
        for col, (symbol, label) in zip(cols, BIG_SYMBOLS[i:i + 2]):
            with col:
                show_price_card(prov, target, symbol, label)


def show_market_dashboard(ctx, prov=None, target=None, history=None):
    """market_context（VIX・Fear&Greed・個別銘柄ヒートマップ）を表示。全群共通の市況情報。

    prov・target を渡すと、個別銘柄（S&P500主要銘柄）のヒートマップを live で引いて
    使う（本番のみ。実験には prov が無いので、そのときは従来のセクター単位のまま）。
    個別銘柄データがまだ揃っていない日は、自動でセクター単位の簡易版に落ちる。

    history（{"vix": [...]} 等、LiveProvider.history()と同じ形）を渡すと、
    VIXメーターの隣に直近の推移を小さく添える（本人要望、2026-09-24）。
    無くても動く（実験側は当面渡さない。渡さなければ従来どおり数値のみ）。
    """
    if not ctx:
        return

    st.subheader("📊 今日のマーケット")

    with st.container(border=True):
        c1, c2 = st.columns([1, 1.2])

        with c1:
            vix = ctx["vix"]
            st.metric(
                "VIX（恐怖指数）",
                f"{vix}",
                delta=ctx.get("vix_change"),
                delta_color="inverse",
            )
            level = (
                "落ち着き" if vix < 16 else
                "やや不安" if vix < 25 else
                "警戒" if vix < 40 else
                "極度の警戒"
            )
            st.caption(f"市場の警戒度：{level}")
            vix_hist = (history or {}).get("vix")
            if vix_hist:
                vfig = _vix_spark(vix_hist)
                if vfig is not None:
                    st.plotly_chart(vfig, width="stretch",
                                    config={"displayModeBar": False})

        with c2:
            fg = ctx["fear_greed"]
            st.plotly_chart(
                _fg_gauge(fg["value"], fg["classification"]),
                width="stretch",
                config={"displayModeBar": False},
            )

        indices_html = _indices_html(ctx.get("indices"))
        if indices_html is not None:
            st.markdown("**指数・コモディティ（前日比）**")
            st.markdown(indices_html, unsafe_allow_html=True)

        stocks = prov.stock_heatmap(target) if prov and target else []
        stock_treemap = _stock_treemap(stocks)
        if stock_treemap is not None:
            st.markdown("**個別銘柄（前日比・面積は時価総額比率の目安、セクターでグループ化）**")
            st.plotly_chart(stock_treemap, width="stretch", config={"displayModeBar": False})
            st.caption("面積はS&P500主要銘柄の時価総額比率（概算）、色はその日の騰落率。"
                      "緑が上げ、赤が下げ。")
        else:
            st.markdown("**セクター別（前日比・面積は指数内の時価総額比率の目安）**")
            treemap = _sector_treemap(ctx["sectors"])
            if treemap is not None:
                st.plotly_chart(treemap, width="stretch", config={"displayModeBar": False})
                st.caption("面積は各セクターの時価総額比率（概算）、色はその日の騰落率。"
                          "緑が上げ、赤が下げ。個別銘柄データが揃うと、銘柄単位の表示に"
                          "切り替わります。")
            else:
                st.markdown(_heatmap_html(ctx["sectors"]), unsafe_allow_html=True)
