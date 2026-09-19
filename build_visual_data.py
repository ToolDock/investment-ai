"""過去データの視覚アセットを実データから計算し knowledge/historical_visuals.json に保存する。

データ源:
- Shiller 長期データ（data/shiller_ie_data.xls, 月次S&P・CPI, 1871-）→ 実質価格・弱気相場・高値掴み・超長期対数
- FRED（S&P500 日次, 直近約10年）→ ベストな数日を逃す影響

生成物は参考書・日報の視覚アセット。統計は実データ由来だが、表示時に出典・期間・注記を添える。
"""

import os
import json
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

SHILLER_XLS = "data/shiller_ie_data.xls"
OUT_PATH = "knowledge/historical_visuals.json"

BEAR_NAMES = {"1906.09": "1907年恐慌", "1909.12": "第一次大戦前後の長期低迷",
              "1929.09": "世界恐慌", "1973.01": "オイルショック",
              "2000.08": "ITバブル崩壊", "2007.10": "世界金融危機（リーマンショック）"}
# 名目・配当なしのため回復期間が実感と乖離する行。日報で単独引用させない
NOT_ALONE = {"1929.09", "1909.12"}

# 直近の下落局面の呼び名。空欄は日付だけで表示されるので、必要なら手で埋める
RECENT_NAMES = {"2018-01": "2018年2月の急落", "2018-09": "2018年末の急落",
                "2020-02": "コロナショック", "2022-01": "2022年の下落局面",
                "2025-02": "2025年の関税ショック"}
TRADING_DAYS_PER_MONTH = 21


def load_shiller():
    df = pd.read_excel(SHILLER_XLS, sheet_name="Data", header=7)
    df = df.rename(columns={df.columns[0]: "Date", df.columns[1]: "P", df.columns[2]: "D",
                            df.columns[4]: "CPI", df.columns[5]: "Frac"})
    d = df[["P", "D", "CPI", "Frac"]].copy()
    d = d[pd.to_numeric(d["Frac"], errors="coerce").notna()
          & pd.to_numeric(d["P"], errors="coerce").notna()].reset_index(drop=True)
    for c in ["P", "CPI", "Frac"]:
        d[c] = d[c].astype(float)
    d["D"] = pd.to_numeric(d["D"], errors="coerce").fillna(0.0)
    d["year"] = np.floor(d["Frac"]).astype(int)
    d["month"] = np.rint((d["Frac"] - d["year"]) * 12 + 0.5).astype(int)
    d["real"] = d["P"] * d["CPI"].iloc[-1] / d["CPI"]
    return d


def bear_markets(d, min_decline=-0.30, since_year=1900):
    P, yr, mo = d["P"].values, d["year"].values, d["month"].values
    eps = []
    peak = P[0]; peak_i = 0; in_bear = False; trough = P[0]; trough_i = 0
    for i in range(1, len(P)):
        if P[i] >= peak and not in_bear:
            peak, peak_i = P[i], i
        if not in_bear and (P[i] - peak) / peak <= -0.20:
            in_bear, trough, trough_i = True, P[i], i
        if in_bear:
            if P[i] < trough:
                trough, trough_i = P[i], i
            if P[i] >= peak:
                eps.append((peak_i, trough_i, i)); in_bear = False; peak, peak_i = P[i], i
    if in_bear:
        eps.append((peak_i, trough_i, None))

    rows = []
    for pk, tr, rc in eps:
        decline = (P[tr] - P[pk]) / P[pk]
        if decline > min_decline or yr[tr] < since_year:
            continue
        rec = (int((yr[rc] - yr[tr]) * 12 + (mo[rc] - mo[tr]))) if rc is not None else None
        peak_key = f"{yr[pk]}.{mo[pk]:02d}"
        rows.append({
            "name": BEAR_NAMES.get(peak_key, ""),
            "cite_alone": peak_key not in NOT_ALONE,
            "peak": peak_key,
            "trough": f"{yr[tr]}.{mo[tr]:02d}",
            "decline_pct": round(decline * 100, 1),
            "decline_months": int((yr[tr] - yr[pk]) * 12 + (mo[tr] - mo[pk])),
            "recovery_months": rec,
        })
    rows.sort(key=lambda r: r["peak"])
    return rows


def longterm_log(d):
    # 年1点（各年最初の月）に間引いた実質価格
    ann = d.groupby("year", as_index=False).first()
    return [{"year": int(r["year"]), "real": round(float(r["real"]), 1)}
            for _, r in ann.iterrows()]


def all_time_high(d, start_year=1950, horizons=(12, 36, 60)):
    # 名目価格で「最高値」を判定し、配当込み(トータルリターン)の将来リターンを比較。
    # 戦後(現代)を対象にするのは、超長期(戦前含む)だと恐慌の影響が過大になるため。
    P = d["P"].values
    D = d["D"].values
    tr = np.ones(len(P))
    for i in range(1, len(P)):
        tr[i] = tr[i - 1] * (P[i] + D[i - 1] / 12) / P[i - 1]
    run_max = np.maximum.accumulate(P)
    is_ath = P >= run_max * 0.999
    yr = d["year"].values

    rows = []
    for h in horizons:
        fa, fath = [], []
        for i in range(len(tr) - h):
            if yr[i] < start_year:
                continue
            r = tr[i + h] / tr[i] - 1
            fa.append(r)
            if is_ath[i]:
                fath.append(r)
        fa, fath = np.array(fa), np.array(fath)
        rows.append({
            "horizon_years": h // 12,
            "ath_avg": round(float(fath.mean()) * 100, 1),
            "all_avg": round(float(fa.mean()) * 100, 1),
            "ath_positive": round(float((fath > 0).mean()) * 100),
            "all_positive": round(float((fa > 0).mean()) * 100),
        })
    return {"start_year": int(start_year), "basis": "配当込み(トータルリターン)", "horizons": rows}


def missing_best_days():
    key = os.getenv("FRED_API_KEY")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": "SP500", "api_key": key,
                             "file_type": "json", "observation_start": "2014-01-01"},
                     timeout=30)
    obs = [(o["date"], float(o["value"])) for o in r.json()["observations"] if o["value"] != "."]
    prices = np.array([v for _, v in obs])
    rets = prices[1:] / prices[:-1] - 1
    start, end = obs[0][0], obs[-1][0]

    def cum(excluded=0):
        rr = rets.copy()
        if excluded:
            idx = np.argsort(rr)[-excluded:]
            rr[idx] = 0.0
        return float(np.prod(1 + rr) - 1)

    return {
        "period": f"{start} 〜 {end}",
        "items": [
            {"label": "ずっと保有", "value": round(cum(0) * 100, 1)},
            {"label": "上昇最良10日を逃す", "value": round(cum(10) * 100, 1)},
            {"label": "上昇最良20日を逃す", "value": round(cum(20) * 100, 1)},
            {"label": "上昇最良30日を逃す", "value": round(cum(30) * 100, 1)},
        ],
    }


def recent_drawdowns(min_decline=-0.10, max_points=120):
    """FRED 日次から直近約10年の下落局面を抽出する。

    実験の下落幅（20〜26%）と期間（60か月）に見合う比較対象を作るのが目的。
    月次・-30%以上の弱気相場一覧では、規模も時間軸も離れすぎている。
    """
    key = os.getenv("FRED_API_KEY")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": "SP500", "api_key": key,
                             "file_type": "json", "observation_start": "2014-01-01"},
                     timeout=30)
    obs = [(o["date"], float(o["value"])) for o in r.json()["observations"] if o["value"] != "."]
    dates = [d for d, _ in obs]
    P = np.array([v for _, v in obs])

    eps = []
    peak = P[0]; peak_i = 0; in_dd = False; trough = P[0]; trough_i = 0
    for i in range(1, len(P)):
        if P[i] >= peak and not in_dd:
            peak, peak_i = P[i], i
        if not in_dd and (P[i] - peak) / peak <= min_decline:
            in_dd, trough, trough_i = True, P[i], i
        if in_dd:
            if P[i] < trough:
                trough, trough_i = P[i], i
            if P[i] >= peak:
                eps.append((peak_i, trough_i, i)); in_dd = False; peak, peak_i = P[i], i
    if in_dd:
        eps.append((peak_i, trough_i, None))

    rows = []
    for pk, tr, rc in eps:
        decline = (P[tr] - P[pk]) / P[pk]
        end = rc if rc is not None else len(P) - 1
        seg = P[pk:end + 1]
        dd = (seg / np.maximum.accumulate(seg) - 1) * 100
        step = max(1, len(dd) // max_points)
        path = [{"m": round(j / TRADING_DAYS_PER_MONTH, 2), "dd": round(float(dd[j]), 2)}
                for j in range(0, len(dd), step)]
        ym = dates[pk][:7]
        rows.append({
            "name": RECENT_NAMES.get(ym, f"{ym[:4]}年{int(ym[5:])}月からの下落"),
            "peak": dates[pk], "trough": dates[tr],
            "decline_pct": round(decline * 100, 1),
            "decline_months": round((tr - pk) / TRADING_DAYS_PER_MONTH, 1),
            "recovery_months": (round((rc - tr) / TRADING_DAYS_PER_MONTH, 1)
                                if rc is not None else None),
            "path": path,
        })
    rows.sort(key=lambda r: r["peak"])
    return {"period": f"{dates[0]} 〜 {dates[-1]}", "episodes": rows}


def main():
    d = load_shiller()
    span = f"{d['year'].iloc[0]}.{d['month'].iloc[0]:02d}〜{d['year'].iloc[-1]}.{d['month'].iloc[-1]:02d}"

    out = {
        "meta": {
            "sources": {
                "shiller": "Robert J. Shiller, Online Data（月次S&P Composite・CPI, 1871-）",
                "fred": "FRED SP500（日次, 直近約10年）",
            },
            "shiller_span": span,
            "caveats": [
                "弱気相場は月次終値・名目価格ベース。日中や配当込みの数値とは差が出る（例：2020年の急落は月次では-20%に届かず本表に載らない）。",
                "実質価格・高値掴み分析は配当を含まない（価格リターンのみ）。配当込みなら数値はさらに良くなる。",
            ],
        },
        "v_bear_markets": {
            "type": "table",
            "title": "過去の主要な弱気相場と、その後の回復（実データ）",
            "columns": ["ピーク", "大底", "下落率", "下落期間(月)", "回復まで(月)"],
            "rows": bear_markets(d),
            "note": "大きな下落も、時間差はあれ回復してきた（Shiller長期データ, 月次終値・名目）。",
        },
        "v_longterm_log": {
            "type": "chart_log",
            "title": "S&P500の超長期・実質価格（対数スケール）",
            "series": longterm_log(d),
            "note": "対数で見ると、暴落や停滞は長期の右肩上がりの一部（Shiller長期データ, 実質・配当除く）。",
        },
        "v_alltime_high": {
            "type": "bars",
            "title": "「最高値」で買っても、その後のリターンは『いつでも買う』とほぼ同じ",
            "data": all_time_high(d, start_year=1950),
            "note": "最高値で投資した場合と、いつでも投資した場合の、その後の平均リターン（1950年以降・配当込み）。ほぼ同水準で、近年（1988年以降）ではむしろ最高値のほうがやや上回る。最高値は売る理由にならない。",
        },
        "v_recent_drawdowns": {
            "type": "table",
            "title": "直近10年の下落局面と、回復までの期間",
            "columns": ["局面", "ピーク", "下落率", "回復まで(月)"],
            "data": recent_drawdowns(),
            "note": "この規模の下落は数か月で回復してきた（FRED日次・配当を含まない価格ベース）。",
        },
        "v_missing_best_days": {
            "type": "bars",
            "title": "上昇の『最良の数日』を逃すと、リターンは大きく削られる",
            "data": missing_best_days(),
            "note": "恐怖で市場から降りると、回復時の最良の日を取り逃しやすい（FRED日次）。",
        },
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("saved ->", OUT_PATH)
    print("bear markets:", len(out["v_bear_markets"]["rows"]), "rows")
    print("longterm points:", len(out["v_longterm_log"]["series"]))
    print("ATH:", out["v_alltime_high"]["data"])
    print("recent drawdowns:", out["v_recent_drawdowns"]["data"]["period"])
    for e in out["v_recent_drawdowns"]["data"]["episodes"]:
        print(f"   {e['name']:<18} {e['peak']} {e['decline_pct']:>6}%  "
              f"下落{e['decline_months']}か月  回復{e['recovery_months']}か月")
    print("best days period:", out["v_missing_best_days"]["data"]["period"])
    for it in out["v_missing_best_days"]["data"]["items"]:
        print("  ", it["label"], it["value"], "%")


if __name__ == "__main__":
    main()
