"""日報の入力を作る層。実験（台本）と本番（実データ）をここで切り替える。"""

from .base import (Provider, classify_phase, drawdown_from_series, validate,
                   select_segments, load_segments, PHASES)
from .scripted import ScriptedProvider
from .live import LiveProvider, closed_message, expected_session, week_ja


def get_provider(name="scripted", **kw):
    if name == "live":
        return LiveProvider(**kw)
    return ScriptedProvider(**kw)
