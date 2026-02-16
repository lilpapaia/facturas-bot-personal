"""
Facturas Bot - Panel de Control Personal
Streamlit App con autenticación
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
# ARREGLAR PRIVATE KEY
# =========================
def fix_private_key(pk):
    """Arregla el formato de la private_key."""
    # Quitar espacios y saltos de línea extras
    pk = pk.strip()
    
    # Extraer el contenido entre BEGIN y END
    match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
    if not match:
        return pk
    
    content = match.group(1).strip()
    
    # Quitar todos los espacios y saltos de línea del contenido
    content = re.sub(r'\s+', '', content)
    
    # Reconstruir con el formato correcto (líneas de 64 caracteres)
    lines = [content[i:i+64] for i in range(0, len(content), 64)]
    
    # Construir la clave correctamente
    fixed = "-----BEGIN PRIVATE KEY-----\n"
    fixed += "\n".join(lines)
    fixed += "\n-----END PRIVATE KEY-----\n"
    
    return fixed


# =========================
# CONEXIÓN GOOGLE SHEETS
# =========================
@st.cache_resource
def get_gspread_client():
    """Conecta con Google Sheets usando secrets."""
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # Arreglar el formato de private_key
    if "private_key" in creds_dict:
        creds_dict["private_key"] = fix_private_key(creds_dict["private_key"])
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300)
def load_movimientos():
    """Carga datos de movimientos."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet("movimientos")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
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
