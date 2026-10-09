# -*- coding: utf-8 -*-
"""対話AIの指示文を変えたときの確認用。ダミーの日報で、種類の違う質問に答えさせる。
使い方: python try_dialogue.py [--g3]   （.env の APIキーを使う。数セント）
"""
import sys

from utils import dialogue, llm

REPORT = {"headline": "S&P500は直近高値から約20%下落、VIXは38に上昇",
          "blocks": [{"text": "今月の米国株は急落しました。S&P500は直近高値から-20.0%まで下げ、VIXは38、Fear & Greedは8まで低下しました。"},
                     {"text": "2018年末の急落（-19.8%）など、過去にも同程度の下落はありましたが、時間をかけて回復してきました。"}]}
MARKET = {"vix": 38.0, "vix_change": 12.0, "fear_greed": {"value": 8, "classification": "Extreme Fear"},
          "drawdown": {"current": -20.0}}
# --g3 を付けると、群3相当（本人の資産・行動を渡す）で試す。付けなければ群2相当
PORTFOLIO = {"cash": 480000, "invested_value": 1325000, "cost_basis": 1560000, "units": 1560000, "nav": 8494}
ACTIONS = [{"label": "16か月目", "phase": "安定上昇", "action": "何もしない"},
           {"label": "17か月目", "phase": "下落", "action": "積立額を増やす"}]
BEHAVIOR = "これまで17か月間、一度も売却していない。毎月の積立を続けている。"
QUESTIONS = ["やばいぞ、とんでもないことに。どうすればいいの？", "今月はなぜ下がったの？",
             "VIXは何の略語ですか", "ただただのんびり", "今月は様子見かな", "少し売ってもいいでしょうか？",
             "投資が怖くて、資金を投入できません・・・", "やったことなくて・・・"]


def main():
    print("model:", llm.model_id("chat"))
    for q in QUESTIONS:
        g3 = "--g3" in sys.argv
        a, _ = dialogue.reply([], q, REPORT, PORTFOLIO if g3 else None, [], unit="month",
                              recent_actions=ACTIONS if g3 else None, market_context=MARKET,
                              behavior_summary=BEHAVIOR if g3 else None)
        print(f"Q: {q}\n（{len(a)}字）\n{a}\n{'-' * 40}")


if __name__ == "__main__":
    main()
