"""
modules/admin_db.py
-------------------
Admin Supabase client (service role key — bypasses RLS) en helper functies
voor zoeken, recordweergave en export.
Alleen importeren in admin-pagina's.
"""

import io
import streamlit as st
import pandas as pd
from supabase import create_client, Client

# ── Admin Supabase client ─────────────────────────────────────────
try:
    _URL         = st.secrets["SUPABASE_URL"].rstrip("/")
    _SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
    admin_supabase: Client = create_client(_URL, _SERVICE_KEY)
except Exception:
    admin_supabase = None


# ── Buitenlands onroerend goed (herhaalbaar blok, zie app.py) ─────
# Moet overeenkomen met MAX_OG_BUITENLAND / og_id() in app.py
MAX_OG_BUITENLAND = 5

def _og_id(basis: str, k: int) -> str:
    return f"Question {basis}" if k == 1 else f"Question {basis}_{k}"

def _og_buitenland_labels() -> dict:
    labels = {}
    for k in range(1, MAX_OG_BUITENLAND + 1):
        nr = "" if k == 1 else f" ({k})"
        labels[_og_id("86", k)]  = "Onroerend goed in buitenland" + nr
        labels[_og_id("87", k)]  = "Adres buitenlands onroerend goed" + nr
        labels[_og_id("88", k)]  = "Waarde buitenlands onroerend goed 1-1" + nr
        labels[_og_id("88b", k)] = "Volledig eigendom buitenlands onroerend goed" + nr
        labels[_og_id("88c", k)] = "Eigendomspercentage buitenlands onroerend goed" + nr
        labels[_og_id("86b", k)] = "Hypotheek/schuld buitenlands onroerend goed" + nr
        labels[_og_id("86c", k)] = "Jaaropgave hypotheek/schuld buitenlands onroerend goed" + nr
        labels[_og_id("89", k)]  = "Aankoop / verkoop buitenlands onroerend goed" + nr
        labels[_og_id("89b", k)] = "Datum aankoop/verkoop buitenlands onroerend goed" + nr
        labels[_og_id("89c", k)] = "Bedrag aankoop/verkoop buitenlands onroerend goed" + nr
    return labels


# ── Vraag-labels (NL) ────────────────────────────────────────────
VRAAG_LABELS = {
    "Question 1":   "Privacy akkoord",
    "Question 2":   "Voornaam",
    "Question 3b":  "Tussenvoegsels",
    "Question 3":   "Achternaam",
    "Question 4":   "Telefoonnummer",
    "Question 5":   "E-mailadres",
    "Question 6":   "Geboortedatum",
    "Question 7":   "BSN",
    "Question 7b":  "Nationaliteit",
    "Question 7c":  "Adres",
    "Question 8":   "Getrouwd / geregistreerd partnerschap",
    "Question 9":   "Trouwdatum / datum partnerschap",
    "Question 10":  "Fiscaal partner",
    "Question 11":  "Voornaam partner",
    "Question 11b": "Tussenvoegsels partner",
    "Question 12":  "Achternaam partner",
    "Question 13":  "Telefoonnummer partner",
    "Question 14":  "E-mailadres partner",
    "Question 15":  "BSN partner",
    "Question 15b": "Nationaliteit partner",
    "Question 16":  "Thuiswonende kinderen",
    "Question 17":  "Naam jongste kind",
    "Question 18":  "Geboortedatum jongste kind",
    "Question 19":  "Woonplaats",
    "Question 20":  "Immigratie of emigratie",
    "Question 21":  "Datum fysieke aankomst NL",
    "Question 22":  "Datum registratie NL",
    "Question 23":  "Land van inwonerschap vóór komst naar NL",
    "Question 24":  "Datum fysiek vertrek NL",
    "Question 26":  "Datum uitschrijving NL",
    "Question 27":  "Land van bestemming",
    "Question 28":  "Inkomsten uit loondienst",
    "Question 29":  "Aantal werkgevers",
    "Question 30":  "Jaaropgave werkgever(s)",
    "Question 31":  "30%-regeling",
    "Question 32":  "Beschikking 30%-regeling",
    "Question 28p": "Loondienst partner",
    "Question 29p": "Aantal werkgevers partner",
    "Question 30p": "Jaaropgave werkgever(s) partner",
    "Question 31p": "30%-regeling partner",
    "Question 32p": "Beschikking 30%-regeling partner",
    "Question 32b":  "Inkomsten uitkering / pensioen / lijfrente",
    "Question 32c":  "Jaaropgaven uitkering / pensioen / lijfrente",
    "Question 32bp": "Inkomsten uitkering / pensioen / lijfrente partner",
    "Question 32cp": "Jaaropgaven uitkering / pensioen / lijfrente partner",
    "Question 33":  "Zelfstandig ondernemer",
    "Question 34":  "Rechtsvorm onderneming",
    "Question 35":  "KvK-nummer",
    "Question 36":  "Boekhoudprogramma",
    "Question 37":  "Balans en winst- en verliesrekening",
    "Question 37b": "Aangifte IB vorig jaar (indien niet via Klår)",
    "Question 38":  "Meer dan 1.225 uur besteed",
    "Question 33p": "Zelfstandig ondernemer partner",
    "Question 34p": "Rechtsvorm onderneming partner",
    "Question 35p": "KvK-nummer onderneming partner",
    "Question 36p": "Boekhoudprogramma partner",
    "Question 37p": "Balans en winst- en verliesrekening partner",
    "Question 37bp": "Aangifte IB vorig jaar partner (indien niet via Klår)",
    "Question 38p": "Meer dan 1.225 uur besteed partner",
    "Question 39":  "Eigen woning (hoofdverblijf)",
    "Question 40":  "Eigenaarschap woning",
    "Question 41":  "Overige eigenaar woning",
    "Question 42":  "Adres eigen woning",
    "Question 43":  "Hypotheek op eigen woning",
    "Question 44":  "Jaaropgave hypotheek",
    "Question 44b": "Erfpacht eigen woning",
    "Question 44c": "Document erfpachtcanon",
    "Question 45":  "Woning gekocht of verkocht",
    "Question 46":  "Datum aankoop woning",
    "Question 46b": "Datum bewoning nieuwe woning",
    "Question 47":  "Notarisafrekening aankoop",
    "Question 47b": "Taxatiefactuur aankoop",
    "Question 48":  "Datum verkoop woning",
    "Question 48b": "Datum einde bewoning woning",
    "Question 49":  "Notarisafrekening verkoop",
    "Question 49b": "Taxatiefactuur verkoop",
    "Question 50":  "Tweede eigen woning",
    "Question 51":  "Eigenaarschap tweede woning",
    "Question 52":  "Overige eigenaar tweede woning",
    "Question 53":  "Adres tweede woning",
    "Question 54":  "Hypotheek op tweede woning",
    "Question 55":  "Jaaropgave hypotheek tweede woning",
    "Question 56":  "Tweede woning gekocht of verkocht",
    "Question 57":  "Datum aankoop tweede woning",
    "Question 57b": "Datum bewoning tweede woning",
    "Question 58":  "Notarisafrekening aankoop tweede woning",
    "Question 59":  "Taxatiefactuur nieuwe woning",
    "Question 59b": "Datum verkoop tweede woning",
    "Question 60":  "Datum einde bewoning tweede woning",
    "Question 61":  "Notarisafrekening verkoop tweede woning",
    "Question 62":  "Taxatiefactuur oude woning",
    "Question 63":  "Hypotheek overgesloten",
    "Question 64":  "Notarisafrekening oversluiting",
    "Question 65":  "Aanmerkelijk belang BV/NV",
    "Question 66":  "Naam BV/NV en aandelen per 1-1",
    "Question 67":  "Aandelen gekocht of verkocht",
    "Question 68":  "Aantal gekochte/verkochte aandelen",
    "Question 68b": "Aankoop-/verkoopprijs per aandeel",
    "Question 69":  "Dividend ontvangen",
    "Question 70":  "Bruto ontvangen dividend",
    "Question 70b": "Dividendbelasting afgedragen",
    "Question 70c": "Bedrag afgedragen dividendbelasting",
    "Question 71":  "Nederlandse bankrekeningen / beleggingen",
    "Question 72":  "Jaaroverzichten Nederlandse rekeningen",
    "Question 73":  "Crypto en/of vorderingen",
    "Question 73b": "Overzicht crypto / vorderingen",
    "Question 74":  "Overig onroerend goed NL",
    "Question 75":  "Adres overig onroerend goed",
    "Question 76":  "Verhuurd overig onroerend goed",
    "Question 77":  "Verhuurd aan familielid",
    "Question 78":  "Kale huurprijs per maand",
    "Question 79":  "Erfpacht",
    "Question 80":  "Erfpachtcanon",
    "Question 81":  "Afzonderlijk verkoopbaar",
    "Question 81b": "Hypotheek/schuld overig onroerend goed",
    "Question 81c": "Jaaropgave hypotheek/schuld overig onroerend goed",
    "Question 82":  "Nederlandse schulden",
    "Question 83":  "Jaaropgaven Nederlandse schulden",
    "Question 84":  "Buitenlandse bankrekeningen / beleggingen",
    "Question 85":  "Jaaroverzichten buitenlandse rekeningen",
    **_og_buitenland_labels(),
    "Question 90":  "Buitenlandse schulden",
    "Question 91":  "Overzicht buitenlandse schulden",
    "Question 92":  "Buitenlands inkomen",
    "Question 93":  "Bron buitenlands inkomen",
    "Question 94":  "Belasting ingehouden in buitenland",
    "Question 95":  "Bewijs buitenlands inkomen",
    "Question 96":  "Donaties goede doelen (>€60)",
    "Question 97":  "Overzicht donaties goede doelen",
    "Question 98":  "Buitengewone zorgkosten",
    "Question 99":  "Overzicht zorgkosten",
    "Question 100": "Dieet op voorschrift",
    "Question 101": "Welk dieet",
    "Question 102": "Voorlopige aanslag ontvangen",
    "Question 103": "Kopie voorlopige aanslag",
    "Question 104": "Aanvullende documenten uploaden",
    "Question 105": "Aanvullende documenten",
    "Question 106": "Aanvullende opmerkingen",
    "Question 107": "Opmerkingen tekst",
}

# ── Stap-structuur (voor gegroepeerde weergave) ───────────────────
STAPPEN_ADMIN = {
    "Stap 1":  {"titel": "Privacy verklaring",
                "vragen": ["Question 1"]},
    "Stap 2":  {"titel": "Persoonlijke gegevens",
                "vragen": ["Question 2","Question 3b","Question 3","Question 4","Question 5","Question 6","Question 7","Question 7b","Question 7c"]},
    "Stap 3":  {"titel": "Fiscaal partner",
                "vragen": ["Question 8","Question 9","Question 10"]},
    "Stap 4":  {"titel": "Persoonlijke gegevens van fiscaal partner",
                "vragen": ["Question 11","Question 11b","Question 12","Question 13","Question 14","Question 15","Question 15b"]},
    "Stap 5":  {"titel": "Thuiswonende kinderen",
                "vragen": ["Question 16","Question 17","Question 18"]},
    "Stap 6":  {"titel": "Waar je woonde",
                "vragen": ["Question 19","Question 20","Question 21","Question 22","Question 23","Question 24","Question 26","Question 27"]},
    "Stap 7":  {"titel": "Inkomen uit loondienst",
                "vragen": ["Question 28","Question 29","Question 30","Question 31","Question 32"]},
    "Stap 7a": {"titel": "Inkomen uit loondienst van jouw partner",
                "vragen": ["Question 28p","Question 29p","Question 30p","Question 31p","Question 32p"]},
    "Stap 7b": {"titel": "Inkomen uit uitkering / pensioen / lijfrente",
                "vragen": ["Question 32b","Question 32c"]},
    "Stap 7c": {"titel": "Inkomen uit uitkering / pensioen / lijfrente van jouw partner",
                "vragen": ["Question 32bp","Question 32cp"]},
    "Stap 8":  {"titel": "Inkomen uit ondernemerschap",
                "vragen": ["Question 33","Question 34","Question 35","Question 36","Question 37","Question 37b","Question 38"]},
    "Stap 8a": {"titel": "Inkomen uit ondernemerschap van jouw partner",
                "vragen": ["Question 33p","Question 34p","Question 35p","Question 36p","Question 37p","Question 37bp","Question 38p"]},
    "Stap 9":  {"titel": "Eigen woonverblijf",
                "vragen": ["Question 39","Question 40","Question 41","Question 42","Question 43","Question 44","Question 44b","Question 44c","Question 45","Question 46","Question 46b","Question 47","Question 47b","Question 48","Question 48b","Question 49","Question 49b"]},
    "Stap 10": {"titel": "Tweede eigen woonverblijf",
                "vragen": ["Question 50","Question 51","Question 52","Question 53","Question 54","Question 55","Question 56","Question 57","Question 57b","Question 58","Question 59","Question 59b","Question 60","Question 61","Question 62"]},
    "Stap 11": {"titel": "Hypotheek",
                "vragen": ["Question 63","Question 64"]},
    "Stap 12": {"titel": "Aanmerkelijk belang",
                "vragen": ["Question 65","Question 66","Question 67","Question 68","Question 68b","Question 69","Question 70","Question 70b","Question 70c"]},
    "Stap 13": {"titel": "Sparen",
                "vragen": ["Question 71","Question 72","Question 73","Question 73b"]},
    "Stap 14": {"titel": "Tweede eigen woonverblijf (Belegging)",
                "vragen": ["Question 74","Question 75","Question 76","Question 77","Question 78","Question 79","Question 80","Question 81","Question 81b","Question 81c"]},
    "Stap 15": {"titel": "Overig — Nederlandse schulden",
                "vragen": ["Question 82","Question 83"]},
    "Stap 16": {"titel": "Buitenlands vermogen, beleggingen, schulden en inkomen",
                "vragen": ["Question 84","Question 85",*_og_buitenland_labels(),"Question 90","Question 91","Question 92","Question 93","Question 94","Question 95"]},
    "Stap 17": {"titel": "Aftrekposten",
                "vragen": ["Question 96","Question 97","Question 98","Question 99","Question 100","Question 101"]},
    "Stap 18": {"titel": "Afronding",
                "vragen": ["Question 102","Question 103","Question 104","Question 105","Question 106","Question 107"]},
}


# ── Helper: is dit een bestandspad? ──────────────────────────────
def _is_pad(waarde: str) -> bool:
    """Detecteer of een string een Supabase Storage pad is."""
    return isinstance(waarde, str) and waarde.count("/") >= 3


# ── Signed URL genereren ─────────────────────────────────────────
def get_signed_url(pad: str, expires_in: int = 3600) -> str | None:
    """Genereer een tijdelijke download-URL (standaard 1 uur geldig)."""
    if not pad or not admin_supabase:
        return None
    try:
        result = admin_supabase.storage.from_("documenten").create_signed_url(
            path=pad, expires_in=expires_in
        )
        return result.get("signedURL")
    except Exception:
        return None


# ── Antwoord → leesbare string (met URL voor bestanden) ──────────
def antwoord_naar_tekst(waarde, als_url: bool = True) -> str:
    """Zet een antwoord om naar leesbare tekst, met signed URLs voor bestanden."""
    if waarde is None:
        return ""
    if isinstance(waarde, bool):
        return "Ja" if waarde else "Nee"
    if isinstance(waarde, list):
        regels = []
        for item in waarde:
            if _is_pad(item):
                url = get_signed_url(item) if als_url else None
                naam = item.split("/")[-1]
                regels.append(url if url else naam)
            elif isinstance(item, dict):
                regels.append(" | ".join(f"{k}: {v}" for k, v in item.items()))
            else:
                regels.append(str(item))
        return "\n".join(regels)
    if _is_pad(str(waarde)):
        url = get_signed_url(str(waarde)) if als_url else None
        return url if url else str(waarde).split("/")[-1]
    return str(waarde)


# ── Database queries ─────────────────────────────────────────────
def search_records(email_query: str = "", jaar: int = None) -> list:
    """Zoek records op e-mail (partial match) en/of jaar."""
    if not admin_supabase:
        return []
    try:
        query = admin_supabase.table("vragenlijsten").select("*")
        if email_query.strip():
            query = query.ilike("email", f"%{email_query.strip()}%")
        if jaar:
            query = query.eq("jaar", jaar)
        result = query.order("created_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


# ── Documenten opruimen (retentie) ───────────────────────────────
def _lijst_bestanden(prefix: str, diepte: int = 0) -> list[dict]:
    """
    Verzamel alle bestandspaden onder een prefix.
    Storage kent geen recursieve list, dus we lopen de mappen zelf af:
    {user_id}/{jaar}/{question_id}/{bestand}
    """
    if not admin_supabase or diepte > 3:
        return []
    try:
        entries = admin_supabase.storage.from_("documenten").list(prefix)
    except Exception:
        return []

    bestanden = []
    for entry in entries or []:
        naam = entry.get("name")
        if not naam or naam == ".emptyFolderPlaceholder":
            continue
        pad = f"{prefix}/{naam}"
        if entry.get("id"):          # een bestand
            grootte = (entry.get("metadata") or {}).get("size") or 0
            bestanden.append({"pad": pad, "grootte": grootte})
        else:                        # een map: een niveau dieper kijken
            bestanden.extend(_lijst_bestanden(pad, diepte + 1))
    return bestanden


def documenten_van_record(user_id: str, jaar: int) -> list[dict]:
    """
    Alle bestanden die deze klant voor dit jaar heeft geüpload,
    als lijst van {"pad": ..., "grootte": bytes}.
    """
    if not user_id or not jaar:
        return []
    return _lijst_bestanden(f"{user_id}/{jaar}")


def verwijder_documenten(user_id: str, jaar: int) -> tuple[int, str]:
    """
    Verwijder alle geüploade bestanden van één klant voor één jaar.
    De antwoorden in de database blijven staan; alleen de bestanden in
    Storage gaan weg. Geeft (aantal verwijderd, foutmelding) terug.
    """
    if not admin_supabase:
        return 0, "Geen Supabase verbinding"

    bestanden = documenten_van_record(user_id, jaar)
    if not bestanden:
        return 0, "Geen bestanden gevonden."
    try:
        paden = [b["pad"] for b in bestanden]
        admin_supabase.storage.from_("documenten").remove(paden)
        return len(paden), ""
    except Exception as e:
        return 0, str(e)


# ── Nextens ID opslaan ───────────────────────────────────────────
def sla_nextens_id_op(record_id: str, nextens_id: str) -> tuple[bool, str]:
    """Sla het Nextens ID op in de Supabase record."""
    if not admin_supabase:
        return False, "Geen Supabase verbinding"
    try:
        admin_supabase.table("vragenlijsten").update(
            {"nextens_id": nextens_id}
        ).eq("id", record_id).execute()
        return True, "Opgeslagen"
    except Exception as e:
        return False, str(e)


# ── Export functies ──────────────────────────────────────────────
def _records_naar_df(records: list) -> pd.DataFrame:
    """Zet records om naar een platte DataFrame met signed URLs."""
    rijen = []
    for r in records:
        rij = {
            "Email":       r.get("email", ""),
            "Jaar":        r.get("jaar", ""),
            "Type":        r.get("vragenlijst_type", ""),
            "Ingevuld op": (r.get("created_at") or "")[:10],
            "Taal":        r.get("taal", ""),
        }
        antwoorden = r.get("antwoorden", {})
        for q_id, label in VRAAG_LABELS.items():
            waarde = antwoorden.get(q_id)
            rij[label] = antwoord_naar_tekst(waarde, als_url=True) if waarde is not None else ""
        rijen.append(rij)
    return pd.DataFrame(rijen)


def export_records_csv(records: list) -> bytes:
    """Exporteer records als CSV (UTF-8 met BOM voor Excel-compatibiliteit)."""
    df = _records_naar_df(records)
    return df.to_csv(index=False).encode("utf-8-sig")


def export_records_excel(records: list) -> bytes:
    """Exporteer records als Excel met opmaak."""
    df = _records_naar_df(records)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Antwoorden")
        ws = writer.sheets["Antwoorden"]
        # Kolombreedtes aanpassen
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
    return buf.getvalue()
