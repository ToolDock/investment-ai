# -*- coding: utf-8 -*-
"""対話AIの指示文を変えたときの確認用。ダミーの日報で、種類の違う質問に答えさせる。
使い方: python try_dialogue.py   （.env の APIキーを使う。数セント）
"""
from utils import dialogue, llm

REPORT = {"headline": "S&P500は直近高値から約20%下落、VIXは38に上昇",
          "blocks": [{"text": "今月の米国株は急落しました。S&P500は直近高値から-20.0%まで下げ、VIXは38、Fear & Greedは8まで低下しました。"},
                     {"text": "2018年末の急落（-19.8%）など、過去にも同程度の下落はありましたが、時間をかけて回復してきました。"}]}
MARKET = {"vix": 38.0, "vix_change": 12.0, "fear_greed": {"value": 8, "classification": "Extreme Fear"},
          "drawdown": {"current": -20.0}}
QUESTIONS = ["やばいぞ、とんでもないことに。どうすればいいの？", "今月はなぜ下がったの？",
             "VIXは何の略語ですか", "ただただのんびり", "少し売ってもいいでしょうか？"]


def main():
    print("model:", llm.model_id("chat"))
    for q in QUESTIONS:
        a, _ = dialogue.reply([], q, REPORT, None, [], unit="month", market_context=MARKET)
        print(f"Q: {q}\n（{len(a)}字）\n{a}\n{'-' * 40}")


if __name__ == "__main__":
    main()
