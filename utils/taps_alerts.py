"""Shared alert state + popup rendering for the TAPS page.

Lives here rather than inside pages/TAPS.py so the test harness (pages/TAPS_Test.py) can
drive the REAL rendering and the REAL latch, instead of a copy that could drift from it.

The contract:
  * one alert per CHUNK -- a chunk is (table, group), group being "+" premium or
    "-" discount, so a single table can raise two independent alerts in a day;
  * an alert fires ONCE, the first time its threshold is crossed that trading day.
    `fired` is write-once per key; nothing re-arms it except the 05:00 day rollover;
  * crossing a popup marks the chunk acknowledged, which only hides that popup. The
    table keeps its static highlight for the rest of the day.
"""
import io

import streamlit as st

# Popup geometry. Boxes are position:fixed so they float over the page instead of pushing
# the tables down, and stack downwards when several chunks are live.
POPUP_TOP_REM = 5.0        # first box, clear of the Streamlit header
POPUP_STEP_REM = 6.4       # vertical pitch between stacked boxes
POPUP_WIDTH_PX = 470

# What the popup calls each side. The record stores the domain term ("premium" /
# "discount"); this is purely how it reads on screen.
SIDE_WORD = {"premium": "bid", "discount": "offer"}



def _shadow() -> str:
    """Drop shadow for the popup, flipped for dark themes.

    A black shadow is invisible against a dark page, so use a soft white halo there.
    Streamlit's own theme is the authority rather than a prefers-color-scheme media query:
    that would miss someone who picks Dark in Streamlit while their OS stays light.
    Unknown theme falls back to the dark-on-light shadow.
    """
    try:
        theme = st.context.theme
        kind = getattr(theme, "type", None) or (theme or {}).get("type")
    except Exception:
        kind = None
    return ("0 6px 22px rgba(255,255,255,0.5)" if kind == "dark"
            else "0 6px 20px rgba(0,0,0,0.35)")


# --- spoken alert -------------------------------------------------------------------
# Two words only: the product, then bid/offer. Table titles are acronyms that read badly
# aloud, so each maps to a spoken form ("SGO" -> "Gas oil", "SKO" -> "Kerro").
SPOKEN_NAME = {
    "Dubai":     "Dubai",
    "Brent SMM": "Brent Marker",
    "S92":       "92 Ron",
    "MOPJ":      "mop J",
    "SGO":       "Gas oil",
    "SKO":       "Kerro",
    "S0.5":      "point five",
    "S380":      "Three eighty",
    "LSGO SMM":  "Gas oil Marker",
}
AUDIO_SPEED = 1.3      # gTTS has no rate control, so ffmpeg's atempo does the speed-up


def phrase(title: str, side: str) -> str:
    return f"{SPOKEN_NAME.get(title, title)} {SIDE_WORD.get(side, side)}"


# Two quick beeps before the speech. Mid pitch -- high enough to carry, well below the
# shrill 1.7-2.3 kHz of an alarm. The envelope is flat-topped rather than decaying: a beep
# that HOLDS its level sounds far louder than one that dies away the moment it starts,
# which is what keeps this audible without pushing the frequency up.
# Built into the SAME clip as the speech, so the two can never overlap.
PCM_RATE = 24000
CHIME_AMP = 0.92                                   # normalised to true peak
BEEP_COUNT = 2
BEEP_FREQ = 780.0                                  # ~G5
BEEP_LEN = 0.085                                   # seconds per beep
BEEP_GAP = 0.070                                   # silence between the two
BEEP_HARMONICS = ((1, 1.0), (2, 0.28), (3, 0.16))  # a little edge, still musical
CHIME_GAP_MS = 180                                 # silence before the first word


def _chime_pcm() -> bytes:
    """Two beeps, normalised to CHIME_AMP by the waveform's TRUE peak.

    Scaling by the sum of harmonic amplitudes wastes headroom -- harmonics do not peak in
    phase -- so the real maximum is measured instead.
    """
    import math
    import struct
    n_beep = int(PCM_RATE * BEEP_LEN)
    samples = []
    for i in range(n_beep):
        t = i / PCM_RATE
        attack = min(1.0, i / (PCM_RATE * 0.003))                  # snap on
        release = min(1.0, (n_beep - i) / (PCM_RATE * 0.010))      # brief tail off
        v = sum(a * math.sin(2 * math.pi * BEEP_FREQ * h * t) for h, a in BEEP_HARMONICS)
        samples.append(attack * release * v)
    peak = max((abs(x) for x in samples), default=1.0) or 1.0
    scale = CHIME_AMP / peak
    beep = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767))
                    for x in samples)
    silence = bytes(2 * int(PCM_RATE * BEEP_GAP))
    return (beep + silence) * (BEEP_COUNT - 1) + beep


def _mp3_to_pcm(mp3: bytes) -> bytes:
    """Decode mp3 -> raw s16le mono PCM at PCM_RATE so it can be concatenated."""
    import subprocess
    import imageio_ffmpeg
    r = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le",
         "-ar", str(PCM_RATE), "-ac", "1", "pipe:1"],
        input=mp3, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode:
        raise RuntimeError(r.stderr[:200].decode("utf-8", "replace"))
    return r.stdout


@st.cache_data(show_spinner=False)
def _say(text: str) -> bytes:
    """chime + gap + speech as ONE wav. Speech is gTTS (no rate control of its own), sped
    up by ffmpeg's atempo. Cached, so each distinct phrase is synthesised once."""
    import subprocess
    import wave
    import imageio_ffmpeg
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang="en", tld="com").write_to_fp(buf)
    fast = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-filter:a", f"atempo={AUDIO_SPEED}", "-f", "mp3", "pipe:1"],
        input=buf.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if fast.returncode:
        raise RuntimeError(fast.stderr[:200].decode("utf-8", "replace"))
    pcm = (_chime_pcm()
           + bytes(2 * int(PCM_RATE * CHIME_GAP_MS / 1000))      # 2 bytes per silent sample
           + _mp3_to_pcm(fast.stdout))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(PCM_RATE)
        w.writeframes(pcm)
    return out.getvalue()


def _on_audio_toggled() -> None:
    """Speak whatever is already on screen when audio is switched on.

    Without this, enabling audio mid-session is silent: chunks that crossed while it was
    off have already been latched by trigger(), which is write-once, so nothing will ever
    queue a phrase for them again today. Turning the toggle on therefore replays the
    alerts still showing, and only those -- anything crossed off stays quiet.
    """
    if not st.session_state.get("audio_on"):
        return
    for key, rec in st.session_state.get("fired", {}).items():
        if key not in st.session_state.get("acked", set()):
            st.session_state.speak.append(phrase(rec["title"], rec["side"]))


def audio_toggle() -> None:
    """Sidebar switch, off by default. Ticking it is also the user gesture browsers demand
    before audio may autoplay — without one the first alert is silently swallowed."""
    st.sidebar.checkbox("🔊 Enable audio", key="audio_on", on_change=_on_audio_toggled,
                        help="Speaks the product and side when an alert is raised.")


def play_queued() -> None:
    """Speak everything queued as ONE utterance.

    Two chunks can be raised on the same poll, and two autoplaying <audio> elements would
    start together and talk over each other. Draining the whole queue into a single clip
    ("Gas oil bid. Dubai offer") makes overlap impossible by construction, rather than
    relying on the gap between polls -- which a click-driven rerun can cut short.
    Rendered only on the run that plays it, so it mounts, speaks once, and is gone.
    Hidden: autoplay still fires, but no stray player widget appears on the page.
    """
    if not (st.session_state.get("audio_on") and st.session_state.get("speak")):
        return
    lines, st.session_state.speak = st.session_state.speak, []
    # Hidden: autoplay still fires, but no player widget clutters the page.
    st.markdown('<style>[data-testid="stAudio"]{display:none;}</style>',
                unsafe_allow_html=True)
    try:
        st.audio(_say(". ".join(lines)), format="audio/wav", autoplay=True)
    except Exception:
        pass          # TTS/ffmpeg unreachable -> stay silent; the popup still shows


def init_state() -> None:
    st.session_state.setdefault("fired", {})     # "table|group" -> alert record, write-once
    st.session_state.setdefault("acked", set())  # chunks crossed off by the user
    st.session_state.setdefault("speak", [])     # phrases waiting to be spoken


def clear() -> None:
    """Drop today's latches — the 05:00 rollover, and the test harness's reset."""
    st.session_state.fired = {}
    st.session_state.acked = set()
    st.session_state.speak = []


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
    if st.session_state.get("audio_on"):
        st.session_state.speak.append(phrase(title, side))
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
    _sh = _shadow()
    for n, (k, _) in enumerate(live):
        sl = slug(k)
        top = POPUP_TOP_REM + n * POPUP_STEP_REM
        css.append(
            f'div.st-key-popup_{sl} {{position:fixed;top:{top}rem;right:1.5rem;'
            f'width:{POPUP_WIDTH_PX}px;z-index:9999;background:rgba(255,214,0,0.97);'
            f'border-radius:0.8rem;padding:1.05rem 0.8rem 1.05rem 1.4rem;'
            f'box-shadow:{_sh};}}'
            f'div.st-key-popup_{sl} p {{color:#111;font-weight:700;'
            f'margin:0;padding:0;font-size:1.5rem;line-height:2.1rem;}}'
            # The X is laid out by a column, NOT absolute positioning: Streamlit wraps
            # buttons in their own block, so position:absolute fell back into normal flow
            # and dropped the X below the text. A column keeps it on the same line, right.
            f'div.st-key-popup_{sl} button {{background:transparent;border:none;'
            f'color:#111;font-weight:800;min-height:0;height:2rem;'
            f'font-size:1.5rem;padding:0 0.35rem;line-height:1;}}'
            f'div.st-key-popup_{sl} button:hover {{color:#b00;background:transparent;}}'
            # Centring the text needed more than columns(vertical_alignment): the button
            # is taller than a line of text, so the row height comes from the button and
            # Streamlit's own column wrappers (stColumn > stVerticalBlock >
            # stElementContainer) each add gap/margin that push the paragraph down. Make
            # every one of those a centred flex box so the text sits on the button's axis.
            f'div.st-key-popup_{sl} div[data-testid="stHorizontalBlock"]'
            f'  {{gap:0.3rem;align-items:center;}}'
            f'div.st-key-popup_{sl} div[data-testid="stColumn"]'
            f'  {{display:flex;align-items:center;min-height:2rem;}}'
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
            _side = SIDE_WORD.get(r["side"], r["side"])
            c1.markdown(f'{r["ts"]} - [{r["title"]}] {r["vol"]} {r["unit"]} {_side}')
            if c2.button("✕", key=f"popup_btn::{k}", help="Dismiss"):
                st.session_state.acked.add(k)
                try:
                    # scope="fragment" is the cheap rerun on the live page; outside a
                    # fragment (the test harness) it raises, so fall back to a full rerun.
                    # Safe to catch broadly: RerunException derives from BaseException.
                    st.rerun(scope="fragment")
                except Exception:
                    st.rerun()
