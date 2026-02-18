"""
Facturas Bot - Panel de Control Personal
Versión WEB completa con dashboard, procesamiento y sync.
"""
import streamlit as st
import pandas as pd
import re
import time
import hashlib
from datetime import datetime

from config.settings import SHEET_ID, WS_MOVIMIENTOS, GOOGLE_SCOPES, SUPPORTED_EXTENSIONS


# =========================
# AUTENTICACIÓN CON "RECUÉRDAME"
# =========================
def generate_token(username, password):
    """Genera un token simple para 'Recuérdame'."""
    data = f"{username}:{password}:facturas-bot-secret"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def check_password():
    # Verificar si ya está autenticado
    if st.session_state.get("authenticated"):
        return True
    
    # Verificar token en query params (Recuérdame)
    params = st.query_params
    if "token" in params:
        expected_token = generate_token(
            st.secrets["auth"]["username"],
            st.secrets["auth"]["password"]
        )
        if params.get("token") == expected_token:
            st.session_state["authenticated"] = True
            return True
    
    # Mostrar formulario de login
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1>🧾 Facturas Bot</h1>
        <p style="color: gray;">Panel de Control Personal</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("login"):
        user = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        remember = st.checkbox("🔐 Recuérdame")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
        
        if submitted:
            if user == st.secrets["auth"]["username"] and password == st.secrets["auth"]["password"]:
                st.session_state["authenticated"] = True
                
                # Si marcó "Recuérdame", guardar token en URL
                if remember:
                    token = generate_token(user, password)
                    st.query_params["token"] = token
                
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos")
    
    return False


# =========================
# GOOGLE SHEETS - LECTURA
# =========================
def _fix_private_key(pk: str) -> str:
    """Arregla el formato de la private_key."""
    match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
    if not match:
        return pk
    content = match.group(1)
    content_clean = re.sub(r'\s+', '', content)
    lines = [content_clean[i:i+64] for i in range(0, len(content_clean), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


def to_number(val):
    """Convierte string con coma decimal a float."""
    if val is None or val == '':
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0


@st.cache_resource
def get_gspread_client():
    """Obtiene cliente gspread usando Streamlit secrets."""
    import gspread
    from google.oauth2.service_account import Credentials
    
    gcp_secrets = st.secrets["gcp_service_account"]
    
    creds_dict = {
        "type": gcp_secrets["type"],
        "project_id": gcp_secrets["project_id"],
        "private_key_id": gcp_secrets["private_key_id"],
        "private_key": _fix_private_key(gcp_secrets["private_key"]),
        "client_email": gcp_secrets["client_email"],
        "client_id": gcp_secrets["client_id"],
        "auth_uri": gcp_secrets["auth_uri"],
        "token_uri": gcp_secrets["token_uri"],
        "auth_provider_x509_cert_url": gcp_secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": gcp_secrets["client_x509_cert_url"],
    }
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300)
def load_movimientos():
    """Carga datos de movimientos."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_MOVIMIENTOS)
        
        all_values = ws.get_all_values()
        
        if len(all_values) < 2:
            return pd.DataFrame()
        
        headers = all_values[0]
        data_rows = all_values[1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        
        numeric_cols = ['base', 'iva', 'irpf', 'total']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(to_number)
        
        df = df[df['tipo'].str.strip() != '']
        
        return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()


# =========================
# SYNC - Actualiza registros y clientes
# =========================
def run_sync(year: int):
    """Ejecuta sincronización de registros."""
    import gspread
    
    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)
    
    # Leer movimientos
    ws_mov = sh.worksheet(WS_MOVIMIENTOS)
    all_values = ws_mov.get_all_values()
    
    if len(all_values) < 2:
        return "No hay datos para sincronizar"
    
    headers = all_values[0]
    data_rows = all_values[1:]
    
    # Construir registros
    hm = {h.strip(): i for i, h in enumerate(headers) if h and str(h).strip()}
    
    def get_val(row, key):
        idx = hm.get(key)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()
    
    ingresos = []
    gastos = []
    clientes_data = {}
    
    for row in data_rows:
        tipo = get_val(row, "tipo").lower()
        anio_trim = get_val(row, "anio_trimestre")
        
        if not anio_trim.startswith(str(year)):
            continue
        
        if tipo == "ingreso":
            ingresos.append(row)
            # Actualizar clientes
            cliente = get_val(row, "proveedor_cliente")
            if cliente:
                if cliente not in clientes_data:
                    clientes_data[cliente] = {
                        "tax_id": get_val(row, "tax_id"),
                        "count": 0,
                        "total": 0.0
                    }
                clientes_data[cliente]["count"] += 1
                try:
                    clientes_data[cliente]["total"] += float(get_val(row, "total").replace(",", ".") or 0)
                except:
                    pass
        elif tipo == "gasto":
            gastos.append(row)
    
    results = []
    
    # Actualizar registro_ingresos
    try:
        ws_ing = sh.worksheet("registro_ingresos")
        # Cabecera
        reg_headers = ["fecha", "tipo", "proveedor_cliente", "tax_id", "numero_factura", 
                       "base", "iva", "irpf", "total", "moneda", "ambito", "archivo_drive"]
        
        reg_rows = [["REGISTRO INGRESOS (auto)"], [f"Año: {year}"], [f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"], [""]]
        reg_rows.append(reg_headers)
        
        for row in ingresos:
            reg_rows.append([get_val(row, h) for h in reg_headers])
        
        ws_ing.clear()
        ws_ing.update(range_name="A1", values=reg_rows, value_input_option="USER_ENTERED")
        results.append(f"✅ registro_ingresos: {len(ingresos)} filas")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ registro_ingresos: {e}")
    
    # Actualizar registro_gastos
    try:
        ws_gas = sh.worksheet("registro_gastos")
        reg_headers = ["fecha", "tipo", "proveedor_cliente", "tax_id", "numero_factura", 
                       "base", "iva", "total", "moneda", "ambito", "archivo_drive"]
        
        reg_rows = [["REGISTRO GASTOS (auto)"], [f"Año: {year}"], [f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"], [""]]
        reg_rows.append(reg_headers)
        
        for row in gastos:
            reg_rows.append([get_val(row, h) for h in reg_headers])
        
        ws_gas.clear()
        ws_gas.update(range_name="A1", values=reg_rows, value_input_option="USER_ENTERED")
        results.append(f"✅ registro_gastos: {len(gastos)} filas")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ registro_gastos: {e}")
    
    # Actualizar clientes
    try:
        ws_cli = sh.worksheet("clientes")
        cli_rows = [["cliente", "tax_id", "n_facturas", "total_facturado"]]
        
        for cli, data in sorted(clientes_data.items()):
            cli_rows.append([cli, data["tax_id"], data["count"], round(data["total"], 2)])
        
        ws_cli.clear()
        ws_cli.update(range_name="A1", values=cli_rows, value_input_option="USER_ENTERED")
        results.append(f"✅ clientes: {len(clientes_data)} clientes")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ clientes: {e}")
    
    # Actualizar config con el año
    try:
        ws_cfg = sh.worksheet("config")
        ws_cfg.update(range_name="B2", values=[[year]], value_input_option="USER_ENTERED")
        results.append(f"✅ config: año {year}")
    except Exception as e:
        results.append(f"⚠️ config: {e}")
    
    return "\n".join(results)


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
        
        base_ing = ingresos['base'].sum()
        iva_rep = ingresos['iva'].sum()
        irpf = ingresos['irpf'].sum()
        
        base_gas = gastos['base'].sum()
        gastos_ded = gastos[gastos['iva_deducible'].str.upper() == 'SI'] if 'iva_deducible' in gastos.columns else gastos
        iva_sop = gastos_ded['iva'].sum()
        
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
# PROCESAMIENTO DE FACTURAS
# =========================
def process_uploaded_files(uploaded_files, tipo_documento):
    """Procesa los archivos subidos."""
    from gastos.processor import process_gasto
    from ingresos.processor import process_ingreso
    
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, uploaded_file in enumerate(uploaded_files):
        filename = uploaded_file.name
        file_bytes = uploaded_file.read()
        
        status_text.text(f"Procesando: {filename}")
        
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        if f".{ext}" not in SUPPORTED_EXTENSIONS:
            results.append({
                "filename": filename,
                "status": "error",
                "reason": f"Extensión no soportada: .{ext}",
            })
            continue
        
        try:
            if tipo_documento == "Ingreso":
                result = process_ingreso(file_bytes, filename)
            elif tipo_documento == "Gasto - Factura":
                result = process_gasto(file_bytes, filename, subtipo="factura")
            elif tipo_documento == "Gasto - Ticket":
                result = process_gasto(file_bytes, filename, subtipo="ticket")
            else:
                result = {"status": "error", "reason": "Tipo desconocido"}
            
            results.append({
                "filename": filename,
                "status": result.get("status"),
                "reason": result.get("reason", ""),
                "data": result.get("data", {}),
            })
        except Exception as e:
            results.append({
                "filename": filename,
                "status": "error",
                "reason": str(e),
            })
        
        progress_bar.progress((i + 1) / len(uploaded_files))
        time.sleep(0.5)
    
    progress_bar.empty()
    status_text.empty()
    
    return results


def show_results(results):
    """Muestra los resultados del procesamiento."""
    processed = [r for r in results if r["status"] == "processed"]
    duplicates = [r for r in results if r["status"] == "duplicate"]
    reviews = [r for r in results if r["status"] == "review"]
    errors = [r for r in results if r["status"] == "error"]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Procesados", len(processed))
    col2.metric("⚠️ Duplicados", len(duplicates))
    col3.metric("🔍 A Revisar", len(reviews))
    col4.metric("❌ Errores", len(errors))
    
    st.divider()
    
    if processed:
        st.subheader("✅ Procesados correctamente")
        for r in processed:
            data = r.get("data", {})
            with st.expander(f"📄 {r['filename']}"):
                col1, col2 = st.columns(2)
                col1.write(f"**Proveedor/Cliente:** {data.get('proveedor_cliente', 'N/A')}")
                col1.write(f"**Fecha:** {data.get('fecha', 'N/A')}")
                col2.write(f"**Total:** {data.get('total', 'N/A')} €")
                col2.write(f"**Nº Factura:** {data.get('numero_factura', 'N/A')}")
    
    if duplicates:
        st.subheader("⚠️ Duplicados (ya existían)")
        for r in duplicates:
            st.write(f"- {r['filename']}")
    
    if reviews:
        st.subheader("🔍 Enviados a REVIEW")
        for r in reviews:
            st.write(f"- {r['filename']}: {r.get('reason', 'Sin razón')}")
    
    if errors:
        st.subheader("❌ Errores")
        for r in errors:
            st.error(f"{r['filename']}: {r.get('reason', 'Error desconocido')}")


# =========================
# INTERFAZ PRINCIPAL
# =========================
def main():
    st.set_page_config(page_title="Facturas Bot", page_icon="🧾", layout="wide")
    
    if not check_password():
        return
    
    # Header
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title("🧾 Facturas Bot")
    with col2:
        if st.button("🚪 Salir"):
            st.session_state["authenticated"] = False
            # Limpiar token de la URL
            st.query_params.clear()
            st.rerun()
    
    # Cargar datos
    df = load_movimientos()
    
    # Selector de año
    if not df.empty:
        years = sorted(df['anio_trimestre'].str[:4].unique(), reverse=True)
        year = st.selectbox("Año", years, index=0)
    else:
        year = datetime.now().year
        st.warning("No hay datos en el Sheet")
    
    # Métricas principales
    resumen = pd.DataFrame()
    totales = None
    if not df.empty:
        resumen = calcular_resumen(df, year)
        
        if not resumen.empty:
            totales = resumen.sum(numeric_only=True)
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 Ingresos", f"{totales['Base Ingresos']:,.2f} €")
            c2.metric("💸 Gastos", f"{totales['Base Gastos']:,.2f} €")
            c3.metric("📊 IVA a Pagar", f"{totales['IVA Neto']:,.2f} €")
            c4.metric("🏛️ IRPF Retenido", f"{totales['IRPF Retenido']:,.2f} €")
    
    st.divider()
    
    # Pestañas
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumen IVA", "📄 Facturas", "📤 Subir", "⚙️ Config"])
    
    # TAB 1: Resumen IVA
    with tab1:
        st.subheader("Resumen IVA Trimestral")
        if not df.empty and not resumen.empty:
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
            if totales is not None:
                st.markdown(f"**Total IVA a Pagar/Devolver: {totales['IVA Neto']:,.2f} €**")
        else:
            st.info("No hay datos para mostrar")
    
    # TAB 2: Facturas
    with tab2:
        st.subheader("Facturas del Año")
        if not df.empty:
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
        else:
            st.info("No hay datos para mostrar")
    
    # TAB 3: Subir
    with tab3:
        st.subheader("📤 Subir Facturas")
        
        st.markdown("""
        Sube tus facturas y tickets para procesarlos automáticamente.
        - Se extrae el texto (OCR si es necesario)
        - Se parsean los datos (fecha, proveedor, total...)
        - Se guarda en el Sheet
        - Se sube el archivo a Google Drive
        """)
        
        tipo_documento = st.selectbox(
            "Tipo de documento",
            ["Ingreso", "Gasto - Factura", "Gasto - Ticket"],
            help="Selecciona el tipo antes de subir"
        )
        
        uploaded_files = st.file_uploader(
            "Arrastra o selecciona tus archivos",
            type=['pdf', 'jpg', 'jpeg', 'png'],
            accept_multiple_files=True,
            help="Puedes subir varios archivos a la vez"
        )
        
        if uploaded_files:
            st.write(f"**{len(uploaded_files)} archivo(s) seleccionado(s)**")
            
            if st.button("🚀 Procesar", type="primary", use_container_width=True):
                with st.spinner("Procesando facturas..."):
                    results = process_uploaded_files(uploaded_files, tipo_documento)
                
                st.success("¡Procesamiento completado!")
                show_results(results)
                
                load_movimientos.clear()
                
                if st.button("🔄 Ver datos actualizados"):
                    st.rerun()
    
    # TAB 4: Config
    with tab4:
        st.subheader("⚙️ Configuración")
        
        st.markdown("### 🔄 Sincronizar Registros")
        st.markdown("""
        Actualiza las pestañas del Sheet:
        - `registro_ingresos` - Lista de ingresos del año
        - `registro_gastos` - Lista de gastos del año  
        - `clientes` - Resumen de clientes
        - `config` - Año activo
        """)
        
        sync_year = st.number_input("Año a sincronizar", value=int(year), min_value=2020, max_value=2030)
        
        if st.button("🔄 Ejecutar Sync", type="primary"):
            with st.spinner("Sincronizando..."):
                result = run_sync(sync_year)
            
            st.success("¡Sync completado!")
            st.code(result)
            
            # Limpiar caché
            load_movimientos.clear()
        
        st.divider()
        
        st.markdown("### 📊 Estado del Sistema")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📁 Movimientos", len(df) if not df.empty else 0)
        with col2:
            st.metric("📅 Año seleccionado", year)
        
        st.divider()
        
        st.markdown("### 🔗 Enlaces útiles")
        st.markdown(f"- [📊 Google Sheet](https://docs.google.com/spreadsheets/d/{SHEET_ID})")
        st.markdown("- [📁 Drive - Procesadas](https://drive.google.com/drive/folders/1doiwiLU4RsSnWt_oCQgtxzleKeJwF7GW)")
        st.markdown("- [📁 Drive - Review](https://drive.google.com/drive/folders/1UkdmXDTew35o2gEubPQ4Uv1TL0gAphoQ)")


if __name__ == "__main__":
    main()
