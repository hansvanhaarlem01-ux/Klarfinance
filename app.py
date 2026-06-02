import streamlit as st
import re
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
        export_records_excel, VRAAG_LABELS, STAPPEN_ADMIN
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
        st.write(""); st.write("")
        zoek_geklikt = st.button("🔍 Zoek", type="primary", use_container_width=True)

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
                use_container_width=True)

        df_overzicht = pd.DataFrame([{
            "#": i + 1, "Email": r.get("email", "—"), "Jaar": r.get("jaar", ""),
            "Type": r.get("vragenlijst_type", ""),
            "Ingevuld op": (r.get("created_at") or "")[:10], "Taal": r.get("taal", ""),
        } for i, r in enumerate(records)])

        event = st.dataframe(df_overzicht, use_container_width=True, hide_index=True,
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

current_step = st.session_state.current_step

# ── Uploader-knoptekst (taalafhankelijk) ──────────────────────────
inject_uploader_label(st.session_state.taal or "NL")

# --- TAALSELECTIE SCHERM ---
if st.session_state.taal is None:
    st.title("Belastingaangifte Vragenlijst / Tax Return Questionnaire")
    st.write("Kies uw gewenste taal / Please select your preferred language:")
    
    col_nl, col_en = st.columns(2)
    with col_nl:
        if st.button("🇳🇱 Nederlands", use_container_width=True):
            st.session_state.taal = "NL"
            st.rerun()
    with col_en:
        if st.button("🇬🇧 English", use_container_width=True):
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
        "Stap 6": "Waar u woonde",
        "Stap 7": "Inkomen uit loondienst",
        "Stap 8": "Inkomen uit ondernemerschap",
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
        "Stap 8": "Income from entrepreneurship",
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
        "warning_empty": "Vul een geldig antwoord in voordat u verder gaat.",
        "success": "🎉 Bedankt voor het invullen van de vragenlijst!",
        "success_sub": "Uw antwoorden zijn veilig opgeslagen.",
        "restart_btn": "Opnieuw beginnen",
        "error_date": "Ongeldig formaat. Gebruik DD-MM-YYYY.",
        "error_privacy": "⚠️ U dient akkoord te gaan met de privacyverklaring om verder te kunnen gaan.",
        "error_file": "Eerder geüpload bestand",
        "error_bsn": "Een BSN bestaat uit exact 9 cijfers.",
        "error_email": "Voer een geldig e-mailadres in.",
        "error_phone": "Voer een geldig telefoonnummer in (minimaal 10 cijfers).",
        "error_kvk": "Een KvK-nummer bestaat uit exact 9 cijfers.",
        "table_col1" : "Naam",
        "table_col2" : "Bedrag/Aantal",
        "string_field": "Uw antwoord:",
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
        "warning_empty": "Please provide a valid answer before proceeding.",
        "success": "🎉 Thank you for completing the questionnaire!",
        "success_sub": "Your answers have been securely saved.",
        "restart_btn": "Start over",
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
        "upload_messsage": "Select a file...",
        "int_message": "Enter a number:",
        "saving_db": "Saving data to database...",
        "save_success": "✅ Data successfully saved!",
        "save_failed": "❌ Saving failed: ",
        "add_row_btn": "Add a row"
    }
}
QUESTIONS_TRANSLATION = {
    "NL": {
        "Q1_text": "Ik ga akkoord met verwerking van mijn gegevens t.b.v. de voorbereiding en indiening van mijn aangifte inkomstenbelasting door Klår Finance.",
        "Q1_toelicht": "Voor privacyverklaring zie: https://klarfinance.nl/privacy-policy/",
        "Q2_text": "Voornaam",
        "Q3_text": "Achternaam",
        "Q4_text": "Telefoonnummer",
        "Q5_text": "E-mailadres",
        "Q6_text": "Wat is je geboortedatum?",
        "Q7_text": "Wat is uw burgerservicenummer (BSN)?",
        "Q8_text": "Bent u getrouwd of zit u in een geregistreerd partnerschap?",
        "Q9_text": "Wat is uw trouwdatum of datum van geregistreerd partnerschap?",
        "Q10_text": f"Heeft u in {JAAR} een fiscaal partner?",
        "Q10_toelicht": f"Je bent fiscale partners als je aan één van de volgende voorwaarden voldoet:\n- je bent getrouwd of geregistreerd partner;\n- je woont samen en hebt samen een kind;\n- Twijfel je? Kies 'Ja' als jullie ook in {JAAR - 1} als fiscale partners aangifte deden.",
        "Q11_text": "Wat is de voornaam van uw partner?",
        "Q12_text": "Wat is de achternaam van uw partner?",
        "Q13_text": "Wat is het telefoonnummer van uw partner?",
        "Q14_text": "Wat is het e-mailadres van uw partner?",
        "Q15_text": "Wat is het burgerservicenummer (BSN) van uw partner?",
        "Q16_text": f"Had u in {JAAR} één of meerdere thuiswonende kinderen?",
        "Q17_text": "Wat is de naam van uw jongste nog thuiswonende kind?",
        "Q18_text": "Wat is de geboortedatum van uw jongste nog thuiswonende kind?",
        "Q19_text": f"Waar woonde u in {JAAR}?",
        "Q19_opt1": f"Heel {JAAR} in Nederland",
        "Q19_opt2": f"Een gedeelte van {JAAR} in Nederland en een gedeelte in het buitenland",
        "Q19_opt3": f"Heel {JAAR} in het buitenland",
        "Q20_text": f"Was er in {JAAR} sprake van immigratie (naar Nederland) of emigratie (uit Nederland)?",
        "Q20_opt1": "Immigratie",
        "Q20_opt2": "Emigratie",
        "Q21_text": "Wat is de datum van uw fysieke aankomst in Nederland?",
        "Q22_text": "Wat is de datum van uw registratie in Nederland?",
        "Q22_toelicht": "Dit is de datum waarop u zich officieel heeft ingeschreven bij de gemeente in Nederland.",
        "Q23_text": "Wat is het land van herkomst?",
        "Q24_text": "Wat is de datum van uw fysieke vertrek uit Nederland?",
        "Q26_text": "Wat is de datum van uw uitschrijving in Nederland?",
        "Q26_toelicht": "Dit is de datum waarop u zich officieel heeft uitgeschreven bij de gemeente in Nederland.",
        "Q27_text": "Wat is het land van bestemming?",
        "Q28_text": f"Had u in {JAAR} inkomsten uit loondienst?",
        "Q29_text": f"Bij hoeveel verschillende werkgevers had u in {JAAR} een dienstverband?",
        "Q30_text": f"Upload de jaaropgave van uw werkgever(s) voor {JAAR}.",
        "Q31_text": f"Was in {JAAR} de 30%-regeling van toepassing?",
        "Q31_toelicht": "De 30%-regeling is een fiscale regeling voor kennismigranten.",
        "Q32_text": "Upload de beschikking 30%-regeling.",
        "Q33_text": f"Was u in {JAAR} zelfstandig ondernemer in een eenmanszaak, vof of maatschap?",
        "Q33_toelicht": "Heeft u een BV, beantwoord deze vraag dan met 'Nee'.",
        "Q34_text": "Wat is de rechtsvorm van uw onderneming?",
        "Q34_opts": ["Eenmanszaak", "VOF", "Maatschap", "Overige rechtsvorm"],
        "Q35_text": "Wat is het KvK-nummer van uw onderneming?",
        "Q36_text": "In welk boekhoudprogramma houdt u de administratie bij?",
        "Q37_text": f"Upload de winst- en verliesrekening {JAAR}.",
        "Q38_text": f"Heeft u in {JAAR} méér dan 1.225 uur besteed aan uw onderneming?",
        "Q38_opts": ["Ja", "Nee", "Ik weet het niet zeker"],
        "Q39_text": f"Had u in {JAAR} een eigen woning (hoofdverblijf)?",
        "Q40_text": "Is deze woning alleen van u?",
        "Q40_opts": ["Ja, ik ben de enige eigenaar", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)", "Nee, er is nog een andere eigenaar (niet mijn partner)."],
        "Q41_text": "Wie is er nog meer eigenaar van uw eigen woning?",
        "Q42_text": "Wat is het adres van uw eigen woning?",
        "Q43_text": "Heeft u een hypotheek op deze eigen woning?",
        "Q44_text": f"Upload de jaaropgave van uw hypotheekverstrekker voor {JAAR}.",
        "Q45_text": f"Heeft u in {JAAR} deze woning gekocht of verkocht?",
        "Q45_opts": ["Ja, gekocht", "Ja, verkocht", "Nee"],
        "Q46_text": "Wat is de datum van de aankoop van uw woning?",
        "Q47_text": "Upload de notarisafrekening van de aankoop.",
        "Q48_text": "Wat is de datum van de verkoop van uw woning?",
        "Q49_text": "Upload de notarisafrekening van de verkoop.",
        "Q50_text": f"Had u in {JAAR} nóg een eigen woning (hoofdverblijf)?",
        "Q51_text": "Is deze woning alleen van u?",
        "Q51_opts": ["Ja, ik ben de enige eigenaar", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)", "Nee, er is nog een andere eigenaar (niet mijn partner)."],
        "Q52_text": "Wie is er nog meer eigenaar?",
        "Q53_text": "Wat is het adres van deze woning?",
        "Q54_text": "Heeft u een hypotheek op deze eigen woning?",
        "Q55_text": f"Upload de jaaropgave van uw hypotheekverstrekker voor {JAAR}.",
        "Q56_text": f"Heeft u in {JAAR} deze woning gekocht of verkocht?",
        "Q56_opts": ["Ja, gekocht", "Ja, verkocht", "Nee"],
        "Q57_text": "Wat is de datum van de aankoop?",
        "Q58_text": "Upload de notarisafrekening van de aankoop.",
        "Q59_text": f"Upload de factuur van de taxatie van de nieuwe woning voor {JAAR}.",
        "Q60_text": "Vanaf welke datum woon je niet meer in deze woning?",
        "Q61_text": "Upload de notarisafrekening van de verkoop.",
        "Q62_text": "Upload de factuur van de taxatie van de oude woning.",
        "Q63_text": f"Heeft u in {JAAR} uw hypotheek overgesloten?",
        "Q64_text": "Upload de notarisafrekening van de oversluiting.",
        "Q65_text": f"Had u in {JAAR} een aanmerkelijk belang in een BV/NV?",
        "Q66_text": f"Wat is de naam van deze BV/NV en hoeveel aandelen bezat u?",
        "Q66_col1": "Naam",
        "Q66_col2": "Bedrag/Aantal",
        "Q67_text": f"Heeft u in {JAAR} aandelen in deze BV/NV verkocht of gekocht?",
        "Q67_opts": ["Nee", "Ja, verkocht", "Ja, gekocht"],
        "Q68_text": "Hoeveel aandelen heeft u gekocht/verkocht?",
        "Q69_text": f"Heeft u in {JAAR} dividend ontvangen van deze BV/NV?",
        "Q70_text": f"Hoeveel was het bruto ontvangen dividend in {JAAR}?",
        "Q71_text": f"Had u in {JAAR} Nederlandse bankrekeningen en/of Nederlandse beleggingen?",
        "Q72_text": f"Upload de jaaroverzichten {JAAR} van al uw Nederlandse rekeningen.",
        "Q72_toelicht": "Upload hier de jaaroverzichten van al uw Nederlandse bankrekeningen en beleggingsrekeningen. U kunt meerdere bestanden tegelijk selecteren door Ctrl ingedrukt te houden (Windows) of ⌘ Cmd (Mac) terwijl u de bestanden aanklikt.",
        "Q73_text": f"Bezat u in {JAAR} crypto en/of vordering(en) zoals een lening aan derden?",
        "Q73b_text": "Vermeld hieronder de omschrijving en waarde per bezitting.",
        "Q73b_col1": "Omschrijving",
        "Q73b_col2": f"Waarde 1-1-{JAAR} (€)",
        "Q73b_col3": f"Waarde 31-12-{JAAR} (€)",
        "Q74_text": f"Had u in {JAAR} overig onroerend goed in Nederland (niet de eigen woning)?",
        "Q75_text": "Wat is het adres van dit onroerend goed?",
        "Q76_text": f"Werd dit overig onroerend goed in {JAAR} verhuurd?",
        "Q76_opts": ["Ja, vaste verhuur", "Ja, vakantieverhuur", "Nee"],
        "Q77_text": "Is het onroerend goed verhuurd aan een familielid?",
        "Q79_text": "Betaalt u jaarlijks erfpacht?",
        "Q80_text": f"Wat was de erfpachtcanon in {JAAR}?",
        "Q81_text": "Kan dit onroerend goed afzonderlijk worden verkocht?",
        "Q82_text": f"Had u Nederlandse schulden in {JAAR}?",
        "Q83_text": f"Upload jaaropgaven {JAAR} van uw Nederlandse schulden.",
        "Q83_toelicht": "Upload hier de jaaropgaven van al uw Nederlandse schulden, zoals een studieschuld, persoonlijke lening of krediet. U kunt meerdere bestanden tegelijk selecteren door Ctrl ingedrukt te houden (Windows) of ⌘ Cmd (Mac) terwijl u de bestanden aanklikt.",
        "Q84_text": f"Had u in {JAAR} buitenlandse bankrekeningen en/of buitenlandse beleggingen?",
        "Q85_text": f"Upload de jaaroverzichten {JAAR} van uw buitenlandse rekeningen.",
        "Q85_toelicht": "Upload hier de jaaroverzichten van al uw buitenlandse bankrekeningen en beleggingsrekeningen. U kunt meerdere bestanden tegelijk selecteren door Ctrl ingedrukt te houden (Windows) of ⌘ Cmd (Mac) terwijl u de bestanden aanklikt.",
        "Q86_text": f"Had u in {JAAR} onroerend goed in het buitenland?",
        "Q87_text": "Wat is het adres?",
        "Q88_text": f"Wat was de waarde op 1-1-{JAAR}?",
        "Q89_text": "Is er onroerend goed gekocht of verkocht?",
        "Q90_text": f"Had u buitenlandse schulden in {JAAR}?",
        "Q91_text": "Omschrijf de buitenlandse schulden.",
        "Q92_text": f"Had u buitenlands inkomen in {JAAR}?",
        "Q93_text": "Wat was de bron?",
        "Q93_opts": ["Inkomen uit loondienst", "Inkomen als zelfstandige", "Pensioen", "Anders"],
        "Q94_text": "Is er belasting ingehouden?",
        "Q94_opts": ["Ja", "Nee", "Weet ik niet zeker"],
        "Q95_text": "Upload bewijs buitenlands inkomen.",
        "Q96_text": f"Heeft u meer dan EUR 60 gedoneerd aan goede doelen in {JAAR}?",
        "Q97_text": "Vermeld per goed doel het bedrag.",
        "Q98_text": f"Heeft u in {JAAR} buitengewone zorgkosten betaald?",
        "Q99_text": "Vermeld per soort zorgkosten het bedrag.",
        "Q100_text": "Volgt u een dieet op voorschrift?",
        "Q101_text": "Om welk dieet gaat het?",
        "Q102_text": f"Ontving u in {JAAR} een voorlopige aanslag?",
        "Q103_text": "Upload kopie voorlopige aanslag.",
        "Q104_text": "Wilt u nog aanvullende documenten uploaden?",
        "Q105_text": "Upload hier aanvullende documenten.",
        "Q106_text": "Heeft u nog opmerkingen of vragen?",
        "Q107_text": "Vermeld uw opmerkingen.",
        "yes": "Ja",
        "no": "Nee"
    },
    "EN": {
        "Q1_text": "I agree to the processing of my data for the preparation and submission of my income tax return by Klår Finance.",
        "Q1_toelicht": "For our privacy policy see: https://klarfinance.nl/privacy-policy/",
        "Q2_text": "First name",
        "Q3_text": "Last name",
        "Q4_text": "Phone number",
        "Q5_text": "Email address",
        "Q6_text": "What is your date of birth?",
        "Q7_text": "What is your citizen service number (BSN)?",
        "Q8_text": "Are you married or in a registered partnership?",
        "Q9_text": "What is the date of your marriage or registered partnership?",
        "Q10_text": f"Did you have a tax partner in {JAAR}?",
        "Q10_toelicht": f"You are tax partners if you meet at least one of the following conditions:\n- you are married or registered partners;\n- you live together and have a child together;\n- In doubt? Choose 'Yes' if you also filed as tax partners in {JAAR - 1}.",
        "Q11_text": "What is your partner's first name?",
        "Q12_text": "What is your partner's last name?",
        "Q13_text": "What is your partner's phone number?",
        "Q14_text": "What is your partner's email address?",
        "Q15_text": "What is your partner's citizen service number (BSN)?",
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
        "Q23_text": "What is the country of origin?",
        "Q24_text": "What is the date of your physical departure from the Netherlands?",
        "Q26_text": "What is the date of your deregistration in the Netherlands?",
        "Q26_toelicht": "This is the date you officially deregistered from the municipality in the Netherlands.",
        "Q27_text": "What is the country of destination?",
        "Q28_text": f"Did you have income from employment in {JAAR}?",
        "Q29_text": f"With how many different employers were you employed in {JAAR}?",
        "Q30_text": f"Upload the annual tax statement (jaaropgave) from your employer(s) for {JAAR}.",
        "Q31_text": f"Was the 30% ruling applicable in {JAAR}?",
        "Q31_toelicht": "The 30% ruling is a tax advantage for highly skilled migrants.",
        "Q32_text": "Upload the 30% ruling decision letter.",
        "Q33_text": f"Were you self-employed in a sole proprietorship, VOF, or partnership in {JAAR}?",
        "Q33_toelicht": "If you own a BV, please answer 'No'.",
        "Q34_text": "What is the legal form of your business?",
        "Q34_opts": ["Sole proprietorship (Eenmanszaak)", "VOF", "Partnership (Maatschap)", "Other legal form"],
        "Q35_text": "What is the Chamber of Commerce (KvK) number of your business?",
        "Q36_text": "Which accounting software do you use?",
        "Q37_text": f"Upload the profit and loss statement for {JAAR}.",
        "Q38_text": f"Did you spend more than 1,225 hours on your business in {JAAR}?",
        "Q38_opts": ["Yes", "No", "I am not entirely sure"],
        "Q39_text": f"Did you own a home (primary residence) in {JAAR}?",
        "Q40_text": "Is this property solely owned by you?",
        "Q40_opts": ["Yes, I am the sole owner", "No, the property is jointly owned by me and my tax partner (50%-50%)", "No, there is another owner (not my partner)."],
        "Q41_text": "Who else owns your primary residence?",
        "Q42_text": "What is the address of your primary residence?",
        "Q43_text": "Do you have a mortgage on this primary residence?",
        "Q44_text": f"Upload the annual mortgage statement from your lender for {JAAR}.",
        "Q45_text": f"Did you buy or sell this property in {JAAR}?",
        "Q45_opts": ["Yes, bought", "Yes, sold", "No"],
        "Q46_text": "What is the date of purchase of your home?",
        "Q47_text": "Upload the notary settlement statement of the purchase.",
        "Q48_text": "What is the date of sale of your home?",
        "Q49_text": "Upload the notary settlement statement of the sale.",
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
        "Q58_text": "Upload the notary settlement statement of the purchase.",
        "Q59_text": f"Upload the valuation/appraisal invoice of the new property for {JAAR}.",
        "Q60_text": "As of what date did you stop living in this property?",
        "Q61_text": "Upload the notary settlement statement of the sale.",
        "Q62_text": "Upload the valuation/appraisal invoice of the old property.",
        "Q63_text": f"Did you refinance your mortgage in {JAAR}?",
        "Q64_text": "Upload the notary settlement statement of the refinancing.",
        "Q65_text": f"Did you hold a substantial interest (aanmerkelijk belang) in a BV/NV in {JAAR}?",
        "Q66_text": "What is the name of this BV/NV and how many shares did you hold?",
        "Q66_col1": "Name",
        "Q66_col2": "Amount/Quantity",
        "Q67_text": f"Did you buy or sell shares in this BV/NV in {JAAR}?",
        "Q67_opts": ["No", "Yes, sold", "Yes, bought"],
        "Q68_text": "How many shares did you buy/sell?",
        "Q69_text": f"Did you receive dividends from this BV/NV in {JAAR}?",
        "Q70_text": f"What was the gross dividend received in {JAAR}?",
        "Q71_text": f"Did you have Dutch bank accounts and/or Dutch investments in {JAAR}?",
        "Q72_text": f"Upload the annual statements for {JAAR} of all your Dutch accounts.",
        "Q72_toelicht": "Upload the annual statements of all your Dutch bank accounts and investment accounts. You can select multiple files at once by holding Ctrl (Windows) or ⌘ Cmd (Mac) while clicking the files.",
        "Q73_text": f"Did you own crypto and/or receivables (such as a loan to third parties) in {JAAR}?",
        "Q73b_text": "Please list the description and value of each asset below.",
        "Q73b_col1": "Description",
        "Q73b_col2": f"Value 1-1-{JAAR} (€)",
        "Q73b_col3": f"Value 31-12-{JAAR} (€)",
        "Q74_text": f"Did you own other real estate in the Netherlands (not the primary residence) in {JAAR}?",
        "Q75_text": "What is the address of this real estate?",
        "Q76_text": f"Was this other real estate rented out in {JAAR}?",
        "Q76_opts": ["Yes, long-term rental", "Yes, holiday rental", "No"],
        "Q77_text": "Is the property rented out to a family member?",
        "Q79_text": "Do you pay ground rent (erfpacht) annually?",
        "Q80_text": f"What was the ground rent canon in {JAAR}?",
        "Q81_text": "Can this real estate be sold separately?",
        "Q82_text": f"Did you have Dutch debts in {JAAR}?",
        "Q83_text": f"Upload annual statements for {JAAR} of your Dutch debts.",
        "Q83_toelicht": "Upload the annual statements of all your Dutch debts, such as a student loan, personal loan, or credit. You can select multiple files at once by holding Ctrl (Windows) or ⌘ Cmd (Mac) while clicking the files.",
        "Q84_text": f"Did you have foreign bank accounts and/or foreign investments in {JAAR}?",
        "Q85_text": f"Upload the annual statements for {JAAR} of your foreign accounts.",
        "Q85_toelicht": "Upload the annual statements of all your foreign bank accounts and investment accounts. You can select multiple files at once by holding Ctrl (Windows) or ⌘ Cmd (Mac) while clicking the files.",
        "Q86_text": f"Did you own real estate abroad in {JAAR}?",
        "Q87_text": "What is the address?",
        "Q88_text": f"What was the value on 1-1-{JAAR}?",
        "Q89_text": "Was any real estate bought or sold?",
        "Q90_text": f"Did you have foreign debts in {JAAR}?",
        "Q91_text": "Describe the foreign debts.",
        "Q92_text": f"Did you have foreign income in {JAAR}?",
        "Q93_text": "What was the source?",
        "Q93_opts": ["Income from employment", "Income as self-employed", "Pension", "Other"],
        "Q94_text": "Was tax withheld?",
        "Q94_opts": ["Yes", "No", "Not entirely sure"],
        "Q95_text": "Upload proof of foreign income.",
        "Q96_text": f"Did you donate more than EUR 60 to charities in {JAAR}?",
        "Q97_text": "Please state the amount per charity.",
        "Q98_text": f"Did you pay extraordinary healthcare expenses in {JAAR}?",
        "Q99_text": "Please state the amount per type of healthcare expense.",
        "Q100_text": "Are you on a prescribed diet?",
        "Q101_text": "Which diet is it?",
        "Q102_text": f"Did you receive a provisional tax assessment (voorlopige aanslag) in {JAAR}?",
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
        "start_subtitle": "### Fijn dat u er bent.",
        "start_body": "Met deze digitale vragenlijst verzamelen we snel en efficiënt alle benodigde gegevens voor uw aangifte. Zo weet u zeker dat u geen aftrekposten mist.",
        "start_info": """
### 📋 Wat kunt u verwachten en wat heeft u nodig?

Het invullen van de vragenlijst duurt ongeveer **10 tot 15 minuten**. U kunt tussendoor op elk moment terugbladeren om antwoorden aan te passen.

**Zorg dat u de volgende zaken bij de hand heeft:**
- Uw **9-cijferige BSN** (en eventueel die van uw partner)
- Inkomensgegevens of jaaropgaven

---
*🔒 Uw gegevens worden volledig versleuteld en strikt conform de AVG verwerkt.*
        """,
        "start_button": "🚀 Start nu de vragenlijst",
        "main_title": "Belastingaangifte Vragenlijst",
        "main_subtitle": "Vul de onderstaande vragen zo nauwkeurig mogelijk in."
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
        "main_subtitle": "Please answer the questions below as accurately as possible."
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
    "Question 21": {
        "text": q_vertaling.get("Q21_text"),
        "type": "datum",
        "depends_on": {
            "question": "Question 20",
            "expected_value": q_vertaling.get("Q20_opt1") # Matcht op Immigratie / Immigration
        },
    },
    "Question 22": {
        "text": q_vertaling.get("Q22_text"),
        "toelichting": q_vertaling.get("Q22_toelicht"),
        "type": "datum",
        "depends_on": {
            "question": "Question 20",
            "expected_value": q_vertaling.get("Q20_opt1")
        },
    },
    "Question 23": {
        "text": q_vertaling.get("Q23_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 20",
            "expected_value": q_vertaling.get("Q20_opt1")
        },
    },
    "Question 24": {
        "text": q_vertaling.get("Q24_text"),
        "type": "datum",
        "depends_on": {
            "question": "Question 20",
            "expected_value": q_vertaling.get("Q20_opt2") # Matcht op Emigratie / Emigration
        },
    },
    "Question 26": {
        "text": q_vertaling.get("Q26_text"),
        "toelichting": q_vertaling.get("Q26_toelicht"),
        "type": "datum",
        "depends_on": {
            "question": "Question 20",
            "expected_value": q_vertaling.get("Q20_opt2")
        },
    },
    "Question 27": {
        "text": q_vertaling.get("Q27_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 20",
            "expected_value": q_vertaling.get("Q20_opt2")
        },
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
        "depends_on": {
            "question": "Question 31",
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
        "type": "bestand",
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
        "depends_on": {
            "question": "Question 40",
            "expected_value": q_vertaling.get("Q40_opts")[2] # Matcht op de 3e optie (andere eigenaar)
        },
    },
    "Question 42": {
        "text": q_vertaling.get("Q42_text"),
        "type": "text",
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
        "depends_on": {
            "question": "Question 43",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
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
        "depends_on": {
            "question": "Question 45",
            "expected_value": q_vertaling.get("Q45_opts")[0] # Gekocht
        },
    },
    "Question 47": {
        "text": q_vertaling.get("Q47_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 45",
            "expected_value": q_vertaling.get("Q45_opts")[0]
        },
    },
    "Question 48": {
        "text": q_vertaling.get("Q48_text"),
        "type": "datum",
        "depends_on": {
            "question": "Question 45",
            "expected_value": q_vertaling.get("Q45_opts")[1] # Verkocht
        },
    },
    "Question 49": {
        "text": q_vertaling.get("Q49_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 45",
            "expected_value": q_vertaling.get("Q45_opts")[1]
        },
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
        "depends_on": {
            "question": "Question 51",
            "expected_value": q_vertaling.get("Q51_opts")[2]
        },
    },
    "Question 53": {
        "text": q_vertaling.get("Q53_text"),
        "type": "text",
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
        "depends_on": {
            "question": "Question 54",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
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
        "depends_on": {
            "question": "Question 56",
            "expected_value": q_vertaling.get("Q56_opts")[0]
        },
    },
    "Question 58": {
        "text": q_vertaling.get("Q58_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 56",
            "expected_value": q_vertaling.get("Q56_opts")[0]
        },
    },
    "Question 59": {
        "text": q_vertaling.get("Q59_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 56",
            "expected_value": q_vertaling.get("Q56_opts")[0]
        },
    },
    "Question 60": {
        "text": q_vertaling.get("Q60_text"),
        "type": "datum",
        "depends_on": {
            "question": "Question 56",
            "expected_value": q_vertaling.get("Q56_opts")[1]
        },
    },
    "Question 61": {
        "text": q_vertaling.get("Q61_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 56",
            "expected_value": q_vertaling.get("Q56_opts")[1]
        },
    },
    "Question 62": {
        "text": q_vertaling.get("Q62_text"),
        "type": "bestand",
        "depends_on": {
            "question": "Question 56",
            "expected_value": q_vertaling.get("Q56_opts")[1]
        },
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
        "options": q_vertaling.get("Q67_opts"),
        "depends_on": {
            "question": "Question 65",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 68": {
        "text": q_vertaling.get("Q68_text"),
        "type": "int",
        "depends_on": [
            {"question": "Question 65", "expected_value": q_vertaling.get("yes", "Ja")},
            {"question": "Question 67", "expected_value_not": q_vertaling.get("Q67_opts", ["Nee"])[0]},
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
        "type": "int",
        "depends_on": {
            "question": "Question 69",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
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
        "type": "text",
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
        "depends_on": {
            "question": "Question 79",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
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
    "Question 86": {
        "text": q_vertaling.get("Q86_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 87": {
        "text": q_vertaling.get("Q87_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 86",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 88": {
        "text": q_vertaling.get("Q88_text"),
        "type": "int",
        "depends_on": {
            "question": "Question 86",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 89": {
        "text": q_vertaling.get("Q89_text"),
        "type": "text",
        "depends_on": {
            "question": "Question 86",
            "expected_value": q_vertaling.get("yes", "Ja")
        },
    },
    "Question 90": {
        "text": q_vertaling.get("Q90_text"),
        "type": "choice",
        "options": JA_NEE_OPTIES,
    },
    "Question 91": {
        "text": q_vertaling.get("Q91_text"),
        "type": "tabel",
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
        "type": "bestand",
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
        "vragen": ["Question 2", "Question 3", "Question 4", "Question 5", "Question 6","Question 7"],
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
        "vragen": ["Question 11","Question 12","Question 13","Question 14","Question 15"],
        "next_step": "Stap 5"
    },
    "Stap 5": {
        "titel": s_vertaling.get("Stap 5", "Thuiswonende kinderen"),
        "vragen": ["Question 16","Question 17","Question 18"],
        "next_step": "Stap 6"
    },
    "Stap 6": {
        "titel": s_vertaling.get("Stap 6", "Waar u woonde"),
        "vragen": ["Question 19", "Question 20", "Question 21", "Question 22", "Question 23", "Question 24", "Question 25", "Question 27"],
        "next_step": "Stap 7"
    },
    "Stap 7": {
        "titel": s_vertaling.get("Stap 7", "Inkomen uit loondienst"),
        "vragen": ["Question 28", "Question 29", "Question 30", "Question 31", "Question 32"],
        "next_step": "Stap 8"
    },
    "Stap 8": {
        "titel": s_vertaling.get("Stap 8", "Inkomen uit ondernemerschap"),
        "vragen": ["Question 33", "Question 34", "Question 35", "Question 36", "Question 37", "Question 38"],
        "next_step": "Stap 9"
    },
    "Stap 9": {
        "titel": s_vertaling.get("Stap 9", "Eigen woonverblijf"),
        "vragen": ["Question 39", "Question 40", "Question 41", "Question 42", "Question 43", "Question 44", "Question 45", "Question 46", "Question 47", "Question 48", "Question 49"],
    },
    "Stap 10": {
        "titel": s_vertaling.get("Stap 10", "Tweede eigen woonverblijf"),
        "vragen": ["Question 50", "Question 51", "Question 52", "Question 53", "Question 54", "Question 55", "Question 56", "Question 57", "Question 58", "Question 59", "Question 60", "Question 61", "Question 62"],
    },
    "Stap 11": {
        "titel": s_vertaling.get("Stap 11", "Hypotheek"),
        "vragen": ["Question 63", "Question 64"],
        "next_step": "Stap 12"
    },
    "Stap 12": {
        "titel": s_vertaling.get("Stap 12", "Aanmerkelijk belang"),
        "vragen": ["Question 65", "Question 66", "Question 67", "Question 68", "Question 69", "Question 70"],
        "next_step": "Stap 13"
    },
    "Stap 13": {
        "titel": s_vertaling.get("Stap 13", "Sparen"),
        "vragen": ["Question 71", "Question 72", "Question 73", "Question 73b"],
        "next_step": "Stap 14"
    },
    "Stap 14": {
        "titel": s_vertaling.get("Stap 14", "Tweede eigen woonverblijf"),
        "vragen": ["Question 74", "Question 75", "Question 76", "Question 77", "Question 78", "Question 79", "Question 80", "Question 81"],
        "next_step": "Stap 15"
    },
    "Stap 15": {
        "titel": s_vertaling.get("Stap 15", "Overig"),
        "vragen": ["Question 82", "Question 83"],
        "next_step": "Stap 16"
    },
    "Stap 16": {
        "titel": s_vertaling.get("Stap 16", "Buitenlands vermogen, beleggingen, schulden en inkomen"),
        "vragen": ["Question 84", "Question 85", "Question 86", "Question 87", "Question 88", "Question 89", "Question 90", "Question 91", "Question 92", "Question 93", "Question 94", "Question 95"],
        "next_step": "Stap 17"
    },
    "Stap 17": {
        "titel": s_vertaling.get("Stap 17", "Aftrekposten"),
        "vragen": ["Question 98", "Question 99", "Question 96", "Question 97", "Question 100", "Question 101"],
        "next_step": "Stap 18"
    },
    "Stap 18": {
        "titel": s_vertaling.get("Stap 18", "Afronding"),
        "vragen": ["Question 102", "Question 103", "Question 104", "Question 105", "Question 106", "Question 107"],
        "next_step": None
    }
}


# --- 1. DE STARTPAGINA 
if current_step == "START":
    st.title(Start_vertaling["start_title"])
    st.write(Start_vertaling["start_subtitle"])
    
    st.write(Start_vertaling["start_body"])
    
    st.info(Start_vertaling["start_info"])
    
    st.write("##") 
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(Start_vertaling["start_button"], use_container_width=True, type="primary"):
            # Laad antwoorden van vorig jaar als die er zijn (eenmalig)
            if not st.session_state.previous_loaded:
                vorige_antwoorden = load_previous_answers(st.session_state.user.id, JAAR)
                if vorige_antwoorden:
                    st.session_state.antwoorden_log = vorige_antwoorden
                st.session_state.previous_loaded = True
            st.session_state.current_step = "Stap 1"
            st.rerun()

# --- 2. DE WERKELIJKE VRAGENLIJST (Hier tonen we de formuliertitels) ---
elif current_step and current_step in STAPPEN:
    scroll_to_top()
    stap_info = STAPPEN[current_step]
    with st.container(key=f"focus_reset_{current_step.replace(' ', '_')}"):
        st.caption(f"{t['caption']}: {current_step}")
        st.subheader(stap_info["titel"])
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
                actueel_antwoord = st.session_state.antwoorden_log.get(target_vraag) or pagina_antwoorden.get(target_vraag)

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
            antwoord_veld = st.text_input("Uw 9-cijferige BSN:", value=default_val, key=input_key)
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
            antwoord = dynamic_list_input(
                key=input_key,
                col1_label=vraag.get("col1", t["table_col1"]),
                col2_label=vraag.get("col2", t["table_col2"]),
                add_btn_label=t["add_row_btn"],
                default_value=bestaand_antwoord if isinstance(bestaand_antwoord, list) else None
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
        if st.button(t["next_btn"]):
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
                st.session_state.antwoorden_log.update(pagina_antwoorden)
                st.session_state.history.append(current_step)
                
                next_step = None
                route_dict = stap_info.get("route", {})
                
                # SPECIFIEKE UITZONDERINGS-ROUTING VOOR STAP 3
                if current_step == "Stap 3":
                    if "Question 10" in pagina_antwoorden:
                        bepalend_antwoord = pagina_antwoorden.get("Question 10")
                    else:
                        bepalend_antwoord = pagina_antwoorden.get("Question 8")
                    next_step = route_dict.get(str(bepalend_antwoord))

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

    # Toon het JSON logboek (optioneel)
    st.json(st.session_state.antwoorden_log)
    
    # Opnieuw beginnen reset ook de verstuur-status
    if st.button(t["restart_btn"]):
        st.session_state.clear()
        st.rerun()