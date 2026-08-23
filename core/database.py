"""
Conexión a Supabase para trackear cuántos videos generó cada mail,
de forma persistente (sobrevive a cerrar el navegador, cambiar de
dispositivo, o borrar cookies — a diferencia de session_state).

Requiere en Secrets (local: .streamlit/secrets.toml, o en Streamlit
Community Cloud: Settings → Secrets):
    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_SERVICE_KEY = "tu-secret-key"
"""

import streamlit as st
from supabase import create_client

# Dominios de mail descartables/temporales más comunes. No es una
# lista exhaustiva (no existe una perfecta), pero frena el caso más
# obvio de "genero un mail trucho para probar de nuevo gratis".
DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "guerrillamail.com",
    "tempmail.com", "throwawaymail.com", "yopmail.com", "trashmail.com",
    "fakeinbox.com", "sharklasers.com", "dispostable.com", "getnada.com",
    "maildrop.cc", "temp-mail.org", "mohmal.com", "moakt.com",
    "tempinbox.com", "mailcatch.com", "spamgourmet.com",
}


@st.cache_resource
def _get_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def is_disposable_email(email: str) -> bool:
    domain = email.strip().lower().split("@")[-1]
    return domain in DISPOSABLE_DOMAINS


def get_or_create_user(email: str) -> int:
    """
    Devuelve la cantidad de videos ya generados por ese mail. Si el
    mail no existe todavía en la tabla, lo crea con 0.
    """
    client = _get_client()
    email = email.strip().lower()

    result = (
        client.table("users")
        .select("videos_generated_count")
        .eq("email", email)
        .execute()
    )
    if result.data:
        return result.data[0]["videos_generated_count"]

    client.table("users").insert(
        {"email": email, "videos_generated_count": 0}
    ).execute()
    return 0


def increment_video_count(email: str) -> int:
    """Suma 1 al contador de ese mail y devuelve el nuevo valor."""
    client = _get_client()
    email = email.strip().lower()
    current = get_or_create_user(email)
    new_count = current + 1
    client.table("users").update(
        {"videos_generated_count": new_count}
    ).eq("email", email).execute()
    return new_count


def reset_user(email: str):
    """Solo para pruebas propias: reinicia el contador de un mail a 0."""
    client = _get_client()
    email = email.strip().lower()
    client.table("users").update({"videos_generated_count": 0}).eq(
        "email", email
    ).execute()
