import streamlit as st

from utils.components.visual import show_visual


def show_daily_report(report, group, timeline=None, month=None, unit="month", overlay=None,
                      history=None):
    """AI日報（群2/群3のみ）。群1は参考書のみで日報は持たない。
    段落ごとに、その段落が語っている図を挟む。

    overlay: 群3だけに追加する1ブロック（{"text":..., "chart": None}）。
    群2と同じ本文の、締めの直前に挟む。知識の中身は増やさず、差はこの1段落だけにする。

    画像添付機能は2026-09-23に廃止した(pick_news_image()関連コードは削除済み)。
    本番の実データでは実際の記事を再現できず訴求力に欠けるという指摘から、
    ニュースは画像ではなく見出し5本(show_news())で伝える方式に一本化した。
    """
    if group == 1:
        return

    report = report or {}
    blocks = report.get("blocks")
    if not blocks:
        text = (report.get("group2") or "").strip()
        if not text:
            return
        blocks = [{"text": p, "chart": None} for p in text.split("\n") if p.strip()]

    if overlay and blocks:
        blocks = blocks[:-1] + [overlay] + blocks[-1:]

    st.subheader("🤖 AI日報")

    name = st.session_state.get("nickname") or "guest"
    headline = report.get("headline", "")

    with st.container(border=True):
        if headline:
            st.markdown(f"##### {headline}")
        for i, b in enumerate(blocks):
            # 図が先、それを読む短文があと。「見ながら読む」の順に合わせる
            if b.get("chart"):
                show_visual(b["chart"], timeline, month, where="report", unit=unit,
                           history=history)
            # 挨拶は毎回同じ枠。名前だけ実行時に埋める
            st.write((f"こんにちは、{name}さん。" if i == 0 else "") + b["text"])
