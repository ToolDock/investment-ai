import uuid
import streamlit as st

from utils.storage import init_results_db, create_participant, save_fin_literacy, save_progress
from utils.pre_survey import (
    GENDER_OPTIONS,
    INVEST_EXPERIENCE_OPTIONS,
    INVEST_YEARS_OPTIONS,
    SELF_RANK_OPTIONS,
    FIN_LITERACY,
    CONFIDENCE_OPTIONS,
    score_literacy,
)

INITIAL_CASH = 500000    # 初期資産
MONTHLY_BUDGET = 50000   # 毎月の余剰資金

st.title("事前アンケート")

init_results_db()

# ブラウザバック等でこのページに戻ってきても、下の「シミュレーション開始」を
# 押すと進行中のデータが無条件に上書きされてしまう。誤操作を防ぐため先に警告する
if st.session_state.get("session_id") and st.session_state.get("resume_code"):
    st.warning(
        f"進行中の実験があります（再開番号: {st.session_state.resume_code}）。"
        "このまま下のフォームを送信すると、進行中のデータは新しい実験として"
        "上書きされます。続きに戻る場合は下のボタンを押してください。"
    )
    if st.button("進行中の実験に戻る"):
        st.switch_page("pages/02_simulation.py")
    st.divider()

# ── 属性 ─────────────────────────────
st.subheader("あなたについて")

nickname = st.text_input(
    "日報の中で呼びかける名前を入力してください",
    max_chars=12,
    placeholder="ニックネームで構いません",
    help="実名である必要はありません。この名前は記録されず、画面上の表示にのみ使われます。",
)

invest_experience = st.radio(
    "投資経験について教えてください",
    INVEST_EXPERIENCE_OPTIONS,
    index=None,
)

invest_years = st.radio(
    "投資歴（投資をしていた期間の合計）はどのくらいですか",
    INVEST_YEARS_OPTIONS,
    index=None,
)

age = st.number_input("年齢", min_value=18, max_value=100, value=30, step=1)

gender = st.radio(
    "性別",
    GENDER_OPTIONS,
    index=None,
    horizontal=True,
)

st.divider()

# ── 金融リテラシー・自信度 ─────────────────
st.subheader("金融・投資に関する質問")

self_rank = st.radio(
    "はじめに：ご自身の金融・投資の知識は、同年代と比べてどの程度だと思いますか",
    SELF_RANK_OPTIONS,
    index=None,
)

st.caption("以下の各問について、答えと「その答えにどのくらい自信があるか」を選んでください。")

lit_answers = {}
for i, item in enumerate(FIN_LITERACY, 1):
    st.markdown(f"**Q{i}. {item['text']}**")
    ans = st.radio(
        "答え",
        item["options"],
        index=None,
        key=f"lit_ans_{item['id']}",
        label_visibility="collapsed",
    )
    conf = st.radio(
        "この答えへの自信",
        CONFIDENCE_OPTIONS,
        index=None,
        horizontal=True,
        key=f"lit_conf_{item['id']}",
    )
    lit_answers[item["id"]] = {
        "answer": ans,
        "confidence": (CONFIDENCE_OPTIONS.index(conf) + 1) if conf else None,
    }
    st.write("")

st.divider()

# ── 初期設定 ─────────────────────────
st.subheader("初期設定")

st.write(f"初期資産は {INITIAL_CASH:,} 円、毎月の余剰資金は {MONTHLY_BUDGET:,} 円です。")


def _parse_amount(raw, max_value):
    # 数値欄をあらかじめ全額投資で埋めてしまうと、何も考えずに送信した人の現金が
    # 実質0円で固定されてしまう（増し買いの選択肢が最初から失われる）。他の設問と
    # 同じく「未回答は空欄のまま」にし、必ず自分で金額を入力させることで、
    # 全額投資も現金を残すのも、どちらも本人の意思による選択にする
    s = (raw or "").strip().replace(",", "")
    if not s.isdigit():
        return None
    value = int(s)
    if value < 0 or value > max_value:
        return None
    return value


initial_invest_raw = st.text_input(
    f"初期資産 {INITIAL_CASH:,} 円のうち、いくらを投資しますか？（円）",
    placeholder=f"0〜{INITIAL_CASH:,} の範囲で半角数字を入力",
    help="投資しなかった分は現金資産として保有し、あとで買い増しにも使えます。",
)

monthly_invest_raw = st.text_input(
    f"毎月の余剰資金 {MONTHLY_BUDGET:,} 円のうち、いくらを積立しますか？（円）",
    placeholder=f"0〜{MONTHLY_BUDGET:,} の範囲で半角数字を入力",
    help="積立しなかった分は毎月の現金資産として加算されます（あとから変更できます）。",
)

initial_invest = _parse_amount(initial_invest_raw, INITIAL_CASH)
monthly_invest = _parse_amount(monthly_invest_raw, MONTHLY_BUDGET)

if initial_invest_raw and initial_invest is None:
    st.warning(f"初期資産は0〜{INITIAL_CASH:,}円の整数で入力してください。")
if monthly_invest_raw and monthly_invest is None:
    st.warning(f"毎月の積立額は0〜{MONTHLY_BUDGET:,}円の整数で入力してください。")

if initial_invest is not None and monthly_invest is not None:
    st.caption(
        f"→ 初期投資 {initial_invest:,} 円／現金 {INITIAL_CASH - initial_invest:,} 円、"
        f"毎月 積立 {monthly_invest:,} 円／現金 {MONTHLY_BUDGET - monthly_invest:,} 円"
    )

st.divider()

# ── 回答完了チェック ─────────────────────
missing = (
    invest_experience is None
    or invest_years is None
    or gender is None
    or self_rank is None
    or any(v["answer"] is None or v["confidence"] is None for v in lit_answers.values())
    or initial_invest is None
    or monthly_invest is None
)

if missing:
    st.info("すべての質問に回答すると、シミュレーションを開始できます。")

if st.button("シミュレーション開始", width="stretch", disabled=missing):
    result = score_literacy(lit_answers)

    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.nickname = (nickname or "").strip() or "guest"
    st.session_state.age = int(age)
    # 群3のパーソナライズはこの値を使う（事前属性は1か月目から効く）
    st.session_state.overconfidence = result["overconfidence"]
    st.session_state.initial_invest = int(initial_invest)
    st.session_state.monthly_invest = int(monthly_invest)

    # シミュレーション状態を初期化（再挑戦時に前回の状態を持ち越さない）
    st.session_state.turn = 0
    st.session_state.decisions = {}
    st.session_state.history = []

    participant_no = create_participant(
        st.session_state.session_id,
        st.session_state.get("group", 1),
        int(age),
        gender,
        invest_experience,
        invest_years,
        self_rank,
        result["score"],
        result["conf_mean"],
        result["overconfidence"],
        int(initial_invest),
        int(monthly_invest),
    )
    st.session_state.participant_no = participant_no

    save_fin_literacy(participant_no, result["detail"])

    # 中断・再開用の進捗スナップショットを最初に保存し、再開コードを発行する。
    # 以降はシミュレーション側で毎ターン上書き保存する
    st.session_state.resume_code = save_progress(st.session_state.session_id, {
        "nickname": st.session_state.nickname,
        "age": st.session_state.age,
        "overconfidence": st.session_state.overconfidence,
        "initial_invest": st.session_state.initial_invest,
        "monthly_invest": st.session_state.monthly_invest,
        "group": st.session_state.get("group", 1),
        "participant_no": participant_no,
        "month_idx": 0,
        "decisions": {},
        "history": [],
    })

    st.switch_page("pages/02_simulation.py")
