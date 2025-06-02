import streamlit as st
import pandas as pd
from utils.oi_constants import name_map, product_fam_map_main
from utils.oi_daily import create_diffs_heatmap, create_main_product_heatmap
import warnings
warnings.filterwarnings("ignore")

def render(dct, symbols):
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("###### Products")
        create_main_product_heatmap(dct, product_fam_map_main)
        st.markdown("###### Diffs")
        create_diffs_heatmap(symbols, name_map)
