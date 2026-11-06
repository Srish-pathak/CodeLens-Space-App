"""Space theme: CSS plus small HTML component helpers for the Streamlit UI."""

from html import escape

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #05060f; --panel: rgba(16, 20, 48, 0.72); --panel-border: rgba(139, 92, 246, 0.28);
  --violet: #8b5cf6; --cyan: #22d3ee; --pink: #f472b6; --gold: #fbbf24;
  --ok: #34d399; --warn: #fbbf24; --bad: #fb7185; --text: #e6e9ff; --muted: #8f96c7;
}

html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; color: var(--text); }
.stApp {
  background:
    radial-gradient(ellipse 80% 60% at 15% 0%, rgba(139,92,246,.22), transparent 60%),
    radial-gradient(ellipse 70% 50% at 90% 10%, rgba(34,211,238,.14), transparent 60%),
    radial-gradient(ellipse 60% 60% at 50% 100%, rgba(244,114,182,.12), transparent 65%),
    var(--bg);
  background-attachment: fixed;
}

/* ---------- animated starfield ---------- */
.stApp::before, .stApp::after {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-repeat: repeat;
}
.stApp::before {
  background-image:
    radial-gradient(1.2px 1.2px at 20px 30px, #fff, transparent),
    radial-gradient(1px 1px at 90px 120px, #cfd6ff, transparent),
    radial-gradient(1.4px 1.4px at 160px 70px, #fff, transparent),
    radial-gradient(1px 1px at 230px 190px, #a5f3fc, transparent),
    radial-gradient(1.2px 1.2px at 300px 40px, #fbcfe8, transparent);
  background-size: 320px 240px; opacity: .55; animation: drift 120s linear infinite;
}
.stApp::after {
  background-image:
    radial-gradient(1.8px 1.8px at 60px 80px, #fff, transparent),
    radial-gradient(1.5px 1.5px at 200px 160px, #fde68a, transparent),
    radial-gradient(1.6px 1.6px at 340px 20px, #fff, transparent);
  background-size: 420px 300px; opacity: .6; animation: drift 200s linear infinite reverse, twinkle 5s ease-in-out infinite;
}
@keyframes drift { from { background-position: 0 0; } to { background-position: 0 1200px; } }
@keyframes twinkle { 0%,100% { opacity: .35; } 50% { opacity: .85; } }
.main .block-container, [data-testid="stSidebar"] { position: relative; z-index: 1; }
.main .block-container { padding-top: 2.2rem; max-width: 1200px; }
header[data-testid="stHeader"] { background: transparent; }

/* ---------- hero ---------- */
.hero { text-align: center; padding: 1.2rem 0 1.6rem; }
.hero .orbit {
  width: 84px; height: 84px; margin: 0 auto 10px; border-radius: 50%; position: relative;
  background: radial-gradient(circle at 35% 30%, #c4b5fd, #7c3aed 55%, #1e1b4b);
  box-shadow: 0 0 40px rgba(139,92,246,.6), inset -8px -8px 18px rgba(0,0,0,.45);
}
.hero .orbit::after {
  content: ""; position: absolute; left: -26px; right: -26px; top: 36px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(34,211,238,.7); transform: rotate(-18deg);
  box-shadow: 0 0 14px rgba(34,211,238,.5);
}
.hero h1 {
  font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 2.7rem; letter-spacing: .08em; margin: 0;
  background: linear-gradient(90deg, #c4b5fd, #67e8f9 50%, #f9a8d4); -webkit-background-clip: text;
  background-clip: text; -webkit-text-fill-color: transparent;
}
.hero p { color: var(--muted); margin: .5rem 0 0; letter-spacing: .04em; }

h2, h3, [data-testid="stHeadingWithActionElements"] h3 { font-family: 'Orbitron', sans-serif !important; letter-spacing: .05em; }

/* ---------- panels & cards ---------- */
.panel {
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: 16px;
  padding: 1.1rem 1.3rem; backdrop-filter: blur(10px); box-shadow: 0 8px 32px rgba(0,0,0,.35);
}
.stat {
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: 14px; padding: .95rem 1.1rem;
  backdrop-filter: blur(10px); position: relative; overflow: hidden; height: 100%;
}
.stat::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--accent, var(--violet)); box-shadow: 0 0 14px var(--accent, var(--violet)); }
.stat .label { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .14em; }
.stat .value { font-family: 'Orbitron', sans-serif; font-size: 1.75rem; font-weight: 700; margin-top: .2rem; }
.stat .sub { color: var(--muted); font-size: .78rem; margin-top: .1rem; }

.finding {
  background: rgba(10, 13, 36, .75); border: 1px solid rgba(143,150,199,.18); border-left: 4px solid var(--c, var(--cyan));
  border-radius: 12px; padding: .75rem 1rem; margin-bottom: .6rem;
}
.finding .meta { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin-bottom: .35rem; }
.chip {
  font-size: .68rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; padding: .15rem .55rem;
  border-radius: 999px; color: #05060f; background: var(--c, var(--cyan));
}
.chip.ghost { background: transparent; color: var(--muted); border: 1px solid rgba(143,150,199,.3); text-transform: none; letter-spacing: 0; font-family: 'JetBrains Mono', monospace; }
.finding .desc { color: var(--text); font-size: .93rem; line-height: 1.5; }
.finding .path { font-family: 'JetBrains Mono', monospace; color: var(--cyan); font-size: .8rem; }
.tip { border-left-color: var(--violet); }
.tip .title { font-weight: 600; margin-bottom: .2rem; }

.ring-wrap { display: flex; flex-direction: column; align-items: center; gap: .4rem; padding: .5rem 0; }
.ring-wrap .verdict { font-family: 'Orbitron', sans-serif; letter-spacing: .1em; }

.banner { border-radius: 12px; padding: .7rem 1rem; margin: .4rem 0 1rem; font-size: .9rem; border: 1px solid; }
.banner.info { background: rgba(34,211,238,.08); border-color: rgba(34,211,238,.35); }
.banner.warn { background: rgba(251,191,36,.08); border-color: rgba(251,191,36,.4); }
.banner.ok   { background: rgba(52,211,153,.08); border-color: rgba(52,211,153,.4); }

.rank { display: inline-block; min-width: 1.6rem; text-align: center; border-radius: 6px; font-weight: 700; padding: 0 .4rem; color: #05060f; }

/* ---------- Streamlit widget polish ---------- */
.stButton > button, .stDownloadButton > button {
  border-radius: 999px; border: 1px solid var(--panel-border); background: rgba(139,92,246,.12); color: var(--text);
  transition: all .2s ease; font-weight: 500;
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--cyan); box-shadow: 0 0 18px rgba(34,211,238,.35); color: #fff; }
.stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #7c3aed, #06b6d4); border: none; color: #fff; font-weight: 600; letter-spacing: .04em;
  box-shadow: 0 0 22px rgba(124,58,237,.45);
}
.stButton > button[kind="primary"]:hover { box-shadow: 0 0 30px rgba(34,211,238,.6); transform: translateY(-1px); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0a0c20, #07081a); border-right: 1px solid var(--panel-border); }
[data-testid="stSidebar"] h2 { font-size: 1.05rem; }
.stTabs [data-baseweb="tab-list"] { gap: .3rem; border-bottom: 1px solid var(--panel-border); }
.stTabs [data-baseweb="tab"] { border-radius: 10px 10px 0 0; padding: .5rem 1rem; color: var(--muted); }
.stTabs [aria-selected="true"] { color: #fff !important; background: rgba(139,92,246,.18); }
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div {
  background: rgba(10,13,36,.8) !important; border-color: var(--panel-border) !important; color: var(--text) !important;
}
[data-testid="stExpander"] { background: rgba(10,13,36,.6); border: 1px solid var(--panel-border); border-radius: 12px; }
[data-testid="stCodeBlock"], pre { border-radius: 12px; border: 1px solid rgba(143,150,199,.18); }
[data-testid="stFileUploader"] section { background: rgba(10,13,36,.6); border: 1px dashed var(--panel-border); border-radius: 12px; }
hr { border-color: var(--panel-border) !important; }
::-webkit-scrollbar { width: 10px; } ::-webkit-scrollbar-thumb { background: rgba(139,92,246,.4); border-radius: 8px; }

@media (max-width: 700px) { .hero h1 { font-size: 1.7rem; } }
</style>
"""

SEVERITY_COLORS = {
    "critical": "#fb7185", "high": "#fb923c", "warning": "#fbbf24",
    "medium": "#fbbf24", "low": "#22d3ee", "info": "#22d3ee",
}
RANK_COLORS = {"A": "#34d399", "B": "#a3e635", "C": "#fbbf24", "D": "#fb923c", "E": "#fb7185", "F": "#f43f5e"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, tagline: str) -> None:
    st.markdown(
        '<div class="hero"><div class="orbit"></div><h1>{}</h1><p>{}</p></div>'.format(escape(title), escape(tagline)),
        unsafe_allow_html=True,
    )


def banner(text: str, kind: str = "info") -> None:
    st.markdown('<div class="banner {}">{}</div>'.format(kind, escape(text)), unsafe_allow_html=True)


def stat_card(label: str, value, sub: str = "", accent: str = "#8b5cf6") -> str:
    return (
        '<div class="stat" style="--accent:{}"><div class="label">{}</div><div class="value">{}</div>'
        '<div class="sub">{}</div></div>'
    ).format(accent, escape(str(label)), escape(str(value)), escape(str(sub)))


def stat_row(cards: list[tuple]) -> None:
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        column.markdown(stat_card(*card), unsafe_allow_html=True)


def finding_card(item: dict, path: str | None = None) -> str:
    severity = str(item.get("severity", "info")).lower()
    color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"])
    description = item.get("description") or item.get("explanation") or item.get("title") or "No description provided."
    meta = '<span class="chip">{}</span><span class="chip ghost">line {}</span>'.format(
        escape(severity.title()), escape(str(item.get("line", "N/A")))
    )
    if item.get("source") == "local":
        meta += '<span class="chip ghost">offline check</span>'
    if path:
        meta += '<span class="path">{}</span>'.format(escape(path))
    return '<div class="finding" style="--c:{}"><div class="meta">{}</div><div class="desc">{}</div></div>'.format(
        color, meta, escape(str(description))
    )


def tip_card(item: dict, path: str | None = None) -> str:
    title = escape(str(item.get("title", "Suggestion")))
    detail = escape(str(item.get("detail") or item.get("explanation") or ""))
    path_html = '<div class="path">{}</div>'.format(escape(path)) if path else ""
    return '<div class="finding tip">{}<div class="title">💡 {}</div><div class="desc">{}</div></div>'.format(
        path_html, title, detail
    )


def rank_badge(rank: str) -> str:
    return '<span class="rank" style="background:{}">{}</span>'.format(RANK_COLORS.get(rank, "#8f96c7"), escape(str(rank)))


def score_ring(score: float, label: str) -> str:
    score = max(0.0, min(10.0, float(score)))
    color = "#34d399" if score >= 8 else "#fbbf24" if score >= 5 else "#fb7185"
    circumference = 2 * 3.14159 * 52
    offset = circumference * (1 - score / 10)
    return (
        '<div class="ring-wrap"><svg width="150" height="150" viewBox="0 0 120 120">'
        '<circle cx="60" cy="60" r="52" fill="none" stroke="rgba(143,150,199,.18)" stroke-width="9"/>'
        '<circle cx="60" cy="60" r="52" fill="none" stroke="{c}" stroke-width="9" stroke-linecap="round" '
        'stroke-dasharray="{ci:.1f}" stroke-dashoffset="{off:.1f}" transform="rotate(-90 60 60)" '
        'style="filter:drop-shadow(0 0 6px {c})"/>'
        '<text x="60" y="64" text-anchor="middle" fill="#e6e9ff" font-family="Orbitron, sans-serif" font-size="26" font-weight="700">{s:g}</text>'
        '<text x="60" y="82" text-anchor="middle" fill="#8f96c7" font-size="9">OUT OF 10</text></svg>'
        '<div class="verdict" style="color:{c}">{l}</div></div>'
    ).format(c=color, ci=circumference, off=offset, s=round(score, 1), l=escape(label.upper()))
