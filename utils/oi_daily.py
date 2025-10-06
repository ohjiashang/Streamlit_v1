import pandas as pd
from datetime import datetime
import calendar
from functools import reduce
import urllib.parse
import streamlit as st
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from utils.oi_constants import FORWARD_CONTRACTS_TO_SKIP, OI_V2_SPREAD_SYMBOLS

@st.cache_data
def read_dfs(symbol, suffix="OI"):
    folder = "OI"
    if suffix == 'price' and symbol in OI_V2_SPREAD_SYMBOLS:
        filename = f"{symbol}_24m_{suffix}_spr.xlsx"
    else:
        filename = f"{symbol}_24m_{suffix}.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
    dfs = pd.read_excel(url, sheet_name=None)
    return dfs

#####
#####
@st.cache_data
def read_OI_volume():
    folder = "Test"
    filename = f"OI_volume.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
    df = pd.read_excel(url)
    return df

def style_OI_column_groups(df):
    # Define suffixes and their colors
    suffix_color_map = {
        '_OI': "#FFFFE0",  
        '_OI_chg': '#FFD480',  # Mellow, warm, and coherent with #FFFFE0
        '_vol': '#b3e6ff',
    }

    # Map each column to a color based on its suffix
    col_colors = {}
    for col in df.columns:
        for suffix, color in suffix_color_map.items():
            if col.endswith(suffix):
                col_colors[col] = color
                break
        else:
            col_colors[col] = ''  # No color if it doesn't match any suffix

    # Style function for each column
    def highlight(col):
        color = col_colors.get(col.name, '')
        return [f'background-color: {color}'] * len(col)

    return df.style.apply(highlight, axis=0)


def get_OI_volume_table(symbol):
    df = read_OI_volume()
    df_filtered = df[df['symbol'] == symbol].copy()

    if df_filtered.empty:
        return  # Do nothing

    df_filtered.reset_index(drop=True, inplace=True)
    df_filtered.index += 1  # Make index start from 1
    styled_df = style_OI_column_groups(df_filtered)
    st.markdown("#### OI & Volume")
    st.dataframe(styled_df, height=600)

#####
#####

#################################################################################################
def get_terminal_date(contract: str) -> datetime:
    """
    Given a contract string like "Jun25", return the day before the 1st of that month.
    Compatible with pandas datetime format.
    """
    month_str = contract[:3]
    year_suffix = contract[3:]
    
    # Convert to numeric month and full year
    month_number = datetime.strptime(month_str, "%b").month
    year_full = 2000 + int(year_suffix)
    
    # First of the contract month
    first_of_month = datetime(year_full, month_number, 1)
    
    # Return the previous day
    return first_of_month - timedelta(days=1)

def get_terminal_OI(symbol, months, years, forwards):
    dfs = read_dfs(symbol)
    
    def process_contract(month, year):
        contract = f"{month}{year}"
        if contract in forwards:
            return None

        sheet = f"{symbol}_{month}"
        if sheet not in dfs:
            return None

        df = dfs[sheet]
        df["Date"] = pd.to_datetime(df["Date"])
        df_contract = df[df["contract"] == contract].copy()
        if df_contract.empty:
            return None

        # Step: Apply cutoff date filter
        month_num = datetime.strptime(month, "%b").month  # e.g., 'Jul' -> 7
        cutoff_date = datetime(2000 + year, month_num, 1) - timedelta(days=1)
        df_contract = df_contract[df_contract["Date"] <= cutoff_date]
        if df_contract.empty:
            return None

        df_contract["n_trading_day"] = 0
        df_contract["contract_month"] = month
        df_contract["year"] = 2000 + year
        return df_contract.tail(1)


    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(process_contract, month, year)
            for year in years for month in months
        ]
        results = [f.result() for f in futures if f.result() is not None]

    if results:
        df = pd.concat(results, ignore_index=True)
        df = df.sort_values("Date").reset_index(drop=True)
    else:
        df = pd.DataFrame()

    return df

def get_forward_today_OI(symbol, months, years, forwards, suffix="OI"):
    dfs = read_dfs(symbol, suffix)
    def process_forward(month, year):
        contract = f"{month}{year}"
        if contract not in forwards:
            return None

        sheet = f"{symbol}_{month}"
        if sheet not in dfs:
            return None

        terminal_date = get_terminal_date(contract)
        df = dfs[sheet]
        df["Date"] = pd.to_datetime(df["Date"])
        df_contract = df[df["contract"] == contract].copy()

        if df_contract.empty:
            return None

        df_contract["contract_month"] = month
        df_contract["year"] = 2000 + year
        df_contract["n_trading_day"] = df_contract["Date"].apply(
            lambda d: np.busday_count(terminal_date.date(), d.date())
        )
        return df_contract.tail(1)

    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(process_forward, month, year)
            for year in years for month in months
        ]
        results = [f.result() for f in futures if f.result() is not None]

    if results:
        df = pd.concat(results, ignore_index=True)
    else:
        df = pd.DataFrame()

    return df


def get_aggregated_terminal_OI(symbols, months, years, forwards, conv_factor_map):
    """
    Aggregates terminal OI for multiple symbols.
    - OI is summed
    - n_trading_day is averaged and rounded
    - symbol column is replaced with 'SYM1+SYM2+...'
    """
    all_dfs = []

    if len(symbols) == 1:
        symbol = symbols[0]
        df = get_terminal_OI(symbol, months, years, forwards)
        all_dfs.append(df)

    else:
        for symbol in symbols:
            cf = conv_factor_map[symbol]
            df = get_terminal_OI(symbol, months, years, forwards)
            df['OI'] = (df['OI'].astype(float) * cf).round().astype('Int64')
            all_dfs.append(df)

    # Base merge keys
    base_df = all_dfs[0][["contract", "Date", "contract_month", "year"]].copy()

    for i, df in enumerate(all_dfs):
        df_subset = df[["contract", "Date", "contract_month", "year", "OI", "n_trading_day"]].copy()
        df_subset = df_subset.rename(columns={
            "OI": f"OI_{i}",
            "n_trading_day": f"n_day_{i}"
        })
        base_df = base_df.merge(df_subset, on=["contract", "Date", "contract_month", "year"], how="inner")

    # Aggregate columns
    oi_cols = [col for col in base_df.columns if col.startswith("OI_")]
    n_day_cols = [col for col in base_df.columns if col.startswith("n_day_")]

    base_df["OI"] = base_df[oi_cols].sum(axis=1)
    base_df["n_trading_day"] = 0

    # Clean up and finalize
    base_df.drop(columns=oi_cols + n_day_cols, inplace=True)
    base_df["symbol"] = "+".join(symbols)

    # Reorder
    base_df = base_df[["Date", "OI", "symbol", "contract", "n_trading_day", "contract_month", "year"]]

    return base_df

def get_aggregated_forward_today_OI(symbols, months, years, forwards, conv_factor_map):
    """
    Aggregates forward OI for multiple symbols.
    - OI is summed
    - n_trading_day is averaged and rounded
    - symbol column is replaced with 'SYM1+SYM2+...'
    """
    all_dfs = []

    if len(symbols) == 1:
        symbol = symbols[0]
        df = get_forward_today_OI(symbol, months, years, forwards)
        all_dfs.append(df)

    else:
        for symbol in symbols:
            cf = conv_factor_map[symbol]
            df = get_forward_today_OI(symbol, months, years, forwards)
            df['OI'] = (df['OI'].astype(float) * cf).round().astype('Int64')
            all_dfs.append(df)

    # Start with base keys
    base_df = all_dfs[0][["contract", "Date", "contract_month", "year"]].copy()

    for i, df in enumerate(all_dfs):
        df_subset = df[["contract", "Date", "contract_month", "year", "OI", "n_trading_day"]].copy()
        df_subset = df_subset.rename(columns={
            "OI": f"OI_{i}",
            "n_trading_day": f"n_day_{i}"
        })
        base_df = base_df.merge(df_subset, on=["contract", "Date", "contract_month", "year"], how="inner")

    # Sum OI and average n_trading_day
    oi_cols = [col for col in base_df.columns if col.startswith("OI_")]
    n_day_cols = [col for col in base_df.columns if col.startswith("n_day_")]

    base_df["OI"] = base_df[oi_cols].sum(axis=1)
    base_df["n_trading_day"] = base_df[n_day_cols].max(axis=1)
    # Final cleanup
    base_df.drop(columns=oi_cols + n_day_cols, inplace=True)
    base_df["symbol"] = "+".join(symbols)

    # Reorder columns
    base_df = base_df[["Date", "OI", "symbol", "contract", "n_trading_day", "contract_month", "year"]]

    return base_df

def get_all_OI(symbols, months, years, forwards, conv_factor_map):
    """
    Combines terminal and forward OI into a single DataFrame.
    Keeps None/NaN values, but ensures numbers are stored as integers.
    """
    df_terminal = get_aggregated_terminal_OI(symbols, months, years, forwards, conv_factor_map)
    df_forward = get_aggregated_forward_today_OI(symbols, months, years, forwards, conv_factor_map)

    if df_terminal.empty and df_forward.empty:
        return pd.DataFrame()

    combined_df = pd.concat([df_terminal, df_forward], ignore_index=True)

    # Convert numeric columns to nullable Int64 (keeps None/NaN)
    for col in combined_df.columns:
        if pd.api.types.is_numeric_dtype(combined_df[col]):
            combined_df[col] = combined_df[col].astype("Int64")

    return combined_df

def get_n_day_OI(symbol, months, years, forwards, cf, suffix="OI"):
    """
    Combines terminal and forward OI into a single DataFrame.
    """
    df_forward = get_forward_today_OI(symbol, months, years, forwards, suffix)

    n_trading_day_dct = (
        df_forward
        .groupby("contract_month")["n_trading_day"]
        .apply(lambda x: tuple(x))  # Will return a tuple even if there's only one value
        .to_dict()
    )

    dfs = read_dfs(symbol, suffix)
    
    contract_lst = []
    for year in years:
        for month in months:
            contract = f"{month}{year}"
            
            forward_25 = [c for c in forwards if c.endswith("25")]
            forward_26 = [c for c in forwards if c.endswith("26")]

            if contract in forward_26:
                continue
            
            sheet = f"{symbol}_{month}"
            if sheet not in dfs:
                continue

            terminal_date = get_terminal_date(contract)
            df = dfs[sheet]
            df["Date"] = pd.to_datetime(df["Date"])
            df_contract = df[df["contract"] == contract].copy()
            df_contract["n_trading_day"] = df_contract["Date"].apply(
                lambda d: np.busday_count(terminal_date.date(), d.date()))
            df_contract["contract_month"] = month
            df_contract["year"] = 2000+year

            days = n_trading_day_dct[month]  # tuple of 1 or 2 days
            if contract in forward_25 and len(days) > 1:
                days_to_do = days[1:2]   # only the second element
            else:
                days_to_do = days        # 1-element or both
        
            for n_trading_day in days_to_do:
                df_nth_day = df_contract[df_contract["n_trading_day"] == n_trading_day]
                if not df_nth_day.empty:
                    contract_lst.append(df_nth_day)

    df = pd.concat(contract_lst, ignore_index=True)

    combined_df = pd.concat([df, df_forward], ignore_index=True)
    combined_df = combined_df.sort_values("Date", ascending=False).reset_index(drop=True)
    if suffix == 'OI':
        combined_df['OI'] = (combined_df['OI'].astype(float) * cf).round().astype('Int64')
        # combined_df['OI'] = combined_df['OI'] * cf
    return combined_df

def get_combined_n_day_OI(symbols, months, years, forwards, conv_factor_map):
    from functools import reduce

    df_list = []

    if len(symbols) == 1:
        symbol = symbols[0]
        df = get_n_day_OI(symbol, months, years, forwards, 1)
        df = df.drop(columns=["Date", "symbol"])
        df = df.rename(columns={"OI": f"OI_{symbol}"})  # Rename OI per symbol
        df_list.append(df)

    else:
        for symbol in symbols:
            cf = conv_factor_map[symbol]
            df = get_n_day_OI(symbol, months, years, forwards, cf)
            df = df.drop(columns=["Date", "symbol"])
            df = df.rename(columns={"OI": f"OI_{symbol}"})  # Rename OI per symbol
            df_list.append(df)

    join_cols = ["contract", "n_trading_day", "contract_month", "year"]

    combined_df = reduce(
        lambda left, right: pd.merge(left, right, on=join_cols),
        df_list
    )

    # Sum all renamed OI columns
    oi_cols = [col for col in combined_df.columns if col.startswith("OI_")]
    combined_df["OI"] = combined_df[oi_cols].sum(axis=1)

    # Drop individual OI_ columns
    combined_df = combined_df.drop(columns=oi_cols)

    # Set symbol column to combined string
    combined_df["symbol"] = " + ".join(symbols)

    return combined_df

######################################################################################################
@st.cache_data
def get_pivot_table(df, suffix="OI"):
    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    df['contract_month'] = pd.Categorical(df['contract_month'], categories=month_order, ordered=True)
    
    def format_number(x):
        if pd.isna(x):
            return None
        elif isinstance(x, (int, float)):
            # If integer, return as int; otherwise, format to 2 decimal places and strip trailing zeros
            return int(x) if x == int(x) else f"{x:.2f}".rstrip('0').rstrip('.')
        return x  # fallback

    def format_oi(series):
        values = list(series)
        values = [format_number(v) for v in values if pd.notna(v)]
        
        if len(values) == 1:
            return values[0]
        elif len(values) >= 2:
            return f"{values[0]} ({values[1]})"
        else:
            return None


    pivot = pd.pivot_table(
        df,
        index='contract_month',
        columns='year',
        values=suffix,
        aggfunc=format_oi
    )

    pivot = pivot.sort_index()
    return pivot

def highlight_forward(val, row, col):
    """Returns light yellow background if the cell is a forward contract."""
    light_yellow = "background-color: #FFFFE0"  # very light yellow
    if col == 2026:
        return light_yellow
    if col == 2025 and row in ["Oct", "Nov", "Dec"]:
        return light_yellow
    return ""

def style_forward_cells(pivot_df):
    return pivot_df.style.apply(lambda row: [
        highlight_forward(row[col], row.name, col) if not pd.isna(row[col]) else ""
        for col in pivot_df.columns
    ], axis=1)

def plot_forwards_combined(symbols, forwards, conv_factor_map):
    all_contract_data = {}

    for symbol in symbols:
        dfs = read_dfs(symbol)

        for contract in forwards:
            month = contract[:3]
            sheet = f"{symbol}_{month}"
            if sheet not in dfs:
                continue

            df = dfs[sheet]
            df["Date"] = pd.to_datetime(df["Date"])
            df_contract = df[df["contract"] == contract].copy()

            if not df_contract.empty:
                latest_date = df_contract["Date"].max()
                one_year_ago = latest_date - pd.DateOffset(years=1)
                df_contract = df_contract[df_contract["Date"] >= one_year_ago]

                if len(symbols) > 1:
                    cf = conv_factor_map[symbol]
                    df_contract['OI'] = (df_contract['OI'].astype(float) * cf).round().astype('Int64')

                # Aggregate into all_contract_data
                if contract not in all_contract_data:
                    all_contract_data[contract] = df_contract[["Date", "OI"]].copy()
                else:
                    all_contract_data[contract] = pd.merge(
                        all_contract_data[contract],
                        df_contract[["Date", "OI"]],
                        on="Date",
                        how="outer",
                        suffixes=('', '_dup')
                    )

    # Sum OI across symbols for each contract
    fig = go.Figure()
    for contract, df_combined in all_contract_data.items():
        # Sum all OI columns (some may be OI_dup, OI_dup1, etc.)
        oi_cols = [col for col in df_combined.columns if col.startswith("OI")]
        df_combined["OI_sum"] = df_combined[oi_cols].sum(axis=1)

        df_combined = df_combined.sort_values("Date")

        fig.add_trace(go.Scatter(
            x=df_combined["Date"],
            y=df_combined["OI_sum"],
            mode='lines',
            name=contract
        ))

    symbol_label = " + ".join(symbols)
    fig.update_layout(
        title=f"[{symbol_label}] Forward Contracts OI",
        xaxis_title="Date",
        yaxis_title="Open Interest (OI)",
        legend_title="Contracts",
        height=600,
        width=1000
    )

    st.plotly_chart(fig, use_container_width=True)

#################################################################################################
#################################################################################################
def construct_prompt_mth_rolling_df(symbol):
    dfs = read_dfs(symbol)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    years = [25]

    contract_lst = []

    for year in years:
        for month in months:
            contract = f"{month}{year}"
            if contract in FORWARD_CONTRACTS_TO_SKIP:
                continue
            sheet = f"{symbol}_{month}"
            if sheet not in dfs:
                continue

            df = dfs[sheet]
            df["Date"] = pd.to_datetime(df["Date"])
            df_contract = df[df["contract"] == contract].copy()

            if not df_contract.empty:
                last_date = df_contract["Date"].max()
                last_year = last_date.year
                last_month = last_date.month

                df_contract = df_contract[
                    (df_contract["Date"].dt.year == last_year) &
                    (df_contract["Date"].dt.month == last_month)
                ]

                if not df_contract.empty:
                    contract_lst.append(df_contract)

    df = pd.concat(contract_lst, ignore_index=True)
    df = df.sort_values("Date").reset_index(drop=True)

    #########################################################################################################
    # Group by contract and compute average OI
    df_grouped = df.groupby("contract", as_index=False)["OI"].mean().rename(columns={"OI": "avg_OI"})
    month_map = {month: index for index, month in enumerate(calendar.month_abbr) if month}
    
    # Function to convert 'Jan24' to datetime (e.g., 2024-01-01)
    def contract_to_date(contract):
        try:
            month_str = contract[:3]
            year_str = contract[3:]
            month = month_map[month_str]
            year = int("20" + year_str)  # Assumes 2000s
            return datetime(year, month, 1)
        except:
            return pd.NaT
    
    # Create a sort key column
    df_grouped["contract_date"] = df_grouped["contract"].apply(contract_to_date)
    
    # Sort by contract_date
    df_grouped = df_grouped.sort_values("contract_date").drop(columns=["contract_date"]).reset_index(drop=True)
        
    # Shift by 1 so that each contract gets the average of the *previous 3* contracts
    df_grouped["3m_avg_OI"] = df_grouped["avg_OI"].shift(1).rolling(window=3).mean()

    # Left join avg_OI and 3m_avg_OI back to original df
    df_1 = df.merge(df_grouped, on="contract", how="left")
    df_1["pct_from_avg"] = (
        100*(df_1["OI"] - df_1["3m_avg_OI"]) / df_1["3m_avg_OI"]
    ).round(1)
    return df_1

import concurrent.futures
def combined_oi_dfs(symbols):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Map symbols to construct_prompt_mth_rolling_df in parallel
        dfs = list(executor.map(construct_prompt_mth_rolling_df, symbols))
    
    df_list = []
    for df_oi, symbol in zip(dfs, symbols):
        df_oi_1 = df_oi.rename(columns={
            'OI': f'{symbol}_OI',
            'avg_OI': f'{symbol}_avg_OI',
            '3m_avg_OI': f'{symbol}_3m_avg_OI',
            'pct_from_avg': f'{symbol}_pct_from_avg',
        })
        df_oi_1 = df_oi_1.drop(columns='symbol', errors='ignore')  # 'symbol' column might not exist
        df_list.append(df_oi_1)

    # Merge all dataframes on 'Date' and 'contract' with inner join
    combined_df = reduce(lambda left, right: pd.merge(left, right, on=['Date', 'contract'], how='inner'), df_list)
    return combined_df


def calc_main_product_oi(main_product, symbols):
    combined_df = combined_oi_dfs(symbols)
    
    oi_cols = [col for col in combined_df.columns if col.endswith('_OI') and not col.endswith('avg_OI') and not col.endswith('3m_avg_OI')]
    combined_df[f'{main_product}_OI'] = combined_df[oi_cols].sum(axis=1)

    oi_avg_cols = [col for col in combined_df.columns if col.endswith('3m_avg_OI')]
    combined_df[f'{main_product}_3m_avg_OI'] = combined_df[oi_avg_cols].sum(axis=1, skipna=False)
    combined_df[f'{main_product}_pct_from_avg'] = (
        100*(combined_df[f"{main_product}_OI"] - combined_df[f"{main_product}_3m_avg_OI"]) / combined_df[f"{main_product}_3m_avg_OI"]
    ).round(1)
    return combined_df

####################################################################
import matplotlib.colors as mcolors

def lighten_color(color, amount):
    color_rgb = mcolors.to_rgb(color)
    white = (1, 1, 1)
    blended = tuple((1 - amount) * c + amount * w for c, w in zip(color_rgb, white))
    return mcolors.to_hex(blended)

def color_pct_from_avg(val):
    if val == 0 or pd.isna(val):
        return ""

    max_val = 100  # Adjust depending on your data
    norm_val = min(abs(val) / max_val, 1.0)
    lighten_amt = 1 - norm_val

    if val < 0:
        color = lighten_color("red", lighten_amt)
    else:
        color = lighten_color("#065DDF", lighten_amt)

    return f"background-color: {color}"

@st.cache_data
def create_diffs_heatmap(symbols, name_map):
    combined_df = combined_oi_dfs(symbols)
    today_df = combined_df.tail(1)
    latest_date = pd.to_datetime(today_df['Date'].values[0]).date()
    prompt_contract = today_df['contract'].values[0]

    pct_cols = [col for col in today_df.columns if col.endswith('pct_from_avg')]
    symbols = [col.split('_')[0] for col in pct_cols]

    rows = []
    for sym in symbols:
        row = {
            'symbol': sym,
            'OI': today_df[f"{sym}_OI"].values[0],
            '3m_avg_OI': today_df[f"{sym}_3m_avg_OI"].values[0],
            'pct_from_avg': today_df[f"{sym}_pct_from_avg"].values[0],
        }
        rows.append(row)

    heatmap_data = pd.DataFrame(rows)
    heatmap_data['diff'] = heatmap_data['symbol'].map(lambda x: name_map.get(x, [x])[0])
    heatmap_data['product_fam'] = heatmap_data['symbol'].map(lambda x: name_map.get(x, [None, None])[1])
    heatmap_data['contract'] = prompt_contract
    heatmap_data['OI_date'] = latest_date

     # ── INSERT: initialize the new columns to empty/NaN ────────────────────
    heatmap_data['T-5_OI']  = None
    heatmap_data['T-10_OI'] = None
    heatmap_data['T-20_OI'] = None
    # ─────────────────────────────────────────────────────────────────────────

    # ── LOOP OVER EACH ROW AND FILL IN HISTORICALS ───────────────────────────
    for idx, row in heatmap_data.iterrows():
        sym = row['symbol']
        contract = row['contract']

        # Call your helper that returns a dict of {"T-5_OI":…, "T-10_OI":…, "T-20_OI":…}
        hist_dict = get_historicals_for_contract([sym], contract)

        # Only write back the keys that exist
        if 'T-5_OI'  in hist_dict: heatmap_data.at[idx, 'T-5_OI']  = hist_dict['T-5_OI']
        if 'T-10_OI' in hist_dict: heatmap_data.at[idx, 'T-10_OI'] = hist_dict['T-10_OI']
        if 'T-20_OI' in hist_dict: heatmap_data.at[idx, 'T-20_OI'] = hist_dict['T-20_OI']
    # ─────────────────────────────────────────────────────────────────────────

    heatmap_data = heatmap_data[['diff', 'pct_from_avg', 'OI', 'T-5_OI', 'T-10_OI', 'T-20_OI', '3m_avg_OI', 'symbol', 'OI_date', 'contract']]
    heatmap_data = heatmap_data.loc[heatmap_data['pct_from_avg'].abs().sort_values(ascending=False).index].reset_index(drop=True)
    heatmap_data.index = heatmap_data.index + 1

    # num_rows = heatmap_data.shape[0]
    # row_height = 35
    # base_height = 50
    # dynamic_height = base_height + num_rows * row_height

    styled_df = heatmap_data.style.applymap(color_pct_from_avg, subset=["pct_from_avg"]).format({
        'OI': '{:,.0f}',
        '3m_avg_OI': '{:,.0f}',
        'T-5_OI': '{:,.0f}', 
        'T-10_OI': '{:,.0f}', 
        'T-20_OI': '{:,.0f}',
        'pct_from_avg': '{:+.1f}'
    })

    st.dataframe(styled_df, use_container_width=True)

@st.cache_data
def create_main_product_heatmap(dct, product_fam_map_main):
    def process_main_product(main_product, symbols):
        combined_df = calc_main_product_oi(main_product, symbols)
        today_df = combined_df.tail(1)
        latest_date = pd.to_datetime(today_df['Date'].values[0]).date()
        prompt_contract = today_df['contract'].values[0]

        cols = ["Date", "contract", f"{main_product}_OI", f"{main_product}_3m_avg_OI", f"{main_product}_pct_from_avg"]
        today_df_1 = today_df[cols].copy()
        today_df_2 = today_df_1.rename(columns={
            f'{main_product}_OI': 'OI',
            f'{main_product}_3m_avg_OI': '3m_avg_OI',
            f'{main_product}_pct_from_avg': 'pct_from_avg',
        })

        today_df_2['constituents'] = ", ".join(symbols)
        today_df_2['product'] = main_product
        today_df_2['contract'] = prompt_contract
        today_df_2['OI_date'] = latest_date

        # Historical OI values
        hist_dict = get_historicals_for_contract(symbols, prompt_contract)
        for col in ['T-5_OI', 'T-10_OI', 'T-20_OI']:
            today_df_2[col] = hist_dict.get(col)

        return today_df_2

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_main_product, p, s) for p, s in dct.items()]
        df_list = [f.result() for f in futures if f.result() is not None]

    combined_df = pd.concat(df_list, ignore_index=True)
    combined_df['product_fam'] = combined_df['product'].map(product_fam_map_main).fillna(combined_df['product'])

    heatmap_data = combined_df[['product', 'pct_from_avg', 'OI', 'T-5_OI', 'T-10_OI', 'T-20_OI', '3m_avg_OI', 'constituents', 'OI_date', 'contract']]
    heatmap_data = heatmap_data.loc[heatmap_data['pct_from_avg'].abs().sort_values(ascending=False).index].reset_index(drop=True)
    heatmap_data.index = heatmap_data.index + 1

    styled_df = heatmap_data.style.applymap(color_pct_from_avg, subset=["pct_from_avg"]).format({
        'OI': '{:,.0f}',
        '3m_avg_OI': '{:,.0f}',
        'T-5_OI': '{:,.0f}', 
        'T-10_OI': '{:,.0f}', 
        'T-20_OI': '{:,.0f}',
        'pct_from_avg': '{:+.1f}'
    })

    st.dataframe(styled_df, use_container_width=True)


@st.cache_data
def get_historicals_for_contract(symbols, contract):
    result = {"T-5_OI": 0, "T-10_OI": 0, "T-20_OI": 0}
    for symbol in symbols:
        dfs = read_dfs(symbol)
        month = contract[:3]
        sheet = f"{symbol}_{month}"

        if sheet not in dfs:
            continue

        df = dfs[sheet]
        df_contract = df[df["contract"] == contract].copy()
        result["T-5_OI"] += df_contract.iloc[-6]["OI"]
        result["T-10_OI"] += df_contract.iloc[-11]["OI"]
        result["T-20_OI"] += df_contract.iloc[-21]["OI"]

    return result