import streamlit as st
import pandas as pd
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

# ── Contract ordering ─────────────────────────────────────────────

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def contract_sort_key(contract):
    """Convert 'Apr26' to (26, 3) for sorting."""
    month_str = contract[:3]
    yr = int(contract[3:])
    m_idx = MONTH_NAMES.index(month_str) if month_str in MONTH_NAMES else 0
    return (yr, m_idx)

FAMILY_ORDER = ["Light", "Middle", "Heavy"]

PRODUCT_ORDER = {
    "Light": ["S92", "Ebob", "Rbob", "MOPJ Naph", "NWE Naph"],
    "Middle": ["SGO", "SKO", "ICEGO", "NWE Jet", "HO"],
    "Heavy": ["S0.5", "Rdm0.5", "S380", "Rdm3.5"],
    "Crude": ["Brent", "WTI"],
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
    # White text when background is dark (lighten_amt < 0.5 means dark)
    text_color = "white" if lighten_amt < 0.5 else "black"
    return f"background-color: {color}; color: {text_color}"

def highlight_oi(val):
    return 'background-color: #FFFFE0'

# ── Fetch data ────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_resid_oi():
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

data = load_resid_oi()

if data is None:
    st.warning("Could not load residual OI data. Has the pipeline been run?")
    st.stop()

df_sym = data['symbol_data']
df_sym = df_sym[df_sym['contract'] != 'Mar26']  # exclude expired prompt month
df_meta = data['meta']

# Extract the resid OI date for display
df_info = data.get('info', pd.DataFrame())
if not df_info.empty and 'run_date' in df_info.columns:
    resid_date_str = str(df_info['run_date'].iloc[0])
else:
    resid_date_str = "N/A"

st.title(f"Residual OI — {resid_date_str}")

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

show_futures = st.sidebar.checkbox("Show ICE Futures", value=True)

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

st.sidebar.markdown("---")

# Check which comparison metrics are available
metric_options = ["vs 27 Feb"]
if 'pct_chg_y1' in df_sym.columns:
    metric_options.append("vs Y-1")
if 'pct_chg_5y' in df_sym.columns:
    metric_options.append("vs 5Y Avg")

if len(metric_options) > 1:
    global_metric = st.sidebar.radio("Compare % chg", metric_options, horizontal=True)
else:
    global_metric = metric_options[0]

_pct_col_map = {"vs 27 Feb": "pct_chg", "vs Y-1": "pct_chg_y1", "vs 5Y Avg": "pct_chg_5y"}
_ref_col_map = {"vs 27 Feb": "ref_oi", "vs Y-1": "ref_oi_y1", "vs 5Y Avg": "ref_oi_5y"}
global_pct_col = _pct_col_map[global_metric]
global_ref_col = _ref_col_map[global_metric]
metric_label = f"{resid_date_str} Resid OI (% chg {global_metric})"

st.sidebar.markdown("---")
st.sidebar.markdown("*Resid OI = T-2 OI − 2d Vol*")

# ── Helper: build product summary table (converted to 1,000 BBL) ──

def build_product_table(products, pct_col='pct_chg'):
    """Pivot: rows=contracts, columns=products, values=resid OI in 1,000 BBL."""
    ref_col = _ref_col_map.get(global_metric, 'ref_oi')
    all_rows = []
    for prod in products:
        syms = prod_sym_map.get(prod, [])
        prod_data = df_sym[df_sym['symbol'].isin(syms)].copy()
        prod_data['resid_bbl'] = prod_data.apply(
            lambda r: r['resid_oi'] * conv_map.get(r['symbol'], 1.0), axis=1
        )
        prod_data['ref_bbl'] = prod_data.apply(
            lambda r: r.get(ref_col, 0) * conv_map.get(r['symbol'], 1.0), axis=1
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

    pivot_resid = df_all.pivot(index='contract', columns='product', values='resid_bbl')
    pivot_resid = pivot_resid.reindex(columns=products)

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

def build_futures_table(pct_col='pct_chg'):
    """Pivot: rows=contracts, columns=futures symbols, values=resid OI."""
    fut_syms = sorted(futures_set)
    fut_data = df_sym[df_sym['symbol'].isin(fut_syms)]
    if fut_data.empty:
        return pd.DataFrame(), pd.DataFrame()

    pivot_resid = fut_data.pivot(index='contract', columns='symbol', values='resid_oi')
    pivot_resid = pivot_resid.reindex(columns=fut_syms)

    pivot_pct = fut_data.pivot(index='contract', columns='symbol', values=pct_col)
    pivot_pct = pivot_pct.reindex(columns=fut_syms)

    return pivot_resid, pivot_pct

def combine_resid_pct(pivot_resid, pivot_pct):
    """Merge resid OI and % chg into combined string cells: '5,000 (+10%)'."""
    mask = pivot_resid.notna().any(axis=1)
    pivot_resid = pivot_resid[mask].copy()
    # Sort contracts chronologically
    sorted_idx = sorted(pivot_resid.index, key=contract_sort_key)
    pivot_resid = pivot_resid.reindex(sorted_idx)
    pivot_pct = pivot_pct.reindex(sorted_idx)

    # Build combined display DataFrame (strings)
    combined = pd.DataFrame(index=pivot_resid.index, columns=pivot_resid.columns)
    # Keep numeric pct for color coding
    pct_numeric = pd.DataFrame(index=pivot_resid.index, columns=pivot_resid.columns)
    # Track which columns are "Total" for highlighting
    is_total = pd.Series(False, index=pivot_resid.columns)

    for col in pivot_resid.columns:
        # Check if this is a Total column (MultiIndex or string)
        if isinstance(col, tuple):
            is_total[col] = (col[1] == 'TOTAL')
        for idx in pivot_resid.index:
            resid_val = pivot_resid.at[idx, col]
            pct_val = pivot_pct.at[idx, col] if col in pivot_pct.columns else None
            # Separator columns stay blank
            is_sep = isinstance(col, tuple) and col[1].strip() == ''
            if is_sep:
                combined.at[idx, col] = ''
                pct_numeric.at[idx, col] = None
            elif pd.isna(resid_val):
                combined.at[idx, col] = '0'
                pct_numeric.at[idx, col] = None
            elif pd.notna(pct_val):
                sign = '+' if pct_val >= 0 else ''
                combined.at[idx, col] = f"{resid_val:,.0f} ({sign}{pct_val:.0f}%)"
                pct_numeric.at[idx, col] = pct_val
            else:
                combined.at[idx, col] = f"{resid_val:,.0f}"
                pct_numeric.at[idx, col] = None

    return combined, pct_numeric, is_total

def style_pivot(pivot_resid, pivot_pct):
    """Style: combined 'resid (% chg)' cells with color coding."""
    combined, pct_numeric, is_total = combine_resid_pct(pivot_resid, pivot_pct)
    if combined.empty:
        return combined.style, 0

    def apply_color(col):
        styles = []
        is_total_col = is_total.get(col.name, False)
        for i, idx in enumerate(combined.index):
            pct_val = pct_numeric.at[idx, col.name] if col.name in pct_numeric.columns else None
            base_style = color_pct(pct_val) if pd.notna(pct_val) else ''
            if is_total_col:
                base_style += '; font-weight: bold' if base_style else 'font-weight: bold'
            styles.append(base_style)
        return styles

    styled = combined.style.apply(apply_color, axis=0)
    return styled, len(combined)

def build_interleaved_table(products, pct_col='pct_chg'):
    """Build interleaved pivot with MultiIndex columns: (Product, Total/symbol)."""
    ref_col = _ref_col_map.get(global_metric, 'ref_oi')
    resid_series = {}
    pct_series = {}

    for prod in products:
        syms = prod_sym_map.get(prod, [])
        swap_syms = [s for s in syms if s not in futures_set]

        # Product total (converted to BBL)
        prod_data = df_sym[df_sym['symbol'].isin(syms)].copy()
        prod_data['resid_bbl'] = prod_data.apply(
            lambda r: r['resid_oi'] * conv_map.get(r['symbol'], 1.0), axis=1
        )
        prod_data['ref_bbl'] = prod_data.apply(
            lambda r: r.get(ref_col, 0) * conv_map.get(r['symbol'], 1.0), axis=1
        )
        agg = prod_data.groupby('contract').agg(
            resid_bbl=('resid_bbl', 'sum'),
            ref_bbl=('ref_bbl', 'sum'),
        )
        agg['pct'] = agg.apply(
            lambda r: round((r['resid_bbl'] / r['ref_bbl'] - 1) * 100, 1) if r['ref_bbl'] else None, axis=1
        )
        col_key = (prod, 'TOTAL')
        resid_series[col_key] = agg['resid_bbl']
        pct_series[col_key] = agg['pct']

        # Constituent symbols
        for s in swap_syms:
            s_data = df_sym[df_sym['symbol'] == s].set_index('contract')
            desc = desc_map.get(s, s)
            col_key = (prod, f"{desc} ({s})")
            resid_series[col_key] = s_data['resid_oi']
            pct_series[col_key] = s_data[pct_col]

        # Separator column after each product
        sep_key = (prod, ' ')
        resid_series[sep_key] = pd.Series(dtype='float64')
        pct_series[sep_key] = pd.Series(dtype='float64')

    pivot_resid = pd.DataFrame(resid_series)
    pivot_pct = pd.DataFrame(pct_series)
    pivot_resid.columns = pd.MultiIndex.from_tuples(pivot_resid.columns)
    pivot_pct.columns = pd.MultiIndex.from_tuples(pivot_pct.columns)
    return pivot_resid, pivot_pct

def render_section(title, products):
    """Render a family section with interleaved product + constituent columns."""
    prods_in_selection = [p for p in products if p in selected_products]
    if not prods_in_selection:
        return

    show_constituents = st.checkbox("Show constituents", value=False, key=f"const_{title}")

    if show_constituents:
        pivot_resid, pivot_pct = build_interleaved_table(prods_in_selection, global_pct_col)
        if not pivot_resid.empty:
            st.markdown(f"*{metric_label} — totals in BBLs, codes in original units*")
            styled, n = style_pivot(pivot_resid, pivot_pct)
            st.dataframe(styled, height=35 * (n + 1) + 2, use_container_width=True)
    else:
        pivot_resid, pivot_pct = build_product_table(prods_in_selection, global_pct_col)
        if not pivot_resid.empty:
            st.markdown("**Main Products Resid OI (1,000 BBLs)**")
            st.markdown(f"*{metric_label}*")
            styled, n = style_pivot(pivot_resid, pivot_pct)
            st.dataframe(styled, height=35 * (n + 1) + 2, use_container_width=True)

# ── Display ───────────────────────────────────────────────────────

if not selected_products:
    st.warning("Please select at least one product.")
    st.stop()

# ICE Futures
if show_futures:
    st.markdown("### ICE Futures")
    fut_resid, fut_pct = build_futures_table(global_pct_col)
    if not fut_resid.empty:
        st.markdown(f"*{metric_label}*")
        col_names = {s: f"{desc_map.get(s, s)} ({s})" for s in fut_resid.columns}
        fut_display = fut_resid.rename(columns=col_names)
        fut_pct_display = fut_pct.rename(columns=col_names)
        styled_fut, n_fut = style_pivot(fut_display, fut_pct_display)
        st.dataframe(styled_fut, height=35 * (n_fut + 1) + 2, use_container_width=True)

# Swaps by family
if family_choice == "All":
    for fam in FAMILY_ORDER:
        st.markdown(f"### Swaps — {fam}")
        render_section(fam, PRODUCT_ORDER[fam])
else:
    st.markdown(f"### Swaps — {family_choice}")
    render_section(family_choice, PRODUCT_ORDER[family_choice])
