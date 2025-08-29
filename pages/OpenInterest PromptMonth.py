import streamlit as st
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

import matplotlib.colors as mcolors

def lighten_color(color, amount):
    color_rgb = mcolors.to_rgb(color)
    white = (1, 1, 1)
    blended = tuple((1 - amount) * c + amount * w for c, w in zip(color_rgb, white))
    return mcolors.to_hex(blended)

def color_pct_from_avg(val):
    if val == 0 or pd.isna(val):
        return ""

    max_val = 200  # Adjust depending on your data
    norm_val = min(abs(val) / max_val, 1.0)
    lighten_amt = 1 - norm_val

    if val < 0:
        color = lighten_color("red", lighten_amt)
    else:
        color = lighten_color("#065DDF", lighten_amt)

    return f"background-color: {color}"


def format_conversion(x):
    # Round to 10 decimals to avoid float precision issues
    x = round(x, 10)
    
    if x == int(x):
        return str(int(x))
    elif round(x*10) == x*10:
        return f"{x:.1f}"
    elif round(x*100) == x*100:
        return f"{x:.2f}"
    else:
        return str(x)


st.set_page_config(layout="wide")
st.title("Open Interest")

file_path = "data/OI_T-2_vs_type_disagg_20250827_v3.xlsx"  # change to your actual filename
file_agg = "data/OI_T-2_vs_type_agg_20250828_v1.xlsx"

df = pd.read_excel(file_path)
df_agg = pd.read_excel(file_agg)

# Example: specify the order you want
new_order = [
    "Description",
    "symbol", 
    "OI_T-2", 
    "pct_3m",
    "pct_1y",
    "pct_5y",
    "OI_3m",
    "OI_1y", 
    "OI_5y",
    "conversion_factor",
    "OI_bbl",
    # "Product Family",
]

# Define the custom order for product_fam
fam_order = ["Light", "Middle", "Heavy"]
fam_order_map = {fam: i for i, fam in enumerate(fam_order)}

oi_cols = [c for c in df.columns if c.startswith("OI_")]
pct_cols = [c for c in df.columns if c.startswith("pct")]
product_fam_col = "Product Family"

# Sort the full DataFrame first
df_sorted = (
    df.sort_values(
        by=[product_fam_col, "OI_bbl"],
        ascending=[True, False],   # product_fam ascending, OI_bbl descending
        key=lambda col: col.map(fam_order_map) if col.name == product_fam_col else col
    )
    .reset_index(drop=True)
)

# Then split into top/bottom
df_top = df_sorted[df_sorted["symbol"].isin(["UHO", "UHU", "GAS"])].reset_index(drop=True)
df_top.index = df_top.index + 1
df_top = df_top[new_order]

df_bottom = df_sorted[~df_sorted["symbol"].isin(["UHO", "UHU", "GAS"])]

# Style top
styled_top = (
    df_top.style
    .applymap(color_pct_from_avg, subset=pct_cols)
    .applymap(lambda x: 'background-color: #FFFFE0', subset=['OI_T-2'])
    .format(
        {**{col: "{:,.0f}" for col in oi_cols},      # OI columns with commas, no decimals
        **{col: "{:.1f}%" for col in pct_cols},
        "conversion_factor": format_conversion,
        }
    )
)

st.write("*T-2 OI: Sep25*")
st.write("*3m OI: AVG(Jun25, Jul25, Aug25)*")
st.write("*1y OI: Sep24*")
st.write("*5y OI: AVG(Sep20, Sep21, Sep22, Sep23, Sep24)*")

st.markdown("### Futures")
st.dataframe(styled_top, height=35*(len(df_top)+1) + 2, use_container_width=True)

# Show bottom tables by fam_order
for fam in fam_order:

    subset_agg = df_agg[df_agg[product_fam_col] == fam].reset_index(drop=True)
    subset_agg.index = subset_agg.index + 1
    o = [
        "Product",
        "OI_T-2", 
        "pct_3m",
        "pct_1y",
        "pct_5y",
        "OI_3m",
        "OI_1y", 
        "OI_5y",
        # "Product Family",
    ]
    subset_agg = subset_agg[o]
    if not subset_agg.empty:
        # Style top
        styled_agg = (
            subset_agg.style
            .applymap(color_pct_from_avg, subset=pct_cols)
            .applymap(lambda x: 'background-color: #FFFFE0', subset=['OI_T-2'])
            .format(
                {**{col: "{:,.0f}" for col in oi_cols},      # OI columns with commas, no decimals
                **{col: "{:.1f}%" for col in pct_cols},
                "conversion_factor": format_conversion,
                }
            )
        )

    subset = df_bottom[df_bottom[product_fam_col] == fam].reset_index(drop=True)
    subset.index = subset.index + 1
    subset = subset[new_order]

    if not subset.empty:
        styled_subset = (
            subset.style
            .applymap(color_pct_from_avg, subset=pct_cols)
            .applymap(lambda x: 'background-color: #FFFFE0', subset=['OI_T-2'])
            .format(
                 {**{col: "{:,.0f}" for col in oi_cols},      # OI columns with commas, no decimals
                **{col: "{:.1f}%" for col in pct_cols},
                "conversion_factor": format_conversion,
                }
            )
        )
        
        st.markdown(f"### Swaps - {fam}")
        st.markdown(f"**Main Products OI (in 1,000 BBLs)**")
        st.dataframe(styled_agg, height=35*(len(subset_agg)+1) + 2, use_container_width=True)
        st.markdown(f"**Product Codes OI (original units)**")
        st.dataframe(styled_subset, height=35*(len(subset)+1) + 2, use_container_width=True)