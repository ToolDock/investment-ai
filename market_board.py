"""今日の米国市場を一面で見るダッシュボード。

    streamlit run market_board.py

データは investment_ai.db のキャッシュを読む。古ければ自動で取りに行き、
サイドバーの「今すぐ更新」でいつでも取り直せる。
初回は基準価額を去年の年初まで遡るので数十秒かかる。
"""

from datetime import date

import streamlit as st

import collect_us_market as collector
from utils import us_market as um
from utils.components.us_market_board import render_board

REFRESH_TTL = 900  # 秒。この間隔より新しければ取りに行かない

st.set_page_config(page_title="今日の米国市場", page_icon="📈", layout="wide")


@st.cache_data(ttl=REFRESH_TTL, show_spinner=False)
def refresh():
    """市場データを取得。戻り値は失敗したものの一覧。
    TTLの間はキャッシュが返るので、リラン程度では取りに行かない。"""
    return collector.refresh_all()


def backfill_if_needed():
    """基準価額が去年ぶんまで揃っていなければ、初回だけまとめて取得する。"""
    collector.init_tables()
    series = um.load_nav_series()
    last_year = date.today().year - 1
    if any(row[0].year == last_year for row in series):
        return
    with st.spinner(f"{um.FUND_NAME} の基準価額を {last_year}年から取得しています（初回のみ・1分ほど）"):
        collector.refresh_fund_nav(start=collector.FUND_START)


def main():
    # 同じフォルダの pages/ は実験アプリのもの。ここでは自動ナビを出さない。
    st.markdown("<style>[data-testid='stSidebarNav']{display:none}</style>",
                unsafe_allow_html=True)
    st.title("📈 今日の米国市場")

    with st.sidebar:
        st.header("データ")
        forced = st.button("今すぐ更新", width="stretch")
        updated = um.last_updated()
        st.caption(f"最終取得: {updated:%Y-%m-%d %H:%M}" if updated else "最終取得: なし")
        st.caption(
            "出典\n\n"
            "- 指数・為替・金利・コモディティ・BTC: Yahoo Finance\n"
            "- 基準価額: 三菱UFJアセットマネジメント ファンド情報API\n"
            "- Fear & Greed: CNN Business"
        )

    if forced:
        refresh.clear()

    backfill_if_needed()

    with st.spinner("市場データを取得しています"):
        try:
            failures = refresh()
        except Exception as e:  # 取得に失敗してもキャッシュ済みデータで描画する
            failures = [("refresh", str(e))]

    if failures:
        st.warning("一部のデータを取得できませんでした（表示はキャッシュ済みの値）: "
                   + ", ".join(f"{item[0]}" for item in failures))

    render_board()

    st.caption(
        "本ダッシュボードは市況の把握を目的とした情報提供であり、"
        "特定の銘柄・商品の売買を勧めるものではありません。"
    )


if __name__ == "__main__":
    main()
