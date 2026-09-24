"""
modules/auth.py
---------------
Login-, registratie- en uitlogfuncties voor Klår Finance.
Roep show_login_screen() aan vóór de rest van de app-logica.
Roep show_logout_button() aan om de uitlogknop in de sidebar te tonen.
"""

import streamlit as st
from modules.database import get_client


def init_auth_state():
    """Initialiseer auth-gerelateerde session state variabelen."""
    if "user" not in st.session_state:
        st.session_state.user = None


def _foutmelding(e: Exception, standaard: str) -> str:
    """Vertaal een Supabase-foutmelding naar een Nederlandse tekst voor de klant."""
    code  = (getattr(e, "code", None) or "").lower()
    tekst = str(e).lower()
    if code == "invalid_credentials" or "invalid login credentials" in tekst:
        return "Dit e-mailadres en wachtwoord horen niet bij elkaar. Controleer ze en probeer het opnieuw."
    if code == "email_not_confirmed" or "email not confirmed" in tekst:
        return ("Je e-mailadres is nog niet bevestigd. Klik op de link in de bevestigingsmail "
                "en log daarna opnieuw in.")
    if code == "otp_expired" or "token has expired or is invalid" in tekst:
        return "Deze code klopt niet of is verlopen. Vraag een nieuwe code aan."
    if code in ("email_address_invalid", "validation_failed") or "validate email" in tekst:
        return "Dit e-mailadres lijkt niet te kloppen. Controleer het en probeer het opnieuw."
    if code == "same_password":
        return "Kies een ander wachtwoord dan je huidige."
    if code == "weak_password" or "password should" in tekst:
        return "Dit wachtwoord is te zwak. Kies een langer wachtwoord."
    if code in ("over_request_rate_limit", "over_email_send_rate_limit") or "rate limit" in tekst:
        return "Je hebt het te vaak geprobeerd. Wacht een paar minuten en probeer het dan opnieuw."
    return standaard


def _log_in_met_sessie(sessie):
    """Zet de ingelogde gebruiker en zijn tokens in session_state en laad de app."""
    st.session_state.user = sessie.user
    # Sla de volledige sessie op voor RLS-verzoeken
    st.session_state.access_token  = sessie.access_token
    st.session_state.refresh_token = sessie.refresh_token
    st.rerun()


def show_login_screen():
    """
    Toont het inlogscherm (inloggen / account aanmaken / wachtwoord vergeten).
    Roept st.stop() aan als de gebruiker niet ingelogd is,
    zodat de rest van de app niet geladen wordt.
    """
    init_auth_state()

    if st.session_state.user is not None:
        return  # Al ingelogd, niets te doen

    st.title("Klår Finance — Inloggen")

    tab_in, tab_reg, tab_reset = st.tabs(
        ["Inloggen", "Account aanmaken", "Wachtwoord vergeten"]
    )

    # --- TAB 1: INLOGGEN ---
    with tab_in:
        with st.form("login_form"):
            email    = st.text_input("E-mailadres", key="login_email")
            password = st.text_input("Wachtwoord", type="password", key="login_pw")
            inloggen = st.form_submit_button("Inloggen", type="primary", width='stretch')

        if inloggen:
            if not email or not password:
                st.error("Vul je e-mailadres en wachtwoord in.")
            else:
                try:
                    response = get_client().auth.sign_in_with_password(
                        {"email": email.strip(), "password": password}
                    )
                except Exception as e:
                    st.error(_foutmelding(e, "Inloggen is niet gelukt. Probeer het later opnieuw."))
                else:
                    _log_in_met_sessie(response.session)

    # --- TAB 2: ACCOUNT AANMAKEN ---
    with tab_reg:
        st.write("Maak een account aan om de vragenlijst in te vullen.")
        with st.form("register_form"):
            reg_email = st.text_input("E-mailadres", key="reg_email")
            reg_pw    = st.text_input("Wachtwoord (minimaal 6 tekens)", type="password", key="reg_pw")
            reg_pw2   = st.text_input("Herhaal wachtwoord", type="password", key="reg_pw2")
            registreren = st.form_submit_button("Account aanmaken", width='stretch')

        if registreren:
            if not reg_email or not reg_pw:
                st.error("Vul alle velden in.")
            elif reg_pw != reg_pw2:
                st.error("De wachtwoorden komen niet overeen.")
            elif len(reg_pw) < 6:
                st.error("Het wachtwoord moet minimaal 6 tekens bevatten.")
            else:
                try:
                    response = get_client().auth.sign_up(
                        {"email": reg_email.strip(), "password": reg_pw}
                    )
                except Exception as e:
                    st.error(_foutmelding(e, "Aanmaken mislukt. Mogelijk bestaat dit e-mailadres al."))
                else:
                    if response.session is None:
                        # E-mailbevestiging staat aan in Supabase: eerst de link aanklikken
                        st.success("Bijna klaar! We hebben je een e-mail gestuurd. Klik op de link "
                                   "in die mail om je e-mailadres te bevestigen. Daarna kun je inloggen.")
                    else:
                        st.success("Account aangemaakt! Je kunt nu inloggen via het tabblad 'Inloggen'.")

    # --- TAB 3: WACHTWOORD VERGETEN ---
    # Stap 1: code aanvragen. Stap 2: code + nieuw wachtwoord invullen.
    # Een code in plaats van een link, omdat Supabase het token van een link
    # achter een '#' in de URL zet en Streamlit dat deel niet kan uitlezen.
    with tab_reset:
        reset_voor = st.session_state.get("reset_voor")

        if not reset_voor:
            st.write("Vul je e-mailadres in. Je ontvangt een code waarmee je een nieuw wachtwoord kunt instellen.")
            with st.form("reset_form"):
                reset_email = st.text_input("E-mailadres", key="reset_email")
                versturen   = st.form_submit_button("Stuur code", width='stretch')

            if versturen:
                if not reset_email:
                    st.error("Vul je e-mailadres in.")
                else:
                    try:
                        get_client().auth.reset_password_email(reset_email.strip())
                    except Exception as e:
                        st.error(_foutmelding(e, "Er is iets misgegaan. Probeer het later opnieuw."))
                    else:
                        st.session_state.reset_voor = reset_email.strip()
                        st.rerun()
        else:
            st.info(f"Als **{reset_voor}** bij ons bekend is, ontvang je binnen een paar minuten "
                    "een e-mail met een code. Kijk ook even in je spam.")
            with st.form("nieuw_wachtwoord_form"):
                code   = st.text_input("Code uit de e-mail", key="reset_code")
                nw_pw  = st.text_input("Nieuw wachtwoord (minimaal 6 tekens)", type="password", key="reset_pw")
                nw_pw2 = st.text_input("Herhaal nieuw wachtwoord", type="password", key="reset_pw2")
                opslaan = st.form_submit_button("Wachtwoord opslaan en inloggen", type="primary", width='stretch')

            if st.button("Andere e-mail of nieuwe code", key="reset_opnieuw"):
                st.session_state.pop("reset_voor", None)
                st.rerun()

            if opslaan:
                code = code.replace(" ", "").strip()
                if not code or not nw_pw:
                    st.error("Vul de code en je nieuwe wachtwoord in.")
                elif not code.isdigit():
                    st.error("De code bestaat alleen uit cijfers. Controleer de code in de e-mail.")
                elif nw_pw != nw_pw2:
                    st.error("De wachtwoorden komen niet overeen.")
                elif len(nw_pw) < 6:
                    st.error("Het wachtwoord moet minimaal 6 tekens bevatten.")
                else:
                    try:
                        client   = get_client()
                        response = client.auth.verify_otp(
                            {"email": reset_voor, "token": code, "type": "recovery"}
                        )
                        client.auth.update_user({"password": nw_pw})
                        sessie = client.auth.get_session() or response.session
                    except Exception as e:
                        st.error(_foutmelding(e, "Het wachtwoord kon niet worden opgeslagen. Probeer het opnieuw."))
                    else:
                        st.session_state.pop("reset_voor", None)
                        _log_in_met_sessie(sessie)

    st.stop()


def show_logout_button():
    """Toont de ingelogde gebruiker, uitlogknop en admin-knop (indien admin) in de sidebar."""
    if st.session_state.get("user") is None:
        return

    ADMIN_EMAILS = [e.lower() for e in st.secrets.get("ADMIN_EMAILS", [])]
    is_admin = st.session_state.user.email.lower() in ADMIN_EMAILS

    with st.sidebar:
        st.write(f"Ingelogd als: **{st.session_state.user.email}**")

        if is_admin:
            admin_modus = st.session_state.get("admin_modus", False)
            knop_label = "📋 Naar vragenlijst" if admin_modus else "⚙️ Admin panel"
            if st.button(knop_label, width='stretch'):
                st.session_state.admin_modus = not admin_modus
                st.rerun()

        if st.button("Uitloggen"):
            try:
                get_client().auth.sign_out()
            except Exception:
                pass
            st.session_state.clear()
            st.rerun()
