import streamlit as st
import pandas as pd
import re
import numpy as np
import os

@st.cache_data
def generate_sd_entry_sd_exit_signals_with_rolling(df, diff, selected_contract, entry_col, exit_col, window, sd_entry):
    """
    Generate entry and exit signals with contract rolling logic.
    Return column displays accumulated returns AFTER each trade and resets to 0 after every exit.
    """
    
    ### Backtest 19 months of data
    df['Date'] = pd.to_datetime(df['Date'])
    latest_date = df['Date'].max()

    # cutoff_date_backtest = latest_date - pd.DateOffset(months=19)
    # df = df[df['Date'] >= cutoff_date_backtest].copy()
    df = df.reset_index(drop=True)

    scenario = f'{window}_{sd_entry}sd_0sd'
    entry_signal_col = f'signal_entry_{scenario}'
    exit_signal_col = f'signal_exit_{scenario}'
    return_col = f'returns_{scenario}'
    max_loss_col = f'max_loss_{scenario}'
    entry_price_col = f'entry_exit_prices_{scenario}'
    entry_date_col = f'entry_date_{scenario}'
    exit_date_col = f'exit_date_{scenario}'
    is_long_trade_col = f'is_long_{scenario}'
    contracts_col = f'contracts_{scenario}'

    # Initialize signal and return columns
    df[entry_signal_col] = 0
    df[exit_signal_col] = 0
    df[return_col] = None
    df[max_loss_col] = None
    df[entry_price_col] = None
    df[entry_date_col] = None
    df[exit_date_col] = None
    df[is_long_trade_col] = None
    df[contracts_col] = None
    
    in_trade = False
    is_long_trade = None
    last_entry_price = None
    last_entry = None # no normalise
    last_entry_date = None

    rolled_once = False

    trade_prices = []
    trade_contracts = []
    trade_low = float('inf')
    trade_high = float('-inf')
    trade_returns = 0.0
    trade_max_loss = 0.0

    for i in range(len(df)):
        row = df.iloc[i]
        exit_contract_month = row['exit_contract_month']
        exit_contract = row['exit_contract']

        if selected_contract == "Box":
            exit_contract = exit_contract.replace('-', '/')
        if selected_contract == "Outright":
            exit_contract = exit_contract[:5]

        current_date = row['Date']
        
        is_last_day_of_contract = (
            i == len(df) - 1 or df.at[i + 1, 'exit_contract_month'] != exit_contract_month
        )

        is_last_day_of_data = i == len(df) - 1

        mid = row[f"rolling_median"]
        upper_bound = row["upper_bound"]
        lower_bound = row["lower_bound"]

        if not in_trade:
            is_long_trade = 2

        entry_price = row[entry_col]
        exit_price = row[exit_col]

        entry = row['entry_price']
        exit = row['exit_price']

        # ENTRY
        if not in_trade:
            # LONG
            if (is_long_trade == 1 or is_long_trade == 2) and entry_price <= lower_bound:
                df.at[i, entry_signal_col] = 1
                in_trade = True
                is_long_trade = True
                last_entry_date = current_date
                last_entry_price = entry_price
                last_entry = entry
                trade_low = entry_price

            # SHORT
            elif (is_long_trade == 0 or is_long_trade == 2) and entry_price >= upper_bound:
                df.at[i, entry_signal_col] = -1
                in_trade = True
                is_long_trade = False
                last_entry_date = current_date
                last_entry_price = entry_price
                last_entry = entry
                trade_high = entry_price

        # EXIT
        elif in_trade:
            if is_long_trade:
                trade_low = min(trade_low, exit_price)
            else:
                trade_high = max(trade_high, exit_price)

            # LONG
            if is_long_trade and ((exit_price >= mid) or is_last_day_of_data):
                df.at[i, exit_signal_col] = 1
                trade_returns += exit_price - last_entry_price
                trade_max_loss += trade_low - last_entry_price
                df.at[i, return_col] = trade_returns
                df.at[i, max_loss_col] = trade_max_loss
                trade_prices.append((round(last_entry, 2), round(exit, 2)))
                trade_contracts.append(exit_contract)
                
                df.at[i, entry_price_col] = trade_prices
                df.at[i, contracts_col] = trade_contracts
                df.at[i, entry_date_col] = last_entry_date
                df.at[i, exit_date_col] = current_date
                df.at[i, is_long_trade_col] = is_long_trade

                in_trade = False
                last_entry_price = None
                last_entry = None
                is_long_trade = None
                trade_returns = 0.0
                trade_max_loss = 0.0
                last_entry_date = None
                trade_prices = []
                trade_contracts = []
                trade_low = float('inf')
                trade_high = float('-inf')
                rolled_once = False

            # SHORT
            elif (not is_long_trade) and ((exit_price <= mid) or is_last_day_of_data):
                df.at[i, exit_signal_col] = -1
                trade_returns += last_entry_price - exit_price
                trade_max_loss += last_entry_price - trade_high
                df.at[i, return_col] = trade_returns
                df.at[i, max_loss_col] = trade_max_loss
                trade_prices.append((round(last_entry, 2), round(exit, 2)))
                trade_contracts.append(exit_contract)
                
                df.at[i, entry_price_col] = trade_prices
                df.at[i, contracts_col] = trade_contracts
                df.at[i, entry_date_col] = last_entry_date
                df.at[i, exit_date_col] = current_date
                df.at[i, is_long_trade_col] = is_long_trade

                in_trade = False
                last_entry_price = None
                last_entry = None
                is_long_trade = None
                trade_returns = 0.0
                trade_max_loss = 0.0
                last_entry_date = None
                trade_prices = []
                trade_contracts = []
                trade_low = float('inf')
                trade_high = float('-inf')
                rolled_once = False

            if is_last_day_of_contract and in_trade:
                if not rolled_once:
                    # Roll once: transfer trade to next contract
                    rolled_once = True
                    trade_prices.append((round(last_entry, 2), round(exit, 2)))
                    trade_contracts.append(exit_contract)
                    trade_returns += (exit_price - last_entry_price) if is_long_trade else (last_entry_price - exit_price)
                    trade_max_loss += (trade_low - last_entry_price) if is_long_trade else (last_entry_price - trade_high)
                    
                    last_entry_price = entry_price
                    last_entry = entry
            
                    if is_long_trade:
                        trade_low = entry_price
                    else:
                        trade_high = entry_price
            
                else:
                    # If already rolled once, force exit
                    df.at[i, exit_signal_col] = 1 if is_long_trade else -1
                    trade_returns += (exit_price - last_entry_price) if is_long_trade else (last_entry_price - exit_price)
                    trade_max_loss += (trade_low - last_entry_price) if is_long_trade else (last_entry_price - trade_high)
                    df.at[i, return_col] = trade_returns
                    df.at[i, max_loss_col] = trade_max_loss
                    trade_prices.append((round(last_entry, 2), round(exit, 2)))
                    trade_contracts.append(exit_contract)
                    df.at[i, entry_price_col] = trade_prices
                    df.at[i, contracts_col] = trade_contracts
                    df.at[i, entry_date_col] = last_entry_date
                    df.at[i, exit_date_col] = current_date
                    df.at[i, is_long_trade_col] = is_long_trade
            
                    # Reset trade variables
                    in_trade = False
                    last_entry_price = None
                    last_entry = None
                    is_long_trade = None
                    trade_returns = 0.0
                    trade_max_loss = 0.0
                    last_entry_date = None
                    trade_prices = []
                    trade_contracts = []
                    trade_low = float('inf')
                    trade_high = float('-inf')
                    rolled_once = False

    trade_columns = [
        f'entry_date_{scenario}',
        f'exit_date_{scenario}',
        f'signal_exit_{scenario}',
        f'entry_exit_prices_{scenario}',
        f'contracts_{scenario}',
        f'returns_{scenario}',
        f'max_loss_{scenario}',
    ]

    selected_columns = trade_columns
    temp = df[selected_columns].dropna(subset=trade_columns).reset_index(drop=True)

    temp['scenario'] = scenario
    temp['rolling_window'] = window
    temp['entry_sd'] = sd_entry
    temp['holding_period'] = np.busday_count(
        temp[f'entry_date_{scenario}'].values.astype('datetime64[D]'),
        temp[f'exit_date_{scenario}'].values.astype('datetime64[D]')
    )
    temp.rename(columns={col: col.replace(f"_{scenario}", "") for col in temp.columns}, inplace=True)
    temp.rename(columns={'signal_exit': 'trade_direction'}, inplace=True)
    temp[f'year'] = pd.to_datetime(temp[f'entry_date']).dt.year
    temp['diff'] = diff

    temp['entry_date'] = pd.to_datetime(temp['entry_date']).dt.strftime("%Y-%m-%d")
    temp['exit_date'] = pd.to_datetime(temp['exit_date']).dt.strftime("%Y-%m-%d")

    column_order = [ 
        "trade_direction", 
        "entry_date", 
        "exit_date", 
        "returns", 
        "max_loss",
        "holding_period", 
        "contracts",
        "year",
        "rolling_window", 
        "entry_sd",
        "diff"
    ]

    temp = temp[column_order]
    float_cols = ["returns", "max_loss"]
    temp[float_cols] = temp[float_cols].astype(float).round(2)

    df2 = temp.copy()
    
    cutoff_date = (latest_date - pd.DateOffset(months=12)).strftime("%Y-%m-%d")
    temp = temp[temp['entry_date'] >= cutoff_date].copy()

    temp = temp.sort_values(by='entry_date', ascending=False).reset_index(drop=True)
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

    st.markdown(f"""
    <span style='font-size:24px; font-weight:600'>Trades (Last 12 Months) </span>
    """, unsafe_allow_html=True)


    col1, col2, col3, col4, spacer = st.columns([1, 1, 1, 1, 4])
    with col1: 
        st.metric("Returns", cum_returns)

    with col2:
        st.metric("Ratio", ratio)

    with col3:
        st.metric("No. Trades", num_trades)

    with col4:
        st.metric("Win Rate", f"{win_rate:.1f}%")

    st.dataframe(temp)

    ###################################################################################################
    st.markdown(f"""
    <span style='font-size:24px; font-weight:600'>Yearly Performance</span>
    """, unsafe_allow_html=True)

    # Create the pivot table
    pivot = df2.groupby(['year', 'rolling_window', 'entry_sd', 'diff']).agg(
        returns=('returns', 'sum'),
        max_loss=('max_loss', 'sum'),
        avg_holding_period=('holding_period', 'mean'),
        num_trades=('entry_date', 'count')
    ).reset_index()


    pivot['ratio'] = (pivot['returns']/-pivot['max_loss']).astype(float).round(2)
    pivot['avg_holding_period'] = pivot['avg_holding_period'].astype(int)

    # Sort the pivot table by descending 'year'
    pivot = pivot.sort_values(by='year', ascending=False).reset_index(drop=True)
    pivot.index = pivot.index + 1

    column_order_pivot = [ 
        "year",
        "returns", 
        "ratio",
        "max_loss",
        "num_trades",
        "avg_holding_period",
        "rolling_window", 
        "entry_sd",
        "diff"
    ]

    pivot = pivot[column_order_pivot]

    st.dataframe(pivot)


