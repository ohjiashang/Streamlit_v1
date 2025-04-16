import streamlit as st
import pandas as pd
import os
from tabs import MR_live_tab, MR_hist_tab

# st.set_page_config(initial_sidebar_state="expanded")
folder_path = "Test"

# Get list of available diffs based on file names
diff_files = [f for f in os.listdir(folder_path) if f.endswith(".xlsx") and f.startswith("df_")]
# diff_options = [f.replace("df_", "").replace(".xlsx", "") for f in diff_files]


tab1, tab2, tab3 = st.tabs(["Live Data", "Top 10", "Historicals"])

with tab1:
    MR_live_tab.render()

with tab2:
    st.title("Top 10")
    st.image("Test/Boxes_top10_20250409.png", caption="Boxes Top 10", use_container_width=True)
    st.image("Test/Outrights_top10_20250409.png", caption="Outrights Top 10", use_container_width=True)

with tab3:
    MR_hist_tab.render()
