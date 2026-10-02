import streamlit as st

from utils.post_survey import LIKERT5, FREE, ATTENTION, items_for, recall_for
from utils.storage import save_post_survey, mark_survey_done, get_completion_info
from utils.components.ui_scale import render_scale_control, inject_scale_css
from utils.components.scroll import scroll_to_top
from utils.rank import reward_rank, rank_task_url

st.set_page_config(page_title="事後アンケート", layout="centered")

render_scale_control()
inject_scale_css()

# 提出後の案内文。支払いの方法が決まったら、ここだけ直す
PAYMENT_NOTE = ("提出いただいた内容を、シミュレーションの結果と照合します。"
                "確認が取れ次第、報酬をお支払いします。")


def _show_completion(sid):
    """アンケート送信後の完了画面。完了コードと成績ランク、追加報酬タスクへの案内を出す。

    金額そのものは画面に出さない。ランクに対応する追加報酬タスクで、完了コードを提出して
    もらい、DBのランクと payout_report.py --tier で照合する。2026-10-02
    """
    info = get_completion_info(sid) or {}
    # 前の画面でスクロールしたまま来ても、完了コードが見える位置から始める
    scroll_to_top("_scrolled_done")
    st.success("ご協力ありがとうございました。実験はすべて終了です。")
    if st.session_state.pop("_just_finished", False):
        st.balloons()

    code = info.get("resume_code") or st.session_state.get("resume_code")
    rank = reward_rank(info.get("reward_yen"))
    if code and rank:
        st.markdown("### 報酬を受け取るために、あと2つ提出してください")
        st.warning("**この画面を閉じる前に、下の①と②の両方を、クラウドワークスで提出してください。**"
                   "②を提出しないと、追加報酬は支払われません。")
        st.markdown("**あなたの完了コード**（表示されているとおりにコピーしてください）")
        st.code(code)
        st.markdown(f"**あなたの成績ランク：ランク {rank}**")
        st.info("**① いま受けているタスクに、上の完了コードを提出する**\n\n"
                "（実験の募集ページに戻り、完了コードを貼り付けて提出します。これで参加賞が支払われます）")
        url = rank_task_url(rank)
        st.info(f"**② 追加報酬のタスク「追加報酬 ランク{rank}」に、同じ完了コードを提出する**\n\n"
                f"（クラウドワークスで「【実験参加者限定】追加報酬 ランク{rank}」を探して提出します。"
                "ランクが違うタスクに提出しても支払われません）")
        if url:
            st.link_button(f"② 追加報酬 ランク{rank} のタスクを開く", url, type="primary")
        st.caption("この画面を閉じてしまっても、同じブラウザでこの実験のURLを開くと、この画面がもう一度表示されます。")
    else:
        st.warning("提出用の情報を表示できませんでした。このまま画面を閉じず、"
                   "クラウドワークスのメッセージでお知らせください。")

    if info.get("final_asset") is not None:
        st.divider()
        st.markdown("### あなたの結果")
        profit = info.get("profit") or 0
        c1, c2 = st.columns(2)
        c1.metric("最終資産", f"{info['final_asset']:,} 円")
        c2.metric("損益", f"{profit:+,} 円")

    st.divider()
    st.markdown(PAYMENT_NOTE)
    st.caption("この画面は閉じて構いません。不明な点や不具合は、クラウドワークスのメッセージでお知らせください。")


_sid = st.session_state.get("session_id")
if _sid:
    # 完了済みかどうかは、この画面を開いたときに一度だけDBで確かめる（操作のたびに通信しない）
    if "survey_done" not in st.session_state:
        _info = get_completion_info(_sid)
        st.session_state.survey_done = bool(_info and _info["survey_done"])
    if st.session_state.survey_done:
        st.title("実験の完了")
        _show_completion(_sid)
        st.stop()

scroll_to_top("_scrolled_survey")
st.title("事後アンケート")
st.write("シミュレーションはこれで終わりです。最後にいくつか質問させてください。")

group = st.session_state.get("group", 1)
final_asset = st.session_state.get("final_asset")
if final_asset is not None:
    st.metric("最終資産", f"{final_asset:,} 円")

st.divider()

items = items_for(group)
answers = {}

for i, item in enumerate(items, 1):
    st.markdown(f"**Q{i}. {item['text']}**")
    a = st.radio(
        "回答", LIKERT5, index=None, horizontal=True,
        key=f"post_{item['id']}", label_visibility="collapsed",
    )
    answers[item["id"]] = (LIKERT5.index(a) + 1) if a else None
    st.write("")

st.divider()
st.caption("以下は、内容を覚えているかどうかの確認です。分からなければ「覚えていない」を選んでください。")

for item in recall_for(group):
    st.markdown(f"**{item['text']}**")
    a = st.radio(
        "回答", item["options"], index=None,
        key=f"post_{item['id']}", label_visibility="collapsed",
    )
    answers[item["id"]] = (item["options"].index(a) + 1) if a else None
    st.write("")

st.divider()

texts = {}
for item in FREE:
    st.markdown(f"**{item['text']}**")
    texts[item["id"]] = st.text_area(
        "自由記述", key=f"post_{item['id']}", label_visibility="collapsed", height=100)
    st.write("")

missing = any(v is None for v in answers.values())
if missing:
    st.info("すべての設問に回答すると、送信できます。")

if st.button("回答を送信して終了", width="stretch", disabled=missing):
    sid = st.session_state.get("session_id")
    if sid:
        save_post_survey(sid, answers, texts)
        mark_survey_done(sid)
    # 注意チェックの通過可否は分析時に使う（この場では participants に触れない）
    st.session_state.attention_passed = (
        answers.get(ATTENTION["id"]) == ATTENTION["correct"])
    if sid:
        st.session_state.survey_done = True
        st.session_state._just_finished = True
        st.rerun()
    st.success("ご協力ありがとうございました。これで終了です。")
    st.balloons()
