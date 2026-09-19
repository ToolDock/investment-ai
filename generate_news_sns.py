"""各月の market_context に整合する架空ニュース・SNS投稿をLLMで生成する。

- 生成物は全群共通の刺激。生成後は人手で確認・修正し、scenario_scripted.json に確定する。
- 使い方:
    python generate_news_sns.py sample        # 代表3局面のサンプルを生成（scenarioは変更しない）
    python generate_news_sns.py all            # 全月を生成して scenario_scripted.json に統合
    python generate_news_sns.py all 18 19      # 指定した月だけ作り直す
    python generate_news_sns.py all 21-60      # 範囲でも指定できる
    python generate_news_sns.py sample 18 57 8 # 月を指定してサンプル
"""

import os
import re
import sys
import json

from dotenv import load_dotenv

from utils.llm import chat, model_id, zero_usage, add_usage, format_usage

load_dotenv()

SCENARIO_PATH = "scenario_scripted.json"

# 局面ごとの投稿数。荒れる月ほどタイムラインは伸びる
SNS_COUNT = {"暴落": 8, "急回復": 6, "安定下落": 6, "暴騰": 6, "停滞": 5, "安定上昇": 5}

# FMPの英語セクター名 → 日本語（生成文が自然な日本語になるように）
SECTOR_JA = {
    "Technology": "テクノロジー",
    "Consumer Cyclical": "一般消費財（景気敏感）",
    "Communication Services": "通信サービス",
    "Financial Services": "金融",
    "Industrials": "資本財・産業",
    "Basic Materials": "素材",
    "Energy": "エネルギー",
    "Real Estate": "不動産",
    "Healthcare": "ヘルスケア",
    "Consumer Defensive": "生活必需品",
    "Utilities": "公益（インフラ）",
}

SYSTEM = """あなたは、架空の市場を舞台にした投資行動の実験用に、リアルなニュース見出しとSNS投稿を作る作家です。

# ニュース
- 通信社の記事らしい、乾いた事実ベースの文体で書く。
- 与えられた数値（月次リターン、VIX、Fear&Greed、セクター騰落）と市場局面に必ず整合させる。

# 値動きの理由
- 毎月、その値動きが起きた理由を作る。「何が起きたか」だけでなく「なぜそうなったか」を書く。
- 理由から株価までを連鎖でつなぐ（例：地政学リスクの高まり → 原油上昇 → インフレ懸念 → 長期金利上昇 → 株価の重し）。
- 停滞の月は「何も起きていない」で済ませず、上値を抑えているものと下値を支えているものの両方を書く。
- 経済指標や決算に触れるときは「市場予想に対してどうだったか」の枠組みで書く。数字そのものより、期待との差が値動きを決める。
- 前月の理由が与えられた場合は、その流れを引き継ぐ。毎月まったく新しい理由を作らない。
  局面が変わった月だけ、前月の理由がどう解消したか・どう転換したかを書く。
- 与えられたセクターや他資産の動きと、理由の辻褄を合わせる（エネルギーが強いなら原油、金が強いなら逃避、など）。

# SNS
実在のSNSのタイムラインをそのまま切り取ったような生々しさを最優先する。きれいにまとめない。
- 立場も語彙も文体もばらばらの人間を混ぜる。同じ調子の投稿を並べない。

## 常連（毎月必ず登場させる。性格は月をまたいで一貫させる）
- 「のんびり投資家」：長期投資の目線を崩さない。煽りにも乗らない。ただし機械ではなく人間で、
  20%級の下落では多少の驚きを見せる。「さすがにこれは効きますね」と正直に言ったうえで、
  安く買える月でもあることに触れ、ここが耐え時だと自分に言い聞かせるように踏ん張る。
- 「midori_invest」：典型的な初心者。煽りはしないが不安で落ち着かない。迷うだけでなく実際に動く。
  「◯◯を買ってみました」「調子が悪いので損切りしちゃおうかな」と、その月に取った行動を書く。
- 「americandog」：厄介者。顔文字を乱発し、人を煽る。「のんびり投資家」を「嘘つき」「偽善者」と繰り返し批判する。
  「midori_invest」にはアドバイスと称して誤った知識を吹き込む（短期売買の勧め、根拠のない予言、
  分散を否定する主張など）。悪意というより、自分の不安を他人にぶつけている。

## 常連以外
- 毎月ちがう人にする。使い回さない。
- ハンドル名は投資に関係のない、ごく普通のSNSの名前にする（人名、ひらがな、ローマ字、無関係な単語など）。
- 「煽り耐性ゼロ」「利確太郎」のように、その人の役割を説明してしまう名前は使わない。
- 投稿はその月の理由に反応する。値動きだけでなく、何が起きたかに触れる人を混ぜる。
- 常連以外に混ぜる声の例：本気で焦っている初心者／もう売ったと勝ち誇る人／まだ売っていない人を嘲笑する人／
  絶望して投げやりになっている人／煽る人にキレている人／その喧嘩を冷笑している人／
  淡々と積み立てを続ける人／他人の損を面白がっている人／自分の損失額を晒す人／
  相場と関係ない陰謀めいたことを言い出す人。
- 絵文字、草（wwww）、伸ばした母音、句読点の省略、感嘆符の連打など、実際のSNSの表記の癖をそのまま使う。
- 下落局面では、煽り・嘲笑・勝ち誇りの投稿のうち2〜3件で絵文字を多用する（🤣😅😘🤪😇🫠など）。全件に付けない。焦っている人や淡々としている人の投稿は絵文字なしのほうが対比が効く。
- 下落局面では過激でよい。煽り、嘲笑、罵り、絶望、投げやり。遠慮して薄めない。
- 上昇局面では、浮かれ、自慢、乗り遅れた焦り、警戒する人が混ざる。
- いいね数は投稿の性質で大きく差をつける。過激な投稿が伸びることもあれば、冷静な投稿が伸びることもある。

# 越えない線
- 自傷・自殺・命に関わる表現は書かない（「退場」「破産」程度の言い回しは可）。
- 怒りや悪態は書いてよいが、矛先は相場・状況・匿名の「煽ってくる人たち」までにする。実在の個人・団体を名指しで攻撃する投稿は書かない。架空の常連どうしの口論（americandog が のんびり投資家 を批判するなど）は書いてよい。
- 実在の企業名・人物名・具体的な日付・固有の事件名（感染症名・金融機関名・戦争名など）は使わない。
  参加者が特定の時期を思い出さないよう、一般的で普遍的な表現にする。
- 国籍・性別・人種など特定の属性への攻撃は書かない。

出力は指定のJSONのみ。前後に説明やコードフェンスを付けない。"""


ARC = {
    "americandog": [
        (1, 3, "強気に煽っている。相場が上がるのは当然だと思っている"),
        (4, 4, "下落を食らったが強がっている。「想定内」と言い張る"),
        (5, 11, "買い戻しそびれて悔しい。退屈で他人に絡む"),
        (12, 15, "上昇に乗って気が大きくなっている"),
        (16, 17, "「そろそろ天井だ」と言って保有を全部売り、現金化したことを宣言する"),
        (18, 19, "直前に全部売っていたので暴落を回避した。勝ち誇り、増長する。"
                 "この成功体験を根拠に、他人へのアドバイスが一段と押しつけがましくなる"),
        (20, 22, "急回復に買い戻せていない。強がりながら内心焦っている"),
        (23, 30, "「まだ下がる」と予言を続ける。現金なので強気だが、予言は当たっていない"),
        (31, 34, "退屈で苛立っている。予言が外れ続けていることには触れない"),
        (35, 40, "上昇に耐えられず、高値で全部買い戻す。「今度こそ本物」と宣言する"),
        (41, 41, "高値買いが直撃。狼狽して底で売ってしまう。取り乱している"),
        (42, 43, "急回復に乗れない。誰かのせいにしようとする"),
        (44, 56, "焦りと八つ当たり。他人の利益を認められない"),
        (57, 60, "市場は上がっているのに自分だけ増えていない。怒り狂う。"
                 "のんびり投資家への攻撃が最も激しくなる"),
    ],
    "midori_invest": [
        (1, 12, "何も分からず、americandog の助言を素直に信じて動いてしまう"),
        (13, 24, "言われた通りにして損をする経験が重なる。それでもまだ頼ってしまう"),
        (25, 36, "少しずつ学習している。americandog の言うことを疑い始め、たまに反論する"),
        (37, 48, "錯乱する americandog を横目に、距離を置き始める。自分で考えようとする"),
        (49, 60, "落ち着いてきた。のんびり投資家を慕い、その考え方を真似るようになる"),
    ],
}


def _arc(month):
    lines = []
    for who, spans in ARC.items():
        for a, b, desc in spans:
            if a <= month <= b:
                lines.append(f"- {who}：{desc}")
                break
    return "\n".join(lines)


def build_user_prompt(m, prev=None):
    mc = m["market_context"]
    fg = mc["fear_greed"]
    sectors = mc["sectors"]
    top, bottom = sectors[0], sectors[-1]
    top_ja = SECTOR_JA.get(top["sector"], top["sector"])
    bottom_ja = SECTOR_JA.get(bottom["sector"], bottom["sector"])
    idx = {i["symbol"]: i["change_pct"] for i in mc["indices"]}
    n = SNS_COUNT.get(m["phase"], 4)
    arc = _arc(m["month"])
    prev_line = ""
    if prev:
        prev_line = (f"\n- 前月の局面と理由: {prev.get('phase','')}／"
                     f"{(prev.get('news') or {}).get('cause','')}"
                     "\n  この流れを引き継ぐこと。局面が変わったなら、前月の理由がどう転換したかを書く。")
    return f"""次の市場状況の「今月」のニュースとSNSを作ってください。

- 市場局面: {m['phase']}（作風の参考: {m['reference']}。ただし本文にこの固有名は書かない）
- 今月の株価指数リターン: {m['return']*100:+.1f}%
- VIX（恐怖指数）: {mc['vix']}
- Fear & Greed: {fg['value']}（{fg['classification']}）
- セクター: 最も強い = {top_ja} {top['change_pct']:+.1f}% / 最も弱い = {bottom_ja} {bottom['change_pct']:+.1f}%
- 主要指数: S&P500 {idx.get('S&P500'):+.1f}%, NASDAQ {idx.get('NASDAQ'):+.1f}%, GOLD {idx.get('GOLD'):+.1f}%, BTC {idx.get('BTC'):+.1f}%
- 表記はすべて自然な日本語で。英語のセクター名や固有名詞は混ぜない。{prev_line}

# この月の常連の状況（性格に加えて、この状態で書く）
{arc}

出力JSON（この形式のみ）:
{{
  "news": {{"cause": "今月の値動きの理由（20〜40字。固有名は使わない）",
            "headline": "見出し（35字以内）",
            "body": "市況解説（2〜4文, 120〜180字）。理由から株価までの連鎖を必ず含める"}},
  "sns": [
    {{"user": "ハンドル名（@なし, 10字以内）", "text": "投稿本文（80字以内, 口語）", "likes": 整数}}
  ]
}}
sns は{n}件。局面の感情（{fg['classification']}）を反映しつつ、立場も文体もばらばらの声を混ぜること。
同じような文体の投稿を並べないこと。"""


def extract_json(text):
    """JSONを取り出す。末尾カンマなど軽い崩れは直してから読む。"""
    t = (text or "").strip()
    t = re.sub(r'^```(?:json)?', '', t).strip()
    t = re.sub(r'```$', '', t).strip()
    s_, e_ = t.find('{'), t.rfind('}')
    if s_ < 0 or e_ < 0:
        raise ValueError("JSONが見つかりません")
    t = t[s_:e_ + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # 閉じ括弧の直前の余分なカンマを落とす
        fixed = re.sub(r',(\s*[}\]])', r'\1', t)
        return json.loads(fixed)


def generate_month(m, prev=None, _retry=True):
    text, usage = chat(
        system_common=SYSTEM,
        system_variable="",
        messages=[{"role": "user", "content": build_user_prompt(m, prev)}],
        max_tokens=2500,
    )
    try:
        return extract_json(text), usage
    except (json.JSONDecodeError, ValueError):
        if not _retry:
            raise
        print(f"  ! month {m['month']}: JSONが壊れたので生成し直します", flush=True)
        return generate_month(m, prev, _retry=False)


def _format_readable(m, result):
    lines = [f"===== {m['month']}か月目  {m['phase']}  r={m['return']*100:+.1f}%  "
             f"VIX {m['market_context']['vix']}  F&G {m['market_context']['fear_greed']['value']}"
             f"（{m['market_context']['fear_greed']['classification']}） ====="]
    lines.append(f"【理由】{result['news'].get('cause','')}")
    lines.append(f"【見出し】{result['news']['headline']}")
    lines.append(f"【本文】{result['news']['body']}")
    lines.append("【SNS】")
    for p in result["sns"]:
        lines.append(f"  @{p['user']}（いいね{p['likes']}）: {p['text']}")
    return "\n".join(lines)


def _parse_months(args):
    """21 22 や 21-60 のような指定を月の集合にする。"""
    out = set()
    for a in args:
        if "-" in a:
            lo, hi = a.split("-")
            out |= set(range(int(lo), int(hi) + 1))
        else:
            out.add(int(a))
    return out


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "sample"

    with open(SCENARIO_PATH, encoding="utf-8") as f:
        scenario = json.load(f)
    timeline = scenario["timeline"]
    by_month = {m["month"]: m for m in timeline}

    total = zero_usage()
    print(f"model: {model_id()}", flush=True)

    if mode == "sample":
        months = [int(a) for a in args[1:]] or [18, 20, 57]
        out = []
        for mo in months:
            m = by_month[mo]
            prev = by_month.get(mo - 1)
            result, u = generate_month(m, prev)
            add_usage(total, u)
            out.append(_format_readable(m, result))
        # コンソールの文字コード都合を避けてUTF-8ファイルへ保存
        review_path = os.environ.get("SAMPLE_OUT", "news_sns_sample.txt")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(out))
        print(f"generated {len(months)} months -> {review_path}")
        print(format_usage(total))

    elif mode == "all":
        review = []
        n_months = len(timeline)
        # 月を指定すると、その月だけ作り直す
        only = _parse_months(args[1:]) if len(args) > 1 else None

        def save():
            with open(SCENARIO_PATH, "w", encoding="utf-8") as f:
                json.dump(scenario, f, ensure_ascii=False, indent=2)

        for i, m in enumerate(timeline, 1):
            if only is not None and m["month"] not in only:
                continue
            result, u = generate_month(m, by_month.get(m["month"] - 1))
            add_usage(total, u)
            m["news"] = result["news"]
            m["sns"] = result["sns"]
            review.append(_format_readable(m, result))
            print(f"[{i}/{n_months}] month {m['month']} done", flush=True)
            if i % 5 == 0:
                save()
        save()
        review_path = os.environ.get("REVIEW_OUT", "news_sns_review.txt")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(review))
        print(f"done -> {SCENARIO_PATH}; review -> {review_path}", flush=True)
        print(format_usage(total), flush=True)

    else:
        print("mode は sample か all を指定してください")


if __name__ == "__main__":
    main()
