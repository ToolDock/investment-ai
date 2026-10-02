from datetime import datetime

import streamlit as st

from utils.storage import (init_results_db, load_progress_by_code, get_progress_status,
                           get_completion_info)
from utils.components.ui_scale import render_scale_control, inject_scale_css
from utils.participation_guard import is_test_mode, prior_participant_sid

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

# 二度目の参加を防ぐ。同じブラウザで以前に参加していたら、新しく始められないようにする
# （?test=1 を付けた動作確認では通す）
if is_test_mode():
    st.caption("🔧 動作確認モード：参加者の集計・報酬には含まれません。")
_prior = prior_participant_sid()
_prior_info = get_completion_info(_prior) if _prior else None
if _prior and _prior_info is None:
    _prior = None      # 記録が無いセッションIDは無視する（DBの入れ替え後など）

if _prior and _prior_info.get("survey_done"):
    # 最後まで終えている人には、完了コードと確認値を出す画面をそのまま見せる
    # （提出前に画面を閉じてしまった人が、値を確認し直せるように）
    st.session_state["session_id"] = _prior
    st.session_state.pop("survey_done", None)
    st.switch_page("pages/03_post_survey.py")

if _prior:
    st.subheader("すでに参加が記録されています")
    st.info(
        "この実験への参加は、お一人につき1回です。このブラウザでは、すでに参加が記録されています。\n\n"
        "続きから再開する、または完了画面を表示するには、下の「再開番号」を入力してください"
        "（シミュレーションの画面の左側、または最後の完了画面に表示されていた6桁の番号です）。"
        "番号が分からない場合は、クラウドワークスのメッセージでお知らせください。"
    )
else:
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
        "長期投資を続けるときの情報の提供のしかたが、投資の判断にどう影響するかを調べる研究です。\n\n"
        "仮想の資金で、**60か月分の積立投資**を体験していただきます（現実のお金は動きません）。"
    )

    st.markdown("#### 参加の流れ")
    st.markdown(
        "1. **事前アンケート**（年齢・性別・投資経験・金融知識など）\n"
        "2. **60か月分のシミュレーション**（毎月、市況や日報を読んで、買い増し・売却・積立額の変更などを選びます）\n"
        "3. **事後アンケート**（終了後に表示される「完了コード」と「確認値」を、クラウドワークスの回答欄に貼り付けて提出します）"
    )

    st.info(
        "#### 報酬について\n\n"
        "**本タスクの報酬額は、このシミュレーション内の投資行動によって得たあなたの最終利益によって決定します。**\n\n"
        "**あなたがすべきことは、資産を最大化し、60か月でより多くの利益を獲得することです。**"
    )

    st.markdown("#### 個人情報とデータの扱い")
    st.markdown(
        "- **記録するもの**：年齢・性別・投資経験・金融知識に関する設問への回答、シミュレーション中の売買などの選択、"
        "アンケートへの回答、AIとの対話の内容\n"
        "- 氏名・メールアドレス・住所など、**個人を特定する情報は集めません**。ニックネームは画面上の表示にのみ使い、記録しません\n"
        "- データは研究の目的にのみ使い、結果は統計的にまとめて発表します。個人が特定される形では公表しません"
    )

    st.markdown("#### 参加について")
    st.markdown(
        "- 参加は任意です。**途中でやめても不利益はありません**\n"
        "- 参加はお一人につき1回です\n"
        "- 途中でやめたいときは、画面を閉じてください。再開番号を使えば、開始から1週間は続きから再開できます"
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
        # 同意した日時。参加者が登録される事前アンケートの送信時に、DBへ記録する
        st.session_state.consented_at = datetime.now().isoformat()

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
            # すでに終えた番号は、プレイ画面ではなく完了画面へ（再プレイ・二重送信の防止）
            done = get_completion_info(session_id)
            if done and done["sim_done"]:
                st.session_state.group = state.get("group", 1)
                st.session_state.final_asset = done["final_asset"]
                st.session_state.simulation_done = True
                st.session_state.survey_done = done["survey_done"]
                st.switch_page("pages/03_post_survey.py")
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
