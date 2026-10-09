# -*- coding: utf-8 -*-
"""LLM分析用に、対話ログと自由記述を、匿名化して書き出す。ローカル専用。
使い方（Tursoの環境変数を設定した状態で）: python export_text_for_llm.py
出力: pilot_dialogue.csv（pid, group, completed, month, turn, role, content, pii_flag）
      pilot_free_text.csv（pid, group, completed, qid, text, pii_flag）
pid は analyze_pilot.py と同じ連番（pilot_features.csv と結べる）。session_id・ワーカーIDは書かない。
pii_flag=1 の行は、メール・URL・長い数字列を含む。LLMに渡す前に、目視で確認して消す。
"""
import csv
import re

from utils.storage import get_connection

NOT_TEST = "session_id NOT IN (SELECT session_id FROM test_sessions)"
PII = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|https?://|www\.|\d{9,}")


def main():
    conn = get_connection()
    parts = conn.execute(f"SELECT session_id, group_no FROM participants WHERE {NOT_TEST} ORDER BY participant_no").fetchall()
    done = {r[0] for r in conn.execute("SELECT session_id FROM participant_status WHERE survey_done_at IS NOT NULL").fetchall()}
    info = {sid: (pid, g, int(sid in done)) for pid, (sid, g) in enumerate(parts, 1)}

    turns, d_rows = {}, []
    for sid, month, role, content in conn.execute(
            f"SELECT session_id, month, role, content FROM dialogue_log WHERE {NOT_TEST} ORDER BY id").fetchall():
        if sid not in info:
            continue
        pid, g, c = info[sid]
        turns[pid] = turns.get(pid, 0) + 1
        d_rows.append([pid, g, c, month, turns[pid], role, content, int(bool(PII.search(content or "")))])

    t_rows = []
    for sid, qid, text in conn.execute(
            "SELECT session_id, qid, text FROM post_survey WHERE text IS NOT NULL AND text <> ''").fetchall():
        if sid not in info:
            continue
        pid, g, c = info[sid]
        t_rows.append([pid, g, c, qid, text, int(bool(PII.search(text)))])
    conn.close()

    for path, head, rows in (("pilot_dialogue.csv", ["pid", "group", "completed", "month", "turn", "role", "content", "pii_flag"], d_rows),
                             ("pilot_free_text.csv", ["pid", "group", "completed", "qid", "text", "pii_flag"], t_rows)):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(rows)
    users = [r for r in d_rows if r[5] == "user"]
    print(f"対話: {len(d_rows)} 行（質問 {len(users)} 件、参加者 {len({r[0] for r in users})} 人）→ pilot_dialogue.csv")
    print(f"自由記述: {len(t_rows)} 件 → pilot_free_text.csv")
    print(f"個人情報の疑い（pii_flag=1）: 対話 {sum(r[7] for r in d_rows)} 行、自由記述 {sum(r[5] for r in t_rows)} 件。LLMに渡す前に確認して消す。")


if __name__ == "__main__":
    main()
