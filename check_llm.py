"""API の疎通・モデル・残高を確認する。

    python check_llm.py            設定とモデル一覧
    python check_llm.py --call     実際に1回だけ生成して実費を表示
"""

import sys

import requests

from utils.llm import (BACKEND, model_id, get_key, chat, format_usage,
                       list_models, resolve_model)


def show_models():
    if BACKEND != "anthropic":
        return
    try:
        ids = list_models()
    except Exception as e:
        print(f"モデル一覧の取得に失敗: {e}")
        return
    print("使えるモデル:")
    for i in ids:
        print(f"  {i}")
    got = resolve_model()
    print(f"→ 使用するモデル: {got}")


def show_credits():
    if BACKEND != "openrouter":
        print("残高は Anthropic Console で確認（API からは取れません）")
        return
    key = get_key("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY が読めません。.env を確認してください")
        return
    r = requests.get("https://openrouter.ai/api/v1/key",
                     headers={"Authorization": f"Bearer {key}"}, timeout=20)
    if r.status_code != 200:
        print(f"残高取得に失敗: {r.status_code} {r.text[:200]}")
        return
    d = r.json().get("data", {})
    print(f"label        : {d.get('label')}")
    print(f"usage        : ${d.get('usage')}")
    print(f"limit        : {d.get('limit')}")
    print(f"limit_remain : {d.get('limit_remaining')}")


def test_call():
    text, u = chat(
        system_common="あなたは長期投資の日報を書く書き手です。" * 40,  # キャッシュ最小長を満たすためのダミー
        system_variable="",
        messages=[{"role": "user", "content": "「疎通確認」とだけ返してください。"}],
        max_tokens=50,
    )
    print(f"応答: {text!r}")
    print(format_usage(u))


if __name__ == "__main__":
    from utils.runlog import tee
    tee("check")
    key_name = "ANTHROPIC_API_KEY" if BACKEND == "anthropic" else "OPENROUTER_API_KEY"
    print(f"backend: {BACKEND}")
    print(f"model  : {model_id()}")
    print(f"key    : {'読めています' if get_key(key_name) else '読めません（.env を確認）'}")
    print("-" * 40)
    show_models()
    print("-" * 40)
    show_credits()
    if "--call" in sys.argv:
        print("-" * 40)
        test_call()
