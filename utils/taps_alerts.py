"""Shared alert state + popup rendering for the TAPS page.

Lives here rather than inside pages/TAPS.py so the test harness (pages/TAPS_Test.py) can
drive the REAL rendering and the REAL latch, instead of a copy that could drift from it.

The contract:
  * one alert per CHUNK -- a chunk is (table, group), group being "+" premium or
    "-" discount, so a single table can raise two independent alerts in a day;
  * an alert fires ONCE, the first time its threshold is crossed that trading day.
    `fired` is write-once per key; nothing re-arms it except the 05:00 day rollover;
  * crossing a popup marks the chunk acknowledged, which only hides the popup. The
    table keeps its static highlight and its first-crossed timestamp.
"""
import streamlit as st

# Popup geometry. Boxes are position:fixed so they float over the page instead of pushing
# the tables down, and stack downwards when several chunks are live.
POPUP_TOP_REM = 5.0        # first box, clear of the Streamlit header
POPUP_STEP_REM = 4.4       # vertical pitch between stacked boxes
POPUP_WIDTH_PX = 360


def init_state() -> None:
    st.session_state.setdefault("fired", {})     # "table|group" -> alert record, write-once
    st.session_state.setdefault("acked", set())  # chunks crossed off by the user


def clear() -> None:
    """Drop today's latches — the 05:00 rollover, and the test harness's reset."""
    st.session_state.fired = {}
    st.session_state.acked = set()


def slug(key: str) -> str:
    """CSS-safe suffix for a container key: "S0.5|+" -> "S0_5_P"."""
    return (key.replace("|", "_").replace(".", "_").replace(" ", "_")
               .replace("+", "P").replace("-", "M"))


def trigger(key: str, *, title: str, side: str, vol: str, unit: str, ts: str) -> bool:
    """Record a chunk's FIRST crossing. No-op (returns False) if it already fired today —
    this is what stops the popup reappearing on every poll while the condition holds."""
    if key in st.session_state.fired:
        return False
    st.session_state.fired[key] = {"ts": ts, "title": title, "side": side,
                                   "vol": vol, "unit": unit}
    return True


def render_popups() -> None:
    """One floating popup per un-acknowledged chunk, with the X on the right of the bar,
    level with the text. Newest sits on top, phone-style.

    Not st.dialog: that is a true modal, so it would cover the numbers being watched, can
    only show one at a time, and re-opens itself on every fragment rerun. A fixed-position
    card avoids all three. The X must be a real Streamlit button to be clickable, and a
    button cannot live inside an st.markdown div — so the row sits in a KEYED container
    that CSS paints and positions, with a narrow column holding the button.
    """
    live = [(k, r) for k, r in st.session_state.fired.items()
            if k not in st.session_state.acked][::-1]      # newest first
    if not live:
        return
    css = []
    for n, (k, _) in enumerate(live):
        sl = slug(k)
        top = POPUP_TOP_REM + n * POPUP_STEP_REM
        css.append(
            f'div.st-key-popup_{sl} {{position:fixed;top:{top}rem;right:1.5rem;'
            f'width:{POPUP_WIDTH_PX}px;z-index:9999;background:rgba(255,214,0,0.97);'
            f'border-radius:0.6rem;padding:0.5rem 0.55rem 0.5rem 0.9rem;'
            f'box-shadow:0 6px 20px rgba(0,0,0,0.35);}}'
            f'div.st-key-popup_{sl} p {{color:#111;font-weight:700;'
            f'margin:0;padding:0;line-height:1.5rem;}}'
            # The X is laid out by a column, NOT absolute positioning: Streamlit wraps
            # buttons in their own block, so position:absolute fell back into normal flow
            # and dropped the X below the text. A column keeps it on the same line, right.
            f'div.st-key-popup_{sl} button {{background:transparent;border:none;'
            f'color:#111;font-weight:800;min-height:0;height:1.5rem;'
            f'padding:0 0.2rem;line-height:1;}}'
            f'div.st-key-popup_{sl} button:hover {{color:#b00;background:transparent;}}'
            # Centring the text needed more than columns(vertical_alignment): the button
            # is taller than a line of text, so the row height comes from the button and
            # Streamlit's own column wrappers (stColumn > stVerticalBlock >
            # stElementContainer) each add gap/margin that push the paragraph down. Make
            # every one of those a centred flex box so the text sits on the button's axis.
            f'div.st-key-popup_{sl} div[data-testid="stHorizontalBlock"]'
            f'  {{gap:0.3rem;align-items:center;}}'
            f'div.st-key-popup_{sl} div[data-testid="stColumn"]'
            f'  {{display:flex;align-items:center;min-height:1.6rem;}}'
            f'div.st-key-popup_{sl} div[data-testid="stColumn"] > div'
            f'  {{width:100%;display:flex;align-items:center;}}'
            f'div.st-key-popup_{sl} [data-testid="stVerticalBlock"]'
            f'  {{gap:0;display:flex;align-items:center;}}'
            f'div.st-key-popup_{sl} [data-testid="stElementContainer"]'
            f'  {{margin:0;padding:0;display:flex;align-items:center;}}'
            f'div.st-key-popup_{sl} [data-testid="stMarkdown"],'
            f'div.st-key-popup_{sl} [data-testid="stMarkdownContainer"]'
            f'  {{display:flex;align-items:center;margin:0;padding:0;}}')
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)
    for k, r in live:
        with st.container(key=f"popup_{slug(k)}"):
            c1, c2 = st.columns([11, 1], vertical_alignment="center")
            c1.markdown(f'{r["ts"]} - [{r["title"]}] {r["vol"]} {r["unit"]} @ {r["side"]}')
            if c2.button("✕", key=f"popup_btn::{k}", help="Dismiss"):
                st.session_state.acked.add(k)
                try:
                    # scope="fragment" is the cheap rerun on the live page; outside a
                    # fragment (the test harness) it raises, so fall back to a full rerun.
                    # Safe to catch broadly: RerunException derives from BaseException.
                    st.rerun(scope="fragment")
                except Exception:
                    st.rerun()
