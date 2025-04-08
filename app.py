import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt

folder_path = r"C:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\Notebooks\Streamlit_Notebooks\Test"

# Get list of available diffs based on file names
diff_files = [f for f in os.listdir(folder_path) if f.endswith(".xlsx") and f.startswith("df_")]
diff_options = [f.replace("df_", "").replace(".xlsx", "") for f in diff_files]

st.title("Test")

# Step 1: Select diff from dropdown
selected_diff = st.selectbox("Select Diff:", diff_options)

# Step 2: Load corresponding file
file_path = os.path.join(folder_path, f"df_{selected_diff}.xlsx")
df = pd.read_excel(file_path)

# Step 3: Select contract from within that dataframe
contract_options = df['contract'].dropna().unique()
selected_contract = st.selectbox("Select Contract:", contract_options)

# Step 4: Filter the dataframe
filtered_df = df[df['contract'] == selected_contract]

# Step 5: Plot
# Detect median/std timeframes automatically (e.g., 1m, 3m, etc.)
median_cols = [col for col in filtered_df.columns if col.startswith("median_") and col.endswith("m")]
if median_cols:
    median_col = median_cols[0]  # Default to the first one found
    suffix = median_col.replace("median_", "")
    upper_col = f"upper_bound_{suffix}"
    lower_col = f"lower_bound_{suffix}"

    # Ensure Date column is datetime
    if 'Date' in filtered_df.columns:
        filtered_df['Date'] = pd.to_datetime(filtered_df['Date'])

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(filtered_df['Date'], filtered_df['price'], label='Price', color='black', linewidth=2)
        ax.plot(filtered_df['Date'], filtered_df[median_col], label=f'Median ({suffix})', color='red', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df[upper_col], label=f'Upper Bound ({suffix})', linestyle='--', color='green', linewidth=1)
        ax.plot(filtered_df['Date'], filtered_df[lower_col], label=f'Lower Bound ({suffix})', linestyle='--', color='green', linewidth=1)

        ax.set_title(f"{selected_diff} — {selected_contract}")
        ax.set_xlabel("Date")
        ax.set_ylabel("Price")
        ax.legend(loc='center left', bbox_to_anchor=(1.0, 0.5))
        st.pyplot(fig)
    else:
        st.warning("The column 'Date' is missing from the data.")
else:
    st.warning("No median_Xm columns found to plot.")
