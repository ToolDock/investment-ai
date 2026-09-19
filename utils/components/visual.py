import streamlit as st

from utils.visuals import build, load_visuals


@st.cache_data
def _visuals():
    return load_visuals()


def show_visual(chart_id, timeline=None, month=None, caption=True, where="x",
                unit="month", history=None):
    """図を1枚描く。未知のIDなら何もしない。"""
    fig, title, note = build(chart_id, _visuals(), timeline, month, unit, history)
    if fig is None:
        return
    st.markdown(f"**{title}**")
    st.plotly_chart(fig, width="stretch",
                    key=f"viz_{where}_{chart_id}_{month}")
    if caption:
        st.caption(note)
