import streamlit as st
from tabs import MR_live_tab, MR_top_diffs_tab
from utils.constants import DIFFS_TO_TRACK_MAP, DIFFS_TO_TRACK_MAP_OR
import warnings
# warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
warnings.filterwarnings("ignore")
import urllib.parse


st.set_page_config(layout="wide", page_title="MeanReversion")
st.title("Mean Reversion")

tab1, tab2, tab3, tab4 = st.tabs(["Top Diffs (Boxes)", "Top Diffs (Outrights)", "Backtest by Diff", "Documentation"])

with tab1:
    MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP, "scenarios_Boxes_50")

with tab2:
    MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP_OR, "scenarios_Outrights")

with tab3:
    MR_live_tab.render()

with tab4:
    folder = "Test"
    filename = f"Mean Reversion Model_Documentation_20250630.pdf"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"

    st.markdown(
        f'<iframe src="{url}" width="850" height="1000" type="application/pdf"></iframe>',
        unsafe_allow_html=True
    )

