"""チャートに読み方を添えて並べる。

日報の本文で触れなかった指標も、ここで短く扱う。
狙いは値動きの実況ではなく、「この図が何を示し、何を示さないか」を覚えてもらうこと。
だから「見方」の文は毎日同じにしてある。
"""

import plotly.graph_objects as go
import streamlit as st

from utils.chart_notes import DOWN as _D, FLAT, UP, build
from utils.visuals import CAT, DOWN, FONT, GRID, MUTED

# 並べる順。上ほど長期投資の判断に近く、下ほど「眺めるだけ」でよいもの
ORDER = ["index", "drawdown", "fear_greed", "vix", "rates", "fx",
         "sectors", "semis", "gold", "btc"]

TREND_MARK = {UP: "↗", _D: "↘", FLAT: "→"}


def _spark(values, key):
    """20営業日ぶんの細い折れ線。数字ではなく形を見るためのもの。"""
    if not values or len(values) < 5:
        return
    up = values[-1] >= values[0]
    color = CAT[0] if up else DOWN
    fig = go.Figure(go.Scatter(
        y=values, mode="lines", line=dict(color=color, width=2),
        hoverinfo="skip", fill="tozeroy",
        fillcolor=("rgba(31,111,235,0.08)" if up else "rgba(198,40,40,0.08)")))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False,
                     range=[min(values) - abs(min(values)) * 0.02 - 0.01,
                            max(values) + abs(max(values)) * 0.02 + 0.01])
    fig.update_layout(height=64, margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False, font=dict(family=FONT))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                    key=f"spark_{key}")


def show_reading_board(ctx, history, columns=2, links=None):
    notes = build(ctx, history)
    # 生成時に理由を書き足したものがあればそちらを使う
    links = links if links is not None else notes.pop("_links", [])
    notes.pop("_links", None)

    st.markdown("#### チャートの見方")
    st.caption("値動きの実況ではなく、それぞれの図が何を示し、何を示さないかを置いています。"
               "毎日同じことが書いてありますが、それでかまいません。")

    if links:
        with st.container(border=True):
            st.markdown("**今日、つながって見えるところ**")
            for l in links:
                st.write(f"・{l['text']}")

    keys = [k for k in ORDER if k in notes]
    cols = st.columns(columns)
    for i, k in enumerate(keys):
        n = notes[k]
        with cols[i % columns]:
            with st.container(border=True):
                mark = next((m for t, m in TREND_MARK.items() if t in (n["now"] or "")), "")
                st.markdown(f"**{n['title']}** {mark}")
                _spark(history.get(k), k)
                if n["now"]:
                    st.caption(n["now"])
                st.markdown(
                    f"<div style='font-size:0.86rem;line-height:1.6;opacity:0.9'>"
                    f"{n['read']}</div>", unsafe_allow_html=True)
