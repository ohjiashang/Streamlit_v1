import streamlit as st
from tabs import MR_live_tab, MR_top_diffs_tab
from utils.constants import DIFFS_TO_TRACK_MAP

st.set_page_config(layout="wide")
st.title("Mean Reversion Model")

tab1, tab2 = st.tabs(["Top Diffs", "Backtest by Diff"])

with tab1:
    MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP)

with tab2:
    MR_live_tab.render()