import pandas as pd
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import streamlit as st

# Global month dictionary
month_dct = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

# def get_start_end_dates(contract, num_lookback_months=5):
def get_start_end_dates(contract, num_lookback_months=3):
    # Step 1: Compute dynamic start and end dates
    year = 2000 + int(contract[-2:])
    month = month_dct[contract[:3]]
    start_date = pd.Timestamp(year, month, 1) - pd.DateOffset(months=num_lookback_months)
    end_date = pd.Timestamp(year, month, 1) - pd.DateOffset(days=1) - pd.offsets.MonthEnd(2)

    # Step 2: Read Dates from static file
    folder = "Data"
    filename = f"Dates.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
    static_df = pd.read_excel(url)
    static_df['Date'] = pd.to_datetime(static_df['Date'])
    static_df = static_df.sort_values('Date').reset_index(drop=True)

    # Step 3: Find matching indices
    start_idx = static_df[static_df['Date'] >= start_date].index.min()
    end_idx = static_df[static_df['Date'] <= end_date].index.max()

    # Step 4: Handle edge cases
    if pd.isna(start_idx) or pd.isna(end_idx):
        return None, None

    # Step 5: Adjust indices
    start_idx = max(0, start_idx - 2)
    if end_idx < len(static_df) - 1:
        end_idx = max(0, end_idx - 1)

    # Step 6: Extract adjusted dates
    adj_start_date = static_df.loc[start_idx, 'Date']
    adj_end_date = static_df.loc[end_idx, 'Date']
    return adj_start_date.strftime('%Y-%m-%d'), adj_end_date.strftime('%Y-%m-%d')

@st.cache_data
def read_excel_cached(url, sheet_name):
    return pd.read_excel(url, sheet_name=sheet_name)

def get_m1_to_m4_contracts(contract_m1):
    month, year = contract_m1[:3], int(contract_m1[3:])
    start_month = month_dct[month]
    contracts = []
    for i in range(4):
        new_month = (start_month + i - 1) % 12 + 1
        new_year = year + (start_month + i - 1) // 12
        new_month_name = [k for k, v in month_dct.items() if v == new_month][0]
        contracts.append(f"{new_month_name}{new_year}")
    return contracts


def calculate_outright(diff, contract_m1, month_scenario, df_cache=None):
    contracts_m1_to_m4 = get_m1_to_m4_contracts(contract_m1)
    start_date, end_date = get_start_end_dates(contract_m1)
    contract = contracts_m1_to_m4[month_scenario - 1]
    target_month = contract[:3]

    tokens = re.split(r'(\+|-)', diff)
    operators = [t for t in tokens if t in ['+', '-']]
    products = [t.strip() for t in tokens if t not in ['+', '-']]

    all_dfs = []
    for i, product in enumerate(products):
        key = (product, target_month)
        if df_cache and key in df_cache:
            df = df_cache[key]
        else:
            folder = "Symbols"
            filename = f"{product}_18m.xlsx"
            encoded_filename = urllib.parse.quote(filename)
            url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
            df = read_excel_cached(url, f"{product}_{target_month}")
            if df_cache is not None:
                df_cache[key] = df

        df = df[df['contract'] == contract][['Date', 'price']].rename(columns={'price': f'price_{i+1}'})
        all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame(columns=["Date", "price", "diff", "contract"])
    
    final_df = all_dfs[0]
    for df in all_dfs[1:]:
        final_df = final_df.merge(df, on='Date', how='inner')

    final_df = final_df[(final_df['Date'] >= start_date) & (final_df['Date'] <= end_date)]
    if final_df.empty:
        return pd.DataFrame(columns=["Date", "price", "diff", "contract"])

    final_price = final_df['price_1']
    for i, op in enumerate(operators):
        if op == '+':
            final_price += final_df[f'price_{i+2}']
        else:
            final_price -= final_df[f'price_{i+2}']

    final_df['price'] = final_price
    final_df['diff'] = diff
    final_df['contract'] = contract
    return final_df[['Date', 'price', 'diff', 'contract']]

def calculate_diff(diff_scenario_tup, contract_m1, month_scenario_tup, df_cache=None):
    diff_1, diff_2 = diff_scenario_tup
    month_scenario_1, month_scenario_2 = month_scenario_tup

    df_1 = calculate_outright(diff_1, contract_m1, month_scenario_1, df_cache=df_cache)
    df_1 = df_1.rename(columns={"Date": "Date", "price": "price_1", "diff": "diff_1", "contract": "contract_1"})

    df_2 = calculate_outright(diff_2, contract_m1, month_scenario_2, df_cache=df_cache)
    df_2 = df_2.rename(columns={"Date": "Date", "price": "price_2", "diff": "diff_2", "contract": "contract_2"})

    df_3 = df_1.merge(df_2, how='inner', on=['Date'])
    df_3['m1_contract'] = contract_m1
    df_3['m1'] = contract_m1[:3]
    df_3['diffs_scenario'] = [diff_scenario_tup] * len(df_3)
    df_3['mths_scenario'] = [month_scenario_tup] * len(df_3)
    df_3['price'] = df_3['price_1'] - df_3['price_2']
    return df_3

def get_price_series(diff_scenario, months_scenario, months_m1_lst, years):
    df_cache = {}  # <-- shared cache
    
    def process_contract(year, month_m1):
        contract_m1 = month_m1 + str(year)
        return calculate_diff(diff_scenario, contract_m1, months_scenario, df_cache=df_cache)

    dfs = []
    last_price = None
    last_norm = 0

    # Step 1: Ordered task list
    task_list = [
        (year, month_m1)
        for year in reversed(years)
        for month_m1 in (
            reversed(months_m1_lst) if year != 26 else ["Jan"]
        )
    ]

    def fetch_contract(year, month_m1):
        df_contract = process_contract(year, month_m1)
        return (year, month_m1, df_contract)

    # Step 2: Parallel fetch (maintains task order)
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda args: fetch_contract(*args), task_list))

    # Step 3: Sequential normalization
    dfs = []
    last_price = None
    last_norm = 0

    for year, month_m1, df_contract in results:
        if not df_contract.empty:
            if last_price is not None:
                norm_diff = df_contract["price"].iloc[-1] - last_price
                last_norm += norm_diff
                df_contract["norm_value"] = last_norm
            else:
                df_contract["norm_value"] = 0.0
            last_price = df_contract["price"].iloc[0]
            df_contract['norm_price'] = df_contract['price'] - df_contract['norm_value']
            dfs.append(df_contract)

    if not dfs:
        raise ValueError("Input list of DataFrames is empty")

    # Validate required columns
    required_cols = ['Date', 'contract_1', 'contract_2', 'diff_1', 'diff_2', 'mths_scenario', 'price', 'norm_value', 'norm_price']
    for df in dfs:
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns in DataFrame: {missing_cols}")

    # Concatenate DataFrames in reverse order
    df_new = pd.concat(dfs[::-1], ignore_index=True, copy=False)

    # Create contract and contract_month columns
    df_new['contract'] = df_new['contract_1'].astype(str) + '-' + df_new['contract_2'].astype(str)
    df_new['contract_month'] = df_new['contract_1'].str[:3] + '-' + df_new['contract_2'].str[:3]

    # Columns to keep
    cols_to_keep = ['Date', 'diff_1', 'diff_2', 'mths_scenario', 'contract', 'contract_month', 'price', 'norm_value', 'norm_price']

    # Process entry and exit DataFrames
    df_entry = df_new.drop_duplicates(subset='Date', keep='last')[cols_to_keep]
    df_exit = df_new.drop_duplicates(subset='Date', keep='first')[cols_to_keep]

    # Rename columns
    cols_to_rename = ['contract', 'contract_month', 'price', 'norm_value', 'norm_price']
    rename_entry = {col: f'entry_{col}' for col in cols_to_rename}
    rename_exit = {col: f'exit_{col}' for col in cols_to_rename}
    
    df_entry = df_entry.rename(columns=rename_entry)
    df_exit = df_exit.rename(columns=rename_exit)

    # Merge DataFrames
    cols_to_merge = ['Date', 'diff_1', 'diff_2', 'mths_scenario']
    df_final = df_entry.merge(df_exit, on=cols_to_merge, how='left', copy=False)
    return df_final