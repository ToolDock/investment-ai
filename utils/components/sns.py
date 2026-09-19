import streamlit as st

def show_sns(posts):
    if not posts:
        return

    st.subheader("◎ SNSの反応")

    for post in posts:
        user = post.get("user", "匿名")
        text = post.get("text", "")
        likes = post.get("likes", 0)

        with st.container(border=True):
            st.markdown(f"**@{user}**")
            st.write(text)
            st.caption(f"❤️ {likes}")