import pandas as pd
import re
import urllib.parse
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

# Global month dictionary
month_dct = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

def get_start_end_dates(contract, num_lookback_months=5):
    year = 2000 + int(contract[-2:])
    month = month_dct[contract[:3]]
    start_date = pd.Timestamp(year, month, 1) - pd.DateOffset(months=num_lookback_months)
    end_date = pd.Timestamp(year, month, 1) - pd.DateOffset(days=1) - pd.offsets.MonthEnd(2)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

@lru_cache(maxsize=100)
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

def calculate_outright(diff, contract_m1, month_scenario):
    contracts_m1_to_m4 = get_m1_to_m4_contracts(contract_m1)
    start_date, end_date = get_start_end_dates(contract_m1)
    contract = contracts_m1_to_m4[month_scenario - 1]
    target_month = contract[:3]

    tokens = re.split(r'(\+|-)', diff)
    operators = [t for t in tokens if t in ['+', '-']]
    products = [t.strip() for t in tokens if t not in ['+', '-']]

    # Collect all product data in one DataFrame
    all_dfs = []
    for i, product in enumerate(products):
        folder = "Symbols"
        filename = f"{product}_18m.xlsx"
        encoded_filename = urllib.parse.quote(filename)
        url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
        df = read_excel_cached(url, f"{product}_{target_month}")
        df = df[df['contract'] == contract][['Date', 'price']].rename(columns={'price': f'price_{i+1}'})
        all_dfs.append(df)

    # Merge all DataFrames on Date
    if not all_dfs:
        return pd.DataFrame(columns=["Date", "price", "diff", "contract"])
    
    final_df = all_dfs[0]
    for df in all_dfs[1:]:
        final_df = final_df.merge(df, on='Date', how='inner')

    final_df = final_df[(final_df['Date'] >= start_date) & (final_df['Date'] <= end_date)]
    if final_df.empty:
        return pd.DataFrame(columns=["Date", "price", "diff", "contract"])

    # Apply diff formula
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

def calculate_diff(diff_scenario_tup, contract_m1, month_scenario_tup):
    diff_1, diff_2 = diff_scenario_tup[0], diff_scenario_tup[1]
    month_scenario_1, month_scenario_2 = month_scenario_tup[0], month_scenario_tup[1]

    # First leg
    df_1 = calculate_outright(diff_1, contract_m1, month_scenario_1)
    df_1 = df_1.rename(columns={
        "Date": "Date",
        "price": "price_1",
        "diff": "diff_1",
        "contract": "contract_1"
    })

    # Second leg
    df_2 = calculate_outright(diff_2, contract_m1, month_scenario_2)
    df_2 = df_2.rename(columns={
        "Date": "Date",
        "price": "price_2",
        "diff": "diff_2",
        "contract": "contract_2"
    })

    df_3 = df_1.merge(df_2, how='inner', on=['Date'])
    df_3['m1_contract'] = contract_m1
    df_3['m1'] = contract_m1[:3]
    df_3['diffs_scenario'] = [diff_scenario_tup] * len(df_3)
    df_3['mths_scenario'] = [month_scenario_tup] * len(df_3)
    df_3['price'] = df_3['price_1'] - df_3['price_2']
    
    return df_3

def process_offset_mths(diff_scenario, diff_name, months_scenario):
    month1, month2 = months_scenario[0], months_scenario[1]
    sheet_name = f"m{month1-1}m{month2-1}"
    months_m1_lst = ["Mar", "Jun", "Sep", "Dec"]
    years = [16, 17, 18, 19, 20, 21, 22, 23, 24, 25]

    def process_contract(year, month_m1):
        contract_m1 = month_m1 + str(year)
        return calculate_diff(diff_scenario, contract_m1, months_scenario)

    dfs = []
    last_price = None
    last_norm = 0

    # Parallel processing
    with ThreadPoolExecutor() as executor:
        tasks = [executor.submit(process_contract, year, month_m1)
                 for year in reversed(years) for month_m1 in reversed(months_m1_lst)]
        for future in tasks:
            df_contract = future.result()
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

    # df_new = pd.concat(reversed(dfs), ignore_index=True)
    # df_new['contract'] = df_new['contract_1'].astype(str) + "-" + df_new['contract_2'].astype(str)
    # df_new['contract_month'] = df_new['contract_1'].astype(str).str[:3] + "-" + df_new['contract_2'].astype(str).str[:3]

    # cols_to_keep = ['Date', 'diff_1', 'diff_2', 'mths_scenario', 'contract', 'contract_month', 'price', 'norm_value', 'norm_price']
    # df_entry = df_new.drop_duplicates(subset="Date", keep="last")[cols_to_keep]
    # df_exit = df_new.drop_duplicates(subset="Date", keep="first")[cols_to_keep]
    
    # cols_to_rename = ['contract', 'contract_month', 'price', 'norm_value', 'norm_price']
    # df_entry = df_entry.rename(columns={col: f"entry_{col}" for col in cols_to_rename})
    # df_exit = df_exit.rename(columns={col: f"exit_{col}" for col in cols_to_rename})
    
    # cols_to_merge = ['Date', 'diff_1', 'diff_2', 'mths_scenario']
    # df_final = df_entry.merge(df_exit, on=cols_to_merge, how='left')

    # df_final['mths_scenario'] = sheet_name
    # df_final['diff'] = diff_name

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


# def get_start_end_dates(contract, num_lookback_months=5):
#     month_dct = {
#         "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
#         "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
#         "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
#     }
#     year = 2000 + int(contract[-2:])
#     month = month_dct[contract[:3]]

#     start_date = pd.Timestamp(year, month, 1) - pd.DateOffset(months=num_lookback_months)
#     end_date = pd.Timestamp(year, month, 1) - pd.DateOffset(days=1) - pd.offsets.MonthEnd(2)
    
#     start_date = pd.to_datetime(start_date).strftime('%Y-%m-%d')
#     end_date = pd.to_datetime(end_date).strftime('%Y-%m-%d')
#     return start_date, end_date


# def calculate_outright(diff, contract_m1, month_scenario):

#     def get_m1_to_m4_contracts(contract_m1):
#         # Dictionary to map month names to their corresponding numbers
#         month_dct = {
#             "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
#             "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
#             "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
#         }
        
#         # Extract the month and year from contract_m1
#         month, year = contract_m1[:3], int(contract_m1[3:])
#         start_month = month_dct[month]
        
#         # Create a list to store the contracts
#         contracts = []
        
#         for i in range(4):
#             # Calculate the new month and year
#             new_month = (start_month + i - 1) % 12 + 1
#             new_year = year + (start_month + i - 1) // 12
            
#             # Find the month name corresponding to the new month
#             new_month_name = [k for k, v in month_dct.items() if v == new_month][0]
            
#             # Append the contract to the list
#             contracts.append(f"{new_month_name}{new_year}")
        
#         return contracts

#     start_date, end_date = get_start_end_dates(contract_m1)
#     contracts_m1_to_m4 = get_m1_to_m4_contracts(contract_m1)
    
#     contract = contracts_m1_to_m4[month_scenario - 1]
#     target_month = contract[:3]

#     # Tokenize the diff formula
#     tokens = re.split(r'(\+|-)', diff)

#     operators = []
#     products = []

#     # Separate operators and products
#     for token in tokens:
#         token = token.strip()
#         if token == '+' or token == '-':
#             operators.append(token)
#         else:
#             products.append(token)

#     # Initialize the final DataFrame to None
#     final_df = None

#     for i, product in enumerate(products):
#         # # Read the product's Excel file
#         # directory = r"C:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\Notebooks\Streamlit_Notebooks\Data - Copy"
#         # file_name = os.path.join(directory, f"{product}_18m_31Mar2025.xlsx")

#         folder = "Symbols"
#         filename = f"{product}_18m.xlsx"
#         encoded_filename = urllib.parse.quote(filename)
#         url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
        
#         df = pd.read_excel(url, sheet_name=f"{product}_{target_month}")
#         df = df[df['contract'] == contract].sort_values("Date").reset_index(drop=True)

#         df_match = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
#         if df_match.empty:
#             return pd.DataFrame(columns=["Date", "price", "diff", "contract"])

#         idx_start = df_match.index[0]
#         idx_end = df_match.index[-1]

#         df = df.iloc[max(0, idx_start - 2): idx_end].copy()
#         df = df[["Date", "price", "contract"]]

#         if final_df is None:
#             # Initialize final_df with the first product
#             final_df = df.rename(columns={"price": "price_1"})
#         else:
#             # Merge with the next product
#             df = df.rename(columns={"price": f"price_{i+1}"})
#             final_df = pd.merge(final_df, df, on=["Date", "contract"], how="inner")

#     # Calculate the final price based on the operators
#     final_price = final_df[f"price_1"]
#     for i, operator in enumerate(operators):
#         if operator == '+':
#             final_price += final_df[f"price_{i+2}"]
#         elif operator == '-':
#             final_price -= final_df[f"price_{i+2}"]

#     # Add the calculated columns
#     final_df["price"] = final_price
#     final_df["diff"] = diff

#     # Return the final DataFrame
#     return final_df[["Date", "price", "diff", "contract"]]


# def calculate_diff(diff_scenario_tup, contract_m1, month_scenario_tup):
    
#     diff_1, diff_2 = diff_scenario_tup[0], diff_scenario_tup[1]
#     month_scenario_1, month_scenario_2 = month_scenario_tup[0], month_scenario_tup[1]

#     # First leg
#     df_1 = calculate_outright(diff_1, contract_m1, month_scenario_1)
#     df_1 = df_1.rename(columns={
#         "Date": "Date",       # No change here
#         "price": "price_1",   # Rename "price" to "price_1"
#         "diff": "diff_1",     # Rename "diff" to "diff_1"
#         "contract": "contract_1"  # Rename "contract" to "contract_1"
#     })

#     # Second leg
#     df_2 = calculate_outright(diff_2, contract_m1, month_scenario_2)
#     df_2 = df_2.rename(columns={
#         "Date": "Date",       # No change here
#         "price": "price_2",   # Rename "price" to "price_1"
#         "diff": "diff_2",     # Rename "diff" to "diff_1"
#         "contract": "contract_2"  # Rename "contract" to "contract_1"
#     })

#     df_3 = df_1.merge(df_2, how='inner', on=['Date'])
#     df_3['m1_contract'] = contract_m1
#     df_3['m1'] = contract_m1[:3]
#     df_3['diffs_scenario'] = [diff_scenario_tup] * len(df_3) 
#     df_3['mths_scenario'] = [month_scenario_tup] * len(df_3)
#     df_3['price'] = df_3['price_1'] - df_3['price_2']
#     # df_3 = handle_outliers(df_3, 'price')
    
#     # RETURNS ['Date', 'price_1', 'diff_1', 'contract_1', 'price_2', 'diff_2',
#     #    'contract_2', 'm1_contract', 'm1', 'diffs_scenario', 'mths_scenario',
#     #    'price', 'price_cleaned']
#     return df_3


# def process_offset_mths(diff_scenario, diff_name, months_scenario):
#     print("here")
#     month1, month2 = months_scenario[0], months_scenario[1]
#     sheet_name = f"m{month1-1}m{month2-1}"
    
#     months_m1_lst=["Mar", "Jun", "Sep", "Dec"]
#     years=[16, 17, 18, 19, 20, 21, 22, 23, 24, 25]

#     dfs = []
#     last_price = None  # to hold the last 'price' of the previous df
#     last_norm = 0

#     for year in reversed(years):
#         for month_m1 in reversed(months_m1_lst):           
#             contract_m1 = month_m1 + str(year)
#             df_contract = calculate_diff(diff_scenario, contract_m1, months_scenario)

#             if not df_contract.empty:
#                 # Calculate norm_value using last_price
#                 if last_price is not None:
#                     norm_diff = df_contract["price"].iloc[-1] - last_price
#                     last_norm += norm_diff
#                     df_contract["norm_value"] = last_norm
                    
#                 else:
#                     df_contract["norm_value"] = 0.0  # or np.nan if preferred
    
#                 # Update last_price for next loop
#                 last_price = df_contract["price"].iloc[0]
                
#                 df_contract['norm_price'] = df_contract['price'] - df_contract['norm_value']
#                 dfs.append(df_contract)
    
#     df_new = pd.concat(reversed(dfs), ignore_index=True)
#     df_new['contract'] = df_new['contract_1'].astype(str) + "-" + df_new['contract_2'].astype(str)
#     df_new['contract_month'] = df_new['contract_1'].astype(str).str[:3] + "-" + df_new['contract_2'].astype(str).str[:3]

#     cols_to_keep = ['Date', 'diff_1', 'diff_2', 'mths_scenario','contract', 'contract_month', 'price', 'norm_value', 'norm_price']
#     df_entry = df_new.drop_duplicates(subset="Date", keep="last")[cols_to_keep]
#     df_exit = df_new.drop_duplicates(subset="Date", keep="first")[cols_to_keep]
    
#     cols_to_rename = ['contract', 'contract_month', 'price', 'norm_value', 'norm_price']
#     df_entry = df_entry.rename(columns={col: f"entry_{col}" for col in cols_to_rename})
#     df_exit = df_exit.rename(columns={col: f"exit_{col}" for col in cols_to_rename})
    
#     cols_to_merge = ['Date', 'diff_1', 'diff_2', 'mths_scenario']
#     df_final = df_entry.merge(df_exit, on=cols_to_merge, how='left')
    
#     df_final['mths_scenario'] = sheet_name
#     df_final['diff'] = diff_name
#     return df_final
