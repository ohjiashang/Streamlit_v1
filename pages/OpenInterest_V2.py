import streamlit as st
from collections import defaultdict
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from utils.oi_constants import OI_V2_SYMBOLS, OI_V2_FORWARDS, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS_MOD
from utils.oi_daily import (
    get_combined_n_day_OI,
    get_all_OI,
    get_pivot_table,
    style_forward_cells,
    plot_forwards_combined, 
    get_n_day_OI,
    get_OI_volume_table
)

st.set_page_config(layout="wide")
st.title("Open Interest")

# ── Sidebar: scrollable checklist ──────────────────────────────────
# Read the Excel file from the data folder
file_path = "data/OI_product_map.xlsx"  # change to your actual filename
df = pd.read_excel(file_path)

# Ensure only needed columns
product_col = 'Label'
symbol_col = 'Symbol'
symbol_desc_col = 'Symbol Description'
df = df[[product_col, symbol_col, symbol_desc_col]].dropna()

# Build product_code_map: product -> list of (symbol, description)
product_code_map = defaultdict(list)
for _, row in df.iterrows():
    product = str(row[product_col]).strip()
    symbol = str(row[symbol_col]).strip()
    desc = str(row[symbol_desc_col]).strip()
    product_code_map[product].append((symbol, desc))

product_code_map = dict(product_code_map)

# --- Step 1: Select product ---
selected_product = st.sidebar.selectbox(
    "Select Product",
    options=list(product_code_map.keys())
)

# st.sidebar.markdown("### Select Product Code(s):")
# --- Step 2: Show checkboxes for symbols with descriptions ---
selected_symbols = []

symbol_desc_list = product_code_map[selected_product]

# Initialize session state for checkboxes if not present
if 'checkbox_states' not in st.session_state:
    st.session_state.checkbox_states = {symbol: False for symbol, _ in symbol_desc_list}

# Determine if all are selected or not
all_selected = all(st.session_state.checkbox_states.get(symbol, False) for symbol, _ in symbol_desc_list)

# Single toggle button text
button_label = "Clear Selection" if all_selected else "Select All"

if st.sidebar.button(button_label):
    new_state = not all_selected
    for symbol, _ in symbol_desc_list:
        st.session_state.checkbox_states[symbol] = new_state

# Show checkboxes using the session state to control defaults
selected_symbols = []
for symbol, desc in symbol_desc_list:
    checked = st.sidebar.checkbox(desc, value=st.session_state.checkbox_states.get(symbol, False), key=f"chk_{symbol}")
    st.session_state.checkbox_states[symbol] = checked
    if checked:
        selected_symbols.append(symbol)

# # st.sidebar.markdown("### Select Product Code(s):")
# for i, (symbol, desc) in enumerate(symbol_desc_list):
#     default = (i == 0)  # First one pre-checked
#     if st.sidebar.checkbox(desc, value=default, key=f"chk_{symbol}"):
#         selected_symbols.append(symbol)

# ── Main content ────────────────────────────────────────────────────────────────
if selected_symbols:
    try:
        df_n_day = get_combined_n_day_OI(selected_symbols, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS)
        pivot_n_day = get_pivot_table(df_n_day)
        styled_n_day = style_forward_cells(pivot_n_day)

        df_terminal = get_all_OI(selected_symbols, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS_MOD)
        pivot_terminal = get_pivot_table(df_terminal)
        styled_terminal = style_forward_cells(pivot_terminal)
        latest_date = df_terminal["Date"].max()

        if len(selected_symbols) == 1:
            s = selected_symbols[0]
            suffix = "price"
            df_prices = get_n_day_OI(s, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS, suffix)
            pivot_prices = get_pivot_table(df_prices, suffix)
            styled_prices = style_forward_cells(pivot_prices)

        ##############################################################################
        st.markdown(f"*OI Date: {latest_date.strftime('%Y-%m-%d')}*")
        st.markdown(f"*Current Selection: {', '.join(selected_symbols)}*")

        col1, spacer, col2 = st.columns([1, 0.05, 1])
        with col1:
            st.markdown("#### Historical Nth-Day OI")
            st.dataframe(styled_n_day, height=460)
            st.markdown("#### Historical Terminal OI")
            st.dataframe(styled_terminal, height=460)

        with col2:
            if len(selected_symbols) == 1:
                st.markdown("#### Historical Nth-Day Prices ($/BBL)")
                st.dataframe(styled_prices, height=460)

        plot_forwards_combined(selected_symbols, OI_V2_FORWARDS)
        if len(selected_symbols) == 1:
            get_OI_volume_table(selected_symbols[0])

    except Exception as e:
        # st.warning(f"An error occurred while loading data: {e}")
        st.warning(f"No data available")

else:
    st.warning("Please select at least one product to display data")