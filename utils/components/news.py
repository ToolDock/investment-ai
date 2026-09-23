import streamlit as st


def show_news(headlines):
    """今日・今月のニュースを、見出しだけを5本並べて伝える(2026-09-23、旧show_news()から刷新)。

    以前は見出し1本+要約文を大きなカードで見せていたが、本人の指摘
    (「文章でつらつら要約するから印象に残らない」)を受け、本番がもともと
    実データ(Finnhub)で行っていた「見出しを並べるだけ」の形式に実験側もそろえた。
    誇張・扇動的な見出し(いわゆる飛ばし記事)は含めず、実際にあったこと
    (台本の場合はその月の本文で語られている内容)だけを見出しにする。

    headlines: [{"text": ..., "text_ja": ...(本番のみ), "source": ...(本番のみ)}, ...]
    """
    if not headlines:
        return

    st.subheader("📰 今日のニュース")
    for h in headlines:
        text = h.get("text_ja") or h.get("text") or ""
        if not text:
            continue
        source = h.get("source")
        st.markdown(f"**{text}**" + (f"　*{source}*" if source else ""))
