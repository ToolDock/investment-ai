"""scenario_scripted.json の各月に market_context を生成・統合する。

scenario_scripted.py（リターン台本の生成）とは分離した後工程。
台本を変更したら本スクリプトを再実行して market_context を更新する。
"""

import json

from utils.market_context import generate_market_context, load_calibration

SCENARIO_PATH = "scenario_scripted.json"


def main():
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        scenario = json.load(f)

    timeline = scenario["timeline"]
    cal = load_calibration()
    contexts = generate_market_context(timeline, cal)

    for month_data, ctx in zip(timeline, contexts):
        month_data["market_context"] = ctx

    scenario["market_calibration_ref"] = cal["meta"]["provenance"]

    with open(SCENARIO_PATH, "w", encoding="utf-8") as f:
        json.dump(scenario, f, ensure_ascii=False, indent=2)

    print(f"market_context を {len(contexts)} 月分に統合しました → {SCENARIO_PATH}")


if __name__ == "__main__":
    main()
