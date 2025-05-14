import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go


@st.cache_data
def add_rolling_cols(df, selected_rolling_window, selected_sd):
    # Mapping of months to approximate trading days
    trading_days_map = {
        1: 22, 2: 44, 3: 65, 4: 87, 5: 108,
        6: 130, 9: 195, 12: 260,
        15: 325, 18: 390, 21: 455, 24: 520,
        27: 585, 30: 650, 33: 715, 36: 780
    }

    price_col = 'exit_norm_price'

    rolling_window_months = int(selected_rolling_window[:-1])
    window = trading_days_map.get(rolling_window_months)

    if df.empty:
        st.warning(f"No data found")
        return

    df['rolling_median'] = df[price_col].rolling(window=window, min_periods=window).median()
    df['rolling_std'] = df[price_col].rolling(window=window, min_periods=window).std()
    df['upper_bound'] = df['rolling_median'] + selected_sd * df['rolling_std']
    df['lower_bound'] = df['rolling_median'] - selected_sd * df['rolling_std']
    return df


def plot_live_contract_roll(df, selected_diff, selected_contract, selected_rolling_window, selected_sd):
    # Mapping of months to approximate trading days
    trading_days_map = {
        1: 22, 2: 44, 3: 65, 4: 87, 5: 108,
        6: 130, 9: 195, 12: 260,
        15: 325, 18: 390, 21: 455, 24: 520,
        27: 585, 30: 650, 33: 715, 36: 780
    }

    price_col = 'exit_norm_price'

    rolling_window_months = int(selected_rolling_window[:-1])
    window = trading_days_map.get(rolling_window_months)

    if window is None:
        st.error(f"Invalid rolling window: {selected_rolling_window}")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    latest_date = df['Date'].max()
    cutoff_date = latest_date - pd.DateOffset(months=12)

    # --- Defaults ---
    min_date = df['Date'].min().date()
    max_date = df['Date'].max().date()
    default_start = cutoff_date.date()
    default_end = max_date

    # --- Initialize session state before the slider is created ---
    if "date_range" not in st.session_state:
        st.session_state["date_range"] = (default_start, default_end)

    # --- Reset logic ---
    if st.button("Reset Date Range"):
        st.session_state["date_range"] = (default_start, default_end)

    # --- Date range slider (no 'value' param because key is used) ---
    st.slider(
        "Select Date Range:",
        min_value=min_date,
        max_value=max_date,
        format="YYYY-MM-DD",
        key="date_range"
    )

    # --- Use session state to access selected range ---
    start_date = pd.to_datetime(st.session_state["date_range"][0])
    end_date = pd.to_datetime(st.session_state["date_range"][1])

    # --- Filter data ---
    filtered_df = df[(df['Date'] > start_date) & (df['Date'] <= end_date)]


    ##### PLOTTING #####
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(filtered_df['Date'], filtered_df[price_col], label='Price', color='black', linewidth=2)

    if not filtered_df['rolling_median'].isnull().all():
        ax.plot(filtered_df['Date'], filtered_df['rolling_median'], label=f'Median ({selected_rolling_window})', color='red', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df['upper_bound'], label=f'+{selected_sd}SD', linestyle='--', color='green', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df['lower_bound'], label=f'-{selected_sd}SD', linestyle='--', color='green', linewidth=1)

    last_row = filtered_df.iloc[-1]
    last_date = last_row['Date']
    last_price = round(last_row[price_col], 2)
    last_median = round(last_row['rolling_median'], 2)
    last_std = round(last_row['rolling_std'], 2)
    last_upper = round(last_row['upper_bound'], 2)
    last_lower = round(last_row['lower_bound'], 2)

    num_sd = round((last_price - last_median) / last_std, 2) if last_std != 0 else 0
    num_sd_formatted = f"{num_sd:.2f}" if num_sd <= 0 else f"+{num_sd:.2f}"

    annotation_text = (
        f"Date: {last_date.strftime('%Y-%m-%d')}\n"
        f"Price: {last_price}\n"
        f"Median: {last_median}\n"
        f"SD: {last_std}\n"
        f"No. SD: {num_sd_formatted}"
    )

    ax.text(1.02, 0.98, annotation_text, transform=ax.transAxes,
            color='black', fontsize=11, verticalalignment='top', horizontalalignment='left',
            bbox=dict(facecolor='white', edgecolor='white', boxstyle='round,pad=0.5'))

    # --- Text for individual points with white highlight ---
    ax.text(last_date, last_median, f'  {selected_rolling_window} Median ({last_median})',
            color='red', fontsize=11, verticalalignment='baseline', horizontalalignment='left',
            bbox=dict(facecolor='white', edgecolor='white', boxstyle='round,pad=0.1'))

    ax.text(last_date, last_upper, f'  +{selected_sd}σ ({last_upper})',
            color='green', fontsize=11, verticalalignment='baseline', horizontalalignment='left',
            bbox=dict(facecolor='white', edgecolor='white', boxstyle='round,pad=0.1'))

    ax.text(last_date, last_lower, f'  -{selected_sd}σ ({last_lower})',
            color='green', fontsize=11, verticalalignment='baseline', horizontalalignment='left',
            bbox=dict(facecolor='white', edgecolor='white', boxstyle='round,pad=0.1'))

    ax.set_xlim(filtered_df['Date'].min() - pd.Timedelta(days=7), filtered_df['Date'].max() + pd.Timedelta(days=7))
    ax.set_title(f"{selected_diff} (Normalised) — {selected_contract}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.tick_params(axis='x', labelrotation=45)
    fig.tight_layout()
    st.pyplot(fig)

def plot_live_contract_roll_plotly(df, selected_diff, selected_contract, selected_rolling_window, selected_sd):
    # Mapping of months to approximate trading days
    trading_days_map = {
        1: 22, 2: 44, 3: 65, 4: 87, 5: 108,
        6: 130, 9: 195, 12: 260,
        15: 325, 18: 390, 21: 455, 24: 520,
        27: 585, 30: 650, 33: 715, 36: 780
    }

    price_col = 'exit_norm_price'

    rolling_window_months = int(selected_rolling_window[:-1])
    window = trading_days_map.get(rolling_window_months)

    if window is None:
        st.error(f"Invalid rolling window: {selected_rolling_window}")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    latest_date = df['Date'].max()
    cutoff_date = latest_date - pd.DateOffset(months=12)

    # --- Defaults ---
    min_date = df['Date'].min().date()
    max_date = df['Date'].max().date()
    default_start = cutoff_date.date()
    default_end = max_date

    # --- Initialize session state before the slider is created ---
    if "date_range" not in st.session_state:
        st.session_state["date_range"] = (default_start, default_end)

    # --- Reset logic ---
    if st.button("Reset Date Range"):
        st.session_state["date_range"] = (default_start, default_end)

    # --- Date range slider (no 'value' param because key is used) ---
    st.slider(
        "Select Date Range:",
        min_value=min_date,
        max_value=max_date,
        format="YYYY-MM-DD",
        key="date_range"
    )

    # --- Use session state to access selected range ---
    start_date = pd.to_datetime(st.session_state["date_range"][0])
    end_date = pd.to_datetime(st.session_state["date_range"][1])

    # --- Filter data ---
    filtered_df = df[(df['Date'] > start_date) & (df['Date'] <= end_date)]

    ##### PLOTTING with Plotly #####
    fig = go.Figure()

    # Plot Price line
    fig.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df[price_col], mode='lines', name='Price', line=dict(color='black', width=2.2)))

    # Plot rolling median, upper, and lower bounds
    if not filtered_df['rolling_median'].isnull().all():
        fig.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['rolling_median'], mode='lines', name=f'Median', line=dict(color='red', width=1.3)))
        fig.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['upper_bound'], mode='lines', name=f'+{selected_sd}SD', line=dict(color='green', dash='dot', width=1.3)))
        fig.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['lower_bound'], mode='lines', name=f'-{selected_sd}SD', line=dict(color='green', dash='dot', width=1.3)))

    # Last row for annotations
    last_row = filtered_df.iloc[-1]
    last_date = last_row['Date']
    last_price = round(last_row[price_col], 2)
    last_median = round(last_row['rolling_median'], 2)
    last_std = round(last_row['rolling_std'], 2)
    last_upper = round(last_row['upper_bound'], 2)
    last_lower = round(last_row['lower_bound'], 2)

    num_sd = round((last_price - last_median) / last_std, 2) if last_std != 0 else 0
    num_sd_formatted = f"{num_sd:.2f}" if num_sd <= 0 else f"+{num_sd:.2f}"

    last_contract = last_row['entry_contract']
    if selected_contract == "Box":
        last_contract = last_contract.replace('-', '/')
    if selected_contract == "Outright":
        last_contract = last_contract[:5]

    annotation_text = (
        f"Date: {last_date.strftime('%Y-%m-%d')}<br>"
        f"Price: {last_price}<br>"
        f"Median: {last_median}<br>"
        f"SD: {last_std}<br>"
        f"No. SD: {num_sd_formatted}<br>"
    )

    fig.add_annotation(
        x=1.15, y=1, xref="paper", yref="paper", text=annotation_text, showarrow=False,
        font=dict(size=15, color="black"), align="left", bgcolor="white", borderpad=4, bordercolor="white", borderwidth=1
    )

    # Add individual point annotations
    fig.add_annotation(
        x=last_date, y=last_median, text=f' {selected_rolling_window} Median ({last_median})', showarrow=False,
        font=dict(size=13, color="red"), xshift=50, align="left"
    )
    fig.add_annotation(
        x=last_date, y=last_upper, text=f' +{selected_sd}σ ({last_upper})', showarrow=False,
        font=dict(size=13, color="green"), xshift=30, align="left"
    )
    fig.add_annotation(
        x=last_date, y=last_lower, text=f' -{selected_sd}σ ({last_lower})', showarrow=False,
        font=dict(size=13, color="green"), xshift=30, align="left"
    )

    # Update layout
    fig.update_layout(
        title=f"Normalised {selected_diff} — {selected_contract} ({last_contract})",
        title_x=0.5,  # Centers the title (0 is left, 1 is right)
        title_xanchor="center",

        xaxis_title="Date", yaxis_title="Price",
        xaxis=dict(tickformat="%Y-%m-%d", tickangle=45),
        margin=dict(r=150),  # Add space for the annotation on the right
        autosize=True
    )

    fig.update_layout(showlegend=False)
    fig.update_layout( width=1200, height=600)

    # Show Plotly plot
    st.plotly_chart(fig)
