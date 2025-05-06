import streamlit as st
import pandas as pd
from utils.plot_live import plot_live_contract_roll
from utils.backtest import generate_sd_entry_sd_exit_signals_with_rolling
from utils.constants import DIFF_NAMES, CONTRACT_TYPES, MONTHS_SCENARIO_MAP, DIFFS_MAP
from utils.month_offsets import process_offset_mths

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
                diff_scenario_og = DIFFS_MAP[selected_diff][0]
                diff_scenario = (f"{diff_scenario_og[0]}+{diff_scenario_og[0]}", diff_scenario_og[1])

            else:
                diff_scenario = DIFFS_MAP[selected_diff][0]

        
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
        # df = load_data(selected_diff, selected_contract)

        df = process_offset_mths(diff_scenario, selected_diff, months_scenario)
        if df is None:
            return
        
        # st.dataframe(df.head())
        df_1 = plot_live_contract_roll(df, diff, selected_contract, selected_rolling_window, selected_sd)

    with col_right:
        try:

            latest_date = df_1['Date'].max()
            cutoff_date = latest_date - pd.DateOffset(months=12)
            filtered_df = df_1[df_1['Date'] >= cutoff_date]

            generate_sd_entry_sd_exit_signals_with_rolling(
                filtered_df, 
                diff, 
                'entry_norm_price', 
                'exit_norm_price',
                selected_rolling_window,
                selected_sd
            )

        except Exception as e:
            st.error(f"Error generating backtest results: {e}")
