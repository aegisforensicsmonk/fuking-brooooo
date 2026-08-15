import base64
import json
import streamlit as st
from datetime import datetime
from pathlib import Path
from scrape import scrape_multiple
from search import get_search_results
import config as _drak_cfg
from llm_utils import BufferedStreamingHandler, get_model_choices, get_model_display_names
from llm import (
    get_llm, refine_query, filter_results, generate_summary, PRESET_PROMPTS,
    answer_followup, suggest_pivots, build_followup_context,
)
from langchain_core.messages import HumanMessage, AIMessage
from config import (
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    GOOGLE_API_KEY,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OLLAMA_BASE_URL,
    LLAMA_CPP_BASE_URL,
)
from health import check_llm_health, check_search_engines, check_tor_proxy


def _render_pipeline_error(stage: str, err: Exception) -> None:
    message = str(err).strip() or err.__class__.__name__
    lower_msg = message.lower()
    hints = [
        "- Confirm the relevant API key is set in your `.env` or shell before launching Streamlit.",
        "- Keys copied from dashboards often include hidden spaces; re-copy if authentication keeps failing.",
        "- Restart the app after updating environment variables so the new values are picked up.",
    ]

    if any(token in lower_msg for token in ("anthropic", "x-api-key", "invalid api key", "authentication")):
        hints.insert(0, "- Claude/Anthropic models require a valid `ANTHROPIC_API_KEY`.")
    elif "openrouter" in lower_msg or "user not found" in lower_msg or "code: 401" in lower_msg:
        hints.insert(0, "- OpenRouter 401/User not found usually means the API key is invalid/expired or has leading/trailing characters.")
        hints.insert(1, "- Set `OPENROUTER_API_KEY` without extra spaces and verify the key is active in your OpenRouter account.")
        hints.insert(2, "- Keep `OPENROUTER_BASE_URL` as `https://openrouter.ai/api/v1` unless you intentionally use a custom gateway.")
    elif "openai" in lower_msg or "gpt" in lower_msg:
        hints.insert(0, "- OpenAI models require `OPENAI_API_KEY` with access to the chosen model.")
    elif "google" in lower_msg or "gemini" in lower_msg:
        hints.insert(0, "- Google Gemini models need `GOOGLE_API_KEY` or Application Default Credentials.")

    st.error(
        f"❌ **Failed to {stage}**\n\n**Error:** `{message}`\n\n" + "\n".join(hints)
    )
    st.stop()


# --- Investigation persistence ---

INVESTIGATIONS_DIR = Path("investigations")


def save_investigation(query: str, refined_query: str, model: str, preset_label: str, sources: list, summary: str) -> str:
    """Save a completed investigation to disk. Returns the filename."""
    INVESTIGATIONS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"investigation_{timestamp}.json"
    data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "refined_query": refined_query,
        "model": model,
        "preset": preset_label,
        "sources": sources,
        "summary": summary,
    }
    (INVESTIGATIONS_DIR / fname).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return fname


def load_investigations() -> list:
    """Return list of saved investigations sorted newest-first."""
    if not INVESTIGATIONS_DIR.exists():
        return []
    files = sorted(INVESTIGATIONS_DIR.glob("investigation_*.json"), reverse=True)
    investigations = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_filename"] = f.name
            investigations.append(data)
        except Exception:
            continue
    return investigations


def delete_investigation(filename: str) -> bool:
    """Delete a saved investigation file by filename."""
    if not filename:
        return False
    safe_name = Path(filename).name
    target = INVESTIGATIONS_DIR / safe_name
    if target.exists() and target.is_file():
        try:
            target.unlink()
            return True
        except Exception:
            return False
    return False


def delete_all_investigations() -> int:
    """Delete all saved investigation files. Returns count of deleted files."""
    if not INVESTIGATIONS_DIR.exists():
        return 0
    count = 0
    for f in INVESTIGATIONS_DIR.glob("investigation_*.json"):
        try:
            f.unlink()
            count += 1
        except Exception:
            continue
    return count


# Cache expensive backend calls
@st.cache_data(ttl=300, show_spinner=False)
def cached_search_results(refined_query: str, threads: int):
    return get_search_results(refined_query.replace(" ", "+"), max_workers=threads)


@st.cache_data(ttl=300, show_spinner=False)
def cached_scrape_multiple(filtered: list, threads: int):
    return scrape_multiple(filtered, max_workers=threads)


# Streamlit page configuration
st.set_page_config(
    page_title="DRAK WEB // AI-Powered Dark Web OSINT & Threat Intel",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Ultra-Premium Cyber UI Styling
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

        /* Global Theme Variables */
        :root {
            --bg-main: #0A0E17;
            --bg-card: rgba(17, 24, 39, 0.78);
            --bg-card-hover: rgba(26, 35, 53, 0.85);
            --border-cyan: rgba(56, 189, 248, 0.2);
            --border-glow: rgba(6, 182, 212, 0.4);
            --accent-cyan: #06B6D4;
            --accent-cyan-light: #38BDF8;
            --accent-emerald: #10B981;
            --accent-violet: #8B5CF6;
            --accent-amber: #F59E0B;
            --accent-rose: #F43F5E;
            --text-primary: #F8FAFC;
            --text-secondary: #94A3B8;
            --text-muted: #64748B;
        }

        /* Hide Streamlit Status Widget (Bicycle / Running Icon / Loading Spinner) */
        [data-testid="stStatusWidget"],
        .stStatusWidget,
        div[data-testid="stStatusWidget"],
        div[class*="StatusWidget"],
        div[class*="statusWidget"],
        header [data-testid="stStatusWidget"],
        header [data-testid="stDecoration"],
        div[data-testid="stToolbarActions"],
        button[title="Stop"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
            width: 0 !important;
            height: 0 !important;
        }

        html, body, [class*="css"], .stApp {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
            background-color: var(--bg-main) !important;
            color: var(--text-primary) !important;
        }

        /* Subtle Cyber Grid Background */
        .stApp {
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(6, 182, 212, 0.04) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.04) 0%, transparent 40%),
                linear-gradient(to right, rgba(255, 255, 255, 0.015) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
            background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
        }

        /* Monospace elements */
        code, pre, .mono-font, [data-testid="stCodeBlock"] * {
            font-family: 'JetBrains Mono', monospace !important;
        }

        /* Header typography */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Space Grotesk', sans-serif !important;
            letter-spacing: -0.02em;
            color: var(--text-primary) !important;
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0D1322 0%, #080C14 100%) !important;
            border-right: 1px solid rgba(56, 189, 248, 0.15) !important;
            box-shadow: 4px 0 24px rgba(0, 0, 0, 0.4);
        }

        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
            color: #E2E8F0 !important;
            font-size: 1.05rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        /* Inputs & Form elements */
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea {
            background-color: rgba(15, 23, 42, 0.85) !important;
            border: 1px solid rgba(56, 189, 248, 0.25) !important;
            border-radius: 8px !important;
            color: #F8FAFC !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 0.95rem !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3) !important;
        }

        .stTextInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {
            border-color: var(--accent-cyan) !important;
            box-shadow: 0 0 12px rgba(6, 182, 212, 0.3), inset 0 2px 4px rgba(0, 0, 0, 0.3) !important;
        }

        /* Selectboxes */
        .stSelectbox > div > div {
            background-color: rgba(15, 23, 42, 0.85) !important;
            border: 1px solid rgba(56, 189, 248, 0.25) !important;
            border-radius: 8px !important;
            color: #F8FAFC !important;
            transition: all 0.2s ease !important;
        }

        .stSelectbox > div > div:hover {
            border-color: var(--accent-cyan) !important;
        }

        /* Premium Buttons */
        .stButton > button {
            background: linear-gradient(135deg, #0891B2 0%, #06B6D4 50%, #0284C7 100%) !important;
            color: #FFFFFF !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 600 !important;
            font-size: 0.88rem !important;
            letter-spacing: 0.03em;
            border: 1px solid rgba(56, 189, 248, 0.4) !important;
            border-radius: 8px !important;
            padding: 0.55rem 1.1rem !important;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
            box-shadow: 0 4px 14px rgba(6, 182, 212, 0.25) !important;
        }

        .stButton > button:hover {
            background: linear-gradient(135deg, #06B6D4 0%, #38BDF8 50%, #0EA5E9 100%) !important;
            box-shadow: 0 6px 20px rgba(6, 182, 212, 0.45) !important;
            transform: translateY(-1px);
            border-color: #67E8F9 !important;
        }

        /* Search Form Submit Button Specifics */
        [data-testid="stFormSubmitButton"] > button {
            background: linear-gradient(135deg, #0284C7 0%, #06B6D4 50%, #10B981 100%) !important;
            box-shadow: 0 4px 18px rgba(6, 182, 212, 0.35) !important;
            height: 46px !important;
        }

        /* Expanders */
        .streamlit-expanderHeader, [data-testid="stExpander"] details summary {
            background-color: rgba(17, 24, 39, 0.7) !important;
            border: 1px solid rgba(56, 189, 248, 0.15) !important;
            border-radius: 8px !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 600 !important;
            color: #E2E8F0 !important;
            transition: all 0.2s ease !important;
        }

        .streamlit-expanderHeader:hover, [data-testid="stExpander"] details summary:hover {
            background-color: rgba(30, 41, 59, 0.8) !important;
            border-color: var(--accent-cyan-light) !important;
        }

        [data-testid="stExpander"] details {
            border: none !important;
            margin-bottom: 0.75rem;
        }

        [data-testid="stExpander"] details > div {
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid rgba(56, 189, 248, 0.1);
            border-top: none;
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
            padding: 1rem;
        }

        /* Chat messages */
        [data-testid="stChatMessage"] {
            background: rgba(17, 24, 39, 0.65) !important;
            border: 1px solid rgba(56, 189, 248, 0.15) !important;
            border-radius: 10px !important;
            margin-bottom: 0.85rem !important;
            backdrop-filter: blur(8px);
        }

        /* Sliders */
        .stSlider [data-baseweb="slider"] {
            color: var(--accent-cyan) !important;
        }

        .kpi-card {
            background: linear-gradient(145deg, rgba(15, 23, 42, 0.85) 0%, rgba(10, 14, 23, 0.95) 100%);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 10px;
            padding: 1rem 1.15rem;
            min-height: 110px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }

        .kpi-card:hover {
            transform: translateY(-2px);
            border-color: rgba(56, 189, 248, 0.45);
        }

        .kpi-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, #06B6D4, #8B5CF6);
        }

        .kpi-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #94A3B8;
            margin-bottom: 0.4rem;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }

        .kpi-value {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.45rem;
            font-weight: 700;
            color: #F8FAFC;
            line-height: 1.2;
            word-break: break-word;
        }

        .badge-live {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.35);
            color: #34D399;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 3px 9px;
            border-radius: 9999px;
            letter-spacing: 0.04em;
        }

        .pulse-dot {
            width: 7px;
            height: 7px;
            background-color: #10B981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10B981;
            animation: pulse-glow 2s infinite;
        }

        @keyframes pulse-glow {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.2); opacity: 1; box-shadow: 0 0 12px #10B981; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        .badge-domain {
            display: inline-flex;
            align-items: center;
            background: rgba(139, 92, 246, 0.15);
            border: 1px solid rgba(139, 92, 246, 0.35);
            color: #C084FC;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            padding: 3px 8px;
            border-radius: 6px;
        }

        .hero-banner {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(26, 35, 53, 0.7) 100%);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
        }

        .hero-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.6rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(90deg, #F8FAFC 0%, #38BDF8 50%, #818CF8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
        }

        .hero-subtitle {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 0.82rem;
            color: #94A3B8;
            margin-top: 2px;
            letter-spacing: 0.02em;
        }

        .findings-box {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(56, 189, 248, 0.18);
            border-radius: 10px;
            padding: 1.5rem;
            margin-top: 0.75rem;
            line-height: 1.65;
        }

        .download-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(6, 182, 212, 0.12);
            border: 1px solid rgba(6, 182, 212, 0.35);
            color: #38BDF8 !important;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 600;
            font-size: 0.85rem;
            padding: 6px 14px;
            border-radius: 6px;
            text-decoration: none !important;
            transition: all 0.2s ease;
        }

        .download-pill:hover {
            background: rgba(6, 182, 212, 0.22);
            border-color: #38BDF8;
            box-shadow: 0 0 12px rgba(6, 182, 212, 0.3);
            color: #FFFFFF !important;
        }

        .onion-link {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.82rem;
            color: #38BDF8;
            background: rgba(15, 23, 42, 0.6);
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid rgba(56, 189, 248, 0.15);
            text-decoration: none;
            word-break: break-all;
        }

        .onion-link:hover {
            color: #67E8F9;
            border-color: #38BDF8;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Sidebar Operations Console ---

st.sidebar.markdown(
    """
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 1.2rem; padding-bottom: 0.8rem; border-bottom: 1px solid rgba(56,189,248,0.15);">
        <span style="font-size: 1.6rem;">🕵️‍♂️</span>
        <div>
            <div style="font-family: 'Space Grotesk', sans-serif; font-weight: 800; font-size: 1.05rem; letter-spacing: 0.04em; color: #F8FAFC;">DRAK WEB</div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #38BDF8; letter-spacing: 0.06em;">HIGH-SPEED OSINT v3.0</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

def _env_is_set(value) -> bool:
    return bool(value and str(value).strip() and "your_" not in str(value))

if "custom_api_url" not in st.session_state:
    st.session_state["custom_api_url"] = _drak_cfg.CUSTOM_API_BASE_URL or ""
    st.session_state["custom_api_key"] = _drak_cfg.CUSTOM_API_KEY or ""
    st.session_state["custom_api_model"] = _drak_cfg.CUSTOM_API_MODEL or ""

_drak_cfg.CUSTOM_API_BASE_URL = st.session_state["custom_api_url"].strip() or None
_drak_cfg.CUSTOM_API_KEY = st.session_state["custom_api_key"].strip() or None
_drak_cfg.CUSTOM_API_MODEL = st.session_state["custom_api_model"].strip() or None

st.sidebar.subheader("🤖 Neural Intelligence Engine")

model_options = get_model_choices()
model_display_names = get_model_display_names(model_options)
default_model_index = (
    next(
        (idx for idx, name in enumerate(model_options) if name.lower() == "gpt4o"),
        0,
    )
    if model_options
    else 0
)

if not model_options:
    st.sidebar.error(
        "⛔ **No LLM models available.**\n\n"
        "No API keys or local providers are configured. "
        "Set at least one in your `.env` file and restart Drak web."
    )
    st.stop()

model = st.sidebar.selectbox(
    "Active AI Model",
    model_options,
    format_func=lambda m: model_display_names.get(m, m),
    index=default_model_index,
    key="model_select",
)

with st.sidebar.expander("🔌 Custom Gateway / OpenAI API"):
    st.text_input("Base URL", key="custom_api_url", placeholder="https://api.groq.com/openai/v1")
    st.text_input("API Key", key="custom_api_key", type="password")
    st.text_input("Model Name", key="custom_api_model", placeholder="llama-3.3-70b-versatile")

st.sidebar.subheader("⚡ High-Speed Pipeline Tuning")
threads = st.sidebar.slider("Parallel Harvester Threads", 4, 16, 16, key="thread_slider", help="Number of concurrent connections used for dark web searches & scraping.")
max_results = st.sidebar.slider(
    "Max Raw Onion Hits to Inspect", 10, 80, 40, key="max_results_slider",
    help="Cap the number of raw search results analyzed by the neural filter.",
)
max_scrape = st.sidebar.slider(
    "Max Deep Onion Pages to Scrape", 2, 12, 6, key="max_scrape_slider",
    help="Fast smart scraping: Only the top relevant filtered candidates get scraped for full content.",
)

st.sidebar.divider()
st.sidebar.subheader("📡 Provider Telemetry")
_providers = [
    ("OpenAI",      OPENAI_API_KEY,     True),
    ("Anthropic",   ANTHROPIC_API_KEY,  True),
    ("Google",      GOOGLE_API_KEY,     True),
    ("OpenRouter",  OPENROUTER_API_KEY, True),
    ("Ollama",      OLLAMA_BASE_URL,    False),
    ("llama.cpp",   LLAMA_CPP_BASE_URL, False),
]
for name, value, is_cloud in _providers:
    if _env_is_set(value):
        st.sidebar.markdown(f"<div style='font-size:0.83rem; margin-bottom:4px;'><span style='color:#10B981;'>●</span> <b>{name}</b> <span style='font-size:0.7rem; color:#34D399; background:rgba(16,185,129,0.15); padding:1px 6px; border-radius:4px;'>READY</span></div>", unsafe_allow_html=True)
    elif is_cloud:
        st.sidebar.markdown(f"<div style='font-size:0.83rem; margin-bottom:4px;'><span style='color:#F59E0B;'>○</span> <b>{name}</b> <span style='font-size:0.7rem; color:#FBBF24; background:rgba(245,158,11,0.15); padding:1px 6px; border-radius:4px;'>NO KEY</span></div>", unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f"<div style='font-size:0.83rem; margin-bottom:4px;'><span style='color:#64748B;'>○</span> <b>{name}</b> <span style='font-size:0.7rem; color:#94A3B8;'>OPTIONAL</span></div>", unsafe_allow_html=True)

with st.sidebar.expander("🎯 Target Domain & System Prompts"):
    preset_options = {
        "🔍 Dark Web Threat Intel": "threat_intel",
        "🦠 Ransomware / Malware Focus": "ransomware_malware",
        "👤 Personal / Identity Investigation": "personal_identity",
        "🏢 Corporate Espionage / Data Leaks": "corporate_espionage",
    }
    preset_placeholders = {
        "threat_intel": "e.g. Pay extra attention to cryptocurrency wallet addresses and exchange names.",
        "ransomware_malware": "e.g. Highlight any references to double-extortion tactics or known ransomware-as-a-service affiliates.",
        "personal_identity": "e.g. Flag any passport or government ID numbers and note which country they appear to be from.",
        "corporate_espionage": "e.g. Prioritize any mentions of source code repositories, API keys, or internal Slack/email dumps.",
    }
    selected_preset_label = st.selectbox("Investigation Domain", list(preset_options.keys()), key="preset_select")
    selected_preset = preset_options[selected_preset_label]
    st.text_area("Active System Prompt", value=PRESET_PROMPTS[selected_preset].strip(), height=160, disabled=True, key="system_prompt_display")
    custom_instructions = st.text_area("Custom Directives (optional)", placeholder=preset_placeholders[selected_preset], height=80, key="custom_instructions")

st.sidebar.divider()
st.sidebar.subheader("🩺 System Diagnostics")
col_h1, col_h2 = st.sidebar.columns(2)
with col_h1:
    check_ai_btn = st.button("🔌 Ping AI", use_container_width=True)
with col_h2:
    check_tor_btn = st.button("🧅 Ping Tor", use_container_width=True)

if check_ai_btn:
    with st.sidebar:
        with st.spinner(f"Testing {model}..."):
            result = check_llm_health(model)
        if result["status"] == "up":
            st.success(f"✅ **{result['provider']}** Connected ({result['latency_ms']}ms)")
        else:
            st.error(f"❌ **{result['provider']}** Failed\n\n{result['error']}")

if check_tor_btn:
    with st.sidebar:
        with st.spinner("Testing Tor socks proxy..."):
            tor_result = check_tor_proxy()
        if tor_result["status"] == "down":
            st.error(f"❌ **Tor Proxy Offline**\n\n{tor_result['error']}")
        else:
            st.success(f"✅ **Tor Proxy Online** ({tor_result['latency_ms']}ms)")
            with st.spinner("Pinging 16 Search Nodes..."):
                engine_results = check_search_engines()
            up_count = sum(1 for r in engine_results if r["status"] == "up")
            st.info(f"📡 **{up_count}/16 Nodes Active**")

st.sidebar.divider()
st.sidebar.subheader("📂 Investigation Dossier Vault")
saved_investigations = load_investigations()
if saved_investigations:
    inv_labels = [
        f"{inv['_filename'].replace('investigation_','').replace('.json','')} — {inv['query'][:35]}"
        for inv in saved_investigations
    ]
    selected_inv_label = st.sidebar.selectbox("Saved Dossiers", ["(none)"] + inv_labels, key="inv_select")
    if selected_inv_label != "(none)":
        selected_inv_idx = inv_labels.index(selected_inv_label)
        _saved = saved_investigations[selected_inv_idx]
        _fname = _saved.get("_filename", "")

        col_load, col_del = st.sidebar.columns([1, 1])
        if col_load.button("📂 Load", use_container_width=True, key="load_inv_btn"):
            _saved_preset = _saved.get("preset", "threat_intel")
            if _saved_preset in preset_options:
                _preset_key = preset_options[_saved_preset]
            elif _saved_preset in preset_options.values():
                _preset_key = _saved_preset
            else:
                _preset_key = "threat_intel"
            st.session_state["active_investigation"] = {
                "query": _saved.get("query", ""),
                "refined": _saved.get("refined_query", ""),
                "model": _saved.get("model", ""),
                "preset": _preset_key,
                "preset_label": _saved.get("preset", ""),
                "sources": _saved.get("sources", []),
                "scraped": None,
                "summary": _saved.get("summary", ""),
                "results_count": len(_saved.get("sources", [])),
                "timestamp": _saved.get("timestamp", ""),
            }
            st.session_state["chat_history"] = []
            st.session_state["pivot_suggestions"] = []
            st.rerun()

        if col_del.button("🗑️ Remove", use_container_width=True, key="del_inv_btn"):
            if delete_investigation(_fname):
                # If the deleted dossier was active, clear active investigation
                curr_active = st.session_state.get("active_investigation", {})
                if curr_active.get("timestamp") == _saved.get("timestamp"):
                    st.session_state.pop("active_investigation", None)
                    st.session_state["chat_history"] = []
                    st.session_state["pivot_suggestions"] = []
                st.sidebar.success(f"Dossier removed.")
                st.rerun()
            else:
                st.sidebar.error("Failed to remove dossier.")

    with st.sidebar.expander("⚙️ Vault Management", expanded=False):
        st.caption(f"Total Dossiers: **{len(saved_investigations)}**")
        wipe_confirm = st.checkbox("Confirm delete all dossiers", key="wipe_confirm_cb")
        if st.button("🗑️ Clear All Saved Dossiers", use_container_width=True, key="clear_all_dossiers_btn", disabled=not wipe_confirm):
            deleted_count = delete_all_investigations()
            st.session_state.pop("active_investigation", None)
            st.session_state["chat_history"] = []
            st.session_state["pivot_suggestions"] = []
            st.sidebar.success(f"Cleared {deleted_count} dossiers.")
            st.rerun()
else:
    st.sidebar.caption("No saved dossiers found in vault.")


# --- Main Command Console Header ---

st.markdown(
    f"""
    <div class="hero-banner">
        <div>
            <div class="hero-title">DRAK WEB // COMMAND CENTER</div>
            <div class="hero-subtitle">High-Speed Autonomous Dark Web OSINT Harvester & Neural Intelligence Engine</div>
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
            <div class="badge-live"><span class="pulse-dot"></span>TOR ACTIVE (127.0.0.1:9050)</div>
            <div class="badge-domain">DOMAIN: {selected_preset_label.split(' ')[-1]}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Search Input Bar
with st.form("search_form", clear_on_submit=False):
    col_input, col_button = st.columns([10, 2])
    query = col_input.text_input(
        "Enter Dark Web Search Query or Threat Target",
        placeholder="Enter Dark Web Search Query (e.g. ransomware leaks, database dump, crypto wallet, telegram breach)...",
        label_visibility="collapsed",
        key="query_input",
    )
    run_button = col_button.form_submit_button("⚡ LAUNCH INTEL SCAN", use_container_width=True)

# Status + result section placeholders
status_slot = st.empty()
_stat_cols = st.columns(4)
p1, p2, p3, p4 = [col.empty() for col in _stat_cols]
notes_placeholder = st.empty()
sources_placeholder = st.empty()
findings_placeholder = st.empty()


# --- Active Investigation & Chat Renderers ---

def _render_investigation_body(inv):
    """Render Notes, Sources, Findings, and Export controls for an active investigation."""
    sources = inv.get("sources", [])
    scraped_count = len(inv.get("scraped", {})) if inv.get("scraped") else "N/A"
    
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">🎯 Target Vector</div>
                <div class="kpi-value" style="font-size: 0.95rem; color: #38BDF8;">{inv.get('refined', inv.get('query', ''))[:35]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with kpi_cols[1]:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">🌐 Onion Hits Harvested</div>
                <div class="kpi-value" style="color: #818CF8;">{inv.get('results_count', len(sources))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with kpi_cols[2]:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">🛡️ Relevant Signals</div>
                <div class="kpi-value" style="color: #34D399;">{len(sources)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with kpi_cols[3]:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">📑 Scraped Artifacts</div>
                <div class="kpi-value" style="color: #F59E0B;">{scraped_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    with st.expander("📋 Investigation Operational Telemetry & Model Parameters", expanded=False):
        st.markdown(f"**Target Query:** `{inv.get('query', '')}`")
        st.markdown(f"**Refined Search Syntax:** `{inv.get('refined', '')}`")
        st.markdown(f"**Neural Engine:** `{inv.get('model', '')}` &nbsp;|&nbsp; **Threat Domain:** `{inv.get('preset_label') or inv.get('preset', '')}`")
        st.markdown(f"**Verified Onion Sources:** `{len(sources)}` &nbsp;|&nbsp; **Deep Scraped Artifacts:** `{scraped_count}`")

    with st.expander(f"🔗 Verified Onion Sources & Evidence URLs ({len(sources)} sources)", expanded=True if sources else False):
        if sources:
            for i, item in enumerate(sources, 1):
                title = item.get("title", "Untitled Onion Node")
                link = item.get("link", "")
                st.markdown(
                    f"<div style='margin-bottom: 8px; padding: 6px 10px; background: rgba(15,23,42,0.6); border-radius: 6px; border: 1px solid rgba(56,189,248,0.1);'>"
                    f"<span style='color: #06B6D4; font-weight: 700; margin-right: 8px;'>#{i}</span>"
                    f"<span style='font-weight: 600; color: #F1F5F9;'>{title}</span><br>"
                    f"<a class='onion-link' href='{link}' target='_blank'>{link}</a>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No onion sources retained in this dossier.")

    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 1.5rem; margin-bottom: 0.5rem; border-bottom: 1px solid rgba(56,189,248,0.2); padding-bottom: 0.4rem;">
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.25rem; font-weight: 700; color: #F8FAFC; display: flex; align-items: center; gap: 8px;">
                <span style="color: #06B6D4;">🔎</span> Threat Intelligence Findings & Dossier
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    summary = inv.get("summary", "") or ""
    if summary:
        st.markdown(f"<div class='findings-box'>{summary}</div>", unsafe_allow_html=True)
        
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        b64_md = base64.b64encode(summary.encode("utf-8")).decode()
        json_data = json.dumps(inv, indent=2)
        b64_json = base64.b64encode(json_data.encode("utf-8")).decode()
        
        st.markdown(
            f"""
            <div style="display: flex; gap: 12px; margin-top: 1rem; align-items: center; flex-wrap: wrap;">
                <a class="download-pill" href="data:file/markdown;base64,{b64_md}" download="dossier_{now}.md">
                    📥 Export Markdown Dossier
                </a>
                <a class="download-pill" style="border-color: rgba(139,92,246,0.35); color: #C084FC !important; background: rgba(139,92,246,0.12);" href="data:file/json;base64,{b64_json}" download="intel_{now}.json">
                    💾 Export JSON Payload
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _followup_history_messages(chat_history, max_turns=5):
    recent = chat_history[-(max_turns * 2):] if chat_history else []
    msgs = []
    for turn in recent:
        if turn.get("role") == "user":
            msgs.append(HumanMessage(content=turn.get("content", "")))
        else:
            msgs.append(AIMessage(content=turn.get("content", "")))
    return msgs


def _render_chat_panel(inv):
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="border-top: 1px solid rgba(56,189,248,0.2); padding-top: 1.2rem; margin-bottom: 0.8rem;">
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.2rem; font-weight: 700; color: #F8FAFC; display: flex; align-items: center; gap: 8px;">
                <span style="color: #818CF8;">💬</span> Threat Hunter Intelligence Chat & Pivots
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pivots = st.session_state.get("pivot_suggestions", [])
    if pivots:
        st.caption("⚡ Autonomous Pivots Detected — Click to launch a dedicated investigation:")
        pivot_cols = st.columns(len(pivots))
        for i, (col, pq) in enumerate(zip(pivot_cols, pivots)):
            if col.button(f"🎯 {pq}", key=f"pivot_{i}", use_container_width=True):
                st.session_state["pivot_query"] = pq
                st.rerun()

    for turn in st.session_state.get("chat_history", []):
        role = turn.get("role", "assistant")
        with st.chat_message(role, avatar="🧑‍💻" if role == "user" else "🤖"):
            st.markdown(turn.get("content", ""))

    if st.session_state.get("chat_history"):
        if st.button("🧹 Clear Chat History", key="clear_chat"):
            st.session_state["chat_history"] = []
            st.rerun()

    followup = st.chat_input("Ask a specialized threat query or request IOC extraction on this dossier...")
    if followup:
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(followup)
        context = build_followup_context(
            inv.get("query", ""), inv.get("refined", ""),
            inv.get("sources", []), inv.get("scraped"), inv.get("summary", ""),
        )
        history = _followup_history_messages(st.session_state.get("chat_history", []))
        with st.chat_message("assistant", avatar="🤖"):
            answer_slot = st.empty()
            acc = {"text": ""}

            def _emit(chunk: str):
                acc["text"] += chunk
                answer_slot.markdown(acc["text"])

            try:
                f_llm = get_llm(inv.get("model"))
                f_llm.callbacks = [BufferedStreamingHandler(ui_callback=_emit)]
                answer = answer_followup(
                    f_llm, followup, context, history=history,
                    preset=inv.get("preset", "threat_intel"),
                )
                if not acc["text"].strip() and answer:
                    acc["text"] = answer
                    answer_slot.markdown(answer)
            except Exception as e:
                acc["text"] = f"⚠️ Failed to answer follow-up: {e}"
                answer_slot.markdown(acc["text"])

        st.session_state.setdefault("chat_history", [])
        st.session_state["chat_history"].append({"role": "user", "content": followup})
        st.session_state["chat_history"].append({"role": "assistant", "content": acc["text"]})


# --- High-Speed Search Pipeline Execution ---

_pivot_query = st.session_state.pop("pivot_query", None)
_active_query = _pivot_query or query
_do_run = bool(_active_query) and (run_button or _pivot_query is not None)

if _do_run:
    query = _active_query
    st.session_state.pop("active_investigation", None)
    for k in ["refined", "results", "filtered", "scraped", "streamed_summary",
              "chat_history", "pivot_suggestions"]:
        st.session_state.pop(k, None)

    # Stage 1: Fast Load LLM
    with status_slot.container():
        with st.spinner("🔄 Initializing Neural Intelligence Engine..."):
            try:
                llm = get_llm(model)
            except Exception as e:
                _render_pipeline_error("load the selected LLM", e)

    # Stage 2: Fast Refine Query
    with status_slot.container():
        with st.spinner("🎯 Optimizing Target Vector..."):
            try:
                st.session_state.refined = refine_query(llm, query)
            except Exception as e:
                _render_pipeline_error("refine the query", e)
    
    p1.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">🎯 Target Vector</div>
            <div class="kpi-value" style="font-size: 0.95rem; color: #38BDF8;">{st.session_state.refined[:35]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Stage 3: High-Speed Parallel Dark Web Harvest
    with status_slot.container():
        with st.spinner("⚡ Parallel Multi-Node Dark Web Harvest across 16 Onion Engines..."):
            st.session_state.results = cached_search_results(
                st.session_state.refined, threads
            )
    if len(st.session_state.results) > max_results:
        st.session_state.results = st.session_state.results[:max_results]
        
    p2.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">🌐 Onion Hits Harvested</div>
            <div class="kpi-value" style="color: #818CF8;">{len(st.session_state.results)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Stage 4: Smart Semantic Pre-Filtering (Instant filter BEFORE scraping to save 90% of time)
    with status_slot.container():
        with st.spinner("🛡️ Fast Neural Relevance Filter prioritizing top onion targets..."):
            candidate_pool = st.session_state.results[:max_results]
            st.session_state.filtered = filter_results(
                llm, st.session_state.refined, candidate_pool
            )
            
    if len(st.session_state.filtered) > max_scrape:
        st.session_state.filtered = st.session_state.filtered[:max_scrape]
        
    p3.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">🛡️ Relevant Signals</div>
            <div class="kpi-value" style="color: #34D399;">{len(st.session_state.filtered)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Stage 5: Targeted Deep Scraping (Only scrape the top relevant candidates)
    with status_slot.container():
        with st.spinner(f"📜 Fast parallel extraction on {len(st.session_state.filtered)} verified onion targets..."):
            st.session_state.scraped = cached_scrape_multiple(
                st.session_state.filtered, threads
            )

    p4.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">📑 Scraped Artifacts</div>
            <div class="kpi-value" style="color: #F59E0B;">{len(st.session_state.scraped)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Stage 6: Intelligence Synthesis & Streaming Summary
    st.session_state.streamed_summary = ""

    with findings_placeholder.container():
        st.markdown(
            """
            <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 1.5rem; margin-bottom: 0.5rem; border-bottom: 1px solid rgba(56,189,248,0.2); padding-bottom: 0.4rem;">
                <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.25rem; font-weight: 700; color: #F8FAFC; display: flex; align-items: center; gap: 8px;">
                    <span style="color: #06B6D4;">🔎</span> Threat Intelligence Findings & Dossier
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        summary_slot = st.empty()

    def ui_emit(chunk: str):
        st.session_state.streamed_summary += chunk
        summary_slot.markdown(
            f"<div class='findings-box'>{st.session_state.streamed_summary}</div>",
            unsafe_allow_html=True,
        )

    with status_slot.container():
        with st.spinner("✍️ Synthesizing Strategic Intelligence Dossier..."):
            stream_handler = BufferedStreamingHandler(ui_callback=ui_emit)
            llm.callbacks = [stream_handler]
            summary_text = generate_summary(
                llm, query, st.session_state.scraped,
                preset=selected_preset, custom_instructions=custom_instructions,
            )

    if not st.session_state.streamed_summary.strip() and summary_text:
        st.session_state.streamed_summary = summary_text
        summary_slot.markdown(
            f"<div class='findings-box'>{summary_text}</div>",
            unsafe_allow_html=True,
        )

    _fname = save_investigation(
        query=query,
        refined_query=st.session_state.refined,
        model=model,
        preset_label=selected_preset_label,
        sources=st.session_state.filtered,
        summary=st.session_state.streamed_summary,
    )

    with notes_placeholder.container():
        with st.expander("📋 Investigation Operational Telemetry & Model Parameters", expanded=False):
            st.markdown(f"**Target Query:** `{query}`")
            st.markdown(f"**Refined Search Syntax:** `{st.session_state.refined}`")
            st.markdown(f"**Neural Engine:** `{model}` &nbsp;|&nbsp; **Threat Domain:** `{selected_preset_label}`")
            st.markdown(
                f"**Raw Onion Hits:** `{len(st.session_state.results)}` &nbsp;|&nbsp; "
                f"**Verified Sources:** `{len(st.session_state.filtered)}` &nbsp;|&nbsp; "
                f"**Scraped Artifacts:** `{len(st.session_state.scraped)}`"
            )

    with sources_placeholder.container():
        with st.expander(f"🔗 Verified Onion Sources & Evidence URLs ({len(st.session_state.filtered)} sources)", expanded=True):
            for i, item in enumerate(st.session_state.filtered, 1):
                title = item.get("title", "Untitled Onion Node")
                link = item.get("link", "")
                st.markdown(
                    f"<div style='margin-bottom: 8px; padding: 6px 10px; background: rgba(15,23,42,0.6); border-radius: 6px; border: 1px solid rgba(56,189,248,0.1);'>"
                    f"<span style='color: #06B6D4; font-weight: 700; margin-right: 8px;'>#{i}</span>"
                    f"<span style='font-weight: 600; color: #F1F5F9;'>{title}</span><br>"
                    f"<a class='onion-link' href='{link}' target='_blank'>{link}</a>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    with findings_placeholder.container():
        st.markdown(
            """
            <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 1.5rem; margin-bottom: 0.5rem; border-bottom: 1px solid rgba(56,189,248,0.2); padding-bottom: 0.4rem;">
                <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.25rem; font-weight: 700; color: #F8FAFC; display: flex; align-items: center; gap: 8px;">
                    <span style="color: #06B6D4;">🔎</span> Threat Intelligence Findings & Dossier
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='findings-box'>{st.session_state.streamed_summary}</div>", unsafe_allow_html=True)
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        b64_md = base64.b64encode(st.session_state.streamed_summary.encode("utf-8")).decode()
        inv_payload = {
            "query": query,
            "refined": st.session_state.refined,
            "model": model,
            "sources": st.session_state.filtered,
            "summary": st.session_state.streamed_summary,
        }
        b64_json = base64.b64encode(json.dumps(inv_payload, indent=2).encode("utf-8")).decode()
        st.markdown(
            f"""
            <div style="display: flex; gap: 12px; margin-top: 1rem; align-items: center; flex-wrap: wrap;">
                <a class="download-pill" href="data:file/markdown;base64,{b64_md}" download="dossier_{now}.md">
                    📥 Export Markdown Dossier
                </a>
                <a class="download-pill" style="border-color: rgba(139,92,246,0.35); color: #C084FC !important; background: rgba(139,92,246,0.12);" href="data:file/json;base64,{b64_json}" download="intel_{now}.json">
                    💾 Export JSON Payload
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    status_slot.success(f"🛡️ Intel scan completed successfully! Dossier archived as `{_fname}`")

    st.session_state["active_investigation"] = {
        "query": query,
        "refined": st.session_state.refined,
        "model": model,
        "preset": selected_preset,
        "preset_label": selected_preset_label,
        "sources": st.session_state.filtered,
        "scraped": st.session_state.scraped,
        "summary": st.session_state.streamed_summary,
        "results_count": len(st.session_state.results),
    }
    st.session_state["chat_history"] = []

    with st.spinner("💡 Calculating autonomous threat pivot vectors..."):
        try:
            st.session_state["pivot_suggestions"] = suggest_pivots(
                get_llm(model), query, st.session_state.scraped, preset=selected_preset,
            )
        except Exception:
            st.session_state["pivot_suggestions"] = []

    _render_chat_panel(st.session_state["active_investigation"])

elif st.session_state.get("active_investigation"):
    _inv = st.session_state["active_investigation"]
    _ts = _inv.get("timestamp")
    st.info(f"📂 Loaded Archived Dossier: **{_inv.get('query', '')}**" + (f" &nbsp;|&nbsp; `{_ts[:16]}`" if _ts else ""))
    _render_investigation_body(_inv)
    _render_chat_panel(_inv)
