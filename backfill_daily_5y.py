"""market_daily の日足を5年分でバックフィルする、一度だけ使うスクリプト。

refresh_daily() は毎朝の収集ではデフォルトで直近2年分しか取ってこない
（それで十分だし、5年分を毎日取り直す必要はない）。ここでだけ rng="5y" で
全シンボルを取り直し、古い分を market_daily に積み増す。INSERT OR REPLACE
なので、既存の直近2年分の行は上書きされるだけで消えない。一度実行すれば、
以後は毎朝の収集（2年分）がその上に積み増していくだけでよい。

使い方（PowerShellから一度だけ）:
    venv\\Scripts\\python.exe backfill_daily_5y.py
"""

import time

from collect_us_market import SYMBOLS, refresh_daily


def main():
    print("5年分の日足をバックフィルします（Yahoo Financeの提供範囲内で、"
          "銘柄によってはそれより短くなります）")
    for symbol, meta in SYMBOLS.items():
        try:
            count, last = refresh_daily(symbol, rng="5y")
            print(f"  {symbol:9s}（{meta['label']}） {count}件 〜{last}")
        except Exception as e:
            print(f"  {symbol:9s} 失敗: {e}")
        time.sleep(0.8)
    print("完了。以後の毎朝の収集は従来どおり2年分のままで問題ありません"
          "（過去分は消えないので、そのまま積み上がります）。")


if __name__ == "__main__":
    main()
