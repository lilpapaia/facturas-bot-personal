"""
Facturas Bot - DEBUG VERSION
"""
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import re

# =========================
# CONFIGURACIÓN
# =========================
SHEET_ID = "1putS_YxGiLGiBzaFxCIzrF6p5AsNxQJoX0EYTDsfen0"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# =========================
# AUTENTICACIÓN
# =========================
def check_password():
    def login_form():
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <h1>🧾 Facturas Bot - DEBUG</h1>
            <p style="color: gray;">Panel de Control Personal</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login"):
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
            
            if submitted:
                if user == st.secrets["auth"]["username"] and password == st.secrets["auth"]["password"]:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
    
    if st.session_state.get("authenticated"):
        return True
    
    login_form()
    return False


# =========================
# ARREGLAR PRIVATE KEY
# =========================
def fix_private_key(pk):
    match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
    if not match:
        return pk
    content = match.group(1)
    content_clean = re.sub(r'\s+', '', content)
    lines = [content_clean[i:i+64] for i in range(0, len(content_clean), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


# =========================
# CONEXIÓN GOOGLE SHEETS
# =========================
@st.cache_resource
def get_gspread_client():
    gcp_secrets = st.secrets["gcp_service_account"]
    creds_dict = {
        "type": gcp_secrets["type"],
        "project_id": gcp_secrets["project_id"],
        "private_key_id": gcp_secrets["private_key_id"],
        "private_key": fix_private_key(gcp_secrets["private_key"]),
        "client_email": gcp_secrets["client_email"],
        "client_id": gcp_secrets["client_id"],
        "auth_uri": gcp_secrets["auth_uri"],
        "token_uri": gcp_secrets["token_uri"],
        "auth_provider_x509_cert_url": gcp_secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": gcp_secrets["client_x509_cert_url"],
    }
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


# =========================
# INTERFAZ
# =========================
def main():
    st.set_page_config(page_title="Facturas Bot DEBUG", page_icon="🔍", layout="wide")
    
    if not check_password():
        return
    
    st.title("🔍 DEBUG - Valores del Sheet")
    
    # Cargar datos RAW
    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet("movimientos")
    
    # Obtener datos como lista de diccionarios
    data = ws.get_all_records()
    
    st.write(f"**Total filas:** {len(data)}")
    st.write("---")
    
    # Mostrar las primeras 5 filas con detalle
    st.subheader("📋 Primeras 5 filas - Valores RAW")
    
    for i, row in enumerate(data[:5]):
        st.write(f"### Fila {i+1}: {row.get('proveedor_cliente', 'Sin nombre')}")
        
        # Mostrar columnas numéricas con detalle
        cols = ['base', 'iva', 'irpf', 'total']
        
        debug_data = []
        for col in cols:
            val = row.get(col, '')
            debug_data.append({
                'Campo': col,
                'Valor RAW': repr(val),
                'Tipo': type(val).__name__,
                'Es string?': isinstance(val, str),
                'Tiene coma?': ',' in str(val) if val else False,
            })
        
        st.table(pd.DataFrame(debug_data))
        st.write("---")
    
    # Mostrar todos los valores de 'total' para análisis
    st.subheader("📊 Todos los valores de 'total'")
    
    totals_debug = []
    for row in data:
        val = row.get('total', '')
        totals_debug.append({
            'Proveedor': row.get('proveedor_cliente', '')[:30],
            'total RAW': repr(val),
            'Tipo': type(val).__name__,
        })
    
    st.dataframe(pd.DataFrame(totals_debug), use_container_width=True)


if __name__ == "__main__":
    main()
