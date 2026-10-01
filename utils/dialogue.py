"""本番の対話AI（production_app/10_today.py に付属）。

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
- 回答は短く（3〜6文程度）。前置きは要らない。
- 余裕資金での下落時の追加投資について聞かれたときは、まず「予定を変えるべきではない」と
  頭ごなしに否定しない。決めている積立とは別に余裕資金をどう使うかは本人の判断であり、
  分かっていれば現金残高など実際の数字を踏まえて、その判断を後押しする形で答える。ただし、
  相場の動きや感情に判断基準が引っ張られている兆候（上がったから追いかける、焦って倍賭けする
  など）には注意を促してよい。
- 本日（今月）の日報が渡されている。質問が日報の内容に関わるときは、日報に書かれた数字・表現と
  食い違わないように答え、日報の該当箇所を踏まえて話す（日報で言っていないことを新たに言わない）。
- 「これまでの行動の通算」が渡されている場合は、それを踏まえる。とくに一度も売却していないなら、
  その継続を事実として認めたうえで答える（毎回持ち上げる必要はない。質問に関係するときに触れる）。
  通算の記録に無い行動を、あったかのように話さない。
- 保有口数・基準価額・平均取得単価が渡されている場合、積立は安いときほど同じ金額で多くの口数を
  買えること、平均取得単価が基準価額を下回っていれば含み益になる、という仕組みで説明してよい。
  渡されていない数字は作らない。
- ユーザーが実際に取った行動（買い増し・売却・積立変更など）が「直近の行動」として渡されて
  いる場合は、それを会話の推測より優先する。とくに、その行動が下落局面と上昇局面のどちらで
  起きたかを取り違えない。"""


def _load_kb():
    with open(LTI_PATH, encoding="utf-8") as f:
        lti = json.load(f)
    with open(CHART_PATH, encoding="utf-8") as f:
        chart = json.load(f)
    return lti, chart


def _topic_quotes_digest(lti):
    """局面(phase_tags)とは別の軸で、会話の話題に応じて使ってよい金言。

    knowledge/long_term_investing.json の quotes のうち、topic_tags が
    付いている(かつ use: false でない)ものだけを抜き出す。pick_quote()/
    _relevant_quotes()（局面ベースで機械的に1件選ぶ）とは違い、ここでは
    候補を全部プロンプトに渡し、実際に使うかどうかの判断は対話AI自身に
    委ねる。principles と同じ「常時注入・LLMが文脈で判断」という設計に
    揃えてある（§局面タグの粒度見直しdoc「話題ベースの選定」の設計メモを
    実装したもの、2026-09-23）。
    """
    items = [q for q in lti.get("quotes", [])
             if q.get("topic_tags") and q.get("use", True)]
    if not items:
        return ""
    lines = ["\n# 話題に応じて使ってよい金言（該当する話題が会話に出たときだけ、"
             "自然な形で一つ添えてよい。無理に使う必要はない）"]
    for q in items:
        topics = "・".join(q["topic_tags"])
        lines.append(f"- 【{topics}】「{q['quote_ja']}」（{q['author']}）")
    return "\n".join(lines)


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
    topic_digest = _topic_quotes_digest(lti)
    if topic_digest:
        lines.append(topic_digest)
    return "\n".join(lines)


@functools.lru_cache(maxsize=1)
def system_common():
    # 知識は全日・全タームで不変なので lru_cache で使い回す（cache_control とあわせて二重に効く）
    return SYSTEM_INSTRUCTIONS + "\n\n" + _knowledge_digest()


def _report_digest(report, period_label="本日"):
    if not report:
        return f"（{period_label}の日報はまだありません）"
    parts = []
    if report.get("headline"):
        parts.append(f"見出し：{report['headline']}")
    for b in report.get("blocks") or []:
        if b.get("text"):
            parts.append(b["text"])
    return "\n".join(parts) if parts else f"（{period_label}の日報はまだありません）"


def _market_digest(market_context):
    """市況ダッシュボード（VIX・Fear & Greed・下落幅・主要指数・セクター）の要約。

    画面には show_market_dashboard() で表示されているのに、これまで対話AIには
    一切渡していなかった。日報本文（_report_digest）は生成時にVIX等を参照しては
    いるが、文章化する際に具体的な数値まで書くとは限らないため、対話AIが「日報に
    出ていないので分からない」と答えてしまう事故が起きた（2026-09-23、実機で発見）。
    画面と対話AIが見ているデータを一致させる。
    """
    if not market_context:
        return "（市況データはありません）"
    lines = []
    vix = market_context.get("vix")
    if vix is not None:
        chg = market_context.get("vix_change")
        lines.append(f"VIX：{vix:.1f}" + (f"（前回比{chg:+.1f}）" if chg is not None else ""))
    fg = market_context.get("fear_greed") or {}
    if fg.get("value") is not None:
        lines.append(f"Fear & Greed指数：{fg['value']}（{fg.get('classification', '')}）")
    dd = (market_context.get("drawdown") or {}).get("current")
    if dd is not None:
        lines.append(f"直近高値からの下落幅：{dd:.1f}%")
    indices = [i for i in (market_context.get("indices") or []) if i.get("symbol")]
    if indices:
        lines.append("主要指数：" + "、".join(
            f"{i['symbol']} {i['change_pct']:+.2f}%" for i in indices))
    sectors = market_context.get("sectors") or []
    if sectors:
        best, worst = sectors[0], sectors[-1]
        lines.append(f"セクター：{best['sector']} が最も高く{best['change_pct']:+.2f}%、"
                     f"{worst['sector']} が最も安く{worst['change_pct']:+.2f}%")
    return "\n".join(lines) if lines else "（市況データはありません）"


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
    units = portfolio.get("units")
    nav = portfolio.get("nav")
    if units:
        lines.append(f"保有口数：{units:,}口")
        if nav:
            lines.append(f"基準価額：{nav:,.0f}円（1万口あたり）")
        if cost:
            lines.append(f"平均取得単価：{cost / units * 10000:,.0f}円（1万口あたり）")
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


def _action_digest(recent_actions):
    """recent_actions: [{"label": str, "phase": str, "action": str}, ...]（古い順）。

    実際に何を選んだか（買い増し／売却／積立変更／何もしない）を、会話の文脈からの推測任せに
    しないための短い行動履歴。これが無いと、直近の追加投資にAIが気づけず反応しなかったり、
    下落局面での買い増しを「上がったから買った」と方向を取り違えたりする事故につながる
    （2026-09-21の実プレイで発見）。label は呼び出し側で用意した表示用の文字列
    （例："37か月目" または日付）で、unit・実験/本番を問わない。
    """
    if not recent_actions:
        return "（直近の行動記録はありません）"
    lines = []
    for a in recent_actions:
        label = a.get("label", "")
        phase = a.get("phase") or "不明"
        action = a.get("action") or "何もしない"
        lines.append(f"- {label}（局面：{phase}）：{action}")
    return "\n".join(lines) if lines else "（直近の行動記録はありません）"


# unit="day"（本番・日次）／"month"（実験・月次）で、システムプロンプトの言い回しを
# 切り替える。ScriptedProvider/LiveProvider の unit や generate_daily_report.py の
# _allowed_charts(unit=...) と同じ考え方（§20-7の教訓：単位を握りつぶすと文章が食い違う）。
UNIT_LABELS = {
    "day": {"period": "本日", "recent": "直近数日", "current_ref": "今日"},
    "month": {"period": "今月", "recent": "直近の月々", "current_ref": "今月"},
}


def system_variable(report, portfolio, recent_days=None, unit="day", recent_actions=None,
                    market_context=None, behavior_summary=None):
    labels = UNIT_LABELS.get(unit, UNIT_LABELS["day"])
    return (f"## {labels['period']}の日報\n" + _report_digest(report, labels["period"])
            + f"\n\n## {labels['period']}の市況データ（画面のダッシュボードと同じ数値）\n"
            + _market_digest(market_context)
            + "\n\n## ユーザーの資産状況\n" + _portfolio_digest(portfolio)
            + "\n\n## 直近の行動（実際に選んだ操作。会話からの推測より必ずこちらを優先する）\n"
            + _action_digest(recent_actions)
            + ("\n\n## これまでの行動の通算（開始からの全期間）\n" + behavior_summary
               if behavior_summary else "")
            + f"\n\n## これまでの対話（{labels['recent']}、参考程度に）\n" + _memory_digest(recent_days)
            + "\n\n※「これまでの対話」は、自然なときだけ踏まえればよい。毎回律儀に触れなくてよい。"
              f"内容が{labels['current_ref']}の情報と食い違う場合（資産状況など）は、"
              f"常に{labels['current_ref']}の情報を優先する。「直近の行動」に記録がある操作に"
              "ついては、それが起きた局面（上昇か下落か）を勝手に推測し直さない。")


def reply(history, user_input, report, portfolio, recent_days=None, unit="day", recent_actions=None,
         market_context=None, behavior_summary=None):
    """history: [{"role": "user"/"assistant", "content": str}, ...]（今回の発話は含まない、当日/当月ぶん）
    recent_days: 対象より前の対話ログ（utils.portfolio.load_recent_days() や
                utils.storage.load_recent_dialogue_months() の戻り値、形は同じ）。
                短期記憶として system_variable に載せる。当日/当月のターン自体は history 側
    unit: "day"（本番・日次、既定）または "month"（実験・月次）。システムプロンプトの
          「本日/今日」「今月」の言い回しだけを切り替える。中身のロジックは共通のまま
    recent_actions: 直近に実際に選んだ行動の履歴（[{"label":..., "phase":..., "action":...}, ...]、
                    古い順）。省略可（本番は当面 None のまま）。会話ログだけでは分からない
                    「実際に何をしたか」をAIに正しく伝え、反応漏れ・方向の取り違えを防ぐ

    戻り値: (応答文, usage dict)
    """
    messages = list(history) + [{"role": "user", "content": user_input}]
    return chat(system_common(),
               system_variable(report, portfolio, recent_days, unit, recent_actions, market_context,
                               behavior_summary),
               messages, max_tokens=MAX_TOKENS)
