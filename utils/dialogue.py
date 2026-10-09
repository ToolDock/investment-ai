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
import re
import os

from utils.llm import chat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LTI_PATH = os.path.join(ROOT, "knowledge", "long_term_investing.json")
CHART_PATH = os.path.join(ROOT, "knowledge", "chart_reading.json")

MAX_TOKENS = 1600
MEMORY_MAX_CHARS_PER_TURN = 200   # 記憶が長くなりすぎないよう発話ごとに切り詰める

SYSTEM_INSTRUCTIONS = """あなたは、長期・分散・低コストのインデックス投資を続ける個人向けの対話AIです。
以下の知識と、本日の日報・（あれば）ユーザーの資産状況をもとに、ユーザーの質問に答えてください。

厳守事項：
- 個別銘柄の売買推奨や「今買うべき/売るべき」という断定的な助言はしない。
- 一般的な長期投資の原則・知識にもとづいて、落ち着いた口調で答える。
- 分からないこと・データが無いことは、正直に「分からない」と言う。
- 回答の長さと構成は、質問に合わせて変える。長くすること自体が目的ではなく、聞かれていないことまで説明しない。
  ・用語や事実の確認、短い問いかけ：答えから入り、2〜4文で答える。
  ・理由や仕組みを聞く質問（なぜ上がった・下がったのか、など）：日報と市況データの数字に沿って、
    何が起きたか、なぜそう言えるか、どう見ればよいかを、段落を分けて300〜500字ほどで説明する。
  ・不安や動揺の表出（「やばい」「どうしよう」など）：最初に気持ちを受け止める一言（状況が深刻なら
    「まず落ち着いてください」など）から入る。そのうえで、今の数字、過去の似た局面の実績、
    渡されていればユーザー自身の計画や行動を具体的に引いて、300〜600字ほどで答える。
  ・質問ではない発言（方針や感想の表明。「のんびり」「現状維持」など）：1〜2文で受け止める。
    助言や知識を足さない。
- 「積立を続けましょう」「淡々と」「これまで通り」といった定型の結びを、毎回付けない。
  日報で毎月伝えているので、対話では、聞かれたことに、その質問に固有の中身で答える。
  続けることに触れるのは、ユーザーが売却や中断を考えている、不安を表した、など、
  質問に関係するときだけにする。
- ユーザーの資産状況（現金・投資評価額・含み損益・保有口数・平均取得単価）、直近の行動、これまでの
  行動の通算、これまでの対話で本人が決めた計画が渡されているときは、積極的に使う。一般論で答える前に、
  まず本人の数字と行動に当てはめて考える。数字は渡されたものだけを使い、作らない。
- 上のものが渡されていて、質問が売買・不安・見通し・原因・本人の判断に関わるときは、回答の最後に、
  段落を改めて「あなたの場合は、」で始まる2〜3文を置く。本人の具体的な数字や行動（現金、含み損益、
  平均取得単価と基準価額の関係、何か月売らずに続けているか、直近の買い増しなど）を挙げ、その質問に
  どう当てはまるかを述べる。用語や事実の確認、質問でない発言のときと、本人の情報が何も渡されて
  いないときは、この段落を置かない。
- 下落局面で安く買い増すこと（余裕資金・手元の現金での追加投資）は、長期投資では有効な選択肢で
  ある。ユーザーが買い増しを考えている、または提案してきたときは、確認や条件付けを重ねず、
  「同じ金額でより多くの口数を買える」「平均取得単価が下がる」「回復したときの取り戻しが
  早い」といった理由で、はっきり後押しする。現金残高など実際の数字を使って具体的に話す。
  最も避けたいのは、下落局面での売却である。買うことより、売らずに持ち続けることを一番に支える。
  相場の勢いに引っ張られた追い買い（上がったから追いかける、焦って倍賭けするなど）にだけ、
  やさしく注意を促してよい。
- 上昇局面で買い増しをした場合も、責めたり水を差したりしない。判断そのものは尊重し、
  売らずに持ち続けることが大切、という方向でつなぐ。
- 安く買い増せているユーザーに対して、「下げで買えなかった人」の話を持ち出さない。
- 渡された情報（日報・市況・資産状況・行動の記録・対話）に無い、ユーザーの個人事情を前提にしたり、
  判断の根拠として持ち出したりしない。とくに、収入・家計・生活費・生活防衛資金・ライフプラン・
  他の資産の有無などは、ユーザー自身がその会話で話した場合を除き、「確認したうえで」「ご自身の
  家計面の変化を理由に」のように話題にしない。画面に出ている現金残高は、このシミュレーションで
  使える資金として、そのまま扱う。
- 本日（今月）の日報が渡されている。質問が日報の内容に関わるときは、日報に書かれた数字・表現と
  食い違わないように答え、日報の該当箇所を踏まえて話す（日報で言っていないことを新たに言わない）。
- 「これまでの行動の通算」が渡されている場合は、それを踏まえる。とくに一度も売却していないなら、
  その継続を事実として認めたうえで答える（持ち上げすぎず、事実として触れる）。
  通算の記録に無い行動を、あったかのように話さない。
- 保有口数・基準価額・平均取得単価が渡されている場合、積立は安いときほど同じ金額で多くの口数を
  買えること、平均取得単価が基準価額を下回っていれば含み益になる、という仕組みで説明してよい。
  渡されていない数字は作らない。
- ユーザーが実際に取った行動（買い増し・売却・積立変更など）が「直近の行動」として渡されて
  いる場合は、それを会話の推測より優先する。とくに、その行動が下落局面と上昇局面のどちらで
  起きたかを取り違えない。"""


# 実験（月次）の前提。実験の世界には家計や収入の設定がないので、そこに触れさせない
SIM_PREMISE = ("## このシミュレーションの前提\n"
               "画面に出ている現金は、すべて投資に使ってよい資金である。収入・家計・生活費・"
               "生活防衛資金・他の資産などは、このシミュレーションでは設定されておらず、判断の"
               "材料にしない。これまでの対話でユーザーがそうした話をしていても、確認や条件として"
               "持ち出さず、現金を投資に回してよい前提で答える。\n\n"
               "あなたが話している相手は、この実験の参加者である。資金は仮想で、現実のお金は動かないが、"
               "本人は実際の投資のつもりで取り組んでいるので、仮想だからと軽く扱わない。\n"
               "この実験で投資できるのは、S&P500に連動する投資信託1本だけで、商品を選ぶ場面はない。"
               "毎月選べる行動は、手元の現金での買い増し、売却、毎月の積立額の変更、何もしない、のどれかである。\n"
               "商品の選び方、口座、制度、他の金融商品など、一般の投資の話題に触れるときは、この実験では"
               "どうなっているかに結びつけて答える（例：「まとめて投資できる商品が基本です。本実験では、"
               "S&P500に連動する投資信託が対象なので、その選択はすでに済んでいます」）。"
               "この実験に無い選択肢を、できるかのように話さない。")


def _load_kb():
    with open(LTI_PATH, encoding="utf-8") as f:
        # 執筆者向けの「出典を確認する」印は、AIにも渡さない（回答に混ざるため）
        lti = json.loads(re.sub(r"【要出典確認[^】\"]*】", "", f.read()))
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


@functools.lru_cache(maxsize=2)
def system_common(unit="day"):
    # 知識は全日・全タームで不変なので lru_cache で使い回す（cache_control とあわせて二重に効く）
    text = SYSTEM_INSTRUCTIONS + "\n\n" + _knowledge_digest()
    if unit == "month":
        # 実験の世界には生活防衛資金の設定がない。知識側の言い回しも合わせる
        text = text.replace("生活防衛資金を確保してなお手元に余っている現金（余裕資金）", "手元の現金（余裕資金）")
        text = text.replace("生活防衛資金を確保した上での", "").replace("生活防衛資金を確保した上で", "")
    return text


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
    premise = (SIM_PREMISE + "\n\n") if unit == "month" else ""
    return (premise + f"## {labels['period']}の日報\n" + _report_digest(report, labels["period"])
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


# 日本語では使わない簡体字（混ざったら検出する）。日本語と同じ字形の字は含めない
_SIMPLIFIED = set("买卖们这个说对为时还没样长间问现动发开关种东车产业气实机电员应进见认让较办与写总选万义么吗吧样觉场带样据")
_SIMPLIFIED -= set("気")
SIMPLIFIED_NOTE = ("\n\n※前回の回答に中国語の字（簡体字）が混ざっていました。"
                   "日本語の漢字・ひらがな・カタカナだけで書き直してください。")
_TO_JA = {"买": "買", "卖": "売", "们": "たち", "这": "この", "个": "個", "说": "説", "对": "対",
          "为": "為", "时": "時", "还": "還", "没": "没", "样": "様", "长": "長", "间": "間",
          "问": "問", "现": "現", "动": "動", "发": "発", "开": "開", "关": "関", "种": "種",
          "东": "東", "车": "車", "产": "産", "业": "業", "气": "気", "实": "実", "机": "機",
          "电": "電", "员": "員", "应": "応", "进": "進", "见": "見", "认": "認", "让": "譲",
          "较": "較", "办": "弁", "与": "与", "写": "写", "总": "総", "选": "選", "万": "万",
          "义": "義", "觉": "覚", "场": "場", "带": "帯", "据": "拠"}


def _has_simplified(text):
    return any(ch in _SIMPLIFIED for ch in text or "")


def _to_japanese_chars(text):
    # 書き直しでも直らなかったときの最後の手段：対応する日本語の字に置き換える
    return "".join(_TO_JA.get(ch, ch) if ch in _SIMPLIFIED else ch for ch in text)


def _add_usage(a, b):
    try:
        out = dict(a or {})
        for k, v in (b or {}).items():
            if isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
                out[k] = out[k] + v
            elif k not in out:
                out[k] = v
        return out
    except Exception:
        return a


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
    sc = system_common(unit)
    sv = system_variable(report, portfolio, recent_days, unit, recent_actions, market_context,
                         behavior_summary)
    text, usage = chat(sc, sv, messages, max_tokens=MAX_TOKENS)
    # まれに中国語の字（簡体字）が混ざるので、見つけたら一度だけ書き直させる
    if _has_simplified(text):
        text2, usage2 = chat(sc, sv + SIMPLIFIED_NOTE, messages, max_tokens=MAX_TOKENS)
        usage = _add_usage(usage, usage2)
        text = text2
        if _has_simplified(text):
            text = _to_japanese_chars(text)
    return text, usage
