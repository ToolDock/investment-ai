"""本番用のデータ源。investment_ai.db に貯めた実データから文脈を組み立てる。

台本と違い、局面ラベル・ドローダウン・値動きの理由は「観測から決める」。
決められないものは埋めずに空で返し、日報側で触れさせない。

前提となる収集（別プロセス）
    python collect_fred.py         S&P500・VIX・金利（日次終値の長い系列）
    python collect_us_market.py    主要指数・為替・コモディティの直近クオート
    python collect_fng.py          Fear & Greed
    python collect_fmp.py          セクター別騰落
    python collect_news.py         ニュース見出し
"""

import json
import os
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from db import DB_PATH

from .base import (ROOT, Provider, classify_phase, classify_situation,
                   drawdown_from_series, load_rules)

# 実データの銘柄コードを、日報が使う呼び名に直す
INDEX_LABEL = {
    "^GSPC": "S&P500", "^NDX": "NASDAQ", "GC=F": "GOLD",
    "BTC-USD": "BTC", "JPY=X": "ドル円", "^SOX": "SOX", "^NYFANG": "FANG+",
    "CL=F": "OIL",
}
# 日報の「他の資産」に載せる順番。S&P500 は本文の主役なので別扱い
OTHER_ORDER = ["^NDX", "^SOX", "JPY=X", "GC=F", "CL=F", "BTC-USD"]

# 市場と無関係な見出しを落とすための語。単純な部分一致だと
# 「Downing Street」が dow に、「billion-dollar」が dollar に
# 引っかかるなど誤検出が実際に起きたため、語の境界で見る
NEWS_KEYWORDS = [
    "stock", "share", "market", "s&p", "nasdaq", "fed", "inflation",
    "rate", "yield", "earnings", "tariff", "bond", "treasury",
    "recession", "cpi", "jobs", "payroll", "gdp", "index", "投資", "株",
]
_PLURAL_OVERRIDE = {"index": "index(es)?"}


def _keyword_pattern(k):
    if k in _PLURAL_OVERRIDE:
        return _PLURAL_OVERRIDE[k]
    if re.fullmatch(r"[a-zA-Z]+", k):
        return re.escape(k) + "s?"   # rate/rates, share/shares のような複数形も拾う
    return re.escape(k)


_KEYWORD_RE = re.compile(
    r"\b(?:" + "|".join(_keyword_pattern(k) for k in NEWS_KEYWORDS) + r")\b", re.I)
# 「dollar」は "billion-dollar" のような金額表現によく紛れ込むので、
# 数字にハイフンで繋がっている場合は通貨の話として数えない
_DOLLAR_RE = re.compile(r"(?<!-)\bdollar\b", re.I)
# 「dow」は化学メーカー Dow（ティッカー DOW）や "Downing" とも紛れるので、
# 株価指数だと分かる言い回しのときだけ拾う
_DOW_RE = re.compile(r"\bdow\s+(jones|industrial|futures)\b|\bthe\s+dow\b", re.I)
# 戦争・制裁そのものの見出しでも、実際に相場を動かした話（原油・金利など）は
# report_segments.json の news 区分が「必ず触れる」対象にしているので、
# ここでは地政学だからという理由だけでは落とさない。落とすのは
# 「dollar／dow が語の一部に紛れ込んだだけ」の誤検出に絞る


def _is_market_news(headline):
    """市場に関わりそうな見出しか。"""
    return bool(_KEYWORD_RE.search(headline) or _DOLLAR_RE.search(headline)
                or _DOW_RE.search(headline))

# ドローダウンは年初来で測る。「今年の最高値からどれだけ下げたか」が
# いちばん実感に近い。年明け直後だけは足りないので直近1年に切り替える。
MIN_YTD_DAYS = 40
FALLBACK_DAYS = 250

NY = ZoneInfo("America/New_York")
CLOSE_HOUR = 17        # 16時の引けに、データが出そろうまでの1時間を足したもの

# 米国市場が開いていれば必ず値が付き、休場日にも値が付く銘柄。
# 「休場」と「収集できていない」を見分けるために使う。
WITNESS = ["JPY=X", "^VIX"]

# 各データの許容する古さ（日）。これを超えたら「その日の話」として扱わない
FRESH = {"price": 5, "vix": 5, "fear_greed": 5, "sectors": 5, "news": 3, "quote": 2,
         "rates": 3, "fx": 3, "fund": 3}


def just_ended(now=None):
    """いま時点で「終わったばかりの1日」（米国東部時間）。土日かどうかを見るのに使う。"""
    ny = now or datetime.now(NY)
    return ny.date() if ny.hour >= CLOSE_HOUR else ny.date() - timedelta(days=1)


def expected_session(now=None):
    """いま時点で「すでに引けているはずの直近の営業日」を米国東部時間で返す。

    祝日は分からないので、ここでは平日かどうかだけを見る。
    実際に休場だったかは、その日の値が付いているかで判定する（session_status）。
    """
    ny = now or datetime.now(NY)
    d = ny.date()
    if ny.hour < CLOSE_HOUR:
        d -= timedelta(days=1)
    while d.weekday() >= 5:        # 土日
        d -= timedelta(days=1)
    return d


WEEK_JA = "月火水木金土日"


def week_ja(d):
    return WEEK_JA[date.fromisoformat(d).weekday()] if isinstance(d, str) else WEEK_JA[d.weekday()]


def closed_message(status):
    """休場・週末・未収集を、そのまま画面や端末に出せる一文にする。"""
    exp = status.get("expected")
    state = status.get("state")
    if state == "closed":
        return f"{exp}（{week_ja(exp)}）の米国市場は休場でした。"
    if state == "stale":
        return f"{exp}（{week_ja(exp)}）の値がまだ取れていません。"
    if state == "open" and status.get("weekend"):
        return f"週末のため、米国市場は休みです。直近の営業日は {exp}（{week_ja(exp)}）です。"
    return ""


def _age(d, target):
    """target から見て d が何日前か。取れなければ None。"""
    if not d:
        return None
    return (date.fromisoformat(target) - date.fromisoformat(d)).days


class LiveProvider(Provider):
    unit = "day"
    name = "live"

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.rules = load_rules()
        self._series = None

    # ── DB ────────────────────────────────
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_store(self):
        conn = self._conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_report (
                date TEXT PRIMARY KEY,
                seq INTEGER,
                phase TEXT,
                ret REAL,
                headline TEXT,
                blocks TEXT,
                context TEXT,
                model TEXT,
                usage TEXT,
                created_at TEXT
            )
        """)
        # あとから足した列を、既存のDBにも入れる
        cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_report)")}
        for name in ("links",):
            if name not in cols:
                conn.execute(f"ALTER TABLE daily_report ADD COLUMN {name} TEXT")
        conn.commit()
        conn.close()

    # ── S&P500 の日次終値 ───────────────────
    def series(self):
        """[(日付, 終値), ...] を昇順で返す。FRED の系列に直近のクオートを継ぎ足す。"""
        if self._series is not None:
            return self._series
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT date, value FROM fred_data WHERE series='sp500' ORDER BY date"
            ).fetchall()
            out = [(r["date"], r["value"]) for r in rows]
            q = conn.execute(
                "SELECT session, price FROM market_quote WHERE symbol='^GSPC'").fetchone()
            if q and q["price"] and (not out or q["session"] > out[-1][0]):
                out.append((q["session"], q["price"]))
        finally:
            conn.close()
        self._series = out
        return out

    def keys(self):
        """日報を作れる営業日。直近30営業日ぶんだけ出す（遡って作り直す用）。"""
        return [d for d, _ in self.series()[1:]][-30:]

    def latest(self):
        ks = self.keys()
        return ks[-1] if ks else None

    def freshness(self):
        """データがどれだけ古いかを返す。(最終営業日, 何日前) """
        last = self.latest()
        if not last:
            return None, None
        gap = (date.today() - date.fromisoformat(last)).days
        return last, gap

    def session_status(self, now=None):
        """直近の営業日について、開いていたのか・休場だったのか・単に取れていないのか。

        戻り値の state は "open"（値が付いている）／"closed"（休場）／
        "stale"（平日なのに何も取れていない）。
        """
        exp = expected_session(now).isoformat()
        weekend = just_ended(now).weekday() >= 5
        last = self.latest()
        if last and last >= exp:
            return {"state": "open", "expected": exp, "last": last,
                    "weekend": weekend}

        # 「休場」と言えるのは、収集がその日を通り越しているのに株の値が無いとき。
        # まだ収集が追いついていないだけの状態と、はっきり分ける。
        conn = self._conn()
        try:
            witness_last = None
            for sym in WITNESS:
                try:
                    d = conn.execute(
                        "SELECT MAX(date) FROM market_daily WHERE symbol=?",
                        (sym,)).fetchone()[0]
                except sqlite3.OperationalError:
                    d = None
                if d and (witness_last is None or d > witness_last):
                    witness_last = d
        finally:
            conn.close()

        moved_past = bool(witness_last and witness_last > exp)
        state = "closed" if moved_past else "stale"
        return {"state": state, "expected": exp, "last": last,
                "weekend": weekend, "witness_last": witness_last}

    # ── 部品 ──────────────────────────────
    def _at_or_before(self, table, col, target, where=""):
        conn = self._conn()
        try:
            return conn.execute(
                f"SELECT * FROM {table} WHERE date <= ? {where} "
                f"ORDER BY date DESC LIMIT 1", (target,)).fetchone()
        finally:
            conn.close()

    def _sector_date(self, target, tol=1):
        """対象日から前後 tol 日以内でいちばん近いセクターの日付。無ければ None。"""
        conn = self._conn()
        try:
            rows = [r["date"] for r in conn.execute(
                "SELECT DISTINCT date FROM sector_performance").fetchall()]
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
        near = [(abs(_age(d, target)), d) for d in rows if d]
        near = [x for x in near if x[0] <= tol]
        return min(near)[1] if near else None

    def _latest_date(self, table, where, target):
        conn = self._conn()
        try:
            r = conn.execute(
                f"SELECT MAX(date) AS d FROM {table} WHERE date <= ? {where}",
                (target,)).fetchone()
            return r["d"]
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()

    def _vix(self, target):
        rows = self._series_of(target, "^VIX", "vix")
        if not rows:
            return None, None, None
        vix = round(rows[-1][1], 1)
        chg = round(vix - rows[-2][1], 1) if len(rows) > 1 else None
        return vix, chg, rows[-1][0]

    def _fear_greed(self, target):
        r = self._at_or_before("fear_greed", "date", target, "AND type='stock'")
        if r is None:
            return None
        return {"value": int(round(r["value"])), "classification": r["classification"]}

    def _sectors(self, target):
        """対象セッションと揃っている日のものだけ。ずれていたら使わない。

        セクターだけ別の日の数字を混ぜると、本文の「最強・最弱」が
        その日の値動きと食い違う。取れないなら触れさせないほうがよい。
        """
        d = self._sector_date(target)
        conn = self._conn()
        try:
            if not d:
                return []
            rows = conn.execute(
                "SELECT sector, average_change FROM sector_performance WHERE date = ?",
                (d,)).fetchall()
        finally:
            conn.close()
        out = [{"sector": r["sector"], "change_pct": round(r["average_change"], 2)}
               for r in rows]
        out.sort(key=lambda s: s["change_pct"], reverse=True)
        return out

    def _indices(self, target, sp_return):
        """対象日と同じセッションのクオートだけを採る。日付がずれたものは載せない。"""
        conn = self._conn()
        try:
            rows = {r["symbol"]: r for r in conn.execute(
                "SELECT symbol, session, price, prev_close FROM market_quote").fetchall()}
        finally:
            conn.close()
        out = [{"symbol": "S&P500", "change_pct": round(sp_return * 100, 2)}]
        for sym in OTHER_ORDER:
            r = rows.get(sym)
            if not r or not r["prev_close"] or not r["session"]:
                continue
            if _age(r["session"], target) > FRESH["quote"]:
                continue
            pct = (r["price"] / r["prev_close"] - 1) * 100
            out.append({"symbol": INDEX_LABEL[sym], "change_pct": round(pct, 2)})
        return out

    def intraday(self, target, symbol="^GSPC"):
        """target営業日の5分足イントラデイ（Yahoo）。無ければ None。

        ToolDock寄りの「当日の値動き」カードに使う。前日終値は market_daily の
        直近日の close から取る（market_quote は「最新」しか持たないので過去日には使えない）。
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT ts, value FROM market_intraday WHERE symbol=? AND session=? "
                "ORDER BY ts", (symbol, target)).fetchall()
            if not rows:
                return None
            q = conn.execute(
                "SELECT tz_offset FROM market_quote WHERE symbol=?", (symbol,)).fetchone()
            offset = q["tz_offset"] if q and q["tz_offset"] is not None else 0
            prev = conn.execute(
                "SELECT close FROM market_daily WHERE symbol=? AND date < ? "
                "ORDER BY date DESC LIMIT 1", (symbol, target)).fetchone()
        finally:
            conn.close()
        if not prev:
            return None
        return {
            "bars": [{"ts": r["ts"], "value": r["value"]} for r in rows],
            "offset": offset,
            "prev_close": prev["close"],
        }

    # 期間ボタン→さかのぼる日数（暦日）。「年初来」だけは別計算
    _PERIOD_LOOKBACK_DAYS = {"1週間": 7, "1か月": 31, "1年": 365, "5年": 365 * 5}

    def price_series(self, target, symbol, period="1日"):
        """指数・コモディティ用の期間別の値動き。ToolDockの期間切替に合わせた形。

        「1日」は intraday() に委譲（5分足）。それ以外は日足（market_daily）から、
        期間の起点（＝グラフの破線基準線）とその後の値を返す。
        戻り値: {"bars": [...], "ref": 基準値, "kind": "intraday"|"daily",
                "offset": 秒(intradayのみ), "clipped": bool}
        clipped は、収集データがその期間の長さに満たず、実際にはもっと短い区間しか
        描けていないときに True になる（表示側で正直に断ってもらうためのフラグ）。
        """
        if period == "1日":
            d = self.intraday(target, symbol)
            if not d:
                return None
            return {"bars": d["bars"], "ref": d["prev_close"], "kind": "intraday",
                    "offset": d["offset"], "clipped": False}

        if period == "年初来":
            start = f"{target[:4]}-01-01"
        else:
            days = self._PERIOD_LOOKBACK_DAYS.get(period)
            if days is None:
                return None
            start = (date.fromisoformat(target) - timedelta(days=days)).isoformat()

        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT date, close FROM market_daily WHERE symbol=? AND date>=? "
                "AND date<=? ORDER BY date", (symbol, start, target)).fetchall()
        finally:
            conn.close()
        if len(rows) < 2:
            return None
        bars = [{"date": r["date"], "value": r["close"]} for r in rows]
        clipped = period in ("1年", "5年") and bars[0]["date"] > start
        return {"bars": bars, "ref": bars[0]["value"], "kind": "daily",
                "offset": 0, "clipped": clipped}

    _STOCK_UNIVERSE_PATH = os.path.join(ROOT, "knowledge", "sp500_constituents.json")
    _stock_universe_cache = None

    def _stock_universe(self):
        if self._stock_universe_cache is None:
            with open(self._STOCK_UNIVERSE_PATH, encoding="utf-8") as f:
                self._stock_universe_cache = json.load(f)["stocks"]
        return self._stock_universe_cache

    def stock_heatmap(self, target):
        """ヒートマップ用：個別銘柄の前日比・比率・セクターをまとめて返す。

        knowledge/sp500_constituents.json の静的な銘柄リスト（時価総額比率・セクター）に、
        market_daily の直近2営業日分（refresh_stock_universe() が貯めたもの）を突き合わせる。
        データが無い・古い銘柄は黙って落とす（_sectors() と同じ「触れさせないほうがよい」方針）。
        """
        try:
            universe = self._stock_universe()
        except Exception:
            return []
        conn = self._conn()
        try:
            out = []
            for s in universe:
                rows = conn.execute(
                    "SELECT date, close FROM market_daily WHERE symbol=? AND date<=? "
                    "ORDER BY date DESC LIMIT 2", (s["symbol"], target)).fetchall()
                if len(rows) < 2:
                    continue
                if _age(rows[0]["date"], target) > FRESH["quote"]:
                    continue
                change_pct = round((rows[0]["close"] / rows[1]["close"] - 1) * 100, 2)
                out.append({
                    "symbol": s["symbol"], "name": s["name"], "sector": s["sector"],
                    "weight_pct": s["weight_pct"], "change_pct": change_pct,
                    "asof": rows[0]["date"],  # 個別銘柄が実際にいつ時点のデータか（2026-09-26、本人指摘）
                })
        finally:
            conn.close()
        return out

    def _news(self, target, limit=5, pool=20):
        """市場に関わりそうな見出しだけを新しい順に。理由は断定せず材料として渡す。

        headlines はキーワード一致の上位limit件（従来どおり）。candidates は
        LLMでの絞り込み用に広めに持つプール（pool件）。キーワード一致だけでは
        個別銘柄ネタや米国と無関係な他地域市場ニュースも拾ってしまうため、
        呼び出し側（run_live）がcandidatesから選び直せるようにしている
        （2026-09-26、本人指摘）。
        """
        since = (date.fromisoformat(target) - timedelta(days=3)).isoformat()
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT date, headline, source FROM news WHERE date BETWEEN ? AND ? "
                "ORDER BY date DESC", (since, target)).fetchall()
        finally:
            conn.close()
        picked = [r for r in rows if _is_market_news(r["headline"])]
        candidates = [{"text": r["headline"], "source": r["source"]} for r in picked[:pool]]
        headlines = candidates[:limit]
        return {
            "headline": headlines[0]["text"] if headlines else "",
            "cause": "",  # 実データでは理由を作らない。見出しから読める範囲に留める
            "headlines": headlines,
            "candidates": candidates,
        }

    def _series_of(self, target, symbol=None, series=None):
        """[(日付, 値), ...] を昇順で返す。日足（Yahoo）を優先し、無ければ FRED。

        FRED は数日遅れることがあるので、同じ指標なら新しいほうを使う。
        """
        conn = self._conn()
        try:
            rows = []
            if symbol:
                try:
                    rows = [(r["date"], r["close"]) for r in conn.execute(
                        "SELECT date, close FROM market_daily WHERE symbol=? AND date <= ? "
                        "ORDER BY date", (symbol, target)).fetchall()]
                except sqlite3.OperationalError:
                    rows = []
            if not rows and series:
                rows = [(r["date"], r["value"]) for r in conn.execute(
                    "SELECT date, value FROM fred_data WHERE series=? AND date <= ? "
                    "ORDER BY date", (series, target)).fetchall()]
            elif rows and series:
                fred = [(r["date"], r["value"]) for r in conn.execute(
                    "SELECT date, value FROM fred_data WHERE series=? AND date <= ? "
                    "ORDER BY date", (series, target)).fetchall()]
                if fred and fred[-1][0] > rows[-1][0]:
                    rows = fred
        finally:
            conn.close()
        return rows

    def _point(self, target, since=None, symbol=None, series=None):
        """(直近値, 前営業日差, 期間差, 最終日) を返す。取れなければ全て None。"""
        rows = self._series_of(target, symbol, series)
        if len(rows) < 2:
            return None, None, None, None
        now, prev = rows[-1][1], rows[-2][1]
        base = None
        if since:
            seg = [r for r in rows if r[0] >= since]
            if seg:
                base = seg[0][1]
        return now, now - prev, (None if base is None else now - base), rows[-1][0]

    def _rates(self, target, since=None):
        """米10年債利回り。株の割高感の話につながるので水準と変化を持つ。"""
        now, chg, ytd, asof = self._point(target, since, "^TNX", "us_10y_yield")
        if now is None:
            return None
        return {"level": round(now, 2),
                "day_bp": round(chg * 100, 1),
                "ytd_bp": None if ytd is None else round(ytd * 100, 1),
                "asof": asof}

    def _fx(self, target, since=None):
        """ドル円。円建て資産の伸びを左右するので、日次と年初来の両方を持つ。"""
        now, chg, ytd, asof = self._point(target, since, "JPY=X", "usdjpy")
        if now is None:
            return None
        return {
            "asof": asof,
            "level": round(now, 2),
            "day_yen": round(chg, 2),
            "day_pct": round(chg / (now - chg) * 100, 2) if now != chg else None,
            "ytd_yen": None if ytd is None else round(ytd, 2),
            "ytd_pct": (None if ytd is None or now == ytd
                        else round(ytd / (now - ytd) * 100, 2)),
        }

    def relations(self, key):
        """指標どうしの関係の変化のうち、今日報告するもの（図の元データ付き）。無ければ []。

        context() と history() の両方から呼ばれるので、同じ日は一度だけ計算する。
        データが足りない・計算に失敗したときは空にする（日報の生成は止めない）。
        """
        cache = self.__dict__.setdefault("_relations_cache", {})
        if key not in cache:
            try:
                from utils import relations as R
                cache[key] = R.detect(lambda sym, ser: self._series_of(key, sym, ser))
            except Exception as e:
                print(f"  ! 関係の変化の検知に失敗しました（触れずに進めます）: {e}", flush=True)
                cache[key] = []
        return cache[key]

    def _earnings(self, target):
        """法人企業利益（税引後、FRED CP、四半期）。前年同期比だけを持つ。

        『見るべきは企業の稼ぐ力』という話を、実際の数字で裏づけるためのもの。
        四半期でしか動かないので、その日の値動きの理由には使わない。
        """
        rows = self._series_of(target, series="corp_profits")
        if len(rows) < 5:
            return None
        asof, now = rows[-1]
        prev = rows[-5][1]      # 4四半期前＝前年同期
        if not prev:
            return None
        return {"asof": asof, "yoy_pct": round((now / prev - 1) * 100, 1)}

    def _fund(self, target, since=None):
        """円建て投信（eMAXIS Slim 米国株式）の直近。円安・円高の効きが見える。

        下落幅は指数と同じ区間で測る。物差しが違うと本文で比べられない。
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT date, nav FROM fund_nav WHERE nav IS NOT NULL AND date <= ? "
                "ORDER BY date", (target,)).fetchall()
        finally:
            conn.close()
        if len(rows) < 2:
            return None
        navs = [r["nav"] for r in rows]
        if since:
            seg = [r["nav"] for r in rows if r["date"] >= since]
            if len(seg) >= 2:
                navs = seg
        dd, worst = drawdown_from_series(navs)
        return {
            "date": rows[-1]["date"],
            "nav": round(navs[-1], 2),
            "change_pct": round((navs[-1] / navs[-2] - 1) * 100, 2),
            "drawdown": {"current": dd, "max_so_far": worst},
        }

    def _phase_at(self, i, s):
        """sのインデックスiの時点の局面だけを、context()と同じロジックで計算する。

        classify_situation()の材料（直近の局面の並び）を作るための軽量版。
        news/fund/rates等の重い項目は作らない。i<=0（前営業日が無い）ならNone。
        """
        if i <= 0:
            return None
        ret = s[i][1] / s[i - 1][1] - 1
        window, _ = self._window(s, i)
        dd, worst = drawdown_from_series([v for _, v in window])
        n = self.rules["day"]["trend_window"]
        j = max(0, i - n)
        trend = s[i][1] / s[j][1] - 1
        return classify_phase(ret, dd / 100, trend, "day", self.rules)

    # ── 文脈の組み立て ──────────────────────
    def context(self, key):
        s = self.series()
        idx = {d: i for i, (d, _) in enumerate(s)}
        if key not in idx or idx[key] == 0:
            raise KeyError(f"{key} の前営業日がありません")
        i = idx[key]
        ret = s[i][1] / s[i - 1][1] - 1
        gap = _age(s[i - 1][0], key)   # 前営業日との間隔。飛んでいたら日次リターンではない

        window, label = self._window(s, i)
        dd, worst = drawdown_from_series([v for _, v in window])

        n = self.rules["day"]["trend_window"]
        j = max(0, i - n)
        trend = s[i][1] / s[j][1] - 1

        phase = classify_phase(ret, dd / 100, trend, "day", self.rules)
        # 直近n件の局面の並びから、下落系局面をさらに細分する（継続下落／反落。2026-09-23）
        recent_phases = [p for p in
                         (self._phase_at(k, s) for k in range(i - 1, max(-1, i - 1 - n), -1))
                         if p]
        situation = classify_situation(phase, recent_phases)
        since = window[0][0]
        fund = self._fund(key, since)
        rates = self._rates(key, since)
        fx = self._fx(key, since)
        earnings = self._earnings(key)
        from utils import relations as R
        relations = R.strip_chart(self.relations(key))
        vix, vix_chg, vix_date = self._vix(key)
        fg_date = self._latest_date("fear_greed", "AND type='stock'", key)
        sec_date = self._sector_date(key)

        return {
            "month": self.next_seq(),          # 切り口の巡回に使う通し番号
            "date": key,
            "unit": "day",
            "phase": phase,
            "situation": situation,
            "return": ret,
            "trend": trend,
            "market_context": {
                "vix": vix,
                "vix_change": vix_chg,
                "fear_greed": self._fear_greed(key),
                "indices": self._indices(key, ret),
                "sectors": self._sectors(key),
                "drawdown": {"current": dd, "max_so_far": worst},
            },
            "news": self._news(key),
            "fund": fund,
            "rates": rates,
            "fx": fx,
            "earnings": earnings,
            "relations": relations,
            "window": {"start": window[0][0], "days": len(window), "label": label},
            "freshness": {
                "price_gap": gap,
                "vix": _age(vix_date, key),
                "fear_greed": _age(fg_date, key),
                "sectors": None if sec_date is None else abs(_age(sec_date, key)),
                "rates": None if not rates else _age(rates.get("asof"), key),
                "fx": None if not fx else _age(fx.get("asof"), key),
                "fund": None if not fund else _age(fund.get("date"), key),
                "asof": key,
                # 「今日」との間隔ではなく「収集できている最終営業日」との間隔。
                # --force で過去の日付を作り直すときは key が何日も前で当然なので、
                # key 基準にすると毎回「重大」になってしまう（2026-09-11 に発覚）。
                "today_gap": self.freshness()[1],
            },
        }

    def check(self, ctx):
        """生成に回してよいかを見る。('重大'|'注意', 説明) の並びを返す。"""
        f = ctx.get("freshness", {})
        out = []
        if f.get("price_gap") is None or f["price_gap"] > FRESH["price"]:
            out.append(("重大", f"前営業日との間隔が {f.get('price_gap')} 日。"
                                "日次リターンとして扱えない（collect_fred.py を回す）"))
        if f.get("today_gap", 99) > FRESH["price"]:
            out.append(("重大", f"最終営業日が {f['today_gap']} 日前。データが古い"))
        for k, label in (("vix", "VIX"), ("fear_greed", "Fear & Greed"),
                         ("sectors", "セクター別騰落"), ("rates", "米10年債利回り"),
                         ("fx", "ドル円"), ("fund", "円建て基準価額")):
            age = f.get(k)
            if age is None:
                out.append(("注意", f"{label} が対象セッションぶん取れていない"
                                    "（本文では触れさせない）"))
            elif age > FRESH[k]:
                out.append(("注意", f"{label} が {age} 日ずれた値"))
        if not ctx.get("news", {}).get("headlines"):
            out.append(("注意", "対象日に近い市場ニュースが1件もない"))
        if ctx["market_context"]["vix"] is None:
            out.append(("重大", "VIX がない"))
        return out

    @staticmethod
    def _window(s, i):
        """ドローダウンを測る区間を返す。既定は年初来。"""
        year = s[i][0][:4]
        start = next((j for j, (d, _) in enumerate(s) if d[:4] == year), i)
        if i - start + 1 >= MIN_YTD_DAYS:
            return s[start:i + 1], f"今年（{year}年）"
        return s[max(0, i - FALLBACK_DAYS + 1): i + 1], "直近1年"

    # ── 図のための推移 ──────────────────────
    def timeline(self, key, days=None):
        """図（v_index_path / v_drawdown / v_fear_greed）に渡す推移。

        実験の台本と同じ形にしてあるので、描画側は実験と本番で共通のまま使える。
        month は日付ではなく 1 からの通し番号（横軸は「経過営業日数」と表示する）。
        区間は本文が使うドローダウンの窓と同じにする（図と文章を食い違わせない）。
        """
        s = self.series()
        idx = {d: i for i, (d, _) in enumerate(s)}
        if key not in idx:
            return []
        end = idx[key]
        if days:
            start = max(1, end - days + 1)
        else:
            win, _ = self._window(s, end)
            start = max(1, end - len(win) + 1)
        seg = s[start - 1: end + 1]           # 1本前から取り、初日のリターンを出す

        conn = self._conn()
        try:
            fg_rows = conn.execute(
                "SELECT date, value FROM fear_greed WHERE type='stock' ORDER BY date"
            ).fetchall()
        finally:
            conn.close()
        fg = {r["date"]: int(round(r["value"])) for r in fg_rows}

        peak = seg[0][1]
        last_fg = None
        out = []
        last_n = len(seg) - 1
        for n, (d, v) in enumerate(seg[1:], 1):
            prev = seg[n - 1][1]
            peak = max(peak, v)
            last_fg = fg.get(d, last_fg)
            mc = {
                "drawdown": {"current": round((v / peak - 1) * 100, 1)},
                "fear_greed": {"value": last_fg if last_fg is not None else 50},
            }
            # セクターは対象日（最後のエントリ）ぶんだけ載せる。v_sector_performance は
            # 「今日の内訳」を描くだけなので、過去の日ぶんまで毎回問い合わせる必要はない
            if n == last_n:
                sec = self._sectors(d)
                if sec:
                    mc["sectors"] = sec
            out.append({
                "month": n,
                "date": d,
                "return": v / prev - 1,
                "market_context": mc,
            })
        return out

    def ytd_drawdown_years(self, target, years=2):
        """target時点を含む年と、その前の年ぶんの『年初来ドローダウン』を年ごとに計算する。

        年が変わるたびに基準（その年の最高値）をリセットして測るので、年をまたいだ
        下落局面の深さ・長さを一目で比べられる。直近年（targetを含む年）はtargetまでで
        打ち切り、それより前の年はその年の全データを使う（前年の年間の姿全体を見せるため）。
        2026-09-18、本人の依頼で追加（tooldock版のいいとこどり）。
        """
        target_year = int(target[:4])
        out = {}
        conn = self._conn()
        try:
            for y in range(target_year - years + 1, target_year + 1):
                end = f"{y}-12-31" if y < target_year else target
                rows = conn.execute(
                    "SELECT date, close FROM market_daily WHERE symbol='^GSPC' "
                    "AND date >= ? AND date <= ? ORDER BY date",
                    (f"{y}-01-01", end)).fetchall()
                if not rows:
                    continue
                peak = float("-inf")
                series = []
                for r in rows:
                    peak = max(peak, r["close"])
                    dd = round((r["close"] / peak - 1) * 100, 2)
                    series.append({"date": r["date"], "dd": dd})
                out[str(y)] = series
        finally:
            conn.close()
        return out

    # ── 注記のための直近の並び ────────────────
    def _daily(self, table, where, params, col, target, days):
        conn = self._conn()
        try:
            rows = conn.execute(
                f"SELECT {col} AS v FROM {table} WHERE date <= ? {where} "
                f"ORDER BY date DESC LIMIT ?", (target, *params, days)).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        return [r["v"] for r in reversed(rows)]

    def history(self, key, days=20):
        """チャート注記が使う直近の並び。取れないものは入れない（埋めない）。"""
        out = {}
        # 本文の _fx()/_rates()/_vix() と同じソース優先順位（Yahoo優先、無ければFRED）に揃える。
        # fred_data 単独だと数日〜1週間遅れ、チャートの「今」が本文の数字と食い違っていた（2026-09-26）。
        for name, symbol, series in (("vix", "^VIX", "vix"),
                                     ("rates", "^TNX", "us_10y_yield"),
                                     ("fx", "JPY=X", "usdjpy")):
            v = [val for _, val in self._series_of(key, symbol, series)[-days:]]
            if v:
                out[name] = v
        v = self._daily("fear_greed", "AND type='stock'", (), "value", key, days)
        if v:
            out["fear_greed"] = v
        for name, sym in (("index", "^GSPC"), ("gold", "GC=F"),
                          ("btc", "BTC-USD"), ("semis", "^SOX")):
            v = self._daily("market_daily", "AND symbol=?", (sym,), "close", key, days)
            if v:
                out[name] = v
        # 関係が変わった二つの指標の推移（図 v_relation 用）。無い日は入れない
        rel = self.relations(key)
        if rel:
            r = rel[0]
            out["relation"] = dict(r["chart"], label=r["label"], kind_ja=r["kind_ja"],
                                   n_recent=r["n_recent"])
        s = self.series()
        idx = {d: i for i, (d, _) in enumerate(s)}
        # 指数の日足がまだ無いときは、FRED の終値で代用する
        if "index" not in out and key in idx:
            out["index"] = [v for _, v in s[max(0, idx[key] - days + 1): idx[key] + 1]]
        # ドローダウンは価格から作る（本文と同じ窓で測る）
        if key in idx:
            window, _ = self._window(s, idx[key])
            peak, dds = float("-inf"), []
            for _, v in window:
                peak = max(peak, v)
                dds.append((v / peak - 1) * 100)
            out["drawdown"] = dds[-days:]
        return out

    # ── 保存 ──────────────────────────────
    def next_seq(self):
        conn = self._conn()
        try:
            r = conn.execute("SELECT MAX(seq) AS s FROM daily_report").fetchone()
            return (r["s"] or 0) + 1
        except sqlite3.OperationalError:
            return 1
        finally:
            conn.close()

    def previous(self, key=None):
        """直前に出した日報。書き出しと図の重複を避けるために生成側が読む。"""
        conn = self._conn()
        try:
            r = conn.execute(
                "SELECT * FROM daily_report WHERE date < ? ORDER BY date DESC LIMIT 1",
                (key or "9999-12-31",)).fetchone()
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
        if r is None:
            return None
        return {
            "month": r["seq"], "date": r["date"], "phase": r["phase"],
            "daily_report": {"blocks": json.loads(r["blocks"] or "[]"),
                             "headline": r["headline"]},
        }

    def exists(self, key):
        conn = self._conn()
        try:
            return conn.execute(
                "SELECT 1 FROM daily_report WHERE date = ?", (key,)).fetchone() is not None
        except sqlite3.OperationalError:
            return False
        finally:
            conn.close()

    def save_report(self, key, blocks, headline="", ctx=None, model="", usage=None,
                    links=None):
        self.init_store()
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO daily_report
            (date, seq, phase, ret, headline, blocks, context, model, usage,
             created_at, links)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            key,
            (ctx or {}).get("month"),
            (ctx or {}).get("phase"),
            (ctx or {}).get("return"),
            headline,
            json.dumps(blocks, ensure_ascii=False),
            json.dumps(ctx or {}, ensure_ascii=False),
            model,
            json.dumps(usage or {}, ensure_ascii=False),
            datetime.now().isoformat(timespec="seconds"),
            json.dumps(links or [], ensure_ascii=False),
        ))
        conn.commit()
        conn.close()

    def flush(self):
        pass
