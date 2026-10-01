"""クラウドワークスの作業結果CSVと実験DBを突き合わせ、報酬の一覧を作る。

    python payout_report.py 作業結果.csv                 完了番号を探して報酬を付ける
    python payout_report.py 作業結果.csv --id-col ワーカーID   ワーカー識別の列を指定（出力に残す）
    python payout_report.py 作業結果.csv --code-col 完了コードの列名 --value-col 確認値の列名
                                                         参加者が貼り付けた確認値をDBの報酬額と照合する
    python payout_report.py --all                         CSVなしで、完了済みの全員の報酬を出す

出力: payout.csv（行ごとの状態と報酬）、payout_summary.txt（報酬額ごとの人数と合計）
CSVの列名が分からなくても、各セルから6桁の完了番号らしい文字列を探して照合する。
状態: OK / 番号なし / 未完了（アンケート未送信）/ 重複（同じ番号が複数行にある）/ 値不一致（貼り付けた確認値がDBの報酬額と違う）
"""

import argparse
import csv
import re
import sys
from collections import Counter

from utils.storage import get_connection

CODE = re.compile(r"\b[2-9A-HJ-NP-Z]{6}\b")


def load_db():
    conn = get_connection()
    rows = conn.execute(
        """SELECT pr.resume_code, p.group_no, p.final_asset, p.profit, p.reward_yen,
                  ps.survey_done_at
           FROM progress pr
           JOIN participants p ON p.session_id = pr.session_id
           LEFT JOIN participant_status ps ON ps.session_id = pr.session_id"""
    ).fetchall()
    conn.close()
    return {r[0]: {"group": r[1], "final_asset": r[2], "profit": r[3],
                   "reward": r[4], "survey_done_at": r[5]} for r in rows}


def read_csv(path):
    for enc in ("utf-8-sig", "cp932"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit("CSVの文字コードを読めませんでした（utf-8 / cp932 以外）")


def parse_value(text):
    """貼り付けられた確認値を整数にする。全角数字・「円」・カンマ・空白まじりも読む。"""
    t = (text or "").translate(str.maketrans("０１２３４５６７８９，", "0123456789,"))
    digits = re.sub(r"[^0-9]", "", t.replace("円", ""))
    return int(digits) if digits else None


def find_code(row, db, col=None):
    """行の各セルから、DBにある完了番号を探す。小文字・空白まじりの入力も拾う。
    col を指定すると、その列だけを見る。"""
    cells = [row.get(col, "")] if col else row.values()
    for v in cells:
        text = (v or "").upper().replace(" ", "").replace("　", "")
        for m in CODE.findall(text):
            if m in db:
                return m
        # 入力に区切りが無く、他の文字と続いている場合のため、短い回答ならそのまま照合
        if len(text) == 6 and text in db:
            return text
    return None


def summarize(rows, out_path):
    ok = [r for r in rows if r["状態"] == "OK"]
    c = Counter(r["報酬(円)"] for r in ok)
    lines = [f"行数 {len(rows)} / OK {len(ok)} / 要確認 {len(rows) - len(ok)}",
             f"OKの報酬合計 {sum(r['報酬(円)'] for r in ok):,} 円", "", "報酬額ごとの人数:"]
    for amt in sorted(c):
        lines.append(f"  {amt:>4} 円 × {c[amt]} 人")
    bad = Counter(r["状態"] for r in rows if r["状態"] != "OK")
    if bad:
        lines += ["", "要確認の内訳:"] + [f"  {k}: {v}" for k, v in bad.items()]
    text = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--id-col")
    ap.add_argument("--code-col", help="完了コードの列名（省略時は全列から探す）")
    ap.add_argument("--value-col", help="確認値の列名。指定するとDBの報酬額と照合する")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    db = load_db()
    out = []
    if a.all or not a.csv:
        for code, d in db.items():
            if d["survey_done_at"]:
                out.append({"ワーカー": "", "完了番号": code, "群": d["group"],
                            "状態": "OK", "報酬(円)": d["reward"]})
    else:
        seen = Counter()
        rows = read_csv(a.csv)
        codes = [find_code(r, db, a.code_col) for r in rows]
        seen.update(c for c in codes if c)
        for r, code in zip(rows, codes):
            wid = r.get(a.id_col, "") if a.id_col else ""
            if not code:
                out.append({"ワーカー": wid, "完了番号": "", "群": "", "状態": "番号なし", "報酬(円)": "",
                            "申告値": "", "DBの報酬額": ""})
                continue
            d = db[code]
            claimed = parse_value(r.get(a.value_col, "")) if a.value_col else None
            if not d["survey_done_at"]:
                status = "未完了"
            elif seen[code] > 1:
                status = "重複"
            elif a.value_col and claimed != d["reward"]:
                status = "値不一致"
            else:
                status = "OK"
            out.append({"ワーカー": wid, "完了番号": code, "群": d["group"],
                        "状態": status, "報酬(円)": d["reward"] if status == "OK" else "",
                        "申告値": "" if claimed is None else claimed, "DBの報酬額": d["reward"]})

    with open("payout.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ワーカー", "完了番号", "群", "状態", "報酬(円)", "申告値", "DBの報酬額"],
                           restval="")
        w.writeheader()
        w.writerows(out)
    summarize([{**r, "報酬(円)": r["報酬(円)"] if r["報酬(円)"] != "" else 0} for r in out],
              "payout_summary.txt")
    print("\n-> payout.csv / payout_summary.txt")


if __name__ == "__main__":
    sys.exit(main())
