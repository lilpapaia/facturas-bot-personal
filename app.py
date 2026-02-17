"""
Facturas Bot - Panel de Control Personal
DEBUG VERSION - SIN CACHE
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

DEBUG = True

# =========================
# AUTENTICACIÓN
# =========================
def check_password():
    def login_form():
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <h1>🧾 Facturas Bot</h1>
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
    """Arregla el formato de la private_key."""
    
    # 1. Extraer SOLO la parte base64 (quitar headers y todo lo demás)
    # Buscar el contenido entre BEGIN y END
    match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
    
    if not match:
        st.error("❌ No se encontró BEGIN/END PRIVATE KEY")
        return pk
    
    # 2. Obtener solo el contenido base64
    content = match.group(1)
    
    # 3. Limpiar: quitar TODOS los espacios, tabs, saltos de línea
    content_clean = re.sub(r'\s+', '', content)
    
    if DEBUG:
        st.write(f"**Contenido base64 limpio:** {len(content_clean)} caracteres")
    
    # 4. Reconstruir con formato PEM correcto (líneas de 64 chars)
    lines = []
    for i in range(0, len(content_clean), 64):
        lines.append(content_clean[i:i+64])
    
    # 5. Construir la clave final
    fixed_key = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"
    
    if DEBUG:
        st.write(f"**Clave reconstruida:** {len(fixed_key)} caracteres, {len(lines)+2} líneas")
        # Mostrar primeras líneas para verificar formato
        first_lines = fixed_key.split('\n')[:3]
        st.code('\n'.join(first_lines) + '\n...')
    
    return fixed_key


# =========================
# CONEXIÓN GOOGLE SHEETS
# =========================
def get_gspread_client():
    """Conecta con Google Sheets - SIN CACHE."""
    try:
        gcp_secrets = st.secrets["gcp_service_account"]
        
        if DEBUG:
            st.write("### 🔍 Verificando credenciales...")
            st.write(f"**project_id:** `{gcp_secrets.get('project_id')}`")
            st.write(f"**client_email:** `{gcp_secrets.get('client_email')}`")
        
        # Crear diccionario de credenciales
        creds_dict = {
            "type": gcp_secrets["type"],
            "project_id": gcp_secrets["project_id"],
            "private_key_id": gcp_secrets["private_key_id"],
            "private_key": fix_private_key(gcp_secrets["private_key"]),  # <-- ARREGLADA
            "client_email": gcp_secrets["client_email"],
            "client_id": gcp_secrets["client_id"],
            "auth_uri": gcp_secrets["auth_uri"],
            "token_uri": gcp_secrets["token_uri"],
            "auth_provider_x509_cert_url": gcp_secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": gcp_secrets["client_x509_cert_url"],
        }
        
        if DEBUG:
            st.write("### 🔑 Conectando a Google...")
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Probar la conexión realmente
        if DEBUG:
            st.write("### 📊 Probando acceso al Sheet...")
        
        sh = client.open_by_key(SHEET_ID)
        
        if DEBUG:
            st.success(f"✅ Conectado a: {sh.title}")
        
        return client
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
        if DEBUG:
            import traceback
            st.code(traceback.format_exc())
        return None


def load_movimientos():
    """Carga datos - SIN CACHE."""
    gc = get_gspread_client()
    if gc is None:
        return pd.DataFrame()
    
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet("movimientos")
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error cargando movimientos: {e}")
        return pd.DataFrame()


# =========================
# CÁLCULOS
# =========================
def calcular_resumen(df, year):
    if df.empty:
        return pd.DataFrame()
    
    df = df[df['anio_trimestre'].str.startswith(str(year))].copy()
    
    resumen = []
    for q in [1, 2, 3, 4]:
        qt = f"{year}-Q{q}"
        dfq = df[df['anio_trimestre'] == qt]
        
        ingresos = dfq[dfq['tipo'].str.lower() == 'ingreso']
        gastos = dfq[dfq['tipo'].str.lower() == 'gasto']
        
        base_ing = pd.to_numeric(ingresos['base'], errors='coerce').sum()
        iva_rep = pd.to_numeric(ingresos['iva'], errors='coerce').sum()
        irpf = pd.to_numeric(ingresos['irpf'], errors='coerce').sum()
        
        base_gas = pd.to_numeric(gastos['base'], errors='coerce').sum()
        gastos_ded = gastos[gastos['iva_deducible'].str.upper() == 'SI']
        iva_sop = pd.to_numeric(gastos_ded['iva'], errors='coerce').sum()
        
        resumen.append({
            'Trimestre': f'Q{q}',
            'Base Ingresos': base_ing,
            'IVA Repercutido': iva_rep,
            'IRPF Retenido': irpf,
            'Base Gastos': base_gas,
            'IVA Soportado': iva_sop,
            'IVA Neto': iva_rep - iva_sop,
        })
    
    return pd.DataFrame(resumen)


# =========================
# INTERFAZ
# =========================
def main():
    st.set_page_config(page_title="Facturas Bot", page_icon="🧾", layout="wide")
    
    if not check_password():
        return
    
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title("🧾 Facturas Bot")
    with col2:
        if st.button("🚪 Salir"):
            st.session_state["authenticated"] = False
            st.rerun()
    
    df = load_movimientos()
    
    if df.empty:
        st.warning("No hay datos en el Sheet")
        return
    
    years = sorted(df['anio_trimestre'].str[:4].unique(), reverse=True)
    year = st.selectbox("Año", years, index=0)
    
    resumen = calcular_resumen(df, year)
    
    if not resumen.empty:
        totales = resumen.sum(numeric_only=True)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Ingresos", f"{totales['Base Ingresos']:,.2f} €")
        c2.metric("💸 Gastos", f"{totales['Base Gastos']:,.2f} €")
        c3.metric("📊 IVA a Pagar", f"{totales['IVA Neto']:,.2f} €")
        c4.metric("🏛️ IRPF Retenido", f"{totales['IRPF Retenido']:,.2f} €")
    
    st.divider()
    
    tab1, tab2, tab3 = st.tabs(["📊 Resumen IVA", "📄 Facturas", "📤 Subir"])
    
    with tab1:
        st.subheader("Resumen IVA Trimestral")
        if not resumen.empty:
            st.dataframe(resumen, use_container_width=True, hide_index=True)
    
    with tab2:
        st.subheader("Facturas del Año")
        df_year = df[df['anio_trimestre'].str.startswith(str(year))].copy()
        if not df_year.empty:
            st.dataframe(df_year, use_container_width=True, hide_index=True)
    
    with tab3:
        st.subheader("Subir Factura")
        st.info("Próximamente")


if __name__ == "__main__":
    main()
