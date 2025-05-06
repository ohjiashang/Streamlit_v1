import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt
import urllib.parse
from utils.plot_live import plot_live
from utils.backtest import generate_sd_entry_sd_exit_signals, get_historicals
from utils.constants import DIFF_NAMES, CONTRACTS


def load_data(selected_diff, selected_contract):
    folder = "Outrights"
    diff_name = selected_diff.partition("]")[2].lstrip()
    filename = f"{diff_name}_Outrights.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"

    try:
        df = pd.read_excel(url, sheet_name=selected_contract[:3])
        if df.empty:
            st.warning(f"No data found for sheet: {selected_contract[:3]}")
            return None
        return df
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None

def render():
    # Step 1: Set initial session state values (only if not already set)
    # --- Session State Initialization ---
    st.session_state.setdefault("selected_diff", DIFF_NAMES[0])
    st.session_state.setdefault("selected_contract", CONTRACTS[0])
    st.session_state.setdefault("selected_rolling_window", '1m')
    st.session_state.setdefault("selected_sd", 1)

    col_left, spacer, col_right = st.columns([1, 0.05, 1])  # adjust ratio as needed

    with col_left:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            selected_diff = st.selectbox("Select Diff:", DIFF_NAMES, key="selected_diff")
            diff = selected_diff.partition("]")[2].lstrip()

        with col2:
            selected_contract = st.selectbox("Select Contract:", CONTRACTS, key="selected_contract")
        
        with col3:
            # Step 3: Conditional options based on selected_diff
            keywords = ["0.5"]
            if any(keyword in selected_diff for keyword in keywords):
                rolling_window_options = ['1m', '2m', '3m', '6m', '12m']
            else:
                rolling_window_options = ['1m', '2m', '3m', '6m', '12m', '24m', '36m']

            selected_rolling_window = st.selectbox(
                "Select Rolling Window:", 
                rolling_window_options, 
                key="selected_rolling_window"
            )

        with col4:
            selected_sd = st.selectbox(
                "Select SD:", 
                [1, 2], 
                key="selected_sd"
            )

        # --- Load and Plot Data ---
        df = load_data(selected_diff, selected_contract)
        if df is None:
            return

        filtered_df = plot_live(df, diff, selected_contract, selected_rolling_window, selected_sd)

    with col_right:
        try:
            generate_sd_entry_sd_exit_signals(
                filtered_df, 
                diff, 
                selected_contract,
                selected_rolling_window,  # Ensure integer format
                selected_sd
            )

            get_historicals(diff, selected_contract, selected_rolling_window)

        except Exception as e:
            st.error(f"Error generating backtest results: {e}")
