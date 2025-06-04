import streamlit as st
from tabs import OI_live_tab
import warnings
# warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
warnings.filterwarnings("ignore")
from utils.oi_constants import OI_V2_SYMBOLS, OI_V2_FORWARDS, OI_V2_MONTHS, OI_V2_YEARS
from utils.oi_daily import get_all_OI, get_n_day_OI, get_pivot_table, style_forward_cells
import pandas as pd


st.set_page_config(layout="wide")
st.title("Open Interest")

# Create dropdown
selected_symbol = st.selectbox("Select Product Code:", OI_V2_SYMBOLS)

########################################################################################
df_n_day = get_n_day_OI(selected_symbol, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS)
latest_date = df_n_day["Date"].max()
pivot_n_day = get_pivot_table(df_n_day)
styled_n_day = style_forward_cells(pivot_n_day)

df_terminal = get_all_OI(selected_symbol, OI_V2_MONTHS, OI_V2_YEARS, OI_V2_FORWARDS)
pivot_terminal = get_pivot_table(df_terminal)
styled_terminal = style_forward_cells(pivot_terminal)
########################################################################################

# st.write("OI Date:", latest_date.strftime("%Y-%m-%d"))
st.markdown(f"*OI Date: {latest_date.strftime('%Y-%m-%d')}*")

# Create two columns
col1, spacer, col2 = st.columns([1, 0.05, 1])

# Add a subtitle to each column
with col1:
    st.markdown("#### Historical Nth-Day OI")
    st.dataframe(styled_n_day, height=460)

with col2:
    st.markdown("#### Historical Terminal OI")
    st.dataframe(styled_terminal, height=460)