"""画面全体の表示倍率（ズーム）をユーザー自身で調整できるようにする共通部品。

対話AI（チャット欄）を追加したページ（simulation・today）は画面が縦に長くなり、
チャット入力欄の分だけ他の表示が窮屈に感じやすくなった。かといって固定で縮小すると
今度は文字が小さすぎて困る場面が出てくるはずなので、既定はやや小さめにしつつ、
いつでも自分で拡大・縮小できるようにする。

サイドバーに選択肢を出すだけで、実際の縮小・拡大は CSS の zoom を
メインコンテンツにだけかける（サイドバー自体・チャット入力欄は対象外にして、
操作しやすい大きさのまま保つ）。
"""

import streamlit as st

SCALE_OPTIONS = {
    "小さめ（80%）": 0.80,
    "やや小さめ（90%）": 0.90,
    "標準（100%）": 1.00,
    "やや大きめ（110%）": 1.10,
    "大きめ（125%）": 1.25,
}
DEFAULT_LABEL = "やや小さめ（90%）"
STATE_KEY = "ui_scale_label"


def render_scale_control():
    """サイドバーに表示倍率の選択肢を出す。ページの先頭付近で1回呼べばよい。"""
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = DEFAULT_LABEL
    with st.sidebar:
        st.selectbox("画面の大きさ", list(SCALE_OPTIONS.keys()), key=STATE_KEY)


def inject_scale_css():
    """選ばれている倍率を、メインコンテンツにだけ適用する
    （サイドバー・チャット入力欄〈固定表示のstBottomBlockContainer〉は対象外）。
    render_scale_control() より後に呼ぶこと（先に選択肢を確定させるため）。
    """
    label = st.session_state.get(STATE_KEY, DEFAULT_LABEL)
    scale = SCALE_OPTIONS.get(label, SCALE_OPTIONS[DEFAULT_LABEL])
    st.markdown(
        f"""<style>
        [data-testid="stMainBlockContainer"], .stMainBlockContainer {{
            zoom: {scale};
        }}
        </style>""",
        unsafe_allow_html=True,
    )
