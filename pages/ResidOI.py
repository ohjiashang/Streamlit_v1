import streamlit as st
import pandas as pd
import urllib.parse
import warnings
warnings.filterwarnings("ignore")

import matplotlib.colors as mcolors

st.set_page_config(layout="wide")
st.title("Residual OI")

# ── Config ────────────────────────────────────────────────────────

FIREBASE_BUCKET = "hotei-streamlit.firebasestorage.app"
FIREBASE_FOLDER = "ResidOI"
FILENAME = "resid_oi_latest.xlsx"

LOCAL_FILE = r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\ResidOI\resid_oi_latest.xlsx"

FAMILY_ORDER = ["Light", "Middle"]

PRODUCT_ORDER = {
    "Light": ["S92", "Ebob", "Rbob", "MOPJ Naph", "NWE Naph"],
    "Middle": ["SGO", "SKO", "ICEGO", "NWE Jet", "HO"],
}

# ── Styling ───────────────────────────────────────────────────────

def lighten_color(color, amount):
    color_rgb = mcolors.to_rgb(color)
    white = (1, 1, 1)
    blended = tuple((1 - amount) * c + amount * w for c, w in zip(color_rgb, white))
    return mcolors.to_hex(blended)

def color_pct(val):
    if pd.isna(val) or val == 0:
        return ""
    max_val = 100
    norm_val = min(abs(val) / max_val, 1.0)
    lighten_amt = 1 - norm_val
    if val < 0:
        color = lighten_color("red", lighten_amt)
    else:
        color = lighten_color("#065DDF", lighten_amt)
    return f"background-color: {color}"

def highlight_oi(val):
    return 'background-color: #FFFFE0'

# ── Fetch data ────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_resid_oi():
    import os
    if os.path.exists(LOCAL_FILE):
        try:
            return {
                'symbol_data': pd.read_excel(LOCAL_FILE, sheet_name='symbol_data'),
                'meta': pd.read_excel(LOCAL_FILE, sheet_name='meta'),
            }
        except Exception:
            pass
    encoded = urllib.parse.quote(FILENAME)
    url = f"https://firebasestorage.googleapis.com/v0/b/{FIREBASE_BUCKET}/o/{FIREBASE_FOLDER}%2F{encoded}?alt=media"
    try:
        return {
            'symbol_data': pd.read_excel(url, sheet_name='symbol_data'),
            'meta': pd.read_excel(url, sheet_name='meta'),
        }
    except Exception:
        return None

data = load_resid_oi()

if data is None:
    st.warning("Could not load residual OI data. Has the pipeline been run?")
    st.stop()

df_sym = data['symbol_data']
df_meta = data['meta']

# Build lookups from meta
conv_map = dict(zip(df_meta['symbol'], df_meta['conversion_factor']))
desc_map = dict(zip(df_meta['symbol'], df_meta['description']))
futures_set = set(df_meta[df_meta['is_futures'] == True]['symbol'])

# Build product -> symbols mapping from meta
prod_sym_map = {}
for _, row in df_meta.iterrows():
    for prod in str(row['products']).split(', '):
        prod = prod.strip()
        if prod:
            prod_sym_map.setdefault(prod, []).append(row['symbol'])

# ── Sidebar ───────────────────────────────────────────────────────

family_choice = st.sidebar.radio("Family", ["All"] + FAMILY_ORDER)

if family_choice == "All":
    all_products = []
    for fam in FAMILY_ORDER:
        all_products.extend(PRODUCT_ORDER[fam])
else:
    all_products = PRODUCT_ORDER[family_choice]

selected_products = st.sidebar.multiselect(
    "Products",
    options=all_products,
    default=all_products,
)

show_futures = st.sidebar.checkbox("Show ICE Futures", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("*Resid OI = T-2 OI − 2d Vol*")
st.sidebar.markdown("*% chg = vs 27 Feb baseline*")

# ── Helper: build product summary table (converted to 1,000 BBL) ──

def build_product_table(products):
    """Pivot: rows=contracts, columns=products, values=resid OI in 1,000 BBL."""
    all_rows = []
    for prod in products:
        syms = prod_sym_map.get(prod, [])
        prod_data = df_sym[df_sym['symbol'].isin(syms)].copy()
        prod_data['resid_bbl'] = prod_data.apply(
            lambda r: r['resid_oi'] * conv_map.get(r['symbol'], 1.0), axis=1
        )
        prod_data['ref_bbl'] = prod_data.apply(
            lambda r: r['ref_oi'] * conv_map.get(r['symbol'], 1.0), axis=1
        )
        agg = prod_data.groupby('contract').agg(
            resid_bbl=('resid_bbl', 'sum'),
            ref_bbl=('ref_bbl', 'sum'),
        ).reset_index()
        agg['product'] = prod
        all_rows.append(agg)

    if not all_rows:
        return pd.DataFrame()

    df_all = pd.concat(all_rows, ignore_index=True)
    df_all['pct_chg'] = df_all.apply(
        lambda r: round((r['resid_bbl'] / r['ref_bbl'] - 1) * 100, 1) if r['ref_bbl'] else None, axis=1
    )

    # Pivot for resid OI
    pivot_resid = df_all.pivot(index='contract', columns='product', values='resid_bbl')
    pivot_resid = pivot_resid.reindex(columns=products)

    # Pivot for pct chg
    pivot_pct = df_all.pivot(index='contract', columns='product', values='pct_chg')
    pivot_pct = pivot_pct.reindex(columns=products)

    return pivot_resid, pivot_pct

def build_symbol_table(products):
    """Pivot: rows=contracts, columns=symbols, values=resid OI (original units)."""
    syms = []
    for prod in products:
        for s in prod_sym_map.get(prod, []):
            if s not in futures_set and s not in syms:
                syms.append(s)

    sym_data = df_sym[df_sym['symbol'].isin(syms)]
    if sym_data.empty:
        return pd.DataFrame(), pd.DataFrame()

    pivot_resid = sym_data.pivot(index='contract', columns='symbol', values='resid_oi')
    pivot_resid = pivot_resid.reindex(columns=syms)

    pivot_pct = sym_data.pivot(index='contract', columns='symbol', values='pct_chg')
    pivot_pct = pivot_pct.reindex(columns=syms)

    return pivot_resid, pivot_pct

def build_futures_table():
    """Pivot: rows=contracts, columns=futures symbols, values=resid OI."""
    fut_syms = sorted(futures_set)
    fut_data = df_sym[df_sym['symbol'].isin(fut_syms)]
    if fut_data.empty:
        return pd.DataFrame(), pd.DataFrame()

    pivot_resid = fut_data.pivot(index='contract', columns='symbol', values='resid_oi')
    pivot_resid = pivot_resid.reindex(columns=fut_syms)

    pivot_pct = fut_data.pivot(index='contract', columns='symbol', values='pct_chg')
    pivot_pct = pivot_pct.reindex(columns=fut_syms)

    return pivot_resid, pivot_pct

def combine_resid_pct(pivot_resid, pivot_pct):
    """Merge resid OI and % chg into combined string cells: '5,000 (+10.5%)'."""
    mask = pivot_resid.notna().any(axis=1)
    pivot_resid = pivot_resid[mask].copy()
    pivot_pct = pivot_pct.reindex(pivot_resid.index)

    # Build combined display DataFrame (strings)
    combined = pd.DataFrame(index=pivot_resid.index, columns=pivot_resid.columns)
    # Keep numeric pct for color coding
    pct_numeric = pd.DataFrame(index=pivot_resid.index, columns=pivot_resid.columns)

    for col in pivot_resid.columns:
        for idx in pivot_resid.index:
            resid_val = pivot_resid.at[idx, col]
            pct_val = pivot_pct.at[idx, col] if col in pivot_pct.columns else None
            if pd.isna(resid_val):
                combined.at[idx, col] = ''
                pct_numeric.at[idx, col] = None
            elif pd.notna(pct_val):
                sign = '+' if pct_val >= 0 else ''
                combined.at[idx, col] = f"{resid_val:,.0f} ({sign}{pct_val:.1f}%)"
                pct_numeric.at[idx, col] = pct_val
            else:
                combined.at[idx, col] = f"{resid_val:,.0f}"
                pct_numeric.at[idx, col] = None

    return combined, pct_numeric

def style_pivot(pivot_resid, pivot_pct):
    """Style: combined 'resid (% chg)' cells with color coding."""
    combined, pct_numeric = combine_resid_pct(pivot_resid, pivot_pct)
    if combined.empty:
        return combined.style, 0

    def apply_color(col):
        if col.name in pct_numeric.columns:
            return [color_pct(v) if pd.notna(v) else '' for v in pct_numeric[col.name]]
        return [''] * len(col)

    styled = combined.style.apply(apply_color, axis=0)
    return styled, len(combined)

def render_section(title, products):
    """Render a family section with main products + product codes."""
    prods_in_selection = [p for p in products if p in selected_products]
    if not prods_in_selection:
        return

    st.markdown(f"### Swaps — {title}")

    # Main Products OI (in 1,000 BBLs)
    pivot_resid, pivot_pct = build_product_table(prods_in_selection)
    if not pivot_resid.empty:
        st.markdown("**Main Products Resid OI (1,000 BBLs)**")
        st.markdown("*Resid OI (% chg vs 27 Feb)*")
        styled, n = style_pivot(pivot_resid, pivot_pct)
        st.dataframe(styled, height=35 * (min(n, 15) + 1) + 2, use_container_width=True)

    # Product Codes OI (original units)
    pivot_sym, pivot_sym_pct = build_symbol_table(prods_in_selection)
    if not pivot_sym.empty:
        # Rename columns to include description
        col_names = {s: f"{s} ({desc_map.get(s, '')})" for s in pivot_sym.columns}
        pivot_sym_display = pivot_sym.rename(columns=col_names)
        pivot_sym_pct_display = pivot_sym_pct.rename(columns=col_names)
        st.markdown("**Product Codes Resid OI (original units)**")
        st.markdown("*Resid OI (% chg vs 27 Feb)*")
        styled_sym, n_sym = style_pivot(pivot_sym_display, pivot_sym_pct_display)
        st.dataframe(styled_sym, height=35 * (min(n_sym, 15) + 1) + 2, use_container_width=True)

# ── Display ───────────────────────────────────────────────────────

if not selected_products:
    st.warning("Please select at least one product.")
    st.stop()

# ICE Futures
if show_futures:
    fut_resid, fut_pct = build_futures_table()
    if not fut_resid.empty:
        st.markdown("### ICE Futures")
        st.markdown("*Resid OI (% chg vs 27 Feb)*")
        # Rename columns to include description
        col_names = {s: f"{s} ({desc_map.get(s, '')})" for s in fut_resid.columns}
        fut_display = fut_resid.rename(columns=col_names)
        fut_pct_display = fut_pct.rename(columns=col_names)
        styled_fut, n_fut = style_pivot(fut_display, fut_pct_display)
        st.dataframe(styled_fut, height=35 * (min(n_fut, 15) + 1) + 2, use_container_width=True)

# Swaps by family
if family_choice == "All":
    for fam in FAMILY_ORDER:
        render_section(fam, PRODUCT_ORDER[fam])
else:
    render_section(family_choice, PRODUCT_ORDER[family_choice])
