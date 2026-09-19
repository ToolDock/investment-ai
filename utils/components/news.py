import streamlit as st

def show_news(news):
    if not news["headline"] and not news["body"]:
        return

    st.subheader("📰 市場ニュース")

    with st.container(border=True):
        st.markdown(f"### {news['headline']}")
        st.write(news["body"])