import json

def load_scenario():
    with open("scenario_scripted.json", encoding="utf-8") as f:
        return json.load(f)

def get_turn(turn):
    scenario = load_scenario()
    timeline = scenario["timeline"]
    turns = scenario["turns"]

    info = turns[turn]

    month = info["month"]

    data = timeline[month - 1].copy()

    data.update(info)

    return data