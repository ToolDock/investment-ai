"""実験用のデータ源。scenario_scripted.json の台本をそのまま文脈として返す。

台本には market_context も news も作り込んであるので、ここは読み出すだけ。
生成済みの日報も一緒に返す（前回の書き出しと図を避けるために生成側が使う）。
"""

import json
import os

from .base import Provider

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PATH = os.path.join(ROOT, "scenario_scripted.json")


class ScriptedProvider(Provider):
    unit = "month"
    name = "scripted"

    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        with open(path, encoding="utf-8") as f:
            self.scenario = json.load(f)
        self.timeline = self.scenario["timeline"]
        self._by_month = {m["month"]: m for m in self.timeline}

    def keys(self):
        return [m["month"] for m in self.timeline]

    def context(self, key):
        # 台本ファイルに余計なキーを書き戻さないよう、浅い写しに単位を足して返す
        m = dict(self._by_month[key])
        m["unit"] = "month"
        return m

    def previous(self, key):
        return self._by_month.get(key - 1)

    # ── 保存（台本ファイルを書き戻す）────────────
    def save_report(self, key, blocks, headline="", usage=None):
        m = self._by_month[key]
        rep = m.setdefault("daily_report", {"group1": "", "group2": ""})
        rep["blocks"] = blocks
        rep["headline"] = headline
        rep["group2"] = "\n\n".join(b["text"] for b in blocks)

    def flush(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.scenario, f, ensure_ascii=False, indent=2)
