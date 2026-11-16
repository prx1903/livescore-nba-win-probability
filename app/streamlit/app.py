"""Streamlit shell of the demo: shows the built page (docs/index.html) inside a Streamlit app.

Run from the repository root:
    pip install streamlit
    streamlit run app/streamlit/app.py

The match screen is the page itself (it draws 60 frames per second in the browser, which Streamlit widgets
cannot do), so both show exactly the same numbers. Rebuild the page with: python -I app/demo/build_page.py"""
from pathlib import Path

import streamlit as st

PAGE = Path(__file__).resolve().parents[2] / 'docs' / 'index.html'
HEIGHT = 900          # px; the page scrolls inside this frame

st.set_page_config(page_title='NBA canlı kazanma olasılığı', layout='wide')
# use the whole window: the page has its own header and margins
st.markdown('<style>.block-container{padding:0.5rem 0.5rem 0;max-width:100%} header{visibility:hidden}</style>',
            unsafe_allow_html=True)

if not PAGE.exists():
    st.error(f'{PAGE} bulunamadı. Önce sayfayı üretin: python -I app/demo/build_page.py')
    st.stop()

html = PAGE.read_text(encoding='utf-8')
if hasattr(st, 'iframe'):                       # current Streamlit
    st.iframe(html, height=HEIGHT)
else:                                           # older Streamlit: the previous function for the same job
    import streamlit.components.v1 as components
    components.html(html, height=HEIGHT, scrolling=True)
