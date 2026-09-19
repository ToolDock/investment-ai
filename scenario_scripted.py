import json
from collections import Counter

SCRIPT = [
    {"phase":"安定上昇","reference":"2019年前半の穏やかな上昇","returns":[0.015,0.012,0.018]},
    {"phase":"暴落","reference":"2018年12月ミニクラッシュ","returns":[-0.09]},
    {"phase":"急回復","reference":"ミニクラッシュ後のリバウンド","returns":[0.06,0.04]},
    {"phase":"停滞","reference":"2015-2016年の横ばい相場","returns":[0.005,-0.005,0.008,-0.003,0.004]},
    {"phase":"安定上昇","reference":"2023-2024年AI相場","returns":[0.03,0.025,0.02,0.035,0.018,0.028]},
    {"phase":"暴落","reference":"コロナショック（2020年3月型）","returns":[-0.20]},
    {"phase":"暴落","reference":"コロナショック継続","returns":[-0.08]},
    {"phase":"急回復","reference":"コロナ後の急回復","returns":[0.10,0.08,0.06]},
    {"phase":"安定下落","reference":"2022年インフレ相場","returns":[-0.03,-0.025,-0.02,-0.04,-0.015,-0.03,-0.02,-0.01]},
    {"phase":"停滞","reference":"底打ち確認期","returns":[0.01,-0.008,0.005,0.002]},
    {"phase":"安定上昇","reference":"回復相場","returns":[0.025,0.02,0.03,0.015,0.022,0.018]},
    {"phase":"暴落","reference":"地政学ショック型","returns":[-0.11]},
    {"phase":"急回復","reference":"地政学ショック後の回復","returns":[0.05,0.03]},
    {"phase":"安定上昇","reference":"終盤の安定成長","returns":[0.018,0.02,0.015,0.022,0.017,0.019,0.021,0.016]},
    {"phase":"停滞","reference":"終盤の小休止","returns":[0.005,-0.002,0.008,0.003,0.006]},
    {"phase":"暴騰","reference":"終盤のミニバブル","returns":[0.09,0.05,0.03,0.02]}
]

QUESTIONNAIRE = [
    {"id":"anxiety","text":"現在、不安を感じていますか？","type":"likert5"},
    {"id":"sell_impulse","text":"売却したい気持ちはありますか？","type":"likert5"},
    {"id":"continue_invest","text":"積立を継続したいと思いますか？","type":"likert5"}
]

def build_scenario():
    month = 0
    timeline = []

    for block in SCRIPT:
        for r in block["returns"]:
            month += 1
            timeline.append({
                "month": month,
                "return": r,
                "phase": block["phase"],
                "reference": block["reference"],
                "news": {
                    "headline": "",
                    "body": ""
                },
                "sns": [],
                "daily_report": {
                    "group1": "",
                    "group2": ""
                }
            })

    turns = []
    i = 0

    while i < len(timeline):
        t = timeline[i]
        event = t["phase"] in ["暴落","暴騰","急回復"]

        turns.append({
            "month": t["month"],
            "is_event": event,
            "questionnaire": {
                "enabled": event,
                "items": QUESTIONNAIRE
            },
            "decision": {
                "sell": True,
                "pause": True,
                "resume": True
            }
        })

        i += 1 if event else 3

    scenario = {
        "type":"scripted",
        "settings":{
            "initial_cash":500000,
            "monthly_invest":50000,
            "total_months":len(timeline)
        },
        "timeline":timeline,
        "turns":turns,
        "phase_counts":dict(Counter(t["phase"] for t in timeline))
    }

    return scenario

if __name__ == "__main__":
    scenario = build_scenario()

    print(f"総月数: {len(scenario['timeline'])}")
    print(f"ターン数: {len(scenario['turns'])}")
    print(f"局面内訳: {scenario['phase_counts']}")

    with open("scenario_scripted.json","w",encoding="utf-8") as f:
        json.dump(scenario,f,ensure_ascii=False,indent=2)

    print("scenario_scripted.json に保存しました")