"""
modules/auth.py
---------------
Login-, registratie- en uitlogfuncties voor Klår Finance.
Roep show_login_screen() aan vóór de rest van de app-logica.
Roep show_logout_button() aan om de uitlogknop in de sidebar te tonen.
"""

import streamlit as st
from modules.database import supabase


def init_auth_state():
    """Initialiseer auth-gerelateerde session state variabelen."""
    if "user" not in st.session_state:
        st.session_state.user = None


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
            inloggen = st.form_submit_button("Inloggen", type="primary", use_container_width=True)

        if inloggen:
            if not email or not password:
                st.error("Vul uw e-mailadres en wachtwoord in.")
            else:
                try:
                    response = supabase.auth.sign_in_with_password(
                        {"email": email, "password": password}
                    )
                    st.session_state.user = response.user
                    # Sla de volledige sessie op voor RLS-verzoeken
                    st.session_state.access_token  = response.session.access_token
                    st.session_state.refresh_token = response.session.refresh_token
                    st.rerun()
                except Exception as e:
                    st.error(f"Inloggen mislukt: {e}")

    # --- TAB 2: ACCOUNT AANMAKEN ---
    with tab_reg:
        st.write("Maak een account aan om de vragenlijst in te vullen.")
        with st.form("register_form"):
            reg_email = st.text_input("E-mailadres", key="reg_email")
            reg_pw    = st.text_input("Wachtwoord (minimaal 6 tekens)", type="password", key="reg_pw")
            reg_pw2   = st.text_input("Herhaal wachtwoord", type="password", key="reg_pw2")
            registreren = st.form_submit_button("Account aanmaken", use_container_width=True)

        if registreren:
            if not reg_email or not reg_pw:
                st.error("Vul alle velden in.")
            elif reg_pw != reg_pw2:
                st.error("De wachtwoorden komen niet overeen.")
            elif len(reg_pw) < 6:
                st.error("Het wachtwoord moet minimaal 6 tekens bevatten.")
            else:
                try:
                    supabase.auth.sign_up({"email": reg_email, "password": reg_pw})
                    st.success("Account aangemaakt! U kunt nu inloggen via het tabblad 'Inloggen'.")
                except Exception:
                    st.error("Aanmaken mislukt. Mogelijk bestaat dit e-mailadres al.")

    # --- TAB 3: WACHTWOORD VERGETEN ---
    with tab_reset:
        st.write("Vul uw e-mailadres in. U ontvangt een link om uw wachtwoord opnieuw in te stellen.")
        with st.form("reset_form"):
            reset_email = st.text_input("E-mailadres", key="reset_email")
            versturen   = st.form_submit_button("Stuur resetlink", use_container_width=True)

        if versturen:
            if not reset_email:
                st.error("Vul uw e-mailadres in.")
            else:
                try:
                    supabase.auth.reset_password_email(reset_email)
                    st.success("Als dit e-mailadres bij ons bekend is, ontvangt u een resetlink.")
                except Exception:
                    st.error("Er is iets misgegaan. Probeer het later opnieuw.")

    st.stop()


def show_logout_button():
    """Toont de ingelogde gebruiker en een uitlogknop in de sidebar."""
    if st.session_state.get("user") is None:
        return
    with st.sidebar:
        st.write(f"Ingelogd als: **{st.session_state.user.email}**")
        if st.button("Uitloggen"):
            st.session_state.clear()
            supabase.auth.sign_out()
            st.rerun()
