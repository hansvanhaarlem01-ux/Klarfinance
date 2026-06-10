"""
modules/nextens.py
------------------
Alle communicatie met de Nextens Synchronization API v2.0.
Alleen importeren in admin-pagina's.

Ondersteunde flows (Persoon):
  - get_access_token()           — Bearer token ophalen via refresh_token
  - zoek_persoon_op_bsn()        — PUT v2/klant/person/byBsn
  - get_persoon()                — GET v2/klant/persoon/{id}
  - maak_persoon_aan()           — POST v2/klant/persoon
  - update_persoon()             — GET → merge → PUT v2/klant/persoon/{id}
  - bouw_persoon_payload()       — mapt Klar antwoorden naar Nextens velden

Beveiliging:
  - Access token wordt gecached in session_state (geldig 30 min)
  - Omgeving (productie / acceptatie) wordt meegegeven per aanroep
"""

import streamlit as st
import requests
from datetime import datetime, timedelta


# ── Endpoints ────────────────────────────────────────────────────────
_ENDPOINTS = {
    "Productie":  "https://api.nextens.nl",
    "Acceptatie": "https://apiacc.nextens.nl",
}
_TOKEN_URL = {
    "Productie":  "https://ids.nextens.nl/connect/token",
    "Acceptatie": "https://idsacc.nextens.nl/connect/token",
}


# ── Token ophalen ────────────────────────────────────────────────────
def get_access_token(omgeving: str = "Acceptatie") -> str | None:
    """
    Haalt een Bearer access token op via de Nextens Identity Server.
    Token wordt 25 minuten gecached in session_state (geldigheid is 30 min).
    """
    cache_key     = f"_nextens_token_{omgeving}"
    cache_exp_key = f"_nextens_token_exp_{omgeving}"

    # Controleer cache
    if cache_key in st.session_state:
        if datetime.now() < st.session_state[cache_exp_key]:
            return st.session_state[cache_key]

    try:
        client_id     = st.secrets["NEXTENS_CLIENT_ID"]
        client_secret = st.secrets["NEXTENS_CLIENT_SECRET"]
        refresh_token = st.secrets["NEXTENS_REFRESH_TOKEN"]
    except KeyError as e:
        st.error(f"⚠️ Nextens credentials ontbreken in secrets.toml: {e}")
        return None

    try:
        r = requests.post(
            _TOKEN_URL[omgeving],
            data={
                "grant_type":    "refresh_token",
                "client_id":     client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        if r.status_code == 200:
            token = r.json().get("access_token")
            st.session_state[cache_key]     = token
            st.session_state[cache_exp_key] = datetime.now() + timedelta(minutes=25)
            return token
        else:
            st.error(f"⚠️ Token ophalen mislukt: {r.status_code} — {r.text}")
            return None
    except Exception as e:
        st.error(f"⚠️ Verbindingsfout Nextens token: {e}")
        return None


def _headers(omgeving: str) -> dict | None:
    """Bouwt de Authorization header op. Geeft None terug als token ontbreekt."""
    token = get_access_token(omgeving)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _base(omgeving: str) -> str:
    return _ENDPOINTS[omgeving]


# ── Zoeken op BSN ────────────────────────────────────────────────────
def zoek_persoon_op_bsn(bsn: str, omgeving: str = "Acceptatie") -> dict:
    """
    Zoekt een persoon op BSN via PUT v2/klant/person/byBsn.
    Geeft {"ok": True, "data": {...}} of {"ok": False, "fout": "..."} terug.
    """
    headers = _headers(omgeving)
    if not headers:
        return {"ok": False, "fout": "Geen geldig token"}

    try:
        r = requests.put(
            f"{_base(omgeving)}/v2/klant/person/byBsn",
            json={"Bsn": bsn},
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            return {"ok": True, "data": r.json()}
        elif r.status_code == 409:
            return {"ok": False, "fout": "Niet gevonden"}
        else:
            return {"ok": False, "fout": f"Status {r.status_code}: {r.text}"}
    except Exception as e:
        return {"ok": False, "fout": str(e)}


# ── Persoon ophalen op ID ─────────────────────────────────────────────
def get_persoon(nextens_id: str, omgeving: str = "Acceptatie") -> dict:
    """
    Haalt een persoon op via GET v2/klant/persoon/{id}.
    Geeft {"ok": True, "data": {...}} of {"ok": False, "fout": "..."} terug.
    """
    headers = _headers(omgeving)
    if not headers:
        return {"ok": False, "fout": "Geen geldig token"}

    try:
        r = requests.get(
            f"{_base(omgeving)}/v2/klant/persoon/{nextens_id}",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            return {"ok": True, "data": r.json()}
        else:
            return {"ok": False, "fout": f"Status {r.status_code}: {r.text}"}
    except Exception as e:
        return {"ok": False, "fout": str(e)}


# ── Persoon aanmaken ─────────────────────────────────────────────────
def maak_persoon_aan(payload: dict, omgeving: str = "Acceptatie") -> dict:
    """
    Maakt een nieuwe persoon aan via POST v2/klant/persoon.
    Geeft {"ok": True, "nextens_id": "..."} of {"ok": False, "fout": "..."} terug.
    """
    headers = _headers(omgeving)
    if not headers:
        return {"ok": False, "fout": "Geen geldig token"}

    try:
        r = requests.post(
            f"{_base(omgeving)}/v2/klant/persoon",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if r.status_code == 201:
            nextens_id = r.json().get("Id")
            return {"ok": True, "nextens_id": nextens_id, "data": r.json()}
        elif r.status_code == 409:
            return {"ok": False, "fout": "Persoon bestaat al in Nextens (conflict op BSN of naam+geboortedatum)"}
        else:
            return {"ok": False, "fout": f"Status {r.status_code}: {r.text}"}
    except Exception as e:
        return {"ok": False, "fout": str(e)}


# ── Persoon updaten ──────────────────────────────────────────────────
def update_persoon(nextens_id: str, nieuw_payload: dict, omgeving: str = "Acceptatie") -> dict:
    """
    Update een persoon via PUT v2/klant/persoon/{id}.
    Haalt eerst de bestaande data op (GET), mergt dan de nieuwe velden
    zodat weggelaten velden niet worden leeggemaakt.
    Geeft {"ok": True} of {"ok": False, "fout": "..."} terug.
    """
    headers = _headers(omgeving)
    if not headers:
        return {"ok": False, "fout": "Geen geldig token"}

    # Stap 1: bestaande data ophalen
    huidig = get_persoon(nextens_id, omgeving)
    if not huidig["ok"]:
        return {"ok": False, "fout": f"Kan huidige data niet ophalen: {huidig['fout']}"}

    # Stap 2: merge — huidig als basis, overschrijven met nieuw_payload
    # Id en Opmerkingen worden nooit meegestuurd in PUT
    gemergd = {k: v for k, v in huidig["data"].items() if k not in ("Id", "Opmerkingen")}
    gemergd.update(nieuw_payload)

    try:
        r = requests.put(
            f"{_base(omgeving)}/v2/klant/persoon/{nextens_id}",
            json=gemergd,
            headers=headers,
            timeout=10,
        )
        if r.status_code == 204:
            return {"ok": True}
        elif r.status_code == 409:
            return {"ok": False, "fout": "Persoon niet gevonden in Nextens"}
        else:
            return {"ok": False, "fout": f"Status {r.status_code}: {r.text}"}
    except Exception as e:
        return {"ok": False, "fout": str(e)}


# ── Veldmapping: Klar → Nextens ──────────────────────────────────────
def bouw_persoon_payload(antwoorden: dict) -> dict:
    """
    Mapt Klar antwoorden naar een Nextens persoon payload.
    Lege / None waarden worden weggelaten.
    """
    def get(key):
        val = antwoorden.get(key)
        return str(val).strip() if val is not None and str(val).strip() else None

    # Geboortedatum omzetten van DD-MM-YYYY naar ISO 8601
    geboortedatum_raw = get("Question 6")
    geboortedatum_iso = None
    if geboortedatum_raw:
        try:
            geboortedatum_iso = datetime.strptime(geboortedatum_raw, "%d-%m-%Y").strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            pass

    mapping = {
        "Voornaam":               get("Question 2"),
        "Tussenvoegsels":         get("Question 3b"),
        "Achternaam":             get("Question 3"),
        "Geboortedatum":          geboortedatum_iso,
        "Bsn":                    get("Question 7"),
        "TelefoonnummerMobiel":   get("Question 4"),
        "EmailAdres":             get("Question 5"),
        "Straatnaam":             get("Question 42_straat"),
        "Huisnummer":             get("Question 42_huisnummer"),
        "HuisnummerToevoeging":   get("Question 42_toevoeging"),
        "Postcode":               get("Question 42_postcode"),
        "Plaats":                 get("Question 42_stad"),
        "LandCode":               "NLD",  # Standaard Nederland
    }

    # Verwijder lege waarden
    return {k: v for k, v in mapping.items() if v}


# ── Vergelijking Klar vs Nextens ─────────────────────────────────────
def vergelijk_payload(klar_payload: dict, nextens_data: dict) -> list[dict]:
    """
    Vergelijkt de Klar-payload met de Nextens-data.
    Geeft een lijst van verschillen terug:
    [{"veld": "...", "klar": "...", "nextens": "..."}]
    """
    verschillen = []
    for veld, klar_waarde in klar_payload.items():
        nextens_waarde = nextens_data.get(veld)
        # Normaliseer voor vergelijking
        klar_str    = str(klar_waarde).strip() if klar_waarde else ""
        nextens_str = str(nextens_waarde).strip() if nextens_waarde else ""
        if klar_str != nextens_str:
            verschillen.append({
                "Veld":    veld,
                "Klar":    klar_str or "—",
                "Nextens": nextens_str or "—",
            })
    return verschillen
