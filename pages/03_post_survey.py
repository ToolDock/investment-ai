import streamlit as st

from utils.post_survey import LIKERT5, FREE, ATTENTION, items_for, recall_for
from utils.storage import save_post_survey
from utils.components.ui_scale import render_scale_control, inject_scale_css

st.set_page_config(page_title="事後アンケート", layout="centered")

render_scale_control()
inject_scale_css()

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
    # 注意チェックの通過可否は分析時に使う（この場では participants に触れない）
    st.session_state.attention_passed = (
        answers.get(ATTENTION["id"]) == ATTENTION["correct"])
    st.success("ご協力ありがとうございました。これで終了です。")
    st.balloons()
