"""成績ランク。報酬の合計（参加賞10円＋利益÷30,000円）から、5段階のランクと追加報酬を決める。

参加賞10円は1段目のタスクで全員に支払う。追加報酬はランクごとのタスクで支払う。
"""

# (報酬合計の下限, ランク, 追加報酬の円)
TIERS = [(50, "S", 45), (40, "A", 35), (30, "B", 25), (20, "C", 15), (0, "D", 5)]
RANKS = [t[1] for t in TIERS]


def reward_rank(reward_yen):
    """報酬合計（円）からランクを返す。値が無ければ None。"""
    if reward_yen is None:
        return None
    for lower, rank, _ in TIERS:
        if reward_yen >= lower:
            return rank
    return TIERS[-1][1]


def rank_extra(rank):
    """ランクの追加報酬（円）。"""
    for _, r, extra in TIERS:
        if r == rank:
            return extra
    return None


def rank_task_url(rank):
    """そのランクの追加報酬タスクのURL。設定（secretsの rank_task_urls）に無ければ None。"""
    try:
        import streamlit as st
        urls = st.secrets.get("rank_task_urls", {})
        return urls.get(rank) or None
    except Exception:
        return None
