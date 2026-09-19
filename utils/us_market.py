"""米国市場ダッシュボードの表示用データを investment_ai.db から組み立てる。

収集は collect_us_market.py が担当。ここは DB を読んで、
タイル・チャート・メーターがそのまま使える形に整えるだけの層。
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone

# collect_us_market と同じ定義を使う（循環importを避けるためこちらでは再定義しない）
from collect_us_market import FUND_CD, FUND_NAME, SYMBOLS  # noqa: E402
from db import DB_PATH  # noqa: E402

ROW1 = ["^GSPC", "^NDX", "^NYFANG", "JPY=X"]
ROW2 = ["GC=F", "^TNX", "BTC-USD", "^SOX"]


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── 指数・為替・金利・コモディティ ─────────────────────────────
def load_tile(symbol, conn=None):
    """1銘柄ぶんの数値と日中チャート。データがなければ None。"""
    own = conn is None
    conn = conn or _conn()
    try:
        quote = conn.execute("SELECT * FROM market_quote WHERE symbol = ?", (symbol,)).fetchone()
        if quote is None:
            return None
        points = conn.execute(
            "SELECT ts, value FROM market_intraday WHERE symbol = ? AND session = ? ORDER BY ts",
            (symbol, quote["session"])).fetchall()
    finally:
        if own:
            conn.close()

    meta = SYMBOLS.get(symbol, {})
    offset = quote["tz_offset"] or 0
    price = quote["price"]
    prev = quote["prev_close"]

    # 前日比。金利だけは % ではなく bp（0.01%）で見るのが慣習。
    change = None if (price is None or prev is None) else price - prev
    change_pct = None if (change is None or not prev) else change / prev * 100
    change_bp = None if change is None else change * 100

    return {
        "symbol": symbol,
        "label": meta.get("label", symbol),
        "digits": meta.get("digits", 2),
        "unit": meta.get("unit", ""),
        "change_mode": meta.get("change", "pct"),
        "session": quote["session"],
        "price": price,
        "prev_close": prev,
        "change": change,
        "change_pct": change_pct,
        "change_bp": change_bp,
        "times": [datetime.fromtimestamp(r["ts"] + offset, timezone.utc).replace(tzinfo=None)
                  for r in points],
        "values": [r["value"] for r in points],
    }


def load_tiles(symbols):
    conn = _conn()
    try:
        return [t for t in (load_tile(s, conn) for s in symbols) if t]
    finally:
        conn.close()


def format_price(tile):
    digits = tile["digits"]
    unit = tile["unit"]
    text = f"{tile['price']:,.{digits}f}"
    if unit == "$":
        return f"${text}"
    return f"{text}{unit}"


def format_change(tile):
    """(前日比の文字列, 上げ下げ符号) を返す。符号は色分けに使う。"""
    if tile["change"] is None:
        return "—", 0
    sign = 1 if tile["change"] > 0 else (-1 if tile["change"] < 0 else 0)
    if tile["change_mode"] == "bp":
        return f"{tile['change_bp']:+.1f}bp（{tile['change_pct']:+.2f}%）", sign
    digits = tile["digits"]
    return f"{tile['change']:+,.{digits}f}（{tile['change_pct']:+.2f}%）", sign


# ── eMAXIS Slim 米国株式（S&P500）の基準価額 ──────────────────
def load_nav_series(fund_cd=FUND_CD, start=None):
    """[(date, nav), ...] を日付昇順で返す。"""
    conn = _conn()
    try:
        sql = "SELECT date, nav, change_pct FROM fund_nav WHERE fund_cd = ? AND nav IS NOT NULL"
        args = [fund_cd]
        if start:
            sql += " AND date >= ?"
            args.append(start.isoformat() if hasattr(start, "isoformat") else start)
        sql += " ORDER BY date"
        return [(date.fromisoformat(r["date"]), r["nav"], r["change_pct"])
                for r in conn.execute(sql, args)]
    finally:
        conn.close()


def year_slice(series, year):
    return [row for row in series if row[0].year == year]


def ytd_stats(series, year):
    """年初来の騰落・前日比・直近値をまとめる。"""
    rows = year_slice(series, year)
    if not rows:
        return None
    first_date, first_nav, _ = rows[0]
    last_date, last_nav, last_chg = rows[-1]
    prev_nav = rows[-2][1] if len(rows) >= 2 else None
    peak = max(r[1] for r in rows)
    return {
        "year": year,
        "start_date": first_date,
        "start_nav": first_nav,
        "date": last_date,
        "nav": last_nav,
        "prev_nav": prev_nav,
        "change": None if prev_nav is None else last_nav - prev_nav,
        "change_pct": last_chg,
        "ytd_pct": (last_nav / first_nav - 1) * 100,
        "peak": peak,
        "from_peak_pct": (last_nav / peak - 1) * 100,
    }


def drawdown_series(series, year):
    """年初来ドローダウン。その年の最初の営業日を起点に、
    それまでの最高値からの下落率（%、0以下）を日ごとに返す。"""
    rows = year_slice(series, year)
    if not rows:
        return []
    out = []
    peak = rows[0][1]
    for day, nav, _ in rows:
        peak = max(peak, nav)
        out.append((day, (nav / peak - 1) * 100))
    return out


def max_drawdown(dd):
    if not dd:
        return None, None
    day, value = min(dd, key=lambda r: r[1])
    return value, day


def day_of_year(d):
    """今年・去年を重ねて比較するための横軸（1/1からの経過日数）。"""
    return (d - date(d.year, 1, 1)).days + 1


# ── Fear & Greed / VIX ──────────────────────────────────────
FG_BANDS = [
    (0, 25, "Extreme Fear", "極度の恐怖", "#c62828"),
    (25, 45, "Fear", "恐怖", "#ef9a9a"),
    (45, 55, "Neutral", "中立", "#fbc02d"),
    (55, 75, "Greed", "強欲", "#9ccc65"),
    (75, 100, "Extreme Greed", "極度の強欲", "#2e7d32"),
]

VIX_BANDS = [
    (0, 15, "落ち着き", "#2e7d32"),
    (15, 20, "やや不安", "#9ccc65"),
    (20, 30, "警戒", "#fbc02d"),
    (30, 50, "極度の警戒", "#c62828"),
]


def fg_band(value):
    for low, high, label_en, label_ja, color in FG_BANDS:
        if low <= value <= high:
            return label_en, label_ja, color
    return FG_BANDS[-1][2], FG_BANDS[-1][3], FG_BANDS[-1][4]


def vix_band(value):
    for low, high, label, color in VIX_BANDS:
        if low <= value < high:
            return label, color
    return VIX_BANDS[-1][2], VIX_BANDS[-1][3]


def load_fear_greed():
    """最新のFear & Greedと、1週間前・1ヶ月前の値。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT date, value, classification FROM fear_greed WHERE type = 'stock' "
            "ORDER BY date DESC LIMIT 40").fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    latest = rows[0]
    by_date = {date.fromisoformat(r["date"]): r["value"] for r in rows}
    today = date.fromisoformat(latest["date"])

    def nearest(target):
        candidates = [d for d in by_date if d <= target]
        return by_date[max(candidates)] if candidates else None

    value = latest["value"]
    label_en, label_ja, color = fg_band(value)
    return {
        "date": today,
        "value": value,
        "label_en": label_en,
        "label_ja": label_ja,
        "color": color,
        "prev": rows[1]["value"] if len(rows) > 1 else None,
        "week_ago": nearest(today - timedelta(days=7)),
        "month_ago": nearest(today - timedelta(days=30)),
    }


def load_vix():
    tile = load_tile("^VIX")
    if not tile or tile["price"] is None:
        return None
    label, color = vix_band(tile["price"])
    tile["band_label"] = label
    tile["band_color"] = color
    return tile


def last_updated():
    conn = _conn()
    try:
        row = conn.execute("SELECT MAX(fetched_at) AS t FROM market_quote").fetchone()
    finally:
        conn.close()
    if not row or not row["t"]:
        return None
    return datetime.fromisoformat(row["t"]).astimezone()
