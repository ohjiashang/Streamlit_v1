"""Spread Library — gallery of all diffs' EW_adj at once.

2-column grid of interactive Plotly mini-charts.
Toggle: full history vs Jan 2025+.
Visual scan for mean-reverting vs trending series.
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Spread Library", layout="wide")

PAGE_DIR = Path(__file__).resolve().parent
SPREAD_DIR = PAGE_DIR.parent / "data" / "spreads"
INDEX_FP = SPREAD_DIR / "index.json"

PG_LABEL = {"Dist": "Distillates", "Lights": "Lights",
             "FO": "Fuel Oil", "Crude": "Crude", "GTGN": "GT/GN"}
PG_ORDER = ["Crude", "Dist", "FO", "Lights", "GTGN"]
PG_COLOR = {"Crude": "#1f77b4", "Dist": "#d62728", "FO": "#2ca02c",
             "Lights": "#9467bd", "GTGN": "#ff7f0e"}


@st.cache_data(ttl=900)
def load_index() -> list[dict]:
    if not INDEX_FP.exists():
        return []
    return json.loads(INDEX_FP.read_text())


@st.cache_data(ttl=900)
def load_spread(filename: str, W: int, SE: float) -> pd.DataFrame:
    fp = SPREAD_DIR / filename
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    # Compute rolling median + bands if not already present
    if "rolling_median" not in df.columns:
        # ~22 trading days per month
        win = max(int(W * 22), 5)
        df["rolling_median"] = df["EW_adj"].rolling(win, min_periods=win).median()
        df["rolling_std"] = df["EW_adj"].rolling(win, min_periods=win).std()
        df["upper_bound"] = df["rolling_median"] + SE * df["rolling_std"]
        df["lower_bound"] = df["rolling_median"] - SE * df["rolling_std"]
    return df


def build_chart(df: pd.DataFrame, diff_name: str, pg: str,
                 shape: str, last_med: float | None) -> go.Figure:
    fig = go.Figure()
    # Bands
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["upper_bound"],
        line=dict(color="lightblue", width=0.6, dash="dot"),
        showlegend=False, hoverinfo="skip", name="upper",
    ))
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["lower_bound"],
        line=dict(color="lightblue", width=0.6, dash="dot"),
        fill="tonexty", fillcolor="rgba(173,216,230,0.12)",
        showlegend=False, hoverinfo="skip", name="lower",
    ))
    # Median
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["rolling_median"],
        line=dict(color="grey", width=0.9),
        showlegend=False, name="median",
    ))
    # Spread
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["EW_adj"],
        line=dict(color="black", width=1.2),
        showlegend=False, name="EW_adj",
        hovertemplate="%{x|%Y-%m-%d}: %{y:.3f}<extra></extra>",
    ))
    # Current marker
    last = df.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last["Date"]], y=[last["EW_adj"]],
        mode="markers",
        marker=dict(symbol="diamond", size=9, color="orange",
                     line=dict(width=1, color="black")),
        showlegend=False, hoverinfo="skip",
    ))
    pg_color = PG_COLOR.get(pg, "#333")
    fig.update_layout(
        height=240,
        margin=dict(t=30, b=20, l=8, r=8),
        title=dict(
            text=f"<b><span style='color:{pg_color}'>{pg}</span></b> · {diff_name} "
                  f"<span style='color:gray;font-size:10px'>({shape})</span> "
                  f"<span style='color:gray;font-size:11px'>last={last['EW_adj']:.2f}</span>",
            font=dict(size=12),
            x=0.02, xanchor="left",
        ),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        hovermode="x unified",
        plot_bgcolor="white",
    )
    return fig


# ── Header ───────────────────────────────────────────────────────
st.title("Spread Library")
st.caption(
    "Gallery of all 38 diffs · classifier-recommended top-1 cell per diff (Y2026 OOS, "
    "best across outright/1mbox/3mbox). Use this to scan visually for mean-reverting "
    "vs trending series."
)

# ── Load index ───────────────────────────────────────────────────
index = load_index()
if not index:
    st.error(f"No data found. Expected: {INDEX_FP}")
    st.stop()

# ── Sidebar: view toggle only ────────────────────────────────────
st.sidebar.header("View")
view = st.sidebar.radio(
    "Date range",
    options=["Full history", "Jan 2025 onwards"],
    index=0,
)
st.sidebar.divider()

# Filter index by product group (optional)
pg_filter = st.sidebar.multiselect(
    "Filter by family (optional)",
    options=PG_ORDER,
    default=PG_ORDER,
    format_func=lambda g: PG_LABEL.get(g, g),
)
st.sidebar.caption(f"{len(index)} diffs total.")

# Sort entries: group by product_group, then by diff
def sort_key(e):
    pg_idx = PG_ORDER.index(e["product_group"]) if e["product_group"] in PG_ORDER else 99
    return (pg_idx, e["diff"])

entries = [e for e in index if e["product_group"] in pg_filter]
entries = sorted(entries, key=sort_key)

# ── Quick scan strip ─────────────────────────────────────────────
n1, n2, n3, n4 = st.columns(4)
with n1:
    st.metric("Diffs shown", len(entries))
with n2:
    st.metric("Range", view)
with n3:
    last_bars = sorted({e["last_bar"] for e in entries})
    st.metric("Latest bar", last_bars[-1] if last_bars else "n/a")
with n4:
    st.metric("Source", "Y2026 top-1 (all shapes)")

st.divider()

# ── 2-column grid ────────────────────────────────────────────────
for i in range(0, len(entries), 2):
    col1, col2 = st.columns(2, gap="small")
    for col, e in zip([col1, col2], entries[i:i + 2]):
        with col:
            df = load_spread(e["data_file"], e["W"], e["SE"])
            if view == "Jan 2025 onwards":
                df = df[df["Date"] >= pd.Timestamp("2025-01-01")].reset_index(drop=True)
            if df.empty:
                st.caption(f"{e['diff']}: no data in selected range")
                continue
            fig = build_chart(df, e["diff"], e["product_group"],
                                e.get("shape", ""), e.get("last_med"))
            st.plotly_chart(fig, use_container_width=True,
                              config={"displayModeBar": False})

st.divider()

# ── Path B: full formula engine ───────────────────────────────────
st.header("Custom formula explorer")
st.caption(
    "Type any synthetic spread using **raw products** or **leg aliases**, with per-leg offsets. "
    "Examples:  `BSP[1] - DBI[1]`  ·  `SYS[3] - SGO[2] + ICEGO[3]`  ·  `S380-GO_EW M323`  ·  "
    "`BOX(BSP, 1, 1)` (= `BSP[1] - BSP[2]`)  ·  `BOX(BSP, 1, 3)` (3-month box = `BSP[1] - BSP[4]`)."
)

RAW_PRODUCTS_DIR = PAGE_DIR.parent / "data" / "raw_products"


@st.cache_data(ttl=900)
def load_aliases() -> dict:
    fp = RAW_PRODUCTS_DIR / "aliases.json"
    if not fp.exists():
        return {}
    return json.loads(fp.read_text())


@st.cache_data(ttl=900)
def load_product_offset(prod: str, off: int) -> pd.DataFrame:
    fp = RAW_PRODUCTS_DIR / prod / f"M{off}.parquet"
    if not fp.exists():
        return pd.DataFrame()
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def list_available_products() -> list[str]:
    if not RAW_PRODUCTS_DIR.exists():
        return []
    return sorted([p.name for p in RAW_PRODUCTS_DIR.iterdir()
                    if p.is_dir() and any(p.glob("M*.parquet"))])


def parse_formula(formula: str, aliases: dict,
                    default_offset: int = 1) -> list[tuple[float, str, int]]:
    """Parse a flat formula string → list of (sign, product, offset) terms.
    Supports raw products (BSP, SYS, ...) and aliases (Brt, GO_EW, SGO, ...).
    Offsets default to `default_offset` when not specified.
    Recursively expands aliases.
    No paren support — aliases handle nested expressions.
    """
    import re
    text = formula.replace("−", "-").strip()
    if not text:
        return []
    tok_re = re.compile(r"\s*([A-Za-z_][A-Za-z_0-9.+]*|\[|\]|[+\-]|\d+)")
    pos, tokens = 0, []
    while pos < len(text):
        m = tok_re.match(text, pos)
        if not m:
            raise ValueError(f"Bad token near '{text[pos:pos+12]}'")
        tokens.append(m.group(1))
        pos = m.end()

    out_terms = []
    cur_sign = 1
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "+":
            cur_sign = 1; i += 1
        elif t == "-":
            cur_sign = -1; i += 1
        elif re.match(r"^[A-Za-z_][A-Za-z_0-9.+]*$", t):
            name = t
            off = None
            if i + 1 < len(tokens) and tokens[i+1] == "[":
                if i + 3 < len(tokens) and tokens[i+3] == "]":
                    off = int(tokens[i+2])
                    i += 4
                else:
                    raise ValueError(f"Bad offset bracket after {name}")
            else:
                i += 1
            if name in aliases:
                # Recursively parse alias body. If user gave an explicit offset
                # on the alias, propagate it as the default for sub-legs.
                sub_default = off if off is not None else default_offset
                sub_terms = parse_formula(aliases[name], aliases,
                                            default_offset=sub_default)
                for s_sub, p_sub, o_sub in sub_terms:
                    out_terms.append((cur_sign * s_sub, p_sub, o_sub))
            else:
                final_off = off if off is not None else default_offset
                out_terms.append((cur_sign, name, final_off))
            cur_sign = 1   # reset after consuming a term (default + for next)
        else:
            i += 1
    return out_terms


def expand_box(formula: str) -> str:
    """Replace `BOX(LEG, M1, MN)` with `LEG[M1] - LEG[M1+MN]`."""
    import re
    pattern = re.compile(r"BOX\(\s*([A-Za-z_][A-Za-z_0-9.+]*)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
    def sub(m):
        leg, m1, mn = m.group(1), int(m.group(2)), int(m.group(3))
        return f"({leg}[{m1}] - {leg}[{m1+mn}])"
    return pattern.sub(sub, formula)


# ── Path B UI ────────────────────────────────────────────────────
aliases = load_aliases()
available_products = list_available_products()
if not available_products:
    st.warning(
        "Raw product data not bundled yet. Run "
        "`analytics/_generate_raw_product_series.py` to produce data files "
        "under `data/raw_products/`, then commit & push."
    )
else:
    fc1, fc2 = st.columns([3, 1])
    with fc1:
        formula_input = st.text_input(
            "Formula",
            value="BSP[1] - DBI[1]",
            help="Examples: `BSP[1] - DBI[1]`, `SYS[3] - SGO[2] + ICEGO[3]`, "
                  "`BOX(BSP, 1, 1)`, `S380-GO_EW` (uses default offset=1)",
            key="formula_input",
        )
    with fc2:
        rolling_W_form = st.number_input(
            "W (m)", min_value=3, max_value=24, value=12, step=1,
            key="formula_W",
        )

    try:
        expanded_form = expand_box(formula_input)
        terms = parse_formula(expanded_form, aliases)
        # Filter to known products
        unknown = [(s, p, o) for s, p, o in terms if p not in available_products]
        if unknown:
            unknown_names = sorted({p for _, p, _ in unknown})
            st.error(
                f"Unknown product(s): {unknown_names}. Available raw products: "
                f"{available_products}"
            )
        else:
            # Compose terms display
            terms_str = " ".join(
                f"{'+ ' if s > 0 and i > 0 else ('- ' if s < 0 else '')}{p}[{o}]"
                for i, (s, p, o) in enumerate(terms)
            )
            st.caption(f"**Expanded:** `{terms_str}`")

            # Build series: load each (product, offset), align dates, sum with signs
            series = None
            for s, p, o in terms:
                df_po = load_product_offset(p, o)
                if df_po.empty:
                    st.error(f"Missing data for {p}[{o}].")
                    st.stop()
                ren = df_po.rename(columns={"EW_adj": f"{p}_{o}"}).set_index("Date")
                if series is None:
                    series = pd.DataFrame(index=ren.index)
                series[f"_{len(series.columns)}"] = (
                    s * ren[f"{p}_{o}"].reindex(series.index)
                    if not series.empty
                    else s * ren[f"{p}_{o}"]
                )
            if series is None or series.empty:
                st.warning("Could not build series.")
            else:
                series_aligned = series.dropna()
                ew = series_aligned.sum(axis=1)
                df_form = pd.DataFrame({"Date": ew.index, "EW_adj": ew.values})
                # Rolling med + bands
                win = max(int(rolling_W_form * 22), 5)
                df_form["rolling_median"] = df_form["EW_adj"].rolling(
                    win, min_periods=win).median()
                df_form["rolling_std"] = df_form["EW_adj"].rolling(
                    win, min_periods=win).std()
                df_form["upper_bound"] = df_form["rolling_median"] + 2.0 * df_form["rolling_std"]
                df_form["lower_bound"] = df_form["rolling_median"] - 2.0 * df_form["rolling_std"]
                if view == "Jan 2025 onwards":
                    df_form = df_form[df_form["Date"] >= pd.Timestamp("2025-01-01")
                                       ].reset_index(drop=True)

                last_row = df_form.iloc[-1]
                fm1, fm2, fm3, fm4 = st.columns(4)
                with fm1:
                    st.metric("Last EW_adj", f"{last_row['EW_adj']:.3f}")
                with fm2:
                    st.metric("Last median",
                               f"{last_row['rolling_median']:.3f}"
                               if pd.notna(last_row["rolling_median"]) else "n/a")
                with fm3:
                    st.metric("Std (current view)",
                               f"{df_form['EW_adj'].std():.3f}")
                with fm4:
                    st.metric("Last bar", str(last_row["Date"].date()))

                fig_f = go.Figure()
                fig_f.add_trace(go.Scatter(
                    x=df_form["Date"], y=df_form["upper_bound"],
                    line=dict(color="lightblue", width=0.8, dash="dot"),
                    showlegend=False, hoverinfo="skip", name="upper"))
                fig_f.add_trace(go.Scatter(
                    x=df_form["Date"], y=df_form["lower_bound"],
                    line=dict(color="lightblue", width=0.8, dash="dot"),
                    fill="tonexty", fillcolor="rgba(173,216,230,0.12)",
                    showlegend=False, hoverinfo="skip", name="lower"))
                fig_f.add_trace(go.Scatter(
                    x=df_form["Date"], y=df_form["rolling_median"],
                    line=dict(color="grey", width=1.0),
                    name=f"median ({rolling_W_form}m)"))
                fig_f.add_trace(go.Scatter(
                    x=df_form["Date"], y=df_form["EW_adj"],
                    line=dict(color="black", width=1.3),
                    name=formula_input,
                    hovertemplate="%{x|%Y-%m-%d}: %{y:.3f}<extra></extra>"))
                fig_f.add_trace(go.Scatter(
                    x=[last_row["Date"]], y=[last_row["EW_adj"]],
                    mode="markers",
                    marker=dict(symbol="diamond", size=12, color="orange",
                                 line=dict(width=1, color="black")),
                    showlegend=False, hoverinfo="skip"))
                fig_f.update_layout(
                    height=420,
                    margin=dict(t=40, b=20, l=10, r=10),
                    title=dict(text=f"<b>{formula_input}</b>",
                                font=dict(size=13)),
                    legend=dict(orientation="h", yanchor="top", y=-0.1),
                    plot_bgcolor="white",
                    hovermode="x unified",
                )
                fig_f.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
                fig_f.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
                st.plotly_chart(fig_f, use_container_width=True)

    except ValueError as e:
        st.error(f"Formula parse error: {e}")

st.divider()
st.caption(
    "Gallery charts read precomputed diffs at `data/spreads/`. "
    "Formula explorer uses raw product Mn series at `data/raw_products/`. "
    "Generated via `_generate_spread_library.py` and `_generate_raw_product_series.py`."
)
