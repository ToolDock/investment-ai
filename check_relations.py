"""指標どうしの関係の変化（utils/relations.py）の現在地と、過去の発火頻度を確認する。

    python check_relations.py          # 現在の全ての組の状態と、直近250営業日の発火回数
    python check_relations.py 500      # 遡る営業日数を指定

発火頻度が高すぎる（ほぼ毎日出る）ようなら、knowledge/relations.json の
しきい値（min_delta / min_z）を上げる。偶然発火する日がゼロにはならない点に注意。
"""

import sys

from utils import relations as R
from utils.providers import LiveProvider


def main():
    span = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 250
    prov = LiveProvider()
    key = prov.latest()
    if not key:
        print("価格データがありません")
        return
    cfg = R.load()
    th = cfg["thresholds"]
    guides = cfg["meta"].get("guide_by_kind")
    print(f"対象日: {key}   しきい値: 相関の差>={th['min_delta']} / z>={th['min_z']} / 相関の絶対値>={th['min_abs']}")
    print()
    for pair in cfg["pairs"]:
        a = prov._series_of(key, pair["a"]["symbol"], pair["a"].get("series"))
        b = prov._series_of(key, pair["b"]["symbol"], pair["b"].get("series"))
        if not a or not b:
            print(f"■ {pair['label']}: データなし（収集を回してください）")
            continue
        rows = R._align(a, b)
        now = R.analyze(pair, rows, th, guides)
        if not now:
            print(f"■ {pair['label']}: 日数が足りない（{len(rows)}日）")
            continue
        print(f"■ {pair['label']}（{now['asof']}）")
        print(f"   直近{now['n_recent']}日: 相関{now['corr_recent']:+.2f}（{now['word_recent']}、"
              f"同じ向きの日 {now['same_recent']}/{now['n_recent']}）"
              f"／ その前{now['n_base']}日: 相関{now['corr_base']:+.2f}（{now['word_base']}）")
        print(f"   z={now['z']:+.2f}  判定: {now['kind_ja'] if now['fired'] else '発火なし'}"
              f"   {now['a']['name']} {now['a']['move_text']} / {now['b']['name']} {now['b']['move_text']}")
        need = th["window_recent"] + th["window_base"] + 1
        hits, fired_days, run = [], 0, 0
        rep = th.get("repeat_days", 15)
        for t in range(max(need, len(rows) - span), len(rows) + 1):
            r = R.analyze(pair, rows[:t], th, guides)
            run = run + 1 if (r and r["fired"]) else 0
            fired_days += 1 if run else 0
            if run and (run == 1 or run % rep == 0):
                hits.append((r["asof"], r["kind_ja"]))
        n = min(span, len(rows) - need + 1)
        print(f"   過去{n}営業日: 条件を満たした日 {fired_days}日／日報で取り上げる日 {len(hits)}日"
              + (f"（{', '.join(h[0] for h in hits[-5:])}{' ほか' if len(hits) > 5 else ''}）" if hits else ""))
        print()


if __name__ == "__main__":
    main()
