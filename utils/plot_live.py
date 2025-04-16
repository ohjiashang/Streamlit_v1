import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

def plot_live(df, selected_diff, selected_contract, selected_rolling_window, selected_sd):
    # Mapping of months to approximate trading days
    trading_days_map = {
        1: 22,  2: 44, 3: 65, 4: 87, 5: 108,
        6: 130, 9: 195, 12: 260,
        15: 325, 18: 390, 21: 455, 24: 520,
        27: 585, 30: 650, 33: 715, 36: 780
    }

    # Extract the number of months from the selected rolling window
    rolling_window_months = int(selected_rolling_window[:-1])
    window = trading_days_map.get(rolling_window_months)

    if window is None:
        st.error(f"Invalid rolling window: {selected_rolling_window}")
        return

    # Ensure 'Date' column is in datetime format
    df['Date'] = pd.to_datetime(df['Date'])

    # Filter the DataFrame for the selected contract
    filtered_df = df[df['contract'] == selected_contract].copy()
    print(filtered_df.shape)
    print(window)

    if filtered_df.empty:
        st.warning(f"No data found for contract: {selected_contract}")
        return

    # Determine the number of rows to use for rolling calculation
    rolling_df = df.tail(window + len(filtered_df)).copy()
    rolling_df['rolling_median'] = rolling_df['price'].rolling(window=window, min_periods=window).median()
    rolling_df['rolling_std'] = rolling_df['price'].rolling(window=window, min_periods=window).std()
    rolling_df['rolling_skew'] = rolling_df['price'].rolling(window=window, min_periods=window).skew()

    # Merge the rolling statistics back into the filtered DataFrame
    filtered_df = filtered_df.merge(
        rolling_df[['Date', 'rolling_median', 'rolling_std', 'rolling_skew']],
        on='Date',
        how='left'
    )

    # Calculate upper and lower bounds based on selected standard deviation
    filtered_df['upper_bound'] = filtered_df['rolling_median'] + selected_sd * filtered_df['rolling_std']
    filtered_df['lower_bound'] = filtered_df['rolling_median'] - selected_sd * filtered_df['rolling_std']

    # Plotting
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(filtered_df['Date'], filtered_df['price'], label='Price', color='black', linewidth=2)

    # Plot rolling median and bounds if they exist
    if not filtered_df['rolling_median'].isnull().all():
        ax.plot(filtered_df['Date'], filtered_df['rolling_median'], label=f'Median ({selected_rolling_window})', color='red', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df['upper_bound'], label=f'Upper Bound ({selected_sd}SD)', linestyle='--', color='green', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df['lower_bound'], label=f'Lower Bound ({selected_sd}SD)', linestyle='--', color='green', linewidth=1)

    # Annotate the final price value
    last_date = filtered_df['Date'].iloc[-1]
    last_price = filtered_df['price'].iloc[-1]
    last_skew = filtered_df['rolling_skew'].iloc[-1]
    last_median = filtered_df['rolling_median'].iloc[-1]
    last_std = filtered_df['rolling_std'].iloc[-1]
    last_upper = filtered_df['upper_bound'].iloc[-1]
    last_lower = filtered_df['lower_bound'].iloc[-1]

    num_sd = round((last_price - last_median) / last_std, 2) if last_std != 0 else 0
    last_price = round(last_price, 2)
    last_median = round(last_median, 2)
    last_std = round(last_std, 2)
    last_skew = round(last_skew, 2)
    # Format num_sd to show "+" if positive, otherwise just the value
    num_sd_formatted = f"{num_sd:.2f}" if num_sd <= 0 else f"+{num_sd:.2f}"
    
    last_lower = round(last_lower, 2)
    last_upper = round(last_upper, 2)

    annotation_text = (
        f"Date: {last_date.strftime('%Y-%m-%d')}\n"
        f"Price: {last_price}\n"
        f"Median: {last_median}\n"
        f"SD: {last_std}\n"
        f"No. SD: {num_sd_formatted}\n"
        f"Skew: {last_skew}"
    )

    # Place annotation box outside the plot (top-right corner)
    ax.text(1.02, 0.98, annotation_text, transform=ax.transAxes, 
             color='black', fontsize=12, verticalalignment='top', horizontalalignment='left',
             bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.5'))
    
    # Annotate upper bound
    ax.text(last_date, last_median, f'  {selected_rolling_window} Median ({last_median})', 
            color='red', fontsize=11, verticalalignment='baseline', horizontalalignment='left')

    # Annotate upper bound
    ax.text(last_date, last_upper, f'  +{selected_sd}σ ({last_upper})', 
            color='green', fontsize=11, verticalalignment='baseline', horizontalalignment='left')

    # Annotate lower bound
    ax.text(last_date, last_lower, f'  -{selected_sd}σ ({last_lower})', 
            color='green', fontsize=11, verticalalignment='baseline', horizontalalignment='left')
    
    # Determine the range of dates
    date_range = filtered_df['Date'].max() - filtered_df['Date'].min()
    extra_days_start = pd.Timedelta(days=7)  # Adjust the number of extra days as needed
    extra_days_end = pd.Timedelta(days=60)  # Adjust the number of extra days as needed

    # Set new x-axis limits
    ax.set_xlim(filtered_df['Date'].min()- extra_days_start, filtered_df['Date'].max() + extra_days_end)

    ax.set_title(f"{selected_diff} — {selected_contract}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.tick_params(axis='x', labelrotation=45)
    fig.tight_layout()
    st.pyplot(fig)
