import os
import re
import json
import streamlit as st

from utils.components.visual import show_visual
from utils.visuals import TITLES

KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "knowledge",
    "long_term_investing.json",
)


@st.cache_data
def load_knowledge():
    with open(KB_PATH, encoding="utf-8") as f:
        raw = f.read()
    # 執筆者向けの「出典を確認する」印は、参加者の画面に出さない
    raw = re.sub(r"【要出典確認[^】\"]*】", "", raw)
    return json.loads(raw)


def _relevant_quotes(kb, phase, situation=None):
    """局面一致＋状況(situation)一致を最優先し、無ければ局面一致＋全局面共通、
    それも無ければ全局面共通のみにフォールバックする。

    2026-09-23: generate_daily_report.pyのpick_quote()と同じ考え方に揃えた
    （状況による優先選定、"all"タグの金言を死蔵させない）。
    """
    quotes = kb.get("quotes", [])
    specific = [q for q in quotes if phase in q.get("phase_tags", [])]
    general = [q for q in quotes if "all" in q.get("phase_tags", [])]
    situational = [q for q in specific
                   if situation and situation in q.get("situation_tags", [])]
    return situational or (specific + general) or general


def show_reference(phase, kb=None, timeline=None, month=None, situation=None):
    """長期投資の参考書。全群共通の知識。現局面に関連する見方＋金言を前面に出し、
    全体は展開できるようにする。"""
    kb = kb or load_knowledge()

    st.subheader("📘 長期投資の参考書")

    modules = [m for m in kb.get("phase_modules", []) if m["phase"] == phase]
    quotes = _relevant_quotes(kb, phase, situation)

    with st.container(border=True):
        if modules:
            for m in modules:
                st.markdown(f"**{m['title']}**")
                st.write(m["body"])
                if m.get("psychological_effect"):
                    st.caption(f"ねらい：{m['psychological_effect']}")
        else:
            # この局面のモジュールが未整備でも、基礎原則を土台として示す
            st.caption("この局面では、まず長期投資の基礎に立ち返りましょう（下の『参考書の全体』を参照）。")

        if quotes:
            # 常に先頭固定だと、同じ局面が続く間ずっと同じ金言になる（2026-09-22、
            # 「金言が効果的に使われていない」という指摘を受けての見直しの一環。
            # generate_daily_report.pyのpick_quote()と同じ、月番号によるローテーション）
            q = quotes[(month - 1) % len(quotes)] if month else quotes[0]
            st.markdown(f"> {q['quote_ja']}　— {q['author']}")

    with st.expander("データで見る（全局面共通）"):
        # 全群が同じ図を持つ。日報はここを指し示すだけ
        for cid in TITLES:
            show_visual(cid, timeline, month, where="ref")

    with st.expander("参考書の全体を見る"):
        st.markdown("#### 基礎原則")
        for p in kb.get("principles", []):
            st.markdown(f"**{p['title']}**")
            st.write(p["body"])
            if p.get("key_points"):
                st.markdown("\n".join(f"- {k}" for k in p["key_points"]))
            st.write("")

        st.markdown("#### 局面別の見方")
        for m in kb.get("phase_modules", []):
            st.markdown(f"**［{m['phase']}］{m['title']}**")
            st.write(m["body"])

        st.markdown("#### 投資家の金言")
        for q in kb.get("quotes", []):
            st.markdown(f"> {q['quote_ja']}　— {q['author']}")
