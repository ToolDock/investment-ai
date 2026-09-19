import time
import streamlit as st

def next_turn_animation(month, is_event):
    message = st.empty()
    progress = st.progress(0)

    message.markdown(
        f"""
        <h2 style="text-align:center;">
        💹 {month}か月目へ進みます...
        </h2>
        """,
        unsafe_allow_html=True
    )

    for i in range(101):
        progress.progress(i)
        time.sleep(0.01)

    progress.empty()

    if is_event:
        message.markdown(
            """
            <h1 style="text-align:center;color:red;">
            ⚠ 相場が大きく動きました！
            </h1>
            """,
            unsafe_allow_html=True
        )
        time.sleep(1.2)
    else:
        message.markdown(
            """
            <h2 style="text-align:center;">
            📈 市場を更新しています...
            </h2>
            """,
            unsafe_allow_html=True
        )
        time.sleep(0.8)

    message.empty()