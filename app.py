import streamlit as st

from utils.storage import init_results_db, load_progress_by_code, get_progress_status
from utils.components.ui_scale import render_scale_control, inject_scale_css

st.set_page_config(
    page_title="長期投資実験",
    layout="wide"
)

render_scale_control()
inject_scale_css()

init_results_db()

st.title("長期投資シミュレーション実験")

# 進行中の実験があれば、appページに来ても再開番号と残り日数がすぐ分かるようにする
status = get_progress_status(st.session_state.get("session_id"))
if status:
    resume_code, remaining_days = status
    st.info(f"進行中の実験があります（再開番号: {resume_code} ／ 期限まで残り{remaining_days}日）")

st.markdown("---")

group = st.selectbox(
    "実験群を選択してください",
    ["群1（知識のみ）", "群2（AIあり）", "群3（パーソナライズ）"]
)

if st.button("実験開始"):

    if "群1" in group:
        st.session_state.group = 1
    elif "群3" in group:
        st.session_state.group = 3
    else:
        st.session_state.group = 2
    st.session_state.turn = 0

    st.switch_page("pages/01_pre_questionnaire.py")

st.markdown("---")
st.subheader("途中から再開する")
st.caption("前回発行された番号を入力してください。開始から1週間を過ぎた場合は再開できません。")

resume_input = st.text_input("再開番号", max_chars=6, key="resume_input")
if st.button("再開する"):
    result = load_progress_by_code(resume_input)
    if result is None:
        st.error("その番号は見つかりませんでした。番号を確認してもう一度お試しください。")
    else:
        state, session_id, is_expired = result
        if is_expired:
            st.error(
                "開始から1週間を過ぎているため、この実験は再開できません。"
                "恐れ入りますが、この続きは無効となります。"
            )
        else:
            st.session_state.session_id = session_id
            st.session_state.resume_code = resume_input.strip().upper()
            st.session_state.nickname = state.get("nickname")
            st.session_state.age = state.get("age")
            st.session_state.overconfidence = state.get("overconfidence")
            st.session_state.initial_invest = state.get("initial_invest")
            st.session_state.monthly_invest = state.get("monthly_invest")
            st.session_state.group = state.get("group", 1)
            st.session_state.participant_no = state.get("participant_no")
            st.session_state.month_idx = state.get("month_idx", 0)
            # JSON化で decisions のキー（月番号）が文字列になっているので int に戻す
            st.session_state.decisions = {
                int(k): v for k, v in (state.get("decisions") or {}).items()
            }
            st.session_state.history = state.get("history") or []
            st.session_state.scroll_top = True
            st.switch_page("pages/02_simulation.py")
