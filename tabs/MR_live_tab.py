import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt
import urllib.parse
from utils.plot_live import plot_live
from utils.constants import DIFF_NAMES, CONTRACTS


def render(): 
    # st.title("Filter by Diff")

    # Step 1: Select diff from dropdown
    selected_diff = st.selectbox("Select Diff:", DIFF_NAMES)
    selected_contract = st.selectbox("Select Contract:", CONTRACTS)

    # Define your options
    rolling_window_options = ['1m', '3m', '12m']
    sd_options = [1, 2]

    # Create two columns
    col1, col2 = st.columns(2)

    # Place the selectboxes in the respective columns
    with col1:
        selected_rolling_window = st.selectbox("Select Rolling Window:", rolling_window_options)

    with col2:
        selected_sd = st.selectbox("Select SD:", sd_options)

    # Firebase public file URL
    folder = "Outrights"
    filename = f"{selected_diff}_Outrights.xlsx"

    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
    print(url)

    try:
        # Load the Excel file (all sheets)
        df = pd.read_excel(url, sheet_name=selected_contract[:3])

        if df is None:
            st.warning(f"No data found for sheet: {selected_contract[:3]}")
            st.stop()

        plot_live(df, selected_diff, selected_contract, selected_rolling_window, selected_sd)
        print("test")



    except Exception as e:
        st.error(f"Error loading or processing file: {e}")
