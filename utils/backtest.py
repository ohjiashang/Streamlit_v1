import streamlit as st
import pandas as pd
import re
import numpy as np
import os

def generate_sd_entry_sd_exit_signals(df, selected_diff, selected_contract, selected_rolling_window, selected_sd):
    scenario = f"{selected_rolling_window}_{selected_sd}sd_0sd"
    diff_col = 'price'

    # Column names
    entry_signal_col = f'signal_entry_{scenario}'
    exit_signal_col = f'signal_exit_{scenario}'
    return_col = f'returns_{scenario}'
    max_loss_col = f'max_loss_{scenario}'
    entry_price_col = f'entry_exit_prices_{scenario}'
    entry_date_col = f'entry_date_{scenario}'
    exit_date_col = f'exit_date_{scenario}'
    is_long_trade_col = f'is_long_{scenario}'

    def get_trade_direction(skew):
        if skew < -1:
            return 0
        elif skew > 1:
            return 1
        else:
            return 2

    # Initialize columns
    df[entry_signal_col] = 0
    df[exit_signal_col] = 0
    df[return_col] = None
    df[max_loss_col] = None
    df[entry_price_col] = None
    df[entry_date_col] = None
    df[exit_date_col] = None
    df[is_long_trade_col] = None

    # Trade state variables
    in_trade = False
    is_long_trade = None
    last_entry_price = None
    last_entry_date = None
    trade_low = float('inf')
    trade_high = float('-inf')
    trade_returns = 0.0
    trade_max_loss = 0.0

    for i in range(len(df)):
        row = df.iloc[i]
        contract_month = row['contract_month']
        current_date = row['Date']
        next_month = (current_date + pd.DateOffset(months=1)).strftime('%b')
        is_last_month = next_month == contract_month

        is_last_day_of_contract = (
            i == len(df) - 1
        )

        price = row[diff_col]
        mid = row[f"rolling_median"]
        skew = row[f"rolling_skew"]
        is_long = get_trade_direction(skew)
        upper_bound = row["upper_bound"]
        lower_bound = row["lower_bound"]

        # ENTRY
        if not in_trade and not is_last_month:
            if (is_long in [1, 2]) and price <= lower_bound:
                df.at[i, entry_signal_col] = 1
                in_trade, is_long_trade = True, True
                last_entry_price = price
                last_entry_date = current_date
                trade_low = price

            elif (is_long in [0, 2]) and price >= upper_bound:
                df.at[i, entry_signal_col] = -1
                in_trade, is_long_trade = True, False
                last_entry_price = price
                last_entry_date = current_date
                trade_high = price

        # EXIT
        elif in_trade:
            if is_long_trade:
                trade_low = min(trade_low, price)
                should_exit = price >= mid
            else:
                trade_high = max(trade_high, price)
                should_exit = price <= mid

            if should_exit or is_last_day_of_contract:
                df.at[i, exit_signal_col] = 1 if is_long_trade else -1
                trade_returns += price - last_entry_price if is_long_trade else last_entry_price - price
                trade_max_loss += trade_low - last_entry_price if is_long_trade else last_entry_price - trade_high
                df.at[i, return_col] = trade_returns
                df.at[i, max_loss_col] = trade_max_loss
                df.at[i, entry_price_col] = [round(last_entry_price, 2), round(price, 2)]
                df.at[i, entry_date_col] = last_entry_date
                df.at[i, exit_date_col] = current_date
                df.at[i, is_long_trade_col] = is_long_trade

                # Reset trade state
                in_trade = False
                is_long_trade = None
                last_entry_price = None
                last_entry_date = None
                trade_low = float('inf')
                trade_high = float('-inf')
                trade_returns = 0.0
                trade_max_loss = 0.0

    # Compile and return results
    trade_columns = [
        entry_date_col, exit_date_col, exit_signal_col,
        entry_price_col, return_col, max_loss_col
    ]

    temp = df[trade_columns].dropna(subset=trade_columns).reset_index(drop=True)
    temp['scenario'] = scenario
    temp['rolling_window'] = selected_rolling_window
    temp['entry_sd'] = selected_sd
    temp['holding_period'] = np.busday_count(
        temp[entry_date_col].values.astype('datetime64[D]'),
        temp[exit_date_col].values.astype('datetime64[D]')
    )
    temp.rename(columns={col: col.replace(f"_{scenario}", "") for col in temp.columns}, inplace=True)
    temp.rename(columns={'signal_exit': 'trade_direction'}, inplace=True)
    temp['diff'] = selected_diff
    temp['contract'] = selected_contract
    temp['entry_date'] = pd.to_datetime(temp['entry_date']).dt.strftime("%Y-%m-%d")
    temp['exit_date'] = pd.to_datetime(temp['exit_date']).dt.strftime("%Y-%m-%d")

    column_order = [
        "entry_date", 
        "exit_date",
        "holding_period", 
        "trade_direction", 
        "returns", 
        "max_loss",
        "entry_exit_prices",
        "diff", 
        "contract",
        "rolling_window", 
        "entry_sd", 
    ]

    temp = temp[column_order]
    float_cols = ["returns", "max_loss"]
    temp[float_cols] = temp[float_cols].astype(float).round(2)
    temp.index = temp.index + 1
    ###########################################################

    num_trades = len(temp)
    if num_trades == 0:
        win_rate = 0
        cum_returns = 0
        cum_max_loss = 0
        ratio = 0

    else:
        cum_returns = temp["returns"].sum()
        cum_max_loss = temp["max_loss"].sum()
        ratio = cum_returns / - cum_max_loss

        win_rate = (temp["returns"] > 0).mean() * 100
        
        cum_returns = round(cum_returns, 2)
        cum_max_loss = round(cum_max_loss, 2)
        ratio = round(ratio, 2)

    ###########################################################
    # st.subheader(f"All Trades ({selected_contract} Contract)")
    # st.markdown(f"""
    #     <span style='font-size:18px'><i>{selected_diff} | {selected_contract} Contract | {selected_rolling_window} Rolling Window | {selected_sd}SD Entry; Median Exit</i></span>
    #     """, unsafe_allow_html=True)

    st.markdown(f"""
    <span style='font-size:24px; font-weight:600'>All Trades | </span>
    <span style='font-size:16px'> {selected_diff} | {selected_contract} Contract | {selected_rolling_window} Rolling Window | {selected_sd}SD Entry; Median Exit</span>
    """, unsafe_allow_html=True)


    col1, col2, col3, col4, spacer = st.columns([1, 1, 1, 1, 4])
    with col1: 
        st.metric("Cumulative Returns", cum_returns)

    with col2:
        st.metric("Ratio", ratio)

    with col3:
        st.metric("Trades", num_trades)

    with col4:
        st.metric("Win Rate", f"{win_rate:.1f}%")

    st.dataframe(temp)


def get_historicals(diff, selected_contract, selected_rolling_window):
    folder_path = "Test"
    summary_file = os.path.join(folder_path, "MeanReversion_Outrights_20250409.xlsx")
    summary_df = pd.read_excel(summary_file, sheet_name="yearly_breakdown")

    # # Extract the desired "month" format from contract: e.g., 'Jan2025'
    # month_str = selected_contract[:3] + "/" + selected_contract[6:9]
    month_str = selected_contract[:3]

    # Extract window size from the median column: e.g., '3m'
    window_str = selected_rolling_window

    # Filter the summary dataframe
    filtered_summary = summary_df[
        (summary_df['diff'] == diff) &
        (summary_df['month'] == month_str) &
        (summary_df['window'] == window_str)
    ].reset_index()

    filtered_summary.rename(columns={
        'is_long': 'trade_direction', 
        'window': 'rolling_window',
        'returns_lst': 'trade_returns_list'
        }, inplace=True)

    # Columns to display
    display_cols = [
        'contract', 'returns', 'max_loss', 'ratio', 
        'num_trades', 'avg_holding_period', 'overall_skew', 'trade_direction', 
        'trade_returns_list',
        'diff', 'rolling_window',
    ]

    st.subheader(f"Historical Base Case (1SD Entry) Performance")
    if not filtered_summary.empty:
        st.dataframe(filtered_summary[display_cols])
    else:
        st.warning("No matching rows found in performance summary.")