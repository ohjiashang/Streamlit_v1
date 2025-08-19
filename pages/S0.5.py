import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st
import urllib.parse


# def get_start_end_dates(contract, num_lookback_months=5):
def read_df(folder, filename):
    filename = f"{filename}.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/{folder}%2F{encoded_filename}?alt=media"
    static_df = pd.read_excel(url)
    static_df['Date'] = pd.to_datetime(static_df['Date'])
    return static_df

@st.cache_data
def plot_dual_axis_streamlit(df, selected_rolling_window=87, selected_sd=2):
    # filter last 6 months
    df = df.sort_values("Date")
    last_date = df["Date"].max()
    six_months = last_date - pd.DateOffset(months=6)
    df = df[df["Date"] >= six_months]

    # last values for annotations
    last_row = df.iloc[-1]
    last_price = last_row["Ex-Wharf-Cargo"]
    last_mean = last_row["Ex-Wharf-Cargo_mean_87d"]
    last_upper = last_row["Ex-Wharf-Cargo_2sd_87d"]
    last_m1m2 = last_row["0.5 M1/M2"]

    # --- Create subplot with 2:1 height ratio
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.67, 0.33],
        vertical_spacing=0.1
    )

    # --- Top Plot
    color_price = "black"
    color_mean = "grey"
    color_upper = "#065DDF"
    color_bottom = "green"

    fig.add_trace(go.Scatter(x=df["Date"], y=df["Ex-Wharf-Cargo"], mode="lines",
                             line=dict(color=color_price), name="Ex-Wharf-Cargo"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Ex-Wharf-Cargo_mean_87d"], mode="lines",
                             line=dict(color=color_mean, dash="dot", width=1), name=f"4m Avg"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Ex-Wharf-Cargo_2sd_87d"], mode="lines",
                             line=dict(color=color_upper, dash="dot", width=1), name=f"+{selected_sd}σ"), row=1, col=1)

    # --- Bottom Plot
    fig.add_trace(go.Scatter(x=df["Date"], y=df["0.5 M1/M2"], mode="lines",
                             line=dict(color=color_bottom), name="0.5 M1/M2"), row=2, col=1)

    # --- Inline annotations for last point
    fig.add_annotation(
        x=last_date, y=last_mean,
        text=f' 4m Avg ({last_mean:.2f})',
        showarrow=False, xshift=55,
        font=dict(size=13, color=color_mean),  # same as line
        align="left"
    )
    fig.add_annotation(
        x=last_date, y=last_upper,
        text=f' +{selected_sd}σ ({last_upper:.2f})',
        showarrow=False, xshift=55,
        font=dict(size=13, color=color_upper),  # same as line
        align="left"
    )

    fig.add_annotation(
        x=last_date, y=last_price,
        text=f' {last_price:.2f}',
        showarrow=False, xshift=15,
        font=dict(size=13, color=color_price),  # same as line
        align="left"
    )

    
    fig.add_annotation(
        x=last_date, y=last_m1m2,
        text=f' {last_m1m2:.2f}',
        showarrow=False, xshift=15,
        font=dict(size=13, color=color_bottom),  # same as line
        align="left",
        xref="x2",  # bottom subplot’s x-axis
        yref="y2"   # bottom subplot’s y-axis
    )


    # Layout
    fig.update_layout(
        height=600, width=900,
        showlegend=True,
        margin=dict(l=40, r=40, t=40, b=40)
    )

    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="Ex-Wharf-Cargo", row=1, col=1)
    fig.update_yaxes(title_text="0.5 M1/M2", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)



st.set_page_config(layout="wide")
st.title("S0.5 Ex-Wharf - Cargo")

df = read_df("Test", "S0.5_87d_data")
latest_date = df["Date"].max()

st.markdown(f"*Date: {latest_date.strftime('%Y-%m-%d')}*")

# Create 2 columns
col1, col2 = st.columns(2)

# Put chart only in left half
with col1:
    plot_dual_axis_streamlit(df)

# Optional: put something else in right half
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
