# import streamlit as st
# import pandas as pd
# import os
# import matplotlib.pyplot as plt
# import urllib.parse
# from utils.plot_live import plot_live
# from utils.constants import DIFF_NAMES, CONTRACTS


# def render(): 
#     # st.title("Filter by Diff")

#     # Step 1: Select diff from dropdown
#     selected_diff = st.selectbox("Select Diff:", DIFF_NAMES)
#     selected_contract = st.selectbox("Select Contract:", CONTRACTS)

#     # Define your options
#     keywords = ["0.5"]
#     if any(keyword in selected_diff for keyword in keywords):
#         rolling_window_options = ['1m', '2m', '3m', '6m', '12m']
#     else:
#         rolling_window_options = ['1m', '2m', '3m', '6m', '12m', '24m', '36m']

#     sd_options = [1, 2]

#     # Create two columns
#     col1, col2 = st.columns(2)

#     # Place the selectboxes in the respective columns
#     with col1:
#         selected_rolling_window = st.selectbox("Select Rolling Window:", rolling_window_options)

#     with col2:
#         selected_sd = st.selectbox("Select SD:", sd_options)

#     # Firebase public file URL
#     folder = "Outrights"
#     diff = selected_diff.partition("]")[2].lstrip()
#     filename = f"{diff}_Outrights.xlsx"

#     encoded_filename = urllib.parse.quote(filename)
#     url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
#     print(url)

#     try:
#         # Load the Excel file (all sheets)
#         df = pd.read_excel(url, sheet_name=selected_contract[:3])

#         if df is None:
#             st.warning(f"No data found for sheet: {selected_contract[:3]}")
#             st.stop()

#         plot_live(df, diff, selected_contract, selected_rolling_window, selected_sd)
#         print("test")



#     except Exception as e:
#         st.error(f"Error loading or processing file: {e}")


import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt
import urllib.parse
from utils.plot_live import plot_live
from utils.constants import DIFF_NAMES, CONTRACTS


def render():
    # Step 1: Set initial session state values (only if not already set)
    if "selected_diff" not in st.session_state:
        st.session_state["selected_diff"] = DIFF_NAMES[0]
    if "selected_contract" not in st.session_state:
        st.session_state["selected_contract"] = CONTRACTS[0]
    if "selected_rolling_window" not in st.session_state:
        st.session_state["selected_rolling_window"] = '1m'
    if "selected_sd" not in st.session_state:
        st.session_state["selected_sd"] = 1

    # Step 2: Widgets (linked to session_state via key)
    selected_diff = st.selectbox("Select Diff:", DIFF_NAMES, key="selected_diff")
    selected_contract = st.selectbox("Select Contract:", CONTRACTS, key="selected_contract")

    # Step 3: Conditional options based on selected_diff
    keywords = ["0.5"]
    if any(keyword in selected_diff for keyword in keywords):
        rolling_window_options = ['1m', '2m', '3m', '6m', '12m']
    else:
        rolling_window_options = ['1m', '2m', '3m', '6m', '12m', '24m', '36m']

    col1, col2 = st.columns(2)
    with col1:
        selected_rolling_window = st.selectbox(
            "Select Rolling Window:", 
            rolling_window_options, 
            key="selected_rolling_window"
        )

    with col2:
        selected_sd = st.selectbox(
            "Select SD:", 
            [1, 2], 
            key="selected_sd"
        )

    # Step 4: Firebase URL setup
    folder = "Outrights"
    diff = selected_diff.partition("]")[2].lstrip()
    filename = f"{diff}_Outrights.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"

    try:
        df = pd.read_excel(url, sheet_name=selected_contract[:3])
        if df is None or df.empty:
            st.warning(f"No data found for sheet: {selected_contract[:3]}")
            st.stop()

        plot_live(df, diff, selected_contract, selected_rolling_window, selected_sd)

    except Exception as e:
        st.error(f"Error loading or processing file: {e}")
