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
# 選択肢を触るたびに通信しないよう、同じ session_id のあいだは結果を使い回す
_sid = st.session_state.get("session_id")
if "_app_status" not in st.session_state or st.session_state.get("_app_status_sid") != _sid:
    st.session_state["_app_status"] = get_progress_status(_sid)
    st.session_state["_app_status_sid"] = _sid
status = st.session_state["_app_status"]
if status:
    resume_code, remaining_days = status
    st.info(f"進行中の実験があります（再開番号: {resume_code} ／ 期限まで残り{remaining_days}日）")

st.markdown("---")

# 募集ページごとに URL の ?g=2 / ?g=3 で群を固定する（参加者に群の名前を見せない）。
# 指定がないときだけ、従来どおり選択欄を出す（開発・確認用）
_GROUP_LABELS = ["群1（知識のみ）", "群2（AIあり）", "群3（パーソナライズ）"]
_g = st.query_params.get("g")
if _g in ("1", "2", "3"):
    group = _GROUP_LABELS[int(_g) - 1]
else:
    group = st.selectbox("実験群を選択してください", _GROUP_LABELS)

st.subheader("研究へのご協力のお願い")
st.markdown(
    """
この実験は、長期投資を続けるときの情報の提供のしかたが、投資の判断にどう影響するかを調べる研究です。
仮想の資金で、60か月分の積立投資をシミュレーションしていただきます（現実のお金は動きません）。

**記録するもの**：年齢・性別・投資経験・金融知識に関する設問への回答、シミュレーション中の売買などの選択、
アンケートへの回答、AIとの対話の内容。氏名・メールアドレス・住所など、個人を特定する情報は集めません。
ニックネームは画面上の表示にのみ使い、記録しません。

**データの扱い**：研究の目的にのみ使い、結果は統計的にまとめて発表します。個人が特定される形では公表しません。

**参加について**：参加は任意です。途中でやめても不利益はありません。
途中でやめたい場合は、画面を閉じてください（再開番号を使えば、開始から1週間は続きから再開できます）。
"""
)
consented = st.checkbox("上記の内容を読み、同意して参加します")

if st.button("実験開始", disabled=not consented):

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
