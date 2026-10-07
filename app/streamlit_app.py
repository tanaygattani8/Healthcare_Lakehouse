"""The app's entry point: the pages and the top bar. Each chapter is its own
script in chapters/; the design kit is ui.py."""

import streamlit as st
from ui import CHAPTERS

st.set_page_config(page_title="Healthcare Lakehouse", page_icon=":material/conversion_path:",
                   layout="wide")

pages = [st.Page("chapters/home.py", title="The map", url_path="map", default=True)]
pages += [st.Page(path, title=f"{n:02d} {short}", url_path=path.split("_", 1)[1][:-3])
          for n, path, short, _, _ in CHAPTERS]
st.navigation(pages, position="top").run()
