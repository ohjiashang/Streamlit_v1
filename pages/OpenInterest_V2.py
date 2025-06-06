import streamlit as st
import warnings
warnings.filterwarnings("ignore")
from utils.oi_constants import OI_V2_SYMBOLS, OI_V2_FORWARDS, OI_V2_MONTHS, OI_V2_YEARS
from utils.oi_daily import get_combined_n_day_OI, get_all_OI, get_pivot_table, style_forward_cells, plot_forwards_combined

st.set_page_config(layout="wide")
st.title("Open Interest")

selected_symbols = st.multiselect(
    "Select Product Code(s):",
    options=OI_V2_SYMBOLS,
    default=[OI_V2_SYMBOLS[0]]
)

# Only run the rest if at least one symbol is selected
if selected_symbols:
    df_n_day = get_combined_n_day_OI(selected_symbols, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS)
    pivot_n_day = get_pivot_table(df_n_day)
    styled_n_day = style_forward_cells(pivot_n_day)

    df_terminal = get_all_OI(selected_symbols, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS)
    pivot_terminal = get_pivot_table(df_terminal)
    styled_terminal = style_forward_cells(pivot_terminal)
    latest_date = df_terminal["Date"].max()

    st.markdown(f"*OI Date: {latest_date.strftime('%Y-%m-%d')}*")

    col1, spacer, col2 = st.columns([1, 0.05, 1])

    with col1:
        st.markdown("#### Historical Nth-Day OI")
        st.dataframe(styled_n_day, height=460)

    with col2:
        st.markdown("#### Historical Terminal OI")
        st.dataframe(styled_terminal, height=460)

    plot_forwards_combined(selected_symbols, OI_V2_FORWARDS)

else:
    st.warning("Please select at least one product to display data")