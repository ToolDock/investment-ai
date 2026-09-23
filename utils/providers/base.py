"""日報の入力となる「文脈」の型と、共通の道具。

実験（台本）と本番（実データ）で、生成側が受け取る辞書の形を揃える。
生成側はこの形しか知らないので、データ源を差し替えても日報の作り方は変わらない。

必須キー
    month           通し番号（切り口の巡回と前回参照に使う）
    phase           局面ラベル
    return          その期間のリターン（小数）
    market_context  vix / vix_change / fear_greed / indices / sectors / drawdown
    news            headline / cause（本番は headlines も入る）

任意キー
    date            本番のみ。対象営業日
    unit            "month" | "day"。文中の「今月／今日」を切り替える
    window          ドローダウンを測った期間（本番のみ）
    fund            円建て投信の状況（本番のみ）
    situation       下落系の局面をさらに細分するラベル（2026-09-23追加）。
                    「継続下落」「反落」のいずれか、該当なしは None。
                    classify_situation() 参照。金言選定をより状況に合わせるための
                    追加の軸で、必須キーではない（無くても既存の動作を維持する）。
"""

import json
import os

PHASES = ["暴落", "急回復", "安定下落", "暴騰", "停滞", "安定上昇"]

# 下落系の局面をさらに細分するための分類（金言選定を状況に合わせるため、2026-09-23）。
DOWN_PHASES = {"暴落", "安定下落"}
UP_PHASES = {"暴騰", "安定上昇"}

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(ROOT, "knowledge", "phase_rules.json")
SEGMENTS_PATH = os.path.join(ROOT, "knowledge", "report_segments.json")

REQUIRED = ("month", "phase", "return", "market_context", "news")
MC_REQUIRED = ("vix", "fear_greed", "indices", "sectors", "drawdown")


def load_rules():
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_segments():
    with open(SEGMENTS_PATH, encoding="utf-8") as f:
        return json.load(f)["segments"]


def _index_pct(ctx, symbol):
    for i in ctx["market_context"].get("indices") or []:
        if i["symbol"] == symbol:
            return i["change_pct"]
    return None


def _fires(seg, ctx):
    """その日にこの話題を載せるかどうか。数値が取れていなければ載せない。"""
    t = seg.get("trigger") or {}
    sid = seg["id"]
    mc = ctx["market_context"]

    if sid == "sector":
        sec = mc.get("sectors") or []
        return len(sec) >= 2 and (sec[0]["change_pct"] - sec[-1]["change_pct"]) >= t["spread_min"]

    if sid == "fx":
        fx = ctx.get("fx")
        if not fx:
            return False
        gap = None
        fund = ctx.get("fund")
        if fund:
            gap = abs(fund["drawdown"]["current"] - mc["drawdown"]["current"])
        return (abs(fx.get("day_pct") or 0) >= t["day_abs_min"]
                or abs(fx.get("ytd_pct") or 0) >= t["ytd_abs_min"]
                or (gap is not None and gap >= t["gap_min"]))

    if sid == "rates":
        r = ctx.get("rates")
        return bool(r) and abs(r.get("day_bp") or 0) >= t["day_bp_abs_min"]

    if sid in ("commodity", "crypto", "semis"):
        sym = {"commodity": "GOLD", "crypto": "BTC", "semis": "SOX"}[sid]
        v = _index_pct(ctx, sym)
        return v is not None and abs(v) >= t["day_abs_min"]

    if sid == "news":
        news = ctx.get("news") or {}
        return bool(news.get("headlines") or news.get("headline"))

    if sid == "sentiment":
        vix = mc.get("vix")
        fg = (mc.get("fear_greed") or {}).get("value")
        if vix is not None and (vix >= t["vix_min"] or vix <= t["vix_max"]):
            return True
        return fg is not None and (fg >= t["fg_min"] or fg <= t["fg_max"])

    return False


def select_segments(ctx, segments=None):
    """その日に載せる話題を順番どおりに返す。always と、実際に動いたものだけ。"""
    return [s for s in (segments or load_segments())
            if s.get("always") or _fires(s, ctx)]


def classify_phase(ret, dd_current, trend, unit="month", rules=None):
    """リターン・現在のドローダウン・直近の傾きから局面を決める。

    ret / dd_current / trend はいずれも小数（-0.05 = -5%）。
    """
    cfg = (rules or load_rules())[unit]
    for r in cfg["rules"]:
        if "ret_max" in r and ret > r["ret_max"]:
            continue
        if "ret_min" in r and ret < r["ret_min"]:
            continue
        if "dd_max" in r and dd_current > r["dd_max"]:
            continue
        if "trend_abs_max" in r and abs(trend) > r["trend_abs_max"]:
            continue
        return r["phase"]
    return "安定上昇"


def classify_situation(phase, recent_phases):
    """下落系の局面（暴落・安定下落）を、直近の局面推移からさらに細分する。

    「ずっと下がり続けている場面」と「高騰の直後に一休みしている下落」とでは、
    投資家にかけるべき言葉（信じて耐える／浮かれず淡々と）が違う、という指摘
    （2026-09-23）を受けて追加。実験・本番どちらも、この関数と直近の局面ラベルの
    並びだけで判定できるようにしてある（本番専用フィールドのcause/referenceには
    依存しない）。

    recent_phases: 直前から古い順に並べた局面ラベルのリスト（取れた分だけでよい。
    空リスト・Noneも許容する）。

    戻り値: "継続下落"／"反落"／None（下落系でない、または判定材料が無い）。
    """
    if phase not in DOWN_PHASES:
        return None
    if recent_phases and recent_phases[0] in UP_PHASES:
        return "反落"
    if recent_phases and all(p not in UP_PHASES for p in recent_phases):
        return "継続下落"
    return None


def drawdown_from_series(values):
    """終値の並びから (現在のドローダウン%, 期間中の最大下落幅%) を返す。"""
    peak = float("-inf")
    worst = 0.0
    dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = (v / peak - 1) * 100
        worst = min(worst, dd)
    return round(dd, 1), round(worst, 1)


def validate(ctx):
    """生成に回す前に、欠けている項目を洗い出す。空リストなら問題なし。"""
    problems = []
    for k in REQUIRED:
        if k not in ctx or ctx[k] is None:
            problems.append(f"{k} がない")
    mc = ctx.get("market_context") or {}
    for k in MC_REQUIRED:
        if k not in mc or mc[k] is None:
            problems.append(f"market_context.{k} がない")
    if ctx.get("phase") and ctx["phase"] not in PHASES:
        problems.append(f"phase が不正: {ctx['phase']}")
    if not (mc.get("indices") or []):
        problems.append("market_context.indices が空")
    return problems


class Provider:
    """データ源の共通の顔。生成側はこの3つしか呼ばない。"""

    unit = "month"
    name = "base"

    def keys(self):
        """生成しうる対象の並び（古い順）。"""
        raise NotImplementedError

    def context(self, key):
        """1件ぶんの文脈を返す。"""
        raise NotImplementedError

    def previous(self, key):
        """直前の文脈。書き出しと図の重複を避けるために使う。なければ None。"""
        ks = self.keys()
        if key in ks:
            i = ks.index(key)
            if i > 0:
                return self.context(ks[i - 1])
        return None
