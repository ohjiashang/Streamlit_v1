"""Helpers for the Mean Reversion V2 Y2026 monitoring page.

State files (per-pick parquet + JSON) are served from Firebase Storage under
folder `mpt7_v2/`. Local copy at `BloombergCOT/analytics/monitor_state/mpt7_v2/`
is the source of truth; `_sync_monitor_to_firebase.py` publishes after each
refresh.

The trade log + refresh subprocess are local-only — they no-op gracefully when
running on Streamlit Cloud where the BloombergCOT directory isn't accessible.
"""
from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

FIREBASE_BUCKET = "hotei-streamlit.firebasestorage.app"
FIREBASE_FOLDER = "mpt7_v2"

BLOOMBERG_COT = Path(
    r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\BloombergCOT"
)
LOCAL_MODE = BLOOMBERG_COT.exists()
STATE_DIR = BLOOMBERG_COT / "analytics" / "monitor_state" / "mpt7_v2"
TRADE_LOG_FP = BLOOMBERG_COT / "analytics" / "live_trade_log.csv"
REFRESH_SCRIPT = BLOOMBERG_COT / "analytics" / "_monitor_refresh_mpt7.py"
DATA_REFRESH_SCRIPT = BLOOMBERG_COT / "analytics" / "refresh_18m.py"
SYNC_SCRIPT = BLOOMBERG_COT / "analytics" / "_sync_monitor_to_firebase.py"

YEAR = 2026



# Trader-friendly names for raw ICE product codes used in pick formulas.
# Synthetic legs (SGO, ICEGO, TC5, etc.) keep their config-defined names.
PRODUCT_NAMES = {
    "AEO": "Ebob",
    "RBS": "Rbob",
    "BSP": "Brt",
    "NEC": "NWE Naph",
    "NJC": "MOPJ Naph",
    "SYS": "S380",
    "SZS": "S180",
    "ULJ": "NWE Jet - ICEGO",
    "SMT": "S92",
}

# Compact aliases used in the per-leg breakdown table where the multi-component
# synthetic expansion (e.g. "(NWE Jet - ICEGO) M2") reads awkwardly. Falls back
# to PRODUCT_NAMES when not overridden.
LEG_NAMES_COMPACT = {
    "ULJ": "Jet Diff",
}

TRADE_LOG_COLS = [
    "trade_id", "fname", "cell", "diff", "shape", "weight",
    "side",
    "entry_date", "entry_signal_price", "entry_fill_price", "entry_slippage_per_leg",
    "exit_date", "exit_signal_price", "exit_fill_price", "exit_slippage_per_leg",
    "n_lots", "notes", "closed", "pnl_realized",
    "created_at", "updated_at",
]


def _firebase_url(path: str) -> str:
    encoded = urllib.parse.quote(path, safe="")
    return (f"https://firebasestorage.googleapis.com/v0/b/"
            f"{FIREBASE_BUCKET}/o/{encoded}?alt=media")


def _fetch_bytes(path: str) -> bytes | None:
    try:
        with urllib.request.urlopen(_firebase_url(path), timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


@st.cache_data(ttl=900)
def load_state() -> dict:
    raw = _fetch_bytes(f"{FIREBASE_FOLDER}/state.json")
    if raw is None:
        return {"error": "state.json missing on Firebase — run sync", "picks": []}
    return json.loads(raw.decode("utf-8"))


@st.cache_data(ttl=900)
def load_pick_df(fname: str) -> pd.DataFrame:
    raw = _fetch_bytes(f"{FIREBASE_FOLDER}/{fname}/df.parquet")
    if raw is None:
        return pd.DataFrame()
    df = pd.read_parquet(BytesIO(raw))
    df["Date"] = pd.to_datetime(df["Date"])
    return df


@st.cache_data(ttl=900)
def load_pick_trades(fname: str) -> pd.DataFrame:
    raw = _fetch_bytes(f"{FIREBASE_FOLDER}/{fname}/trades_closed.parquet")
    if raw is None:
        return pd.DataFrame()
    t = pd.read_parquet(BytesIO(raw))
    if not t.empty:
        t["entry_date"] = pd.to_datetime(t["entry_date"])
        t["exit_date"] = pd.to_datetime(t["exit_date"])
    return t


def load_pick_open_trade(fname: str) -> dict | None:
    raw = _fetch_bytes(f"{FIREBASE_FOLDER}/{fname}/open_trade.json")
    if raw is None:
        return None
    d = json.loads(raw.decode("utf-8"))
    d["entry_date"] = pd.Timestamp(d["entry_date"])
    return d


def compute_daily_pnl(trades_closed: pd.DataFrame, ew: pd.Series,
                      year: int, open_trade: dict | None = None) -> pd.Series:
    """Daily MTM in raw spread units for one cell over `year`.

    Same convention as BloombergCOT/analytics/_backtest_portfolio_daily.py but
    extended to handle an OPEN trade (not yet closed at last bar).

    For an open trade, daily MTM accrues from max(entry_date, year_start) to the
    last available bar, using close-to-close deltas; entry day uses entry_price.
    """
    if ew.index.tz is not None:
        ew = ew.copy()
        ew.index = ew.index.tz_localize(None)

    y_start = pd.Timestamp(year, 1, 1)
    y_end = pd.Timestamp(year, 12, 31)
    days = ew.index[(ew.index >= y_start) & (ew.index <= y_end)]
    if len(days) == 0:
        return pd.Series(dtype=float)
    daily = pd.Series(0.0, index=days)

    closed_iter = []
    if trades_closed is not None and not trades_closed.empty:
        t = trades_closed.copy()
        t["entry_date"] = pd.to_datetime(t["entry_date"])
        t["exit_date"] = pd.to_datetime(t["exit_date"])
        t = t[(t["entry_date"] <= y_end) & (t["exit_date"] >= y_start)]
        for _, tr in t.iterrows():
            closed_iter.append({
                "side": str(tr["side"]).lower(),
                "entry_date": tr["entry_date"], "exit_date": tr["exit_date"],
                "entry": float(tr["entry"]), "exit": float(tr["exit"]),
                "is_open": False,
            })
    if open_trade is not None:
        ed = pd.Timestamp(open_trade["entry_date"])
        if ed <= y_end:
            closed_iter.append({
                "side": str(open_trade["side"]).lower(),
                "entry_date": ed, "exit_date": days[-1],
                "entry": float(open_trade["entry_price"]),
                "exit": float(open_trade["current_price"]),
                "is_open": True,
            })

    for tr in closed_iter:
        direction = 1.0 if tr["side"] == "long" else -1.0
        seg_start = max(tr["entry_date"], y_start)
        seg_end = min(tr["exit_date"], y_end)
        seg = ew.index[(ew.index >= seg_start) & (ew.index <= seg_end)]
        if len(seg) == 0:
            continue
        for d in seg:
            if d == tr["entry_date"]:
                pnl_d = direction * (ew.loc[d] - tr["entry"])
            elif d == tr["exit_date"] and not tr["is_open"]:
                prev = ew.index[ew.index < d]
                if len(prev) == 0:
                    pnl_d = 0.0
                else:
                    pnl_d = direction * (tr["exit"] - ew.loc[prev[-1]])
            else:
                prev = ew.index[ew.index < d]
                if len(prev) == 0:
                    pnl_d = 0.0
                else:
                    pnl_d = direction * (ew.loc[d] - ew.loc[prev[-1]])
            daily.loc[d] += pnl_d
    return daily


@st.cache_data(ttl=900)
def build_portfolio_daily_pnl(year: int = YEAR) -> pd.DataFrame:
    """Weighted daily P&L across all 7 picks for `year`.
    Returns DataFrame with Date index and columns = pick fnames + portfolio + cum."""
    state = load_state()
    if "error" in state:
        return pd.DataFrame()
    picks = state["picks"]

    pieces = {}
    for p in picks:
        fname = p["fname"]
        df = load_pick_df(fname)
        trades = load_pick_trades(fname)
        open_trade = load_pick_open_trade(fname)
        ew = df.set_index("Date")["EW_adj"]
        raw = compute_daily_pnl(trades, ew, year, open_trade)
        pieces[fname] = raw * p["weight"]

    portfolio = pd.concat(pieces, axis=1).fillna(0.0)
    portfolio["portfolio_daily_pnl"] = portfolio.sum(axis=1)
    portfolio["cumulative_pnl"] = portfolio["portfolio_daily_pnl"].cumsum()
    return portfolio


@st.cache_data(ttl=900)
def spread_return_correlation(window_months: int = 12) -> pd.DataFrame:
    """Pearson correlation of daily EW_adj returns (diff) across picks over the
    trailing `window_months`. Independent of trade state — reflects underlying
    market co-movement of the spreads."""
    state = load_state()
    if "error" in state:
        return pd.DataFrame()
    picks = state["picks"]
    last_bar = pd.Timestamp(state["portfolio_last_bar"])
    start = last_bar - pd.DateOffset(months=window_months)
    returns = {}
    for p in picks:
        df = load_pick_df(p["fname"])
        ew = df.set_index("Date")["EW_adj"]
        ret = ew.diff().dropna()
        ret = ret[(ret.index >= start) & (ret.index <= last_bar)]
        returns[p["fname"]] = ret
    if not returns:
        return pd.DataFrame()
    return pd.concat(returns, axis=1).corr()


@st.cache_data(ttl=900)
def load_backtest_baseline_daily_pnl(year: int = YEAR) -> pd.Series:
    """The backtest's own daily_pnl sheet, sliced to `year`. Read from Firebase."""
    raw = _fetch_bytes(f"{FIREBASE_FOLDER}/portfolio_MPT_meanvar_universe_v2.xlsx")
    if raw is None:
        return pd.Series(dtype=float)
    try:
        s = pd.read_excel(BytesIO(raw), sheet_name="daily_pnl")
    except Exception:
        return pd.Series(dtype=float)
    s["Date"] = pd.to_datetime(s["Date"])
    s = s.set_index("Date")
    return s.loc[s.index.year == year, "portfolio_daily_pnl"]


def derive_status_row(pick: dict) -> dict:
    """Build one row for the Section B status grid.

    Strategy bands, Status σ-distances, and realised YTD all stay on the
    blended EW_adj series (the strategy's internal convention — keeps the
    backtest signals consistent across roll boundaries).

    But the **displayed Current value**, the **Unrealised P&L** for any open
    trade, and **today's Day P&L** are switched to the **raw sum-of-signed-legs
    frame** so the dashboard's numbers match what the trader actually quotes
    at D-1. This affects display only — it never re-detects trades."""
    fname = pick["fname"]
    weight = pick["weight"]
    med = pick["last_median"]
    std = pick["last_std"]
    upper = pick["last_upper"]
    lower = pick["last_lower"]

    open_trade = load_pick_open_trade(fname)
    df = load_pick_df(fname)
    trades = load_pick_trades(fname)
    current_contract = str(df.iloc[-1]["contract"]) if not df.empty else ""

    # ── Build raw series + EW_adj series ──────────────────────────────
    # `raw_series` = sum of signed leg columns = the OLD-contract spread
    #   (leg columns always point to current contracts that haven't rolled).
    # `ew_adj_series` = framework's blended EW. CAVEAT: the framework's
    #   blending uses the last-5-POPULATED dates of each chunk. When the
    #   incremental refresh has data only through mid-roll, the framework
    #   treats the last populated date as k=1 (100% NEW). That's why on
    #   roll day 1 (Jun 24) EW_adj reflects 100% NEW contract spread, not
    #   the user's expected 80/20 blend.
    df_sorted = df.sort_values("Date").reset_index(drop=True) if not df.empty else df
    ew_adj_series = None
    if not df_sorted.empty and "EW_adj" in df_sorted.columns:
        ew_adj_series = df_sorted["EW_adj"].copy()
        ew_adj_series.index = pd.to_datetime(df_sorted["Date"])
    leg_cols = [c for c in df.columns
                if c not in {"Date", "EW", "EW_adj", "rolling_median",
                              "rolling_std", "upper_bound", "lower_bound",
                              "contract", "pnl_running"}
                and not c.endswith("_contract")] if not df.empty else []
    raw_series = None
    if leg_cols and not df_sorted.empty:
        raw_series = df_sorted[leg_cols].sum(axis=1)
        raw_series.index = pd.to_datetime(df_sorted["Date"])

    # ── Real-calendar blending of the live tail ───────────────────────
    # For the LAST bar, replace EW_adj with the calendar-correct blend
    # using the REAL last-5 BDs of that calendar month (holiday-aware).
    # The framework's last-5-populated convention gets fixed live here.
    from pandas.tseries.holiday import AbstractHolidayCalendar, Holiday, GoodFriday
    from pandas.tseries.offsets import CustomBusinessDay
    class _StratCal(AbstractHolidayCalendar):
        rules = [Holiday("NewYears", month=1, day=1), GoodFriday,
                 Holiday("Christmas", month=12, day=25)]
    _bday = CustomBusinessDay(calendar=_StratCal())

    def _real_last_n_bds(yr: int, mo: int, n: int = 5) -> list[pd.Timestamp]:
        ms = pd.Timestamp(yr, mo, 1)
        me = ms + pd.offsets.MonthEnd(0)
        bds = list(pd.bdate_range(start=ms, end=me, freq=_bday))
        return [pd.Timestamp(d).normalize() for d in bds[-n:]]

    def _blended_at(ts: pd.Timestamp) -> float | None:
        """Calendar-correct blended price at `ts`. On dates inside the real
        last-5-BDs of the month, computes
            old_w * raw[ts] + new_w * ew_adj[ts]
        where the framework's EW_adj equals 100%-NEW on the latest populated
        date. On dates outside the roll window, returns raw."""
        if raw_series is None:
            return None
        if ts not in raw_series.index:
            prior = raw_series.index[raw_series.index <= ts]
            if len(prior) == 0:
                return None
            ts = prior[-1]
        ts_n = pd.Timestamp(ts).normalize()
        real_last5 = _real_last_n_bds(int(ts_n.year), int(ts_n.month), n=5)
        if ts_n not in real_last5:
            return float(raw_series.loc[ts])
        # ts is in real last-5-BDs of its calendar month → blend
        k = 5 - real_last5.index(ts_n)   # k=5 first day, k=1 last day
        old_w = (k - 1) / 5
        new_w = (5 - k + 1) / 5
        raw_v = float(raw_series.loc[ts])
        ew_v = (float(ew_adj_series.loc[ts])
                if ew_adj_series is not None and ts in ew_adj_series.index
                else raw_v)
        return old_w * raw_v + new_w * ew_v

    # Displayed Current = calendar-correct blend at the latest bar.
    if raw_series is not None and len(raw_series) > 0:
        last_ts = raw_series.index[-1]
        ew = _blended_at(last_ts)
        if ew is None:
            ew = pick["last_ew_adj"]
    else:
        ew = pick["last_ew_adj"]
    ew_blended_today = ew
    z = (ew - med) / std if (med is not None and std and std > 0) else np.nan

    # ── Day P&L (blended frame) ───────────────────────────────────────
    daily_raw = 0.0
    if open_trade is not None and raw_series is not None and len(raw_series) >= 2:
        direction = +1 if str(open_trade["side"]).lower() == "long" else -1
        entry_d = pd.Timestamp(open_trade["entry_date"])
        last_bar_d = pd.Timestamp(raw_series.index[-1])
        if entry_d.date() < last_bar_d.date():
            prev_bar_d = pd.Timestamp(raw_series.index[-2])
            curr_b = _blended_at(last_bar_d)
            prev_b = _blended_at(prev_bar_d)
            if curr_b is not None and prev_b is not None:
                daily_raw = direction * float(curr_b - prev_b)

    # ── Realised YTD (blended frame — unchanged) ──────────────────────
    ew_series_blended = df.set_index("Date")["EW_adj"]
    realised_daily = compute_daily_pnl(trades, ew_series_blended, YEAR, open_trade=None)
    ytd_realised_raw = float(realised_daily.sum()) if len(realised_daily) > 0 else 0.0

    # ── Open-trade Unrealised P&L (blended) ───────────────────────────
    if open_trade is not None and raw_series is not None and len(raw_series) > 0:
        entry_d = pd.Timestamp(open_trade["entry_date"])
        blended_entry = _blended_at(entry_d)
        if blended_entry is not None:
            direction = +1 if str(open_trade["side"]).lower() == "long" else -1
            open_pnl_raw = direction * (ew_blended_today - blended_entry)
        else:
            open_pnl_raw = 0.0
    else:
        open_pnl_raw = 0.0

    if open_trade is not None:
        entry_date_str = (f"{pd.Timestamp(open_trade['entry_date']).date().isoformat()} "
                          f"({open_trade['days_held']}d)")
        # Display entry in BLENDED frame to match the Current column.
        entry_d = pd.Timestamp(open_trade["entry_date"])
        blended_entry_display = _blended_at(entry_d)
        entry_price_display = (round(blended_entry_display, 4)
                                if blended_entry_display is not None
                                else open_trade['entry_price'])
        # Distance to median (take-profit) exit, in σ and $
        if not pd.isna(z) and med is not None:
            dist_to_med_sigma = abs(float(z))
            dist_to_med_dollar = abs(float(ew) - float(med))
            exit_str = (f" · {dist_to_med_sigma:.2f}σ (${dist_to_med_dollar:.2f}) "
                        f"to exit @ {float(med):.3f}")
        else:
            exit_str = ""
        status_str = (f"{open_trade['side'].upper()} @ {entry_price_display}{exit_str}")
        signal_alert = ""
        if pd.Timestamp(open_trade["entry_date"]).date() == pd.Timestamp(pick["last_bar_date"]).date():
            signal_alert = f"FRESH {open_trade['side'].upper()} ENTRY today"
    else:
        se_val = float(pick.get("SE", 1.0))
        # Detect pause-after-stop: if last closed trade was a stop AND price
        # hasn't yet reverted to median, the strategy can't fire a new entry.
        in_pause = False
        pause_wait = None
        if not trades.empty:
            last_closed = trades.sort_values("exit_date").iloc[-1]
            if str(last_closed.get("exit_reason", "")).lower() == "stop":
                stop_side = str(last_closed["side"]).lower()
                if stop_side == "long" and not pd.isna(ew) and not pd.isna(med) and ew < med:
                    in_pause = True
                    pause_wait = "above"
                elif stop_side == "short" and not pd.isna(ew) and not pd.isna(med) and ew > med:
                    in_pause = True
                    pause_wait = "below"

        if not pd.isna(z) and lower is not None and upper is not None:
            sig = "short" if z > 0 else "long"
            target = upper if z > 0 else lower
            dist_sig = max(se_val - abs(z), 0.0)
            dist_dollar = abs(float(ew) - float(target))
            if in_pause:
                # Pause clears when spread reverts back to (and past) the median:
                # "wait_above" for long-stop → resumes when spread ≥ median
                # "wait_below" for short-stop → resumes when spread ≤ median
                pause_side = "long" if pause_wait == "above" else "short"
                comparator = "≥" if pause_wait == "above" else "≤"
                status_str = (f"FLAT (cooldown after stop) · {pause_side} entry "
                              f"suppressed until spread {comparator} {float(med):.3f}")
            else:
                status_str = (f"FLAT · {dist_sig:.2f}σ (${dist_dollar:.2f}) "
                              f"to {sig} @ {target:.3f}")
        else:
            status_str = "FLAT (cooldown after stop)" if in_pause else "FLAT"
        entry_date_str = ""
        signal_alert = ""
        if not trades.empty:
            last_exit = pd.to_datetime(trades["exit_date"].max())
            if last_exit.date() == pd.Timestamp(pick["last_bar_date"]).date():
                last_trade = trades.iloc[-1]
                signal_alert = f"EXIT today ({last_trade.get('exit_reason', '?')})"

    params_str = f"W{pick['W']} / SE{pick['SE']:g} / SL{pick['SL']:g}"

    # Offset: parse the formula's [N] markers into a readable contract-month
    # layout. Boxes show pairs per product ("M2/M3"); products joined by " - ".
    # E.g. AEO[2] - AEO[3] - BSP[1] + BSP[2]  →  "M2/M3 - M1/M2"
    import re
    matches = re.findall(r"(\w+)\[(\d+)\]", pick.get("formula", ""))
    _groups: dict[str, list[str]] = {}
    _order: list[str] = []
    for _prod, _off in matches:
        if _prod not in _groups:
            _groups[_prod] = []
            _order.append(_prod)
        _groups[_prod].append(_off)
    _parts = []
    for _prod in _order:
        offs = _groups[_prod]
        if len(offs) == 1:
            _parts.append(f"M{offs[0]}")
        elif len(offs) == 2:
            _parts.append(f"M{offs[0]}/M{offs[1]}")
        else:
            _pairs = ["/".join([f"M{o}" for o in offs[i:i+2]])
                      for i in range(0, len(offs), 2)]
            _parts.append("-".join(_pairs))
    # Single-product "box" formulas use a synthetic-diff leg (e.g. ULJ =
    # NWE_Jet - ICEGO). Duplicate the pair so the display reads as a 4-leg
    # box rather than a single 2-leg calendar spread.
    if ("box" in pick.get("shape", "") and len(_order) == 1
            and len(_groups[_order[0]]) == 2):
        offset_str = f"{_parts[0]} - {_parts[0]}"
    else:
        offset_str = " - ".join(_parts)

    # Formula display: combine sign + product + M-offsets into one readable
    # string per leg group, e.g. "+ AEO (M2/M3) − BSP (M1/M2)".
    formula = pick.get("formula", "")
    formula_padded = formula
    if formula_padded and not re.match(r"^\s*[+-]", formula_padded):
        formula_padded = "+" + formula_padded
    items = re.findall(r"([+-])\s*(\w+)\[(\d+)\]", formula_padded)
    _grp = []
    _grp_idx = {}
    for _sign, _prod, _off in items:
        if _prod not in _grp_idx:
            _grp_idx[_prod] = len(_grp)
            _grp.append((_prod, []))
        _grp[_grp_idx[_prod]][1].append((_sign, _off))
    def _fmt_leg(sign: str, name: str, offsets: list[str]) -> str:
        gs = "+" if sign == "+" else "−"
        if len(offsets) == 1:
            mp = f"M{offsets[0]}"
        else:
            mp = "/".join([f"M{o}" for o in offsets])
        return f"{gs} {name} ({mp})"

    formula_parts = []
    for _prod, _sign_offs in _grp:
        _offs = [o for _, o in _sign_offs]
        _name = PRODUCT_NAMES.get(_prod, _prod)
        # If the friendly name is a synthetic expression (contains " + " or
        # " - "), expand it into per-component legs. Each component inherits
        # the original product's offsets, with sign = outer × inner.
        if re.search(r"\s[+\-]\s", _name):
            _split = re.split(r"\s([+\-])\s", _name)
            components: list[tuple[str, str]] = []
            if not _name.lstrip().startswith(("+", "-")):
                components.append(("+", _split[0].strip()))
                _idx = 1
            else:
                _idx = 0
            while _idx < len(_split) - 1:
                components.append((_split[_idx], _split[_idx + 1].strip()))
                _idx += 2
            for inner_sign, comp_name in components:
                comp_pairs = []
                for outer_sign, outer_off in _sign_offs:
                    combined = "+" if outer_sign == inner_sign else "-"
                    comp_pairs.append((combined, outer_off))
                grp_sign = comp_pairs[0][0]
                grp_offsets = [o for _, o in comp_pairs]
                formula_parts.append(_fmt_leg(grp_sign, comp_name, grp_offsets))
        else:
            formula_parts.append(_fmt_leg(_sign_offs[0][0], _name, _offs))
    formula_display = " ".join(formula_parts)

    # Distance to next entry in σ (FLAT picks only; active = NaN)
    if open_trade is None and not pd.isna(z):
        se_val = float(pick.get("SE", 1.0))
        dist_to_entry_sigma = max(se_val - abs(z), 0.0)
    else:
        dist_to_entry_sigma = float("nan")

    return {
        "diff": pick["diff"],
        "shape": pick["shape"],
        "contract": current_contract,
        "offset": offset_str,
        "formula_display": formula_display,
        "params": params_str,
        "weight": weight,
        "var99_bbl": pick.get("var99_bbl"),
        "current": ew,
        "median": med,
        "lower": lower,
        "upper": upper,
        "z": z,
        "status": status_str,
        "entry_date": entry_date_str,
        "signal_alert": signal_alert,
        "daily_pnl_raw": daily_raw,
        "daily_pnl_weighted": daily_raw * weight,
        "open_trade_pnl_raw": open_pnl_raw,
        "open_trade_pnl_weighted": open_pnl_raw * weight,
        "ytd_realised_raw": ytd_realised_raw,
        "ytd_realised_weighted": ytd_realised_raw * weight,
        "dist_to_entry_sigma": dist_to_entry_sigma,
        "fname": fname,
        "cell": pick["cell"],
        "formula": pick["formula"],
    }


def portfolio_metrics(daily: pd.Series) -> dict:
    """YTD performance metrics on the portfolio daily P&L series."""
    if daily.empty or daily.std() == 0:
        return {"ytd_pnl": 0.0, "sharpe": np.nan, "max_dd": 0.0,
                "win_rate": np.nan, "best_day": 0.0, "worst_day": 0.0,
                "n_days": int(len(daily))}
    cum = daily.cumsum()
    dd = cum - cum.cummax()
    return {
        "ytd_pnl": float(daily.sum()),
        "sharpe": float(daily.mean() / daily.std() * np.sqrt(252)),
        "max_dd": float(dd.min()),
        "win_rate": float((daily > 0).mean() * 100),
        "best_day": float(daily.max()),
        "worst_day": float(daily.min()),
        "n_days": int(len(daily)),
    }


# ── Trade log persistence ─────────────────────────────────────────────

def load_trade_log() -> pd.DataFrame:
    if not LOCAL_MODE or not TRADE_LOG_FP.exists():
        return pd.DataFrame(columns=TRADE_LOG_COLS)
    df = pd.read_csv(TRADE_LOG_FP, parse_dates=["entry_date", "exit_date",
                                                  "created_at", "updated_at"])
    for c in TRADE_LOG_COLS:
        if c not in df.columns:
            df[c] = None
    return df[TRADE_LOG_COLS]


def save_trade_log_row(row: dict) -> str:
    """Append a new trade. Returns the trade_id."""
    if not LOCAL_MODE:
        raise RuntimeError("Trade log not writeable in cloud mode")
    log = load_trade_log()
    row = dict(row)
    if "trade_id" not in row or not row["trade_id"]:
        row["trade_id"] = uuid.uuid4().hex[:12]
    row["created_at"] = datetime.now().isoformat(timespec="seconds")
    row["updated_at"] = row["created_at"]
    for c in TRADE_LOG_COLS:
        if c not in row:
            row[c] = None
    log = pd.concat([log, pd.DataFrame([row])[TRADE_LOG_COLS]], ignore_index=True)
    log.to_csv(TRADE_LOG_FP, index=False)
    return row["trade_id"]


def update_trade_log_row(trade_id: str, updates: dict) -> bool:
    if not LOCAL_MODE:
        raise RuntimeError("Trade log not writeable in cloud mode")
    log = load_trade_log()
    mask = log["trade_id"] == trade_id
    if not mask.any():
        return False
    for k, v in updates.items():
        log.loc[mask, k] = v
    log.loc[mask, "updated_at"] = datetime.now().isoformat(timespec="seconds")
    log.to_csv(TRADE_LOG_FP, index=False)
    return True


def delete_trade_log_row(trade_id: str) -> bool:
    if not LOCAL_MODE:
        raise RuntimeError("Trade log not writeable in cloud mode")
    log = load_trade_log()
    n0 = len(log)
    log = log[log["trade_id"] != trade_id]
    if len(log) == n0:
        return False
    log.to_csv(TRADE_LOG_FP, index=False)
    return True


# ── Refresh subprocess ────────────────────────────────────────────────

def run_refresh(include_data: bool = True) -> tuple[bool, str]:
    """Invoke refresh_18m.py + _monitor_refresh_mpt7.py + _sync_monitor_to_firebase.py
    as subprocesses. Returns (success, log_text). Local-only — fails immediately
    in cloud mode."""
    if not LOCAL_MODE:
        return False, "Refresh not available in cloud mode."
    chunks = []
    if include_data:
        try:
            r = subprocess.run(
                ["python", str(DATA_REFRESH_SCRIPT)],
                cwd=str(BLOOMBERG_COT),
                capture_output=True, text=True, timeout=900,
            )
            chunks.append("=== refresh_18m.py ===\n" + (r.stdout or "") + (r.stderr or ""))
            if r.returncode != 0:
                return False, "\n".join(chunks)
        except Exception as e:
            chunks.append(f"refresh_18m failed: {e}")
            return False, "\n".join(chunks)

    try:
        r = subprocess.run(
            ["python", str(REFRESH_SCRIPT)],
            cwd=str(BLOOMBERG_COT),
            capture_output=True, text=True, timeout=900,
        )
        chunks.append("=== _monitor_refresh_mpt7.py ===\n" + (r.stdout or "") + (r.stderr or ""))
        if r.returncode != 0:
            return False, "\n".join(chunks)
    except Exception as e:
        chunks.append(f"monitor refresh failed: {e}")
        return False, "\n".join(chunks)

    # Sync to Firebase so cloud reads see the new state
    try:
        r = subprocess.run(
            ["python", str(SYNC_SCRIPT)],
            cwd=str(BLOOMBERG_COT),
            capture_output=True, text=True, timeout=300,
        )
        chunks.append("=== _sync_monitor_to_firebase.py ===\n" + (r.stdout or "") + (r.stderr or ""))
        return r.returncode == 0, "\n".join(chunks)
    except Exception as e:
        chunks.append(f"firebase sync failed: {e}")
        return False, "\n".join(chunks)
