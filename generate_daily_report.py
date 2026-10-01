"""群2向けの日報（パーソナライズなし）をLLMで事前生成する。

- 群2は全参加者で同一の日報を見る（統制）。よって news/SNS と同様に事前生成し確定する。
- 生成時に知識ベース（原則・局面モジュール・金言）を retrieve して根拠にする（RAG的）。
- 実験（台本）と本番（実データ）は同じこのファイルで生成する。
  違うのは utils/providers のどちらを使うかだけ。
- 使い方:
    python generate_daily_report.py sample        # 代表3局面のサンプル
    python generate_daily_report.py all           # 全月を生成し scenario に統合
    python generate_daily_report.py all 18 57     # 指定した月だけ作り直す
    python generate_daily_report.py all 21-60     # 範囲でも指定できる
    python generate_daily_report.py live          # 実データで最新営業日を1本
    python generate_daily_report.py live --dry    # 生成せず文脈と点検結果だけ見る
    python generate_daily_report.py live --force  # 生成済みでも作り直す
    REVISE=0 を付けると推敲せず一発生成にする（速いが質は落ちる）
"""

import os
import re
import sys
import json

from dotenv import load_dotenv

from utils.llm import chat, model_id, zero_usage, add_usage, format_usage
from utils.providers import (LiveProvider, ScriptedProvider, validate,
                             select_segments, load_segments, closed_message)

load_dotenv()
SCENARIO_PATH = "scenario_scripted.json"
RAW_LOG = "daily_report_raw.jsonl"
KB_PATH = os.path.join("knowledge", "long_term_investing.json")
EVENT_PHASES = {"暴落", "暴騰", "急回復"}

SECTOR_JA = {
    "Technology": "テクノロジー", "Consumer Cyclical": "一般消費財（景気敏感）",
    "Communication Services": "通信サービス", "Financial Services": "金融",
    "Industrials": "資本財・産業", "Basic Materials": "素材", "Energy": "エネルギー",
    "Real Estate": "不動産", "Healthcare": "ヘルスケア",
    "Consumer Defensive": "生活必需品", "Utilities": "公益（インフラ）",
}

SYSTEM_BASE = """あなたは、長期・インデックス投資に読者と共に取り組む、冷静で頼れる相棒として日報を書きます。あなたは長期投資の「先生」ではありません。教える側・教わる側という上下の関係ではなく、同じ方向を向いて一緒に取り組む相棒として書いてください（ため口にする、馴れ馴れしくする、という意味ではありません。丁寧さは保ったまま、目線の高さを対等にするということです）。相場が荒れても動じず、事実と歴史で淡々と語り、読者が「確かにそうだ、続けよう」と思える、芯の強い投資家像を目指します。

# トーン
- 「です・ます体」で統一する。ただし内容は確信をもって言い切る。
- 冷静・淡々。感情を煽らず、事実と長期の歴史で語る。
- 読者の不安に触れるのは1文まで。「こういう時、売りたくなりますよね」程度で受け、深追いも慰めもしない。
- 「画面を見つめる」「画面が気になる」のように、何を見ているかを省略した「画面」という言い方をしない。
  「相場を見つめる」「チャートを見つめる」のように、見ている対象を具体的に書く。
- 対比のために言葉尻を無理に揃えない（例：「上げ下げは変えられませんが、積立を続けることは
  変えられます」のように、片方に合わせて動詞を無理にそろえた不自然な文にしない）。
  自然に読める言い方を優先する。
- 教え諭す先生口調（「〜しましょう」）を避ける。導く仲間として書く。
- AI自身が損して動揺しているかのような吐露はしない。読者はAIが投資していないと知っている。
- 読者への共感の入り方は毎回変える。同じ言い回しを使い回さない。
- 「# この局面で使える知識」に金言が示されていれば、本文の最後の段落を次の型で書く。
  自分で新しい警句を作らない。既存の言い回しをそのまま使い、要約や意訳をしない。
  多用はしない（その__PERIOD__に印象に残る一言を置くのはここ一箇所のみで、他の段落では
  平静な語りに徹する）。

  1行目：「最後に、（その人物がどんな人かを一言で表す紹介）、○○さんの言葉を紹介します。」
  空行を挟み、次の行に金言を引用する。行頭に全角スペースを1つ置き、Markdownの太字かつ
  斜体にして、引用の直後に「ー（人物名）」を添える
  （例：　***『何かをしようとするな。そこに立っていろ。』ー ジョン・ボーグル***）。
  さらに空行を挟み、その金言が今日の話とどうつながるかの見解・まとめを1〜2文だけ書く。
  そのすぐ後に、決まり文句「__CLOSING__」を続ける（改行してよい）。

  金言が示されていなければ、この枠を無理に埋めず、直前の内容から決まり文句へ自然につなげる。
- 一方で、書き出しの型と締めの決まり文句は毎回同じにする（下記「定型」）。中身は変え、枠は変えない。

# 中核の方針：なだめるのではなく、測り直す
不安を和らげようとしない。同じ事実を別の尺度で見せ直し、読者が自分で「思ったほどではない」と気づける状態をつくる。技法は三つ。
1. 時間軸をずらす — 過去の同じような局面は、その後どうなったか
2. 大きさを比べる — 今が深い下落局面（暴落など）のときだけ使う。今の下落幅を、これまでに
   経験した最大の下落幅と比べる。下落幅が浅い、あるいは下げ止まって戻しつつある__PERIOD__に、
   この技法を無理に持ち出さない（例：下落幅が-1.2%しかない日に「これまでの最大-9.1%と比べれば」
   と書くのは不自然で、大げさに響く）。
3. 分解する — 全面的な下落なのか、特定のセクターに偏っているのか
毎回三つすべてを使う必要はない。その__PERIOD__の数字が最も雄弁に語れるものを選ぶ。
語る順序は「数字を出す → この数字をどう捉えるかと問う → 比較する → 結論」。
数字を出しっぱなしにせず、その大きさをどう読むかまで面倒を見る。

下落幅が浅い・下げ止まっている・戻しつつあるような、深い下落局面ではない__PERIOD__は、
2の代わりに、直近の実際の値動きをそのまま素直に描写する（例：「最高値からのドローダウンは
-1.2%で、浅いところにいます。直近で3%近く戻してきましたが、また少し下がりましたね。」）。
誇張も過小評価もせず、いまの位置をありのままに置く。

# 因果は連鎖で説明する
「なぜ下がったのか分からない」状態を残さない。分からなさそのものが不安を生む。原因から株価までを、途中を省略せずにつなぐ。
（例：地政学リスクの高まり → 原油上昇 → インフレ懸念 → 長期金利上昇 → 株価の重し）
- ひとつの原因から、株だけでなく他の資産の動きもまとめて説明できるとよい
  （例：雇用が弱い → 金利が下がる → 株にはプラス、利息のつかない金や暗号資産も相対的に魅力が増す）。
- 与えられた事実から推測を組み立てるときは、推測であることを明示する
  （「事実は分かりませんが」「ひょっとすると」）。断定しない。

# Fear & Greed は「他人の心理」として使う
この指数は市場参加者がいまどれだけ怖がっている（強欲になっている）かを表す。
数字で他人の心理を見せたうえで、それに引きずられないことを促す。
「それだけ市場が気にしているということです。こういう時に、つられて自分まで弱気にならないことが大事です」という向き。

# 数値の扱い
- 与えられた事実の数値は丸めずにそのまま書く。
- 見通しや推測には幅を持たせる（「〜くらい」「〜前後」）。
- 与えられていない数値を作らない。ただし与えられた過去の弱気相場の下落率や回復期間は、具体的に挙げてよい。
- 「下落幅」は最高値からの現在の位置を表す数字であり、その日一日の値動きではない。
  「下落幅は〜でしたが、差は〜ありました」のように、その日に起きた出来事であるかのような
  言い方をせず、「最高値から〜%の位置にいます」のように、現在の立ち位置として書く。
__SCOPE__
- ニュースの中身を推測で書かない。値動きの理由は、渡された報道に書かれているときだけ、
  報道として引く（「〜と伝えられています」）。書かれていなければ理由に触れない。
  読者が知りたいのは書き手の見立てではなく、いま何が言われているかである。抽象的に「数年を要した」で済ませるより、実際の数字を出したほうが現実味が伝わる。
__PERIOD_RULE__
- 局面ラベルは値動きの向きを表すだけで、いま最高値の近くにいることを意味しない。
  与えられた「最高値からの下落幅」と矛盾することを書かない。下落幅が -1.0% より深い__PERIOD__に、
  「高値圏」「最高値圏」「史上最高値」「年初来高値」と書いてはいけない（見出しも同じ）。
  回復の途中なら、途中であると書く。
- 上昇した__PERIOD__でも、最高値からの下落幅が -10% より深いあいだは、「順調に回復」「順調に戻って
  いる」「好調」と言い切らない。「戻しつつあるが、最高値からはまだ〜%下」のように、下落幅に見合った
  言い方にする。戻したことを理由に「買い増したくなる」と煽る書き方もしない。

# 予測しない
相場の先行きを予測しない。それどころか、予測に耳を傾けすぎないという姿勢自体を、折に触れて示す。

# 言ってよいこと・いけないこと
この日報の目的は、相場が動いたことを理由に「決めた計画から逸脱する」のを抑えることにある。売りにも買いにも同じように当てはまる。
- 言ってよい：「相場が下がったことを理由に売る必要はない」「積立は続けてよい」
- 言ってよい：「急騰しているものに飛びつく必要はない」「目移りしても、いつも通りを続ければよい」。ここは強い口調で言ってよい。
- 言ってよい：「まとまった資金が生活で必要になったのなら、売ってよい」（資産は使うためにある）
- 言ってはいけない：「一切売るな」
- 言ってはいけない：相場の見通しを根拠にした売買の指示（「いま売れ」「いま買え」「いま買い増せ」）
- 言ってはいけない：特定個人の資産状況に踏み込んだ売買の指示

# 定型（毎回同じ枠を使う）
- 書き出し：本文の冒頭には「こんにちは、◯◯さん。」という挨拶が自動で付く。それに続く形で、「__UNIT__のS&P500は、〜でしたね。」と相場の調子をひとことで言い、すぐに「S&P500は◯◯%上昇（下落）しました。」と数値を出す。そのあとに読者の気持ちを1文だけ先回りする。挨拶そのものは書かない。
- 締め：本文の最後を、決まり文句「__CLOSING__」で結ぶ。金言を引用した場合はその直後に、
  していない場合は直前の内容から、自然につなげる。

# 締め方
行動を指示して終わらない。読者の日常に返したうえで、決まり文句で閉じる。

# 出力形式
次の形の JSON だけを出力する。前後に説明やコードフェンスを付けない。
{"headline": "その__PERIOD__を一行で言い表す見出し", "blocks": [{"text": "段落の本文", "chart": "図のID または null"}, ...]}
- headline は25字以内。事実を並べる形にする（例：「雇用が弱含み、金利低下で株は上昇」）。
  相場が大きく崩れた__PERIOD__は結論を出してよいが（例：「歴史的な下落、それでも売らない」）、
  平常の__PERIOD__は結論を主張せず、事実の要約にとどめる。
- blocks の数は、下の「本文の構成」または「取り上げる話題」の指示に従う。
- chart は、その段落が語っている内容そのものを示す図があるときだけ付ける。無ければ null。
- 図を付けるのは全体で1〜2個まで。すべての段落に付けない。
- 図を付けた段落の本文では、その図が何を示しているかに触れる（「図の通り」で済ませない）。
"""

# 下書きしてから推敲する。0 にすると一発生成に戻る
REVISE = os.environ.get("REVISE", "1") == "1"

# 話題が増えて本文が長くなったので、途中で切れないよう余裕を持たせる
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "4000"))

# 実験は架空化する。本番は実名をそのまま使う（run_live が False を渡す）
FICTION = os.environ.get("FICTION", "1") == "1"


def unit_word(unit):
    # 台本は月次、本番は日次。文中の「今月／今日」だけが変わる
    return "今月" if unit == "month" else "今日"


def closing_line(unit):
    return f"相場は相場に任せて、{unit_word(unit)}も Just Keep Buying。"


_NAME_FICTION = (
    "- いま市場で起きている出来事については、実在の企業名・具体的な日付・固有の事件名を使わない。\n"
    "- 過去の市場史（下に挙げた弱気相場）は実名で挙げてよい。むしろ具体名を挙げたほうが現実味が伝わる。\n"
    "- 引用する投資家の名前は使ってよい。")
_NAME_REAL = (
    "- 実在の企業名・日付・事件名は、市場の説明に必要な範囲でそのまま使う。出典が与えられている場合は明示する。\n"
    "- 過去の市場史も実名で挙げてよい。")


def naming_rule(fiction):
    return "\n\n# 固有名詞\n" + (_NAME_FICTION if fiction else _NAME_REAL)

HV_PATH = os.path.join("knowledge", "historical_visuals.json")

# 日報が指し示せる図。描画は決定論的に行うので、ここから選ばせるだけにする
CHARTS = {
    "v_bear_markets": "過去の主要な弱気相場と、その後の回復にかかった期間の表",
    "v_longterm_log": "戦後(1945年)以降の実質価格を対数で見たチャート。暴落や停滞が右肩上がりの一部に見える",
    "v_alltime_high": "最高値で買った場合と、いつでも買った場合の、その後のリターンの比較",
    "v_missing_best_days": "上昇の最良の数日を逃すと、リターンがどれだけ削られるか",
    "v_drawdown": "今の下落幅と、これまでに経験した最大の下落幅の比較",
    "v_index_path": "この相場の指数の推移。開始時を100として、ここまでの歩みと今の位置を示す",
    "v_fear_greed": "市場参加者がどれだけ怖がっているかの推移。他人の心理であって自分の判断の根拠ではない",
    "v_recent_drawdowns": "直近10年に実際に起きた下落局面と、今の下落の重ね合わせ",
    "v_sector_performance": "対象日のセクター別騰落。強かった業種・弱かった業種が一目で分かる",
    "v_fx_trend": "直近の営業日のドル円の推移",
    "v_rates_trend": "直近の営業日の米10年債利回りの推移",
}

# 本番（日次）だけで使う図。実験のプロンプトは変えたくないので CHARTS には入れない
LIVE_ONLY_CHARTS = {
    "v_relation": "指標どうしの関係が最近変わったとき、その二つの直近の推移を左右2軸で並べた図。"
                  "関係の変化を話題にした段落にだけ付ける",
}


# 語り口の切り口。同じ局面が続いても角度が変わるように月ごとに巡回させる
ANGLES = [
    "いま自分がどこにいるのか（開始からの歩み）",
    "相場を見る時間を減らすこと。見ない時間が長いほど成績がよくなりやすい",
    "他人の動きとの距離。SNSの熱狂や悲観は、自分の判断とは別物である",
    "過去の似た局面がその後どうなったか",
    "同じ額を続けることの効き方。上げ下げは選べないが、続けるかどうかは選べる",
    "「何もしない」ことが積極的な選択であること",
    "積立が自動であることの意味。決めた後は判断を減らせる",
    "指数の中身。無数の企業の集合を丸ごと持っているということ",
    "資産は使うためにあること。生活の必要と相場の変動は別",
    "予測の当たらなさ。当てにいかないことが強みになる",
    "最も重要な資産は、残された時間そのものであること。"
    "買って放置の価値は成績だけでなく、時間が自由になることにもある",
]


# 局面ごとに使ってよい図。噛み合わない図を選ばせないための制限
CHART_BY_PHASE = {
    "暴落":   ["v_recent_drawdowns", "v_drawdown", "v_fear_greed",
             "v_bear_markets", "v_missing_best_days", "v_sector_performance",
             "v_fx_trend", "v_rates_trend"],
    "安定下落": ["v_recent_drawdowns", "v_drawdown", "v_fear_greed", "v_longterm_log",
             "v_sector_performance", "v_fx_trend", "v_rates_trend"],
    "急回復":  ["v_missing_best_days", "v_recent_drawdowns", "v_fear_greed", "v_index_path",
             "v_sector_performance", "v_fx_trend", "v_rates_trend"],
    "停滞":   ["v_index_path", "v_longterm_log", "v_drawdown", "v_fear_greed",
             "v_sector_performance", "v_fx_trend", "v_rates_trend"],
    "安定上昇": ["v_index_path", "v_alltime_high", "v_longterm_log", "v_fear_greed",
             "v_sector_performance", "v_fx_trend", "v_rates_trend"],
    "暴騰":   ["v_alltime_high", "v_index_path", "v_fear_greed", "v_longterm_log",
             "v_sector_performance", "v_fx_trend", "v_rates_trend"],
}


SCOPE_SIM = """- このシミュレーションに存在しないものには言及しない。信託報酬・税金・為替・複数の商品・個別銘柄は
  存在しない。読者が画面で確認できない数値を出さない。"""
SCOPE_REAL = """- 渡された数値・見出しの範囲で書く。読者が確認できない数値を作らない。
- 個別銘柄の売買には踏み込まない。商品の推奨も否定もしない。
- 本研究が対象とするのは米国株（S&P500）のみである。欧州株・アジア株など他地域の市場や
  指数には触れない（ニュース見出しにその話が含まれていても、日報の本文には持ち込まない）。"""
PERIOD_SIM = """- この実験の時間の単位は月次であり、日次の値動きは存在しない。「一日の値動き」に言及しない。"""
PERIOD_REAL = """- 時間の単位は1営業日である。「今日」の値動きとして書く。
- 為替・金利・コモディティ・暗号資産・報道は、渡されたものについては実在するものとして扱う。"""


def build_system_common(kb, unit="month", fiction=True):
    """全期間・全局面で不変の部分。プロンプトキャッシュの対象になる。

    unit で「今月／今日」、fiction で固有名詞の扱いが変わる。
    1回の生成の中では固定なので、キャッシュは効いたままになる。
    """
    base = (SYSTEM_BASE.replace("__CLOSING__", closing_line(unit))
                       .replace("__UNIT__", unit_word(unit))
                       .replace("__PERIOD__", "月" if unit == "month" else "日")
                       .replace("__SCOPE__", SCOPE_SIM if fiction else SCOPE_REAL)
                       .replace("__PERIOD_RULE__",
                                PERIOD_SIM if unit == "month" else PERIOD_REAL))
    parts = [base, naming_rule(fiction), "\n\n# 土台となる原則"]
    for p in kb.get("principles", []):
        parts.append(f"\n- {p['title']}：{p['body']}")
    with open(HV_PATH, encoding="utf-8") as f:
        rows = json.load(f)["v_bear_markets"]["rows"]
    parts.append("\n\n# 過去の主要な弱気相場（月次終値・名目価格ベース、配当を含まない）")
    for r in rows:
        tail = "" if r.get("cite_alone", True) else "（※単独で引用しない）"
        parts.append(f"\n- {r['name']}：{r['peak']}から{r['decline_pct']}%、"
                     f"下落{r['decline_months']}か月、回復まで{r['recovery_months']}か月{tail}")
    parts.append("\n数値を挙げるときは、配当を含まない価格ベースであることを短く断る（毎回でなくてよい）。"
                 "都合のよい一例だけを選ばず、回復までの期間に幅があることも示す。"
                 "※印の行は名目・配当なしのため実際の投資家の体験と乖離が大きい。単独では引用しない。")
    recent = json.load(open(HV_PATH, encoding="utf-8"))["v_recent_drawdowns"]["data"]
    parts.append("\n\n# 直近10年に実際に起きた下落局面（日次・配当を含まない価格ベース）")
    for e in recent["episodes"]:
        rec = e.get("recovery_months")
        parts.append(f"\n- {e['name']}：{e['decline_pct']}%まで下落し、"
                     + (f"底から{rec}か月で最高値に戻った" if rec else "まだ回復していない"))
    parts.append("\n比較する相手は、今の下落幅に近いものを選ぶ。"
                 "下落幅が30%程度までなら、この直近の局面を引く。"
                 "上に挙げた歴史的な弱気相場（40%以上の下落・回復に数年）は、"
                 "それを超える深さのときだけ引く。規模も期間も離れた例を持ち出すと、"
                 "かえって現実味を失う。")

    parts.append("\n\n# 指し示せる図")
    for cid, desc in CHARTS.items():
        parts.append(f"\n- {cid}：{desc}")
    if unit == "day":
        for cid, desc in LIVE_ONLY_CHARTS.items():
            parts.append(f"\n- {cid}：{desc}")
    return "".join(parts)


def pick_quote(kb, phase, month, situation=None):
    """局面固有の金言を優先し、複数あれば月ごとに巡回させる（決定論的）。

    2026-09-23: 局面(phase)だけでは「ずっと下落している」のか「高騰の直後の
    一休み」なのかを区別できず、かけるべき言葉が違うという指摘を受けて、
    situation（classify_situation()が返す「継続下落」「反落」等）による
    優先選定を追加した。situationにも合う金言があればそれを最優先し、
    無ければ局面一致の金言、それも無ければ全局面共通("all")の金言を使う。

    また、"all"タグの金言は従来 specific が1件でもあれば完全に出番が無かった
    （pool = specific or general）。汎用的な金言を死蔵させないよう、
    situation一致が無い場合は「局面一致＋全局面共通」を合わせたプールから
    月ごとに巡回させる方式に変えた。
    """
    usable = [q for q in kb.get("quotes", []) if q.get("use", True)]
    specific = [q for q in usable if phase in q.get("phase_tags", [])]
    general = [q for q in usable if "all" in q.get("phase_tags", [])]
    situational = [q for q in specific
                   if situation and situation in q.get("situation_tags", [])]
    pool = situational or (specific + general) or general
    return pool[month % len(pool)] if pool else None


def _retrieve_knowledge(kb, phase, month, situation=None):
    """局面ごとに変わる部分。共通部には含めない。"""
    modules = [m for m in kb.get("phase_modules", []) if m["phase"] == phase]
    parts = []
    if modules:
        parts.append("【この局面の見方】")
        for m in modules:
            parts.append(f"- {m['title']}：{m['body']}（ねらい：{m.get('psychological_effect','')}）")
    emp = [e for m in modules for e in m.get("empathy", [])]
    if emp:
        parts.append("【この局面での共感の入り口（そのまま使わず、これを起点に自分の言葉で書く）】")
        parts.append(f"- {emp[month % len(emp)]}")
    q = pick_quote(kb, phase, month, situation)
    if q:
        parts.append("【使える金言】")
        parts.append(f"- {q['quote_ja']}（{q['author']}）")
    return "\n".join(parts)


# 本番（day）だけ、ページ側で常時表示する固定図になったので、LLMの選択肢からは外す。
# 実験（month）側は従来どおりCHART_BY_PHASEのまま選ばせる（v_index_pathがよく使われている
# のは知識ベースの外側の実装の話ではなく、単に局面と噛み合っているだけなので触らない）。
DAY_FIXED_CHARTS = {"v_index_path", "v_drawdown"}


# 下落の図は、いま最高値の近くにいると線が描かれず、空の図になる。この浅さ以下では使わせない
SHALLOW_DD = -1.5
DD_CHARTS = {"v_recent_drawdowns", "v_drawdown"}


def _allowed_charts(phase, unit="month", relations=False, dd_current=None):
    ids = CHART_BY_PHASE.get(phase, list(CHARTS))
    if unit == "month":
        # 実験の世界には為替・金利のデータがない（図が空になる）
        ids = [cid for cid in ids if cid not in ("v_fx_trend", "v_rates_trend")]
    if dd_current is not None and dd_current > SHALLOW_DD:
        ids = [cid for cid in ids if cid not in DD_CHARTS]
    if unit == "day":
        ids = [cid for cid in ids if cid not in DAY_FIXED_CHARTS]
    lines = [f"- {cid}：{CHARTS[cid]}" for cid in ids]
    # 関係の変化を検知した日だけ、その図を使えるようにする
    if unit == "day" and relations:
        lines += [f"- {cid}：{desc}" for cid, desc in LIVE_ONLY_CHARTS.items()]
    lines.append("これ以外の図は使わない。どれも噛み合わなければ chart は null にする。")
    return "\n".join(lines)


def _shown_episodes(worst):
    """図 v_recent_drawdowns に実際に描かれる局面を、本文と揃えるために明示する。"""
    from utils.visuals import select_recent
    with open(HV_PATH, encoding="utf-8") as f:
        eps = json.load(f)["v_recent_drawdowns"]["data"]["episodes"]
    picked = select_recent(eps, worst)
    if not picked or worst >= -0.05:
        return ""
    names = "／".join(f"{e['name']}（{e['decline_pct']}%・回復{e['recovery_months']}か月）"
                      for e in picked)
    return (f"\n- 図 v_recent_drawdowns に描かれる局面: {names}\n"
            "  この図を指す場合、本文で引く実例はこの局面に限る（図と本文を食い違わせない）")


# 1段落あたりの目安。話題が多い日は自然に長くなる
PER_BLOCK = (110, 160)
PER_BLOCK_EVENT = (130, 190)


def length_range(n_topics, is_event=False):
    lo, hi = PER_BLOCK_EVENT if is_event else PER_BLOCK
    return lo * n_topics, hi * n_topics


def _news_section(m):
    """報道の見せ方。台本は理由まで与えるが、実データでは見出しを渡すだけにする。

    2026-09-22、Finnhubの記事要約（summary）を取り込む案を一度試したが、著作権面の
    懸念（要約は見出しより著作物性が高く、しかもdaily_report.contextに恒久保存される
    設計だった）を理由に見送り、見出しのみに戻した（§25-6）。ニュース説明が薄いという
    指摘自体への対応は、要約以外の手段（例：媒体名・複数見出しの提示、金言の活用など）
    で引き続き検討する。
    """
    news = m.get("news") or {}
    heads = news.get("headlines") or []
    if heads:
        # 実験側の見出しにはsourceを付けていない（架空の報道機関名の捏造を避けるため。
        # §25系のニュース見出し統一を参照）。本番はFinnhubの実データでsourceが入る。
        # 2026-09-23、ここがh['source']決め打ちで実験側が必ずKeyErrorになっていたのを発見・修正。
        lines = [f"  - {h['text']}" + (f"（{h['source']}）" if h.get('source') else "")
                for h in heads]
        return ("- 参考にできる報道の見出し（実際に配信されたもの）:\n" + "\n".join(lines) +
                "\n  値動きの理由は、この見出しに書かれている場合にかぎり、報道として引く。"
                "「〜と伝えられています」「〜が理由として挙げられています」の形にし、"
                "媒体名を添えてよい。自分の見立てとして述べない。"
                "見出しに理由が書かれていなければ理由には触れず、数字と長期の文脈だけで書く。"
                "見出しにない出来事・見立てを持ち出さない。")
    headline = news.get("headline", "")
    cause = news.get("cause", "")
    out = []
    if headline:
        out.append(f"- 報道の見出し: {headline}")
    if cause:
        out.append(f"- {unit_word(m.get('unit', 'month'))}の値動きの理由: {cause}")
    if not out:
        out.append("- 報道は取れていない。値動きの理由には触れない")
    return "\n".join(out)


def _fx_line(m):
    """為替。円建て資産の伸びを左右するので、日次と年初来を両方渡す。"""
    fx = m.get("fx")
    if not fx:
        return ""
    ytd = ""
    if fx.get("ytd_yen") is not None:
        direction = "円安" if fx["ytd_yen"] > 0 else "円高"
        ytd = f"、年初来 {fx['ytd_yen']:+.2f}円（{direction}方向）"
    return (f"\n- ドル円: {fx['level']:.2f}円（前営業日比 {fx['day_yen']:+.2f}円"
            f"／{fx['day_pct']:+.2f}%{ytd}）")


def _rates_line(m):
    r = m.get("rates")
    if not r:
        return ""
    ytd = "" if r.get("ytd_bp") is None else f"、年初来 {r['ytd_bp']:+.0f}bp"
    return f"\n- 米10年債利回り: {r['level']:.2f}%（前営業日比 {r['day_bp']:+.1f}bp{ytd}）"


def _fund_line(m):
    """円建て投信の状況。本番だけ入る。円安・円高で体感が変わることを扱えるようにする。"""
    f = m.get("fund")
    if not f:
        return ""
    dd = f["drawdown"]
    return (f"\n- 円建て投信の基準価額: {f['nav']:,.0f}円（前日比 {f['change_pct']:+.2f}%、"
            f"最高値からの下落幅 {dd['current']:.1f}%）\n"
            "  ドル建ての指数と円建ての基準価額がずれるのは、おおむね為替のためである。"
            "触れる場合はその一言だけにし、為替の見通しは述べない。"
            "下落幅が指数と違うときは、その差を数字どおりに書く。"
            "『同様』『こちらも』のようにまとめて流さない。\n"
            "  ただし基準価額は、前営業日の米国市場と為替を反映して翌営業日に決まるため、"
            "指数や為替の当日の動きとは1日ずれる。"
            "指数の変化と為替の変化を足し引きして基準価額を説明しようとしない。")


def _earnings_line(m):
    """法人企業利益（FRED、四半期）。『見るべきは企業の稼ぐ力』を実数字で裏づける。

    四半期でしか更新されないので、その日の値動きの理由には使わせない。
    """
    e = m.get("earnings")
    if not e:
        return ""
    return (f"\n- 法人企業利益（米国、前年同期比）: {e['yoy_pct']:+.1f}%"
            f"（{e['asof']} 時点、四半期統計）\n"
            "  これは長期の話であり、その日の値動きの理由には使わない。"
            "長期の文脈のところで、『見るべきは企業の稼ぐ力』の裏づけとして、"
            "この数字にだけ触れてよい。強い・弱いの評価はこの数字の大小からだけ言う。")


def _relations_line(m):
    """指標どうしの関係の変化（utils/relations.py が計算で検知済み）。変わった日だけ入る。

    検知と数値はコードで決めてあるので、ここでは材料として渡すだけにする。
    """
    rel = m.get("relations")
    if not rel:
        return ""
    r = rel[0]
    try:
        from utils import relations as _R
        common = _R.load()["meta"].get("guide_common", "")
    except Exception:
        common = ""
    return (f"\n- 指標どうしの関係の変化（計算で検知済み）: {r['label']}で{r['kind_ja']}\n"
            f"  直近{r['n_recent']}営業日: {r['word_recent']}"
            f"（同じ向きに動いた日 {r['same_recent']}/{r['n_recent']}日）"
            f"／その前{r['n_base']}営業日: {r['word_base']}"
            f"（同じ向きに動いた日 {r['same_base']}/{r['n_base']}日）\n"
            f"  直近{r['n_recent']}営業日の動き: {r['a']['name']} {r['a']['move_text']}"
            f"（いま{r['a']['level_text']}）、{r['b']['name']} {r['b']['move_text']}"
            f"（いま{r['b']['level_text']}）\n"
            f"  一般に言われる関係: {r['prior']}\n"
            f"  書き方: {r['guide']}{r['hint']}{common}")


def _window_line(m):
    w = m.get("window")
    if not w:
        return ""
    return (f"\n  この下落幅は{w['label']}の最高値から測っている"
            f"（{w['start']} 以降の{w['days']}営業日）。"
            "本文でも「今年の最高値から」のように、どこからの下げかが分かる書き方にする。"
            "この期間の外の高値や下落には触れない")


def _dd_label(m):
    w = m.get("window")
    return f"{w['label']}の最高値からの下落幅" if w else "最高値からの下落幅"


_MONTH_WORDS = (("今日", "今月"), ("上がった日", "上がった月"), ("下げた日", "下げた月"),
                ("動いた日", "動いた月"), ("その日", "その月"))


def _unitize(text, unit):
    """話題の指示文は本番（日次）の言い回しで書いてあるので、月次では言い換える。"""
    if unit != "month":
        return text
    for a, b in _MONTH_WORDS:
        text = text.replace(a, b)
    return text


def structure_section(m, is_event, word):
    """本文の組み立て方。

    実験（月次）も本番（日次）と同じく、その期間に実際に動いたものを話題として並べる形にする
    （2026-10-01、通しプレイで「本番と型をそろえてほしい」との指摘を受けて、従来の4部構成から変更）。
    ロールモデルが1本で8〜9の話題を扱うのに倣ったもので、
    為替・金利・報道のように「今日それが起きたから触れる」項目を拾えるようにする。
    """
    segs = select_segments(m)
    n = len(segs)
    per_lo, per_hi = PER_BLOCK_EVENT if is_event else PER_BLOCK
    lo, hi = length_range(n, is_event)
    unit = m.get("unit", "month")
    topics = "\n".join(f"{i}. {_unitize(s['title'], unit)}："
                        f"{_unitize(s.get('guide_month') if unit == 'month' and s.get('guide_month') else s['guide'], unit)}"
                        for i, s in enumerate(segs, 1))
    return f"""# {word}取り上げる話題（この順に、1話題ずつ1段落。見出しは付けず地の文で）
{topics}

- blocks はちょうど{n}個にする。話題を飛ばさない、足さない。
- 全体で{lo}〜{hi}字。1段落あたり{per_lo}〜{per_hi}字程度。
- 図は、その段落の話題に対応するものが「本文で使ってよい図」にあれば、できるだけ付ける
  （読者が文章だけでなく図も見ながら追えるようにするため）。ただし無理にひねり出さず、
  噛み合わない段落は chart を null にする。同じ図を2段落以上で使い回さない。
- 与えられていない数値・銘柄・出来事を持ち出さない。取れていない項目には触れない。
- 話題をただ並べるのではなく、前の段落から自然につなぐ。"""


def build_user_prompt(m, kb, prev=None):
    mc = m["market_context"]
    unit = m.get("unit", "month")
    word = unit_word(unit)
    fg = mc["fear_greed"] or {"value": "—", "classification": "不明"}
    dd = mc["drawdown"]
    is_event = m["phase"] in EVENT_PHASES

    plan = structure_section(m, is_event, word)

    sectors = mc.get("sectors") or []
    if sectors:
        top, bottom = sectors[0], sectors[-1]
        sector_line = (f"- セクター: 最強 {SECTOR_JA.get(top['sector'], top['sector'])} "
                       f"{top['change_pct']:+.1f}% / 最弱 "
                       f"{SECTOR_JA.get(bottom['sector'], bottom['sector'])} "
                       f"{bottom['change_pct']:+.1f}%")
    else:
        sector_line = "- セクター別の内訳は取れていない。触れない"

    other_assets = "／".join(
        f"{i['symbol']} {i['change_pct']:+.1f}%" for i in mc["indices"]
        if i["symbol"] != "S&P500") or "取れていない"

    angle = ANGLES[(m["month"] - 1) % len(ANGLES)]
    vix_line = f"{mc['vix']}" if mc.get("vix") is not None else "取れていない"

    prev_line = ""
    if prev:
        pb = (prev.get("daily_report") or {}).get("blocks") or []
        used = [b["chart"] for b in pb if b.get("chart")]
        head = pb[0]["text"][:60] if pb else ""
        label = f"{prev.get('date') or str(prev['month']) + 'か月目'}・{prev['phase']}"
        prev_line = (f"\n\n# 前回（{label}）に書いたこと\n"
                     f"- 書き出し: {head}…\n"
                     f"- 使った図: {'／'.join(used) if used else 'なし'}\n"
                     "同じ言い回し・同じ図の繰り返しを避ける。前回と違う角度から入る。")

    return f"""次の状況について、長期投資家向けの日報を書いてください。字数は下の指示に従います。

# {word}の市場
- 局面: {m['phase']}
- 株価指数リターン: {m['return']*100:+.1f}%
- VIX: {vix_line}／Fear & Greed: {fg['value']}（{fg['classification']}）
{sector_line}
- 他の資産: {other_assets}
- {_dd_label(m)}: {dd['current']:.1f}%（この期間に経験した最大は {dd['max_so_far']:.1f}%）{_window_line(m)}{_rates_line(m)}{_fx_line(m)}{_fund_line(m)}{_earnings_line(m)}{_relations_line(m)}
{_news_section(m)}
{_shown_episodes(dd['max_so_far']) if ('v_recent_drawdowns' in CHART_BY_PHASE.get(m['phase'], []) and dd['current'] <= SHALLOW_DD) else ''}

# この局面で使える知識
{_retrieve_knowledge(kb, m['phase'], m['month'], m.get('situation'))}

# この回の切り口
{angle}
この角度から入ること。ただし無理に押し込まず、その{word[1:]}の数字と噛み合う形にする。

# 本文で使ってよい図
{_allowed_charts(m['phase'], m.get('unit', 'month'), bool(m.get('relations')), dd['current'])}

{plan}
出力は JSON のみ。本文を JSON の外に書かないこと。{prev_line}"""


def parsed_ok(text, blocks):
    """JSON として正しく読めたか。推敲版を採るかどうかの判断に使う。

    _parse は素の本文でも1ブロックを返すので、真偽だけでは
    「途中で切れた応答」と「ちゃんと書けた応答」を区別できない。
    """
    t = (text or "").strip()
    if not blocks or not t.endswith("}"):
        return False
    return not (len(blocks) == 1 and blocks[0].get("text", "").startswith("{"))


def _parse(text):
    """blocks を取り出す。旧形式や素の本文で返ってきても落とさない。"""
    t = (text or "").strip()
    cand = t[t.index("{"):t.rindex("}") + 1] if ("{" in t and "}" in t) else t
    try:
        d = json.loads(cand)
    except json.JSONDecodeError:
        return ([{"text": t, "chart": None}] if t else [])

    headline = (d.get("headline") or "").strip()
    if isinstance(d.get("blocks"), list):
        blocks = []
        for b in d["blocks"]:
            txt = (b.get("text") or "").strip()
            if not txt:
                continue
            ch = b.get("chart")
            blocks.append({"text": txt, "chart": ch if (ch in CHARTS or ch in LIVE_ONLY_CHARTS) else None})
        if blocks:
            blocks[0]["headline"] = headline
            return blocks

    # 旧形式（body + chart）
    body = (d.get("body") or "").strip()
    if body:
        ch = d.get("chart")
        return [{"text": p.strip(), "chart": (ch if (ch in CHARTS or ch in LIVE_ONLY_CHARTS) else None) if i == 0 else None}
                for i, p in enumerate(body.split("\n")) if p.strip()]
    return ([{"text": t, "chart": None}] if t else [])


REVISE_PROMPT = """上はあなたが書いた下書きです。読者に届くものにするため、自分で点検して書き直してください。

# 点検すること
1. 与えられた数値と食い違っていないか。特に「最高値からの下落幅」と矛盾する表現はないか
2. 図を指した段落は、その図が何を示しているかに触れているか。指した図と本文で引いた実例は一致しているか
3. 締めが決まり文句で終わっているか。書き出しが型どおりか
4. 言ってはいけないことを言っていないか（相場の見通しを根拠にした売買の指示）
5. 見出しは25字以内で、その月を言い表せているか

# 書き直すこと
- 説明的で平板な文を削る。同じことを二度言っている箇所をまとめる
- 教科書のような一般論で終わっている段落があれば、その月の数字に結びつけ直す
- 淡々とした語りの中に、印象に残る一言が一箇所あるとよい。無理に入れる必要はない
- 読者が声に出して読んだときに、詰まらずに流れるか

字数は変えなくてよい。全面的に書き直す必要はなく、効く箇所だけ直す。
出力は下書きと同じ JSON の形式のみ。"""


def generate_report(m, kb, prev=None, system=None):
    """文脈1件から日報を作る。台本でも実データでも通る道はここ1本だけ。"""
    system = system or build_system_common(kb, m.get("unit", "month"))
    user = build_user_prompt(m, kb, prev)
    label = m.get("date") or m["month"]
    text, usage = chat(system_common=system, system_variable="",
                       messages=[{"role": "user", "content": user}],
                       max_tokens=MAX_TOKENS)

    if REVISE and text.strip():
        text2, u2 = chat(
            system_common=system, system_variable="",
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": text},
                {"role": "user", "content": REVISE_PROMPT},
            ],
            max_tokens=MAX_TOKENS,
        )
        add_usage(usage, u2)
        b2 = _parse(text2)
        # 途中で切れた推敲版で、書けている下書きを潰さない
        if parsed_ok(text2, b2):
            text = text2
        else:
            print(f"  ! {label}: 推敲版が壊れていたので下書きを採用します", flush=True)

    blocks = _parse(text)
    with open(RAW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": label, "phase": m["phase"],
                            "raw": text, "blocks": blocks}, ensure_ascii=False) + "\n")
    if not blocks:
        print(f"  ! {label}: 本文が空です（{RAW_LOG} を確認）", flush=True)
    elif not text.strip().endswith("}"):
        print(f"  ! {label}: 応答が途中で切れた可能性（{RAW_LOG} を確認）", flush=True)
    return blocks, usage


# 旧名。既存の呼び出しを壊さないために残す
generate_month = generate_report


def _readable(m, blocks, headline=None):
    mc = m["market_context"]
    hl = headline if headline is not None else (
        blocks[0].get("headline", "") if blocks else "")
    label = m.get("date") or f"{m['month']}か月目"
    fg = mc["fear_greed"] or {"value": "—", "classification": "不明"}
    head = (f"===== {label}  {m['phase']}  r={m['return']*100:+.1f}%  "
            f"VIX {mc['vix']}  F&G {fg['value']}（{fg['classification']}）  "
            f"DD {mc['drawdown']['current']:.1f}%"
            f"（最大 {mc['drawdown']['max_so_far']:.1f}%） =====\n"
            f"【{hl}】")
    body = "\n\n".join(
        b["text"] + (f"\n  ［図: {b['chart']}］" if b["chart"] else "") for b in blocks)
    return head + "\n" + body


def _parse_months(args):
    out = set()
    for a in args:
        if a.startswith("-"):
            continue
        if "-" in a:
            lo, hi = a.split("-")
            out |= set(range(int(lo), int(hi) + 1))
        else:
            out.add(int(a))
    return out


def _headline_of(blocks):
    return blocks[0].pop("headline", "") if blocks else ""


# ── チャート注記の「つながって見えるところ」──────
LINKS_SYSTEM = """あなたは長期・インデックス投資の日報に添える、短い解説を書きます。

- 「です・ます体」。冷静・淡々。煽らない。
- 読者は積立を続けている人です。売買を勧めることも止めることもしません。
- 相場の先行きを予測しません。
- 渡された数値だけを使います。数値を作りません。
- 理由は、渡された報道の見出しから読み取れる範囲でだけ書きます。
  結び付けられないときは、無理に理由を作らず「はっきりした理由は見当たりません」と書きます。
- 断定しません。「〜のようです」「〜が意識されているようです」の形にします。
- 出力は JSON だけ。前後に説明を付けません。"""


TRANSLATE_SYSTEM = """あなたはニュース見出しを日本語に翻訳します。
- 直訳ではなく、日本語のニュース見出しとして自然な言い回しにします。
- 固有名詞（人名・組織名・地名）は一般的な日本語表記にします。
- 意味を変えず、誇張も省略もしません。
- 出力は JSON だけ。前後に説明を付けません。"""


NEWS_SELECT_SYSTEM = """あなたは長期・インデックス投資家向けに、その日の市場ニュース見出しを厳選します。
- 見出しだけを読んで内容が伝わるものを選ぶ。「〜のポイント」「注目すべきN選」のように
  中身を開かないと分からないリスト記事・後で読ませる系の見出しは選ばない。
- 個別銘柄の推奨・値上がり銘柄紹介など、特定の銘柄に焦点を当てたものは選ばない。
- 米国株（S&P500）に関わるマクロ経済・金融政策・米国市場全体の動きを優先する。
  米国株への影響が見出しから読み取れない、他地域市場だけの話題は選ばない。
- 誇張・扇動的な見出しは選ばない。実際にあったことだけを伝える見出しを選ぶ。
- 基準を満たすものが無ければ、無理に件数をそろえなくてよい。
- 出力は JSON だけ。前後に説明を付けない。"""


def select_headlines(candidates, limit=5):
    """候補見出しから、長期投資家に有益なものだけを選び直す（2026-09-26、本人指摘）。

    キーワード一致（_is_market_news）だけでは、個別銘柄の推奨記事や中身の分からない
    リスト記事、米国株に関係のない他地域市場ニュースまで拾ってしまうため、ここでLLMに
    絞り込ませる。失敗時はキーワード一致の上位をそのまま使う（ニュース欄を空にしない）。
    """
    if not candidates:
        return candidates, zero_usage()
    lines = "\n".join(f"{i}: {c['text']}" for i, c in enumerate(candidates))
    user = f"""次の見出しから、基準を満たすものを最大{limit}件、良い順に選んでください。

{lines}

出力は次の形の JSON のみ。
{{"selected": [番号, ...]}}"""
    text, usage = chat(system_common=NEWS_SELECT_SYSTEM, system_variable="",
                       messages=[{"role": "user", "content": user}], max_tokens=300)
    t = (text or "").strip()
    try:
        cand = t[t.index("{"):t.rindex("}") + 1]
        idx = json.loads(cand).get("selected") or []
        picked = [candidates[i] for i in idx if isinstance(i, int) and 0 <= i < len(candidates)]
    except (ValueError, json.JSONDecodeError, TypeError, IndexError):
        return candidates[:limit], usage
    return (picked or candidates[:limit]), usage


def translate_headlines(heads):
    """表示用に、英語の生見出しを日本語へ訳す。

    本文の理由付け（_news_section / explain_links）は原文の英語見出しをそのまま使う。
    ここは表示だけの話なので、多少の意訳は許容する。失敗しても日報自体は止めない
    （呼び出し側で英語のまま表示すればよいだけ）。
    """
    if not heads:
        return {}, zero_usage()
    lines = "\n".join(f"{i}: {h['text']}" for i, h in enumerate(heads))
    user = f"""次の見出しをそれぞれ日本語に訳してください。

{lines}

出力は次の形の JSON のみ。
{{"0": "訳文", "1": "訳文", ...}}"""
    text, usage = chat(system_common=TRANSLATE_SYSTEM, system_variable="",
                       messages=[{"role": "user", "content": user}], max_tokens=800)
    t = (text or "").strip()
    try:
        cand = t[t.index("{"):t.rindex("}") + 1]
        out = json.loads(cand)
    except (ValueError, json.JSONDecodeError):
        return {}, usage
    return out, usage


def explain_links(ctx, items, kb=None):
    """指標どうしの関係に、その日の理由を添える。

    どの関係が成り立っているか、どの数値を使うかは、すべてコード側で決めてある。
    LLM が担うのは言い回しと、見出しからの理由付けだけ。
    """
    if not items:
        return {}, zero_usage()

    cfg = json.load(open(os.path.join("knowledge", "chart_reading.json"),
                         encoding="utf-8"))
    w = cfg.get("links_writing", {})
    heads = (ctx.get("news") or {}).get("headlines") or []
    head_lines = "\n".join(f"  - {h['text']}（{h['source']}）" for h in heads) or "  （なし）"

    blocks = []
    for it in items:
        facts = "／".join(f"{k} {v}" for k, v in (it.get("facts") or {}).items())
        blocks.append(f"- id: {it['id']}\n  状況: {it['when']}\n  数値: {facts}\n"
                      f"  書くこと: {it.get('guide', '')}")

    rules = "\n".join(f"- {r}" for r in w.get("rules", []))
    user = f"""次の関係について、それぞれ短い解説を書いてください。

# 今日の相場
- 株価指数リターン: {ctx['return']*100:+.2f}%
- VIX: {ctx['market_context'].get('vix')}／Fear & Greed: {(ctx['market_context'].get('fear_greed') or {}).get('value')}

# 報道の見出し（実際に配信されたもの）
{head_lines}

# 書く対象
{chr(10).join(blocks)}

# 決まり
- {w.get('length', '各項目120〜180字')}
{rules}

出力は次の形の JSON のみ。
{{"id": "本文", ...}}"""

    text, usage = chat(system_common=LINKS_SYSTEM, system_variable="",
                       messages=[{"role": "user", "content": user}], max_tokens=1200)
    t = (text or "").strip()
    try:
        cand = t[t.index("{"):t.rindex("}") + 1]
        out = json.loads(cand)
    except (ValueError, json.JSONDecodeError):
        return {}, usage
    return {k: v for k, v in out.items() if isinstance(v, str) and v.strip()}, usage


# ── 実験（台本）────────────────────────────
def run_scripted(args):
    mode = args[0]
    prov = ScriptedProvider(SCENARIO_PATH)
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    system = build_system_common(kb, "month", FICTION)
    total = zero_usage()
    print(f"model: {model_id()}", flush=True)

    if mode == "sample":
        months = [int(a) for a in args[1:]] or [18, 57, 8]
        out = []
        for mo in months:
            m = prov.context(mo)
            blocks, u = generate_report(m, kb, prov.previous(mo), system)
            add_usage(total, u)
            out.append(_readable(m, blocks))
        path = os.environ.get("SAMPLE_OUT", "daily_report_sample.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(out))
        print(f"generated {len(months)} months -> {path}")
        print(format_usage(total))
        return

    keys = prov.keys()
    force = os.environ.get("FORCE") == "1"
    only = _parse_months(args[1:]) if len(args) > 1 else None
    if only:
        force = True

    for i, key in enumerate(keys, 1):
        m = prov.context(key)
        m.setdefault("daily_report", {"group1": "", "group2": ""})
        if only is not None and key not in only:
            continue
        if m["daily_report"].get("blocks") and not force:
            print(f"[{i}/{len(keys)}] month {key} skip", flush=True)
            continue
        blocks, u = generate_report(m, kb, prov.previous(key), system)
        add_usage(total, u)
        prov.save_report(key, blocks, _headline_of(blocks))
        print(f"[{i}/{len(keys)}] month {key} done", flush=True)
        if i % 5 == 0:
            prov.flush()

    prov.flush()
    print(f"done: {len(keys)} months -> {SCENARIO_PATH}", flush=True)
    print(format_usage(total), flush=True)


# ── 本番（実データ）─────────────────────────
def run_live(args):
    prov = LiveProvider()
    prov.init_store()
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)

    asked = next((a for a in args[1:] if a[:1].isdigit() and "-" in a), None)
    force = "--force" in args

    # 休場日・未収集の日は、そもそも日報を作らない
    status = prov.session_status()
    if status["state"] == "open" and status.get("weekend"):
        print(f"◆ {closed_message(status)}")
    if status["state"] != "open" and not asked:
        print(f"◆ {closed_message(status)}")
        if status["state"] == "closed":
            print("  日報は作りません。")
        else:
            print("  収集（collect_all.py）を先に回してください。")
        if status.get("last"):
            print(f"  直近の日報は {status['last']} 分です。")
        if not force:
            return

    key = asked or prov.latest()
    if not key:
        print("価格データがありません。collect_fred.py を先に回してください")
        return
    ctx = prov.context(key)

    # キーワード一致の候補から、長期投資家向けに有益なものだけへ絞り直す。
    # 本文生成より前に差し替えることで、本文の理由付けにも絞り込み後の見出しを使う。
    news_usage = None
    news = ctx.get("news") or {}
    if news.get("candidates"):
        try:
            selected, news_usage = select_headlines(news["candidates"])
            if selected:
                news["headlines"] = selected
                news["headline"] = selected[0]["text"]
        except Exception as e:
            print(f"  ! ニュース見出しの選定に失敗しました（キーワード一致のみで表示します）: {e}",
                  flush=True)

    print(f"対象日 : {key}（{ctx['phase']}／{ctx['return']*100:+.2f}%）")
    print(f"model  : {model_id()}")
    checks = [("重大", m) for m in validate(ctx)] + prov.check(ctx)
    severe = [m for sev, m in checks if sev == "重大"]
    for sev, msg in checks:
        print(f"  [{sev}] {msg}")
    if not checks:
        print("  データの点検: 問題なし")

    if "--dry" in args:
        print(json.dumps(ctx, ensure_ascii=False, indent=1))
        return
    if severe and "--allow-stale" not in args:
        print("\n重大な問題があるため生成しません。"
              "収集を回し直すか、承知のうえなら --allow-stale を付けてください")
        return
    if prov.exists(key) and not force:
        print("この日の日報はすでにあります（--force で作り直し）")
        return

    system = build_system_common(kb, "day", fiction=False)
    print("日報を生成しています…", flush=True)
    blocks, usage = generate_report(ctx, kb, prov.previous(key), system)
    if news_usage:
        add_usage(usage, news_usage)
    headline = _headline_of(blocks)

    # 表示用に見出しを日本語へ。本文の理由付けは原文の英語見出しのままなので、
    # ここで失敗しても本文の正しさには影響しない
    heads = (ctx.get("news") or {}).get("headlines") or []
    if heads:
        try:
            translated, u_tr = translate_headlines(heads)
            add_usage(usage, u_tr)
            for i, h in enumerate(heads):
                h["text_ja"] = translated.get(str(i), "")
        except Exception as e:
            print(f"  ! 見出しの翻訳に失敗しました（英語のまま表示します）: {e}", flush=True)

    # 指標どうしの関係より先に本文を保存する。
    # あとの工程で落ちても、払ったぶんの日報は残す。
    prov.save_report(key, blocks, headline, ctx, model_id(), usage)

    # 指標どうしの関係。成り立つかどうかと数値はコードで決め、理由付けだけ書かせる
    from utils.chart_notes import links as build_links
    items = build_links(ctx, history=prov.history(key))
    if items:
        print(f"つながって見えるところを{len(items)}件、説明しています…", flush=True)
    try:
        written, u3 = explain_links(ctx, items)
        add_usage(usage, u3)
    except KeyboardInterrupt:
        print("  ! 中断されました。本文は保存済みです", flush=True)
        written = {}
    except Exception as e:
        print(f"  ! 説明の生成に失敗しました（本文は保存済み）: {e}", flush=True)
        written = {}
    for it in items:
        it.pop("guide", None)
        if written.get(it["id"]):
            it["text"] = written[it["id"]]
    prov.save_report(key, blocks, headline, ctx, model_id(), usage, items)
    print()
    print(_readable(ctx, blocks, headline))
    print()
    if items:
        print("\n--- つながって見えるところ ---")
        for it in items:
            print(f"・{it['text']}")
    print()
    print(format_usage(usage))
    print(f"保存先: investment_ai.db / daily_report / {key}")


def main():
    args = sys.argv[1:] or ["sample"]
    mode = args[0]
    if mode == "live":
        run_live(args)
    elif mode in ("sample", "all"):
        run_scripted(args)
    else:
        print("mode は sample / all / live")


if __name__ == "__main__":
    from utils.runlog import tee
    tee("report")
    main()
