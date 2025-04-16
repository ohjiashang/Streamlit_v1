import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt

st.set_page_config(initial_sidebar_state="expanded")

folder_path = "Test"

# Get list of available diffs based on file names
diff_files = [f for f in os.listdir(folder_path) if f.endswith(".xlsx") and f.startswith("df_")]
# diff_options = [f.replace("df_", "").replace(".xlsx", "") for f in diff_files]

diff_options = [
    'Brt-Dub',
    'Dated-Brt',
    'Wti-Brt'
]

tab1, tab2 = st.tabs(["Top 10", "Diff"])

with tab1:
    st.title("Top 10")
    st.image("Test/Boxes_top10_20250409.png", caption="Boxes Top 10", use_container_width=True)
    st.image("Test/Outrights_top10_20250409.png", caption="Outrights Top 10", use_container_width=True)

with tab2:
    st.title("Filter by Diff")

    # Step 1: Select diff from dropdown
    selected_diff = st.selectbox("Select Diff:", diff_options)

    contract_options = ['Jun25', 'Jul25', 'Aug25', 'Sep25', 'Oct25', 'Nov25', 'Dec25', 'Jan26']
    selected_contract = st.selectbox("Select Contract:", contract_options)

    # Firebase public file URL
    folder = "Outrights"
    filename = f"{selected_diff}_Outrights.xlsx"

    url = F"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.firebasestorage.app/o/Outrights%2F{selected_diff}_Outrights.xlsx?alt=media&token=aec5fe07-738e-46cf-914f-a7b49c372ac9"
# df = pd.read_excel(url)

    # url = f"https://firebasestorage.googleapis.com/v0/b/hotei-streamlit.appspot.com/o/{folder}%2F{filename}?alt=media"
    print(url)

    try:
        # Load the Excel file (all sheets)
        df = pd.read_excel(url, sheet_name=selected_contract[:3])

        if df is None:
            st.warning(f"No data found for sheet: {selected_contract[:3]}")
            st.stop()

        # Step 2: Filter the dataframe
        filtered_df = df[df['contract'] == selected_contract]

        rolling_window_options = [1, 2, 3, 4, 5, 6]
        selected_rolling_window = st.selectbox("Select Rolling Window:", rolling_window_options)

        sd_options = [1, 2]
        selected_sd = st.selectbox("Select SD:", sd_options)

        # Step 3: Plotting
        suffix = f"{selected_rolling_window}m"
        median_col = f"median_{suffix}"
        std_col = f"std_{suffix}"

        if median_col in filtered_df.columns and std_col in filtered_df.columns:
            filtered_df["upper_custom"] = filtered_df[median_col] + selected_sd * filtered_df[std_col]
            filtered_df["lower_custom"] = filtered_df[median_col] - selected_sd * filtered_df[std_col]

            if 'Date' in filtered_df.columns:
                filtered_df['Date'] = pd.to_datetime(filtered_df['Date'])

                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(filtered_df['Date'], filtered_df['price'], label='Price', color='black', linewidth=2)
                ax.plot(filtered_df['Date'], filtered_df[median_col], label=f'Median ({suffix})', color='red', linewidth=1)
                ax.plot(filtered_df['Date'], filtered_df["upper_custom"], label=f'Upper Bound ({selected_sd}×STD)', linestyle='--', color='green', linewidth=1)
                ax.plot(filtered_df['Date'], filtered_df["lower_custom"], label=f'Lower Bound ({selected_sd}×STD)', linestyle='--', color='green', linewidth=1)

                ax.set_title(f"{selected_diff} — {selected_contract}")
                ax.set_xlabel("Date")
                ax.set_ylabel("Price")
                ax.legend(loc='center left', bbox_to_anchor=(1.0, 0.5))
                st.pyplot(fig)
            else:
                st.warning("The column 'Date' is missing from the data.")
        else:
            st.warning("Selected rolling window columns not found.")

        # Step 4: Load and display mean reversion summary
        summary_file = os.path.join(folder_path, "MeanReversion_Boxes_20250409.xlsx")
        summary_df = pd.read_excel(summary_file, sheet_name="yearly_breakdown")

        month_str = selected_contract[:3] + "/" + selected_contract[6:9]
        window_str = median_col[-2:]

        filtered_summary = summary_df[
            (summary_df['diff'] == selected_diff) &
            (summary_df['month'] == month_str) &
            (summary_df['window'] == window_str)
        ].reset_index()

        display_cols = [
            'contract', 'window', 'returns', 'max_loss', 'ratio',
            'num_trades', 'overall_skew', 'is_long'
        ]

        st.subheader("Historical Performance")
        if not filtered_summary.empty:
            st.dataframe(filtered_summary[display_cols])
        else:
            st.warning("No matching rows found in performance summary.")

    except Exception as e:
        st.error(f"Error loading or processing file: {e}")
