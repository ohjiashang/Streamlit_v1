import streamlit as st
import pandas as pd
from utils.plot_live import plot_live_contract_roll, add_rolling_cols, plot_live_contract_roll_plotly
from utils.backtest import generate_sd_entry_sd_exit_signals_with_rolling
from utils.constants import DIFF_NAMES, CONTRACT_TYPES, MONTHS_SCENARIO_MAP, DIFFS_MAP
from utils.month_offsets import get_price_series

def render():
    # Step 1: Set initial session state values (only if not already set)
    # --- Session State Initialization ---
    st.session_state.setdefault("selected_diff", DIFF_NAMES[0])
    st.session_state.setdefault("selected_contract", CONTRACT_TYPES[0])
    st.session_state.setdefault("selected_rolling_window", '1m')
    st.session_state.setdefault("selected_sd", 1)

    col_left, spacer, col_right = st.columns([1, 0.05, 1])  # adjust ratio as needed

    with col_left:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            selected_diff = st.selectbox("Select Diff:", DIFF_NAMES, key="selected_diff")
            diff = selected_diff.partition("]")[2].lstrip()

        with col2:
            selected_contract = st.selectbox("Select Price Series:", CONTRACT_TYPES, key="selected_contract")
            months_scenario = MONTHS_SCENARIO_MAP[selected_contract]

            if selected_contract == "Box":
                diff_scenario = DIFFS_MAP[selected_diff][1]

            elif selected_contract == "Outright":
                diff_scenario_og = DIFFS_MAP[selected_diff][1]
                diff_scenario = (f"{diff_scenario_og[0]}+{diff_scenario_og[0]}", diff_scenario_og[1])

            else:
                diff_scenario = DIFFS_MAP[selected_diff][0]
        
        with col3:
            rolling_window_options = ['1m', '3m', '6m', '12m']

            selected_rolling_window = st.selectbox(
                "Select Rolling Window:", 
                rolling_window_options, 
                key="selected_rolling_window"
            )

        with col4:
            selected_sd = st.selectbox(
                "Select Entry SD:", 
                [1, 2, 3, 4], 
                key="selected_sd"
            )

        # --- Load and Plot Data ---
        months_m1_lst = ["Mar", "Jun", "Sep", "Dec"]
        years = [16, 17, 18, 19, 20, 21, 22, 23, 24, 25]

        df = get_price_series(diff_scenario, months_scenario, months_m1_lst, years)
        
        if df is None:
            return

        df = add_rolling_cols(df, selected_rolling_window, selected_sd)
        plot_live_contract_roll_plotly(df, diff, selected_contract, selected_rolling_window, selected_sd)

    with col_right:
        try:

            generate_sd_entry_sd_exit_signals_with_rolling(
                df, 
                diff, 
                selected_contract,
                'entry_norm_price', 
                'exit_norm_price',
                selected_rolling_window,
                selected_sd
            )

        except Exception as e:
            st.error(f"Error generating backtest results: {e}")
