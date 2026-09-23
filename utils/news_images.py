# -*- coding: utf-8 -*-
# 【2026-09-23付けで廃止】pick_news_image()はもうどこからも呼ばれていない
# (utils/components/daily_report.pyから呼び出しを削除済み)。理由は設計doc
# 「画像廃止とニュース見出し5本方式への統一_2026-09.md」参照。本番で実際の記事
# 画像を再現できず訴求力に欠けるとの指摘から、ニュースは画像ではなく見出し5本
# (utils/components/news.pyのshow_news())で伝える方式に一本化した。このファイル
# 自体は記録として残しているが、削除しても実害はない。
import hashlib
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "news_images"

# 「大きな下落・上昇」の基準は局面(phase)そのものを使う。暴落・暴騰はclassify_phase()が
# 実験(月次)・本番(日次)どちらでも同じ規則(knowledge/phase_rules.json)で出す値なので、
# 画像を出すかどうかの判定ロジックを実験・本番で1本にできる
# (実験でできることは本番でもできる、という方針に合わせた設計)。
CATEGORY_BY_PHASE = {"暴落": "crash", "暴騰": "surge"}

# 「原因が特定できるニュース」には、それを写した画像を優先して出す(§25-11)。
# 暴落・暴騰かどうかに関係なく、見出し(headline)にキーワードが出てきたら該当テーマの
# フォルダを使う。reference(台本の物語ラベル、実験専用)は見出しより精度が高いが、
# 「急回復」局面(暴落・暴騰の直後、原因はもう和らいでいる場面)まで拾うと、収まった
# 危機の画像が回復局面に居座ってしまうので、その局面だけは対象から外す。
# 見出し側は実験・本番どちらの daily_report["headline"] にも同じ形で入っているので、
# reference が無い本番でもこの判定だけはそのまま使える
# (実験でできることは本番でもできる、という方針に合わせた設計)。
THEME_KEYWORDS = {
    "infection": {"reference": ["コロナ"], "headline": ["感染症"]},
    "energy": {"reference": ["地政学"], "headline": ["地政学"]},
    "tech": {"reference": [], "headline": ["テクノロジー主導"]},
    "policy": {"reference": ["インフレ相場"], "headline": ["規制"]},
}
THEME_ORDER = ("infection", "energy", "tech", "policy")


def _detect_theme(reference, headline, phase):
    """その月・その日のニュースがどのテーマ画像に当たるかを判定する。
    reference(台本のみ)は「急回復」局面を除いた上で使い、headline(実験・本番共通)は
    局面を問わず使う。優先順位はTHEME_ORDERの順(同時に複数該当することは無い想定)。"""
    ref = reference or ""
    hl = headline or ""
    for theme in THEME_ORDER:
        kw = THEME_KEYWORDS[theme]
        if phase != "急回復" and any(k in ref for k in kw["reference"]):
            return theme
        if any(k in hl for k in kw["headline"]):
            return theme
    return None


def _list_images(folder):
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in (".svg", ".jpg", ".jpeg", ".png", ".webp")
    )


def _phase_occurrence(timeline, month, phase):
    """台本(月次)では、これまでの月で同じ局面が何回目かを数える。文言ローテーション
    (personalization.py の occurrence ベースの考え方)と同じ発想。"""
    if not timeline or not month:
        return 0
    return max(0, sum(1 for m in timeline[:month] if (m or {}).get("phase") == phase) - 1)


def _theme_occurrence(timeline, month, theme):
    """台本(月次)では、これまでの月で同じテーマが何回目かを数える。_phase_occurrence()の
    テーマ版。theme の判定に使う reference/headline/phase は timeline の各月から作れるので、
    追加の引数なしにここだけで再計算できる。"""
    if not timeline or not month:
        return 0
    count = 0
    for m in timeline[:month]:
        m = m or {}
        ref = m.get("reference")
        hl = (m.get("daily_report") or {}).get("headline", "")
        if _detect_theme(ref, hl, m.get("phase")) == theme:
            count += 1
    return max(0, count - 1)


def _date_variant(date_str, n):
    """本番(日次)は月のような通し番号を持たないため、日付から決定的に選ぶ。"""
    if not date_str or n <= 0:
        return 0
    h = hashlib.sha1(date_str.encode("utf-8")).hexdigest()
    return int(h, 16) % n


def pick_news_image(phase, *, timeline=None, month=None, date=None, unit="month", headline=None):
    """その月・その日のニュースに合う画像を1枚返す。無ければNone。

    まずheadline(与えられていればtimeline[month-1]から補う)とreference(実験のみ)から
    テーマ(infection/energy/tech/policy)を判定し、当てはまればそのフォルダから選ぶ
    (原因が分かるニュースには、その原因を写した画像を出す方が伝わる、という方針。
    §25-11)。テーマが無ければ、従来通り局面(暴落・暴騰)だけでcrash/surgeフォルダから選ぶ。

    選び方は unit で決める。unit="month"(実験)はtimeline上でこれまで同じテーマ/局面が
    何回目かを数えてローテーションし、unit="day"(本番)はtimelineに通し番号はあっても
    「月」の意味を持たない(単なる直近営業日の連番)ため、日付のハッシュ値で決定的に選ぶ
    (本番のtimelineにはreference/daily_reportが無いため、テーマのローテーション数え上げは
    そもそも意味を成さない)。

    画像はPixabay/Pexelsの無料ライセンス(商用利用可・帰属表示不要。詳細は
    assets/news_images/README.md)の素材だけを想定している。ニュース記事そのものの
    画像(著作権のある報道写真)は使わない(§25-7の判断を踏襲)。
    """
    ref = None
    if timeline and month:
        ref = (timeline[month - 1] or {}).get("reference")
        if headline is None:
            headline = ((timeline[month - 1] or {}).get("daily_report") or {}).get("headline")

    theme = _detect_theme(ref, headline, phase)
    category = theme or CATEGORY_BY_PHASE.get(phase)
    if not category:
        return None

    files = _list_images(ASSET_ROOT / category)
    if not files:
        return None

    if unit == "day":
        idx = _date_variant(date, len(files))
    elif theme:
        idx = _theme_occurrence(timeline, month, theme) % len(files)
    else:
        idx = _phase_occurrence(timeline, month, phase) % len(files)
    return str(files[idx])
