"""米国市場ダッシュボードの Streamlit 描画。

紙面のように段組みで並べる:
  1段目  S&P500 / NASDAQ100 / FANG+ / ドル円
  2段目  ゴールド / 米国債10年 / BTC/USD / SOX
  3段目  eMAXIS Slim 米国株式（S&P500）の基準価額と年初来チャート
  4段目  同ファンドの年初来ドローダウン推移（今年・去年）
  5段目  Fear & Greed（120度メーター） / VIX（縦メーター）

数値は utils.us_market、チャートは utils.us_market_figures が用意したものを
並べるだけ。図の組み立てを分けてあるのは、静的サイト（build_static.py）でも
同じ図をそのまま使うため。
"""

from datetime import date

import streamlit as st

from utils import us_market as um
from utils import us_market_figures as figs

CHART_CONFIG = {"displayModeBar": False}


# ── 1・2段目のタイル ─────────────────────────────────────────
def render_tile(tile):
    change_text, sign = um.format_change(tile)
    color = figs.dir_color(sign)
    arrow = "▲" if sign > 0 else ("▼" if sign < 0 else "―")

    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.82rem;opacity:0.75;line-height:1.2'>{tile['label']}</div>"
            f"<div style='font-size:1.55rem;font-weight:700;line-height:1.35'>"
            f"{um.format_price(tile)}</div>"
            f"<div style='font-size:0.9rem;font-weight:600;color:{color};line-height:1.3'>"
            f"{arrow} {change_text}</div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(figs.intraday_chart(tile, color), width="stretch",
                        config=CHART_CONFIG, key=f"tile_{tile['symbol']}")
        st.markdown(
            f"<div style='font-size:0.72rem;opacity:0.55;margin-top:-6px'>"
            f"{tile['session']} のセッション</div>",
            unsafe_allow_html=True,
        )


def render_tile_row(symbols):
    tiles = {t["symbol"]: t for t in um.load_tiles(symbols)}
    for column, symbol in zip(st.columns(len(symbols)), symbols):
        with column:
            if symbol in tiles:
                render_tile(tiles[symbol])
            else:
                st.container(border=True).caption(
                    f"{um.SYMBOLS.get(symbol, {}).get('label', symbol)}：未取得")


# ── 3段目 eMAXIS Slim S&P500 ────────────────────────────────
def render_fund_section(series, year):
    stats = um.ytd_stats(series, year)
    st.markdown(f"#### {um.FUND_NAME}（円建て・基準価額）")
    if not stats:
        st.info("基準価額のデータがありません。`python collect_us_market.py --backfill` を実行してください。")
        return

    with st.container(border=True):
        left, right = st.columns([1, 2.4])

        with left:
            change = stats["change"]
            sign = 1 if (change or 0) > 0 else (-1 if (change or 0) < 0 else 0)
            color = figs.dir_color(sign)
            arrow = "▲" if sign > 0 else ("▼" if sign < 0 else "―")
            change_text = "—" if change is None else \
                f"{change:+,.0f}円（{stats['change_pct']:+.2f}%）"

            st.markdown(
                f"<div style='font-size:0.8rem;opacity:0.7'>基準価額（1万口あたり）</div>"
                f"<div style='font-size:2.4rem;font-weight:700;line-height:1.2'>"
                f"{stats['nav']:,.0f}<span style='font-size:1.1rem'>円</span></div>"
                f"<div style='font-size:1.0rem;font-weight:600;color:{color}'>"
                f"{arrow} {change_text}</div>"
                f"<div style='font-size:0.75rem;opacity:0.6;margin-top:2px'>"
                f"{stats['date'].year}年{stats['date'].month}月{stats['date'].day}日 基準</div>",
                unsafe_allow_html=True,
            )
            st.divider()
            ytd_color = figs.dir_color(1 if stats["ytd_pct"] >= 0 else -1)
            st.markdown(
                f"<div style='font-size:0.8rem;opacity:0.7'>年初来"
                f"（{stats['start_date'].month}月{stats['start_date'].day}日 比）</div>"
                f"<div style='font-size:1.5rem;font-weight:700;color:{ytd_color}'>"
                f"{stats['ytd_pct']:+.2f}%</div>"
                f"<div style='font-size:0.8rem;opacity:0.7;margin-top:8px'>年初来高値からの位置</div>"
                f"<div style='font-size:1.2rem;font-weight:700'>{stats['from_peak_pct']:+.2f}%</div>"
                f"<div style='font-size:0.72rem;opacity:0.55'>高値 {stats['peak']:,.0f}円</div>",
                unsafe_allow_html=True,
            )

        with right:
            st.plotly_chart(figs.nav_chart(um.year_slice(series, year)), width="stretch",
                            config=CHART_CONFIG, key="nav_ytd")


# ── 4段目 年初来ドローダウン ──────────────────────────────────
DRAWDOWN_NOTE = (
    "その年の年初からの最高値を更新するたびに基準を引き上げ、そこからの下落率を日ごとに描いたもの。"
    "0%の線に張り付いているときは高値圏、下に伸びているときは高値から下げている局面。"
)


def render_drawdown_section(series, this_year, last_year):
    st.markdown(f"#### 年初来ドローダウンの推移（{this_year}年 と {last_year}年）")
    if not um.year_slice(series, this_year) and not um.year_slice(series, last_year):
        st.info("基準価額のデータがありません。")
        return
    with st.container(border=True):
        st.plotly_chart(figs.drawdown_chart(series, this_year, last_year), width="stretch",
                        config=CHART_CONFIG, key="drawdown")
        st.caption(DRAWDOWN_NOTE)


# ── 5段目 Fear & Greed ／ VIX ────────────────────────────────
def render_fear_greed(fg):
    st.markdown("##### 本日の Fear &amp; Greed Index")
    if not fg:
        st.info("Fear & Greed のデータがありません。")
        return
    with st.container(border=True):
        st.plotly_chart(figs.fg_gauge(fg["value"], fg["label_en"], fg["label_ja"], fg["color"]),
                        width="stretch", config=CHART_CONFIG, key="fg_gauge")
        parts = []
        for label, value in (("前営業日", fg["prev"]), ("1週間前", fg["week_ago"]),
                             ("1ヶ月前", fg["month_ago"])):
            parts.append(
                f"<div style='text-align:center'>"
                f"<div style='font-size:0.72rem;opacity:0.6'>{label}</div>"
                f"<div style='font-size:1.0rem;font-weight:600'>"
                f"{'—' if value is None else f'{value:.0f}'}</div></div>"
            )
        st.markdown(
            "<div style='display:flex;justify-content:space-around'>" + "".join(parts) + "</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"出典: CNN Business Fear & Greed Index（{fg['date']}）　0=極度の恐怖／100=極度の強欲")


def render_vix(vix):
    st.markdown("##### 本日の VIX 指数")
    if not vix:
        st.info("VIX のデータがありません。")
        return
    change_text, sign = um.format_change(vix)
    with st.container(border=True):
        st.plotly_chart(figs.vix_meter(vix["price"], change_text, sign,
                                       vix["band_label"], vix["band_color"]),
                        width="stretch", config=CHART_CONFIG, key="vix_meter")
        st.caption(
            f"S&P500オプションが織り込む今後30日の予想変動率（年率%）。"
            f"{vix['session']} のセッション　20超で警戒、30超で極度の警戒。"
        )


# ── 全体 ────────────────────────────────────────────────────
def render_board(series=None, today=None):
    today = today or date.today()
    series = um.load_nav_series() if series is None else series

    st.markdown("### 主要指数・為替")
    render_tile_row(um.ROW1)
    st.markdown("### コモディティ・金利・暗号資産・半導体")
    render_tile_row(um.ROW2)

    st.divider()
    render_fund_section(series, today.year)

    st.divider()
    render_drawdown_section(series, today.year, today.year - 1)

    st.divider()
    st.markdown("### 市場のセンチメント")
    left, right = st.columns(2)
    with left:
        render_fear_greed(um.load_fear_greed())
    with right:
        render_vix(um.load_vix())
