import pandas as pd
import numpy as np
import os
from datetime import datetime
import matplotlib.pyplot as plt
import streamlit as st

def add_rolling_stats(df, col, days_lst):
    """
    Add rolling statistics (mean, std, and median) to the DataFrame for the specified column.
    
    Parameters:
        df (pd.DataFrame): Input DataFrame.
        col (str): Column name for which rolling stats are calculated.
        days_lst (list): List of rolling window sizes (in days).
    
    Returns:
        pd.DataFrame: DataFrame with additional rolling statistics columns.
    """
    # Calculate daily change for the column
    df[f'{col}_chg'] = df[col].diff()
    
    for days in days_lst:
        window_size = days
        
        # Compute rolling median
        df[f'{col}_median_{days}d'] = df[col].rolling(window=window_size, min_periods=window_size).median()

        # Compute rolling standard deviation
        df[f'{col}_std_{days}d'] = df[f'{col}'].rolling(window=window_size, min_periods=window_size).std()
        
    return df

def generate_upper_lower_bounds(df, col, days_lst, sd_lst):
    for days in days_lst:
        for sd in sd_lst:
            df[f'{days}d_{sd}sd_lower'] = df[f'{col}_median_{days}d'] - sd*df[f'{col}_std_{days}d']
            df[f'{days}d_{sd}sd_upper'] = df[f'{col}_median_{days}d'] + sd*df[f'{col}_std_{days}d']
    return df


def generate_m1m2_series(df, m1m2_col, m2m3_col):
    """
    Creates a new column 'm1/m2_plot' based on m1m2_col, except for the last trading day 
    of each month, where it takes the value from m2m3_col.
    
    The last row is also checked: if the next business day is in the same month, it's not treated as the last trading day.

    Parameters:
    df (pd.DataFrame): DataFrame containing 'Date' and 'Month' columns, along with m1m2_col & m2m3_col.
    m1m2_col (str): Column name for m1/m2 values.
    m2m3_col (str): Column name for m2/m3 values.

    Returns:
    pd.DataFrame: Modified DataFrame with 'm1/m2_plot' column.
    """
    # Create a copy to avoid modifying the original DataFrame
    df = df.copy()

    # Ensure Date column is datetime format
    df['Date'] = pd.to_datetime(df['Date'])

    # Identify the last trading day of the month (default method)
    df['is_last_day'] = df['Month'] != df['Month'].shift(-1)

    # Special handling for the last row
    if not df.empty:
        last_idx = df.index[-1]
        next_business_day = df.loc[last_idx, 'Date'] + pd.offsets.BDay(1)

        # If next business day is in the same month, it's not the last trading day
        if next_business_day.month == df.loc[last_idx, 'Month']:
            df.at[last_idx, 'is_last_day'] = False

    # Assign values: default is m1/m2_col, but replace last trading day with m2m3_col
    df['m1/m2_plot'] = df[m1m2_col]
    df.loc[df['is_last_day'], 'm1/m2_plot'] = df[m2m3_col]

    # Drop helper column
    df.drop(columns=['is_last_day'], inplace=True)

    return df


def plot_prem_disc(df, prem_col, day):
    """
    Plots the 92R Prem/Disc time series along with its median and standard deviation bands.
    Also includes a second plot below for 'm1/m2_plot'.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing 'Date', 'm1/m2_plot', and standard deviation bands.
    """
    # Convert Date to datetime if not already
    df['Date'] = pd.to_datetime(df['Date'])

    # Define standard deviation levels and their corresponding colors
    sd_dict = {
        0.5: '#006400',  # Dark Green
        1: '#8B0000',     # Dark Red
        1.5: '#B8860B',   # Dark Yellow
        2: '#FF8C00'      # Dark Orange
    }

    # Determine the latest date in the dataset
    latest_date = df['Date'].max()

    # Adjust the start date to include an extra 2 weeks before the 6-month period
    six_months_ago = latest_date - pd.DateOffset(months=6)
    start_date = six_months_ago - pd.Timedelta(days=7)  # Add 2 weeks before

    # Filter data to show the adjusted period
    df_filtered = df[(df['Date'] >= six_months_ago) & (df['Date'] <= latest_date)]

    # Create a figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [2, 1]})

    ### MAIN PLOT (92R Prem/Disc) ###
    ax1.plot(df_filtered['Date'], df_filtered[prem_col], color='black', linewidth=1.5, label=prem_col)

    # Plot median line in solid blue
    ax1.plot(df_filtered['Date'], df_filtered[f'{prem_col}_median_{day}d'], color='blue', linewidth=1, label=f'Median ({day}d)')

    # Expand x-axis limit to create space on both sides
    extra_days_right = pd.Timedelta(days=30)  # Adds ~1 month of extra space on the right
    ax1.set_xlim(start_date, latest_date + extra_days_right)

    # Annotate the median line at the rightmost side
    last_median_value = df_filtered[f'{prem_col}_median_{day}d'].dropna().iloc[-1]
    ax1.text(latest_date, last_median_value, f'  {day}d Median ({round(last_median_value,2)})', color='blue', fontsize=10, 
            verticalalignment='baseline', horizontalalignment='left')

    # Loop through standard deviation levels and plot upper/lower bounds in the specified colors
    for sd, color in sd_dict.items():
        lower_col = f'{day}d_{sd}sd_lower'
        upper_col = f'{day}d_{sd}sd_upper'

        if lower_col in df_filtered.columns and upper_col in df_filtered.columns:
            # Plot the lines
            ax1.plot(df_filtered['Date'], df_filtered[lower_col], linestyle='dotted', color=color)
            ax1.plot(df_filtered['Date'], df_filtered[upper_col], linestyle='dotted', color=color)

            # Get last valid value for annotation
            last_lower_value = df_filtered[lower_col].dropna().iloc[-1]
            last_upper_value = df_filtered[upper_col].dropna().iloc[-1]

            # Annotate upper bound
            ax1.text(latest_date, last_upper_value, f'  +{sd}σ ({round(last_upper_value,2)})', 
                    color=color, fontsize=10, verticalalignment='baseline', horizontalalignment='left')

            # Annotate lower bound
            ax1.text(latest_date, last_lower_value, f'  -{sd}σ ({round(last_lower_value,2)})', 
                    color=color, fontsize=10, verticalalignment='baseline', horizontalalignment='left')

    ### SECOND PLOT (m1/m2_plot) ###
    ax2.plot(df_filtered['Date'], df_filtered['m1/m2_plot'], color='black', linewidth=1.2, label='m1/m2_plot')

    last_m1m2 = df_filtered['m1/m2_plot'].dropna().iloc[-1]
    ax2.text(latest_date, last_m1m2, f'  {round(last_m1m2,2)}', color='black', fontsize=10, 
            verticalalignment='baseline', horizontalalignment='left')

    
    # Labels for second plot
    ax2.set_ylabel('M1/M2')
    ax2.set_xlabel('Date')
    ax2.grid(True, linewidth=0.3, alpha=0.75, color='gray')

    # Get latest values for annotation box
    latest_price = df_filtered[prem_col].dropna().iloc[-1]
    latest_median = df_filtered[f'{prem_col}_median_{day}d'].dropna().iloc[-1]
    latest_sd = df_filtered[f'{prem_col}_std_{day}d'].dropna().iloc[-1]
    num_sd = round((latest_price - latest_median) / latest_sd, 2) if latest_sd != 0 else 0
    latest_price = round(latest_price, 2)
    latest_median = round(latest_median, 2)
    latest_sd = round(latest_sd, 2)
    # Format num_sd to show "+" if positive, otherwise just the value
    num_sd_formatted = f"{num_sd:.2f}" if num_sd <= 0 else f"+{num_sd:.2f}"
    
    # Format annotation text
    annotation_text = (
        f"Date: {latest_date.strftime('%Y-%m-%d')}\n"
        f"Price: {latest_price}\n"
        f"Median: {latest_median}\n"
        f"SD: {latest_sd}\n"
        f"No. SD: {num_sd_formatted}"
    )

    # Place annotation box outside the plot (top-right corner)
    ax1.text(1.02, 0.98, annotation_text, transform=ax1.transAxes, 
             color='black', fontsize=10, verticalalignment='top', horizontalalignment='left',
             bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.5'))

    # Customize plot
    ax1.set_ylabel('Cash Prem/Disc')
    ax1.set_title(f'{prem_col} with Median and SD Bands')
    ax1.grid(True, linewidth=0.3, alpha=0.75, color='gray')

    # Ensure all elements are within the figure
    plt.tight_layout()
    st.pyplot(fig)

