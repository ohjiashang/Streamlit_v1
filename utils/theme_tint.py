"""Theme-aware cell tints for pandas Styler output shown with st.dataframe.

A fixed pastel like #FFFFE0 reads fine on a white page but turns into a
glaring block on Streamlit's dark theme. Instead of hard-coding colours,
composite a tint (an RGB colour plus an alpha) onto the viewer's own theme
background, taken from ``st.context.theme``. Small alphas give a faint wash
on either theme, and the text keeps the theme's default colour, so nothing
has to be forced black or white.

Usage::

    from utils.theme_tint import tint_css
    AMBER = (255, 193, 7)
    css = tint_css(AMBER, 0.30)        # -> "background-color: #FFEEBA" on light
"""
from __future__ import annotations

import streamlit as st

LIGHT_BG = (255, 255, 255)   # Streamlit light theme backgroundColor
DARK_BG = (14, 17, 23)       # Streamlit dark theme backgroundColor #0E1117


def theme_background() -> tuple[int, int, int] | None:
    """Cell background of the viewer's current theme as (r, g, b).

    Returns None when the theme cannot be determined (no browser session, or
    an old Streamlit without ``st.context.theme``); callers then fall back to
    an rgba colour and let the browser do the blending."""
    try:
        theme = st.context.theme
        bg = None
        if hasattr(theme, "get"):
            bg = theme.get("backgroundColor")
        if bg:
            bg = str(bg).lstrip("#")
            return tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4))
        return DARK_BG if getattr(theme, "type", None) == "dark" else LIGHT_BG
    except Exception:
        return None


def tint_css(rgb: tuple[int, int, int], alpha: float,
             bg: tuple[int, int, int] | None = None) -> str:
    """CSS ``background-color`` for ``rgb`` at ``alpha`` over the theme
    background (or ``bg`` if given). Solid hex when the theme is known, rgba
    otherwise."""
    alpha = max(0.0, min(1.0, float(alpha)))
    if bg is None:
        bg = theme_background()
    if bg is None:
        return f"background-color: rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha:.2f})"
    r, g, b = (round(alpha * t + (1 - alpha) * c) for t, c in zip(rgb, bg))
    return f"background-color: #{r:02X}{g:02X}{b:02X}"
