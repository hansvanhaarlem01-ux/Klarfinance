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

import io
import requests
import streamlit as st
from datetime import datetime
from supabase import create_client, Client

try:
    from PIL import Image, ImageOps
except ImportError:          # Pillow ontbreekt: verkleinen wordt overgeslagen
    Image = ImageOps = None

try:                          # iPhone-foto's (.heic) – optioneel
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# --- SUPABASE VERBINDING ---
try:
    _URL = st.secrets["SUPABASE_URL"].rstrip("/")
    _KEY = st.secrets["SUPABASE_KEY"].strip()
except KeyError:
    st.error("⚠️ Supabase configuratie ontbreekt. Voeg SUPABASE_URL en SUPABASE_KEY toe aan secrets.toml.")
    st.stop()

def _maak_client() -> Client:
    return create_client(_URL, _KEY)


def get_client() -> Client:
    """
    Geef de Supabase-client van DEZE browsersessie.

    Streamlit draait alle bezoekers als threads binnen één proces. Een client
    op moduleniveau wordt daardoor door iedereen gedeeld, en omdat inloggen het
    access token op die client zet, zou het token van de ene klant ook voor de
    andere gelden. Elke sessie krijgt daarom een eigen client in session_state.
    """
    try:
        client = st.session_state.get("_supabase_client")
        if client is None:
            client = _maak_client()
            st.session_state["_supabase_client"] = client
        return client
    except Exception:
        # Geen Streamlit-context (bijvoorbeeld in tests): losse client
        return _maak_client()

# Google Maps API key (optioneel – voor adresautocomplete)
try:
    GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
except KeyError:
    GOOGLE_MAPS_API_KEY = None


# --- UPLOAD-INSTELLINGEN ---
# Maximale bestandsgrootte die een klant mag uploaden (MB).
# Houd dit gelijk aan server.maxUploadSize in .streamlit/config.toml.
MAX_UPLOAD_MB = 25

# Bestandstypes die de uploadvelden accepteren (gebruikt door app.py).
TOEGESTANE_BESTANDSTYPES = ["pdf", "jpg", "jpeg", "png", "heic", "heif"]

# Telefoonfoto's worden verkleind voordat ze naar Storage gaan. Alleen
# bestanden boven _VERKLEIN_DREMPEL of breder/hoger dan _MAX_ZIJDE worden
# aangepakt, zodat kleine scherpe scans onaangeroerd blijven.
_MAX_ZIJDE        = 2000        # pixels op de langste zijde
_JPEG_KWALITEIT   = 85
_VERKLEIN_DREMPEL = 1_500_000   # bytes

_UPLOAD_FOUTEN = {
    "NL": {
        "te_groot": lambda naam, mb: (
            f"'{naam}' is {mb:.0f} MB en daarmee te groot (maximaal {MAX_UPLOAD_MB} MB). "
            "Maak de foto opnieuw met een lagere resolutie, of sla de scan op als PDF."
        ),
        "leeg": "Het bestand is leeg of kon niet gelezen worden. Probeer het opnieuw.",
    },
    "EN": {
        "te_groot": lambda naam, mb: (
            f"'{naam}' is {mb:.0f} MB, which is too large (maximum {MAX_UPLOAD_MB} MB). "
            "Please retake the photo at a lower resolution, or save the scan as a PDF."
        ),
        "leeg": "The file is empty or could not be read. Please try again.",
    },
}


# --- FUNCTIES ---

def _set_auth_token() -> Client:
    """
    Geef de client van deze sessie terug, met het token van de ingelogde
    gebruiker erop gezet (zodat RLS de juiste auth.uid() ziet).
    """
    client = get_client()
    try:
        access_token  = st.session_state.get("access_token")
        refresh_token = st.session_state.get("refresh_token")
        if access_token and refresh_token:
            client.auth.set_session(access_token, refresh_token)
    except Exception:
        pass
    return client


def save_to_supabase(
    answers_dict: dict,
    language: str,
    user_id: str,
    jaar: int,
    vragenlijst_type: str = "belastingaangifte",
    email: str = ""
) -> tuple[bool, str]:
    """
    Sla de ingevulde antwoorden op via de Supabase client (respecteert RLS).
    """
    try:
        client = _set_auth_token()
        payload = {
            "created_at": datetime.now().isoformat(),
            "taal": language,
            "antwoorden": answers_dict,
            "user_id": user_id,
            "jaar": jaar,
            "vragenlijst_type": vragenlijst_type,
            "email": email,
        }
        client.table("vragenlijsten").insert(payload).execute()
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
        client = _set_auth_token()

        # Stap 1: zoek antwoorden van hetzelfde jaar (hervatten)
        for zoekjaar in [jaar, jaar - 1]:
            result = (
                client.table("vragenlijsten")
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


def _schoon_bestandsnaam(naam: str) -> str:
    """
    Maak een bestandsnaam veilig voor gebruik in een Storage-pad.
    Alleen letters, cijfers, punt, streepje en underscore blijven over;
    de extensie blijft altijd behouden.
    """
    naam = naam.replace("\\", "/").split("/")[-1]

    basis, punt, extensie = naam.rpartition(".")
    if not punt:
        basis, extensie = naam, ""

    def _veilig(tekst: str) -> str:
        return "".join(
            c if ((c.isascii() and c.isalnum()) or c in "._-") else "_"
            for c in tekst
        )

    basis    = _veilig(basis).strip("._")[:100] or "bestand"
    extensie = _veilig(extensie).strip("._").lower()[:10]
    return f"{basis}.{extensie}" if extensie else basis


def _verklein_afbeelding(bestand_bytes: bytes, bestandsnaam: str) -> tuple[bytes, str]:
    """
    Verklein een foto tot maximaal _MAX_ZIJDE pixels en sla hem op als JPEG.
    Geeft (bytes, bestandsnaam) terug — bij twijfel altijd het origineel.
    """
    if Image is None:
        return bestand_bytes, bestandsnaam

    extensie = bestandsnaam.rsplit(".", 1)[-1].lower() if "." in bestandsnaam else ""
    if extensie not in ("jpg", "jpeg", "png", "heic", "heif"):
        return bestand_bytes, bestandsnaam

    try:
        afbeelding = Image.open(io.BytesIO(bestand_bytes))
        afbeelding.load()
    except Exception:
        return bestand_bytes, bestandsnaam   # geen (leesbare) afbeelding

    # HEIC altijd omzetten: Windows en de meeste PDF-tools openen het niet.
    moet_kleiner = (
        len(bestand_bytes) > _VERKLEIN_DREMPEL
        or max(afbeelding.size) > _MAX_ZIJDE
        or extensie in ("heic", "heif")
    )
    if not moet_kleiner:
        return bestand_bytes, bestandsnaam

    try:
        afbeelding = ImageOps.exif_transpose(afbeelding)   # rotatie van de telefoon
        if afbeelding.mode not in ("RGB", "L"):
            afbeelding = afbeelding.convert("RGB")
        afbeelding.thumbnail((_MAX_ZIJDE, _MAX_ZIJDE), Image.LANCZOS)

        buffer = io.BytesIO()
        afbeelding.save(buffer, format="JPEG", quality=_JPEG_KWALITEIT, optimize=True)
        nieuwe_bytes = buffer.getvalue()
    except Exception:
        return bestand_bytes, bestandsnaam

    # Alleen vervangen als het echt kleiner werd (HEIC hoe dan ook)
    if len(nieuwe_bytes) >= len(bestand_bytes) and extensie not in ("heic", "heif"):
        return bestand_bytes, bestandsnaam

    basis = bestandsnaam.rsplit(".", 1)[0] if "." in bestandsnaam else bestandsnaam
    return nieuwe_bytes, f"{basis}.jpg"


def upload_document(
    file,
    user_id: str,
    jaar: int,
    question_id: str,
    taal: str = "NL",
) -> tuple[bool, str]:
    """
    Upload een bestand naar Supabase Storage.
    Bestanden worden opgeslagen onder: {user_id}/{jaar}/{question_id}/{bestandsnaam}

    Bestanden groter dan MAX_UPLOAD_MB worden geweigerd, foto's worden eerst
    verkleind. Geeft (True, pad) terug bij succes, anders (False, foutmelding).
    """
    fouten = _UPLOAD_FOUTEN.get(taal, _UPLOAD_FOUTEN["NL"])

    try:
        # getvalue() leest de hele buffer, ook na een eerdere read()
        bestand_bytes = file.getvalue() if hasattr(file, "getvalue") else file.read()
    except Exception as e:
        return False, str(e)

    if not bestand_bytes:
        return False, fouten["leeg"]

    if len(bestand_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
        return False, fouten["te_groot"](file.name, len(bestand_bytes) / 1024 / 1024)

    bestand_bytes, bestandsnaam = _verklein_afbeelding(bestand_bytes, file.name)
    bestandsnaam = _schoon_bestandsnaam(bestandsnaam)

    try:
        client = _set_auth_token()
        pad = f"{user_id}/{jaar}/{question_id}/{bestandsnaam}"

        # Upload naar Supabase Storage (overschrijf als het al bestaat)
        client.storage.from_("documenten").upload(
            path=pad,
            file=bestand_bytes,
            file_options={"upsert": "true"}
        )
        return True, pad
    except Exception as e:
        return False, str(e)


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
