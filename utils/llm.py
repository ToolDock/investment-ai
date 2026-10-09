"""LLM 呼び出しの共通入口。

Anthropic 直接契約と OpenRouter を LLM_BACKEND で切り替える。
system は「全参加者で共通の部分」と「可変部分」に分けて渡す。
共通部分にキャッシュ指定を打つので、必ず共通部分を先に置くこと。
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()

BACKEND = os.getenv("LLM_BACKEND", "anthropic")

MODEL_IDS = {
    "openrouter": {"chat": "anthropic/claude-sonnet-5",
                   "batch": "anthropic/claude-sonnet-5:batch"},
    "anthropic": {"chat": "claude-sonnet-5-5",
                  "batch": "claude-sonnet-5-5"},
}

# 別名が使えない場合に備えて、実IDを直接指定できるようにしておく
MODEL_OVERRIDE = os.getenv("LLM_MODEL")

# 単価（USD / 100万トークン）。実費の概算に使う
PRICE = {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.2}

MAX_RETRY = 3
RETRY_WAIT = 4      # 秒。指数バックオフの基準
TIMEOUT = 120.0     # 秒。1回の呼び出しの上限

# 拡張思考は既定で切る。思考トークンが max_tokens を食って本文が途中で切れるため。
# 必要なときだけ LLM_THINKING=1 で戻す。
THINKING = os.getenv("LLM_THINKING", "0") == "1"

_no_thinking_param = False   # API がこの引数を受け付けなかったときに立てる
_thinking_off = {"type": "disabled"}   # 思考を切る指定。モデルによって形が違う

_client = None
_resolved = {}


def model_id(kind="chat"):
    if MODEL_OVERRIDE:
        return MODEL_OVERRIDE
    return _resolved.get(kind) or MODEL_IDS[BACKEND][kind]


def get_key(name):
    # 公開時は Streamlit の secrets、手元では .env から読む
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


# ── 利用量 ────────────────────────────────
def zero_usage():
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
            "cost_usd": 0.0, "calls": 0}


def estimate_cost(u):
    return (u["input"] * PRICE["input"]
            + u["output"] * PRICE["output"]
            + u["cache_write"] * PRICE["cache_write"]
            + u["cache_read"] * PRICE["cache_read"]) / 1_000_000


def add_usage(total, u):
    for k in ("input", "output", "cache_write", "cache_read", "cost_usd", "calls"):
        total[k] += u.get(k, 0)
    return total


def format_usage(u):
    return (f"calls={u['calls']} in={u['input']} out={u['output']} "
            f"cache_w={u['cache_write']} cache_r={u['cache_read']} "
            f"cost=${u['cost_usd']:.4f}")


# ── クライアント ───────────────────────────
def anthropic_client():
    """使い回す。SDK 側の再送は切って、再送はこのモジュールに一本化する。"""
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic(api_key=get_key("ANTHROPIC_API_KEY"),
                            max_retries=0, timeout=TIMEOUT)
    return _client


def list_models():
    """契約で使えるモデルの一覧。移行時の確認用。"""
    if BACKEND != "anthropic":
        return []
    return [m.id for m in anthropic_client().models.list(limit=100).data]


def resolve_model(kind="chat"):
    """設定したモデル名が通らないとき、一覧から最も新しい該当版を選ぶ。"""
    if BACKEND != "anthropic" or MODEL_OVERRIDE:
        return model_id(kind)
    want = MODEL_IDS["anthropic"][kind]
    try:
        ids = list_models()
    except Exception:
        return want
    if want in ids:
        return want
    stem = want.replace("claude-", "").replace("-", "")   # sonnet5
    hits = sorted([i for i in ids if i.replace("-", "").startswith("claude" + stem)],
                  reverse=True)
    if hits:
        _resolved[kind] = hits[0]
        return hits[0]
    return want


# ── 再送の判定 ────────────────────────────
def _retryable(e):
    code = getattr(e, "status_code", None)
    if code is None:
        code = getattr(getattr(e, "response", None), "status_code", None)
    if code is None:
        return True                       # 接続断など。ひとまず再送する
    return code == 429 or code >= 500     # 認証・入力の誤りは再送しない


# ── 本体 ──────────────────────────────────
def chat(system_common, system_variable, messages, max_tokens=600, kind="chat"):
    """(本文, 利用量dict) を返す。429・一時障害は指数バックオフで再送する。"""
    last = None
    for attempt in range(MAX_RETRY):
        try:
            if BACKEND == "anthropic":
                return _call_anthropic(system_common, system_variable,
                                       messages, max_tokens, kind)
            return _call_openrouter(system_common, system_variable,
                                    messages, max_tokens, kind)
        except Exception as e:
            last = e
            if attempt == MAX_RETRY - 1 or not _retryable(e):
                break
            time.sleep(RETRY_WAIT * (2 ** attempt))
    raise last


def _system_blocks(system_common, system_variable):
    # 共通部分にだけキャッシュ指定を打つ
    blocks = [{"type": "text", "text": system_common,
               "cache_control": {"type": "ephemeral"}}]
    if system_variable:
        blocks.append({"type": "text", "text": system_variable})
    return blocks


def _call_anthropic(system_common, system_variable, messages, max_tokens, kind):
    global _no_thinking_param, _thinking_off
    kw = dict(
        model=model_id(kind),
        max_tokens=max_tokens,
        system=_system_blocks(system_common, system_variable),
        messages=messages,
    )
    if not THINKING and not _no_thinking_param:
        kw["thinking"] = dict(_thinking_off)
    r = None
    for _ in range(3):
        try:
            r = anthropic_client().messages.create(**kw)
            break
        except TypeError:
            _no_thinking_param = True
            kw.pop("thinking", None)
        except Exception as e:
            msg = str(e)
            if "thinking" not in kw or "thinking" not in msg:
                raise
            # モデルによって、思考を切る指定の形が違う。エラーが示す形があれば、それで一度やり直す
            if "between_tools" in msg and kw["thinking"].get("type") != "between_tools":
                _thinking_off = {"type": "between_tools"}
                kw["thinking"] = dict(_thinking_off)
            else:
                _no_thinking_param = True
                kw.pop("thinking", None)
                print(f"  ! thinking引数が受け付けられなかったため外します: {msg[:200]}", flush=True)
    if r is None:
        raise RuntimeError("応答を取得できませんでした")
    text = "".join(b.text for b in r.content if getattr(b, "type", None) == "text")
    u = {
        "input": getattr(r.usage, "input_tokens", 0) or 0,
        "output": getattr(r.usage, "output_tokens", 0) or 0,
        "cache_write": getattr(r.usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(r.usage, "cache_read_input_tokens", 0) or 0,
        "calls": 1,
    }
    u["cost_usd"] = estimate_cost(u)
    if getattr(r, "stop_reason", None) == "max_tokens":
        print("  ! 応答が max_tokens で打ち切られました", flush=True)
    _warn_hidden_tokens(u, text)
    if u["output"] > len(text) * 2 + 200:
        print(f"    blocks={[getattr(blk, 'type', '?') for blk in r.content]}", flush=True)
    if not text.strip():
        kinds = [getattr(blk, "type", "?") for blk in r.content]
        print(f"  ! 本文が空です: stop_reason={getattr(r, 'stop_reason', None)} "
              f"blocks={kinds} output={u['output']}", flush=True)
    return text, u


def _warn_hidden_tokens(u, text):
    """本文の長さに比べて出力トークンが多すぎる＝思考トークンが混ざっている兆候。

    これを見逃すと、max_tokens を上げても本文だけが切れ続ける。
    """
    n = len(text or "")
    if u["output"] > n * 2 + 200:
        print(f"  ! 出力{u['output']}トークンに対し本文は{n}字しかありません。"
              "思考トークンが混ざっている可能性があります", flush=True)
        print(f"    thinking引数を外している={_no_thinking_param}", flush=True)


def _call_openrouter(system_common, system_variable, messages, max_tokens, kind):
    from openai import OpenAI

    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=get_key("OPENROUTER_API_KEY"))
    r = client.chat.completions.create(
        model=model_id(kind),
        max_tokens=max_tokens,
        messages=[{"role": "system",
                   "content": _system_blocks(system_common, system_variable)}] + messages,
        extra_body={
            # 経路を固定して再現性を確保する
            "provider": {"order": ["Anthropic"], "allow_fallbacks": False},
            "usage": {"include": True},
            # 推論トークンが max_tokens を食って本文が切れるので止める
            "reasoning": {"enabled": False},
        },
    )
    text = r.choices[0].message.content or ""
    usage = r.usage
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    u = {
        "input": max(prompt - cached, 0),
        "output": getattr(usage, "completion_tokens", 0) or 0,
        "cache_write": 0,
        "cache_read": cached,
        "calls": 1,
    }
    # OpenRouter は実費を返すので、取れたらそちらを優先する
    cost = getattr(usage, "cost", None)
    u["cost_usd"] = float(cost) if cost is not None else estimate_cost(u)
    return text, u
