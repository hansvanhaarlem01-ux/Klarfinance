"""
modules/database.py
-------------------
Gedeelde Supabase-verbinding en database-functies.
Importeer dit in elke vragenlijst-pagina die data moet opslaan of laden.

Vereiste tabelkolommen in 'vragenlijsten':
  - created_at        (timestamptz)
  - taal              (text)
  - antwoorden        (jsonb)
  - user_id           (uuid)
  - jaar              (int4)
  - vragenlijst_type  (text)  ← voor als er meerdere vragenlijsten komen
"""

import requests
import streamlit as st
from datetime import datetime
from supabase import create_client, Client

# --- SUPABASE VERBINDING ---
try:
    _URL = st.secrets["SUPABASE_URL"].rstrip("/")
    _KEY = st.secrets["SUPABASE_KEY"].strip()
except KeyError:
    st.error("⚠️ Supabase configuratie ontbreekt. Voeg SUPABASE_URL en SUPABASE_KEY toe aan secrets.toml.")
    st.stop()

supabase: Client = create_client(_URL, _KEY)

# Google Maps API key (optioneel – voor adresautocomplete)
try:
    GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
except KeyError:
    GOOGLE_MAPS_API_KEY = None


# --- FUNCTIES ---

def _set_auth_token():
    """Zet de sessie van de ingelogde gebruiker op de Supabase client."""
    try:
        import streamlit as st
        access_token  = st.session_state.get("access_token")
        refresh_token = st.session_state.get("refresh_token")
        if access_token and refresh_token:
            supabase.auth.set_session(access_token, refresh_token)
    except Exception:
        pass


def save_to_supabase(
    answers_dict: dict,
    language: str,
    user_id: str,
    jaar: int,
    vragenlijst_type: str = "belastingaangifte"
) -> tuple[bool, str]:
    """
    Sla de ingevulde antwoorden op via de Supabase client (respecteert RLS).
    """
    try:
        _set_auth_token()
        payload = {
            "created_at": datetime.now().isoformat(),
            "taal": language,
            "antwoorden": answers_dict,
            "user_id": user_id,
            "jaar": jaar,
            "vragenlijst_type": vragenlijst_type,
        }
        supabase.table("vragenlijsten").insert(payload).execute()
        return True, "Succes"
    except Exception as e:
        return False, str(e)


def load_previous_answers(
    user_id: str,
    jaar: int,
    vragenlijst_type: str = "belastingaangifte",
) -> dict | None:
    """
    Laad antwoorden voor pre-populatie:
    1. Eerst zoeken naar het huidige jaar (hervatten)
    2. Als niets gevonden: zoeken naar vorig jaar (pre-populatie)
    Geeft een dict terug, of None als er niets gevonden is.
    """
    try:
        _set_auth_token()

        # Stap 1: zoek antwoorden van hetzelfde jaar (hervatten)
        for zoekjaar in [jaar, jaar - 1]:
            result = (
                supabase.table("vragenlijsten")
                .select("antwoorden")
                .eq("user_id", user_id)
                .eq("jaar", zoekjaar)
                .eq("vragenlijst_type", vragenlijst_type)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["antwoorden"]
    except Exception:
        pass
    return None


def upload_document(
    file,
    user_id: str,
    jaar: int,
    question_id: str,
) -> tuple[bool, str]:
    """
    Upload een bestand naar Supabase Storage.
    Bestanden worden opgeslagen onder: {user_id}/{jaar}/{question_id}/{bestandsnaam}

    Geeft (True, publieke_path) terug bij succes, anders (False, foutmelding).
    """
    try:
        _set_auth_token()
        bestandsnaam = file.name
        pad = f"{user_id}/{jaar}/{question_id}/{bestandsnaam}"
        bestand_bytes = file.read()

        # Upload naar Supabase Storage (overschrijf als het al bestaat)
        supabase.storage.from_("documenten").upload(
            path=pad,
            file=bestand_bytes,
            file_options={"upsert": "true"}
        )
        return True, pad
    except Exception as e:
        return False, str(e)


def get_document_url(pad: str, geldig_seconden: int = 3600) -> str | None:
    """
    Genereer een tijdelijke download-URL voor een opgeslagen document.
    Standaard geldig voor 1 uur.
    """
    try:
        result = supabase.storage.from_("documenten").create_signed_url(
            path=pad,
            expires_in=geldig_seconden
        )
        return result.get("signedURL")
    except Exception:
        return None


def google_address_autocomplete(search_term: str) -> list[str]:
    """
    Geeft een lijst met adressuggesties via de Google Places API.
    Werkt alleen als GOOGLE_MAPS_API_KEY in secrets.toml staat.
    """
    if not GOOGLE_MAPS_API_KEY or not search_term or len(search_term) < 3:
        return []
    url = (
        f"https://maps.googleapis.com/maps/api/place/autocomplete/json"
        f"?input={search_term}&types=address&key={GOOGLE_MAPS_API_KEY}"
    )
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            return [p["description"] for p in response.json().get("predictions", [])]
    except Exception:
        pass
    return []
