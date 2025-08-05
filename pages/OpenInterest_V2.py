import streamlit as st
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

# ── Sidebar: scrollable checklist (no search) ──────────────────────────────────
st.sidebar.markdown("### Select Product Code(s):")
selected_symbols = []
for sym in OI_V2_SYMBOLS:
    default = (sym == OI_V2_SYMBOLS[0])
    if st.sidebar.checkbox(sym, value=default, key=f"chk_{sym}"):
        selected_symbols.append(sym)

# ── Main content ────────────────────────────────────────────────────────────────
if selected_symbols:
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

else:
    st.warning("Please select at least one product to display data")