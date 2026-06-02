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

def save_to_supabase(
    answers_dict: dict,
    language: str,
    user_id: str,
    jaar: int,
    vragenlijst_type: str = "belastingaangifte"
) -> tuple[bool, str]:
    """
    Sla de ingevulde antwoorden op in Supabase.
    Geeft (True, "Succes") terug bij succes, anders (False, foutmelding).
    """
    url = f"{_URL}/rest/v1/vragenlijsten"
    headers = {
        "apikey": _KEY,
        "Authorization": f"Bearer {_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload = {
        "created_at": datetime.now().isoformat(),
        "taal": language,
        "antwoorden": answers_dict,
        "user_id": user_id,
        "jaar": jaar,
        "vragenlijst_type": vragenlijst_type,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code in [200, 201]:
            return True, "Succes"
        return False, f"Statuscode {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)


def load_previous_answers(
    user_id: str,
    jaar: int,
    vragenlijst_type: str = "belastingaangifte"
) -> dict | None:
    """
    Haal de antwoorden van het vorige jaar op voor deze gebruiker en vragenlijst-type.
    Geeft een dict terug, of None als er niets gevonden is.
    """
    try:
        result = (
            supabase.table("vragenlijsten")
            .select("antwoorden")
            .eq("user_id", user_id)
            .eq("jaar", jaar - 1)
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
