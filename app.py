import streamlit as st
import re
import requests
import pandas as pd
from datetime import datetime

# ── Gedeelde modules ──────────────────────────────────────────────
from modules.ui import setup_page, inject_uploader_label, scroll_to_top
from modules.auth import show_login_screen, show_logout_button
from modules.components import phone_input, dynamic_list_input
from modules.database import (
    supabase,
    save_to_supabase,
    load_previous_answers,
    upload_document,
    get_document_url,
    google_address_autocomplete,
)

try:
    from streamlit_searchbox import st_searchbox
except ImportError:
    st_searchbox = None

# ── Pagina-setup (moet als eerste) ───────────────────────────────
setup_page("Klår Finance - Belastingaangifte Vragenlijst")

# ── Authenticatie ─────────────────────────────────────────────────
show_login_screen()   # stopt de app als niet ingelogd
show_logout_button()  # toont uitlogknop (+ admin-knop) in sidebar

# ── Admin modus ───────────────────────────────────────────────────
if st.session_state.get("admin_modus", False):
    from modules.admin_db import (
        search_records, get_signed_url, antwoord_naar_tekst,
        export_records_excel, VRAAG_LABELS, STAPPEN_ADMIN,
        sla_nextens_id_op
    )
    from modules.nextens import (
        zoek_persoon_op_bsn, maak_persoon_aan, update_persoon,
        bouw_persoon_payload, vergelijk_payload
    )
    import pandas as pd

    st.title("Admin Panel")
    st.divider()

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        email_query = st.text_input("Zoek op e-mailadres", placeholder="Geef (deel van) een e-mailadres op", key="admin_email_query")
    with col2:
        jaar_filter = st.number_input("Jaar", min_value=2020, max_value=2035, value=datetime.now().year - 1, step=1, key="admin_jaar_filter")
    with col3:
        st.markdown('<p style="font-size:14px;margin-bottom:5px;color:#707070">Zoeken</p>', unsafe_allow_html=True)
        zoek_geklikt = st.button("🔍 Zoek", type="primary", width='stretch')

    if "admin_results" not in st.session_state:
        st.session_state.admin_results  = []
    if "admin_selected" not in st.session_state:
        st.session_state.admin_selected = None

    if zoek_geklikt:
        with st.spinner("Zoeken..."):
            st.session_state.admin_results  = search_records(email_query, jaar_filter)
            st.session_state.admin_selected = None

    records = st.session_state.admin_results

    if records:
        st.write(f"**{len(records)} record(s) gevonden**")

        col_excel, _ = st.columns([1, 5])
        with col_excel:
            st.download_button("⬇️ Download Excel", data=export_records_excel(records),
                file_name=f"klar_export_{jaar_filter}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch')

        df_overzicht = pd.DataFrame([{
            "#": i + 1, "Email": r.get("email", "—"), "Jaar": r.get("jaar", ""),
            "Type": r.get("vragenlijst_type", ""),
            "Ingevuld op": (r.get("created_at") or "")[:10], "Taal": r.get("taal", ""),
        } for i, r in enumerate(records)])

        event = st.dataframe(df_overzicht, width='stretch', hide_index=True,
            selection_mode="single-row", on_select="rerun", key="admin_tabel",
            column_config={"Ingevuld op": st.column_config.TextColumn("Datum", width="small")})

        if event.selection.rows:
            st.session_state.admin_selected = event.selection.rows[0]

    elif zoek_geklikt:
        st.info("Geen records gevonden.")

    geselecteerd = st.session_state.admin_selected
    if geselecteerd is not None and geselecteerd < len(records):
        record     = records[geselecteerd]
        antwoorden = record.get("antwoorden", {})

        st.divider()
        st.subheader(f"📋 {record.get('email', '—')} — {record.get('jaar', '')}")
        st.caption(f"Taal: {record.get('taal', '')}  ·  Ingevuld: {(record.get('created_at') or '')[:10]}")
        st.write("")

        for stap_id, stap_info in STAPPEN_ADMIN.items():
            beantwoord = [q for q in stap_info["vragen"] if q in antwoorden]
            if not beantwoord:
                continue
            st.markdown(f"### {stap_info['titel']}")
            st.markdown("---")
            for q_id in beantwoord:
                label  = VRAAG_LABELS.get(q_id, q_id)
                waarde = antwoorden[q_id]
                col_l, col_r = st.columns([2, 3])
                with col_l:
                    st.markdown(f"**{label}**")
                with col_r:
                    if isinstance(waarde, bool):
                        st.markdown("✅ Ja" if waarde else "❌ Nee")
                    elif isinstance(waarde, list):
                        for item in waarde:
                            if isinstance(item, str) and item.count("/") >= 3:
                                url = get_signed_url(item)
                                naam = item.split("/")[-1]
                                st.markdown(f"📄 [{naam}]({url})" if url else f"📄 {naam}")
                            elif isinstance(item, dict):
                                st.markdown(" | ".join(f"**{k}:** {v}" for k, v in item.items()))
                            else:
                                st.markdown(f"- {item}")
                    elif isinstance(waarde, str) and waarde.count("/") >= 3:
                        url = get_signed_url(waarde)
                        naam = waarde.split("/")[-1]
                        st.markdown(f"📄 [{naam}]({url})" if url else f"📄 {naam}")
                    else:
                        st.markdown(str(waarde))
            st.write("")

    # ── Nextens synchronisatie ────────────────────────────────────
    if geselecteerd is not None and geselecteerd < len(records):
        record     = records[geselecteerd]
        antwoorden = record.get("antwoorden", {})
        record_id  = record.get("id")

        st.divider()
        st.subheader("🔗 Nextens synchronisatie")

        # Omgeving toggle
        omgeving = st.radio(
            "Omgeving:",
            ["Acceptatie", "Productie"],
            horizontal=True,
            key="nextens_omgeving"
        )

        nextens_id = record.get("nextens_id")
        bsn        = antwoorden.get("Question 7", "")

        if not bsn:
            st.warning("⚠️ Geen BSN gevonden in dit record — synchronisatie niet mogelijk.")
        else:
            klar_payload = bouw_persoon_payload(antwoorden)

            # Al gekoppeld
            if nextens_id:
                st.success(f"✅ Gekoppeld aan Nextens ID: `{nextens_id}`")
            else:
                st.info("Dit record is nog niet gekoppeld aan Nextens.")

            col_zoek, col_aan = st.columns(2)

            with col_zoek:
                if st.button("🔍 Zoek in Nextens op BSN", key="nextens_zoek"):
                    with st.spinner("Zoeken..."):
                        resultaat = zoek_persoon_op_bsn(bsn, omgeving)
                    st.session_state["_nextens_zoekresultaat"] = resultaat
                    st.session_state["_nextens_api_log"] = {"actie": "Zoek op BSN", "response": resultaat}

            with col_aan:
                if not nextens_id:
                    if st.button("➕ Aanmaken in Nextens", key="nextens_aanmaken"):
                        with st.spinner("Aanmaken..."):
                            resultaat = maak_persoon_aan(klar_payload, omgeving)
                        st.session_state["_nextens_api_log"] = {"actie": "Aanmaken persoon", "payload": klar_payload, "response": resultaat}
                        if resultaat["ok"]:
                            nieuw_id = resultaat["nextens_id"]
                            ok, fout = sla_nextens_id_op(record_id, nieuw_id)
                            if ok:
                                st.success(f"✅ Aangemaakt! Nextens ID: `{nieuw_id}`")
                                st.session_state["_nextens_zoekresultaat"] = None
                                st.rerun()
                            else:
                                st.error(f"Aangemaakt in Nextens maar opslaan in Supabase mislukt: {fout}")
                        else:
                            st.error(f"❌ Aanmaken mislukt: {resultaat['fout']}")

            # Zoekresultaat tonen
            zoekresultaat = st.session_state.get("_nextens_zoekresultaat")
            if zoekresultaat:
                if zoekresultaat["ok"]:
                    gevonden_data = zoekresultaat["data"]
                    gevonden_id   = gevonden_data.get("Id")
                    st.success(f"✅ Gevonden in Nextens — ID: `{gevonden_id}`")

                    # Koppelen als nog niet gekoppeld
                    if not nextens_id:
                        if st.button("🔗 Koppel dit Nextens ID aan record", key="nextens_koppel"):
                            ok, fout = sla_nextens_id_op(record_id, gevonden_id)
                            if ok:
                                st.success("Gekoppeld!")
                                st.session_state["_nextens_zoekresultaat"] = None
                                st.rerun()
                            else:
                                st.error(f"Koppelen mislukt: {fout}")

                    # Vergelijking tonen
                    verschillen = vergelijk_payload(klar_payload, gevonden_data)
                    if verschillen:
                        st.warning(f"⚠️ {len(verschillen)} verschil(len) gevonden tussen Klar en Nextens:")
                        st.dataframe(
                            verschillen,
                            width='stretch',
                            hide_index=True
                        )
                        huidig_nextens_id = nextens_id or gevonden_id
                        if st.button("✅ Update Nextens met Klar-gegevens", key="nextens_update"):
                            with st.spinner("Updaten..."):
                                update_res = update_persoon(huidig_nextens_id, klar_payload, omgeving)
                            st.session_state["_nextens_api_log"] = {"actie": "Update persoon", "payload": klar_payload, "response": update_res}
                            if update_res["ok"]:
                                st.success("✅ Nextens bijgewerkt!")
                                st.session_state["_nextens_zoekresultaat"] = None
                            else:
                                st.error(f"❌ Update mislukt: {update_res['fout']}")
                    else:
                        st.info("✅ Klar en Nextens zijn al gelijk — geen update nodig.")
                else:
                    st.error(f"❌ {zoekresultaat['fout']}")

            # API debug log
            api_log = st.session_state.get("_nextens_api_log")
            if api_log:
                with st.expander("🔎 API response (debug)", expanded=False):
                    st.write(f"**Actie:** {api_log['actie']}")
                    if "payload" in api_log:
                        st.write("**Verstuurde payload:**")
                        st.json(api_log["payload"])
                    st.write("**Response:**")
                    st.json(api_log["response"])

    # ── Google Places API test ─────────────────────────────────────
    st.divider()
    st.subheader("🔍 Google Places API test")
    api_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "NIET GEVONDEN")
    st.write("API key (eerste 10 tekens):", api_key[:10] if api_key != "NIET GEVONDEN" else api_key)
    test_input = st.text_input("Testadres:", key="debug_adres_input")

    if st.button("Test Autocomplete API", key="debug_api_btn"):
        import requests
        url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={test_input}&types=address&key={api_key}"
        try:
            r = requests.get(url, timeout=5)
            st.write("Status code:", r.status_code)
            st.write("Response:", r.json())
        except Exception as e:
            st.write("Fout:", str(e))

    if st.button("Test Places Details API", key="debug_details_btn"):
        import requests
        # Eerst een autocomplete doen om een place_id te krijgen
        url_ac = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={test_input}&types=address&key={api_key}"
        try:
            r_ac = requests.get(url_ac, timeout=5)
            predictions = r_ac.json().get("predictions", [])
            if not predictions:
                st.warning("Geen resultaten gevonden via Autocomplete — kan Details niet testen.")
            else:
                place_id = predictions[0]["place_id"]
                st.write("place_id:", place_id)
                url_det = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=address_components&key={api_key}"
                r_det = requests.get(url_det, timeout=5)
                st.write("Status code:", r_det.status_code)
                st.write("Response:", r_det.json())
        except Exception as e:
            st.write("Fout:", str(e))

    st.stop()  # Voorkom dat de vragenlijst ook geladen wordt

# ── Session state ─────────────────────────────────────────────────
if "taal" not in st.session_state:
    st.session_state.taal = None
if "current_step" not in st.session_state:
    st.session_state.current_step = "START"
if "antwoorden_log" not in st.session_state:
    st.session_state.antwoorden_log = {}
if "history" not in st.session_state:
    st.session_state.history = []
if "data_verstuurd" not in st.session_state:
    st.session_state.data_verstuurd = False
if "previous_loaded" not in st.session_state:
    st.session_state.previous_loaded = False
if "toon_melding" not in st.session_state:
    st.session_state.toon_melding = False
if "geladen_van_jaar" not in st.session_state:
    st.session_state.geladen_van_jaar = None

current_step = st.session_state.current_step

# ── Uploader-knoptekst (taalafhankelijk) ──────────────────────────
inject_uploader_label(st.session_state.taal or "NL")

# --- TAALSELECTIE SCHERM ---
if st.session_state.taal is None:
    st.title("Belastingaangifte Vragenlijst / Tax Return Questionnaire")
    st.write("Kies je gewenste taal / Please select your preferred language:")
    
    col_nl, col_en = st.columns(2)
    with col_nl:
        if st.button("🇳🇱 Nederlands", width='stretch'):
            st.session_state.taal = "NL"
            st.rerun()
    with col_en:
        if st.button("🇬🇧 English", width='stretch'):
            st.session_state.taal = "EN"
            st.rerun()
            
    st.stop() # Zorgt ervoor dat de rest van de app nog niet laadt

JAAR = datetime.now().year - 1


STAPPEN_TRANSLATION = {
    "NL": {
        "START": "Welkom",
        "Stap 1": "Privacy verklaring",
        "Stap 2": "Persoonlijke gegevens",
        "Stap 3": "Fiscaal partner",
        "Stap 4": "Persoonlijke gegevens van fiscaal partner",
        "Stap 5": "Thuiswonende kinderen",
        "Stap 6": "Waar je woonde",
        "Stap 7": "Inkomen uit loondienst",
        "Stap 7a": "Inkomen uit loondienst van jouw partner",
        "Stap 7b": "Inkomen uit uitkering / pensioen / lijfrente",
        "Stap 7c": "Inkomen uit uitkering / pensioen / lijfrente van jouw partner",
        "Stap 8": "Inkomen uit ondernemerschap",
        "Stap 8a": "Inkomen uit ondernemerschap van jouw partner",
        "Stap 9": "Eigen woonverblijf",
        "Stap 10": "Tweede eigen woonverblijf",
        "Stap 11": "Hypotheek",
        "Stap 12": "Aanmerkelijk belang",
        "Stap 13": "Sparen",
        "Stap 14": "Tweede eigen woonverblijf (Belegging)",
        "Stap 15": "Overig",
        "Stap 16": "Buitenlands vermogen, beleggingen, schulden en inkomen",
        "Stap 17": "Aftrekposten",
        "Stap 18": "Afronding"
    },
    "EN": {
        "START": "Welcome",
        "Stap 1": "Privacy statement",
        "Stap 2": "Personal information",
        "Stap 3": "Tax partner",
        "Stap 4": "Personal information of tax partner",
        "Stap 5": "Children living at home",
        "Stap 6": "Where you lived",
        "Stap 7": "Income from employment",
        "Stap 7a": "Partner's income from employment",
        "Stap 7b": "Income from benefits / pension / annuity",
        "Stap 7c": "Partner's income from benefits / pension / annuity",
        "Stap 8": "Income from entrepreneurship",
        "Stap 8a": "Partner's income from entrepreneurship",
        "Stap 9": "Primary residence",
        "Stap 10": "Second residence",
        "Stap 11": "Mortgage",
        "Stap 12": "Substantial interest",
        "Stap 13": "Savings",
        "Stap 14": "Second residence (Investment)",
        "Stap 15": "Other",
        "Stap 16": "Foreign assets, investments, debts and income",
        "Stap 17": "Deductions",
        "Stap 18": "Finalisation"
    }
}
UI_TRANSLATION = {
    "NL": {
        "title": "Belastingaangifte Vragenlijst",
        "subtitle": "Vul de onderstaande vragen zo nauwkeurig mogelijk in.",
        "caption": "Actieve stap",
        "choice_placeholder": "Maak een keuze:",
        "int_placeholder": "Voer een cijfer in:",
        "file_placeholder": "Kies een bestand...",
        "prev_btn": "Vorige",
        "next_btn": "Volgende",
        "submit_btn": "Antwoorden versturen",
        "warning_empty": "Vul een geldig antwoord in voordat je verder gaat.",
        "success": "🎉 Bedankt voor het invullen van de vragenlijst!",
        "success_sub": "Jouw antwoorden zijn veilig opgeslagen.",
        "restart_btn": "Einde, log uit!",
        "error_date": "Ongeldig formaat. Gebruik DD-MM-YYYY.",
        "error_privacy": "⚠️ Je dient akkoord te gaan met de privacyverklaring om verder te kunnen gaan.",
        "error_file": "Eerder geüpload bestand",
        "error_bsn": "Een BSN bestaat uit exact 9 cijfers.",
        "error_email": "Voer een geldig e-mailadres in.",
        "error_phone": "Voer een geldig telefoonnummer in (minimaal 10 cijfers).",
        "error_kvk": "Een KvK-nummer bestaat uit exact 9 cijfers.",
        "table_col1" : "Naam",
        "table_col2" : "Bedrag/Aantal",
        "string_field": "Jouw antwoord:",
        "bsn_label": "Jouw 9-cijferige BSN:",
        "upload_messsage": "Kies een bestand...",
        "int_message": "Voer een cijfer in:",
        "saving_db": "Gegevens opslaan in database...",
        "save_success": "✅ Gegevens succesvol opgeslagen!",
        "save_failed": "❌ Opslaan mislukt: ",
        "add_row_btn": "Voeg een regel toe"
    },
    "EN": {
        "title": "Tax Return Questionnaire",
        "subtitle": "Please fill out the questions below as accurately as possible.",
        "caption": "Active step",
        "choice_placeholder": "Make a choice:",
        "int_placeholder": "Enter a number:",
        "file_placeholder": "Choose a file...",
        "prev_btn": "Previous",
        "next_btn": "Next",
        "submit_btn": "Submit answers",
        "warning_empty": "Please provide a valid answer before proceeding.",
        "success": "🎉 Thank you for completing the questionnaire!",
        "success_sub": "Your answers have been securely saved.",
        "restart_btn": "Done, log out!",
        "error_date": "Invalid format. Use DD-MM-YYYY.",
        "error_privacy": "⚠️ You must agree to the privacy statement to proceed.",
        "error_file": "File has already been uploaded",
        "error_bsn": "A BSN must consist of exactly 9 digits.",
        "error_email": "Please enter a valid email address.",
        "error_phone": "Please enter a valid phone number (at least 10 digits).",
        "error_kvk": "A KvK number must consist of exactly 9 digits.",
        "table_col1" : "Name",
        "table_col2" : "Amount/Quantity",
        "string_field": "Your answer:",
        "bsn_label": "Your 9-digit BSN:",
        "upload_messsage": "Select a file...",
        "int_message": "Enter a number:",
        "saving_db": "Saving data to database...",
        "save_success": "✅ Data successfully saved!",
        "save_failed": "❌ Saving failed: ",
        "add_row_btn": "Add a row"
    }
}
# Uitleg bij uploadvelden waar meerdere bestanden tegelijk kunnen
_UPLOAD_TIP_NL = "Je kunt meerdere bestanden tegelijk selecteren door Ctrl ingedrukt te houden (Windows) of ⌘ Cmd (Mac) terwijl je de bestanden aanklikt. Of druk op het plus-teken dat verschijnt zodra je het eerste bestand hebt geüpload."
_UPLOAD_TIP_EN = "You can select multiple files at once by holding Ctrl (Windows) or ⌘ Cmd (Mac) while clicking the files. Or press the plus sign that appears once you have uploaded the first file."
QUESTIONS_TRANSLATION = {
    "NL": {
        "Q1_text": "Ik ga akkoord met verwerking van mijn gegevens t.b.v. de voorbereiding en indiening van mijn aangifte inkomstenbelasting door Klår Finance.",
        "Q1_toelicht": "Voor privacyverklaring zie: https://klarfinance.nl/privacy-policy/",
        "Q2_text": "Voornaam",
        "Q3_text": "Achternaam",
        "Q3b_text": "Tussenvoegsels",
        "Q4_text": "Telefoonnummer",
        "Q5_text": "E-mailadres",
        "Q6_text": "Wat is je geboortedatum?",
        "Q7_text": "Wat is jouw burgerservicenummer (BSN)?",
        "Q7b_text": "Wat is jouw nationaliteit?",
        "Q7c_text": "Wat is jouw adres?",
        "Q8_text": "Ben je getrouwd of zit je in een geregistreerd partnerschap?",
        "Q9_text": "Wat is jouw trouwdatum of datum van geregistreerd partnerschap?",
        "Q10_text": f"Heb je in {JAAR} een fiscaal partner?",
        "Q10_toelicht": f"Je bent fiscale partners als je aan één van de volgende voorwaarden voldoet:\n- je bent getrouwd of geregistreerd partner;\n- je woont samen en hebt samen een kind;\n- Twijfel je? Kies 'Ja' als jullie ook in {JAAR - 1} als fiscale partners aangifte deden.",
        "Q11_text": "Wat is de voornaam van jouw partner?",
        "Q11b_text": "Tussenvoegsels partner",
        "Q12_text": "Wat is de achternaam van jouw partner?",
        "Q13_text": "Wat is het telefoonnummer van jouw partner?",
        "Q14_text": "Wat is het e-mailadres van jouw partner?",
        "Q15_text": "Wat is het burgerservicenummer (BSN) van jouw partner?",
        "Q15b_text": "Wat is de nationaliteit van jouw partner?",
        "Q16_text": f"Had je in {JAAR} één of meerdere thuiswonende kinderen?",
        "Q17_text": "Wat is de naam van jouw jongste nog thuiswonende kind?",
        "Q18_text": "Wat is de geboortedatum van jouw jongste nog thuiswonende kind?",
        "Q19_text": f"Waar woonde je in {JAAR}?",
        "Q19_opt1": f"Heel {JAAR} in Nederland",
        "Q19_opt2": f"Een gedeelte van {JAAR} in Nederland en een gedeelte in het buitenland",
        "Q19_opt3": f"Heel {JAAR} in het buitenland",
        "Q20_text": f"Was er in {JAAR} sprake van immigratie (naar Nederland) of emigratie (uit Nederland)?",
        "Q20_opt1": "Immigratie",
        "Q20_opt2": "Emigratie",
        "Q21_text": "Wat is de datum van jouw fysieke aankomst in Nederland?",
        "Q22_text": "Wat is de datum van jouw registratie in Nederland?",
        "Q22_toelicht": "Dit is de datum waarop je je officieel hebt ingeschreven bij de gemeente in Nederland.",
        "Q23_text": "Van welk land was je inwoner voordat je naar Nederland kwam?",
        "Q24_text": "Wat is de datum van jouw fysieke vertrek uit Nederland?",
        "Q26_text": "Wat is de datum van jouw uitschrijving uit Nederland?",
        "Q26_toelicht": "Dit is de datum waarop je je officieel hebt uitgeschreven bij de gemeente in Nederland.",
        "Q27_text": "Wat is het land van bestemming?",
        "Q28_text": f"Had je in {JAAR} inkomsten uit loondienst?",
        "Q29_text": f"Bij hoeveel verschillende werkgevers had je in {JAAR} een dienstverband?",
        "Q30_text": f"Upload de jaaropgave van jouw werkgever(s) voor {JAAR}.",
        "Q31_text": f"Was in {JAAR} de 30%-regeling van toepassing?",
        "Q31_toelicht": "De 30%-regeling is een fiscale regeling voor kennismigranten.",
        "Q32_text": "Upload de beschikking 30%-regeling.",
        # Stap 7b — uitkering / pensioen / lijfrente
        "Q32b_text": f"Had je in {JAAR} inkomsten uit uitkering / pensioen / lijfrente?",
        "Q32c_text": f"Upload de jaaropgaven {JAAR} van al deze inkomstenbronnen.",
        "Q32c_toelicht": f"Upload hier de jaaropgaven {JAAR} van al jouw uitkeringen, pensioenen en lijfrentes. {_UPLOAD_TIP_NL}",
        "Q33_text": f"Was je in {JAAR} zelfstandig ondernemer in een eenmanszaak, vof of maatschap?",
        "Q33_toelicht": "Heb je een BV, beantwoord deze vraag dan met 'Nee'.",
        "Q34_text": "Wat is de rechtsvorm van jouw onderneming?",
        "Q34_opts": ["Eenmanszaak", "VOF", "Maatschap", "Overige rechtsvorm"],
        "Q35_text": "Wat is het KvK-nummer van jouw onderneming?",
        "Q36_text": "In welk boekhoudprogramma houd je de administratie bij?",
        "Q37_text": f"Upload de balans en de winst- en verliesrekening {JAAR}.",
        "Q37_toelicht": _UPLOAD_TIP_NL,
        "Q37b_text": f"Upload de ingediende aangifte IB {JAAR - 1} inclusief balans en winst- en verliesrekening.",
        "Q37b_toelicht": "Let op: dit is enkel van toepassing indien deze niet door Klår Finance is verzorgd.",
        "Q38_text": f"Heb je in {JAAR} méér dan 1.225 uur besteed aan jouw onderneming?",
        "Q38_opts": ["Ja", "Nee", "Ik weet het niet zeker"],
        # Stap 7a — loondienst partner
        "Q28p_text": f"Had jouw partner in {JAAR} inkomsten uit loondienst?",
        "Q29p_text": f"Bij hoeveel verschillende werkgevers had jouw partner in {JAAR} een dienstverband?",
        "Q30p_text": f"Upload de jaaropgave van de werkgever(s) van jouw partner voor {JAAR}.",
        "Q31p_text": f"Was in {JAAR} de 30%-regeling van toepassing op jouw partner?",
        "Q31p_toelicht": "De 30%-regeling is een fiscale regeling voor kennismigranten.",
        "Q32p_text": "Upload de beschikking 30%-regeling van jouw partner.",
        # Stap 7c — uitkering / pensioen / lijfrente partner
        "Q32bp_text": f"Had jouw partner in {JAAR} inkomsten uit uitkering / pensioen / lijfrente?",
        "Q32cp_text": f"Upload de jaaropgaven {JAAR} van al deze inkomstenbronnen van jouw partner.",
        "Q32cp_toelicht": f"Upload hier de jaaropgaven {JAAR} van alle uitkeringen, pensioenen en lijfrentes van jouw partner. {_UPLOAD_TIP_NL}",
        # Stap 8a — ondernemerschap partner
        "Q33p_text": f"Was jouw partner in {JAAR} zelfstandig ondernemer in een eenmanszaak, vof of maatschap?",
        "Q33p_toelicht": "Heeft jouw partner een BV, beantwoord deze vraag dan met 'Nee'.",
        "Q34p_text": "Wat is de rechtsvorm van de onderneming van jouw partner?",
        "Q35p_text": "Wat is het KvK-nummer van de onderneming van jouw partner?",
        "Q36p_text": "In welk boekhoudprogramma houdt jouw partner de administratie bij?",
        "Q37p_text": f"Upload de balans en de winst- en verliesrekening {JAAR} van jouw partner.",
        "Q37bp_text": f"Upload de ingediende aangifte IB {JAAR - 1} van jouw partner inclusief balans en winst- en verliesrekening.",
        "Q38p_text": f"Heeft jouw partner in {JAAR} méér dan 1.225 uur besteed aan zijn/haar onderneming?",
        # Partner melding
        "partner_melding": "⚠️ Let op! Onderstaande vragen betreffen zowel jou als jouw partner.",
        "Q39_text": f"Had je in {JAAR} een eigen woning (hoofdverblijf)?",
        "Q40_text": "Is deze woning alleen van jou?",
        "Q40_opts": ["Ja, ik ben de enige eigenaar", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)", "Nee, er is nog een andere eigenaar (niet mijn partner)."],
        "Q41_text": "Wie is er nog meer eigenaar van jouw eigen woning?",
        "Q42_text": "Wat is het adres van jouw eigen woning?",
        "Q43_text": "Heb je een hypotheek op deze eigen woning?",
        "Q44_text": f"Upload de jaaropgave van jouw hypotheekverstrekker voor {JAAR}.",
        "Q44b_text": "Betaal je jaarlijks erfpacht voor deze woning?",
        "Q44c_text": f"Upload het document van de erfpachtcanon {JAAR}.",
        "Q45_text": f"Heb je in {JAAR} deze woning gekocht of verkocht?",
        "Q45_opts": ["Ja, gekocht", "Ja, verkocht", "Nee"],
        "Q46_text": "Wat is de datum van de aankoop van jouw woning?",
        "Q46b_text": "Vanaf welke datum woon je in deze woning?",
        "Q47_text": "Upload de notarisafrekening van de aankoop.",
        "Q47b_text": "Upload de taxatiefactuur inzake de aankoop van de woning.",
        "Q48_text": "Wat is de datum van de verkoop van jouw woning?",
        "Q48b_text": "Vanaf welke datum woon je niet meer in deze woning?",
        "Q49_text": "Upload de notarisafrekening van de verkoop.",
        "Q49b_text": "Upload de taxatiefactuur inzake de verkoop van de woning.",
        "taxatie_toelicht": "Alleen van toepassing als er een taxatie is uitgevoerd.",
        "Q50_text": f"Had je in {JAAR} nóg een eigen woning (hoofdverblijf)?",
        "Q51_text": "Is deze woning alleen van jou?",
        "Q51_opts": ["Ja, ik ben de enige eigenaar", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)", "Nee, er is nog een andere eigenaar (niet mijn partner)."],
        "Q52_text": "Wie is er nog meer eigenaar?",
        "Q53_text": "Wat is het adres van deze woning?",
        "Q54_text": "Heb je een hypotheek op deze eigen woning?",
        "Q55_text": f"Upload de jaaropgave van jouw hypotheekverstrekker voor {JAAR}.",
        "Q56_text": f"Heb je in {JAAR} deze woning gekocht of verkocht?",
        "Q56_opts": ["Ja, gekocht", "Ja, verkocht", "Nee"],
        "Q57_text": "Wat is de datum van de aankoop?",
        "Q57b_text": "Vanaf welke datum woon je in deze woning?",
        "Q58_text": "Upload de notarisafrekening van de aankoop.",
        "Q59_text": f"Upload de factuur van de taxatie van de nieuwe woning voor {JAAR}.",
        "Q59b_text": "Wat is de datum van verkoop?",
        "Q60_text": "Vanaf welke datum woon je niet meer in deze woning?",
        "Q61_text": "Upload de notarisafrekening van de verkoop.",
        "Q62_text": "Upload de factuur van de taxatie van de oude woning.",
        "Q63_text": f"Heb je in {JAAR} jouw hypotheek overgesloten?",
        "Q64_text": "Upload de notarisafrekening van de oversluiting.",
        "Q65_text": f"Had je in {JAAR} een aanmerkelijk belang in een BV/NV?",
        "Q65_toelichting": "Je hebt een aanmerkelijk belang in een bv of nv wanneer je direct of indirect minimaal 5% bezit van het geplaatste aandelenkapitaal.",
        "Q66_text": f"Wat is de naam van deze BV/NV en hoeveel aandelen bezat je op 1-1-{JAAR}?",
        "Q66_col1": "Naam",
        "Q66_col2": "Bedrag/Aantal",
        "Q67_text": f"Heb je in {JAAR} aandelen in deze BV/NV verkocht of gekocht?",
        "Q68_text": "Hoeveel aandelen heb je gekocht/verkocht?",
        "Q68_col2": "Gekocht/verkocht",
        "Q68_toelichting": f"Voer indien je in {JAAR} aandelen gekocht hebt een positief getal in achter de betreffende entiteit en bij verkoop een negatief getal. Voer 0 in wanneer er geen mutaties waren.",
        "Q68b_text": "Wat was de aankoopprijs/verkoopprijs per aandeel?",
        "Q68b_col2": "Prijs per aandeel (€)",
        "Q68b_toelichting": "Voer achter de betreffende entiteit de aankoop- of verkoopprijs per aandeel in. Voer 0 in wanneer er geen mutaties waren.",
        "Q69_text": f"Heb je in {JAAR} dividend ontvangen van deze BV/NV?",
        "Q70_text": f"Hoeveel was het bruto ontvangen dividend in {JAAR}?",
        "Q70_col2": "Dividend (€)",
        "Q70_toelichting": "Voer achter de betreffende entiteit het ontvangen dividend in en voer 0 in wanneer er geen dividend is uitgekeerd.",
        "Q70b_text": "Is er door de BV/NV al dividendbelasting afgedragen?",
        "Q70c_text": "Hoeveel dividendbelasting is er afgedragen?",
        "Q70c_col2": "Dividendbelasting (€)",
        "Q70c_toelichting": "Voer achter de betreffende entiteit de afgedragen dividendbelasting in en voer 0 in wanneer er geen dividendbelasting is afgedragen.",
        "Q71_text": f"Had je (en/of jouw fiscaal partner) in {JAAR} Nederlandse bankrekeningen en/of Nederlandse beleggingen?",
        "Q72_text": f"Upload de jaaroverzichten {JAAR} van alle Nederlandse rekeningen.",
        "Q72_toelicht": f"Upload hier de jaaroverzichten van alle Nederlandse bankrekeningen en beleggingsrekeningen van jou (en jouw fiscaal partner). Bankrekeningen/beleggingen op naam van een minderjarig kind vallen hier ook onder. {_UPLOAD_TIP_NL}",
        "Q73_text": f"Bezat je (en/of jouw fiscaal partner) in {JAAR} crypto en/of vordering(en) zoals een lening aan derden?",
        "Q73b_text": f"Vermeld hieronder de omschrijving en waarde per bezitting per 1-1-{JAAR} en 31-12-{JAAR}.",
        "Q73b_col1": "Omschrijving",
        "Q73b_col2": f"Waarde 1-1-{JAAR} (€)",
        "Q73b_col3": f"Waarde 31-12-{JAAR} (€)",
        "Q74_text": f"Had je (en/of jouw fiscaal partner) in {JAAR} overig onroerend goed in Nederland (niet de eigen woning)?",
        "Q75_text": "Wat is het adres van dit onroerend goed?",
        "Q76_text": f"Werd dit overig onroerend goed in {JAAR} verhuurd?",
        "Q76_opts": ["Ja, vaste verhuur", "Ja, vakantieverhuur", "Nee"],
        "Q77_text": "Is het onroerend goed verhuurd aan een familielid?",
        "Q79_text": "Betaal je jaarlijks erfpacht?",
        "Q80_text": f"Wat was de erfpachtcanon in {JAAR}?",
        "Q81_text": "Kan dit onroerend goed afzonderlijk worden verkocht?",
        "Q81b_text": "Rust er een hypotheek of andere schuld op dit onroerend goed?",
        "Q81c_text": f"Upload de jaaropgave {JAAR} van deze hypotheek/schuld.",
        "Q82_text": f"Had je (en/of jouw fiscaal partner) Nederlandse schulden in {JAAR}?",
        "Q83_text": f"Upload de jaaropgaven {JAAR} van alle Nederlandse schulden.",
        "Q83_toelicht": f"Upload hier de jaaropgaven van alle Nederlandse schulden van jou (en/of jouw fiscaal partner), zoals een studieschuld, persoonlijke lening of krediet. {_UPLOAD_TIP_NL}",
        "Q84_text": f"Had je (en/of jouw fiscaal partner) in {JAAR} buitenlandse bankrekeningen en/of buitenlandse beleggingen?",
        "Q85_text": f"Upload de jaaroverzichten {JAAR} van alle buitenlandse rekeningen.",
        "Q85_toelicht": f"Upload hier de jaaroverzichten van alle buitenlandse bankrekeningen en beleggingsrekeningen van jou (en/of jouw fiscaal partner). {_UPLOAD_TIP_NL}",
        # Stap 16 — buitenlands onroerend goed (herhaalt per object)
        "Q86_text": f"Had je (en/of jouw fiscaal partner) in {JAAR} onroerend goed in het buitenland?",
        "Q86_meer_text": f"Had je (en/of jouw fiscaal partner) in {JAAR} nog meer onroerend goed in het buitenland?",
        "og_object": " (onroerend goed {k})",
        "Q87_text": "Wat is het adres?",
        "Q88_text": f"Wat was de waarde op 1-1-{JAAR}?",
        "Q88b_text": "Is dit onroerend goed volledig eigendom van jou (en/of jouw fiscaal partner)?",
        "Q88c_text": "Voor hoeveel procent ben je (en/of jouw fiscaal partner) eigenaar?",
        "Q86b_text": "Rust er een hypotheek of andere schuld op dit onroerend goed?",
        "Q86c_text": f"Upload de jaaropgave {JAAR} van deze hypotheek/schuld.",
        "Q89_text": f"Is dit onroerend goed gekocht of verkocht in {JAAR}?",
        "Q89b_text": "Op welke datum heeft de aankoop/verkoop plaatsgevonden?",
        "Q89c_text": "Tegen welk bedrag is het onroerend goed gekocht/verkocht?",
        "Q90_text": f"Had je (en/of jouw fiscaal partner) buitenlandse schulden in {JAAR}?",
        "Q91_text": f"Omschrijf de buitenlandse schulden en vermeld de hoogte op 1-1-{JAAR} en 31-12-{JAAR}.",
        "Q91_col2": f"Hoogte 1-1-{JAAR} (€)",
        "Q91_col3": f"Hoogte 31-12-{JAAR} (€)",
        "Q92_text": f"Had je (en/of jouw fiscaal partner) buitenlands inkomen in {JAAR}?",
        "Q93_text": "Wat was de bron?",
        "Q93_opts": ["Inkomen uit loondienst", "Inkomen als zelfstandige", "Pensioen", "Anders"],
        "Q94_text": "Is er belasting ingehouden?",
        "Q94_opts": ["Ja", "Nee", "Weet ik niet zeker"],
        "Q95_text": "Upload hier het bewijs van alle buitenlandse inkomsten van jou (en/of jouw fiscaal partner).",
        "Q95_toelicht": f"Bijvoorbeeld een jaaropgave of salarisstrook. {_UPLOAD_TIP_NL}",
        "Q96_text": f"Heb je (en/of jouw fiscaal partner) meer dan EUR 60 gedoneerd aan goede doelen in {JAAR}?",
        "Q97_text": "Vermeld per goed doel het bedrag.",
        "Q98_text": f"Heb je (en/of jouw fiscaal partner) in {JAAR} buitengewone zorgkosten betaald?",
        "Q99_text": "Vermeld per soort zorgkosten het bedrag.",
        "Q100_text": "Volg je (en/of jouw fiscaal partner) een dieet op doktersvoorschrift?",
        "Q101_text": "Om welk dieet gaat het?",
        "Q102_text": f"Ontving je (en/of jouw fiscaal partner) in {JAAR} een voorlopige aanslag?",
        "Q103_text": "Upload kopie voorlopige aanslag.",
        "Q104_text": "Wil je nog aanvullende documenten uploaden?",
        "Q105_text": "Upload hier aanvullende documenten.",
        "Q106_text": "Heb je nog opmerkingen of vragen?",
        "Q107_text": "Vermeld jouw opmerkingen.",
        "yes": "Ja",
        "no": "Nee"
    },
    "EN": {
        "Q1_text": "I agree to the processing of my data for the preparation and submission of my income tax return by Klår Finance.",
        "Q1_toelicht": "For our privacy policy see: https://klarfinance.nl/privacy-policy/",
        "Q2_text": "First name",
        "Q3_text": "Last name",
        "Q3b_text": "Middle name / prefix",
        "Q4_text": "Phone number",
        "Q5_text": "Email address",
        "Q6_text": "What is your date of birth?",
        "Q7_text": "What is your citizen service number (BSN)?",
        "Q7b_text": "What is your nationality?",
        "Q7c_text": "What is your address?",
        "Q8_text": "Are you married or in a registered partnership?",
        "Q9_text": "What is the date of your marriage or registered partnership?",
        "Q10_text": f"Did you have a tax partner in {JAAR}?",
        "Q10_toelicht": f"You are tax partners if you meet at least one of the following conditions:\n- you are married or registered partners;\n- you live together and have a child together;\n- In doubt? Choose 'Yes' if you also filed as tax partners in {JAAR - 1}.",
        "Q11_text": "What is your partner's first name?",
        "Q11b_text": "Partner's middle name / prefix",
        "Q12_text": "What is your partner's last name?",
        "Q13_text": "What is your partner's phone number?",
        "Q14_text": "What is your partner's email address?",
        "Q15_text": "What is your partner's citizen service number (BSN)?",
        "Q15b_text": "What is your partner's nationality?",
        "Q16_text": f"Did you have one or more children living at home in {JAAR}?",
        "Q17_text": "What is the name of your youngest child living at home?",
        "Q18_text": "What is the date of birth of your youngest child living at home?",
        "Q19_text": f"Where did you live in {JAAR}?",
        "Q19_opt1": f"The entire year of {JAAR} in the Netherlands",
        "Q19_opt2": f"Part of {JAAR} in the Netherlands and part abroad",
        "Q19_opt3": f"The entire year of {JAAR} abroad",
        "Q20_text": f"Was there any immigration (to the Netherlands) or emigration (from the Netherlands) in {JAAR}?",
        "Q20_opt1": "Immigration",
        "Q20_opt2": "Emigration",
        "Q21_text": "What is the date of your physical arrival in the Netherlands?",
        "Q22_text": "What is the date of your registration in the Netherlands?",
        "Q22_toelicht": "This is the date you officially registered with the municipality in the Netherlands.",
        "Q23_text": "Which country were you a resident of before you came to the Netherlands?",
        "Q24_text": "What is the date of your physical departure from the Netherlands?",
        "Q26_text": "What is the date of your deregistration from the Netherlands?",
        "Q26_toelicht": "This is the date you officially deregistered from the municipality in the Netherlands.",
        "Q27_text": "What is the country of destination?",
        "Q28_text": f"Did you have income from employment in {JAAR}?",
        "Q29_text": f"With how many different employers were you employed in {JAAR}?",
        "Q30_text": f"Upload the annual tax statement (jaaropgave) from your employer(s) for {JAAR}.",
        "Q31_text": f"Was the 30% ruling applicable in {JAAR}?",
        "Q31_toelicht": "The 30% ruling is a tax advantage for highly skilled migrants.",
        "Q32_text": "Upload the 30% ruling decision letter.",
        # Stap 7b — benefits / pension / annuity
        "Q32b_text": f"Did you have income from benefits / pension / annuity in {JAAR}?",
        "Q32c_text": f"Upload the {JAAR} annual statements of all these income sources.",
        "Q32c_toelicht": f"Upload the {JAAR} annual statements of all your benefits, pensions and annuities. {_UPLOAD_TIP_EN}",
        "Q33_text": f"Were you self-employed in a sole proprietorship, VOF, or partnership in {JAAR}?",
        "Q33_toelicht": "If you own a BV, please answer 'No'.",
        "Q34_text": "What is the legal form of your business?",
        "Q34_opts": ["Sole proprietorship (Eenmanszaak)", "VOF", "Partnership (Maatschap)", "Other legal form"],
        "Q35_text": "What is the Chamber of Commerce (KvK) number of your business?",
        "Q36_text": "Which accounting software do you use?",
        "Q37_text": f"Upload the balance sheet and the profit and loss statement for {JAAR}.",
        "Q37_toelicht": _UPLOAD_TIP_EN,
        "Q37b_text": f"Upload the filed {JAAR - 1} income tax return, including balance sheet and profit and loss statement.",
        "Q37b_toelicht": "Note: this only applies if the return was not prepared by Klår Finance.",
        "Q38_text": f"Did you spend more than 1,225 hours on your business in {JAAR}?",
        "Q38_opts": ["Yes", "No", "I am not entirely sure"],
        # Stap 7a — loondienst partner
        "Q28p_text": f"Did your partner have income from employment in {JAAR}?",
        "Q29p_text": f"With how many different employers was your partner employed in {JAAR}?",
        "Q30p_text": f"Upload the annual tax statement (jaaropgave) from your partner's employer(s) for {JAAR}.",
        "Q31p_text": f"Was the 30% ruling applicable to your partner in {JAAR}?",
        "Q31p_toelicht": "The 30% ruling is a tax advantage for highly skilled migrants.",
        "Q32p_text": "Upload the 30% ruling decision letter of your partner.",
        # Stap 7c — benefits / pension / annuity partner
        "Q32bp_text": f"Did your partner have income from benefits / pension / annuity in {JAAR}?",
        "Q32cp_text": f"Upload the {JAAR} annual statements of all these income sources of your partner.",
        "Q32cp_toelicht": f"Upload the {JAAR} annual statements of all benefits, pensions and annuities of your partner. {_UPLOAD_TIP_EN}",
        # Stap 8a — ondernemerschap partner
        "Q33p_text": f"Was your partner self-employed in a sole proprietorship, VOF, or partnership in {JAAR}?",
        "Q33p_toelicht": "If your partner owns a BV, please answer 'No'.",
        "Q34p_text": "What is the legal form of your partner's business?",
        "Q35p_text": "What is the Chamber of Commerce (KvK) number of your partner's business?",
        "Q36p_text": "Which accounting software does your partner use?",
        "Q37p_text": f"Upload the balance sheet and the profit and loss statement of your partner for {JAAR}.",
        "Q37bp_text": f"Upload your partner's filed {JAAR - 1} income tax return, including balance sheet and profit and loss statement.",
        "Q38p_text": f"Did your partner spend more than 1,225 hours on his/her business in {JAAR}?",
        # Partner melding
        "partner_melding": "⚠️ Note: The questions below apply to both you and your partner.",
        "Q39_text": f"Did you own a home (primary residence) in {JAAR}?",
        "Q40_text": "Is this property solely owned by you?",
        "Q40_opts": ["Yes, I am the sole owner", "No, the property is jointly owned by me and my tax partner (50%-50%)", "No, there is another owner (not my partner)."],
        "Q41_text": "Who else owns your primary residence?",
        "Q42_text": "What is the address of your primary residence?",
        "Q43_text": "Do you have a mortgage on this primary residence?",
        "Q44_text": f"Upload the annual mortgage statement from your lender for {JAAR}.",
        "Q44b_text": "Do you pay ground rent (erfpacht) annually for this property?",
        "Q44c_text": f"Upload the ground rent (erfpachtcanon) document for {JAAR}.",
        "Q45_text": f"Did you buy or sell this property in {JAAR}?",
        "Q45_opts": ["Yes, bought", "Yes, sold", "No"],
        "Q46_text": "What is the date of purchase of your home?",
        "Q46b_text": "As of what date do you live in this property?",
        "Q47_text": "Upload the notary settlement statement of the purchase.",
        "Q47b_text": "Upload the valuation/appraisal invoice for the purchase of the property.",
        "Q48_text": "What is the date of sale of your home?",
        "Q48b_text": "As of what date did you stop living in this property?",
        "Q49_text": "Upload the notary settlement statement of the sale.",
        "Q49b_text": "Upload the valuation/appraisal invoice for the sale of the property.",
        "taxatie_toelicht": "Only applicable if a valuation was carried out.",
        "Q50_text": f"Did you own another home (primary residence) in {JAAR}?",
        "Q51_text": "Is this property solely owned by you?",
        "Q51_opts": ["Yes, I am the sole owner", "No, the property is jointly owned by me and my tax partner (50%-50%)", "No, there is another owner (not my partner)."],
        "Q52_text": "Who else is an owner?",
        "Q53_text": "What is the address of this property?",
        "Q54_text": "Do you have a mortgage on this property?",
        "Q55_text": f"Upload the annual mortgage statement from your lender for {JAAR}.",
        "Q56_text": f"Did you buy or sell this property in {JAAR}?",
        "Q56_opts": ["Yes, bought", "Yes, sold", "No"],
        "Q57_text": "What is the date of purchase?",
        "Q57b_text": "As of what date do you live in this property?",
        "Q58_text": "Upload the notary settlement statement of the purchase.",
        "Q59_text": f"Upload the valuation/appraisal invoice of the new property for {JAAR}.",
        "Q59b_text": "What is the date of sale?",
        "Q60_text": "As of what date did you stop living in this property?",
        "Q61_text": "Upload the notary settlement statement of the sale.",
        "Q62_text": "Upload the valuation/appraisal invoice of the old property.",
        "Q63_text": f"Did you refinance your mortgage in {JAAR}?",
        "Q64_text": "Upload the notary settlement statement of the refinancing.",
        "Q65_text": f"Did you hold a substantial interest (aanmerkelijk belang) in a BV/NV in {JAAR}?",
        "Q65_toelichting": "You hold a substantial interest (aanmerkelijk belang) in a BV or NV when you directly or indirectly own at least 5% of the issued share capital.",
        "Q66_text": f"What is the name of this BV/NV and how many shares did you hold on 1-1-{JAAR}?",
        "Q66_col1": "Name",
        "Q66_col2": "Amount/Quantity",
        "Q67_text": f"Did you buy or sell shares in this BV/NV in {JAAR}?",
        "Q68_text": "How many shares did you buy/sell?",
        "Q68_col2": "Bought/sold",
        "Q68_toelichting": f"For shares bought in {JAAR}, enter a positive number next to the relevant entity; for shares sold, enter a negative number. Enter 0 if there were no changes.",
        "Q68b_text": "What was the purchase/sale price per share?",
        "Q68b_col2": "Price per share (€)",
        "Q68b_toelichting": "Enter the purchase or sale price per share next to the relevant entity. Enter 0 if there were no changes.",
        "Q69_text": f"Did you receive dividends from this BV/NV in {JAAR}?",
        "Q70_text": f"What was the gross dividend received in {JAAR}?",
        "Q70_col2": "Dividend (€)",
        "Q70_toelichting": "Enter the dividend received for each relevant entity, and enter 0 if no dividend was paid out.",
        "Q70b_text": "Has the BV/NV already paid dividend tax?",
        "Q70c_text": "How much dividend tax was paid?",
        "Q70c_col2": "Dividend tax (€)",
        "Q70c_toelichting": "Enter the dividend tax paid for each relevant entity, and enter 0 if no dividend tax was paid.",
        "Q71_text": f"Did you (and/or your tax partner) have Dutch bank accounts and/or Dutch investments in {JAAR}?",
        "Q72_text": f"Upload the annual statements for {JAAR} of all Dutch accounts.",
        "Q72_toelicht": f"Upload the annual statements of all Dutch bank accounts and investment accounts of you (and your tax partner). Bank accounts/investments in the name of a minor child are also included. {_UPLOAD_TIP_EN}",
        "Q73_text": f"Did you (and/or your tax partner) own crypto and/or receivables (such as a loan to third parties) in {JAAR}?",
        "Q73b_text": f"Please list the description and value of each asset below as of 1-1-{JAAR} and 31-12-{JAAR}.",
        "Q73b_col1": "Description",
        "Q73b_col2": f"Value 1-1-{JAAR} (€)",
        "Q73b_col3": f"Value 31-12-{JAAR} (€)",
        "Q74_text": f"Did you (and/or your tax partner) own other real estate in the Netherlands (not the primary residence) in {JAAR}?",
        "Q75_text": "What is the address of this real estate?",
        "Q76_text": f"Was this other real estate rented out in {JAAR}?",
        "Q76_opts": ["Yes, long-term rental", "Yes, holiday rental", "No"],
        "Q77_text": "Is the property rented out to a family member?",
        "Q79_text": "Do you pay ground rent (erfpacht) annually?",
        "Q80_text": f"What was the ground rent canon in {JAAR}?",
        "Q81_text": "Can this real estate be sold separately?",
        "Q81b_text": "Is there a mortgage or other debt on this real estate?",
        "Q81c_text": f"Upload the {JAAR} annual statement of this mortgage/debt.",
        "Q82_text": f"Did you (and/or your tax partner) have Dutch debts in {JAAR}?",
        "Q83_text": f"Upload annual statements for {JAAR} of all Dutch debts.",
        "Q83_toelicht": f"Upload the annual statements of all Dutch debts of you (and/or your tax partner), such as a student loan, personal loan, or credit. {_UPLOAD_TIP_EN}",
        "Q84_text": f"Did you (and/or your tax partner) have foreign bank accounts and/or foreign investments in {JAAR}?",
        "Q85_text": f"Upload the annual statements for {JAAR} of all foreign accounts.",
        "Q85_toelicht": f"Upload the annual statements of all foreign bank accounts and investment accounts of you (and/or your tax partner). {_UPLOAD_TIP_EN}",
        # Stap 16 — foreign real estate (repeats per property)
        "Q86_text": f"Did you (and/or your tax partner) own real estate abroad in {JAAR}?",
        "Q86_meer_text": f"Did you (and/or your tax partner) own any other real estate abroad in {JAAR}?",
        "og_object": " (property {k})",
        "Q87_text": "What is the address?",
        "Q88_text": f"What was the value on 1-1-{JAAR}?",
        "Q88b_text": "Is this real estate fully owned by you (and/or your tax partner)?",
        "Q88c_text": "What percentage do you (and/or your tax partner) own?",
        "Q86b_text": "Is there a mortgage or other debt on this real estate?",
        "Q86c_text": f"Upload the {JAAR} annual statement of this mortgage/debt.",
        "Q89_text": f"Was this real estate bought or sold in {JAAR}?",
        "Q89b_text": "On what date did the purchase/sale take place?",
        "Q89c_text": "For what amount was the real estate bought/sold?",
        "Q90_text": f"Did you (and/or your tax partner) have foreign debts in {JAAR}?",
        "Q91_text": f"Describe the foreign debts and state the amount on 1-1-{JAAR} and 31-12-{JAAR}.",
        "Q91_col2": f"Amount 1-1-{JAAR} (€)",
        "Q91_col3": f"Amount 31-12-{JAAR} (€)",
        "Q92_text": f"Did you (and/or your tax partner) have foreign income in {JAAR}?",
        "Q93_text": "What was the source?",
        "Q93_opts": ["Income from employment", "Income as self-employed", "Pension", "Other"],
        "Q94_text": "Was tax withheld?",
        "Q94_opts": ["Yes", "No", "Not entirely sure"],
        "Q95_text": "Upload proof of all foreign income of you (and/or your tax partner).",
        "Q95_toelicht": f"For example an annual statement or pay slip. {_UPLOAD_TIP_EN}",
        "Q96_text": f"Did you (and/or your tax partner) donate more than EUR 60 to charities in {JAAR}?",
        "Q97_text": "Please state the amount per charity.",
        "Q98_text": f"Did you (and/or your tax partner) pay extraordinary healthcare expenses in {JAAR}?",
        "Q99_text": "Please state the amount per type of healthcare expense.",
        "Q100_text": "Are you (and/or your tax partner) on a diet prescribed by a doctor?",
        "Q101_text": "Which diet is it?",
        "Q102_text": f"Did you (and/or your tax partner) receive a provisional tax assessment (voorlopige aanslag) in {JAAR}?",
        "Q103_text": "Upload a copy of the provisional assessment.",
        "Q104_text": "Would you like to upload any additional documents?",
        "Q105_text": "Upload additional documents here.",
        "Q106_text": "Do you have any further comments or questions?",
        "Q107_text": "Please state your comments.",
        "yes": "Yes",
        "no": "No"
    }
}
START_TRANSLATION = {
    "NL": {
        "start_title": "Welkom bij de Belastingaangifte Vragenlijst",
        "start_subtitle": "### Fijn dat je er bent.",
        "start_body": "Met deze digitale vragenlijst verzamelen we snel en efficiënt alle benodigde gegevens voor jouw aangifte. Zo weet je zeker dat je geen aftrekposten mist.",
        "start_info": """
### 📋 Wat kun je verwachten en wat heb je nodig?

Het invullen van de vragenlijst duurt ongeveer **10 tot 15 minuten**. Je kunt tussendoor op elk moment terugbladeren om antwoorden aan te passen.

**Zorg dat je de volgende zaken bij de hand hebt:**
- Jouw **9-cijferige BSN** (en eventueel die van jouw partner)
- Inkomensgegevens of jaaropgaven

---
*🔒 Jouw gegevens worden volledig versleuteld en strikt conform de AVG verwerkt.*
        """,
        "start_button": "🚀 Start nu de vragenlijst",
        "main_title": "Belastingaangifte Vragenlijst",
        "main_subtitle": "Vul de onderstaande vragen zo nauwkeurig mogelijk in.",
        "melding_titel": "Eerdere antwoorden geladen",
        "melding_tekst": lambda jaar: f"We hebben jouw antwoorden van **{jaar}** alvast geladen in de vragenlijst. Veel antwoorden zullen hetzelfde zijn — pas de antwoorden aan wanneer jouw situatie is gewijzigd. **Alle bestanden moeten wel opnieuw geüpload worden.**",
        "melding_knop": "Begrepen, start de vragenlijst"
    },
    "EN": {
        "start_title": "Welcome to the Tax Declaration Questionnaire",
        "start_subtitle": "### We are glad you're here.",
        "start_body": "With this digital questionnaire, we collect all necessary data for your tax return quickly and efficiently. This ensures you won't miss out on any deductions.",
        "start_info": """
### 📋 What to expect and what do you need?

Filling out the questionnaire takes about **10 to 15 minutes**. You can go back at any time to change your answers.

**Please have the following ready:**
- Your **9-digit BSN** (and your partner's, if applicable)
- Income statements or annual tax statements

---
*🔒 Your data is fully encrypted and processed strictly in accordance with GDPR.*
        """,
        "start_button": "🚀 Start the questionnaire now",
        "main_title": "Tax Declaration Questionnaire",
        "main_subtitle": "Please answer the questions below as accurately as possible.",
        "melding_titel": "Previous answers loaded",
        "melding_tekst": lambda jaar: f"We have pre-filled the questionnaire with your answers from **{jaar}**. Many answers will be the same — please update them where your situation has changed. **All files will need to be uploaded again.**",
        "melding_knop": "Got it, start the questionnaire"
    }
}
# Dynamische snelkoppeling naar de actieve vragen-taal
q_vertaling = QUESTIONS_TRANSLATION.get(st.session_state.taal, QUESTIONS_TRANSLATION["NL"])
# Snelkoppelingen naar de universele Ja/Nee keuzes per taal
JA_NEE_OPTIES = [q_vertaling.get("yes", "Ja"), q_vertaling.get("no", "Nee")]
# Snelkoppeling naar de actieve taalset
t = UI_TRANSLATION[st.session_state.taal]

# Dynamische snelkoppeling naar de actieve stappen-taal
s_vertaling = STAPPEN_TRANSLATION.get(st.session_state.taal, STAPPEN_TRANSLATION["NL"])
Start_vertaling = START_TRANSLATION[st.session_state.taal]

# --- VRAGEN MATRIX (DYNAMISCH) ---
QUESTIONS = {
    "Question 1": {
        "text": q_vertaling.get("Q1_text"),
        "toelichting": q_vertaling.get("Q1_toelicht"),
        "type": "checkbox"
    },
    "Question 2": {
        "text": q_vertaling.get("Q2_text"),
        "type": "text",
    },
    "Question 3": {
        "text": q_vertaling.get("Q3_text"),
        "type": "text",
    },
    "Question 3b": {
        "text": q_vertaling.get("Q3b_text"),
        "type": "tekst_optioneel",
    },
    "Question 4": {
        "text": q_vertaling.get("Q4_text"),
        "type": "phonenumber",
    },
    "Question 5": {
        "text": q_vertaling.get("Q5_text"),
        "type": "emailadress",
    },
    "Question 6": {
        "text": q_vertaling.get("Q6_text"),
        "type": "datum",
    },
    "Question 7": {
        "text": q_vertaling.get("Q7_text"),
        "type": "BSN",
    },
    "Question 7b": {
        "text": q_vertaling.get("Q7b_text"),
        "type": "text",
    },
    "Question 7c": {
        "text": q_vertaling.get("Q7c_text"),
        "type": "adres",
    },
    "Question 8": {
        "text": q_vertaling.get("Q8_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES, 
    },
    "Question 9": {
        "text": q_vertaling.get("Q9_text"),
        "type": "datum",
        "depends_on": {
            "question": "Question 8",
            "expected_value": q_vertaling.get("yes", "Ja") # Dynamisch matchen op het gekozen antwoord
        },
    },
    "Question 10": {
        "text": q_vertaling.get("Q10_text"),
        "toelichting": q_vertaling.get("Q10_toelicht"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 8",
            "expected_value": q_vertaling.get("no", "Nee")
        },  
    },
    "Question 11": {
        "text": q_vertaling.get("Q11_text"),
        "type": "text",
    },
    "Question 11b": {
        "text": q_vertaling.get("Q11b_text"),
        "type": "tekst_optioneel",
    },
    "Question 12": {
        "text": q_vertaling.get("Q12_text"),
        "type": "text",
    },
    "Question 13": {
        "text": q_vertaling.get("Q13_text"),
        "type": "phonenumber",
    },
    "Question 14": {
        "text": q_vertaling.get("Q14_text"),
        "type": "emailadress",
    }, 
    "Question 15": {
        "text": q_vertaling.get("Q15_text"),
        "type": "BSN",
    },
    "Question 15b": {
        "text": q_vertaling.get("Q15b_text"),
        "type": "text",
    },
    "Question 16": {
        "text": q_vertaling.get("Q16_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 17": {
        "text": q_vertaling.get("Q17_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 16",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 18": {
        "text": q_vertaling.get("Q18_text"),
        "type": "datum",
        "depends_on": {
            "question": "Question 16",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 19": {
        "text": q_vertaling.get("Q19_text"),
        "type": "choice",
        "options": [q_vertaling.get("Q19_opt1"), q_vertaling.get("Q19_opt2"), q_vertaling.get("Q19_opt3")],
    },
    "Question 20": {
        "text": q_vertaling.get("Q20_text"),
        "type": "choice",
        "options": [q_vertaling.get("Q20_opt1"), q_vertaling.get("Q20_opt2")],
        "depends_on": {
            "question": "Question 19",
            "expected_value": q_vertaling.get("Q19_opt2")
        },
    },
    # Q19 staat mee in de condities: anders tonen oude antwoorden op Q20 deze vragen nog
    "Question 21": {
        "text": q_vertaling.get("Q21_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 19", "expected_value": q_vertaling.get("Q19_opt2")},
            {"question": "Question 20", "expected_value": q_vertaling.get("Q20_opt1")},  # Immigratie
        ],
    },
    "Question 22": {
        "text": q_vertaling.get("Q22_text"),
        "toelichting": q_vertaling.get("Q22_toelicht"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 19", "expected_value": q_vertaling.get("Q19_opt2")},
            {"question": "Question 20", "expected_value": q_vertaling.get("Q20_opt1")},
        ],
    },
    "Question 23": {
        "text": q_vertaling.get("Q23_text"),
        "type": "text",
        "depends_on": [
            {"question": "Question 19", "expected_value": q_vertaling.get("Q19_opt2")},
            {"question": "Question 20", "expected_value": q_vertaling.get("Q20_opt1")},
        ],
    },
    "Question 24": {
        "text": q_vertaling.get("Q24_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 19", "expected_value": q_vertaling.get("Q19_opt2")},
            {"question": "Question 20", "expected_value": q_vertaling.get("Q20_opt2")},  # Emigratie
        ],
    },
    "Question 26": {
        "text": q_vertaling.get("Q26_text"),
        "toelichting": q_vertaling.get("Q26_toelicht"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 19", "expected_value": q_vertaling.get("Q19_opt2")},
            {"question": "Question 20", "expected_value": q_vertaling.get("Q20_opt2")},
        ],
    },
    "Question 27": {
        "text": q_vertaling.get("Q27_text"),
        "type": "text",
        "depends_on": [
            {"question": "Question 19", "expected_value": q_vertaling.get("Q19_opt2")},
            {"question": "Question 20", "expected_value": q_vertaling.get("Q20_opt2")},
        ],
    },
    "Question 28": {
        "text": q_vertaling.get("Q28_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 29": {
        "text": q_vertaling.get("Q29_text"),
        "type": "int",
        "depends_on": {
            "question": "Question 28",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 30": {
        "text": q_vertaling.get("Q30_text"),
        "type": "multi_bestand",
        "herhaling": {"vraag": "Question 29", "max": 5},
        "depends_on": {
            "question": "Question 28",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 31": {
        "text": q_vertaling.get("Q31_text"),
        "toelichting": q_vertaling.get("Q31_toelicht"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 28",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 32": {
        "text": q_vertaling.get("Q32_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 28", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 31", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    # ── Stap 7b: Uitkering / pensioen / lijfrente ────────────────────
    "Question 32b": {
        "text": q_vertaling.get("Q32b_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 32c": {
        "text": q_vertaling.get("Q32c_text"),
        "toelichting": q_vertaling.get("Q32c_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 32b",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 33": {
        "text": q_vertaling.get("Q33_text"),
        "toelichting": q_vertaling.get("Q33_toelicht"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 34": {
        "text": q_vertaling.get("Q34_text"),
        "type": "choice",
        "options": q_vertaling.get("Q34_opts"),
        "depends_on": {
            "question": "Question 33",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 35": {
        "text": q_vertaling.get("Q35_text"),
        "type": "kvk-nummer",
        "depends_on": {
            "question": "Question 33",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 36": {
        "text": q_vertaling.get("Q36_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 33",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 37": {
        "text": q_vertaling.get("Q37_text"),
        "toelichting": q_vertaling.get("Q37_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 33",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 37b": {
        "text": q_vertaling.get("Q37b_text"),
        "toelichting": q_vertaling.get("Q37b_toelicht"),
        "type": "multi_bestand_vrij",
        "optioneel": True,
        "depends_on": {
            "question": "Question 33",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 38": {
        "text": q_vertaling.get("Q38_text"),
        "type": "choice",
        "options": q_vertaling.get("Q38_opts"),
        "depends_on": {
            "question": "Question 33",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    # ── Stap 7a: Loondienst partner ──────────────────────────────────
    "Question 28p": {
        "text": q_vertaling.get("Q28p_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 29p": {
        "text": q_vertaling.get("Q29p_text"),
        "type": "int",
        "depends_on": {
            "question": "Question 28p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 30p": {
        "text": q_vertaling.get("Q30p_text"),
        "type": "multi_bestand",
        "herhaling": {"vraag": "Question 29p", "max": 5},
        "depends_on": {
            "question": "Question 28p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 31p": {
        "text": q_vertaling.get("Q31p_text"),
        "toelichting": q_vertaling.get("Q31p_toelicht"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 28p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 32p": {
        "text": q_vertaling.get("Q32p_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 28p", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 31p", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    # ── Stap 7c: Uitkering / pensioen / lijfrente partner ────────────
    "Question 32bp": {
        "text": q_vertaling.get("Q32bp_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 32cp": {
        "text": q_vertaling.get("Q32cp_text"),
        "toelichting": q_vertaling.get("Q32cp_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 32bp",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    # ── Stap 8a: Ondernemerschap partner ─────────────────────────────
    "Question 33p": {
        "text": q_vertaling.get("Q33p_text"),
        "toelichting": q_vertaling.get("Q33p_toelicht"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 34p": {
        "text": q_vertaling.get("Q34p_text"),
        "type": "choice",
        "options": q_vertaling.get("Q34_opts"),
        "depends_on": {
            "question": "Question 33p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 35p": {
        "text": q_vertaling.get("Q35p_text"),
        "type": "kvk-nummer",
        "depends_on": {
            "question": "Question 33p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 36p": {
        "text": q_vertaling.get("Q36p_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 33p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 37p": {
        "text": q_vertaling.get("Q37p_text"),
        "toelichting": q_vertaling.get("Q37_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 33p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 37bp": {
        "text": q_vertaling.get("Q37bp_text"),
        "toelichting": q_vertaling.get("Q37b_toelicht"),
        "type": "multi_bestand_vrij",
        "optioneel": True,
        "depends_on": {
            "question": "Question 33p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 38p": {
        "text": q_vertaling.get("Q38p_text"),
        "type": "choice",
        "options": q_vertaling.get("Q38_opts"),
        "depends_on": {
            "question": "Question 33p",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 39": {
        "text": q_vertaling.get("Q39_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 40": {
        "text": q_vertaling.get("Q40_text"),
        "type": "choice",
        "options": q_vertaling.get("Q40_opts"),
        "depends_on": {
            "question": "Question 39",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 41": {
        "text": q_vertaling.get("Q41_text"),
        "type": "text",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 40", "expected_value": q_vertaling.get("Q40_opts")[2]},
        ],
    },
    "Question 42": {
        "text": q_vertaling.get("Q42_text"),
        "type": "adres",
        "depends_on": {
            "question": "Question 39",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 43": {
        "text": q_vertaling.get("Q43_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 39",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 44": {
        "text": q_vertaling.get("Q44_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 43", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 44b": {
        "text": q_vertaling.get("Q44b_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 39",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 44c": {
        "text": q_vertaling.get("Q44c_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 44b", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 45": {
        "text": q_vertaling.get("Q45_text"),
        "type": "choice",
        "options": q_vertaling.get("Q45_opts"),
        "depends_on": {
            "question": "Question 39",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 46": {
        "text": q_vertaling.get("Q46_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[0]},
        ],
    },
    "Question 46b": {
        "text": q_vertaling.get("Q46b_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[0]},
        ],
    },
    "Question 47": {
        "text": q_vertaling.get("Q47_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[0]},
        ],
    },
    "Question 47b": {
        "text": q_vertaling.get("Q47b_text"),
        "toelichting": q_vertaling.get("taxatie_toelicht"),
        "type": "bestand",
        "optioneel": True,
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[0]},
        ],
    },
    "Question 48": {
        "text": q_vertaling.get("Q48_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[1]},
        ],
    },
    "Question 48b": {
        "text": q_vertaling.get("Q48b_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[1]},
        ],
    },
    "Question 49": {
        "text": q_vertaling.get("Q49_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[1]},
        ],
    },
    "Question 49b": {
        "text": q_vertaling.get("Q49b_text"),
        "toelichting": q_vertaling.get("taxatie_toelicht"),
        "type": "bestand",
        "optioneel": True,
        "depends_on": [
            {"question": "Question 39", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 45", "expected_value": q_vertaling.get("Q45_opts")[1]},
        ],
    },
    "Question 50": {
        "text": q_vertaling.get("Q50_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 39",
            "expected_value": q_vertaling.get("yes", "Ja")
        }
    },
    "Question 51": {
        "text": q_vertaling.get("Q51_text"),
        "type": "choice",
        "options": q_vertaling.get("Q51_opts"),
        "depends_on": {
            "question": "Question 50",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 52": {
        "text": q_vertaling.get("Q52_text"),
        "type": "text",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 51", "expected_value": q_vertaling.get("Q51_opts")[2]},
        ],
    },
    "Question 53": {
        "text": q_vertaling.get("Q53_text"),
        "type": "adres",
        "depends_on": {
            "question": "Question 50",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 54": {
        "text": q_vertaling.get("Q54_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 50",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 55": {
        "text": q_vertaling.get("Q55_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 54", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 56": {
        "text": q_vertaling.get("Q56_text"),
        "type": "choice",
        "options": q_vertaling.get("Q56_opts"),
        "depends_on": {
            "question": "Question 50",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 57": {
        "text": q_vertaling.get("Q57_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[0]},
        ],
    },
    "Question 57b": {
        "text": q_vertaling.get("Q57b_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[0]},
        ],
    },
    "Question 58": {
        "text": q_vertaling.get("Q58_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[0]},
        ],
    },
    "Question 59": {
        "text": q_vertaling.get("Q59_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[0]},
        ],
    },
    "Question 59b": {
        "text": q_vertaling.get("Q59b_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[1]},
        ],
    },
    "Question 60": {
        "text": q_vertaling.get("Q60_text"),
        "type": "datum",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[1]},
        ],
    },
    "Question 61": {
        "text": q_vertaling.get("Q61_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[1]},
        ],
    },
    "Question 62": {
        "text": q_vertaling.get("Q62_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 50", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 56", "expected_value": q_vertaling.get("Q56_opts")[1]},
        ],
    },
    "Question 63": {
        "text": q_vertaling.get("Q63_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 64": {
        "text": q_vertaling.get("Q64_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 63",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 65": {
        "text": q_vertaling.get("Q65_text"),
        "toelichting": q_vertaling.get("Q65_toelichting"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 66": {
        "text": q_vertaling.get("Q66_text"),
        "type": "tabel",
        "col1": q_vertaling.get("Q66_col1"),
        "col2": q_vertaling.get("Q66_col2"),
        "depends_on": {
            "question": "Question 65",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 67": {
        "text": q_vertaling.get("Q67_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 65",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 68": {
        "text": q_vertaling.get("Q68_text"),
        "toelichting": q_vertaling.get("Q68_toelichting"),
        "type": "tabel",
        "col1": q_vertaling.get("Q66_col1"),
        "col2": q_vertaling.get("Q68_col2"),
        "allow_negative": True,
        "prefill_from": "Question 66",
        "depends_on": [
            {"question": "Question 65", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 67", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 68b": {
        "text": q_vertaling.get("Q68b_text"),
        "toelichting": q_vertaling.get("Q68b_toelichting"),
        "type": "tabel",
        "col1": q_vertaling.get("Q66_col1"),
        "col2": q_vertaling.get("Q68b_col2"),
        "prefill_from": "Question 66",
        "depends_on": [
            {"question": "Question 65", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 67", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 69": {
        "text": q_vertaling.get("Q69_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 65",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 70": {
        "text": q_vertaling.get("Q70_text"),
        "toelichting": q_vertaling.get("Q70_toelichting"),
        "type": "tabel",
        "col1": q_vertaling.get("Q66_col1"),
        "col2": q_vertaling.get("Q70_col2"),
        "prefill_from": "Question 66",
        "depends_on": [
            {"question": "Question 65", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 69", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 70b": {
        "text": q_vertaling.get("Q70b_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": [
            {"question": "Question 65", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 69", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 70c": {
        "text": q_vertaling.get("Q70c_text"),
        "toelichting": q_vertaling.get("Q70c_toelichting"),
        "type": "tabel",
        "col1": q_vertaling.get("Q66_col1"),
        "col2": q_vertaling.get("Q70c_col2"),
        "prefill_from": "Question 66",
        "depends_on": [
            {"question": "Question 65", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 69", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 70b", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 71": {
        "text": q_vertaling.get("Q71_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 72": {
        "text": q_vertaling.get("Q72_text"),
        "toelichting": q_vertaling.get("Q72_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 71",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 73": {
        "text": q_vertaling.get("Q73_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 73b": {
        "text": q_vertaling.get("Q73b_text"),
        "type": "tabel_3col",
        "col1": q_vertaling.get("Q73b_col1"),
        "col2": q_vertaling.get("Q73b_col2"),
        "col3": q_vertaling.get("Q73b_col3"),
        "depends_on": {
            "question": "Question 73",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 74": {
        "text": q_vertaling.get("Q74_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 75": {
        "text": q_vertaling.get("Q75_text"),
        "type": "adres",
        "depends_on": {
            "question": "Question 74",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 76": {
        "text": q_vertaling.get("Q76_text"),
        "type": "choice",
        "options": q_vertaling.get("Q76_opts"),
        "depends_on": {
            "question": "Question 74",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 77": {
        "text": q_vertaling.get("Q77_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 74",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 79": {
        "text": q_vertaling.get("Q79_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 74",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 80": {
        "text": q_vertaling.get("Q80_text"),
        "type": "int",
        "depends_on": [
            {"question": "Question 74", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 79", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 81": {
        "text": q_vertaling.get("Q81_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 74",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 81b": {
        "text": q_vertaling.get("Q81b_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
        "depends_on": {
            "question": "Question 74",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 81c": {
        "text": q_vertaling.get("Q81c_text"),
        "type": "bestand",
        "depends_on": [
            {"question": "Question 74", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 81b", "expected_value": q_vertaling.get("yes", "Ja")},
        ],
    },
    "Question 82": {
        "text": q_vertaling.get("Q82_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 83": {
        "text": q_vertaling.get("Q83_text"),
        "toelichting": q_vertaling.get("Q83_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 82",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 84": {
        "text": q_vertaling.get("Q84_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 85": {
        "text": q_vertaling.get("Q85_text"),
        "toelichting": q_vertaling.get("Q85_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 84",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    # Question 86 t/m 89 (buitenlands onroerend goed) worden hieronder per object gegenereerd
    "Question 90": {
        "text": q_vertaling.get("Q90_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 91": {
        "text": q_vertaling.get("Q91_text"),
        "type": "tabel_3col",
        "col1": q_vertaling.get("Q73b_col1"),
        "col2": q_vertaling.get("Q91_col2"),
        "col3": q_vertaling.get("Q91_col3"),
        "depends_on": {
            "question": "Question 90",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 92": {
        "text": q_vertaling.get("Q92_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 93": {
        "text": q_vertaling.get("Q93_text"),
        "type": "choice",
        "options": q_vertaling.get("Q93_opts"),
        "depends_on": {
            "question": "Question 92",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 94": {
        "text": q_vertaling.get("Q94_text"),
        "type": "choice",
        "options": q_vertaling.get("Q94_opts"),
        "depends_on": {
            "question": "Question 92",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 95": {
        "text": q_vertaling.get("Q95_text"),
        "toelichting": q_vertaling.get("Q95_toelicht"),
        "type": "multi_bestand_vrij",
        "depends_on": {
            "question": "Question 92",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 96": {
        "text": q_vertaling.get("Q96_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 97": {
        "text": q_vertaling.get("Q97_text"),
        "type": "tabel",
        "depends_on": {
            "question": "Question 96",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 98": {
        "text": q_vertaling.get("Q98_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 99": {
        "text": q_vertaling.get("Q99_text"),
        "type": "tabel",
        "depends_on": {
            "question": "Question 98",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 100": {
        "text": q_vertaling.get("Q100_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 101": {
        "text": q_vertaling.get("Q101_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 100",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 102": {
        "text": q_vertaling.get("Q102_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 103": {
        "text": q_vertaling.get("Q103_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 102",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 104": {
        "text": q_vertaling.get("Q104_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 105": {
        "text": q_vertaling.get("Q105_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 104",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 106": {
        "text": q_vertaling.get("Q106_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 107": {
        "text": q_vertaling.get("Q107_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 106",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    }
}

# ── Stap 16: buitenlands onroerend goed, herhaalbaar tot MAX_OG_BUITENLAND objecten ──
# Object 1 houdt de oorspronkelijke ID's (compatibel met eerdere antwoorden),
# object k ≥ 2 krijgt het achtervoegsel "_k" (bijv. "Question 87_2").
# Let op: modules/admin_db.py gebruikt dezelfde ID-opbouw.
MAX_OG_BUITENLAND = 5

def og_id(basis: str, k: int) -> str:
    return f"Question {basis}" if k == 1 else f"Question {basis}_{k}"

OG_BUITENLAND_VRAGEN = []
_ja = q_vertaling.get("yes", "Ja")
for k in range(1, MAX_OG_BUITENLAND + 1):
    # Alle voorgaande "heb je (nog meer) onroerend goed"-vragen moeten Ja zijn
    keten = [{"question": og_id("86", i), "expected_value": _ja} for i in range(1, k + 1)]
    object_label = "" if k == 1 else q_vertaling.get("og_object").format(k=k)

    blok = {
        og_id("86", k): {
            "text": q_vertaling.get("Q86_text") if k == 1 else q_vertaling.get("Q86_meer_text"),
            "type": "choice",
            "options": JA_NEE_OPTIES,
        },
        og_id("87", k):  {"text": q_vertaling.get("Q87_text") + object_label,  "type": "adres", "depends_on": keten},
        og_id("88", k):  {"text": q_vertaling.get("Q88_text") + object_label,  "type": "int",   "depends_on": keten},
        og_id("88b", k): {"text": q_vertaling.get("Q88b_text") + object_label, "type": "choice", "options": JA_NEE_OPTIES, "depends_on": keten},
        og_id("88c", k): {"text": q_vertaling.get("Q88c_text") + object_label, "type": "int",
                          "depends_on": keten + [{"question": og_id("88b", k), "expected_value": q_vertaling.get("no", "Nee")}]},
        og_id("86b", k): {"text": q_vertaling.get("Q86b_text") + object_label, "type": "choice", "options": JA_NEE_OPTIES, "depends_on": keten},
        og_id("86c", k): {"text": q_vertaling.get("Q86c_text") + object_label, "type": "bestand",
                          "depends_on": keten + [{"question": og_id("86b", k), "expected_value": _ja}]},
        og_id("89", k):  {"text": q_vertaling.get("Q89_text") + object_label,  "type": "choice", "options": JA_NEE_OPTIES, "depends_on": keten},
        og_id("89b", k): {"text": q_vertaling.get("Q89b_text") + object_label, "type": "datum",
                          "depends_on": keten + [{"question": og_id("89", k), "expected_value": _ja}]},
        og_id("89c", k): {"text": q_vertaling.get("Q89c_text") + object_label, "type": "int",
                          "depends_on": keten + [{"question": og_id("89", k), "expected_value": _ja}]},
    }
    if k > 1:
        blok[og_id("86", k)]["depends_on"] = keten[:-1]
    QUESTIONS.update(blok)
    OG_BUITENLAND_VRAGEN.extend(blok.keys())

STAPPEN = {
    "START": {
        "titel": s_vertaling.get("START", "Welkom"),
        "vragen": [] 
    },
    "Stap 1": {
        "titel": s_vertaling.get("Stap 1", "Privacy verklaring"),
        "vragen": ["Question 1"],
        "next_step": "Stap 2" 
    },
    "Stap 2": {
        "titel": s_vertaling.get("Stap 2", "Persoonlijke gegevens"),
        "vragen": ["Question 2", "Question 3b", "Question 3", "Question 4", "Question 5", "Question 6", "Question 7", "Question 7b", "Question 7c"],
        "next_step": "Stap 3"
    },
    "Stap 3": {
        "titel": s_vertaling.get("Stap 3", "Fiscaal Partner"),
        "vragen": ["Question 8", "Question 9","Question 10"],
        "route": {
            q_vertaling.get("yes", "Ja"): "Stap 4",
            q_vertaling.get("no", "Nee"): "Stap 5"
        }    
    },
    "Stap 4": {
        "titel": s_vertaling.get("Stap 4", "Persoonlijke gegevens van Fiscaal Partner"),
        "vragen": ["Question 11","Question 11b","Question 12","Question 13","Question 14","Question 15","Question 15b"],
        "next_step": "Stap 5"
    },
    "Stap 5": {
        "titel": s_vertaling.get("Stap 5", "Thuiswonende kinderen"),
        "vragen": ["Question 16","Question 17","Question 18"],
        "next_step": "Stap 6"
    },
    "Stap 6": {
        "titel": s_vertaling.get("Stap 6", "Waar je woonde"),
        "vragen": ["Question 19", "Question 20", "Question 21", "Question 22", "Question 23", "Question 24", "Question 26", "Question 27"],
        "next_step": "Stap 7"
    },
    "Stap 7": {
        "titel": s_vertaling.get("Stap 7", "Inkomen uit loondienst"),
        "vragen": ["Question 28", "Question 29", "Question 30", "Question 31", "Question 32"],
    },
    "Stap 7a": {
        "titel": s_vertaling.get("Stap 7a", "Inkomen uit loondienst van jouw partner"),
        "vragen": ["Question 28p", "Question 29p", "Question 30p", "Question 31p", "Question 32p"],
        "next_step": "Stap 7b",
    },
    "Stap 7b": {
        "titel": s_vertaling.get("Stap 7b", "Inkomen uit uitkering / pensioen / lijfrente"),
        "vragen": ["Question 32b", "Question 32c"],
    },
    "Stap 7c": {
        "titel": s_vertaling.get("Stap 7c", "Inkomen uit uitkering / pensioen / lijfrente van jouw partner"),
        "vragen": ["Question 32bp", "Question 32cp"],
        "next_step": "Stap 8",
    },
    "Stap 8": {
        "titel": s_vertaling.get("Stap 8", "Inkomen uit ondernemerschap"),
        "vragen": ["Question 33", "Question 34", "Question 35", "Question 36", "Question 37", "Question 37b", "Question 38"],
    },
    "Stap 8a": {
        "titel": s_vertaling.get("Stap 8a", "Inkomen uit ondernemerschap van jouw partner"),
        "vragen": ["Question 33p", "Question 34p", "Question 35p", "Question 36p", "Question 37p", "Question 37bp", "Question 38p"],
        "next_step": "Stap 9",
    },
    "Stap 9": {
        "titel": s_vertaling.get("Stap 9", "Eigen woonverblijf"),
        "vragen": ["Question 39", "Question 40", "Question 41", "Question 42", "Question 43", "Question 44", "Question 44b", "Question 44c", "Question 45", "Question 46", "Question 46b", "Question 47", "Question 47b", "Question 48", "Question 48b", "Question 49", "Question 49b"],
        "partner_melding": True,
    },
    "Stap 10": {
        "titel": s_vertaling.get("Stap 10", "Tweede eigen woonverblijf"),
        "vragen": ["Question 50", "Question 51", "Question 52", "Question 53", "Question 54", "Question 55", "Question 56", "Question 57", "Question 57b", "Question 58", "Question 59", "Question 59b", "Question 60", "Question 61", "Question 62"],
        "partner_melding": True,
    },
    "Stap 11": {
        "titel": s_vertaling.get("Stap 11", "Hypotheek"),
        "vragen": ["Question 63", "Question 64"],
        "next_step": "Stap 12",
        "partner_melding": True,
    },
    "Stap 12": {
        "titel": s_vertaling.get("Stap 12", "Aanmerkelijk belang"),
        "vragen": ["Question 65", "Question 66", "Question 67", "Question 68", "Question 68b", "Question 69", "Question 70", "Question 70b", "Question 70c"],
        "next_step": "Stap 13",
        "partner_melding": True,
    },
    "Stap 13": {
        "titel": s_vertaling.get("Stap 13", "Sparen"),
        "vragen": ["Question 71", "Question 72", "Question 73", "Question 73b"],
        "next_step": "Stap 14",
        "partner_melding": True,
    },
    "Stap 14": {
        "titel": s_vertaling.get("Stap 14", "Tweede eigen woonverblijf"),
        "vragen": ["Question 74", "Question 75", "Question 76", "Question 77", "Question 78", "Question 79", "Question 80", "Question 81", "Question 81b", "Question 81c"],
        "next_step": "Stap 15",
        "partner_melding": True,
    },
    "Stap 15": {
        "titel": s_vertaling.get("Stap 15", "Overig"),
        "vragen": ["Question 82", "Question 83"],
        "next_step": "Stap 16",
        "partner_melding": True,
    },
    "Stap 16": {
        "titel": s_vertaling.get("Stap 16", "Buitenlands vermogen, beleggingen, schulden en inkomen"),
        "vragen": ["Question 84", "Question 85", *OG_BUITENLAND_VRAGEN, "Question 90", "Question 91", "Question 92", "Question 93", "Question 94", "Question 95"],
        "next_step": "Stap 17",
        "partner_melding": True,
    },
    "Stap 17": {
        "titel": s_vertaling.get("Stap 17", "Aftrekposten"),
        "vragen": ["Question 96", "Question 97", "Question 98", "Question 99", "Question 100", "Question 101"],
        "next_step": "Stap 18",
        "partner_melding": True,
    },
    "Stap 18": {
        "titel": s_vertaling.get("Stap 18", "Afronding"),
        "vragen": ["Question 102", "Question 103", "Question 104", "Question 105", "Question 106", "Question 107"],
        "next_step": None,
        "partner_melding": True,
    }
}


# --- MELDING: eerdere antwoorden geladen ---
if st.session_state.toon_melding:
    st.title(Start_vertaling["melding_titel"])
    st.write("")
    jaar_geladen = st.session_state.geladen_van_jaar or JAAR - 1
    st.info(Start_vertaling["melding_tekst"](jaar_geladen))
    st.write("")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(Start_vertaling["melding_knop"], width='stretch', type="primary"):
            st.session_state.toon_melding = False
            st.session_state.current_step = "Stap 1"
            st.rerun()
    st.stop()

# --- 1. DE STARTPAGINA
if current_step == "START":
    st.title(Start_vertaling["start_title"])
    st.write(Start_vertaling["start_subtitle"])
    
    st.write(Start_vertaling["start_body"])
    
    st.info(Start_vertaling["start_info"])
    
    st.write("##") 
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(Start_vertaling["start_button"], width='stretch', type="primary"):
            if not st.session_state.previous_loaded:
                vorige_antwoorden = load_previous_answers(st.session_state.user.id, JAAR)
                if vorige_antwoorden:
                    st.session_state.antwoorden_log = vorige_antwoorden
                    # Bepaal van welk jaar de antwoorden zijn geladen
                    for zoekjaar in [JAAR, JAAR - 1]:
                        check = load_previous_answers(st.session_state.user.id, zoekjaar + 1)
                        if check == vorige_antwoorden:
                            st.session_state.geladen_van_jaar = zoekjaar
                            break
                    if st.session_state.geladen_van_jaar is None:
                        st.session_state.geladen_van_jaar = JAAR - 1
                    st.session_state.toon_melding = True
                    st.session_state.previous_loaded = True
                    st.rerun()
                st.session_state.previous_loaded = True
            if not st.session_state.toon_melding:
                st.session_state.current_step = "Stap 1"
                st.rerun()

# --- 2. DE WERKELIJKE VRAGENLIJST (Hier tonen we de formuliertitels) ---
elif current_step and current_step in STAPPEN:
    scroll_to_top()
    stap_info = STAPPEN[current_step]
    with st.container(key=f"focus_reset_{current_step.replace(' ', '_')}"):
        st.caption(f"{t['caption']}: {current_step}")
        st.subheader(stap_info["titel"])
        if stap_info.get("partner_melding") and st.session_state.antwoorden_log.get("Question 8") == q_vertaling.get("yes", "Ja") or stap_info.get("partner_melding") and st.session_state.antwoorden_log.get("Question 10") == q_vertaling.get("yes", "Ja"):
            st.warning(q_vertaling.get("partner_melding", "⚠️ Let op! Onderstaande vragen betreffen zowel jou als jouw partner."))
        st.divider()
    # Een tijdelijke dictionary om de geldige antwoorden van DEZE pagina in te verzamelen
    pagina_antwoorden = {}
    alle_vragen_geldig = True

    # LOOP DOOR ALLE GEBUNDELDE VRAGEN OP DEZE PAGINA
    for q_id in stap_info["vragen"]:
        if q_id not in QUESTIONS:
            continue
            
        vraag = QUESTIONS[q_id]
        
        # --- DYNAMISCHE AFHANKELIJKHEIDSCHECK ---
        if "depends_on" in vraag:
            # Normaliseer naar altijd een lijst van condities
            condities = vraag["depends_on"]
            if isinstance(condities, dict):
                condities = [condities]

            skip = False
            for conditie in condities:
                target_vraag     = conditie["question"]
                # pagina_antwoorden heeft prioriteit over antwoorden_log (huidige invoer boven oude antwoorden)
                actueel_antwoord = pagina_antwoorden.get(target_vraag) if target_vraag in pagina_antwoorden else st.session_state.antwoorden_log.get(target_vraag)

                if "expected_value" in conditie:
                    if str(actueel_antwoord) != str(conditie["expected_value"]):
                        skip = True
                        break
                elif "expected_value_not" in conditie:
                    if str(actueel_antwoord) == str(conditie["expected_value_not"]):
                        skip = True
                        break

            if skip:
                continue
        # ----------------------------------------

        v_type = vraag.get("type", "text")
        input_key = f"input_{q_id}"
        taal = st.session_state.taal  # 'NL' of 'EN'
        
        # Controleer of er al EERDER een antwoord is gegeven op deze specifieke vraag
        bestaand_antwoord = st.session_state.antwoorden_log.get(q_id, None)
        
        # Toon de individuele vraagtekst en info-blok
        st.write(f"#### {vraag['text']}")
        if "toelichting" in vraag:
            st.info(vraag["toelichting"])
            
        antwoord = None

        # --- INPUT ELEMENTEN MET GEHEUGEN-LOGICA ---
        if v_type == "choice":
            # Bepaal de index van het eerder gekozen antwoord, anders None
            default_index = None
            if bestaand_antwoord in vraag["options"]:
                default_index = vraag["options"].index(bestaand_antwoord)
            
            antwoord = st.radio(t["choice_placeholder"] ,vraag["options"], key=input_key, index=default_index)

        elif v_type == "int":
            default_val = int(bestaand_antwoord) if bestaand_antwoord is not None else None
            waarde = st.number_input(t["int_message"], step=1, value=default_val, min_value=0, key=input_key)
            if waarde is not None:
                antwoord = int(waarde)

        elif v_type == "bestand":
            uploaded_file = st.file_uploader(
                "Bestand uploader",
                key=input_key,
                label_visibility="collapsed"
            )
            if uploaded_file:
                ok, pad = upload_document(uploaded_file, st.session_state.user.id, JAAR, q_id)
                if ok:
                    antwoord = pad
                else:
                    st.error(f"Upload mislukt: {pad}")
            elif bestaand_antwoord:
                st.info(f"📁 Eerder geüpload: **{bestaand_antwoord.split('/')[-1]}**")
                antwoord = bestaand_antwoord

        elif v_type == "multi_bestand_vrij":
            uploaded_files = st.file_uploader(
                "Bestanden uploader",
                key=input_key,
                label_visibility="collapsed",
                accept_multiple_files=True
            )
            if uploaded_files:
                paden = []
                for f in uploaded_files:
                    ok, pad = upload_document(f, st.session_state.user.id, JAAR, q_id)
                    if ok:
                        paden.append(pad)
                    else:
                        st.error(f"Upload mislukt voor {f.name}: {pad}")
                if paden:
                    antwoord = paden
            elif bestaand_antwoord:
                eerder = bestaand_antwoord if isinstance(bestaand_antwoord, list) else [bestaand_antwoord]
                namen = [p.split("/")[-1] for p in eerder]
                st.info("📁 Eerder geüpload: " + ", ".join(f"**{n}**" for n in namen))
                antwoord = eerder

        elif v_type == "multi_bestand":
            # Haal het aantal werkgevers op uit de gekoppelde vraag (max 5)
            herhaling  = vraag.get("herhaling", {})
            bron_vraag = herhaling.get("vraag")
            maximum    = herhaling.get("max", 5)

            # Kijk eerst in de huidige pagina-antwoorden, dan in de log
            aantal_raw = pagina_antwoorden.get(bron_vraag) or st.session_state.antwoorden_log.get(bron_vraag)
            try:
                aantal = max(1, min(int(aantal_raw), maximum))
            except (TypeError, ValueError):
                aantal = 1

            # Laad eerder opgeslagen lijst (voor pre-populatie)
            eerder = bestaand_antwoord if isinstance(bestaand_antwoord, list) else []

            bestanden = []
            for i in range(aantal):
                label = f"Werkgever {i + 1}" if aantal > 1 else ""
                if label:
                    st.caption(label)
                eerder_i = eerder[i] if i < len(eerder) else None
                upload = st.file_uploader(
                    f"Uploader {i + 1}",
                    key=f"{input_key}_{i}",
                    label_visibility="collapsed"
                )
                if upload:
                    ok, pad = upload_document(upload, st.session_state.user.id, JAAR, f"{q_id}_{i}")
                    if ok:
                        bestanden.append(pad)
                    else:
                        st.error(f"Upload mislukt: {pad}")
                elif eerder_i:
                    st.info(f"📁 Eerder geüpload: **{eerder_i.split('/')[-1]}**")
                    bestanden.append(eerder_i)

            # Geldig als minstens één bestand is geüpload
            if bestanden:
                antwoord = bestanden

        elif v_type == "adres":
            if st_searchbox is not None:
                gekozen_adres = st_searchbox(
                    google_address_autocomplete,
                    key=input_key,
                    placeholder="Begin met typen... (bijv. Keizersgracht 123)"
                )
                if gekozen_adres:
                    antwoord = gekozen_adres
                    st.success(f"📍 Geselecteerd adres: {antwoord}")
                elif bestaand_antwoord:
                    st.info(f"📁 Eerder ingevuld adres: **{bestaand_antwoord}**")
                    antwoord = bestaand_antwoord
            else:
                # Fallback als streamlit_searchbox niet geïnstalleerd is
                default_val = str(bestaand_antwoord) if bestaand_antwoord else ""
                antwoord_veld = st.text_input("Adres:", value=default_val, key=input_key)
                if antwoord_veld.strip():
                    antwoord = antwoord_veld.strip()

        elif v_type == "datum":
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord_veld = st.text_input("Formaat: DD-MM-YYYY", value=default_val, placeholder="01-01-1990", key=input_key)
            if re.match(r'^\d{2}-\d{2}-\d{4}$', antwoord_veld):
                antwoord = antwoord_veld
            elif antwoord_veld:
                st.error(t["error_date"])
        
        elif v_type == "checkbox":
            default_toggle = bool(bestaand_antwoord) if bestaand_antwoord is not None else False
            antwoord = st.toggle(vraag["text"], value=default_toggle, key=f"cb_{q_id}")

        elif v_type == "BSN":
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord_veld = st.text_input(t["bsn_label"], value=default_val, key=input_key)
            if antwoord_veld.isdigit() and len(antwoord_veld) == 9:
                antwoord = antwoord_veld
            elif antwoord_veld:
                st.error(t["error_bsn"])

        elif v_type == "emailadress":
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord_veld = st.text_input("E-mailadres:", value=default_val, key=input_key)
            if "@" in antwoord_veld and "." in antwoord_veld:
                antwoord = antwoord_veld
            elif antwoord_veld:
                st.error(t["error_email"])

        elif v_type == "phonenumber":
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord = phone_input(vraag["text"], key=input_key, default_value=default_val)

        elif v_type == "kvk-nummer":
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord_veld = st.text_input(t["error_kvk"], value=default_val, key=input_key)
            if antwoord_veld.isdigit() and len(antwoord_veld) == 9:
                antwoord = antwoord_veld
            elif antwoord_veld:
                st.error(t["error_bsn"])

        elif v_type == "tabel":
            prefill_from = vraag.get("prefill_from")
            allow_negative = vraag.get("allow_negative", False)
            default_val = bestaand_antwoord if isinstance(bestaand_antwoord, list) else None
            if default_val is None and prefill_from:
                bron = pagina_antwoorden.get(prefill_from) or st.session_state.antwoorden_log.get(prefill_from)
                if bron and isinstance(bron, list):
                    default_val = [{"naam": r.get("naam", ""), "bedrag": None} for r in bron]
            antwoord = dynamic_list_input(
                key=input_key,
                col1_label=vraag.get("col1", t["table_col1"]),
                col2_label=vraag.get("col2", t["table_col2"]),
                add_btn_label=t["add_row_btn"],
                default_value=default_val,
                allow_negative=allow_negative,
            )

        elif v_type == "tabel_3col":
            antwoord = dynamic_list_input(
                key=input_key,
                col1_label=vraag.get("col1", t["table_col1"]),
                col2_label=vraag.get("col2", t["table_col2"]),
                col3_label=vraag.get("col3"),
                add_btn_label=t["add_row_btn"],
                default_value=bestaand_antwoord if isinstance(bestaand_antwoord, list) else None
            )

        elif v_type == "tekst_optioneel":
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord_veld = st.text_input("Optioneel", value=default_val, key=input_key, placeholder="Optioneel", label_visibility="collapsed")
            antwoord = antwoord_veld  # Altijd geldig, ook als leeg

        else: # Standaard vrije tekst
            default_val = str(bestaand_antwoord) if bestaand_antwoord is not None else ""
            antwoord_veld = st.text_input(t["string_field"], value=default_val, key=input_key)
            if antwoord_veld.strip():
                antwoord = antwoord_veld.strip()

        # --- VALIDATIE CHECK PER VRAAG ---
        if antwoord is not None:
            pagina_antwoorden[q_id] = antwoord
        elif v_type == "checkbox":
            # Bij een checkbox is False ook een geldig antwoordtype voor de pagina_antwoorden dictionary!
            pagina_antwoorden[q_id] = False
        elif vraag.get("optioneel"):
            pass  # Mag leeg blijven (bijv. upload die alleen soms van toepassing is)
        else:
            # Alleen tekstvelden, BSN's, etc. die echt 'None' of leeg zijn triggeren dit
            alle_vragen_geldig = False
            
        st.write("---")

    # NAVIGATIE KNOOPPEN
    col1, col2 = st.columns([1, 4])
    
    with col1:
        if len(st.session_state.history) > 0:
            if st.button(t["prev_btn"]):
                st.session_state.antwoorden_log.update(pagina_antwoorden)
                last_step = st.session_state.history.pop()
                st.session_state.current_step = last_step
                st.rerun()

    with col2:
        # Laatste stap: de stap waarvan de key de laatste is in STAPPEN
        is_laatste_stap = current_step == list(STAPPEN.keys())[-1]
        knop_label = t["submit_btn"] if is_laatste_stap else t["next_btn"]
        if st.button(knop_label, type="primary" if is_laatste_stap else "secondary"):
            # 1. Check specifiek of er een ongevinkte privacy-checkbox op de pagina staat
            heeft_ongevinkte_privacy = False
            for q_id, antw in pagina_antwoorden.items():
                if q_id in QUESTIONS and QUESTIONS[q_id].get("type") == "checkbox":
                    if antw is False:  # Als de checkbox expliciet niet is aangevinkt
                        heeft_ongevinkte_privacy = True

            # 2. NAVIGATIE-AFHANDELING
            if heeft_ongevinkte_privacy:
                st.error(t["error_privacy"])
            
            elif alle_vragen_geldig:
                # Sla de ingevulde antwoorden op
                st.session_state.antwoorden_log.update(pagina_antwoorden)

                # Verwijder antwoorden van vragen die op deze stap NIET getoond werden
                for q_id in stap_info.get("vragen", []):
                    if q_id not in pagina_antwoorden and q_id in st.session_state.antwoorden_log:
                        del st.session_state.antwoorden_log[q_id]

                st.session_state.history.append(current_step)
                
                next_step = None
                route_dict = stap_info.get("route", {})
                
                # Helper: heeft de gebruiker een fiscaal partner?
                ja = q_vertaling.get("yes", "Ja")
                heeft_partner = (
                    st.session_state.antwoorden_log.get("Question 8") == ja or
                    st.session_state.antwoorden_log.get("Question 10") == ja
                )

                # SPECIFIEKE UITZONDERINGS-ROUTING VOOR STAP 3
                if current_step == "Stap 3":
                    if "Question 10" in pagina_antwoorden:
                        bepalend_antwoord = pagina_antwoorden.get("Question 10")
                    else:
                        bepalend_antwoord = pagina_antwoorden.get("Question 8")
                    next_step = route_dict.get(str(bepalend_antwoord))

                # ROUTERING STAP 7: met partner → Stap 7a, zonder → Stap 7b
                elif current_step == "Stap 7":
                    next_step = "Stap 7a" if heeft_partner else "Stap 7b"

                # ROUTERING STAP 7b: met partner → Stap 7c, zonder → Stap 8
                elif current_step == "Stap 7b":
                    next_step = "Stap 7c" if heeft_partner else "Stap 8"

                # ROUTERING STAP 8: met partner → Stap 8a, zonder → Stap 9
                elif current_step == "Stap 8":
                    next_step = "Stap 8a" if heeft_partner else "Stap 9"

                # SPECIFIEKE UITZONDERINGS-ROUTING VOOR STAP 9
                # Q39=Nee → geen eigen woning → sla Stap 10 én 11 over
                # Q39=Ja  → altijd naar Stap 10 (Q50 staat daar als eerste vraag)
                # Q39=Ja, Q43=Nee → geen hypotheek eerste woning, maar Q50 bepaalt of Stap 10 nodig is
                elif current_step == "Stap 9":
                    ja  = q_vertaling.get("yes", "Ja")
                    q39 = pagina_antwoorden.get("Question 39")
                    q43 = pagina_antwoorden.get("Question 43")

                    if q39 == ja:
                        next_step = "Stap 10"          # altijd naar Stap 10, Q50 staat daar
                    elif q43 == ja:
                        next_step = "Stap 11"          # hypotheek maar geen eigen woning (edge case)
                    else:
                        next_step = "Stap 12"          # geen eigen woning, geen hypotheek

                # SPECIFIEKE UITZONDERINGS-ROUTING VOOR STAP 10
                # Q50=Nee én Q43=Nee → geen hypotheek op beide → sla Stap 11 over
                # Q50=Ja, Q54=Nee én Q43=Nee → idem
                elif current_step == "Stap 10":
                    ja  = q_vertaling.get("yes", "Ja")
                    q43 = st.session_state.antwoorden_log.get("Question 43")
                    q50 = pagina_antwoorden.get("Question 50")
                    q54 = pagina_antwoorden.get("Question 54")

                    if q43 == ja or q54 == ja:
                        next_step = "Stap 11"          # minstens één hypotheek → Stap 11
                    else:
                        next_step = "Stap 12"          # geen hypotheek op beide woningen → sla 11 over

                # STANDAARD ROUTERING VOOR ALLE OVERIGE STAPPEN
                elif "route_bepaling" in stap_info:
                    bepalende_vraag = stap_info["route_bepaling"]
                    gegeven_antwoord = pagina_antwoorden.get(bepalende_vraag)
                    next_step = route_dict.get(str(gegeven_antwoord))
                else:
                    next_step = stap_info.get("next_step")

                # AFHANDELING VAN DE VOLGENDE STAP IN DE STATE
                # Wis antwoorden van overgeslagen stappen
                stap_namen = list(STAPPEN.keys())
                if current_step in stap_namen and next_step in stap_namen:
                    current_idx = stap_namen.index(current_step)
                    next_idx    = stap_namen.index(next_step)
                    for i in range(current_idx + 1, next_idx):
                        overgeslagen = stap_namen[i]
                        for q_id in STAPPEN[overgeslagen].get("vragen", []):
                            if q_id in st.session_state.antwoorden_log:
                                del st.session_state.antwoorden_log[q_id]

                if next_step is None or next_step == "END" or next_step not in STAPPEN:
                    st.session_state.current_step = "END"
                    st.rerun()
                else:
                    st.session_state.current_step = next_step
                    st.rerun()
            else:
                st.warning(t["warning_empty"])
if current_step != "END":
    # [Hier draait de reguliere rendering van je stappen/vragen]
    pass
else:
    # EINDscherm bereikt
    st.success(t["success"])
    st.balloons()
    st.write(t["success_sub"])
    
    # Automatisch opslaan zodra het eindscherm geladen wordt (indien nog niet gedaan)
    if not st.session_state.data_verstuurd:
        with st.spinner(t["saving_db"]):
            success, msg = save_to_supabase(
                st.session_state.antwoorden_log,
                st.session_state.taal,
                st.session_state.user.id,
                JAAR,
                email=st.session_state.user.email
            )
            if success:
                st.session_state.data_verstuurd = True
                st.success(t["save_success"])
            else:
                st.error(f"{t['save_failed']} {msg}")

    if st.button(t["restart_btn"], type="primary"):
        st.session_state.clear()
        supabase.auth.sign_out()
        st.rerun()