import streamlit as st
import pandas as pd
import numpy as np
import urllib.parse
import warnings
warnings.filterwarnings("ignore")

import matplotlib.colors as mcolors

st.set_page_config(layout="wide")

# ── Config ────────────────────────────────────────────────────────

FIREBASE_BUCKET = "hotei-streamlit.firebasestorage.app"
FIREBASE_FOLDER = "ResidOI"
FILENAME = "resid_oi_latest.xlsx"
LOCAL_FILE = r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\ResidOI\resid_oi_latest.xlsx"

FAMILY_ORDER = ["Light", "Middle", "Heavy"]

# ── Styling ───────────────────────────────────────────────────────

def lighten_color(color, amount):
    color_rgb = mcolors.to_rgb(color)
    white = (1, 1, 1)
    blended = tuple((1 - amount) * c + amount * w for c, w in zip(color_rgb, white))
    return mcolors.to_hex(blended)

def color_voi(val):
    """Color V/OI: higher = more red (active turnover)."""
    try:
        num = float(str(val).replace('%', ''))
    except (ValueError, TypeError):
        return ""
    if num == 0 or pd.isna(num):
        return ""
    max_val = 50  # 50% V/OI is max intensity
    norm = min(abs(num) / max_val, 1.0)
    lighten_amt = 1 - norm
    color = lighten_color("#D4380D", lighten_amt)
    text_color = "white" if lighten_amt < 0.5 else "black"
    return f"background-color: {color}; color: {text_color}"

def color_vol_chg(val):
    """Color volume % chg: blue=higher than Y-1, red=lower."""
    try:
        num = float(str(val).replace('%', '').replace('+', ''))
    except (ValueError, TypeError):
        return ""
    if pd.isna(num) or num == 0:
        return ""
    max_val = 200
    norm = min(abs(num) / max_val, 1.0)
    lighten_amt = 1 - norm
    if num < 0:
        color = lighten_color("red", lighten_amt)
    else:
        color = lighten_color("#065DDF", lighten_amt)
    text_color = "white" if lighten_amt < 0.5 else "black"
    return f"background-color: {color}; color: {text_color}"

# ── Fetch data ────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data():
    import os
    def _read(source):
        return {
            'symbol_data': pd.read_excel(source, sheet_name='symbol_data'),
            'meta': pd.read_excel(source, sheet_name='meta'),
            'info': pd.read_excel(source, sheet_name='info'),
        }
    if os.path.exists(LOCAL_FILE):
        try:
            return _read(LOCAL_FILE)
        except Exception:
            pass
    encoded = urllib.parse.quote(FILENAME)
    url = f"https://firebasestorage.googleapis.com/v0/b/{FIREBASE_BUCKET}/o/{FIREBASE_FOLDER}%2F{encoded}?alt=media"
    try:
        return _read(url)
    except Exception:
        return None

data = load_data()
if data is None:
    st.warning("Could not load data.")
    st.stop()

df_sym = data['symbol_data']
df_meta = data['meta']
df_info = data.get('info', pd.DataFrame())

# Extract date
if not df_info.empty and 'run_date' in df_info.columns:
    resid_date_str = str(df_info['run_date'].iloc[0])
else:
    resid_date_str = "N/A"

st.title(f"Volume Screener — {resid_date_str}")

# Build lookups
conv_map = dict(zip(df_meta['symbol'], df_meta['conversion_factor']))
desc_map = dict(zip(df_meta['symbol'], df_meta['description']))
family_map = dict(zip(df_meta['symbol'], df_meta['family']))
product_map = dict(zip(df_meta['symbol'], df_meta['products']))

# ── Build leaderboard ─────────────────────────────────────────────

df = df_sym.copy()
df = df[df['contract'] != 'Mar26']  # exclude expired

df['description'] = df['symbol'].map(desc_map)
df['family'] = df['symbol'].map(family_map)
df['product'] = df['symbol'].map(product_map)
df['conv'] = df['symbol'].map(conv_map).fillna(1.0)
df['vol_bbl'] = df['vol_2d'] * df['conv']
df['oi_bbl'] = df['t2_oi'] * df['conv']

# V/OI
df['v_oi_pct'] = np.where(df['t2_oi'] > 0, df['vol_2d'] / df['t2_oi'] * 100, 0)

# Vol % chg vs Y-1
if 'vol_y1' in df.columns:
    df['vol_chg_y1'] = np.where(
        df['vol_y1'] > 0,
        (df['vol_2d'] / df['vol_y1'] - 1) * 100,
        None
    )
else:
    df['vol_chg_y1'] = None

# ── Sidebar filters ───────────────────────────────────────────────

families = st.sidebar.multiselect("Family", FAMILY_ORDER, default=FAMILY_ORDER)
min_vol = st.sidebar.number_input("Min 2d Volume (lots)", min_value=0, value=10, step=10)

filtered = df[df['family'].isin(families) & (df['vol_2d'] >= min_vol)].copy()
filtered = filtered.sort_values('vol_bbl', ascending=False).reset_index(drop=True)
filtered.index = filtered.index + 1

st.sidebar.markdown("---")
st.sidebar.markdown(f"*Showing {len(filtered)} rows*")
st.sidebar.markdown("*V/OI = 2d Vol / T-2 OI*")

# ── Display ───────────────────────────────────────────────────────

display_cols = {
    'product': 'Product',
    'contract': 'Contract',
    'symbol': 'Symbol',
    'description': 'Description',
    'vol_2d': '2d Vol (lots)',
    'vol_bbl': '2d Vol (BBL)',
    't2_oi': 'T-2 OI',
    'v_oi_pct': 'V/OI %',
}

has_y1 = 'vol_y1' in df.columns
if has_y1:
    display_cols['vol_y1'] = 'Y-1 Vol'
    display_cols['vol_chg_y1'] = 'Vol %chg Y-1'

display = filtered[list(display_cols.keys())].rename(columns=display_cols)

# Format
fmt = {
    '2d Vol (lots)': '{:,.0f}',
    '2d Vol (BBL)': '{:,.0f}',
    'T-2 OI': '{:,.0f}',
    'V/OI %': '{:.1f}%',
}
if has_y1:
    fmt['Y-1 Vol'] = '{:,.0f}'
    fmt['Vol %chg Y-1'] = '{:+.0f}%'

styled = display.style.format(fmt, na_rep='—')

# Color V/OI and Vol chg columns
if 'V/OI %' in display.columns:
    styled = styled.applymap(color_voi, subset=['V/OI %'])
if has_y1 and 'Vol %chg Y-1' in display.columns:
    styled = styled.applymap(color_vol_chg, subset=['Vol %chg Y-1'])

st.dataframe(styled, height=35 * (min(len(display), 50) + 1) + 2, use_container_width=True)
