import streamlit as st


def scroll_to_top(once_key=None):
    """ページの先頭に戻す。once_key を渡すと、そのキーごとに最初の1回だけ実行する。"""
    if once_key:
        if st.session_state.get(once_key):
            return
        st.session_state[once_key] = True
    st.session_state["_scroll_n"] = st.session_state.get("_scroll_n", 0) + 1
    # 呼ぶたびに中身を変えないと、同じ iframe と見なされて再実行されない
    html = """<script>// run NONCE
        const sels = ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]',
                      '[data-testid="stMainViewContainer"]',
                      '[data-testid="stMainBlockContainer"]',
                      '.stMainBlockContainer', 'section.main', '.main'];
        function toTop() {
          const d = window.parent.document;
          if (d.activeElement && typeof d.activeElement.blur === 'function') {
            d.activeElement.blur();
          }
          for (const s of sels) {
            d.querySelectorAll(s).forEach(el => {
              if (el.scrollHeight > el.clientHeight) el.scrollTop = 0;
            });
          }
          d.querySelectorAll('*').forEach(el => {
            if (el.scrollTop > 0 && el.scrollHeight > el.clientHeight) el.scrollTop = 0;
          });
          if (d.scrollingElement) d.scrollingElement.scrollTop = 0;
          if (d.documentElement) d.documentElement.scrollTop = 0;
          if (d.body) d.body.scrollTop = 0;
          window.parent.scrollTo(0, 0);
        }
        [0, 60, 200, 500, 900, 1500].forEach(t => setTimeout(toTop, t));
        </script>""".replace("NONCE", str(st.session_state["_scroll_n"]))
    st.iframe(html, height=1)
