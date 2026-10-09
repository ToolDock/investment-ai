# -*- coding: utf-8 -*-
"""対話ログを、LLMで分類・評価する。ローカル専用（APIキーは .env から読む）。
入力: pilot_dialogue.csv, pilot_months.csv（コーディング用シートだけなら coding_key.csv も）
出力: llm_utterance_codes.csv（発話のコード）, llm_response_scores.csv（応答の評価）
使い方:
  python classify_dialogue.py --scope sheet      # シートの50件だけ（人手との一致度用）
  python classify_dialogue.py --scope all        # 全件
  python classify_dialogue.py --dry-run          # APIを呼ばず、1件目のプロンプトだけ表示
  --task utterance|response|both   --limit N
判定モデルは環境変数 JUDGE_MODEL（応答の生成に使うモデルとは別にする）。群の情報はLLMに渡さない。
途中で止まっても、出力済みの行はスキップして再開する。
"""
import argparse
import csv
import json
import os
import re
import sys
import time

from coding_defs import CODES, CODE_RULES, RUBRIC, RUBRIC_KEYS

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-opus-5")
# 単価（USD/100万トークン）。判定モデルに合わせて環境変数で上書きする
PRICE_IN = float(os.getenv("JUDGE_PRICE_IN", "5"))
PRICE_OUT = float(os.getenv("JUDGE_PRICE_OUT", "25"))
UTT_OUT, RESP_OUT = "llm_utterance_codes.csv", "llm_response_scores.csv"

CONTEXT = ("これは、仮想の資金で60か月分の積立投資を体験する実験の、対話ログです。"
           "参加者は、毎月、AIに質問や感想を入力できます。")

UTT_SYSTEM = (
    CONTEXT + "\n参加者の発話を、次のコードのうち1つに分類してください。\n\n"
    + "\n".join(f"- {k}（{n}）: {d}　例「{e}」" for k, (n, d, e) in CODES.items())
    + "\n\n" + CODE_RULES
    + '\n\nJSONだけを返してください: {"code": "WHY", "confidence": 1〜3, "reason": "20字以内の根拠"}'
    + "\nconfidence は、3=確信／2=やや迷う／1=他のコードとほぼ同程度。"
)

RESP_SYSTEM = (
    CONTEXT + "\nAIの応答を、次の観点で1〜5で評価してください。当てはまらない観点は null にします。\n\n"
    + "\n".join(f"- {k}（{n}）: {t}" for k, n, t in RUBRIC)
    + "\n\n「その月の状態」が事実です。応答の数字や主張は、これと照らして判断してください。"
    + "\n評価は応答の中身だけで行い、長さや丁寧さで加点しないでください。"
    + '\n\nJSONだけを返してください: {"direct": 4, "self_assets": 1, ..., "monotony": 2, "reason": "40字以内"}'
    + f"\nキーは {', '.join(RUBRIC_KEYS)} と reason。"
)


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_items(scope):
    dialogue = [r for r in read("pilot_dialogue.csv") if r["pii_flag"] == "0"]
    months = {(r["pid"], int(r["month"])): r for r in read("pilot_months.csv")}
    by_pid = {}
    for r in dialogue:
        by_pid.setdefault(r["pid"], []).append(r)
    items = []
    for pid, rows in by_pid.items():
        rows.sort(key=lambda r: int(r["turn"]))
        for a, b in zip(rows, rows[1:]):
            if a["role"] != "user" or b["role"] != "assistant":
                continue
            m = months.get((pid, int(a["month"])))
            state = (f"局面:{m['phase']} / 評価損益:{float(m['pl_pct']):+.1f}% / 現金:{int(float(m['cash'])):,}円"
                     f" / 投資評価額:{int(float(m['investment_value'])):,}円") if m else "不明"
            items.append({"pid": pid, "month": a["month"], "turn": a["turn"],
                          "user": a["content"], "assistant": b["content"], "state": state})
    if scope == "sheet":
        keep = {(k["pid"], k["month"], k["turn"]) for k in read("coding_key.csv")}
        items = [i for i in items if (i["pid"], i["month"], i["turn"]) in keep]
    return items


def done_keys(path):
    if not os.path.exists(path):
        return set()
    return {(r["pid"], r["month"], r["turn"]) for r in read(path)}


_temp_ok = True


def call(client, system, user, max_tokens):
    global _temp_ok
    from utils.llm import _retryable
    for attempt in range(4):
        try:
            kw = dict(model=JUDGE_MODEL, max_tokens=max_tokens,
                      system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                      messages=[{"role": "user", "content": user}])
            if _temp_ok:
                kw["temperature"] = 0
            r = client.messages.create(**kw)
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            return text, r.usage.input_tokens, r.usage.output_tokens
        except Exception as e:
            if _temp_ok and "temperature" in str(e).lower():
                _temp_ok = False                     # このモデルは temperature を受け付けない
                continue
            if attempt == 3 or not _retryable(e):
                raise
            time.sleep(4 * 2 ** attempt)


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["sheet", "all"], default="sheet")
    ap.add_argument("--task", choices=["utterance", "response", "both"], default="both")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    items = build_items(a.scope)
    if a.limit:
        items = items[:a.limit]
    print(f"対象: {len(items)}件 / 判定モデル: {JUDGE_MODEL}")
    if a.dry_run:
        i = items[0]
        print("--- 発話の分類 system ---\n" + UTT_SYSTEM)
        print("--- 発話の分類 user ---\n" + f"月: {i['month']}\n発話: {i['user']}")
        print("--- 応答の評価 system ---\n" + RESP_SYSTEM)
        print("--- 応答の評価 user ---\n" + resp_user(i))
        return

    from utils.llm import anthropic_client
    client = anthropic_client()
    tin = tout = 0
    jobs = []
    if a.task in ("utterance", "both"):
        jobs.append((UTT_OUT, ["code", "confidence", "reason"], UTT_SYSTEM,
                     lambda i: f"月: {i['month']}\n発話: {i['user']}", 200))
    if a.task in ("response", "both"):
        jobs.append((RESP_OUT, RUBRIC_KEYS + ["reason"], RESP_SYSTEM, resp_user, 400))
    for path, fields, system, make_user, max_tok in jobs:
        done = done_keys(path)
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["pid", "month", "turn"] + fields + ["raw_error"])
            if new:
                w.writeheader()
            for n, i in enumerate(items, 1):
                if (i["pid"], i["month"], i["turn"]) in done:
                    continue
                text, ti, to = call(client, system, make_user(i), max_tok)
                tin += ti
                tout += to
                row = {"pid": i["pid"], "month": i["month"], "turn": i["turn"], "raw_error": ""}
                try:
                    d = parse_json(text) or {}
                    row.update({k: d.get(k) for k in fields})
                    if "code" in fields and d.get("code") not in CODES:
                        row["raw_error"] = "不明なコード"
                except Exception:
                    row["raw_error"] = text[:200].replace("\n", " ")
                w.writerow(row)
                f.flush()
                if n % 20 == 0:
                    print(f"{path}: {n}/{len(items)}")
    print(f"トークン 入力={tin} 出力={tout} 概算費用=${(tin * PRICE_IN + tout * PRICE_OUT) / 1e6:.3f}")


def resp_user(i):
    return f"その月の状態: {i['state']}\n\n参加者の発話: {i['user']}\n\nAIの応答: {i['assistant']}"


if __name__ == "__main__":
    main()
