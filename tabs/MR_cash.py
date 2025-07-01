import streamlit as st
import pandas as pd
from utils.constants import CASH, CASH_MAP
from utils.cash import add_rolling_stats, generate_upper_lower_bounds, generate_m1m2_series, plot_prem_disc
import urllib.parse

def render():
    selected_diff = st.selectbox("Select Product:", CASH, key="selected_cash")

    symbol = CASH_MAP[selected_diff][0]
    prem_col = CASH_MAP[selected_diff][1]
    m1m2_col = "m1/m2"
    m2m3_col = "m2/m3"

    day = CASH_MAP[selected_diff][2]
    days_lst = [day]
    sd_entry_lst=[0.5, 1, 1.5, 2]

    folder = "Cash"
    filename = f"{symbol}_OR_full.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"

    df = pd.read_excel(url)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values(by='Date')

    df_2024_onwards_1 = add_rolling_stats(df, prem_col, days_lst)
    df_2024_onwards_2 = generate_upper_lower_bounds(df_2024_onwards_1, prem_col, days_lst, sd_entry_lst)
    df_2024_onwards_3 = generate_m1m2_series(df_2024_onwards_2, m1m2_col, m2m3_col)

    plot_prem_disc(df_2024_onwards_3, prem_col, day)