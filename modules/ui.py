"""
modules/ui.py
-------------
Gedeelde UI-setup voor Klår Finance: pagina-config, lettertype en CSS.
Roep setup_page() aan bovenin elke pagina, vóór alle andere st.* aanroepen.
"""

import base64
import os
import streamlit as st
from PIL import Image

FONT_FILE  = "Jaapokki-Regular.otf"
FAVICON_FILE = "browsertab_logo.png"


def setup_page(title: str = "Klår Finance - Vragenlijst"):
    """
    Configureert de Streamlit-pagina en injecteert font + CSS.
    Moet als EERSTE worden aangeroepen in elk paginabestand.
    """
    # Favicon
    try:
        favicon = Image.open(FAVICON_FILE)
    except FileNotFoundError:
        favicon = "📊"

    st.set_page_config(
        page_title=title,
        page_icon=favicon,
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    _inject_scroll_reset()
    _inject_font()
    _inject_base_css()


def inject_uploader_label(taal: str = "NL"):
    """
    Injecteert de juiste tekst op de file-uploader knop (taalafhankelijk).
    Roep aan ná setup_page() en nadat de taal bekend is.
    """
    tekst = '"Choose file 📂"' if taal == "EN" else '"Bestand kiezen 📂"'
    st.markdown(
        f"<style>:root {{ --uploader-text: {tekst}; }}</style>",
        unsafe_allow_html=True,
    )


# --- PRIVÉ HULPFUNCTIES ---

def scroll_to_top():
    """
    Plaatshouder — scroll via JS is niet mogelijk in Streamlit SPA-modus.
    Wordt aangeroepen bij elke stap-wissel maar doet momenteel niets.
    Verwijder de aanroepen niet: ze zijn nodig zodra Streamlit een
    native scroll-API aanbiedt.
    """
    pass

def _inject_scroll_reset():
    pass


def _inject_font():
    if not os.path.exists(FONT_FILE):
        st.error(f"Lettertypebestand '{FONT_FILE}' niet gevonden!")
        return

    with open(FONT_FILE, "rb") as f:
        font_b64 = base64.b64encode(f.read()).decode("utf-8").replace("\n", "").replace("\r", "")

    st.markdown(
        f"""
        <style>
        @font-face {{
            font-family: 'KlarCustomFont';
            src: url('data:font/otf;charset=utf-8;base64,{font_b64}') format('opentype');
            font-weight: normal;
            font-style: normal;
            font-display: block;
        }}
        html, body, [class*="st-"], .stMarkdown,
        p, h1, h2, h3, h4, h5, h6, label, span, button, input, div {{
            font-family: 'KlarCustomFont', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_base_css():
    st.markdown(
        """
        <style>
        /* ── Infoblokken (st.info) ── */
        div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] span {
            color: #707070 !important;
            font-weight: normal !important;
        }
        div[data-testid="stAlert"] strong,
        div[data-testid="stAlert"] h1,
        div[data-testid="stAlert"] h2,
        div[data-testid="stAlert"] h3 {
            color: #707070 !important;
            font-weight: bold !important;
        }
        div[data-testid="stAlert"] {
            background-color: #ffffff !important;
            border: 1px solid #707070 !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 3px rgba(28, 50, 92, 0.08) !important;
            overflow: hidden !important;
        }
        div[data-testid="stAlert"] > div {
            background-color: #ffffff !important;
            border: none !important;
            border-radius: 11px !important;
        }
        div[data-testid="stAlert"]::before,
        div[data-testid="stAlert"]::after { display: none !important; }

        /* ── Stap headers (st.subheader → h3) ── */
        [data-testid="stHeading"] h3 {
            font-size: 2.5rem !important;
        }

        /* ── Sidebar achtergrond ── */
        [data-testid="stSidebar"] {
            background-color: #e75954 !important;
        }
        [data-testid="stSidebar"] * {
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] button {
            border-color: #ffffff !important;
            background-color: transparent !important;
        }

        /* ── Sidebar collapse-knop: verberg tooltip-tekst ── */
        button[kind="headerNoPadding"] > div,
        [data-testid="stSidebarCollapsedControl"] span {
            display: none !important;
        }
        button[title],
        button[aria-label] {
            pointer-events: auto !important;
        }
        /* Verberg de tekst in de collapse-toggle knop */
        [data-testid="stSidebarCollapseButton"] span,
        [data-testid="stSidebarCollapseButton"] p {
            display: none !important;
        }

        /* ── Toggle switch (privacy) ── */
        [data-testid="stToggle"] p {
            font-size: 1rem !important;
        }
        /* Achtergrond rood als toggle aan staat */
        [data-testid="stToggleSwitch"] {
            background-color: #cccccc;
            transition: background-color 0.2s ease;
        }
        [data-testid="stToggleSwitch"][aria-checked="true"] {
            background-color: #e75954 !important;
        }

        /* ── File uploader knop ── */
        div[data-testid="stFileUploader"] button * { display: none !important; }
        div[data-testid="stFileUploader"] button {
            background-color: #ffffff !important;
            border: 1px solid #707070 !important;
            border-radius: 8px !important;
            padding: 6px 16px !important;
            height: 38px !important;
            min-width: 140px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        div[data-testid="stFileUploader"] button::after {
            content: var(--uploader-text) !important;
            font-size: 14px !important;
            color: #31333f !important;
            font-weight: normal !important;
            display: block !important;
            visibility: visible !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
