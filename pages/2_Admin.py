"""
pages/2_Admin.py
----------------
Admin backend — alleen toegankelijk voor beheerders (ADMIN_EMAILS in secrets).
Functionaliteiten: zoeken, recordweergave per stap, export CSV/Excel.
"""

import streamlit as st
from datetime import datetime

from modules.ui import setup_page
from modules.auth import show_login_screen, show_logout_button
from modules.admin_db import (
    search_records,
    get_signed_url,
    antwoord_naar_tekst,
    export_records_csv,
    export_records_excel,
    VRAAG_LABELS,
    STAPPEN_ADMIN,
)

# ── Pagina-setup ──────────────────────────────────────────────────
setup_page("Klår Finance - Admin")
show_login_screen()
show_logout_button()

# ── Admin-toegangscontrole ────────────────────────────────────────
ADMIN_EMAILS = [e.lower() for e in st.secrets.get("ADMIN_EMAILS", [])]
if st.session_state.user.email.lower() not in ADMIN_EMAILS:
    st.error("🔒 Geen toegang. Dit gedeelte is alleen voor beheerders.")
    st.stop()

# ── Pagina-inhoud ─────────────────────────────────────────────────
st.title("Admin Panel")
st.divider()

# ── Zoekfilters ───────────────────────────────────────────────────
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    email_query = st.text_input(
        "Zoek op e-mailadres",
        placeholder="Geef (deel van) een e-mailadres op",
        key="admin_email_query"
    )
with col2:
    jaar_filter = st.number_input(
        "Jaar",
        min_value=2020,
        max_value=2035,
        value=datetime.now().year - 1,
        step=1,
        key="admin_jaar_filter"
    )
with col3:
    st.write("")
    st.write("")
    zoek_geklikt = st.button("🔍 Zoek", type="primary", use_container_width=True)

# ── Session state initialiseren ───────────────────────────────────
if "admin_results" not in st.session_state:
    st.session_state.admin_results  = []
if "admin_selected" not in st.session_state:
    st.session_state.admin_selected = None

# ── Zoekactie ─────────────────────────────────────────────────────
if zoek_geklikt:
    with st.spinner("Zoeken..."):
        st.session_state.admin_results  = search_records(email_query, jaar_filter)
        st.session_state.admin_selected = None

records = st.session_state.admin_results

# ── Resultaten ────────────────────────────────────────────────────
if records:
    st.write(f"**{len(records)} record(s) gevonden**")

    # Export knop
    col_excel, _ = st.columns([1, 5])
    with col_excel:
        st.download_button(
            "⬇️ Download Excel",
            data=export_records_excel(records),
            file_name=f"klar_export_{jaar_filter}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # Resultaten tabel
    import pandas as pd
    df_overzicht = pd.DataFrame([{
        "#":           i + 1,
        "Email":       r.get("email", "—"),
        "Jaar":        r.get("jaar", ""),
        "Type":        r.get("vragenlijst_type", ""),
        "Ingevuld op": (r.get("created_at") or "")[:10],
        "Taal":        r.get("taal", ""),
    } for i, r in enumerate(records)])

    event = st.dataframe(
        df_overzicht,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="admin_tabel",
        column_config={
            "Ingevuld op": st.column_config.TextColumn("Datum", width="small"),
        }
    )

    geselecteerde_rijen = event.selection.rows
    if geselecteerde_rijen:
        st.session_state.admin_selected = geselecteerde_rijen[0]

elif zoek_geklikt:
    st.info("Geen records gevonden voor deze zoekopdracht.")

# ── Record detail weergave ────────────────────────────────────────
geselecteerd = st.session_state.admin_selected
if geselecteerd is not None and geselecteerd < len(records):
    record     = records[geselecteerd]
    antwoorden = record.get("antwoorden", {})

    st.divider()

    # Record-koptekst
    st.subheader(f"📋 {record.get('email', '—')} — {record.get('jaar', '')}")
    st.caption(f"Taal: {record.get('taal', '')}  ·  Ingevuld: {(record.get('created_at') or '')[:10]}")

    st.write("")

    # Loop door stappen
    for stap_id, stap_info in STAPPEN_ADMIN.items():
        # Toon stap alleen als er minstens één vraag beantwoord is
        beantwoorde_vragen = [q for q in stap_info["vragen"] if q in antwoorden]
        if not beantwoorde_vragen:
            continue

        st.markdown(f"### {stap_info['titel']}")
        st.markdown("---")

        for q_id in beantwoorde_vragen:
            label  = VRAAG_LABELS.get(q_id, q_id)
            waarde = antwoorden[q_id]

            col_label, col_waarde = st.columns([2, 3])

            with col_label:
                st.markdown(f"**{label}**")

            with col_waarde:
                # Bepaal weergave op basis van type
                if isinstance(waarde, bool):
                    st.markdown("✅ Ja" if waarde else "❌ Nee")

                elif isinstance(waarde, list):
                    for item in waarde:
                        if isinstance(item, str) and item.count("/") >= 3:
                            url  = get_signed_url(item)
                            naam = item.split("/")[-1]
                            if url:
                                st.markdown(f"📄 [{naam}]({url})")
                            else:
                                st.markdown(f"📄 {naam}")
                        elif isinstance(item, dict):
                            cols = st.columns(len(item))
                            for col, (k, v) in zip(cols, item.items()):
                                col.markdown(f"**{k}:** {v}")
                        else:
                            st.markdown(f"- {item}")

                elif isinstance(waarde, str) and waarde.count("/") >= 3:
                    url  = get_signed_url(waarde)
                    naam = waarde.split("/")[-1]
                    if url:
                        st.markdown(f"📄 [{naam}]({url})")
                    else:
                        st.markdown(f"📄 {naam}")

                else:
                    st.markdown(str(waarde))

        st.write("")
