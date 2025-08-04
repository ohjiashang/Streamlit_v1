import streamlit as st
from tabs import OI_live_tab
import warnings
# warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
warnings.filterwarnings("ignore")
from utils.oi_constants import dct, symbols, dist_dct, dist_symbols

st.set_page_config(layout="wide")
st.title("Open Interest")

tab1, tab2 = st.tabs(["Lights", "Dist"])

with tab1:
    OI_live_tab.render(dct, symbols)

with tab2:
    OI_live_tab.render(dist_dct, dist_symbols)



