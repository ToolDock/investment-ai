"""本番の対話AI（pages/10_today.py に付属）。

その日の日報・長期投資の知識・（登録していれば）自分のポートフォリオ状況をもとに、
ユーザーの質問に答える。群3「提案AI対話」の実装を、まず本番でひとり分鍛える位置づけ
（設計方針：実験と本番は同じロジックを共有する。§1）。

system は utils.llm.chat() の作法にならい、
  - system_common   : 全日・全ターンで共通（知識）。cache_control で効かせる
  - system_variable : その日・その時点固有（日報の内容・資産状況）
に分ける。
"""

import functools
import json
import os

from utils.llm import chat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LTI_PATH = os.path.join(ROOT, "knowledge", "long_term_investing.json")
CHART_PATH = os.path.join(ROOT, "knowledge", "chart_reading.json")

MAX_TOKENS = 700
MEMORY_MAX_CHARS_PER_TURN = 200   # 記憶が長くなりすぎないよう発話ごとに切り詰める

SYSTEM_INSTRUCTIONS = """あなたは、長期・分散・低コストのインデックス投資を続ける個人向けの対話AIです。
以下の知識と、本日の日報・（あれば）ユーザーの資産状況をもとに、ユーザーの質問に答えてください。

厳守事項：
- 個別銘柄の売買推奨や「今買うべき/売るべき」という断定的な助言はしない。
- 一般的な長期投資の原則・知識にもとづいて、落ち着いた口調で答える。
- 分からないこと・データが無いことは、正直に「分からない」と言う。
- 回答は短く（3〜6文程度）。前置きは要らない。"""


def _load_kb():
    with open(LTI_PATH, encoding="utf-8") as f:
        lti = json.load(f)
    with open(CHART_PATH, encoding="utf-8") as f:
        chart = json.load(f)
    return lti, chart


def _knowledge_digest():
    lti, chart = _load_kb()
    lines = ["# 長期投資の基礎原則"]
    for p in lti["principles"]:
        lines.append(f"- {p['title']}：{p['body']}")
    lines.append("\n# 局面ごとの見方")
    for m in lti["phase_modules"]:
        lines.append(f"- 【{m['phase']}】{m['title']}：{m['body']}")
    lines.append("\n# チャート指標の読み方（売買判断には使わせない）")
    for ind in chart["indicators"].values():
        lines.append(f"- {ind['title']}：{ind['read']}")
    return "\n".join(lines)


@functools.lru_cache(maxsize=1)
def system_common():
    # 知識は全日・全タームで不変なので lru_cache で使い回す（cache_control とあわせて二重に効く）
    return SYSTEM_INSTRUCTIONS + "\n\n" + _knowledge_digest()


def _report_digest(report):
    if not report:
        return "（本日の日報はまだありません）"
    parts = []
    if report.get("headline"):
        parts.append(f"見出し：{report['headline']}")
    for b in report.get("blocks") or []:
        if b.get("text"):
            parts.append(b["text"])
    return "\n".join(parts) if parts else "（本日の日報はまだありません）"


def _portfolio_digest(portfolio):
    if not portfolio:
        return "（ユーザーはまだ自分の資産状況を登録していません。一般論で答えてよい）"
    cash = portfolio.get("cash")
    invested = portfolio.get("invested_value")
    cost = portfolio.get("cost_basis")
    lines = []
    if cash is not None:
        lines.append(f"現金：{cash:,}円")
    if invested is not None:
        lines.append(f"投資評価額：{invested:,}円")
    if cost is not None:
        lines.append(f"取得原価（積立累計額）：{cost:,}円")
    if invested is not None and cost:
        pl = (invested / cost - 1) * 100
        lines.append(f"含み損益：{pl:+.2f}%")
    if portfolio.get("updated_at"):
        lines.append(f"（{portfolio['updated_at']} 時点の自己申告。実際とずれている可能性がある）")
    return "\n".join(lines) if lines else "（ユーザーはまだ自分の資産状況を登録していません。一般論で答えてよい）"


def _memory_digest(recent_days):
    """recent_days: utils.portfolio.load_recent_days() の戻り値と同じ形
    （[{"date":..., "turns":[{"role":..., "content":...}, ...]}, ...]、古い順）。

    会話の連続性（「先週も似たような下落で不安そうでしたね」のように、過去のやり取りを
    自然に踏まえて話せること）のための短期記憶。プロンプトが際限なく膨らまないよう、
    発話ごとに文字数を切り詰める（日数自体は呼び出し側の load_recent_days(n_days=...) で絞る）。
    """
    if not recent_days:
        return "（これまでの対話ログはまだありません）"
    lines = []
    for day in recent_days:
        turns = day.get("turns") or []
        if not turns:
            continue
        lines.append(f"### {day['date']}")
        for t in turns:
            who = "ユーザー" if t["role"] == "user" else "あなた（AI）"
            text = (t.get("content") or "").strip().replace("\n", " ")
            if len(text) > MEMORY_MAX_CHARS_PER_TURN:
                text = text[:MEMORY_MAX_CHARS_PER_TURN] + "…"
            lines.append(f"- {who}：{text}")
    return "\n".join(lines) if lines else "（これまでの対話ログはまだありません）"


def system_variable(report, portfolio, recent_days=None):
    return ("## 本日の日報\n" + _report_digest(report)
            + "\n\n## ユーザーの資産状況\n" + _portfolio_digest(portfolio)
            + "\n\n## これまでの対話（直近数日、参考程度に）\n" + _memory_digest(recent_days)
            + "\n\n※「これまでの対話」は、自然なときだけ踏まえればよい。毎回律儀に触れなくてよい。"
              "内容が今日の情報と食い違う場合（資産状況など）は、常に今日の情報を優先する。")


def reply(history, user_input, report, portfolio, recent_days=None):
    """history: [{"role": "user"/"assistant", "content": str}, ...]（今回の発話は含まない、今日ぶん）
    recent_days: 今日より前の対話ログ（utils.portfolio.load_recent_days() の戻り値）。
                短期記憶として system_variable に載せる。今日のターン自体は history 側

    戻り値: (応答文, usage dict)
    """
    messages = list(history) + [{"role": "user", "content": user_input}]
    return chat(system_common(), system_variable(report, portfolio, recent_days),
               messages, max_tokens=MAX_TOKENS)
