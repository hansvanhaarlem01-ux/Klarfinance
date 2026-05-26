import streamlit as st
import re
from datetime import datetime

# Stel de pagina in (titel en Klår Finance branding hint)
st.set_page_config(page_title="Klår Finance - Vragenlijst", page_icon="💼", layout="centered")

JAAR = datetime.now().year - 1

# Jouw exacte Questions dictionary (met een paar kleine typo-fixes in de keys)
Questions = {
    "Question 1": {
        "text": "Ik ga akkoord met verwerking van mijn gegevens t.b.v. de voorbereiding en indiening van mijn aangifte inkomstenbelasting door Klår Finance.",
        "toelichting": "Voor privacyverklaring zie: https://klarfinance.nl/privacy-policy/",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": "Question 2" 
    },
    "Question 2": {"text": "Voornaam", "type": "text", "route": "Question 3"},
    "Question 3": {"text": "Achternaam", "type": "text", "route": "Question 4"},
    "Question 4": {"text": "Telefoonnummer", "type": "phonenumber", "route": "Question 5"},
    "Question 5": {"text": "E-mailadres", "type": "emailadress", "route": "Question 6"},
    "Question 6": {"text": "Wat is je geboortedatum?", "type": "datum", "route": "Question 7"},
    "Question 7": {
        "text": "Wat is uw burgerservicenummer (BSN)?",
        "type": "BSN",
        "route": "Question 8"
    },
    "Question 8": {
        "text": "Bent u getrouwd of zit u in een geregistreerd partnerschap?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 9", "Nee": "Question 10"} 
    },
    "Question 9": {
        "text": "Wat is uw trouwdatum of datum van geregistreerd partnerschap?",
        "type": "datum",
        "route": "Question 12"
    },
    "Question 10": {
        "text": f"Heeft u in {JAAR} een fiscaal partner?",
        "toelichting": f"Je bent fiscale partners als je aan één van de volgende voorwaarden voldoet: je bent getrouwd of geregistreerd partner; je woont samen en hebt samen een kind... Twijfel je? Kies 'Ja' als jullie ook in {JAAR - 1} als fiscale partners aangifte deden.",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 11", "Nee": "Question 16"}  
    },
    "Question 11": {"text": "Wat is de voornaam van uw partner?", "type": "text", "route": "Question 12"},
    "Question 12": {"text": "Wat is de achternaam van uw partner?", "type": "text", "route": "Question 13"},
    "Question 13": {"text": "Wat is het telefoonnummer van uw partner?", "type": "phonenumber", "route": "Question 14"},
    "Question 14": {"text": "Wat is het e-mailadres van uw partner?", "type": "emailadress", "route": "Question 15"}, # Fixed typo route hier
    "Question 15": {"text": "Wat is het burgerservicenummer (BSN) van uw partner?", "type": "BSN", "route": "Question 16"},
    "Question 16": {
        "text": f"Had u in {JAAR} één of meerdere thuiswonende kinderen?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 17", "Nee": "Question 19"}
    },
    "Question 17": {"text": "Wat is de naam van uw jongste nog thuiswonende kind?", "type": "text", "route": "Question 18"},
    "Question 18": {"text": "Wat is de geboortedatum van uw jongste nog thuiswonende kind?", "type": "datum", "route": "Question 19"},
    "Question 19": {
        "text": f"Waar woonde u in {JAAR}?",
        "type": "choice",
        "options": [f"Heel {JAAR} in Nederland", f"Een gedeelte van {JAAR} in Nederland en een gedeelte in het buitenland", f"Heel {JAAR} in het buitenland"],
        "route": {f"Heel {JAAR} in Nederland": "Question 28", f"Een gedeelte van {JAAR} in Nederland en een gedeelte in het buitenland": "Question 20", f"Heel {JAAR} in het buitenland": "Question 28"}
    },
    "Question 20": {
        "text": f"Was er in {JAAR} sprake van immigratie (naar Nederland) of emigratie (uit Nederland)?",
        "type": "choice",
        "options": ["Immigratie", "Emigratie"],
        "route": {"Immigratie": "Question 21", "Emigratie": "Question 24"} # Fixed typo route
    },
    "Question 21": {"text": "Wat is de datum van uw fysieke aankomst in Nederland?", "type": "datum", "route": "Question 22"},
    "Question 22": {
        "text": "Wat is de datum van uw registratie in Nederland?",
        "toelichting": "Dit is de datum waarop u zich officieel heeft ingeschreven bij de gemeente in Nederland.",
        "type": "datum",
        "route": "Question 23"
    },
    "Question 23": {"text": "Wat is het land van herkomst?", "type": "text", "route": "Question 28"},
    "Question 24": {"text": "Wat is de datum van uw fysieke vertrek uit Nederland?", "type": "datum", "route": "Question 26"},
    "Question 26": {
        "text": "Wat is de datum van uw uitschrijving in Nederland?",
        "toelichting": "Dit is de datum waarop u zich officieel heeft uitgeschreven bij de gemeente in Nederland.",
        "type": "datum",
        "route": "Question 27"
    },
    "Question 27": {"text": "Wat is het land van bestemming?", "type": "text", "route": "Question 28"},
    "Question 28": {
        "text": f"Had u in {JAAR} inkomsten uit loondienst?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 29", "Nee": "Question 33"}
    },
    "Question 29": {"text": f"Bij hoeveel verschillende werkgevers had u in {JAAR} een dienstverband?", "type": "int", "route": "Question 30"},
    "Question 30": {"text": f"Upload de jaaropgave van uw werkgever(s) voor {JAAR}.", "type": "bestand", "route": "Question 31"},
    "Question 31": {
        "text": f"Was in {JAAR} de 30%-regeling van toepassing?",
        "toelichting": "De 30%-regeling is een fiscale regeling voor kennismigranten.",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 32", "Nee": "Question 33"}
    },
    "Question 32": {"text": "Upload de beschikking 30%-regeling.", "type": "bestand", "route": "Question 33"},
    "Question 33": {
        "text": f"Was u in {JAAR} zelfstandig ondernemer in een eenmanszaak, vof of maatschap?",
        "toelichting": "Heeft u een BV, beantwoord deze vraag dan met 'Nee'.",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 34", "Nee": "Question 39"}
    },
    "Question 34": {
        "text": "Wat is de rechtsvorm van uw onderneming?",
        "type": "choice",
        "options": ["Eenmanszaak", "VOF", "Maatschap", "Overige rechtsvorm"],
        "route": "Question 35"
    },
    "Question 35": {"text": "Wat is het KvK-nummer van uw onderneming?", "type": "kvk-nummer", "route": "Question 36"},
    "Question 36": {"text": "In welk boekhoudprogramma houdt u de administratie bij?", "type": "text", "route": "Question 37"},
    "Question 37": {"text": f"Upload de winst- en verliesrekening {JAAR}.", "type": "bestand", "route": "Question 38"},
    "Question 38": {
        "text": f"Heeft u in {JAAR} méér dan 1.225 uur besteed aan uw onderneming?",
        "type": "choice",
        "options": ["Ja", "Nee", "Ik weet het niet zeker"],
        "route": "Question 39"
    },
    "Question 39": {
        "text": f"Had u in {JAAR} een eigen woning (hoofdverblijf)?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 40", "Nee": "Question 65"}
    },
    "Question 40": {
        "text": "Is deze woning alleen van u?",
        "type": "choice",
        "options": ["Ja, ik ben de enige eigenaar", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)", "Nee, er is nog een andere eigenaar (niet mijn partner)."],
        "route": {"Ja, ik ben de enige eigenaar": "Question 42", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)": "Question 42", "Nee, er is nog een andere eigenaar (niet mijn partner).": "Question 41"}
    },
    "Question 41": {"text": "Wie is er nog meer eigenaar van uw eigen woning?", "type": "text", "route": "Question 42"},
    "Question 42": {"text": "Wat is het adres van uw eigen woning?", "type": "text", "route": "Question 43"},
    "Question 43": {
        "text": "Heeft u een hypotheek op deze eigen woning?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 44", "Nee": "Question 65"}
    },
    "Question 44": {"text": f"Upload de jaaropgave van uw hypotheekverstrekker voor {JAAR}.", "type": "bestand", "route": "Question 45"},
    "Question 45": {
        "text": f"Heeft u in {JAAR} deze woning gekocht of verkocht?",
        "type": "choice",
        "options": ["Ja, gekocht", "Ja, verkocht", "Nee"],
        "route": {"Ja, gekocht": "Question 46", "Ja, verkocht": "Question 48", "Nee": "Question 50"}
    },
    "Question 46": {"text": "Wat is de datum van de aankoop van uw woning?", "type": "datum", "route": "Question 47"},
    "Question 47": {"text": "Upload de notarisafrekening van de aankoop.", "type": "bestand", "route": "Question 48"},
    "Question 48": {"text": "Wat is de datum van de verkoop van uw woning?", "type": "datum", "route": "Question 49"},
    "Question 49": {"text": "Upload de notarisafrekening van de verkoop.", "type": "bestand", "route": "Question 50"},
    "Question 50": {
        "text": f"Had u in {JAAR} nóg een eigen woning (hoofdverblijf)?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 51", "Nee": "Question 63"}
    },
    "Question 51": {
        "text": "Is deze woning alleen van u?",
        "type": "choice",
        "options": ["Ja, ik ben de enige eigenaar", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)", "Nee, er is nog een andere eigenaar (niet mijn partner)."],
        "route": {"Ja, ik ben de enige eigenaar": "Question 53", "Nee, de woning is eigendom van mij en mijn fiscaal partner (50%-50%)": "Question 53", "Nee, er is nog een andere eigenaar (niet mijn partner).": "Question 52"}
    },
    "Question 52": {"text": "Wie is er nog meer eigenaar?", "type": "text", "route": "Question 53"},
    "Question 53": {"text": "Wat is het adres van deze woning?", "type": "text", "route": "Question 54"},
    "Question 54": {
        "text": "Heeft u een hypotheek op deze eigen woning?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 55", "Nee": "Question 56"}
    },
    "Question 55": {"text": f"Upload de jaaropgave van uw hypotheekverstrekker voor {JAAR}.", "type": "bestand", "route": "Question 56"},
    "Question 56": {
        "text": f"Heeft u in {JAAR} deze woning gekocht of verkocht?",
        "type": "choice",
        "options": ["Ja, gekocht", "Ja, verkocht", "Nee"],
        "route": {"Ja, gekocht": "Question 57", "Ja, verkocht": "Question 60", "Nee": "Question 63"}
    },
    "Question 57": {"text": "Wat is de datum van de aankoop?", "type": "datum", "route": "Question 58"},
    "Question 58": {"text": "Upload de notarisafrekening van de aankoop.", "type": "bestand", "route": "Question 59"},
    "Question 59": {"text": f"Upload de factuur van de taxatie van de nieuwe woning voor {JAAR}.", "type": "bestand", "route": "Question 63"},
    "Question 60": {"text": "Vanaf welke datum woon je niet meer in deze woning?", "type": "datum", "route": "Question 61"},
    "Question 61": {"text": "Upload de notarisafrekening van de verkoop.", "type": "bestand", "route": "Question 62"},
    "Question 62": {"text": "Upload de factuur van de taxatie van de oude woning.", "type": "bestand", "route": "Question 63"},
    "Question 63": {
        "text": f"Heeft u in {JAAR} uw hypotheek overgesloten?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 64", "Nee": "Question 65"}
    },
    "Question 64": {"text": "Upload de notarisafrekening van de oversluiting.", "type": "bestand", "route": "Question 65"},
    "Question 65": {
        "text": f"Had u in {JAAR} een aanmerkelijk belang in een BV/NV?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 66", "Nee": "Question 71"}
    },
    "Question 66": {"text": f"Wat is de naam van deze BV/NV en hoeveel aandelen bezat u?", "type": "text", "route": "Question 67"},
    "Question 67": {
        "text": f"Heeft u in {JAAR} aandelen in deze BV/NV verkocht of gekocht?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 68", "Nee": "Question 71"}
    },
    "Question 68": {"text": "Hoeveel aandelen heeft u gekocht/verkocht?", "type": "text", "route": "Question 69"},
    "Question 69": {
        "text": f"Heeft u in {JAAR} dividend ontvangen van deze BV/NV?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 70", "Nee": "Question 71"}
    },
    "Question 70": {"text": f"Hoeveel was het bruto ontvangen dividend in {JAAR}?", "type": "int", "route": "Question 71"},
    "Question 71": {
        "text": f"Had u in {JAAR} Nederlandse bankrekeningen en/of Nederlandse beleggingen?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 72", "Nee": "Question 73"}
    },
    "Question 72": {"text": f"Upload de jaaroverzichten {JAAR} van al uw Nederlandse rekeningen.", "type": "bestand", "route": "Question 73"},
    "Question 73": {"text": f"Bezat u in {JAAR} crypto en/of vorderingen?", "type": "text", "route": "Question 74"},
    "Question 74": {
        "text": f"Had u in {JAAR} overig onroerend goed in Nederland (niet de eigen woning)?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 75", "Nee": "Question 82"} # Fixed typo key in original (Questions 75 -> Question 75)
    },
    "Question 75": {"text": "Wat is het adres van dit onroerend goed?", "type": "text", "route": "Question 76"},
    "Question 76": {
        "text": f"Werd dit overig onroerend goed in {JAAR} verhuurd?",
        "type": "choice",
        "options": ["Ja, vaste verhuur", "Ja, vakantieverhuur", "Nee"],
        "route": {"Ja, vaste verhuur": "Question 77", "Ja, vakantieverhuur": "Question 77", "Nee": "Question 79"}
    },
    "Question 77": {"text": "Is het onroerend goed verhuurd aan een familielid?", "type": "choice", "options": ["Ja", "Nee"], "route": "Question 78"},
    "Question 78": {"text": "Wat was de kale huurprijs per maand?", "type": "int", "route": "Question 79"},
    "Question 79": {"text": "Betaalt u jaarlijks erfpacht?", "type": "choice", "options": ["Ja", "Nee"], "route": {"Ja": "Question 80", "Nee": "Question 81"}},
    "Question 80": {"text": f"What was de erfpachtcanon in {JAAR}?", "type": "int", "route": "Question 81"},
    "Question 81": {"text": "Kan dit onroerend goed afzonderlijk worden verkocht?", "type": "choice", "options": ["Ja", "Nee"], "route": "Question 82"},
    "Question 82": {
        "text": f"Had u Nederlandse schulden in {JAAR}?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 83", "Nee": "Question 84"}
    },
    "Question 83": {"text": f"Upload jaaropgaven {JAAR} van uw Nederlandse schulden.", "type": "bestand", "route": "Question 84"},
    "Question 84": {
        "text": f"Had u in {JAAR} buitenlandse bankrekeningen en/of buitenlandse beleggingen?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 85", "Nee": "Question 86"}
    },
    "Question 85": {"text": f"Upload de jaaroverzichten {JAAR} van uw buitenlandse rekeningen.", "type": "bestand", "route": "Question 86"},
    "Question 86": {
        "text": f"Had u in {JAAR} onroerend goed in het buitenland?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 87", "Nee": "Question 90"}
    },
    "Question 87": {"text": "Wat is het adres?", "type": "text", "route": "Question 88"},
    "Question 88": {"text": f"Wat was de waarde op 1-1-{JAAR}?", "type": "text", "route": "Question 89"},
    "Question 89": {"text": "Is er onroerend goed gekocht of verkocht?", "type": "text", "route": "Question 90"},
    "Question 90": {
        "text": f"Had u buitenlandse schulden in {JAAR}?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 91", "Nee": "Question 92"}
    },
    "Question 91": {"text": "Omschrijf de buitenlandse schulden.", "type": "text", "route": "Question 92"},
    "Question 92": {
        "text": f"Had u buitenlands inkomen in {JAAR}?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 93", "Nee": "Question 96"}
    },
    "Question 93": {
        "text": "Wat was de bron?",
        "type": "choice",
        "options": ["Inkomen uit loondienst", "Inkomen als zelfstandige", "Pensioen", "Anders"],
        "route": {"Inkomen uit loondienst": "Question 94", "Inkomen als zelfstandige": "Question 95", "Pensioen": "Question 96", "Anders": "Question 97"}
    },
    "Question 94": {"text": "Is er belasting ingehouden?", "type": "choice", "options": ["Ja", "Nee", "Weet ik niet zeker"], "route": "Question 95"},
    "Question 95": {"text": "Upload bewijs buitenlands inkomen.", "type": "bestand", "route": "Question 96"},
    "Question 96": {
        "text": f"Heeft u meer dan EUR 60 gedoneerd aan goede doelen in {JAAR}?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 97", "Nee": "Question 98"}
    },
    "Question 97": {"text": "Vermeld per goed doel het bedrag.", "type": "text", "route": "Question 98"},
    "Question 98": {
        "text": f"Heeft u in {JAAR} buitengewone zorgkosten betaald?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 99", "Nee": "Question 100"}
    },
    "Question 99": {"text": "Vermeld per soort zorgkosten het bedrag.", "type": "text", "route": "Question 100"},
    "Question 100": {
        "text": "Volgt u een dieet op voorschrift?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 101", "Nee": "Question 102"}
    },
    "Question 101": {"text": "Om welk dieet gaat het?", "type": "text", "route": "Question 102"},
    "Question 102": {
        "text": f"Ontving u in {JAAR} een voorlopige aanslag?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 103", "Nee": "Question 104"}
    },
    "Question 103": {"text": "Upload kopie voorlopige aanslag.", "type": "bestand", "route": "Question 104"},
    "Question 104": {
        "text": "Wilt u nog aanvullende documenten uploaden?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 105", "Nee": "Question 106"}
    },
    "Question 105": {"text": "Upload hier aanvullende documenten.", "type": "bestand", "route": "Question 106"},
    "Question 106": {
        "text": "Heeft u nog opmerkingen of vragen?",
        "type": "choice",
        "options": ["Ja", "Nee"],
        "route": {"Ja": "Question 107", "Nee": "Question 106"} # Stuurt door naar einde
    },
    "Question 107": {"text": "Vermeld uw opmerkingen.", "type": "text", "route": None}
}

# --- INITIALISATIE VAN DE STATE ---
if "current_id" not in st.session_state:
    st.session_state.current_id = "Question 1"
if "antwoorden_log" not in st.session_state:
    st.session_state.antwoorden_log = {}
if "history" not in st.session_state:
    st.session_state.history = []

st.title("Belastingaangifte Vragenlijst")
st.write("Vul de onderstaande vragen zo nauwkeurig mogelijk in.")

# Check of we aan het einde zijn
current_id = st.session_state.current_id

if current_id and current_id in Questions:
    vraag = Questions[current_id]
    v_type = vraag.get("type", "text")

    # Toon voortgang (optioneel, indicatie)
    st.caption(f"Actieve stap: {current_id}")
    
    # De Vraag en Toelichting
    st.subheader(vraag["text"])
    if "toelichting" in vraag:
        st.info(vraag["toelichting"])

    # Input elementen op basis van het type
    antwoord = None
    input_key = f"input_{current_id}" # Unieke key per vraag voor Streamlit

    if v_type == "choice":
        # Gebruik een index = None (of selectbox met placeholder) zodat men bewust kiest
        antwoord = st.radio("Maak een keuze:", vraag["options"], key=input_key)

    elif v_type == "int":
        antwoord = st.number_input("Voer een cijfer in:", step=1, value=1, key=input_key)

    elif v_type == "bestand":
        # Verwerkt direct bestanden online!
        uploaded_file = st.file_uploader("Kies een bestand...", key=input_key)
        if uploaded_file:
            antwoord = uploaded_file.name  # Sla voor nu de bestandsnaam op in de log

    elif v_type == "datum":
        # Streamlit heeft een ingebouwde datumkiezer, maar we kunnen ook tekst + regex doen zoals jouw code:
        antwoord_veld = st.text_input("Formaat: DD-MM-YYYY", placeholder="01-01-1990", key=input_key)
        if re.match(r'^\d{2}-\d{2}-\d{4}$', antwoord_veld):
            antwoord = antwoord_veld
        elif antwoord_veld:
            st.error("Ongeldig formaat. Gebruik DD-MM-YYYY.")

    elif v_type == "BSN":
        antwoord_veld = st.text_input("Uw 9-cijferige BSN:", key=input_key)
        if antwoord_veld.isdigit() and len(antwoord_veld) == 9:
            antwoord = antwoord_veld
        elif antwoord_veld:
            st.error("Een BSN bestaat uit exact 9 cijfers.")

    elif v_type == "emailadress":
        antwoord_veld = st.text_input("E-mailadres:", key=input_key)
        if "@" in antwoord_veld and "." in antwoord_veld:
            antwoord = antwoord_veld
        elif antwoord_veld:
            st.error("Voer een geldig e-mailadres in.")

    elif v_type == "phonenumber":
        antwoord_veld = st.text_input("Telefoonnummer:", key=input_key)
        if antwoord_veld.isdigit() and len(antwoord_veld) >= 10:
            antwoord = antwoord_veld
        elif antwoord_veld:
            st.error("Voer een geldig telefoonnummer in (minimaal 10 cijfers).")

    elif v_type == "kvk-nummer":
        antwoord_veld = st.text_input("KvK-nummer (9 cijfers):", key=input_key)
        if antwoord_veld.isdigit() and len(antwoord_veld) == 9:
            antwoord = antwoord_veld
        elif antwoord_veld:
            st.error("Een KvK-nummer bestaat uit exact 9 cijfers.")

    else:  # Standaard vrije tekst
        antwoord_veld = st.text_input("Uw antwoord:", key=input_key)
        if antwoord_veld.strip():
            antwoord = antwoord_veld.strip()

    # Knoppen voor navigatie
    col1, col2 = st.columns([1, 4])
    
    with col1:
        # Vorige knop (om terug te kunnen bladeren)
        if len(st.session_state.history) > 0:
            if st.button("Vorige"):
                last_id = st.session_state.history.pop()
                st.session_state.current_id = last_id
                st.rerun()

    with col2:
        # Volgende knop
        if st.button("Volgende ➡️"):
            if antwoord is not None:
                # Sla antwoord op
                st.session_state.antwoorden_log[current_id] = antwoord
                st.session_state.history.append(current_id)
                
                # Bepaal de volgende route
                route = vraag["route"]
                if isinstance(route, dict):
                    next_id = route.get(str(antwoord))
                else:
                    next_id = route

                # Als de route 'Question 106' (Nee) direct moet stoppen of naar het einde gaat:
                if next_id is None or next_id not in Questions:
                    st.session_state.current_id = "END"
                else:
                    st.session_state.current_id = next_id
                
                st.rerun()
            else:
                st.warning("Vul aanzienlijk eerst een geldig antwoord in voordat u verder gaat.")

else:
    # EINDscherm
    st.success("🎉 Bedankt voor het invullen van de vragenlijst!")
    st.balloons()
    st.write("Uw antwoorden zijn veilig opgeslagen.")
    
    # Toon het resultaat aan de gebruiker (In productie kun je dit weglaten of direct naar een database sturen)
    st.json(st.session_state.antwoorden_log)
    
    if st.button("Opnieuw beginnen"):
        st.session_state.current_id = "Question 1"
        st.session_state.antwoorden_log = {}
        st.session_state.history = []
        st.rerun()