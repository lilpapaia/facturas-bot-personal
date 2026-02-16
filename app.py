"""
Facturas Bot - Panel de Control Personal
Streamlit App con autenticación - VERSION DEBUG
"""
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# =========================
# CONFIGURACIÓN
# =========================
SHEET_ID = "1putS_YxGiLGiBzaFxCIzrF6p5AsNxQJoX0EYTDsfen0"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# =========================
# DEBUG MODE - cambiar a False cuando funcione
# =========================
DEBUG = True

# =========================
# AUTENTICACIÓN
# =========================
def check_password():
    """Verifica usuario y contraseña."""
    
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
# CONEXIÓN GOOGLE SHEETS
# =========================
def get_gspread_client():
    """Conecta con Google Sheets usando secrets."""
    try:
        # Obtener credenciales
        gcp_secrets = st.secrets["gcp_service_account"]
        
        if DEBUG:
            st.write("### 🔍 DEBUG INFO")
            st.write(f"**Keys en gcp_service_account:** {list(gcp_secrets.keys())}")
            st.write(f"**project_id:** {gcp_secrets.get('project_id', 'NO ENCONTRADO')}")
            st.write(f"**client_email:** {gcp_secrets.get('client_email', 'NO ENCONTRADO')}")
            
            pk = gcp_secrets.get('private_key', '')
            st.write(f"**private_key length:** {len(pk)} caracteres")
            st.write(f"**private_key empieza con:** {pk[:50]}...")
            st.write(f"**private_key termina con:** ...{pk[-50:]}")
            st.write(f"**Contiene saltos de linea reales:** {'SI' if chr(10) in pk else 'NO'}")
            st.write(f"**Contiene \\\\n literal:** {'SI' if '\\n' in pk.replace(chr(10), '') else 'NO'}")
        
        creds_dict = dict(gcp_secrets)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
        
    except Exception as e:
        st.error(f"Error en get_gspread_client: {e}")
        if DEBUG:
            import traceback
            st.code(traceback.format_exc())
        return None


def load_movimientos():
    """Carga datos de movimientos."""
    try:
        gc = get_gspread_client()
        if gc is None:
            return pd.DataFrame()
            
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet("movimientos")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        if DEBUG:
            import traceback
            st.code(traceback.format_exc())
        return pd.DataFrame()


# =========================
# CÁLCULOS
# =========================
def calcular_resumen(df, year):
    """Calcula resumen IVA/IRPF por trimestre."""
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
    st.set_page_config(
        page_title="Facturas Bot",
        page_icon="🧾",
        layout="wide"
    )
    
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
            st.dataframe(
                resumen.style.format({
                    'Base Ingresos': '{:,.2f} €',
                    'IVA Repercutido': '{:,.2f} €',
                    'IRPF Retenido': '{:,.2f} €',
                    'Base Gastos': '{:,.2f} €',
                    'IVA Soportado': '{:,.2f} €',
                    'IVA Neto': '{:,.2f} €',
                }),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown("---")
            st.markdown(f"**Total IVA a Pagar/Devolver: {totales['IVA Neto']:,.2f} €**")
    
    with tab2:
        st.subheader("Facturas del Año")
        df_year = df[df['anio_trimestre'].str.startswith(str(year))].copy()
        
        if not df_year.empty:
            tipo_filter = st.radio("Filtrar", ["Todos", "Ingresos", "Gastos"], horizontal=True)
            
            if tipo_filter == "Ingresos":
                df_year = df_year[df_year['tipo'].str.lower() == 'ingreso']
            elif tipo_filter == "Gastos":
                df_year = df_year[df_year['tipo'].str.lower() == 'gasto']
            
            cols_show = ['fecha', 'tipo', 'proveedor_cliente', 'numero_factura', 'base', 'iva', 'total']
            cols_exist = [c for c in cols_show if c in df_year.columns]
            
            st.dataframe(
                df_year[cols_exist].sort_values('fecha', ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(f"Total: {len(df_year)} facturas")
        else:
            st.info("No hay facturas este año")
    
    with tab3:
        st.subheader("Subir Factura")
        uploaded = st.file_uploader(
            "Arrastra o selecciona tu factura",
            type=['pdf', 'jpg', 'jpeg', 'png'],
        )
        if uploaded:
            st.success(f"✅ Archivo: {uploaded.name}")
            st.info("⚠️ Función de subida pendiente")


if __name__ == "__main__":
    main()
