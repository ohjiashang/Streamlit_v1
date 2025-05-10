import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# def plot_live(df, selected_diff, selected_contract, selected_rolling_window, selected_sd):
#     # Mapping of months to approximate trading days
#     trading_days_map = {
#         1: 22, 2: 44, 3: 65, 4: 87, 5: 108,
#         6: 130, 9: 195, 12: 260,
#         15: 325, 18: 390, 21: 455, 24: 520,
#         27: 585, 30: 650, 33: 715, 36: 780
#     }

#     rolling_window_months = int(selected_rolling_window[:-1])
#     window = trading_days_map.get(rolling_window_months)

#     if window is None:
#         st.error(f"Invalid rolling window: {selected_rolling_window}")
#         return

#     df['Date'] = pd.to_datetime(df['Date'])
#     filtered_df = df[df['contract'] == selected_contract].copy()

#     if filtered_df.empty:
#         st.warning(f"No data found for contract: {selected_contract}")
#         return

#     # Add date range slider
#     min_date = filtered_df['Date'].min()
#     max_date = filtered_df['Date'].max()
#     date_range = st.slider(
#         "Select Date Range:",
#         min_value=min_date.date(),
#         max_value=max_date.date(),
#         value=(min_date.date(), max_date.date()),
#         format="YYYY-MM-DD"
#     )

#     # Convert slider dates to pandas Timestamp for comparison
#     start_date = pd.to_datetime(date_range[0])
#     end_date = pd.to_datetime(date_range[1])
#     filtered_df = filtered_df[(filtered_df['Date'] >= start_date) & (filtered_df['Date'] <= end_date)]

#     if filtered_df.empty:
#         st.warning("No data in selected date range.")
#         return

#     rolling_df = df.tail(window + len(filtered_df)).copy()
#     rolling_df['rolling_median'] = rolling_df['price'].rolling(window=window, min_periods=window).median()
#     rolling_df['rolling_std'] = rolling_df['price'].rolling(window=window, min_periods=window).std()
#     rolling_df['rolling_skew'] = rolling_df['price'].rolling(window=window, min_periods=window).skew()

#     filtered_df = filtered_df.merge(
#         rolling_df[['Date', 'rolling_median', 'rolling_std', 'rolling_skew']],
#         on='Date',
#         how='left'
#     )

#     filtered_df['upper_bound'] = filtered_df['rolling_median'] + selected_sd * filtered_df['rolling_std']
#     filtered_df['lower_bound'] = filtered_df['rolling_median'] - selected_sd * filtered_df['rolling_std']

#     fig, ax = plt.subplots(figsize=(12, 6))
#     ax.plot(filtered_df['Date'], filtered_df['price'], label='Price', color='black', linewidth=2)

#     if not filtered_df['rolling_median'].isnull().all():
#         ax.plot(filtered_df['Date'], filtered_df['rolling_median'], label=f'Median ({selected_rolling_window})', color='red', linewidth=1)
#         ax.plot(filtered_df['Date'], filtered_df['upper_bound'], label=f'Upper Bound ({selected_sd}SD)', linestyle='--', color='green', linewidth=1)
#         ax.plot(filtered_df['Date'], filtered_df['lower_bound'], label=f'Lower Bound ({selected_sd}SD)', linestyle='--', color='green', linewidth=1)

#     last_row = filtered_df.iloc[-1]
#     last_date = last_row['Date']
#     last_price = round(last_row['price'], 2)
#     last_median = round(last_row['rolling_median'], 2)
#     last_std = round(last_row['rolling_std'], 2)
#     last_skew = round(last_row['rolling_skew'], 2)
#     last_upper = round(last_row['upper_bound'], 2)
#     last_lower = round(last_row['lower_bound'], 2)

#     num_sd = round((last_price - last_median) / last_std, 2) if last_std != 0 else 0
#     num_sd_formatted = f"{num_sd:.2f}" if num_sd <= 0 else f"+{num_sd:.2f}"

#     annotation_text = (
#         f"Date: {last_date.strftime('%Y-%m-%d')}\n"
#         f"Price: {last_price}\n"
#         f"Median: {last_median}\n"
#         f"SD: {last_std}\n"
#         f"No. SD: {num_sd_formatted}\n"
#         f"Skew: {last_skew}"
#     )

#     ax.text(1.02, 0.98, annotation_text, transform=ax.transAxes,
#             color='black', fontsize=12, verticalalignment='top', horizontalalignment='left',
#             bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.5'))

#     ax.text(last_date, last_median, f'  {selected_rolling_window} Median ({last_median})',
#             color='red', fontsize=11, verticalalignment='baseline', horizontalalignment='left')
#     ax.text(last_date, last_upper, f'  +{selected_sd}σ ({last_upper})',
#             color='green', fontsize=11, verticalalignment='baseline', horizontalalignment='left')
#     ax.text(last_date, last_lower, f'  -{selected_sd}σ ({last_lower})',
#             color='green', fontsize=11, verticalalignment='baseline', horizontalalignment='left')

#     ax.set_xlim(filtered_df['Date'].min() - pd.Timedelta(days=7), filtered_df['Date'].max() + pd.Timedelta(days=60))
#     ax.set_title(f"{selected_diff} — {selected_contract}")
#     ax.set_xlabel("Date")
#     ax.set_ylabel("Price")
#     ax.tick_params(axis='x', labelrotation=45)
#     fig.tight_layout()
#     st.pyplot(fig)

#     return filtered_df

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

    # --- Reset logic ---
    if st.button("Reset Date Range"):
        st.session_state.date_range = (default_start, default_end)
        st.session_state.reset_date_range = True

    # --- Initialize session state ---
    if "reset_date_range" not in st.session_state:
        st.session_state.reset_date_range = False

    # --- Date range slider with direct session state binding ---
    st.slider(
        "Select Date Range:",
        min_value=min_date,
        max_value=max_date,
        value=(default_start, default_end),
        format="YYYY-MM-DD",
        key="date_range"
    )

    # --- Convert to Timestamp for filtering ---
    start_date = pd.to_datetime(st.session_state.date_range[0])
    end_date = pd.to_datetime(st.session_state.date_range[1])
    filtered_df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]


    ##### PLOTTING #####
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(filtered_df['Date'], filtered_df[price_col], label='Price', color='black', linewidth=2)

    if not filtered_df['rolling_median'].isnull().all():
        ax.plot(filtered_df['Date'], filtered_df['rolling_median'], label=f'Median ({selected_rolling_window})', color='red', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df['upper_bound'], label=f'Upper Bound ({selected_sd}SD)', linestyle='--', color='green', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df['lower_bound'], label=f'Lower Bound ({selected_sd}SD)', linestyle='--', color='green', linewidth=1)

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

        # f"+{selected_sd}σ: {last_upper}\n"
        # f"{selected_rolling_window} Median: {last_median}\n"
        # f"-{selected_sd}σ: {last_lower}\n"
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

