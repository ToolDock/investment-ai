"""事後アンケートの設問定義。

操作チェック（介入が届いたか）と主観評価を分けて持つ。
群1は日報を持たないので、日報に関する設問は出さない。
"""

LIKERT5 = [
    "まったくそう思わない",
    "あまりそう思わない",
    "どちらともいえない",
    "ややそう思う",
    "とてもそう思う",
]

# 全群共通
COMMON = [
    {"id": "ref_read", "text": "「長期投資の参考書」に目を通しましたか"},
    {"id": "ref_useful", "text": "参考書の内容は、行動を決めるときの助けになりましたか"},
    {"id": "media_attention", "text": "市場ニュースやSNSの反応は、気になりましたか"},
]

# 群2・群3のみ。層ごとに何が届いたかを切り分ける
REPORT = [
    {"id": "rep_read", "text": "AI日報を読みましたか", "layer": "受容"},
    {"id": "rep_self", "text": "AI日報は、あなた自身の資産の状況に触れていたと思いますか", "layer": "層2"},
    {"id": "rep_history", "text": "AI日報は、あなたのこれまでの行動に触れていたと思いますか", "layer": "層3"},
    {"id": "rep_clear", "text": "AI日報の説明は、あなたにとって分かりやすかったですか", "layer": "層4"},
    {"id": "rep_useful", "text": "AI日報は、行動を決めるときの助けになりましたか", "layer": "評価"},
    {"id": "rep_trust", "text": "AI日報の内容は信頼できると感じましたか", "layer": "評価"},
    {"id": "rep_again", "text": "実際の投資でも、こうした日報があれば使いたいと思いますか", "layer": "評価"},
]

# 群2・群3のみ。対話AI（質問機能）について。日報の設問と同じ層で切り分ける
DIALOGUE = [
    {"id": "dlg_asked", "text": "対話AIに、自分から積極的に質問しましたか", "layer": "受容"},
    {"id": "dlg_self", "text": "対話AIの答えは、あなた自身の資産の状況に触れていたと思いますか", "layer": "層2"},
    {"id": "dlg_history", "text": "対話AIの答えは、あなたのこれまでの行動に触れていたと思いますか", "layer": "層3"},
    {"id": "dlg_clear", "text": "対話AIの説明は、あなたにとって分かりやすかったですか", "layer": "層4"},
    {"id": "dlg_useful", "text": "対話AIは、行動を決めるときの助けになりましたか", "layer": "評価"},
    {"id": "dlg_trust", "text": "対話AIの答えは信頼できると感じましたか", "layer": "評価"},
    {"id": "dlg_again", "text": "実際の投資でも、こうした対話AIがあれば使いたいと思いますか", "layer": "評価"},
]

# 注意チェック（クラウドソーシングでの不真面目回答をはじく）
ATTENTION = {
    "id": "attention_check",
    "text": "この設問は回答の確認用です。「あまりそう思わない」を選んでください",
    "correct": 2,  # LIKERT5 の1始まりの位置
}

# 記憶の確認。自己申告の「真剣に取り組んだか」は全員が最高評価を選ぶので使わない。
# 実際に見ていなければ答えられない設問で、関与の程度を外側から測る。
RECALL_COMMON = [
    {"id": "sns_recall",
     "text": "シミュレーション中のSNSで、何度も見かけたハンドル名はどれですか",
     "options": ["のんびり投資家", "かぶきち2000", "インデックス番長", "覚えていない"],
     "correct": 1},
]

RECALL_REPORT = [
    {"id": "rep_recall_open",
     "text": "AI日報は、毎回どのような書き出しでしたか",
     "options": ["「こんにちは、◯◯さん。」という呼びかけから始まった",
                 "「本日の市況」という見出しから始まった",
                 "数字の一覧表から始まった",
                 "覚えていない"],
     "correct": 1},
    {"id": "rep_recall_close",
     "text": "AI日報は、毎回同じ言葉で締めくくられていました。それはどれですか",
     "options": ["相場は相場に任せて、今月も Just Keep Buying。",
                 "明日はきっと良い日になります。",
                 "無理のない範囲で続けていきましょう。",
                 "覚えていない"],
     "correct": 1},
]


def recall_for(group):
    return list(RECALL_COMMON) + (list(RECALL_REPORT) if group != 1 else [])


def screen(group, answers):
    """回答から除外判定と操作チェックを計算する。

    除外基準は全群で同一の設問だけを使う。群によって基準の厳しさが変わると、
    除外率が群間で偏り、生き残った標本が比較できなくなるため。

    - 注意チェック（全群共通・指示応答型）: 外したら一発除外
    - SNS常連の記憶（全群共通）: 外したら除外
    - 日報の記憶2問（群2・群3のみ）: 除外には使わない。介入がどれだけ届いたかの指標とし、
      per-protocol 分析の切り分けに使う（3問中1問までの不正解を許容）
    """
    att = answers.get(ATTENTION["id"])
    attention_pass = (att == ATTENTION["correct"])

    common = RECALL_COMMON[0]
    common_pass = (answers.get(common["id"]) == common["correct"])

    report_correct = sum(
        1 for it in RECALL_REPORT if answers.get(it["id"]) == it["correct"]
    ) if group != 1 else None

    # 3問（共通1＋日報2）のうち1問までの不正解を許容
    engaged = None
    if group != 1:
        engaged = (int(common_pass) + report_correct) >= 2

    return {
        "attention_pass": attention_pass,
        "recall_common_pass": common_pass,
        "report_recall_correct": report_correct,
        "excluded": not (attention_pass and common_pass),
        "engaged_with_report": engaged,
    }


FREE = [
    {"id": "reason_free",
     "text": "相場が大きく下がったとき、売る・売らないをどのように決めましたか（任意）"},
    {"id": "comment_free",
     "text": "気づいたことや感想があれば、自由にお書きください（任意）"},
]


def items_for(group):
    """その群で出す5件法の設問を、表示順に返す。"""
    items = list(COMMON)
    if group != 1:
        items += REPORT + DIALOGUE
    items.append(ATTENTION)
    return items
