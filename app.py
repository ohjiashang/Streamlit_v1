import streamlit as st
from tabs import MR_live_tab, MR_top_diffs_tab, MR_cash
from utils.constants import DIFFS_TO_TRACK_MAP, DIFFS_TO_TRACK_MAP_OR

st.set_page_config(layout="wide")
st.title("Mean Reversion Model")

tab1, tab2, tab3 = st.tabs(["Top Diffs (Boxes)", "Top Diffs (Outrights)", "Backtest by Diff"])

with tab1:
    MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP, "scenarios_Boxes_50")

with tab2:
    MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP_OR, "scenarios_Outrights")

with tab3:
    MR_live_tab.render()

# tab1, tab2, tab3, tab4 = st.tabs(["Top Diffs (Boxes)", "Top Diffs (Outrights)", "Backtest by Diff", "Cash"])

# with tab1:
#     MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP, "scenarios_Boxes_50")

# with tab2:
#     MR_top_diffs_tab.get_table(DIFFS_TO_TRACK_MAP_OR, "scenarios_Outrights")

# with tab3:
#     MR_live_tab.render()

# with tab4:
#     col1, col2 = st.columns(2)

#     with col1:
#         MR_cash.render()
