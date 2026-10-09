# -*- coding: utf-8 -*-
"""パイロットのLLM利用量（llm_usage・dialogue_log）と、DBの書き込み量を集計する。ローカル専用。
使い方（Tursoの環境変数を設定した状態で）: python check_llm_usage.py
個人を特定する情報は出力しない。
"""
import statistics

from utils.storage import get_connection

TABLES = ["participants", "fin_literacy", "responses", "personalization_log", "post_survey",
          "progress", "participant_status", "dialogue_log", "llm_usage"]
NOT_TEST = "session_id NOT IN (SELECT session_id FROM test_sessions)"


def fetch(conn, sql):
    try:
        return conn.execute(sql).fetchall()
    except Exception as e:
        print("  （取得できませんでした）", str(e)[:80])
        return []


def main():
    conn = get_connection()

    print("【完了者の数（群ごと、テストを除く）】")
    done = fetch(conn, f"""SELECT p.group_no, COUNT(*) FROM participants p
                          JOIN participant_status ps ON ps.session_id = p.session_id
                          WHERE ps.survey_done_at IS NOT NULL AND p.{NOT_TEST}
                          GROUP BY p.group_no ORDER BY p.group_no""")
    group_done = {g: n for g, n in done}
    for g, n in done:
        print(f"  群{g}: {n} 人")
    total_done = sum(group_done.values())

    print("\n【LLM（対話AI）の利用量】")
    rows = fetch(conn, f"""SELECT u.session_id, p.group_no, COUNT(*), COALESCE(SUM(u.cost_usd), 0)
                          FROM llm_usage u JOIN participants p ON p.session_id = u.session_id
                          WHERE u.{NOT_TEST} GROUP BY u.session_id, p.group_no""")
    if not rows:
        print("  利用の記録なし（llm_usage が空、または表がない）")
    else:
        calls = [r[2] for r in rows]
        cost = sum(r[3] for r in rows)
        print(f"  利用した参加者: {len(rows)} 人 / 呼び出し合計: {sum(calls)} 回 / 費用合計: ${cost:.4f}")
        print(f"  1人あたりの呼び出し: 平均 {statistics.mean(calls):.1f}・中央値 {statistics.median(calls)}・最大 {max(calls)}")
        for g in sorted({r[1] for r in rows}):
            c = [r[2] for r in rows if r[1] == g]
            print(f"  群{g}: 利用者 {len(c)} 人（未完了者を含む。完了者は {group_done.get(g, '?')} 人。利用率は対話ログで見る）、平均 {statistics.mean(c):.1f} 回、最大 {max(c)} 回")
        if sum(calls):
            print(f"  1回あたりの費用: 平均 ${cost / sum(calls):.4f}")

    print("\n【対話AIへの質問（dialogue_log の role='user'、群ごと）】")
    for g, n_users, n_msgs in fetch(conn, f"""SELECT p.group_no, COUNT(DISTINCT d.session_id), COUNT(*)
                                             FROM dialogue_log d JOIN participants p ON p.session_id = d.session_id
                                             WHERE d.role = 'user' AND d.{NOT_TEST} GROUP BY p.group_no ORDER BY p.group_no"""):
        print(f"  群{g}: 質問した参加者 {n_users} 人、質問 {n_msgs} 件")

    print("\n【DBの行数（テストを含む全体）。1,000人に引き伸ばす目安】")
    sums = 0
    for t in TABLES:
        r = fetch(conn, f"SELECT COUNT(*) FROM {t}")
        n = r[0][0] if r else None
        if n is not None:
            sums += n
        print(f"  {t}: {n}")
    if total_done:
        print(f"  合計 {sums} 行 ÷ 完了者 {total_done} 人 ≒ 1人あたり {sums / total_done:.0f} 行"
              f" → 1,000人なら約 {sums / total_done * 1000:,.0f} 行（未完了者の分を含むので、やや多めの見積もり）")
    conn.close()


if __name__ == "__main__":
    main()
