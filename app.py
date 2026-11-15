import html
import json
import random
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit import runtime

# Lets PyCharm's Run button work: re-launch through `streamlit run` when started as plain Python.
if __name__ == "__main__" and not runtime.exists():
    from streamlit.web import cli

    sys.argv = ["streamlit", "run", __file__]
    sys.exit(cli.main())

# ------------------------------------------------------------
# Flame in Freefall | Streamlit interface · v1.0
# Place this file in the root of the Flames_of_Aron repository (next to agent.py)
# Run: streamlit run app.py
#
# Data comes from the repository, nothing is hard-coded here:
#   Ask the Expert       agent.answer_question()  (router -> tools -> evidence bundle -> LLM -> validator)
#   Experiment Explorer  processed/golden_table.csv, golden_table_conflicts.csv, reference/manifest.csv
#   Atmosphere Check     tools.query_psi_tests(), tools.lunar_check(), tools.calculate()
#   Chat history         chat_history/<id>.json (local files; add chat_history/ to .gitignore)
# ------------------------------------------------------------
#
# DESIGN TOKENS (single source of truth; mirrored in CSS :root)
#   Color   void #05070d · surface rgba(255,255,255,.035) · line rgba(255,255,255,.08)
#           text #e9eef6 / #a3afc0 / #6b778a
#           flame  #ff7a4d  → primary accent, fire, user state
#           ember  #ffb36b  → flame highlights, particles, "nearest"
#           nebula #8aa8ff  → references, prevention, microgravity "blue flame" rim
#           aurora #5fd4c4  → detection · verified
#           amber  #f2b84b  → pending expert review
#   Type    Space Grotesk (display) · DM Sans (body) · JetBrains Mono (data & labels)
#   Space   4 · 8 · 12 · 16 · 24 · 32 · 48 px
#   Radius  8 · 12 · 20 · pill
#   Motion  150ms (hover) · 300ms (enter/expand) · 600ms+ (ambient)
#           ease cubic-bezier(.2,.8,.2,1); everything stops under prefers-reduced-motion.
# ------------------------------------------------------------

st.set_page_config(
    page_title="Flame in Freefall",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "chat_history"

try:
    import agent
    import evidence
    import investigations
    import tools
except ImportError as exc:  # app.py is not in the repository root, or requirements are missing
    st.error(
        f"Could not import the project modules ({exc}). Put app.py in the root of the "
        "Flames_of_Aron repository and run `pip install -r requirements.txt streamlit plotly`."
    )
    st.stop()

FLAME, EMBER, NEBULA, AURORA, AMBER = "#ff7a4d", "#ffb36b", "#8aa8ff", "#5fd4c4", "#f2b84b"
TEXT, TEXT_2, TEXT_3 = "#e9eef6", "#a3afc0", "#6b778a"
CATEGORY_COLOR = {"prevention": NEBULA, "detection": AURORA, "suppression": FLAME}

LUNAR_O2_MIN = tools.LUNAR_O2_MIN * 100                      # % [F-005]
LUNAR_P_MAX = tools.LUNAR_PRESSURE_MAX_PSI                   # psi [F-005]
EARTH_O2 = tools.EARTH_O2 * 100                              # % [C-002]
EARTH_P = tools.EARTH_PRESSURE_PSI                           # psi [F-002]
EARTH_PO2 = round(tools.EARTH_O2 * tools.EARTH_PRESSURE_PSI, 2)
SUIT_O2, SUIT_P = tools.SUIT_O2 * 100, tools.SUIT_PRESSURE_PSI  # [F-001]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


# ------------------------------------------------------------
# Generated decoration (seeded so it stays stable across reruns)
# ------------------------------------------------------------
def star_layer(n: int, size: float, alpha: float, seed: int) -> str:
    rng = random.Random(seed)
    dots = []
    for _ in range(n):
        x, y = rng.uniform(0, 100), rng.uniform(0, 100)
        a = alpha * rng.uniform(0.45, 1)
        dots.append(
            f"radial-gradient({size}px {size}px at {x:.2f}% {y:.2f}%, "
            f"rgba(255,255,255,{a:.2f}) 50%, transparent 100%)"
        )
    return ",".join(dots)


def flame_orb(size: int, embers: int, seed: int) -> str:
    """Spherical microgravity flame: no buoyancy, so embers drift out in every direction."""
    rng = random.Random(seed)
    sparks = "".join(
        f'<i class="ember" style="--a:{rng.uniform(0, 360):.0f}deg;--t:{rng.uniform(2.4, 4.6):.2f}s;'
        f'--d:-{rng.uniform(0, 4.6):.2f}s"></i>'
        for _ in range(embers)
    )
    return (
        f'<div class="ff-flame" style="--sz:{size}px">'
        '<div class="halo"></div><div class="shell"></div><div class="core"></div>'
        f"{sparks}</div>"
    )


def drifting_embers(n: int, seed: int) -> str:
    rng = random.Random(seed)
    return '<div class="ff-drift">' + "".join(
        f'<i style="left:{rng.uniform(0, 100):.1f}%;top:{rng.uniform(0, 100):.1f}%;'
        f'--dx:{rng.uniform(-60, 60):.0f}px;--dy:{rng.uniform(-60, 60):.0f}px;'
        f'--t:{rng.uniform(9, 18):.1f}s;--d:-{rng.uniform(0, 18):.1f}s"></i>'
        for _ in range(n)
    ) + "</div>"


STARS_FAR = star_layer(90, 1, 0.55, 7)
STARS_NEAR = star_layer(28, 1.6, 0.9, 21)

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {{
  --c-void:#05070d; --c-surface:rgba(255,255,255,.035); --c-surface-hi:rgba(255,255,255,.065);
  --c-line:rgba(255,255,255,.08); --c-line-hi:rgba(255,255,255,.18);
  --c-text:{TEXT}; --c-text-2:{TEXT_2}; --c-text-3:{TEXT_3};
  --c-flame:{FLAME}; --c-flame-soft:rgba(255,122,77,.14); --c-ember:{EMBER};
  --c-nebula:{NEBULA}; --c-nebula-soft:rgba(138,168,255,.12);
  --c-aurora:{AURORA}; --c-amber:{AMBER};
  --g-fire:linear-gradient(135deg, #ffd08a 0%, #ff7a4d 45%, #e2453c 100%);
  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px; --s-5:24px; --s-6:32px; --s-7:48px;
  --r-sm:8px; --r-md:12px; --r-lg:20px; --r-pill:999px;
  --dur-1:150ms; --dur-2:300ms; --ease:cubic-bezier(.2,.8,.2,1);
  --f-display:'Space Grotesk',system-ui,sans-serif; --f-body:'DM Sans',system-ui,sans-serif; --f-mono:'JetBrains Mono',ui-monospace,monospace;
}}

/* ---------- Canvas: deep space with a warm horizon ---------- */
[data-testid="stApp"] {{
  background:
    radial-gradient(1100px 600px at 85% -15%, rgba(138,168,255,.10), transparent 60%),
    radial-gradient(1000px 420px at 50% 112%, rgba(255,122,77,.12), transparent 65%),
    var(--c-void);
  color:var(--c-text); font-family:var(--f-body);
}}
[data-testid="stApp"]::before, [data-testid="stApp"]::after {{
  content:""; position:fixed; left:0; right:0; top:0; height:200vh; pointer-events:none; z-index:0;
}}
[data-testid="stApp"]::before {{ background-image:{STARS_FAR}; background-size:100% 100vh; animation:drift 240s linear infinite; }}
[data-testid="stApp"]::after {{ background-image:{STARS_NEAR}; background-size:100% 100vh;
  animation:drift 140s linear infinite, twinkle 6s ease-in-out infinite alternate; }}
@keyframes drift {{ from {{ transform:translateY(0) }} to {{ transform:translateY(-100vh) }} }}
@keyframes twinkle {{ from {{ opacity:.55 }} to {{ opacity:1 }} }}

[data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stMain"] {{ background:transparent; }}
[data-testid="stAppViewContainer"] > * {{ position:relative; z-index:1; }}
[data-testid="stHeader"] {{ height:0; }}
[data-testid="stSidebar"] {{ background:rgba(8,11,18,.88); border-right:1px solid var(--c-line); backdrop-filter:blur(10px); }}
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] {{ display:none !important; }}
[data-testid="stSidebar"] .stButton > button {{ justify-content:flex-start; text-align:left; min-height:2.3rem; font-size:.86rem;
  background:transparent; border-color:transparent; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
[data-testid="stSidebar"] .stButton > button p {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background:var(--c-surface-hi); border-color:var(--c-line); transform:none; }}
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {{ background:var(--c-flame-soft); border-color:rgba(255,122,77,.35); color:var(--c-text); }}
[data-testid="stSidebar"] .st-key-new_chat button {{ border:1px solid var(--c-line-hi); justify-content:center; background:var(--c-surface); }}
.block-container {{ padding-top:var(--s-6); max-width:1180px; }}
footer {{ visibility:hidden; }}
[data-testid="stStatusWidget"] {{ display:none; }}

/* Page transition: new elements rise in softly */
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"] {{ animation:fadein 450ms var(--ease) both; }}
[data-testid="stElementContainer"]:has(.ff-splash), [data-testid="stElementContainer"]:has(.ff-drift) {{ animation:none; }}
@keyframes fadein {{ from {{ opacity:0 }} to {{ opacity:1 }} }}

h1, h2, h3 {{ font-family:var(--f-display); color:var(--c-text); letter-spacing:-.03em; }}
h1 {{ font-size:2.4rem !important; font-weight:600 !important; }}
p, li {{ color:var(--c-text-2); }}

/* Ambient embers drifting weightlessly */
.ff-drift {{ position:fixed; inset:0; pointer-events:none; z-index:-1; }}
.ff-drift i {{ position:absolute; width:3px; height:3px; border-radius:50%; background:var(--c-ember);
  box-shadow:0 0 8px 1px rgba(255,122,77,.7); opacity:0; animation:float var(--t) ease-in-out var(--d) infinite; }}
@keyframes float {{ 0% {{ opacity:0; transform:translate(0,0) }} 20% {{ opacity:.55 }} 80% {{ opacity:.35 }}
  100% {{ opacity:0; transform:translate(var(--dx),var(--dy)) }} }}

/* ---------- Primitives ---------- */
.ff-eyebrow {{ font-family:var(--f-mono); font-size:.68rem; letter-spacing:.18em; text-transform:uppercase; color:var(--c-flame); }}
.ff-muted {{ color:var(--c-text-3); }}
.ff-mono {{ font-family:var(--f-mono); }}
.ff-fire-text {{ background:var(--g-fire); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.ff-card {{ background:var(--c-surface); border:1px solid var(--c-line); border-radius:var(--r-md);
  padding:var(--s-4) var(--s-5); backdrop-filter:blur(6px);
  transition:border-color var(--dur-1) var(--ease), transform var(--dur-2) var(--ease), background var(--dur-1); }}
.ff-card.hover:hover {{ border-color:var(--c-line-hi); background:var(--c-surface-hi); transform:translateY(-2px); }}
.ff-chip {{ display:inline-flex; align-items:center; gap:6px; font-family:var(--f-mono); font-size:.68rem;
  color:var(--c-text-2); border:1px solid var(--c-line); border-radius:var(--r-pill); padding:3px 10px; }}
.ff-chip.ok {{ color:var(--c-aurora); border-color:rgba(95,212,196,.35); background:rgba(95,212,196,.06); }}
.ff-chip.missing {{ color:var(--c-text-3); border-style:dashed; }}
.ff-chip.pending {{ color:var(--c-amber); border-color:rgba(242,184,75,.35); background:rgba(242,184,75,.06); }}
.ff-dot {{ width:6px; height:6px; border-radius:50%; display:inline-block; flex:none; }}
.ff-live {{ animation:pulse 2.4s ease-in-out infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity:.35 }} 50% {{ opacity:1 }} }}
.ff-enter {{ animation:enter var(--dur-2) var(--ease) both; }}
@keyframes enter {{ from {{ opacity:0; transform:translateY(8px) }} to {{ opacity:1; transform:none }} }}

/* ---------- Microgravity flame orb ---------- */
.ff-flame {{ position:relative; width:var(--sz); height:var(--sz); flex:none; }}
.ff-flame > div {{ position:absolute; border-radius:50%; }}
.ff-flame .halo {{ inset:-35%; background:radial-gradient(circle, rgba(110,150,255,.26) 0%, rgba(110,150,255,.07) 45%, transparent 70%);
  animation:breathe 3.4s ease-in-out infinite; }}
.ff-flame .shell {{ inset:0; filter:blur(1.5px);
  background:radial-gradient(circle, rgba(255,214,160,.95) 0 20%, rgba(255,122,77,.85) 42%, rgba(226,69,60,.5) 56%, rgba(120,150,255,.45) 66%, rgba(80,120,255,0) 72%);
  animation:flicker 2.6s ease-in-out infinite; }}
.ff-flame .core {{ inset:31%; background:radial-gradient(circle, #fffaf0 0%, #ffd08a 55%, rgba(255,208,138,0) 75%);
  animation:flicker 1.3s ease-in-out infinite reverse; }}
.ff-flame .ember {{ position:absolute; left:50%; top:50%; width:3px; height:3px; margin:-1.5px; border-radius:50%;
  background:var(--c-ember); box-shadow:0 0 6px var(--c-flame); opacity:0;
  animation:emit var(--t) linear var(--d) infinite; }}
@keyframes emit {{
  0% {{ transform:rotate(var(--a)) translateX(calc(var(--sz) * .32)); opacity:0 }}
  15% {{ opacity:1 }}
  100% {{ transform:rotate(var(--a)) translateX(calc(var(--sz) * 1.05)); opacity:0 }} }}
@keyframes flicker {{ 0%,100% {{ transform:scale(1) }} 30% {{ transform:scale(1.04) }} 60% {{ transform:scale(.97) }} }}
@keyframes breathe {{ 0%,100% {{ opacity:.7; transform:scale(1) }} 50% {{ opacity:1; transform:scale(1.08) }} }}

/* ---------- Splash ---------- */
.ff-splash {{ position:fixed; inset:0; z-index:999999; display:grid; place-items:center; pointer-events:none;
  background:radial-gradient(700px 500px at 50% 45%, rgba(255,122,77,.10), transparent 70%), var(--c-void);
  animation:splashOut 900ms var(--ease) 2.9s forwards; }}
.ff-splash .inner {{ display:flex; flex-direction:column; align-items:center; gap:var(--s-4); text-align:center; }}
.ff-splash .inner > * {{ animation:enter 700ms var(--ease) both; }}
.ff-splash .inner > :nth-child(2) {{ animation-delay:.35s }}
.ff-splash .inner > :nth-child(3) {{ animation-delay:.55s }}
.ff-splash .inner > :nth-child(4) {{ animation-delay:.75s }}
.ff-splash .inner > :nth-child(5) {{ animation-delay:.95s }}
.ff-splash .title {{ font-family:var(--f-display); font-size:3rem; font-weight:700; letter-spacing:-.04em; line-height:1; margin-top:var(--s-6); }}
.ff-splash .bar {{ width:180px; height:2px; background:var(--c-line); border-radius:2px; overflow:hidden; }}
.ff-splash .bar::after {{ content:""; display:block; height:100%; background:var(--g-fire); animation:load 2.2s var(--ease) .6s both; }}
@keyframes load {{ from {{ width:0 }} to {{ width:100% }} }}
@keyframes splashOut {{ to {{ opacity:0; visibility:hidden; transform:scale(1.03) }} }}

/* ---------- Header ---------- */
.ff-brand {{ display:flex; align-items:center; gap:10px; font-family:var(--f-display); font-weight:700;
  letter-spacing:.12em; font-size:.86rem; color:var(--c-text); white-space:nowrap; }}

/* Segmented nav & pills */
[data-testid="stButtonGroup"] button {{ background:transparent !important; border:1px solid transparent !important;
  color:var(--c-text-2) !important; border-radius:var(--r-pill) !important; transition:all var(--dur-1) var(--ease); }}
[data-testid="stButtonGroup"] button:hover {{ color:var(--c-text) !important; background:var(--c-surface-hi) !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[data-selected="true"] {{
  color:var(--c-text) !important; background:var(--c-flame-soft) !important; border-color:rgba(255,122,77,.4) !important; }}

/* Buttons */
.stButton > button {{ background:var(--c-surface); color:var(--c-text-2); border:1px solid var(--c-line);
  border-radius:var(--r-md); min-height:2.6rem; transition:all var(--dur-1) var(--ease); }}
.stButton > button:hover {{ border-color:rgba(255,122,77,.55); color:var(--c-text); background:var(--c-surface-hi); transform:translateY(-1px); }}

/* ---------- Chat ---------- */
.st-key-chat {{ max-width:860px; margin:0 auto; width:100%; }}
[data-testid="stChatMessage"] {{ background:transparent; padding:0; gap:var(--s-3); }}
[data-testid="stChatMessageContent"] {{ background:var(--c-surface); border:1px solid var(--c-line);
  border-radius:4px var(--r-lg) var(--r-lg) var(--r-lg); padding:var(--s-4) var(--s-5); }}
[data-testid="stChatMessage"] p {{ color:#dbe3ee; line-height:1.75; margin-bottom:0; }}
/* user turn: right aligned, warm bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ flex-direction:row-reverse; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {{
  flex:0 1 auto; max-width:78%; margin:0 !important; background:var(--c-flame-soft); border-color:rgba(255,122,77,.28);
  border-radius:var(--r-lg) 4px var(--r-lg) var(--r-lg); padding:var(--s-3) var(--s-5); }}
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] p:first-child {{ margin-top:0; }}
[data-testid="stChatMessageAvatarUser"] {{ background:rgba(255,255,255,.06) !important; color:var(--c-text-2) !important; }}
[data-testid="stChatMessageAvatarCustom"] {{ background:transparent !important; }}

/* Larger composer */
[data-testid="stBottom"] > div {{ background:linear-gradient(transparent, rgba(5,7,13,.94) 30%); }}
[data-testid="stBottomBlockContainer"] {{ max-width:900px; padding-bottom:var(--s-6); }}
[data-testid="stChatInput"] {{ border-radius:var(--r-lg) !important; border:1px solid rgba(255,255,255,.12) !important;
  background:rgba(15,21,32,.92) !important; box-shadow:0 0 0 1px transparent, 0 18px 50px -20px rgba(255,122,77,.35);
  transition:border-color var(--dur-1), box-shadow var(--dur-2); }}
[data-testid="stChatInput"]:focus-within {{ border-color:rgba(255,122,77,.6) !important;
  box-shadow:0 0 0 3px rgba(255,122,77,.12), 0 18px 60px -18px rgba(255,122,77,.5); }}
[data-testid="stChatInput"] textarea {{ font-family:var(--f-body); font-size:1.02rem !important; min-height:76px !important;
  padding-top:18px !important; line-height:1.55 !important; }}

/* Thinking indicator */
.ff-think {{ display:flex; align-items:center; gap:10px; font-family:var(--f-mono); font-size:.76rem; color:var(--c-text-2); padding:6px 0; }}
.ff-think .dots i {{ display:inline-block; width:4px; height:4px; margin-left:3px; border-radius:50%; background:var(--c-ember);
  animation:pulse 1s ease-in-out infinite; }}
.ff-think .dots i:nth-child(2) {{ animation-delay:.15s }} .ff-think .dots i:nth-child(3) {{ animation-delay:.3s }}

/* Evidence drawer: opens on hover or keyboard focus */
.ff-evi {{ margin-top:var(--s-4); border-top:1px dashed var(--c-line); padding-top:var(--s-3); outline:none; }}
.ff-evi-tab {{ display:inline-flex; align-items:center; gap:8px; font-family:var(--f-mono); font-size:.7rem; letter-spacing:.06em;
  color:var(--c-text-3); cursor:default; transition:color var(--dur-1); }}
.ff-evi-tab .chev {{ display:inline-block; transition:transform var(--dur-2) var(--ease); }}
.ff-evi-body {{ display:grid; grid-template-rows:0fr; opacity:0; transition:grid-template-rows var(--dur-2) var(--ease), opacity var(--dur-2); }}
.ff-evi-body > div {{ overflow:hidden; }}
.ff-evi-body .src {{ margin-top:var(--s-3); padding:var(--s-3) var(--s-4); border-radius:var(--r-sm);
  background:rgba(255,255,255,.03); border-left:2px solid var(--c-flame); font-family:var(--f-mono); font-size:.74rem; color:var(--c-text); }}
.ff-evi-body .note {{ margin-top:6px; font-size:.72rem; color:var(--c-text-3); }}
.ff-evi:hover .ff-evi-body, .ff-evi:focus-within .ff-evi-body {{ grid-template-rows:1fr; opacity:1; }}
.ff-evi:hover .ff-evi-tab, .ff-evi:focus-within .ff-evi-tab {{ color:var(--c-ember); }}
.ff-evi:hover .chev, .ff-evi:focus-within .chev {{ transform:rotate(180deg); }}

/* Evidence drawer extras */
.ff-evi-body .row {{ display:flex; gap:10px; align-items:baseline; padding:5px 0; font-size:.76rem; color:var(--c-text-2); border-bottom:1px solid var(--c-line); }}
.ff-evi-body .row:last-child {{ border-bottom:0; }}
.ff-evi-body .row .id {{ font-family:var(--f-mono); color:var(--c-ember); flex:none; min-width:54px; }}
.ff-evi-body a {{ color:var(--c-nebula); text-decoration:none; }} .ff-evi-body a:hover {{ text-decoration:underline; }}
.ff-evi-body .meta {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:var(--s-3); }}

/* Data tables */
.ff-table {{ width:100%; border-collapse:collapse; font-family:var(--f-mono); font-size:.76rem; }}
.ff-table th {{ text-align:left; font-weight:500; color:var(--c-text-3); letter-spacing:.08em; font-size:.66rem; text-transform:uppercase;
  padding:6px 10px; border-bottom:1px solid var(--c-line-hi); }}
.ff-table td {{ padding:8px 10px; border-bottom:1px solid var(--c-line); color:var(--c-text-2); vertical-align:top; }}
.ff-table tr.near td {{ color:var(--c-text); background:rgba(255,179,107,.06); }}
.ff-kv {{ display:grid; grid-template-columns:150px 1fr; gap:8px 16px; font-size:.84rem; color:var(--c-text-2); }}
.ff-kv > span:nth-child(odd) {{ font-family:var(--f-mono); font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:var(--c-text-3); padding-top:3px; }}

/* Native widgets */
[data-testid="stExpander"] details {{ border:1px solid var(--c-line); border-radius:var(--r-md); background:var(--c-surface); }}
[data-testid="stDataFrame"] {{ border:1px solid var(--c-line); border-radius:var(--r-md); overflow:hidden; }}
[data-testid="stTextInput"] input, [data-baseweb="select"] > div {{ background:var(--c-surface) !important; border-color:var(--c-line) !important; }}

/* ---------- Hero ---------- */
.ff-hero {{ display:flex; flex-direction:column; align-items:center; text-align:center; gap:var(--s-3); margin:var(--s-6) 0 var(--s-6); }}
.ff-hero h1 {{ margin:var(--s-4) 0 0; }}

/* ---------- Counters ---------- */
@property --n {{ syntax:'<integer>'; initial-value:0; inherits:false; }}
.ff-count {{ font-family:var(--f-display); font-size:2rem; font-weight:600; color:var(--c-text);
  animation:count 1.4s var(--ease) both; counter-reset:n var(--n); }}
.ff-count::after {{ content:counter(n); }}
@keyframes count {{ from {{ --n:0 }} }}

/* ---------- Pipeline ---------- */
.ff-pipe {{ display:flex; align-items:stretch; flex-wrap:wrap; }}
.ff-node {{ flex:1 1 150px; min-width:140px; }}
.ff-link {{ flex:0 0 36px; position:relative; align-self:center; height:1px; background:var(--c-line-hi); }}
.ff-link::after {{ content:""; position:absolute; top:-2px; left:0; width:5px; height:5px; border-radius:50%;
  background:var(--c-flame); box-shadow:0 0 8px var(--c-flame); animation:travel 2.4s linear infinite; }}
@keyframes travel {{ from {{ left:0; opacity:0 }} 15% {{ opacity:1 }} 85% {{ opacity:1 }} to {{ left:calc(100% - 5px); opacity:0 }} }}

/* ---------- Gauge (conic ring) ---------- */
@property --p {{ syntax:'<number>'; initial-value:0; inherits:false; }}
.ff-gauge {{ width:132px; height:132px; flex:none; border-radius:50%; display:grid; place-items:center;
  background:conic-gradient(from 0deg, var(--g1) 0%, var(--g2) calc(var(--p) * 1%), rgba(255,255,255,.07) 0);
  animation:gauge 900ms var(--ease) both; box-shadow:0 0 32px -8px var(--g2); }}
.ff-gauge::before {{ content:""; grid-area:1/1; width:116px; height:116px; border-radius:50%; background:#090c14; }}
.ff-gauge > div {{ grid-area:1/1; text-align:center; position:relative; }}
@keyframes gauge {{ from {{ --p:0 }} }}

/* Nearest test card */
.st-key-nearest {{ background:var(--c-surface); border:1px solid var(--c-line); border-radius:var(--r-md);
  padding:var(--s-4) var(--s-5); transition:border-color var(--dur-1); }}
.st-key-nearest:hover {{ border-color:rgba(255,122,77,.4); }}
.st-key-nearest .stButton > button {{ justify-content:center; }}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation:none !important; transition:none !important; }}
  .ff-splash {{ display:none; }}
}}
</style>
""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Cached data access
# ------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_engine():
    import query_engine

    return query_engine.CombustionQueryEngine()


@st.cache_data(show_spinner=False)
def llm_status():
    provider, model, key = agent.resolve_provider_and_key()
    return (provider, model) if key else ("none", None)


@st.cache_data(show_spinner=False)
def psi_test_data():
    """Every PSI test row, plus the subset where both O2 and total pressure are known."""
    res = tools.query_psi_tests()
    known = [
        {"investigation": r["investigation"], "test": str(r["test"]), "row": r["row"], "run": r.get("flex_id") or "",
         "fuel": r["fuel"] or "unknown", "o2": round(r["o2_min"] * 100, 2), "p": round(r["pressure_psi"], 2),
         "burn_s": r.get("burn_time_s"), "end": r.get("test_end") or "", "source_id": r["source_id"], "psi_id": r["psi_id"]}
        for r in res["rows"] if r["o2_min"] is not None and r["o2_min"] == r["o2_max"] and r["pressure_psi"] is not None
    ]
    per_inv = {}
    for r in res["rows"]:
        per_inv[r["investigation"]] = per_inv.get(r["investigation"], 0) + 1
    return known, per_inv, res["n_scanned"]


@st.cache_data(show_spinner=False)
def lunar_screen():
    return tools.lunar_check()


@st.cache_data(show_spinner=False)
def dataset_counts():
    ev_path = BASE_DIR / "processed" / "golden_table_evidence.jsonl"
    q_path = BASE_DIR / "evaluation" / "questions.jsonl"
    count = lambda p: sum(1 for line in p.open(encoding="utf-8") if line.strip()) if p.exists() else 0
    manifest = tools.manifest_rows()
    chunks = sum(int(r["chunk_count"]) for r in manifest if str(r.get("chunk_count", "")).strip().isdigit())
    facts = tools.facts_data()
    return {
        "investigations": len(tools.golden_rows()),
        "fields": len(tools.golden_rows()[0]) if tools.golden_rows() else 0,
        "evidence": count(ev_path),
        "conflicts": len(tools.conflict_rows()),
        "sources": len(manifest),
        "sources_local": sum(r["status"] == "downloaded" for r in manifest),
        "chunks": chunks,
        "facts": len(facts.get("facts", [])),
        "rules": len(facts.get("rules", [])),
        "questions": count(q_path),
        "verified": sum(str(r.get("verified", "")).strip().lower() == "yes" for r in tools.golden_rows()),
    }


VERSIONS = evidence.versions()
PROVIDER, MODEL = llm_status()  # key from the environment / .env / host secrets, if any
SERVER_PROVIDER = PROVIDER

# ------------------------------------------------------------
# Optional API key typed by the visitor (hover panel under the team logo, top left)
# Kept only in this browser session's memory: never written to disk, chat history or the
# process environment, so one visitor's key is never used for another visitor's questions.
# ------------------------------------------------------------
LLM_CHOICES = {"Gemini": "gemini", "Groq": "groq", "Mistral": "mistral"}
LLM_KEY_LINKS = {
    "Gemini": "https://aistudio.google.com/apikey",
    "Groq": "https://console.groq.com/keys",
    "Mistral": "https://console.mistral.ai/api-keys",
}
st.session_state.setdefault("llm_provider", "Gemini")
st.session_state.setdefault("llm_key", "")
USER_KEY = st.session_state.llm_key.strip()
if USER_KEY:
    PROVIDER = LLM_CHOICES[st.session_state.llm_provider]
    MODEL = agent.DEFAULT_MODELS[PROVIDER]


def llm_kwargs():
    """Arguments for agent.answer_question: the visitor's own key if typed, else the server default."""
    if not USER_KEY:
        return {}
    prov, mod, key = PROVIDER, MODEL, USER_KEY
    return {"llm_fn": lambda msgs: agent.call_llm(msgs, provider=prov, model=mod, api_key=key)}


def _sync_llm_settings():
    st.session_state.llm_provider = st.session_state._llm_provider_input
    st.session_state.llm_key = (st.session_state._llm_key_input or "").strip()


def _clear_llm_key():
    st.session_state.llm_key = ""
    st.session_state._llm_key_input = ""


LOGO_CANDIDATES = ("logo.png", "logo.svg", "logo.jpg", "logo.jpeg", "logo.webp")


@st.cache_data(show_spinner=False)
def _logo_data_uri():
    """Team logo from assets/ as a data URI, or '' when no logo file is present."""
    import base64
    import mimetypes
    for name in LOGO_CANDIDATES:
        path = Path(__file__).resolve().parent / "assets" / name
        if path.exists():
            mime = mimetypes.guess_type(name)[0] or "image/png"
            return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return ""


def logo_html(size):
    uri = _logo_data_uri()
    if uri:
        return f'<img src="{uri}" alt="Team logo" style="height:{size}px;width:auto;display:block;border-radius:50%">'
    return flame_orb(size - 6, 0, 1)


# Hovering the logo (or typing in the panel) opens the API key panel under it.
st.markdown(
    """<style>
/* Streamlit's transparent top toolbar sits over the header row; let the mouse reach the logo */
[data-testid="stHeader"] { pointer-events:none; }
[data-testid="stHeader"] button, [data-testid="stHeader"] a { pointer-events:auto; }
.st-key-brand_logo { flex-wrap:nowrap; position:relative; z-index:1000001; }
.st-key-logo_key { position:relative; cursor:pointer; }
.ff-logo { display:flex; align-items:center; padding:4px; margin-top:8px; border-radius:10px;
  border:1px solid transparent; transition:border-color .15s ease, box-shadow .15s ease; }
.st-key-logo_key:hover .ff-logo, .st-key-logo_key:focus-within .ff-logo {
  border-color:rgba(255,122,77,.55); box-shadow:0 0 14px rgba(255,122,77,.35); }
.st-key-logo_key_panel { display:none; position:absolute; top:100%; left:0; z-index:1000002; width:300px;
  padding:14px; background:#0f1520; border:1px solid rgba(255,255,255,.12);
  border-radius:12px; box-shadow:0 18px 40px rgba(0,0,0,.55); }
.st-key-logo_key:hover .st-key-logo_key_panel,
.st-key-logo_key:focus-within .st-key-logo_key_panel { display:flex; flex-direction:column; }
.st-key-logo_key_panel { width:300px !important; min-width:300px !important; max-width:300px !important; }
.st-key-logo_key_panel > div { width:100% !important; }
</style>""",
    unsafe_allow_html=True,
)


def llm_settings_panel():
    """Provider picker + password field. Empty field -> warning and evidence-summary mode."""
    # Widget state is dropped when the visitor opens another page; re-seed it from the stored values.
    if "_llm_provider_input" not in st.session_state:
        st.session_state._llm_provider_input = st.session_state.llm_provider
    if "_llm_key_input" not in st.session_state:
        st.session_state._llm_key_input = st.session_state.llm_key
    st.html('<div class="ff-eyebrow" style="margin:4px 0 10px">LLM API key · optional</div>')
    st.selectbox("Provider", list(LLM_CHOICES), key="_llm_provider_input", on_change=_sync_llm_settings)
    st.text_input(
        "API key", type="password", key="_llm_key_input", on_change=_sync_llm_settings,
        placeholder="Paste your key and press Enter",
        help="Used only for this browser session to write answers. It is not saved anywhere.",
    )
    link = LLM_KEY_LINKS[st.session_state.llm_provider]
    if USER_KEY:
        st.success(f"Key set · answers are written by {PROVIDER}/{MODEL} and checked against the evidence.",
                   icon=":material/key:")
        st.button("Remove key", icon=":material/close:", use_container_width=True, key="clear_key",
                  on_click=_clear_llm_key)
    elif SERVER_PROVIDER != "none":
        st.info(f"No key entered · using this server's {SERVER_PROVIDER} key. "
                "Enter your own key to use your quota instead.", icon=":material/info:")
    else:
        st.warning(
            "No API key entered. Answers will show the validated evidence summary (sources and values) "
            f"instead of written prose. Free keys: [{st.session_state.llm_provider}]({link}).",
            icon=":material/warning:",
        )

# ------------------------------------------------------------
# Routing state (kept in the URL so a refresh returns to the same page and chat)
# ------------------------------------------------------------
PAGES = ["Ask the Expert", "Experiment Explorer", "Atmosphere Check", "Sources & About"]
SLUGS = {"ask": PAGES[0], "explorer": PAGES[1], "atmosphere": PAGES[2], "about": PAGES[3]}
SLUG_OF = {v: k for k, v in SLUGS.items()}
qp = st.query_params

if "nav" not in st.session_state:
    st.session_state.nav = SLUGS.get(qp.get("p", "ask"), PAGES[0])

# Opening screen: only on a fresh visit, not when the page is refreshed mid-work
if not st.session_state.get("intro_done"):
    if "c" not in qp and "p" not in qp:
        st.html(
            '<div class="ff-splash"><div class="inner">'
            f"{flame_orb(120, 22, 3)}"
            '<div class="title">Flame in <span class="ff-fire-text">Freefall</span></div>'
            '<div style="color:var(--c-text-2);max-width:420px">Without gravity a flame has no up. '
            "It burns as a quiet, blue-rimmed sphere.</div>"
            '<div class="ff-eyebrow" style="color:var(--c-text-3)">Space fire safety research workspace</div>'
            '<div class="bar"></div></div></div>'
        )
    st.session_state.intro_done = True

# ------------------------------------------------------------
# Header + navigation
# ------------------------------------------------------------
h_left, h_mid, h_right = st.columns([1.15, 2.75, 1.1], vertical_alignment="center")
with h_left:
    with st.container(key="brand_logo", horizontal=True, vertical_alignment="center", gap="small"):
        with st.container(key="logo_key", width="content"):
            st.html(f'<div class="ff-logo" title="LLM API key">{logo_html(34)}</div>')
            with st.container(key="logo_key_panel"):
                llm_settings_panel()
        st.html('<div class="ff-brand">FLAME IN FREEFALL</div>' + drifting_embers(16, 11))
with h_mid:
    choice = st.segmented_control("Workspace", PAGES, key="nav", label_visibility="collapsed")
with h_right:
    llm_chip = (
        f'<span class="ff-chip" title="Answers are written by {esc(PROVIDER)}/{esc(MODEL)} and validated against the evidence bundle">'
        f'<span class="ff-dot ff-live" style="background:{AURORA}"></span>{esc(PROVIDER.upper())}</span>'
        if PROVIDER != "none" else
        '<span class="ff-chip pending" title="No API key entered (hover over the logo, top left) and none configured on the server. '
        'Answers show the validated evidence summary instead of LLM prose.">EVIDENCE MODE</span>'
    )
    st.html(
        '<div style="display:flex;justify-content:flex-end;gap:6px;flex-wrap:wrap">'
        f'{llm_chip}<span class="ff-chip">DATA {esc(VERSIONS.get("data", ""))}</span></div>'
    )

page = choice or st.session_state.get("last_page", PAGES[0])
st.session_state.last_page = page
qp["p"] = SLUG_OF[page]


def eyebrow(text: str):
    st.html(f'<div class="ff-eyebrow" style="margin-top:var(--s-6)">{text}</div>')


def footer():
    st.html(
        '<div class="ff-mono" style="border-top:1px solid var(--c-line);margin-top:var(--s-7);padding-top:var(--s-4);'
        'color:var(--c-text-3);font-size:.66rem;letter-spacing:.12em;display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap">'
        "<span>FLAME IN FREEFALL · SPACE FIRE SAFETY</span><span>NASA SPACE APPS CHALLENGE 2026</span></div>"
    )


# ------------------------------------------------------------
# Chat history (one JSON file per conversation)
# ------------------------------------------------------------
ID_RE = re.compile(r"^[a-f0-9]{12}$")


def new_conversation():
    return {"id": uuid.uuid4().hex[:12], "title": "New chat", "created": datetime.now().isoformat(timespec="seconds"),
            "updated": None, "messages": []}


def load_conversation(conv_id):
    if not conv_id or not ID_RE.match(conv_id):
        return None
    path = HISTORY_DIR / f"{conv_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_conversation(conv):
    HISTORY_DIR.mkdir(exist_ok=True)
    conv["updated"] = datetime.now().isoformat(timespec="seconds")
    (HISTORY_DIR / f"{conv['id']}.json").write_text(json.dumps(conv, ensure_ascii=False, indent=1), encoding="utf-8")


def list_conversations():
    out = []
    if HISTORY_DIR.is_dir():
        for path in HISTORY_DIR.glob("*.json"):
            try:
                c = json.loads(path.read_text(encoding="utf-8"))
                out.append({"id": c["id"], "title": c.get("title") or "Untitled", "updated": c.get("updated") or ""})
            except (OSError, ValueError, KeyError):
                continue
    return sorted(out, key=lambda c: c["updated"], reverse=True)


def day_label(iso):
    try:
        d = datetime.fromisoformat(iso).date()
    except ValueError:
        return "Earlier"
    delta = (datetime.now().date() - d).days
    return "Today" if delta == 0 else "Yesterday" if delta == 1 else d.strftime("%d %b %Y")


# ------------------------------------------------------------
# Answering
# ------------------------------------------------------------
FOLLOW_UP_RE = re.compile(r"\b(it|its|they|them|their|that|those|this|these|there|same|one|ones)\b|^(and|but|so|what about|how about|why)\b", re.I)


def with_context(question, messages):
    """Follow-ups such as 'why does the pressure matter there?' name no investigation.
    The pipeline is stateless, so the previous question is attached to keep routing and retrieval on topic."""
    if investigations.detect_investigations(question) or not FOLLOW_UP_RE.search(question.strip()):
        return question, None
    prev_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
    prev_ans = next((m for m in reversed(messages) if m["role"] == "assistant"), None)
    if not prev_user:
        return question, None
    invs = (prev_ans or {}).get("investigations") or []
    hint = ", ".join(invs) if invs else prev_user.get("asked") or prev_user["content"]
    return f"{question} (follow-up about: {hint})", hint


def compact_answer(ans, context_hint):
    """Keep what the interface needs; the full evidence bundle is not written to the history file."""
    bundle = ans["bundle"]
    text = ans["text"]
    fallback = ans["validation"]["fallback_used"]
    if fallback:
        text = re.sub(r"^LLM answer not available - showing evidence summary\.\n?", "", text)
    cited = {re.split(r":", c)[0] for c in ans["citations"]}
    sources = [s for s in bundle.get("sources", []) if s.get("found")]
    sources.sort(key=lambda s: s["id"] not in cited)
    return {
        "role": "assistant", "content": text, "answer_type": ans["answer_type"], "model": ans["model"],
        "citations": ans["citations"], "fallback": fallback, "validated": ans["validation"]["passed"],
        "retried": ans["validation"]["retried"], "intent": bundle["intent"], "investigations": bundle["investigations"],
        "latency_ms": ans["latency_ms"], "context": context_hint,
        "n_chunks": len(bundle.get("chunks", [])), "n_tests": len(bundle.get("tests", [])),
        "n_conflicts": len(bundle.get("conflicts", [])),
        "sources": [{"id": s["id"], "title": s.get("title") or "", "url": s.get("url") or "", "kind": s.get("kind") or ""}
                    for s in sources[:10]],
        "n_sources": len(sources),
        "llm_error": short_llm_error(ans["validation"]["errors"]),
    }


def short_llm_error(errors):
    """First 'LLM API error' entry, reduced to the provider's own message (e.g. 'API key not valid')."""
    err = next((str(e) for e in errors if str(e).startswith("LLM API error")), "")
    if not err:
        return ""
    found = re.search(r'"message"\s*:\s*"([^"]+)"', err)
    code = re.search(r"HTTP (\d{3})", err)
    text = found.group(1) if found else err.replace("LLM API error: ", "")
    return (f"HTTP {code.group(1)} · " if code else "") + text[:160]


def llm_error_note(m):
    """Say plainly when the LLM call itself failed (wrong key, quota, network) rather than the validator."""
    if m.get("llm_error"):
        st.warning("The LLM call failed, so this reply is the evidence summary. Hover over the logo (top left) "
                   f"to check the API key and provider. Details: {m['llm_error']}", icon=":material/error:")


def stream_tokens(text, delay=0.012):
    for token in re.split(r"(\s+)", text):
        yield token
        if token.strip():
            time.sleep(delay)


def evidence_drawer(m):
    if m.get("error"):
        return
    rows = "".join(
        f'<div class="row"><span class="id">{esc(s["id"])}</span><span>'
        + (f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["title"])}</a>' if s["url"].startswith("http") else esc(s["title"]))
        + "</span></div>"
        for s in m.get("sources", [])
    ) or '<div class="row"><span>No citable source was needed for this reply.</span></div>'
    more = m.get("n_sources", 0) - len(m.get("sources", []))
    if more > 0:
        rows += f'<div class="row"><span class="ff-muted">+ {more} more in the evidence bundle</span></div>'
    check = ("LLM call failed · evidence summary" if m.get("llm_error")
             else "Evidence summary · no LLM" if m.get("fallback") and m.get("model", "").startswith("none")
             else "Validator fallback · evidence summary" if m.get("fallback")
             else "Validated · retried once" if m.get("retried") else "Validated against evidence")
    meta = [f'intent · {esc(m.get("intent", ""))}', esc(m.get("model", "")), check,
            f'{m.get("n_chunks", 0)} passages', f'{m.get("n_tests", 0)} test rows']
    if m.get("n_conflicts"):
        meta.append(f'{m["n_conflicts"]} source conflicts')
    if m.get("context"):
        meta.append(f'follow-up context · {esc(m["context"][:60])}')
    chips = "".join(f'<span class="ff-chip">{x}</span>' for x in meta if x)
    n = len(m.get("citations", []))
    st.html(
        '<div class="ff-evi" tabindex="0">'
        '<div class="ff-evi-tab"><span class="ff-dot" style="background:var(--c-flame)"></span>'
        f'EVIDENCE USED · {n} citation{"" if n == 1 else "s"} <span class="chev">▾</span></div>'
        f'<div class="ff-evi-body"><div><div class="src" style="font-family:var(--f-body)">{rows}</div>'
        f'<div class="meta">{chips}</div></div></div></div>'
    )


def answer_badge(m):
    kind = m.get("answer_type")
    if kind == "no_data":
        st.html('<span class="ff-chip pending">Data not available in the repository</span>')
    elif kind == "out_of_scope":
        st.html('<span class="ff-chip missing">Outside the scope of this workspace</span>')


ASSISTANT_AVATAR = ":material/local_fire_department:"

# ============================================================
# ASK THE EXPERT · chat
# ============================================================
if page == "Ask the Expert":
    if "conv" not in st.session_state:
        st.session_state.conv = load_conversation(qp.get("c")) or new_conversation()
        st.session_state.pending = None
    conv = st.session_state.conv

    def open_conversation(conv_id):
        st.session_state.conv = load_conversation(conv_id) or new_conversation()
        st.session_state.pending = None

    def start_new():
        st.session_state.conv = new_conversation()
        st.session_state.pending = None

    def delete_current():
        (HISTORY_DIR / f"{st.session_state.conv['id']}.json").unlink(missing_ok=True)
        start_new()

    # ---- History rail ----
    with st.sidebar:
        st.html('<div class="ff-eyebrow" style="margin:4px 0 10px">Conversations</div>')
        st.button("New chat", icon=":material/add:", use_container_width=True, key="new_chat", on_click=start_new)
        saved = list_conversations()
        if not saved:
            st.html('<p class="ff-muted" style="font-size:.8rem;margin-top:var(--s-4)">Your conversations are saved here '
                    "and stay available after a refresh or restart.</p>")
        last_day = None
        for c in saved:
            label = day_label(c["updated"])
            if label != last_day:
                st.html(f'<div class="ff-mono ff-muted" style="font-size:.64rem;letter-spacing:.12em;margin:14px 0 2px">{label.upper()}</div>')
                last_day = label
            st.button(c["title"], key=f"conv_{c['id']}", use_container_width=True,
                      type="primary" if c["id"] == conv["id"] else "secondary",
                      on_click=open_conversation, args=(c["id"],))
        if conv["messages"]:
            st.html('<div style="height:var(--s-4)"></div>')
            st.button("Delete this chat", icon=":material/delete:", use_container_width=True,
                      key="delete_chat", on_click=delete_current)

    conv = st.session_state.conv
    if conv["messages"]:
        qp["c"] = conv["id"]
    elif "c" in qp:
        del qp["c"]

    def ask(question):
        asked, hint = with_context(question, conv["messages"])
        if not conv["messages"]:
            conv["title"] = question.strip()[:60]
        conv["messages"].append({"role": "user", "content": question, "asked": asked})
        save_conversation(conv)
        st.session_state.pending = {"asked": asked, "hint": hint}

    # A refresh in the middle of an answer: answer the last unanswered question again
    if not st.session_state.pending and conv["messages"] and conv["messages"][-1]["role"] == "user":
        last = conv["messages"][-1]
        st.session_state.pending = {"asked": last.get("asked") or last["content"], "hint": None}

    chat = st.container(key="chat")
    with chat:
        if not conv["messages"]:
            st.html(
                '<div class="ff-hero">'
                f"{flame_orb(96, 16, 5)}"
                '<div class="ff-eyebrow" style="margin-top:var(--s-5)">Research assistant</div>'
                '<h1>Ask the Expert</h1>'
                '<p style="margin:0;max-width:540px">How does fire behave without gravity? Ask about microgravity '
                "combustion experiments, test conditions and oxygen limits. Every answer is built from NASA PSI data "
                "and cites its sources; when the repository has no data, it says so.</p></div>"
            )
        else:
            st.html(f'<div class="ff-eyebrow" style="margin:var(--s-5) 0 var(--s-2)">Ask the Expert · {esc(conv["title"])}</div>')

        for m in conv["messages"]:
            with st.chat_message(m["role"], avatar=ASSISTANT_AVATAR if m["role"] == "assistant" else None):
                if m["role"] == "assistant":
                    answer_badge(m)
                st.markdown(m["content"])
                if m["role"] == "assistant":
                    evidence_drawer(m)
                    llm_error_note(m)

        if st.session_state.pending:
            job = st.session_state.pending
            with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                thinking = st.empty()
                thinking.html(
                    f'<div class="ff-think">{flame_orb(16, 0, 2)}<span>Retrieving evidence, running tools and checking citations</span>'
                    '<span class="dots"><i></i><i></i><i></i></span></div>'
                )
                try:
                    result = agent.answer_question(job["asked"], get_engine(), **llm_kwargs())
                    msg = compact_answer(result, job["hint"])
                except Exception as exc:  # index missing, network error, ...
                    msg = {"role": "assistant", "error": True, "answer_type": "error",
                           "content": f"The answer pipeline could not run: `{type(exc).__name__}: {exc}`"}
                thinking.empty()
                answer_badge(msg)
                st.write_stream(stream_tokens(msg["content"]))
                evidence_drawer(msg)
                llm_error_note(msg)
            conv["messages"].append(msg)
            save_conversation(conv)
            st.session_state.pending = None

        if PROVIDER == "none":
            st.warning(
                "Evidence mode · no API key entered, so replies show the validated evidence summary instead of "
                "LLM-written prose. To get written answers, hover over the logo next to FLAME IN FREEFALL (top left) "
                "and enter a Gemini, Groq or Mistral API key.",
                icon=":material/key_off:",
            )

    question = st.chat_input("Ask a follow-up…" if conv["messages"] else "Ask about an experiment, condition or comparison…")
    if question and question.strip():
        ask(question.strip())
        st.rerun()

# ============================================================
# EXPERIMENT EXPLORER
# ============================================================
elif page == "Experiment Explorer":
    counts = dataset_counts()
    _, per_inv, n_rows = psi_test_data()
    golden = tools.golden_rows()

    eyebrow("Structured dataset")
    st.title("Experiment Explorer")
    st.markdown("The golden table: one row per core investigation, every value tied to a source.")

    stats = [(counts["investigations"], "Investigations"), (n_rows, "PSI test rows"),
             (counts["evidence"], "Evidence records"), (counts["conflicts"], "Source conflicts")]
    st.html(
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s-3);margin:var(--s-4) 0 var(--s-6)">'
        + "".join(
            f'<div class="ff-card ff-enter" style="animation-delay:{i*70}ms">'
            f'<div class="ff-count" style="--n:{n}"></div>'
            f'<div class="ff-muted" style="font-size:.78rem">{label}</div></div>'
            for i, (n, label) in enumerate(stats)
        )
        + "</div>"
    )

    def rng(lo, hi, unit="", scale=1.0, digits=2):
        a, b = tools.to_float(lo), tools.to_float(hi)
        if a is None or b is None:
            return None
        a, b = a * scale, b * scale
        text = f"{a:.{digits}f}".rstrip("0").rstrip(".") if a == b else \
            f"{a:.{digits}f}".rstrip("0").rstrip(".") + "–" + f"{b:.{digits}f}".rstrip("0").rstrip(".")
        return text + unit

    def review_status(row):
        if str(row.get("verified", "")).strip().lower() == "yes":
            return "Expert verified", "ok"
        if str(row.get("evidence_level", "")).strip().lower() == "missing":
            return "No source found", "missing"
        return "Pending expert review", "pending"

    def hardware_short(text):
        text = str(text or "unknown")
        head = text.split(":")[0].strip()
        if head.lower().startswith("other") and ":" in text:
            head = text.split(":", 1)[1].split("(")[0].strip()
        return head[:38] or "unknown"

    def cats(row):
        return [c.strip() for c in str(row["category"]).split("|") if c.strip()]

    table = pd.DataFrame([{
        "Investigation": r["id"], "Category": " / ".join(c.title() for c in cats(r)),
        "Fuel": r.get("material_class") or "unknown", "Hardware": hardware_short(r.get("hardware")),
        "O₂ (%)": rng(r["o2_min"], r["o2_max"], scale=100, digits=1) or "unknown",
        "Pressure (psi)": rng(r["pressure_psi_min"], r["pressure_psi_max"]) or "unknown",
        "Flow (cm/s)": rng(r["flow_cm_s_min"], r["flow_cm_s_max"], digits=1) or "unknown",
        "Lunar match": r.get("lunar_joint_flag") or "unknown",
        "PSI test rows": per_inv.get(r["id"], 0),
        "Review status": review_status(r)[0],
    } for r in golden])

    f1, f2, f3 = st.columns([1.3, 1.6, .7], vertical_alignment="bottom")
    with f1:
        search = st.text_input("Search", placeholder="e.g. FLEX, Saffire, plastic…", label_visibility="collapsed")
    with f2:
        category = st.pills("Category", ["All", "Prevention", "Detection", "Suppression"],
                            default="All", label_visibility="collapsed")
    with f3:
        view = st.segmented_control("View", [":material/grid_view:", ":material/table_rows:"],
                                    default=":material/grid_view:", label_visibility="collapsed", key="view")

    keep = []
    for r in golden:
        hay = " ".join(str(r.get(k, "")) for k in ("id", "name", "category", "material_class", "fuel_material", "hardware")).lower()
        if search and search.lower() not in hay:
            continue
        if category and category != "All" and category.lower() not in cats(r):
            continue
        keep.append(r)
    ids = [r["id"] for r in keep]

    def cell(v):
        return f'<span class="ff-muted">unknown</span>' if v in (None, "", "unknown") else esc(v)

    if not keep:
        st.html('<div class="ff-card ff-muted" style="text-align:center;padding:var(--s-7)">'
                "No investigations match. Try another name or category.</div>")
    elif view == ":material/table_rows:":
        st.dataframe(table[table["Investigation"].isin(ids)], use_container_width=True, hide_index=True)
    else:
        cards = []
        for i, r in enumerate(keep):
            chips = "".join(
                f'<span class="ff-chip"><span class="ff-dot" style="background:{CATEGORY_COLOR.get(c, TEXT_3)}"></span>{esc(c.title())}</span>'
                for c in cats(r))
            label, tone = review_status(r)
            dot = f'<span class="ff-dot{" ff-live" if tone == "pending" else ""}" style="background:currentColor"></span>'
            n_tests = per_inv.get(r["id"], 0)
            cards.append(
                f'<div class="ff-card hover ff-enter" style="animation-delay:{i*40}ms">'
                '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">'
                f'<span style="font-family:var(--f-display);font-size:1.12rem;font-weight:600;color:var(--c-text)">{esc(r["id"])}</span>'
                f'<span style="display:flex;gap:4px">{chips}</span></div>'
                '<div class="ff-mono" style="display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin-top:var(--s-4);font-size:.76rem;color:var(--c-text-2)">'
                f'<span class="ff-muted">FUEL</span><span>{cell(r.get("material_class"))}</span>'
                f'<span class="ff-muted">HARDWARE</span><span>{cell(hardware_short(r.get("hardware")))}</span>'
                f'<span class="ff-muted">O₂</span><span>{cell(rng(r["o2_min"], r["o2_max"], " %", 100, 1))}</span>'
                f'<span class="ff-muted">PRESSURE</span><span>{cell(rng(r["pressure_psi_min"], r["pressure_psi_max"], " psi"))}</span>'
                f'<span class="ff-muted">TEST ROWS</span><span>{n_tests if n_tests else '<span class="ff-muted">no PSI table</span>'}</span></div>'
                f'<div style="margin-top:var(--s-4)"><span class="ff-chip {tone}">{dot}{label}</span></div>'
                "</div>"
            )
        st.html('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:var(--s-3)">'
                + "".join(cards) + "</div>")

    # ---- Detail ----
    st.html('<div style="height:var(--s-5)"></div>')
    picked = st.selectbox("Inspect an investigation", ids, index=None, placeholder="Open an investigation for findings, conflicts and sources…",
                          label_visibility="collapsed")
    if picked:
        r = tools.golden_row(picked)
        label, tone = review_status(r)
        kv = [
            ("Main finding", r.get("main_finding")), ("Fuel", r.get("fuel_material")), ("Sample", r.get("fuel_shape_size")),
            ("O₂", r.get("o2_raw")), ("Pressure", r.get("pressure_raw")), ("Flow", r.get("flow_raw")),
            ("Hardware", r.get("hardware")), ("Gravity regime", r.get("gravity_regime")),
            ("Tests", r.get("test_count")), ("Operated", r.get("operation_period")),
            ("Lunar check", r.get("lunar_note")),
        ]
        kv_html = "".join(f"<span>{esc(k)}</span><span>{cell(v)}</span>" for k, v in kv)
        st.html(
            '<div class="ff-card ff-enter">'
            '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:var(--s-4)">'
            f'<div style="font-family:var(--f-display);font-size:1.2rem;font-weight:600;color:var(--c-text)">{esc(r["name"])}</div>'
            f'<span class="ff-chip {tone}">{label}</span></div>'
            f'<div class="ff-kv">{kv_html}</div></div>'
        )
        conflicts = [c for c in tools.conflict_rows() if c["investigation_id"] == picked]
        if conflicts:
            with st.expander(f"Source conflicts · {len(conflicts)}", icon=":material/compare_arrows:"):
                body = "".join(
                    f"<tr><td>{esc(c['field'])}</td><td>{esc(c['value_1'])}<br><span class='ff-muted'>{esc(c['source_1'])}</span></td>"
                    f"<td>{esc(c['value_2'])}<br><span class='ff-muted'>{esc(c['source_2'])}</span></td>"
                    f"<td>{esc(c['chosen'])}</td></tr>" for c in conflicts)
                st.html('<table class="ff-table"><tr><th>Field</th><th>Value 1</th><th>Value 2</th><th>Used in table</th></tr>'
                        f"{body}</table>")
        src_ids = [s.strip() for s in str(r.get("source_ids", "")).split("|") if re.match(r"^S-\d{3}$", s.strip())]
        if src_ids:
            with st.expander(f"Sources · {len(src_ids)}", icon=":material/description:"):
                body = ""
                for s in tools.get_sources(src_ids):
                    title = esc(s.get("title") or "")
                    if str(s.get("url") or "").startswith("http"):
                        title = f'<a href="{esc(s["url"])}" target="_blank" rel="noopener" style="color:{NEBULA};text-decoration:none">{title}</a>'
                    body += (f"<tr><td style='color:{EMBER}'>{esc(s['id'])}</td><td style='font-family:var(--f-body)'>{title}</td>"
                             f"<td>{esc(s.get('role') or '')}</td><td>{esc(s.get('year') or '')}</td></tr>")
                st.html(f'<table class="ff-table"><tr><th>ID</th><th>Title</th><th>Role</th><th>Year</th></tr>{body}</table>')

    st.html(
        f'<p class="ff-muted" style="font-size:.78rem;margin-top:var(--s-5)">{counts["verified"]} of {counts["investigations"]} rows '
        "have been verified by a domain expert. Unknown values stay unknown; they are never filled with 0 or an estimate.</p>"
    )
    footer()

# ============================================================
# ATMOSPHERE CHECK
# ============================================================
elif page == "Atmosphere Check":
    tests, per_inv, n_rows = psi_test_data()
    screen = lunar_screen()
    st.session_state.setdefault("o2", 30.0)
    st.session_state.setdefault("p_total", 10.2)

    def load_point(o2, p):
        st.session_state.o2 = float(min(max(o2, 10.0), 100.0))
        st.session_state.p_total = float(min(max(p, 3.0), 45.0))

    eyebrow("Condition calculator")
    st.title("Atmosphere Check")
    st.markdown(
        f"Set a cabin atmosphere and compare it with the lunar reference envelope and with the "
        f"{len(tests)} PSI tests whose oxygen fraction and pressure were both recorded."
    )

    left, right = st.columns([1, 1.35], gap="large")
    with left:
        oxygen = st.slider("Oxygen fraction (%)", 10.0, 100.0, key="o2", step=0.5, format="%.1f")
        pressure = st.slider("Total pressure (psi)", 3.0, 45.0, key="p_total", step=0.01, format="%.2f")

        po2 = tools.calculate("po2", o2_fraction=oxygen / 100, pressure=pressure)["result"]
        ratio = tools.calculate("po2_ratio_vs_earth", o2_fraction=oxygen / 100, pressure_psi=pressure)["result"]
        inside = oxygen >= LUNAR_O2_MIN and pressure <= LUNAR_P_MAX

        pct = min(ratio / 3, 1) * 100  # ring spans 0–3× Earth sea-level pO2
        g1, g2 = ("#ffd08a", FLAME) if inside else ("#5b7bd6", NEBULA)
        status_txt = "Inside lunar envelope" if inside else "Outside lunar envelope"
        st.html(
            '<div class="ff-card" style="display:flex;gap:var(--s-5);align-items:center;margin-top:var(--s-4)">'
            f'<div class="ff-gauge" style="--p:{pct:.1f};--g1:{g1};--g2:{g2}"><div>'
            f'<div style="font-family:var(--f-display);font-size:1.6rem;font-weight:600;color:var(--c-text)">{po2:.2f}</div>'
            '<div class="ff-mono ff-muted" style="font-size:.66rem">psi p(O₂)</div></div></div>'
            f'<div><div class="ff-eyebrow" style="color:{g2}">{status_txt}</div>'
            '<div class="ff-mono" style="margin-top:var(--s-3);font-size:.8rem;line-height:1.9;color:var(--c-text-2)">'
            f'×{ratio:.2f} Earth sea level<br><span class="ff-muted">reference {EARTH_PO2} psi</span></div></div></div>'
        )
        st.html(
            '<div class="ff-card" style="margin-top:var(--s-3)">'
            '<div class="ff-eyebrow" style="color:var(--c-text-3)">Lunar reference envelope · F-005</div>'
            f'<div style="font-family:var(--f-display);font-size:1.05rem;color:var(--c-text);margin-top:6px">'
            f"O₂ ≥ {LUNAR_O2_MIN:.0f}% · P ≤ {LUNAR_P_MAX} psi</div>"
            '<div class="ff-mono ff-muted" style="font-size:.72rem;margin-top:6px">p(O₂) = x(O₂) × P</div></div>'
        )
        b1, b2, b3 = st.columns(3)
        b1.button("Lunar", use_container_width=True, on_click=load_point, args=(LUNAR_O2_MIN, LUNAR_P_MAX),
                  help=f"Envelope corner: {LUNAR_O2_MIN:.0f}% O₂ at {LUNAR_P_MAX} psi")
        b2.button("Earth", use_container_width=True, on_click=load_point, args=(EARTH_O2, EARTH_P),
                  help=f"Sea level: {EARTH_O2}% O₂ at {EARTH_P} psi")
        b3.button("EVA suit", use_container_width=True, on_click=load_point, args=(SUIT_O2, SUIT_P),
                  help=f"Spacesuit: {SUIT_O2:.0f}% O₂ at {SUIT_P} psi")

    # ---- Nearest documented tests (normalised distance over the spread of the test data) ----
    o2_span = (max(t["o2"] for t in tests) - min(t["o2"] for t in tests)) or 1.0
    p_span = (max(t["p"] for t in tests) - min(t["p"] for t in tests)) or 1.0

    def distance(t):
        return (((t["o2"] - oxygen) / o2_span) ** 2 + ((t["p"] - pressure) / p_span) ** 2) ** 0.5

    ranked = sorted(tests, key=lambda t: (distance(t), int(t["test"]) if t["test"].isdigit() else 0))
    nearest = ranked[0]
    at_test = abs(nearest["o2"] - oxygen) < 0.05 and abs(nearest["p"] - pressure) < 0.006

    with right:
        fig = go.Figure()
        fig.add_shape(type="rect", x0=0, x1=LUNAR_P_MAX, y0=LUNAR_O2_MIN, y1=100,
                      fillcolor="rgba(255,122,77,.08)", line=dict(color="rgba(255,122,77,.45)", width=1, dash="dot"))
        fig.add_annotation(x=0.4, y=97, text="LUNAR ENVELOPE", showarrow=False, xanchor="left",
                           font=dict(family="JetBrains Mono, monospace", size=10, color=FLAME))
        xs = [x / 10 for x in range(31, 461)]
        fig.add_trace(go.Scatter(x=xs, y=[EARTH_PO2 / x * 100 for x in xs], mode="lines",
                                 line=dict(color=NEBULA, width=1, dash="dash"),
                                 name=f"p(O₂) = {EARTH_PO2} psi", hoverinfo="skip"))
        # documented tests, grouped by identical condition; marker area grows with the number of tests
        for fuel, symbol in zip(sorted({t["fuel"] for t in tests}), ["circle", "diamond", "square", "triangle-up"]):
            groups = {}
            for t in tests:
                if t["fuel"] == fuel:
                    groups.setdefault((t["p"], t["o2"]), []).append(t["test"])
            pts = sorted(groups.items())
            fig.add_trace(go.Scatter(
                x=[k[0] for k, _ in pts], y=[k[1] for k, _ in pts], mode="markers", name=f"{fuel} tests",
                marker=dict(symbol=symbol, size=[6 + 2.2 * len(v) ** 0.5 for _, v in pts],
                            color="rgba(233,238,246,.16)", line=dict(color="rgba(233,238,246,.75)", width=1)),
                customdata=[[len(v), ", ".join("#" + x for x in v[:6]) + (" …" if len(v) > 6 else "")] for _, v in pts],
                hovertemplate=f"{fuel} · %{{customdata[0]}} test(s)<br>%{{y:.1f}}% O₂ · %{{x:.2f}} psi<br>%{{customdata[1]}}<extra></extra>"))
        refs = [("Earth", EARTH_P, EARTH_O2, "top center"), ("EVA suit", SUIT_P, SUIT_O2, "middle right")]
        fig.add_trace(go.Scatter(x=[r[1] for r in refs], y=[r[2] for r in refs], mode="markers+text", name="Reference atmospheres",
                                 marker=dict(size=9, color=NEBULA), text=[r[0] for r in refs],
                                 textposition=[r[3] for r in refs], textfont=dict(color=TEXT_2, size=11),
                                 hovertemplate="%{text}<br>%{y}% O₂ · %{x} psi<extra></extra>"))
        if not at_test:
            fig.add_trace(go.Scatter(x=[pressure, nearest["p"]], y=[oxygen, nearest["o2"]], mode="lines",
                                     line=dict(color="rgba(255,179,107,.7)", width=1, dash="dot"),
                                     hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=[nearest["p"]], y=[nearest["o2"]], mode="markers", name="Nearest test",
                                 marker=dict(size=15, color="rgba(0,0,0,0)", line=dict(color=EMBER, width=2)),
                                 hovertemplate=f"Nearest: {nearest['investigation']} #{nearest['test']}<br>%{{y:.1f}}% O₂ · %{{x:.2f}} psi<extra></extra>"))
        fig.add_trace(go.Scatter(x=[pressure], y=[oxygen], mode="markers", hoverinfo="skip", showlegend=False,
                                 marker=dict(size=32, color="rgba(255,122,77,.18)")))
        fig.add_trace(go.Scatter(x=[pressure], y=[oxygen], mode="markers", name="Your setting",
                                 marker=dict(size=12, color=FLAME, line=dict(color="#ffe2c4", width=1.5)),
                                 hovertemplate="Your setting<br>%{y:.1f}% O₂ · %{x:.2f} psi<extra></extra>"))
        axis = dict(gridcolor="rgba(255,255,255,.05)", zeroline=False, linecolor="rgba(255,255,255,.12)",
                    tickfont=dict(family="JetBrains Mono, monospace", size=10, color=TEXT_3),
                    title_font=dict(size=12, color=TEXT_2))
        fig.update_layout(
            height=470, margin=dict(l=8, r=8, t=8, b=8),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Sans, system-ui, sans-serif", color=TEXT_2),
            xaxis=dict(title="Total pressure (psi)", range=[0, 46.5], **axis),
            yaxis=dict(title="Oxygen fraction (%)", range=[0, 104], **axis),
            legend=dict(orientation="h", y=-0.16, font=dict(size=11, color=TEXT_2)),
            hoverlabel=dict(bgcolor="#111823", bordercolor="rgba(255,255,255,.15)", font=dict(color=TEXT)),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---- Lunar screen of every PSI test row ----
    joint = len(screen["joint_matches"])
    best = (screen["closest_o2_ok"] or [None])[0]
    cells = [
        (joint, f"of {screen['n_known']} tests meet both limits in the same test"),
        (screen["n_o2_ok"], f"meet O₂ ≥ {LUNAR_O2_MIN:.0f}%"),
        (screen["n_pressure_ok"], f"meet P ≤ {LUNAR_P_MAX} psi"),
        (screen["n_unknown_o2_or_pressure"], "rows not screened: O₂ or pressure unknown"),
    ]
    st.html(
        '<div class="ff-eyebrow" style="color:var(--c-text-3);margin:var(--s-5) 0 var(--s-3)">Lunar screen · all PSI test rows</div>'
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s-3)">'
        + "".join(
            f'<div class="ff-card"><div style="font-family:var(--f-display);font-size:1.6rem;font-weight:600;'
            f'color:{FLAME if i == 0 else TEXT}">{n}</div><div class="ff-muted" style="font-size:.76rem">{esc(label)}</div></div>'
            for i, (n, label) in enumerate(cells))
        + "</div>"
    )

    # ---- Nearest tests table ----
    with st.container(key="nearest"):
        c1, c2, c3 = st.columns([2.6, 1.2, 1.5], vertical_alignment="center")
        with c1:
            st.html(
                '<div class="ff-eyebrow" style="color:var(--c-text-3)">Nearest documented tests to your setting</div>'
                + ('<div class="ff-mono" style="font-size:.76rem;color:var(--c-ember);margin-top:6px">The calculator is set to a documented test.</div>'
                   if at_test else "")
            )
        with c2:
            st.button("Snap to nearest", icon=":material/my_location:", use_container_width=True,
                      on_click=load_point, args=(nearest["o2"], nearest["p"]), disabled=at_test)
        with c3:
            if best:
                st.button("Closest to lunar envelope", icon=":material/dark_mode:", use_container_width=True,
                          on_click=load_point, args=(best["o2_min"] * 100, round(best["pressure_psi"], 2)),
                          help=f"{best['investigation']} #{best['test']}: the O₂ ≥ {LUNAR_O2_MIN:.0f}% test with the lowest pressure, "
                               f"{best['pressure_excess_psi']:.2f} psi above the limit")
        body = ""
        for i, t in enumerate(ranked[:5]):
            ok = t["o2"] >= LUNAR_O2_MIN and t["p"] <= LUNAR_P_MAX
            over = t["p"] - LUNAR_P_MAX
            env = "inside" if ok else (f"{over:+.2f} psi" if t["o2"] >= LUNAR_O2_MIN else f"O₂ {t['o2'] - LUNAR_O2_MIN:+.0f} pts")
            burn = f"{t['burn_s']:g} s" if isinstance(t["burn_s"], (int, float)) else "unknown"
            body += (
                f'<tr class="{"near" if i == 0 else ""}"><td>{esc(t["investigation"])} #{esc(t["test"])}</td><td>{esc(t["run"])}</td>'
                f'<td>{esc(t["fuel"])}</td><td>{t["o2"]:.1f}%</td><td>{t["p"]:.2f}</td>'
                f'<td>{t["o2"] - oxygen:+.1f} pts</td><td>{t["p"] - pressure:+.2f} psi</td><td>{env}</td>'
                f'<td>{burn}</td><td>{esc(t["psi_id"])} · row {t["row"]}</td></tr>'
            )
        st.html(
            '<table class="ff-table" style="margin-top:var(--s-3)"><tr><th>Test</th><th>Run ID</th><th>Fuel</th><th>O₂</th><th>P (psi)</th>'
            '<th>Δ O₂</th><th>Δ P</th><th>vs envelope</th><th>Burn time</th><th>Source</th></tr>' + body + "</table>"
        )

    with st.expander("How this page works", icon=":material/help:"):
        inv_txt = ", ".join(f"{k} {v}" for k, v in per_inv.items())
        st.markdown(
            f"""
**What it calculates.** Oxygen partial pressure, p(O₂) = oxygen fraction × total pressure. The ring shows that value and how it compares
with Earth sea-level air ({EARTH_O2}% O₂ at {EARTH_P} psi = {EARTH_PO2} psi). Both numbers come from the same `tools.calculate()` function the chat agent uses.

**Lunar envelope.** The challenge text expects lunar habitats to run at O₂ ≥ {LUNAR_O2_MIN:.0f}% and total pressure ≤ {LUNAR_P_MAX} psi (fact F-005).
The status turns orange only when your setting meets both limits. The shaded region on the chart is that envelope.

**Chart.** Each marker is a tested condition from the PSI experiment tables; a larger marker means more tests at that exact condition, and the shape shows the fuel.
The dashed curve joins all atmospheres with the same p(O₂) as Earth sea level: points above it are more oxygen-rich than normal air, points below less.

**Nearest tests.** The table ranks tests by distance to your setting. Oxygen and pressure differences are each divided by the spread of the test data
({o2_span:.0f} points of O₂, {p_span:.1f} psi) so neither axis dominates. "Snap to nearest" moves the sliders onto the closest test.

**Why only FLEX appears.** The repository holds {n_rows} PSI test rows ({inv_txt}). Only FLEX recorded both oxygen fraction and chamber pressure per test
({len(tests)} rows). The BASS, BASS-II and Saffire tables give no per-test pressure, so those rows cannot be placed on the chart or screened; they are counted as "not screened" rather than guessed.

**Lunar screen.** `tools.lunar_check()` scans every test row. No test meets both limits at once. FLEX #37 (34% O₂ at 10.33 psi) is the closest from the oxygen side;
the only test under {LUNAR_P_MAX} psi ran at 18% O₂.
"""
        )
    st.caption("Test conditions are read from the PSI experiment tables in raw/psi. Verify against the primary sources before scientific use.")
    footer()

# ============================================================
# SOURCES & ABOUT
# ============================================================
else:
    counts = dataset_counts()
    _, _, n_rows = psi_test_data()

    eyebrow("Project information")
    st.title("Sources & About")
    st.markdown("A transparent research interface for microgravity combustion experiments and space fire safety.")

    steps = [("01", "Router", "Intent · scope · data gaps"),
             ("02", "Hybrid retrieval", "BM25 + dense embeddings"),
             ("03", "Structured tools", "PSI tests · lunar check · calculator"),
             ("04", "Evidence bundle", "Facts, rows, passages, conflicts"),
             ("05", "LLM writer", f"{PROVIDER}/{MODEL}" if PROVIDER != "none" else "Not configured"),
             ("06", "Validator", "Citations · conflicts · refusals")]
    parts = []
    for i, (n, title, sub) in enumerate(steps):
        if i:
            parts.append('<div class="ff-link" style="flex-basis:20px"></div>')
        parts.append(
            f'<div class="ff-node ff-card hover ff-enter" style="animation-delay:{i*80}ms;padding:var(--s-4);min-width:120px">'
            f'<div class="ff-mono" style="font-size:.68rem;color:var(--c-flame)">{n}</div>'
            f'<div style="font-family:var(--f-display);color:var(--c-text);font-weight:600;margin-top:4px">{esc(title)}</div>'
            f'<div class="ff-muted" style="font-size:.74rem;margin-top:2px">{esc(sub)}</div></div>'
        )
    st.html('<div class="ff-eyebrow" style="color:var(--c-text-3);margin:var(--s-5) 0 var(--s-3)">How an answer is produced</div>'
            f'<div class="ff-pipe">{"".join(parts)}</div>')

    layers = [
        ("K1", "PSI metadata and experiment tables", f"{n_rows} test rows"),
        ("K2", "Published reports and papers", f"{counts['sources_local']} of {counts['sources']} sources in corpus · {counts['chunks']} passages"),
        ("K3", "Facts and rules", f"{counts['facts']} facts · {counts['rules']} rules"),
        ("K4", "Golden table", f"{counts['investigations']} investigations · {counts['evidence']} evidence records"),
        ("K5", "Evaluation questions", f"{counts['questions']} questions"),
    ]
    layer_html = "".join(
        '<div style="display:flex;gap:14px;padding:10px 0;border-bottom:1px solid var(--c-line);align-items:baseline">'
        f'<span class="ff-mono" style="color:var(--c-nebula);font-size:.78rem;width:24px">{k}</span>'
        f'<span style="color:var(--c-text-2);font-size:.9rem;flex:1">{esc(v)}</span>'
        f'<span class="ff-mono ff-muted" style="font-size:.7rem;text-align:right">{esc(n)}</span></div>'
        for k, v, n in layers
    )
    review = (f'{counts["verified"]} of {counts["investigations"]} rows expert verified')
    st.html(
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:var(--s-3);margin-top:var(--s-6)">'
        f'<div class="ff-card"><div class="ff-eyebrow" style="color:var(--c-text-3)">Data layers</div>{layer_html}</div>'
        '<div style="display:flex;flex-direction:column;gap:var(--s-3)">'
        '<div class="ff-card"><div class="ff-eyebrow" style="color:var(--c-text-3)">Data integrity</div>'
        f'<div style="margin:10px 0;display:flex;gap:6px;flex-wrap:wrap"><span class="ff-chip pending">GOLDEN TABLE · {esc(review.upper())}</span>'
        f'<span class="ff-chip">DATA {esc(VERSIONS.get("data", ""))}</span><span class="ff-chip">INDEX {esc(VERSIONS.get("index", ""))}</span></div>'
        '<p style="font-size:.9rem;margin:0">Unknown values stay unknown. Conflicting source values are kept with their sources '
        f'({counts["conflicts"]} recorded). Every answer is checked against its evidence bundle before it is shown.</p></div>'
        '<div class="ff-card"><div class="ff-eyebrow" style="color:var(--c-text-3)">Scope &amp; limits</div>'
        '<ul style="font-size:.9rem;margin:10px 0 0;padding-left:18px">'
        "<li>Rocket and propellant combustion are out of scope.</li>"
        "<li>NASA PSI holds no partial-gravity combustion test data.</li>"
        "<li>E-FIELD is a simulation, not direct partial-gravity evidence.</li></ul></div>"
        "</div></div>"
    )

    st.html('<div class="ff-eyebrow" style="color:var(--c-text-3);margin:var(--s-6) 0 var(--s-3)">Source registry</div>')
    manifest = pd.DataFrame(tools.manifest_rows())
    s1, s2 = st.columns([1.4, 1], vertical_alignment="bottom")
    with s1:
        s_query = st.text_input("Search sources", placeholder="Title, investigation or source ID…", label_visibility="collapsed")
    with s2:
        only_local = st.toggle("Only sources in the local corpus", value=False)
    view = manifest[["source_id", "investigation", "role", "title", "year", "file_type", "status", "url"]].copy()
    if only_local:
        view = view[view["status"] == "downloaded"]
    if s_query:
        view = view[view.apply(lambda r: r.astype(str).str.contains(s_query, case=False, regex=False).any(), axis=1)]
    view["status"] = view["status"].map(lambda s: "In corpus" if s == "downloaded" else "Web citation" if s.startswith("not downloaded") else "Unavailable")
    st.dataframe(
        view.rename(columns={"source_id": "ID", "investigation": "Investigation", "role": "Role", "title": "Title",
                             "year": "Year", "file_type": "Type", "status": "Status", "url": "Link"}),
        use_container_width=True, hide_index=True, height=360,
        column_config={"Link": st.column_config.LinkColumn(display_text="open"), "Title": st.column_config.TextColumn(width="large")},
    )

    with st.expander(f"Agent rules · {counts['rules']}", icon=":material/gavel:"):
        body = "".join(f"<tr><td style='color:{EMBER}'>{esc(r['id'])}</td><td style='font-family:var(--f-body)'>{esc(r['rule'])}</td></tr>"
                       for r in tools.facts_data().get("rules", []))
        st.html(f'<table class="ff-table"><tr><th>ID</th><th>Rule</th></tr>{body}</table>')
    footer()
