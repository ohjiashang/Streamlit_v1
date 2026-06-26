"""Spread Library — 9/10-year EW_adj chart for every diff in the universe.

Reads precomputed parquets from data/spreads/<safe_diff>.parquet.
For each diff (1mbox shape, Y2026 top-1 cell config):
  - Renders EW_adj over full history with rolling median + entry bands
  - Toggle: full history vs. Jan 2025 onwards (recent zoom)
  - Family + diff dropdowns to navigate
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Spread Library", layout="wide")

PAGE_DIR = Path(__file__).resolve().parent
SPREAD_DIR = PAGE_DIR.parent / "data" / "spreads"
INDEX_FP = SPREAD_DIR / "index.json"

PG_LABEL = {"Dist": "Distillates", "Lights": "Lights",
             "FO": "Fuel Oil", "Crude": "Crude", "GTGN": "GT/GN"}


@st.cache_data(ttl=900)
def load_index() -> list[dict]:
    if not INDEX_FP.exists():
        return []
    return json.loads(INDEX_FP.read_text())


@st.cache_data(ttl=900)
def load_spread(filename: str) -> pd.DataFrame:
    fp = SPREAD_DIR / filename
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


# ── Header ───────────────────────────────────────────────────────
st.title("Spread Library")
st.caption("Per-diff 9-year normalised EW_adj history with rolling median + entry bands. "
            "Top-1 cell of each diff (1mbox shape, Y2026 classifier).")
st.divider()

# ── Load index ───────────────────────────────────────────────────
index = load_index()
if not index:
    st.error(f"No data found. Expected: {INDEX_FP}")
    st.info("Run `analytics/_generate_spread_library.py` to produce the data files, "
             "then commit & push the `data/spreads/` directory.")
    st.stop()

# ── Sidebar: family + diff ───────────────────────────────────────
st.sidebar.header("Filters")

groups_present = sorted({e["product_group"] for e in index})
fam_choice = st.sidebar.selectbox(
    "Product family",
    options=groups_present,
    format_func=lambda g: f"{g} — {PG_LABEL.get(g, g)}",
    index=0,
)

diffs_in_family = sorted({e["diff"] for e in index
                            if e["product_group"] == fam_choice})
diff_choice = st.sidebar.selectbox("Diff", options=diffs_in_family, index=0)

# ── View toggle ──────────────────────────────────────────────────
view = st.sidebar.radio(
    "Date range",
    options=["Full history", "Jan 2025 onwards"],
    index=0,
    help="Toggle between the full 9-year view and a recent-action zoom.",
)

st.sidebar.divider()

# Find the entry matching the selection
entry = next((e for e in index
              if e["product_group"] == fam_choice
              and e["diff"] == diff_choice), None)

if entry is None:
    st.warning("No matching data for selection.")
    st.stop()

# ── Top strip: meta info ─────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("Family", PG_LABEL.get(fam_choice, fam_choice))
with m2:
    st.metric("Diff", diff_choice)
with m3:
    st.metric("Last bar", entry["last_bar"])
with m4:
    st.metric("Last EW_adj", f"{entry['last_ew_adj']:.3f}")
with m5:
    if entry.get("last_med") is not None:
        st.metric("Last median", f"{entry['last_med']:.3f}")

st.caption(
    f"**Cell:** `{entry['cell']}`  ·  "
    f"**W:** {entry['W']}m  ·  "
    f"**SE:** {entry['SE']}σ  ·  "
    f"**SL:** {entry['SL']}σ  ·  "
    f"**Data:** {entry['first_bar']} → {entry['last_bar']}"
)

# ── Chart ─────────────────────────────────────────────────────────
df = load_spread(entry["data_file"])

# Apply date filter for view toggle
if view == "Jan 2025 onwards":
    df = df[df["Date"] >= pd.Timestamp("2025-01-01")].reset_index(drop=True)

fig, ax = plt.subplots(figsize=(14, 6))

if "rolling_median" in df:
    ax.plot(df["Date"], df["rolling_median"], color="grey",
             linewidth=1.0, alpha=0.7,
             label=f"rolling median ({entry['W']}m)")
if "upper_bound" in df and "lower_bound" in df:
    ax.plot(df["Date"], df["upper_bound"], color="steelblue",
             linewidth=0.9, linestyle="--", alpha=0.7,
             label=f"upper (med + {entry['SE']}σ)")
    ax.plot(df["Date"], df["lower_bound"], color="firebrick",
             linewidth=0.9, linestyle="--", alpha=0.7,
             label=f"lower (med − {entry['SE']}σ)")
    ax.fill_between(df["Date"], df["upper_bound"], df["lower_bound"],
                     color="grey", alpha=0.05)

ax.plot(df["Date"], df["EW_adj"], color="black", linewidth=1.2,
         label="EW_adj (normalised spread)")
ax.axhline(0, color="grey", linewidth=0.6)

# Mark current
last_row = df.iloc[-1]
ax.scatter([last_row["Date"]], [last_row["EW_adj"]],
            s=80, color="orange", zorder=5,
            edgecolors="black", linewidths=0.8,
            label=f"current ({last_row['EW_adj']:.3f})")

ax.set_title(
    f"{diff_choice} 1mbox · {entry['fname']} W{entry['W']}M_SE{entry['SE']}_SL{entry['SL']}",
    fontsize=12, fontweight="bold",
)
ax.set_ylabel(r"EW_adj (normalised \$/bbl)")
ax.set_xlabel("Date")
ax.legend(loc="upper left", fontsize=9, ncol=2, framealpha=0.92)
ax.grid(alpha=0.3)
ax.xaxis.set_major_locator(mdates.YearLocator() if view == "Full history"
                            else mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter(
    "%Y" if view == "Full history" else "%b%y"
))
if view == "Jan 2025 onwards":
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
st.pyplot(fig, clear_figure=True)

# ── Below-chart summary ──────────────────────────────────────────
st.subheader("Distribution & extremes (current view)")
if not df.empty:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Mean", f"{df['EW_adj'].mean():.3f}")
    with c2:
        st.metric("Std", f"{df['EW_adj'].std():.3f}")
    with c3:
        st.metric("Max", f"{df['EW_adj'].max():.3f}")
    with c4:
        st.metric("Min", f"{df['EW_adj'].min():.3f}")

st.divider()
st.caption(f"Data: `data/spreads/{entry['data_file']}` "
            f"(precomputed via `analytics/_generate_spread_library.py`)")
