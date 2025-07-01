import streamlit as st
from tabs import MR_live_tab, MR_top_diffs_tab
from utils.constants import DIFFS_TO_TRACK_MAP, DIFFS_TO_TRACK_MAP_OR
from utils.documentation import display_doc
import warnings
# warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
warnings.filterwarnings("ignore")

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
    display_doc(folder, f"Mean Reversion Model_Documentation_20250630_A.htm", "A) Methodology")
    display_doc(folder, f"Mean Reversion Model_Documentation_20250630_B.htm", "B) Shortlisting of Top Mean-Reverting Differentials")

