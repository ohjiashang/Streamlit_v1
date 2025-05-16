from utils.constants import DIFFS_MAP, MONTHS_SCENARIO_MAP
from utils.month_offsets import get_price_series
from utils.plot_live import add_rolling_cols
import pandas as pd
import streamlit as st
import matplotlib.colors as mcolors

@st.cache_data
def get_table(diffs_to_track_map, sheet_name):
    months_m1_lst = ["Mar", "Jun", "Sep", "Dec"]
    years = [24, 25]
    rows = []  # Step 1: initialize a list to store row dicts
    
    for diff, values in diffs_to_track_map.items():
        product_fam = values[0]
        window = values[1]
        scenario = values[2]
        window_str = f"{window}m"

        diff_w_pf = '[' + product_fam + '] ' + diff
        months_scenario = MONTHS_SCENARIO_MAP[scenario]
        if scenario == 'Box':
            diff_scenario = DIFFS_MAP[diff_w_pf][1]

        elif scenario == "Outright":
            diff_scenario_og = DIFFS_MAP[diff_w_pf][1]
            diff_scenario = (f"{diff_scenario_og[0]}+{diff_scenario_og[0]}", diff_scenario_og[1])

        else:
            diff_scenario = DIFFS_MAP[diff_w_pf][0]

        df_single_diff = get_price_series(diff_scenario, months_scenario, months_m1_lst, years)
        df_single_diff_1 = add_rolling_cols(df_single_diff, window_str, 1)

        price_col = 'exit_norm_price'
        last_row = df_single_diff_1.iloc[-1]
        # last_date = last_row['Date']
        last_price = round(last_row[price_col], 2)
        last_median = round(last_row['rolling_median'], 2)
        last_std = round(last_row['rolling_std'], 2)
        last_upper = round(last_row['upper_bound'], 2)
        last_lower = round(last_row['lower_bound'], 2)
        num_sd = round((last_price - last_median) / last_std, 2) if last_std != 0 else 0

        if scenario == "Box":
            last_contract = last_row['entry_contract']
        else:
            last_contract = last_row['entry_contract'][:5]

         # Step 2: collect row data as a dict
        row = {
            'diff': diff,
            'contract': last_contract.replace('-', '/'),
            'num_sd': num_sd,
            'price': last_price,
            'median': last_median,
            'sd': last_std,
            'window': window_str,
            'rolling_window': window,
            'product_fam': product_fam,
        }
        rows.append(row)

    # Step 3: convert to DataFrame
    result_df = pd.DataFrame(rows)
    result_df = result_df.reindex(result_df["num_sd"].abs().sort_values(ascending=False).index).reset_index(drop=True)

    # static_df = pd.read_excel('data/ContractRolls_1-4sd_V3.xlsx', sheet_name="scenarios_Boxes_50")
    static_df = pd.read_excel('data/ContractRolls_1-4sd_V3.xlsx', sheet_name=sheet_name)
    columns_needed = ['diff', 'rolling_window', 'entry_sd', 'avg_yearly_returns', 'ratio', 'cv']
    filtered_df = static_df[columns_needed]
    matching_df = filtered_df.merge(result_df[['diff', 'rolling_window']], on=['diff', 'rolling_window'], how='inner')
    result_df = result_df.merge(matching_df[['diff', 'avg_yearly_returns', 'ratio', 'cv', 'entry_sd']], on='diff', how='left')

    result_df = result_df.drop(columns='rolling_window')

    col_order = [
        'diff','contract',
        'num_sd',
        'price',
        'entry_sd',
        'avg_yearly_returns', 'ratio', 'cv',
        'median', 'sd',
        'window',
        'product_fam'
    ]
    result_df = result_df[col_order]
    result_df['entry_sd'] = result_df['entry_sd'].astype(str) + 'sd'
    result_df.index = result_df.index + 1

    num_rows = result_df.shape[0]
    row_height = 35
    base_height = 50
    dynamic_height = base_height + num_rows * row_height

    def lighten_color(color, amount):
        """
        Blend a color with white to lighten it.
        `amount` = 0 → original color
        `amount` = 1 → white
        """
        color_rgb = mcolors.to_rgb(color)
        white = (1, 1, 1)
        blended = tuple((1 - amount) * c + amount * w for c, w in zip(color_rgb, white))
        return mcolors.to_hex(blended)

    def color_num_sd(val):
        if val == 0:
            return ""

        max_val = 5  # max |num_sd| expected for normalization
        norm_val = min(abs(val) / max_val, 1.0)  # clamp between 0 and 1

        # Lighten more when value is small (i.e. closer to 1)
        lighten_amt = 1 - norm_val  # inverse: larger abs → darker (less white)

        if val > 0:
            color = lighten_color("red", lighten_amt)
        else:
            color = lighten_color("blue", lighten_amt)

        return f"background-color: {color}"

    styled_df = result_df.style.applymap(color_num_sd, subset=["num_sd"]).format({
        col: "{:.2f}" for col in result_df.select_dtypes(include=["float"]).columns
    })

    st.dataframe(styled_df, height=dynamic_height, width=1500)