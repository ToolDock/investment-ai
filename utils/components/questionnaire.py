import streamlit as st

LIKERT = [
    "全くそう思わない",
    "あまりそう思わない",
    "どちらともいえない",
    "ややそう思う",
    "非常にそう思う"
]


def show_questionnaire(items, key_suffix=""):
    st.subheader("アンケート")

    answers = {}

    for item in items:
        choice = st.radio(
            item["text"],
            LIKERT,
            horizontal=True,
            index=None,
            key=f"q_{item['id']}_{key_suffix}",
        )
        answers[item["id"]] = (LIKERT.index(choice) + 1) if choice else None

    return answers
