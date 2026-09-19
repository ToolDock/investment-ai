"""事前アンケートの設問定義とスコアリング。

金融リテラシー設問は Lusardi & Mitchell の "Big Three"（複利・インフレ・分散投資）を
日本語化したものに、本研究の主題である長期投資に関する1問を加えた構成。
各設問に自信度（confidence）を併せて取得し、自信過剰バイアス（キャリブレーション）を測る。
"""

# 属性設問の選択肢
GENDER_OPTIONS = ["男性", "女性", "その他", "無回答"]

INVEST_EXPERIENCE_OPTIONS = [
    "現在投資している",
    "過去に投資していた（今はしていない）",
    "投資したことはない",
]

INVEST_YEARS_OPTIONS = [
    "投資経験なし",
    "1年未満",
    "1〜3年",
    "3〜5年",
    "5〜10年",
    "10年以上",
]

# 自信過剰（overplacement）を測る自己評価
SELF_RANK_OPTIONS = [
    "上位25%以内（同年代より詳しい）",
    "上位25〜50%",
    "下位25〜50%",
    "下位25%以内（同年代より詳しくない）",
]

# 金融リテラシー設問（客観・正誤あり）
FIN_LITERACY = [
    {
        "id": "compound",
        "text": "元本100万円を年利2%の複利で5年間運用しました（手数料・税金は考えません）。"
                "5年後の金額に最も近いものはどれですか。",
        "options": ["110万円より多い", "ちょうど110万円", "110万円より少ない", "わからない"],
        "correct": "110万円より多い",
    },
    {
        "id": "inflation",
        "text": "預金の金利が年1%、物価上昇率（インフレ）が年2%だとします。"
                "1年後、この預金で買えるモノの量は今日と比べてどうなりますか。",
        "options": ["増える", "変わらない", "減る", "わからない"],
        "correct": "減る",
    },
    {
        "id": "diversification",
        "text": "「1つの会社の株式だけを買うことは、複数の会社に投資する株式投資信託を買うことより、"
                "ふつう安全である」。この文は正しいですか。",
        "options": ["正しい", "間違い", "わからない"],
        "correct": "間違い",
    },
    {
        "id": "long_term",
        "text": "「過去の実績では、米国株の代表的な指数（S&P500）は、保有期間が長くなるほど"
                "元本割れする可能性が低くなる傾向がある」。この文は正しいですか。",
        "options": ["正しい", "間違い", "わからない"],
        "correct": "正しい",
    },
]

# 自信度（1〜4）
CONFIDENCE_OPTIONS = ["自信なし", "あまり自信がない", "やや自信がある", "自信がある"]


def score_literacy(answers):
    """金融リテラシーの回答をスコアリングする。

    answers: {qid: {"answer": str, "confidence": int(1-4)}}
    戻り値: score(正答数), n, conf_mean, overconfidence(自信過剰の乖離), detail(保存用の明細)
    """
    n = len(FIN_LITERACY)
    correct = 0
    conf_sum = 0
    detail = []

    for item in FIN_LITERACY:
        a = answers.get(item["id"], {})
        ans = a.get("answer")
        conf = a.get("confidence")
        is_correct = 1 if ans == item["correct"] else 0
        correct += is_correct
        conf_sum += conf if conf else 0
        detail.append({
            "qid": item["id"],
            "answer": ans,
            "is_correct": is_correct,
            "confidence": conf,
        })

    conf_mean = conf_sum / n
    accuracy = correct / n
    # 自信度(1-4)を主観正答確率(0-1)に写像し、実際の正答率との差を自信過剰とする
    conf_prob = (conf_mean - 1) / 3
    overconfidence = round(conf_prob - accuracy, 3)

    return {
        "score": correct,
        "n": n,
        "conf_mean": round(conf_mean, 2),
        "overconfidence": overconfidence,
        "detail": detail,
    }
