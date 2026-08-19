"""TAPS page — live T&S bin tallies (Dubai / SGO / SKO).

Reads taps/display.json from Firebase Storage (uploaded by the DubaiTS daemon each
cycle, Cache-Control: no-cache) and auto-refreshes every 30s. Public-read, no creds.

Layout: Dubai on row 1, SGO + SKO on row 2; each table is 1/4 of the page width.
"""
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from streamlit_sortables import sort_items

from utils import taps_alerts

st.set_page_config(page_title="TAPS", layout="wide")

FIREBASE_BUCKET = "hotei-streamlit.firebasestorage.app"
REMOTE_PATH = "taps/display.json"
REFRESH_SEC = 30
PAGE_POLL_SEC = 5   # page Firebase-read rate DURING the daemon's fast (10s ICE) window (NO ICE).
                    # Outside it, the page reads at the daemon's own cadence (30s) — no point
                    # polling faster than the data changes. Cuts lag at zero ICE cost.
STALE_AFTER_SEC = 120   # if the feed hasn't updated in this long (daemon stopped @17:00 / stalled),
                        # show a neutral grey "as of HH:MM" bar instead of the live green one.
# Highlight the premium (+XC) or discount (-XC) group when that group's summed value
# (across all its rows and contracts) reaches the table's threshold. FLAT + totals never
# highlight. Live/conditional — resets at 07:00 or when the sum drops back below.
HIGHLIGHT_THRESHOLDS = {
    "Dubai": 500,
    "SGO": 500, "SKO": 500, "S92": 500,
    "S0.5": 500 / 6.35, "S380": 500 / 6.35,
    "MOPJ": 500 / 8.9,           # $/mt, naphtha conversion (8.9 bbl/mt)
}
HIGHLIGHT_DEFAULT = 500

# --- Sidebar product filter -------------------------------------------------------
# Products grouped by family. Each product has its own checkbox; each family header is a
# master checkbox that toggles all products under it (kept in two-way sync). Default:
# everything on == the full current layout. Selection lives in session_state, so it's
# per-user and survives every auto-refresh (only a hard browser reload resets it).
FAMILIES = {
    "Crude":  ["Dubai", "Brent SMM"],
    "Light":  ["S92", "MOPJ"],
    "Middle": ["SGO", "SKO", "LSGO SMM"],
    "Heavy":  ["S0.5", "S380"],
}
# Display order = the current page grid read L->R, top->bottom. Selected tables re-flow
# into this order 2-per-row, so all-selected reproduces the original layout exactly.
GRID_ORDER = ["Dubai", "Brent SMM", "S92", "MOPJ", "SGO", "SKO", "S0.5", "S380", "LSGO SMM"]


def _public_url() -> str:
    p = urllib.parse.quote(REMOTE_PATH, safe="")
    return f"https://firebasestorage.googleapis.com/v0/b/{FIREBASE_BUCKET}/o/{p}?alt=media"


def fetch():
    # cache-bust so a proxy can never hand us a stale copy
    url = _public_url() + f"&_={int(time.time())}"
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


# --- alert on first highlight -------------------------------------------------------
# One popup per CHUNK -- (table, group) -- per TRADING DAY, raised the first time that
# group crosses its threshold. The page re-polls every few seconds, so a level-triggered
# alert would reappear for as long as the condition held; instead each chunk is latched in
# session_state once raised, and only unlatches when the trading day rolls at 05:00.
RESET_HOUR = 5          # daemon resets its bins at 05:00, so that is the day boundary


def _trading_day(updated_iso: str) -> str:
    """Trading day the feed timestamp belongs to (the day rolls at RESET_HOUR, not midnight)."""
    try:
        dt = datetime.fromisoformat(updated_iso)
    except Exception:
        return "?"
    if dt.hour < RESET_HOUR:
        dt -= timedelta(days=1)
    return dt.date().isoformat()


# $/mt products: their thresholds are divided by a bbl/mt factor, so their volumes are
# tonnes (kt) rather than barrels (kb). Only affects the unit shown in the popup.
CONV_TABLES = {"S0.5", "S380", "MOPJ"}


def _grp(label):
    """Which highlight group a bin row belongs to: '+' (premium), '-' (discount), or None
    for FLAT. Most tables label these +1C / -2C, but Brent SMM and LSGO SMM use PREM/DISC —
    without mapping those, neither table could ever highlight."""
    s = str(label).strip().upper()
    if s.startswith("+") or s == "PREM":
        return "+"
    if s.startswith("-") or s == "DISC":
        return "-"
    return None


def render_table(t: dict) -> None:
    index = [t["total_label"]] + t["bin_labels"]
    matrix = [t["totals"]] + [t["bins"][bl] for bl in t["bin_labels"]]
    df = pd.DataFrame(matrix, index=index, columns=t["columns"])

    # Premium (+XC) / discount (-XC) groups — FLAT and the totals row are excluded.
    # Highlight the WHOLE group when its summed value (all its rows, all contracts)
    # reaches the table's threshold.
    def _grp_sum(prefix):
        return sum(float(v) for bl in t["bin_labels"] if _grp(bl) == prefix
                   for v in t["bins"][bl])
    thr = HIGHLIGHT_THRESHOLDS.get(t["title"], HIGHLIGHT_DEFAULT)
    prem_hot = _grp_sum("+") >= thr
    disc_hot = _grp_sum("-") >= thr

    # Latched per CHUNK -- (table, group) -- not per table, so one table can raise two
    # independent alerts in a day: one premium, one discount. The feed clock is captured at
    # FIRST crossing, so the popup quotes when it actually tripped, not when it is read.
    for _g, _hot in (("+", prem_hot), ("-", disc_hot)):
        _key = f"{t['title']}|{_g}"
        if not _hot or _key in st.session_state.fired:
            continue
        try:
            _clock = datetime.fromisoformat(
                st.session_state.get("feed_updated", "")).strftime("%H:%M:%S")
        except Exception:
            _clock = "?"
        taps_alerts.trigger(
            _key, title=t["title"],
            side="premium" if _g == "+" else "discount",
            vol=f"{_grp_sum(_g):g}",             # raw sum, no rounding
            unit="kt" if t["title"] in CONV_TABLES else "kb", ts=_clock)

    def _cell_style(row):
        name = str(row.name)
        if name == t["total_label"]:   # totals row: grey emphasis (both themes)
            return ["font-weight:bold;background-color:rgba(128,128,128,0.25)"] * len(row)
        _g2 = _grp(name)
        if (_g2 == "+" and prem_hot) or (_g2 == "-" and disc_hot):
            return ["font-weight:bold;background-color:rgba(255,165,0,0.55)"] * len(row)
        return [""] * len(row)         # FLAT and un-triggered groups: no highlight

    def _fmt(v):
        # whole numbers as ints (0, 112); composite fractions to 1 dp (32.7)
        f = float(v)
        return f"{int(f):,}" if f == int(f) else f"{f:,.1f}"

    styled = (df.style
                .apply(_cell_style, axis=1)
                .set_properties(**{"text-align": "right"})
                .format(_fmt))

    # Thick grey rules: under the totals row, and wrapping the FLAT row
    # (span the label + data cells).
    grey = "3px solid #888"
    styles = [{"selector": "tbody tr:nth-child(1) td, tbody tr:nth-child(1) th",
               "props": [("border-bottom", grey)]}]
    if "FLAT" in t["bin_labels"]:
        pos = 2 + t["bin_labels"].index("FLAT")   # tbody nth-child (row 1 = totals)
        styles.append({"selector": f"tbody tr:nth-child({pos}) td, tbody tr:nth-child({pos}) th",
                       "props": [("border-top", grey), ("border-bottom", grey)]})
    styled = styled.set_table_styles(styles, overwrite=False)
    st.markdown(f"#### {t['title']}")

    st.table(styled)


st.title("TAPS")

# Sidebar filter — seed everything ON, then draw family (master) + product checkboxes.
for _fam, _prods in FAMILIES.items():
    st.session_state.setdefault(f"fam::{_fam}", True)
    for _p in _prods:
        st.session_state.setdefault(f"tbl::{_p}", True)

# Alert state lives in utils.taps_alerts (shared with the test harness). `alert_day` tracks
# which trading day the latches belong to, so live() can clear them at the 05:00 rollover.
# Per-user, like every other bit of session_state.
taps_alerts.init_state()
st.session_state.setdefault("alert_day", None)
st.session_state.setdefault("feed_updated", "")  # feed timestamp -> the popup clock


def _sync_family(fam):          # family master toggled -> set all its products
    v = st.session_state[f"fam::{fam}"]
    for p in FAMILIES[fam]:
        st.session_state[f"tbl::{p}"] = v


def _sync_product(fam):         # a product toggled -> family reflects "all on?"
    st.session_state[f"fam::{fam}"] = all(st.session_state[f"tbl::{p}"] for p in FAMILIES[fam])


# Tighten vertical spacing between rows in the sidebar (more compact checkbox list).
st.markdown(
    '<style>section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:0.2rem;}'
    'section[data-testid="stSidebar"] [data-testid="stCheckbox"]{margin-bottom:0;}</style>',
    unsafe_allow_html=True)

st.sidebar.header("Selected:")
for fam, prods in FAMILIES.items():
    st.sidebar.checkbox(f"**{fam}**", key=f"fam::{fam}", on_change=_sync_family, args=(fam,))
    for p in prods:
        _, c = st.sidebar.columns([1, 10])      # small left gutter -> products indent under family
        c.checkbox(p, key=f"tbl::{p}", on_change=_sync_product, args=(fam,))
    st.sidebar.divider()

# Drag-to-reorder (Route A). Per-user, persists across auto-refresh; resets on hard reload.
# Shows ONLY the checked products, laid out 2-per-row to mirror the page's 2-col grid; the
# dragged (row-major) order is spliced back into the master order and drives the layout.
# Sortable lives OUTSIDE the auto-refresh fragment so drags aren't reset. Its key tracks the
# selected *set* (not order) so it re-mounts on check/uncheck but stays put during a drag.
_all = st.session_state.get("tbl_order", GRID_ORDER)
_all = [p for p in _all if p in GRID_ORDER] + [p for p in GRID_ORDER if p not in _all]
_sel = [p for p in _all if st.session_state.get(f"tbl::{p}", True)]
# Blueprint: 2-col grid of tiles whose position == the table's slot on the page (row-major,
# left->right then top->bottom). Bordered tiles at 50% width give the 2xN page mirror.
_blueprint = (".sortable-container-body{display:grid!important;grid-template-columns:1fr 1fr;"
              "gap:6px;}"
              ".sortable-item{width:auto!important;margin:0!important;box-sizing:border-box;"
              "text-align:center;padding:8px 4px;border-radius:6px;}")
with st.sidebar:
    st.header("Layout")
    st.caption("Drag — each tile's slot mirrors the table's spot on the page")
    if _sel:
        _res = sort_items(_sel, direction="horizontal", custom_style=_blueprint,
                          key="sort_" + "_".join(sorted(_sel))) or _sel
    else:
        _res = []
        st.caption("Select products to arrange.")
# splice the reordered selected items back into their slots in the master order
_it = iter(_res)
st.session_state["tbl_order"] = [
    next(_it) if st.session_state.get(f"tbl::{p}", True) else p for p in _all
]

# Page read rate: fast (PAGE_POLL_SEC) during the daemon's 10s window to cut lag, else match
# the daemon's cadence (reading faster than the data changes is wasted). Reading the JSON
# touches NO ICE. Re-tune via a full rerun when the daemon's cadence changes.
def _page_poll(di):
    return PAGE_POLL_SEC if di <= 10 else di

if "page_poll" not in st.session_state:
    try:
        st.session_state.page_poll = _page_poll(int(fetch().get("interval", REFRESH_SEC)))
    except Exception:
        st.session_state.page_poll = REFRESH_SEC


@st.fragment(run_every=f"{st.session_state.page_poll}s")
def live():
    try:
        data = fetch()
    except Exception as e:
        st.error(f"Could not load data from Firebase: {e}")
        return

    updated = data.get("updated", "?")
    di = int(data.get("interval", REFRESH_SEC))     # daemon's data-update cadence
    want = _page_poll(di)
    if want != st.session_state.page_poll:          # cadence changed -> re-tune page rate
        st.session_state.page_poll = want
        try:
            st.rerun(scope="app")
        except TypeError:
            st.rerun()

    age = None
    if data.get("updated_epoch"):
        age = max(0, int(time.time() - float(data["updated_epoch"])))

    # Live GREEN bar when fresh; neutral GREY "as of <ts>" bar when the daemon is stopped or
    # stalled (after 17:00, overnight, or a mid-day hang) — no scary warning, just marks the
    # data as static. Grey rgba reads in both light/dark themes.
    if age is None or age > STALE_AFTER_SEC:
        st.markdown(
            f'<div style="background:rgba(128,128,128,0.2);padding:0.5rem 0.9rem;'
            f'border-radius:0.5rem;">As of {updated} SGT</div>',
            unsafe_allow_html=True)
    else:
        st.success(f"**Last updated:** {updated} SGT  ·  **{age}s ago**  ·  ↻ updates every {di}s")

    notif_slot = st.container()   # anchors the floating popups; filled after the tables

    tables = {t["title"]: t for t in data.get("tables", [])}

    st.session_state.feed_updated = updated   # the popup clock comes from the feed
    # Trading day rolled (05:00) -> clear the latches so each table may alert once again.
    day = _trading_day(updated)
    if day != st.session_state.alert_day:
        st.session_state.alert_day = day
        taps_alerts.clear()

    # Show only the sidebar-selected tables, in the user's dragged order, re-flowed 2-per-row
    # (default order == the original Dubai|Brent, S92|SGO, SKO|S0.5, S380|LSGO layout).
    order = st.session_state.get("tbl_order", GRID_ORDER)
    sel = [name for name in order
           if st.session_state.get(f"tbl::{name}", True) and name in tables]
    if not sel:
        st.info("No products selected — pick some from the sidebar.")
    for i in range(0, len(sel), 2):
        cols = st.columns(2)
        for col, name in zip(cols, sel[i:i + 2]):
            with col:
                render_table(tables[name])

    # Fill the slot reserved above the tables. This runs AFTER render_table(), because that
    # is what evaluates the thresholds and raises the alerts -- rendering the popups earlier
    # would always be one poll behind.
    with notif_slot:
        taps_alerts.render_popups()


live()


# ======================================================================================
# SPOKEN ALERTS — retained, commented out. Not wired to anything; delete or restore at will.
#
# This spoke the alert instead of (or alongside) the popup, e.g.
#     "Gas oil. 508 kay bee traded at premium at 4:59PM"
# One clip per alert: chime + 0.7s gap + product name + 0.5s pause + the rest, built
# server-side as a SINGLE wav so the chime and speech can never overlap.
#
# To restore:
#   1. paste the blocks below back in at the marked places and set AUDIO_ENABLED = True;
#   2. the trigger loop in render_table() must also queue the sentence:
#          if AUDIO_ENABLED and st.session_state.get("chime_on"):
#              st.session_state.speak.append(
#                  _alert_sentence(t["title"], _g, _grp_sum(_g), _when))
#   3. re-add the session keys: "speak" (list), "chime_now" (bool);
#   4. add to requirements.txt:  gtts, imageio-ffmpeg, audioop-lts
#      (audioop left the stdlib in Python 3.13, and pydub/ffmpeg decode the mp3);
#   5. keep the once-per-CHUNK latch — per table would silence a table's second side.
#
# Notes worth keeping: browsers block autoplay until the user interacts, so the toggle's
# own click doubles as the unlock gesture; and the volume is spoken "kay bee"/"kay tee"
# because TTS reads "kb"/"kt" as gibberish.
# ======================================================================================
#  --- master switch + chime synthesis ---
#  AUDIO_ENABLED = False   # TEMPORARY: audio parked while the flashing highlight is trialled
#
#  @st.cache_data
#  def _chime_wav() -> bytes:
#      """A short two-tone chime, synthesised so there is no asset to host or fetch."""
#      rate, out = 44100, bytearray()
#      for freq, secs in ((880.0, 0.14), (1174.7, 0.26)):      # A5 -> D6
#          n = int(rate * secs)
#          for i in range(n):
#              fade = min(1.0, i / (rate * 0.01)) * (1.0 - i / n) ** 2   # attack + decay
#              out += struct.pack("<h", int(0.5 * fade * 32767
#                                           * math.sin(2 * math.pi * freq * i / rate)))
#      buf = io.BytesIO()
#      with wave.open(buf, "wb") as w:
#          w.setnchannels(1)
#          w.setsampwidth(2)
#          w.setframerate(rate)
#          w.writeframes(bytes(out))
#      return buf.getvalue()
#
#
#
#  --- spoken product names ---
#  SPOKEN_NAME = {
#      "Dubai":     "Dubai",
#      "Brent SMM": "Brent Marker",
#      "S92":       "92 Ron",
#      "MOPJ":      "mop J",
#      "SGO":       "Gas oil",
#      "SKO":       "Kerro",        # "Kero" as in kerosene — chosen from the voice-test alternatives
#      "S0.5":      "point five",
#      "S380":      "Three eighty",
#      "LSGO SMM":  "Gas oil Marker",
#  }
#  # $/mt products: their thresholds are divided by a bbl/mt factor, so the volumes are
#  # tonnes (kt). Everything else is barrels (kb).
#
#  --- TTS + single-clip builder (chime + gap + name + pause + rest) ---
#  @st.cache_data(show_spinner=False)
#  def _tts(text: str) -> bytes:
#      """Synthesise one phrase to mp3. Cached, so each distinct sentence costs one call."""
#      from gtts import gTTS
#      buf = io.BytesIO()
#      gTTS(text=text, lang="en", tld="com").write_to_fp(buf)
#      return buf.getvalue()
#
#
#
#  # One alert = chime + gap + name + pause + rest, rendered as a SINGLE clip. Building it
#  # server-side is what guarantees the chime and the speech can never overlap: two
#  # autoplaying <audio> elements would start together and talk over each other, and the
#  # page's poll interval is far too coarse to sequence them.
#  PCM_RATE = 24000
#  CHIME_GAP_MS = 700       # chime -> first word
#  NAME_PAUSE_MS = 500      # after the product name; TTS rattles short names off too fast
#
#
#  def _ffmpeg_exe() -> str:
#      import imageio_ffmpeg
#      return imageio_ffmpeg.get_ffmpeg_exe()
#
#
#  def _mp3_to_pcm(mp3: bytes) -> bytes:
#      """Decode mp3 -> raw signed 16-bit mono PCM at PCM_RATE, so clips can be concatenated."""
#      import subprocess
#      r = subprocess.run([_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
#                          "-f", "s16le", "-acodec", "pcm_s16le",
#                          "-ar", str(PCM_RATE), "-ac", "1", "pipe:1"],
#                         input=mp3, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#      if r.returncode:
#          raise RuntimeError(r.stderr[:200].decode("utf-8", "replace"))
#      return r.stdout
#
#
#  def _chime_pcm() -> bytes:
#      out = bytearray()
#      for freq, secs in ((880.0, 0.14), (1174.7, 0.26)):          # A5 -> D6
#          n = int(PCM_RATE * secs)
#          for i in range(n):
#              fade = min(1.0, i / (PCM_RATE * 0.01)) * (1.0 - i / n) ** 2
#              out += struct.pack("<h", int(0.5 * fade * 32767
#                                           * math.sin(2 * math.pi * freq * i / PCM_RATE)))
#      return bytes(out)
#
#
#  def _silence_pcm(ms: int) -> bytes:
#      return bytes(2 * int(PCM_RATE * ms / 1000))   # 2 bytes per silent sample
#
#
#  @st.cache_data(show_spinner=False)
#  def _alert_audio(sentence: str) -> bytes:
#      """The full alert as one wav: chime, gap, "<name>.", pause, then the rest."""
#      head, sep, tail = sentence.partition(". ")
#      pcm = _chime_pcm() + _silence_pcm(CHIME_GAP_MS) + _mp3_to_pcm(_tts(head + "."))
#      if tail:
#          pcm += _silence_pcm(NAME_PAUSE_MS) + _mp3_to_pcm(_tts(tail))
#      buf = io.BytesIO()
#      with wave.open(buf, "wb") as w:
#          w.setnchannels(1)
#          w.setsampwidth(2)
#          w.setframerate(PCM_RATE)
#          w.writeframes(pcm)
#      return buf.getvalue()
#
#
#  def _volume_phrase(title: str, total: float) -> str:
#      if title in CONV_TABLES:
#          return f"{round(total):g} kay tee"
#      if total >= 1000:                       # read big barrel counts as millions
#          return f"{total / 1000:g} million barrels"
#      return f"{total:g} kay bee"
#
#
#  def _alert_sentence(title: str, group: str, total: float, when_iso: str) -> str:
#      side = "premium" if group == "+" else "discount"
#      try:
#          clock = datetime.fromisoformat(when_iso).strftime("%I:%M%p").lstrip("0")
#      except Exception:
#          clock = ""
#      return (f"{SPOKEN_NAME.get(title, title)}. {_volume_phrase(title, total)} "
#              f"traded at {side} at {clock}")
#
#
#
#  --- sidebar toggle + voice-test panel ---
#  def _chime_test():
#      """Ticking the box is the user gesture browsers require before audio may play, so
#      sound a confirmation chime right then — it proves it works AND unlocks audio for the
#      session. Without a gesture the first real alert is silently swallowed by autoplay policy."""
#      if st.session_state.get("chime_on"):
#          st.session_state.speak.append("Voice alerts enabled")
#
#
#  if AUDIO_ENABLED:
#      st.sidebar.checkbox("🔊 Voice alert on first highlight", key="chime_on",
#                      on_change=_chime_test,
#                      help="One spoken alert per table, the first time it highlights each day.")
#  if AUDIO_ENABLED:
#      st.sidebar.checkbox("🧪 Voice test (temporary)", key="voice_test",
#                      help="Preview product-name pronunciation and full alert sentences.")
#
#  # TEMPORARY preview panel — delete once the wording and pronunciation are signed off.
#  if st.session_state.get("voice_test"):
#      with st.expander("🧪 Voice test — product names & sample sentences", expanded=True):
#          st.caption("Press play on each; nothing autoplays. Each phrase is synthesised once and cached.")
#          st.markdown("**Product names**")
#          for _title, _spoken in SPOKEN_NAME.items():
#              _c1, _c2, _c3 = st.columns([2, 3, 5])
#              _c1.markdown(f"`{_title}`")
#              _c2.markdown(f"→ *{_spoken}*")
#              with _c3:
#                  st.audio(_tts(_spoken), format="audio/mp3")
#          st.divider()
#          st.markdown("**SKO alternatives** — pick whichever lands closest to *kerosene*")
#          for _alt in ["Care-oh", "Kair-oh", "Care oh", "Kerro", "Kero"]:
#              _a1, _a2 = st.columns([5, 5])
#              _a1.markdown(f"*{_alt}*")
#              with _a2:
#                  st.audio(_tts(_alt), format="audio/mp3")
#          st.divider()
#          st.markdown("**Sample sentences**")
#          for _t, _g, _v in [
#              ("Dubai", "+", 1000.0),      # -> "1 million barrels"
#              ("Dubai", "+", 1500.0),      # -> "1.5 million barrels"
#              ("SGO", "+", 508.0),         # kb — today's real SGO trigger
#              ("S92", "-", 640.0),         # kb, discount side
#              ("S0.5", "-", 78.7),         # kt — conversion product
#              ("SKO", "-", 512.0),         # kb — hear SKO inside a full sentence
#              ("S380", "-", 78.2),         # kt -> rounds DOWN to 78
#              ("MOPJ", "+", 56.6),         # kt -> rounds UP to 57
#              ("Brent SMM", "+", 900.0),   # kb — PREM now maps to '+'
#          ]:
#              _sent = _alert_sentence(_t, _g, _v, "2026-08-18T16:23:00")
#              _c1, _c2 = st.columns([6, 4])
#              _c1.markdown(f"*{_sent}*")
#              with _c2:
#                  st.audio(_alert_audio(_sent), format="audio/wav")
#  st.sidebar.divider()
#
#
#  --- playback, at the end of live() ---
#      # At most one chime per rerun, after the tables have set the flag. The element renders
#      # ONLY on the triggering run, so it mounts, plays once, and is gone by the next poll.
#      # Hidden via CSS: autoplay still fires, but no stray player widget appears on the page.
#      with notif_slot:
#          taps_alerts.render_popups()
#
#      if AUDIO_ENABLED and st.session_state.chime_now and st.session_state.get("chime_on"):
#          st.markdown('<style>[data-testid="stAudio"]{display:none;}</style>',
#                      unsafe_allow_html=True)
#          st.audio(_chime_wav(), format="audio/wav", autoplay=True)
#      st.session_state.chime_now = False
#
#      # Speak ONE queued alert per rerun — two clips autoplaying together would talk over each
#      # other, so anything else waits for the next poll (seconds away). Rendered only on the
#      # run that plays it, so it mounts, speaks once, and is gone by the next poll.
#      if AUDIO_ENABLED and st.session_state.speak and st.session_state.get("chime_on"):
#          _line = st.session_state.speak.pop(0)
#          st.markdown('<style>[data-testid="stAudio"]{display:none;}</style>',
#                      unsafe_allow_html=True)
#          try:
#              st.audio(_alert_audio(_line), format="audio/wav", autoplay=True)
#          except Exception:                      # TTS unreachable -> fall back to the chime
#              st.audio(_chime_wav(), format="audio/wav", autoplay=True)
#          st.caption(f"🔊 {_line}")              # visible too, so a muted tab still sees it
#
#
#
