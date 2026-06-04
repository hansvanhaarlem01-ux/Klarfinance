"""
modules/components.py
---------------------
Herbruikbare UI-componenten voor Klår Finance.
"""

import streamlit as st

# Landen gesorteerd op relevantie voor Nederlandse belastingklanten
LANDEN = [
    ("🇳🇱", "Nederland",        "+31"),
    ("🇧🇪", "België",           "+32"),
    ("🇩🇪", "Duitsland",        "+49"),
    ("🇬🇧", "Verenigd Koninkrijk", "+44"),
    ("🇫🇷", "Frankrijk",        "+33"),
    ("🇪🇸", "Spanje",           "+34"),
    ("🇮🇹", "Italië",           "+39"),
    ("🇵🇱", "Polen",            "+48"),
    ("🇹🇷", "Turkije",          "+90"),
    ("🇲🇦", "Marokko",          "+212"),
    ("🇸🇷", "Suriname",         "+597"),
    ("🇦🇼", "Aruba",            "+297"),
    ("🇨🇼", "Curaçao",          "+599"),
    ("🇺🇸", "Verenigde Staten", "+1"),
    ("🇨🇦", "Canada",           "+1"),
    ("🇦🇺", "Australië",        "+61"),
    ("🇨🇭", "Zwitserland",      "+41"),
    ("🇦🇹", "Oostenrijk",       "+43"),
    ("🇸🇪", "Zweden",           "+46"),
    ("🇩🇰", "Denemarken",       "+45"),
    ("🇳🇴", "Noorwegen",        "+47"),
    ("🇵🇹", "Portugal",         "+351"),
    ("🇬🇷", "Griekenland",      "+30"),
    ("🇷🇺", "Rusland",          "+7"),
    ("🇨🇳", "China",            "+86"),
    ("🇮🇳", "India",            "+91"),
    ("🇯🇵", "Japan",            "+81"),
    ("🇿🇦", "Zuid-Afrika",      "+27"),
    ("🇧🇷", "Brazilië",         "+55"),
    ("🇲🇽", "Mexico",           "+52"),
]

# Opties zoals ze in de selectbox verschijnen
_OPTIES = [f"{vlag}  {naam}  ({code})" for vlag, naam, code in LANDEN]
_CODES  = [code for _, _, code in LANDEN]


def _parse_bestaand(waarde: str):
    """
    Splits een opgeslagen waarde als '+31 612345678' terug naar
    (geselecteerde optie-index, netnummer-vrij getal).
    """
    if not waarde:
        return 0, ""
    for i, code in enumerate(_CODES):
        if waarde.startswith(code + " "):
            return i, waarde[len(code):].strip()
        if waarde.startswith(code):
            return i, waarde[len(code):].strip()
    return 0, waarde  # geen match → gebruik rauw als nummer


def phone_input(label: str, key: str, default_value: str = "") -> str | None:
    """
    Typeform-achtige telefoonnummer-invoer:
    [🇳🇱 +31 ▾]  [06 12345678        ]

    Geeft de gecombineerde waarde terug als '+31 612345678',
    of None als het nummer leeg of ongeldig is.
    """
    default_idx, default_nummer = _parse_bestaand(str(default_value))

    col_land, col_nummer = st.columns([1, 2])

    with col_land:
        gekozen = st.selectbox(
            label,
            options=_OPTIES,
            index=default_idx,
            key=f"{key}_land",
            label_visibility="collapsed",
        )
        dial_code = _CODES[_OPTIES.index(gekozen)]

    with col_nummer:
        nummer = st.text_input(
            "Nummer",
            value=default_nummer,
            placeholder="612345678",
            key=f"{key}_nummer",
            label_visibility="collapsed",
        )

    # Validatie: alleen cijfers, minimaal 6 tekens
    nummer_clean = nummer.replace(" ", "").replace("-", "")
    if nummer_clean and not nummer_clean.isdigit():
        st.error("Voer alleen cijfers in.")
        return None
    if nummer_clean and len(nummer_clean) < 6:
        st.error("Voer een geldig telefoonnummer in.")
        return None

    if nummer_clean:
        return f"{dial_code} {nummer_clean}"
    return None


def dynamic_list_input(
    key: str,
    col1_label: str,
    col2_label: str,
    add_btn_label: str,
    default_value: list = None,
    col3_label: str = None,
    allow_negative: bool = False
) -> list | None:
    """
    Dynamisch lijstcomponent: naam + bedrag per rij, met toevoeg- en verwijderknop.
    Geeft een lijst van dicts terug: [{"naam": "Unicef", "bedrag": 150}, ...]
    of None als er niets is ingevuld.
    """
    state_key = f"dynlist_{key}"

    drie_kolommen = col3_label is not None

    # Initialiseer de rijen in session state
    if state_key not in st.session_state:
        if default_value and isinstance(default_value, list) and len(default_value) > 0:
            st.session_state[state_key] = list(default_value)
        else:
            lege_rij = {"naam": "", "bedrag": None}
            if drie_kolommen:
                lege_rij["bedrag2"] = None
            st.session_state[state_key] = [lege_rij]

    rijen = st.session_state[state_key]
    te_verwijderen = None

    # Kolomkoppen
    if drie_kolommen:
        h1, h2, h3, h4 = st.columns([3, 2, 2, 0.5])
        with h1: st.caption(col1_label)
        with h2: st.caption(col2_label)
        with h3: st.caption(col3_label)
    else:
        h1, h2, h3 = st.columns([3, 2, 0.5])
        with h1: st.caption(col1_label)
        with h2: st.caption(col2_label)

    # Render elke rij
    for i, rij in enumerate(rijen):
        if drie_kolommen:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 0.5])
        else:
            c1, c2, c4 = st.columns([3, 2, 0.5])

        with c1:
            naam = st.text_input(
                col1_label, value=rij.get("naam", ""),
                key=f"{key}_naam_{i}", label_visibility="collapsed"
            )
        with c2:
            bedrag_default = int(rij["bedrag"]) if rij.get("bedrag") is not None else None
            bedrag = st.number_input(
                col2_label, value=bedrag_default,
                min_value=None if allow_negative else 0, step=1,
                key=f"{key}_bedrag_{i}", label_visibility="collapsed"
            )

        bedrag2 = None
        if drie_kolommen:
            with c3:
                bedrag2_default = int(rij["bedrag2"]) if rij.get("bedrag2") is not None else None
                bedrag2 = st.number_input(
                    col3_label, value=bedrag2_default, min_value=0, step=1,
                    key=f"{key}_bedrag2_{i}", label_visibility="collapsed"
                )

        with c4:
            if len(rijen) > 1:
                if st.button("×", key=f"{key}_del_{i}", help="Verwijder deze regel"):
                    te_verwijderen = i

        # Sla actuele waarden terug
        rijen[i] = {"naam": naam, "bedrag": bedrag}
        if drie_kolommen:
            rijen[i]["bedrag2"] = bedrag2

    if te_verwijderen is not None:
        st.session_state[state_key].pop(te_verwijderen)
        st.rerun()

    if st.button(f"+ {add_btn_label}", key=f"{key}_add"):
        lege_rij = {"naam": "", "bedrag": None}
        if drie_kolommen:
            lege_rij["bedrag2"] = None
        st.session_state[state_key].append(lege_rij)
        st.rerun()

    # Geef alleen ingevulde rijen terug
    gevuld = [r for r in rijen if str(r.get("naam", "")).strip() and r.get("bedrag") is not None]
    return gevuld if gevuld else None
