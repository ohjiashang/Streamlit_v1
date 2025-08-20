import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import pandas as pd
import urllib.parse

@st.cache_data
def read_df_from_firebase(folder, filename, sheet_name="Sheet1"):
    """
    Helper: Read Excel sheet from Firebase storage.
    """
    filename = f"{filename}.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = (
        f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/"
        f"{folder}%2F{encoded_filename}?alt=media"
    )
    df = pd.read_excel(url, sheet_name=sheet_name, engine="openpyxl")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    return df


def process_excel(
    folder,
    filename,
    sheet_main="Sheet1",
    sheet_new="Sheet3",
    target_col="0.5 Cash/M1",
    compare_col="0.5 M1/M2",
    spread_col="Ex-Wharf-Cargo",
    rolling_days=[87],
    date_col="Date",
    shift_months=1
):
    def map_shifted_monthly_avg(df, target_col, date_col, shift_months):
        new_df = df.copy()
        new_df[date_col] = pd.to_datetime(new_df[date_col])
        new_df["Year"] = new_df[date_col].dt.year
        new_df["Month"] = new_df[date_col].dt.month

        # Step 1: Calculate monthly average
        monthly_avg = (
            new_df.groupby(["Year", "Month"])[target_col]
            .mean()
            .reset_index()
            .rename(columns={target_col: f"{compare_col}_exit"})
        )

        # Step 2: Shift monthly averages
        monthly_avg[f"{compare_col}_exit"] = monthly_avg[f"{compare_col}_exit"].shift(-shift_months)

        # Step 3: Merge back to daily dataframe
        new_df = new_df.merge(monthly_avg, on=["Year", "Month"], how="left")
        return new_df

    def add_rolling_stats(df, col, days_lst):
        for days in days_lst:
            df[f"{col}_mean_{days}d"] = df[col].rolling(window=days, min_periods=days).mean()
            df[f"{col}_std_{days}d"] = df[col].rolling(window=days, min_periods=days).std()
            df[f"{col}_2sd_{days}d"] = df[f"{col}_mean_{days}d"] + 2 * df[f"{col}_std_{days}d"]
        return df

    # --- Step 1: Load data from Firebase ---
    df = read_df_from_firebase(folder, filename, sheet_main).dropna(how="any")
    df_new = read_df_from_firebase(folder, filename, sheet_new).dropna(subset=[target_col, compare_col])

    # --- Step 2: Monthly avg + shift ---
    df_new = map_shifted_monthly_avg(df_new, target_col=target_col, date_col=date_col, shift_months=shift_months)

    # --- Step 3: Merge ---
    df_main = df.merge(df_new, on=date_col, how="inner")

    # --- Step 4: Rolling stats ---
    df_final = add_rolling_stats(df_main, spread_col, rolling_days)

    return df_final


def plot_dual_axis_streamlit(df, selected_sd=2):
    # --- Ensure Date is datetime ---
    df['Date'] = pd.to_datetime(df['Date'])

    # --- Slider Defaults ---
    latest_date = df['Date'].max()
    cutoff_date = latest_date - pd.DateOffset(months=6)
    min_date = df['Date'].min().date()
    max_date = df['Date'].max().date()
    default_start = cutoff_date.date()
    default_end = max_date

    # --- initialize once, before slider is created ---
    if "date_range_s05" not in st.session_state:
        st.session_state.date_range_s05 = (default_start, default_end)

    # --- reset button must run before slider ---
    if st.button("Reset Date Range"):
        st.session_state.date_range_s05 = (default_start, default_end)

    # --- slider (do NOT set value=, let session state handle it) ---
    date_range = st.slider(
        "Select Date Range:",
        min_value=min_date,
        max_value=max_date,
        format="YYYY-MM-DD",
        key="date_range_s05"
    )

    # --- use result ---
    start_date = pd.to_datetime(date_range[0])
    end_date = pd.to_datetime(date_range[1])

    # --- Filter data by slider range ---
    df = df[(df['Date'] > start_date) & (df['Date'] <= end_date)]
    df = df.sort_values("Date")

    if df.empty:
        st.warning("No data in selected range.")
        return

    # --- Last row values for annotation ---
    last_row = df.iloc[-1]
    last_price = last_row["Ex-Wharf-Cargo"]
    last_mean = last_row["Ex-Wharf-Cargo_mean_87d"]
    last_upper = last_row["Ex-Wharf-Cargo_2sd_87d"]
    last_m1m2 = last_row["0.5 M1/M2"]

    # --- Create subplot ---
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.67, 0.33],
        vertical_spacing=0.1
    )

    # --- Top Plot ---
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Ex-Wharf-Cargo"], mode="lines",
                             line=dict(color="black"), name="Ex-Wharf-Cargo"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Ex-Wharf-Cargo_mean_87d"], mode="lines",
                             line=dict(color="grey", dash="dot", width=1), name="4m Avg"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Ex-Wharf-Cargo_2sd_87d"], mode="lines",
                             line=dict(color="#065DDF", dash="dot", width=1), name=f"+{selected_sd}σ"), row=1, col=1)

    # --- Bottom Plot ---
    fig.add_trace(go.Scatter(x=df["Date"], y=df["0.5 M1/M2"], mode="lines",
                             line=dict(color="green"), name="0.5 M1/M2"), row=2, col=1)

    # --- Annotations ---
    fig.add_annotation(x=last_row["Date"], y=last_mean, text=f'4m Avg ({last_mean:.2f})',
                       showarrow=False, xshift=55, font=dict(size=13, color="grey"))
    fig.add_annotation(x=last_row["Date"], y=last_upper, text=f'+{selected_sd}σ ({last_upper:.2f})',
                       showarrow=False, xshift=55, font=dict(size=13, color="#065DDF"))
    fig.add_annotation(x=last_row["Date"], y=last_price, text=f'{last_price:.2f}',
                       showarrow=False, xshift=15, font=dict(size=13, color="black"))
    fig.add_annotation(x=last_row["Date"], y=last_m1m2, text=f'{last_m1m2:.2f}',
                       showarrow=False, xshift=15, font=dict(size=13, color="green"),
                       xref="x2", yref="y2")

    fig.update_layout(height=600, width=900, showlegend=True,
                      margin=dict(l=40, r=40, t=40, b=40))
    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="Ex-Wharf-Cargo", row=1, col=1)
    fig.update_yaxes(title_text="0.5 M1/M2", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)


###############################################################################################
st.set_page_config(layout="wide")
st.title("S0.5 Ex-Wharf - Cargo")


df = process_excel(
    folder="Test",
    filename="0.5PhyDiffHistoricals_js",
    sheet_main="Sheet1",
    sheet_new="Sheet3"
)

latest_date = df["Date"].max()
st.markdown(f"*Date: {latest_date.strftime('%Y-%m-%d')}*")

col1, spacer, col2 = st.columns([1, 0.05, 1])

with col1:
    plot_dual_axis_streamlit(df)

with col2:
    df_display_cols = [
        'Date', 'Cargo', 'Ex-Wharf', 'Ex-Wharf-Cargo','0.5 M1/M2', 
        'Ex-Wharf-Cargo_mean_87d', 'Ex-Wharf-Cargo_std_87d', 'Ex-Wharf-Cargo_2sd_87d'
    ]

    df_display = df[df_display_cols].copy()

    # Format date as YYYY-MM-DD
    df_display["Date"] = pd.to_datetime(df_display["Date"]).dt.strftime("%Y-%m-%d")

    # Round numeric columns to 2 decimals
    df_display = df_display.round(2)

    # Show last 5 rows
    st.write(df_display.tail(10).reset_index(drop=True))
