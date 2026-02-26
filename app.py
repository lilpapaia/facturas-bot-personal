"""
Facturas Bot - Panel de Control Personal
Versión WEB completa con dashboard, procesamiento y sync.
"""
import streamlit as st
import pandas as pd
import re
import time
import hashlib
import io
from datetime import datetime, date

from config.settings import SHEET_ID, WS_MOVIMIENTOS, WS_BORRADOR, GOOGLE_SCOPES, SUPPORTED_EXTENSIONS, FOLDER_EMITIDAS


# =========================
# GENERACIÓN DE PDF DE FACTURA
# =========================
def generate_invoice_pdf(
    numero_factura: str,
    fecha: str,
    cliente_nombre: str,
    cliente_direccion: str,
    cliente_cif: str,
    conceptos: list,  # Lista de dicts: {descripcion, unidades, precio}
    irpf_percent: float = 0.15,
    iva_percent: float = 0.21,
) -> bytes:
    """
    Genera un PDF de factura con estilo profesional.
    
    Returns:
        Bytes del PDF generado
    """
    from fpdf import FPDF
    
    # Calcular totales
    subtotal = sum(c["unidades"] * c["precio"] for c in conceptos)
    irpf = round(subtotal * irpf_percent, 2)
    iva = round(subtotal * iva_percent, 2)
    total = round(subtotal - irpf + iva, 2)
    
    # Crear PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # === HEADER: FACTURA título ===
    pdf.set_fill_color(139, 0, 0)  # Rojo oscuro
    pdf.rect(0, 0, 210, 25, 'F')
    pdf.set_xy(0, 8)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "FACTURA", align="C")
    
    # === DATOS DEL EMISOR (derecha) ===
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(110, 35)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "Julio Taeño Muñoz", ln=True, align="R")
    pdf.set_font("Helvetica", size=9)
    pdf.set_x(110)
    pdf.cell(0, 4, "NIF: 05337839E", ln=True, align="R")
    pdf.set_x(110)
    pdf.cell(0, 4, "C/Travesía de San Joaquín, 4", ln=True, align="R")
    pdf.set_x(110)
    pdf.cell(0, 4, "28320 - Pinto - Madrid", ln=True, align="R")
    pdf.set_x(110)
    pdf.cell(0, 4, "SPAIN", ln=True, align="R")
    
    # === NÚMERO Y FECHA ===
    pdf.set_xy(20, 35)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(25, 7, "Número:", border=0)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(139, 0, 0)
    pdf.cell(50, 7, numero_factura, ln=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(20)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(25, 7, "Fecha:", border=0)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(50, 7, fecha, ln=True)
    
    # === DATOS DEL CLIENTE ===
    pdf.set_xy(20, 65)
    pdf.set_fill_color(31, 78, 121)  # Azul oscuro
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 6, " FACTURAR A:", fill=True, ln=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_x(20)
    pdf.cell(90, 6, cliente_nombre, ln=True)
    pdf.set_font("Helvetica", size=9)
    if cliente_direccion:
        pdf.set_x(20)
        pdf.multi_cell(90, 4, cliente_direccion)
    if cliente_cif:
        pdf.set_x(20)
        pdf.cell(90, 5, f"CIF/NIF: {cliente_cif}", ln=True)
    
    # === TABLA DE CONCEPTOS ===
    pdf.set_xy(20, 100)
    
    # Header de tabla
    pdf.set_fill_color(31, 78, 121)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(85, 8, " Descripción", border=1, fill=True, align="L")
    pdf.cell(20, 8, "Uds.", border=1, fill=True, align="C")
    pdf.cell(30, 8, "Precio/Ud.", border=1, fill=True, align="C")
    pdf.cell(35, 8, "Subtotal", border=1, fill=True, align="C")
    pdf.ln()
    
    # Filas de conceptos
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=9)
    fill_row = False
    for c in conceptos:
        if fill_row:
            pdf.set_fill_color(245, 245, 245)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.cell(85, 7, f" {c['descripcion'][:45]}", border=1, fill=True, align="L")
        pdf.cell(20, 7, str(c["unidades"]), border=1, fill=True, align="C")
        pdf.cell(30, 7, f"{c['precio']:.2f} €", border=1, fill=True, align="R")
        pdf.cell(35, 7, f"{c['unidades'] * c['precio']:.2f} €", border=1, fill=True, align="R")
        pdf.ln()
        fill_row = not fill_row
    
    # === TOTALES ===
    y_totales = pdf.get_y() + 5
    
    # Caja de totales
    pdf.set_xy(110, y_totales)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(40, 6, "Subtotal:", border=0, align="R")
    pdf.cell(35, 6, f"{subtotal:.2f} €", border=0, align="R")
    pdf.ln()
    
    if irpf_percent > 0:
        pdf.set_x(110)
        pdf.cell(40, 6, f"IRPF ({int(irpf_percent*100)}%):", border=0, align="R")
        pdf.set_text_color(180, 0, 0)
        pdf.cell(35, 6, f"-{irpf:.2f} €", border=0, align="R")
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
    
    if iva_percent > 0:
        pdf.set_x(110)
        pdf.cell(40, 6, f"IVA ({int(iva_percent*100)}%):", border=0, align="R")
        pdf.cell(35, 6, f"+{iva:.2f} €", border=0, align="R")
        pdf.ln()
    
    # Total final con fondo
    pdf.set_x(110)
    pdf.set_fill_color(139, 0, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(40, 10, "TOTAL:", border=0, fill=True, align="R")
    pdf.cell(35, 10, f"{total:.2f} €", border=0, fill=True, align="R")
    
    # === DATOS BANCARIOS ===
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(20, 230)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(170, 5, " DATOS DE PAGO", fill=True, ln=True)
    pdf.set_font("Helvetica", size=8)
    pdf.set_x(20)
    pdf.cell(170, 4, "Forma de pago: Transferencia bancaria a 30 días", ln=True)
    pdf.set_x(20)
    pdf.cell(170, 4, "IBAN: ES41 2100 3607 5613 0011 4646", ln=True)
    pdf.set_x(20)
    pdf.cell(170, 4, "BIC/SWIFT: CAIXESBBXXX", ln=True)
    
    # Retornar bytes
    return bytes(pdf.output())


def get_next_invoice_number(year: int, existing_numbers: list) -> str:
    """Genera el siguiente número de factura disponible."""
    prefix = f"DAZZ_{year}_"
    max_num = 0
    
    for num in existing_numbers:
        if num and num.startswith(prefix):
            try:
                n = int(num.replace(prefix, ""))
                if n > max_num:
                    max_num = n
            except:
                pass
    
    return f"{prefix}{str(max_num + 1).zfill(3)}"


# =========================
# ENVÍO DE EMAIL
# =========================
def send_email_with_attachments(
    to_email: str,
    subject: str,
    body: str,
    attachments: list,  # Lista de tuples: (filename, bytes)
) -> tuple:
    """
    Envía un email con adjuntos usando SMTP de Gmail.
    
    Returns:
        (success: bool, message: str)
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    
    try:
        sender_email = st.secrets["email"]["sender"]
        sender_password = st.secrets["email"]["password"]
    except KeyError:
        return False, "Configura email en Streamlit secrets"
    
    try:
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Cuerpo
        msg.attach(MIMEText(body, 'plain'))
        
        # Adjuntos
        for filename, file_bytes in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(file_bytes)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            msg.attach(part)
        
        # Enviar
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        
        return True, "Email enviado correctamente"
    
    except smtplib.SMTPAuthenticationError:
        return False, "Error de autenticación. Verifica la contraseña de aplicación."
    except Exception as e:
        return False, f"Error enviando email: {str(e)}"


def get_clientes_con_email():
    """Obtiene lista de clientes con su email desde el Sheet."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet("clientes")
        
        all_values = ws.get_all_values()
        if len(all_values) < 2:
            return {}
        
        headers = all_values[0]
        cliente_col = headers.index("cliente") if "cliente" in headers else -1
        email_col = headers.index("email") if "email" in headers else -1
        
        if cliente_col == -1:
            return {}
        
        clientes = {}
        for row in all_values[1:]:
            if len(row) > cliente_col and row[cliente_col].strip():
                cliente = row[cliente_col].strip()
                email = row[email_col].strip() if email_col != -1 and len(row) > email_col else ""
                clientes[cliente] = email
        
        return clientes
    except:
        return {}


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


def load_borrador():
    """Carga datos de borrador_emitidas."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_BORRADOR)
        
        all_values = ws.get_all_values()
        
        if len(all_values) < 2:
            return pd.DataFrame(), []
        
        headers = all_values[0]
        data_rows = all_values[1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        
        # Filtrar filas vacías
        if 'numero_factura' in df.columns:
            df = df[df['numero_factura'].str.strip() != '']
        
        return df, headers
    except Exception as e:
        st.error(f"Error cargando borrador: {e}")
        return pd.DataFrame(), []


def save_to_borrador(data: dict):
    """Guarda una factura en borrador_emitidas con estilo."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_BORRADOR)
        
        # Obtener headers
        headers = ws.row_values(1)
        
        # Si no hay headers, crearlos (mismos que movimientos) y aplicar estilo
        if not headers or headers[0] == '':
            ws_mov = sh.worksheet(WS_MOVIMIENTOS)
            headers = ws_mov.row_values(1)
            ws.update('A1', [headers])
            time.sleep(1)
            
            # Aplicar formato al header (azul como movimientos)
            ws_id = ws.id
            requests = [{
                "repeatCell": {
                    "range": {
                        "sheetId": ws_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.122, "green": 0.306, "blue": 0.475},
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True
                            },
                            "horizontalAlignment": "CENTER"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            }]
            sh.batch_update({"requests": requests})
            time.sleep(1)
        
        # Construir fila
        row = []
        for h in headers:
            row.append(data.get(h, ""))
        
        # Añadir al final
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.error(f"Error guardando en borrador: {e}")
        return False


def move_borrador_to_movimientos(numero_factura: str):
    """Mueve una factura de borrador_emitidas a movimientos."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws_borrador = sh.worksheet(WS_BORRADOR)
        ws_mov = sh.worksheet(WS_MOVIMIENTOS)
        
        # Leer borrador
        all_values = ws_borrador.get_all_values()
        if len(all_values) < 2:
            return False, "Borrador vacío"
        
        headers = all_values[0]
        num_col = headers.index("numero_factura") if "numero_factura" in headers else -1
        
        if num_col == -1:
            return False, "Columna numero_factura no encontrada"
        
        # Buscar la fila
        row_idx = None
        row_data = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > num_col and row[num_col].strip().upper() == numero_factura.strip().upper():
                row_idx = i
                row_data = row
                break
        
        if row_idx is None:
            return False, "Factura no encontrada en borrador"
        
        # Añadir a movimientos
        ws_mov.append_row(row_data, value_input_option="USER_ENTERED")
        time.sleep(1)
        
        # Borrar de borrador
        ws_borrador.delete_rows(row_idx)
        
        return True, "OK"
    except Exception as e:
        return False, str(e)


def delete_from_borrador(numero_factura: str):
    """Elimina una factura del borrador sin moverla."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws_borrador = sh.worksheet(WS_BORRADOR)
        
        all_values = ws_borrador.get_all_values()
        if len(all_values) < 2:
            return False
        
        headers = all_values[0]
        num_col = headers.index("numero_factura") if "numero_factura" in headers else -1
        
        if num_col == -1:
            return False
        
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > num_col and row[num_col].strip().upper() == numero_factura.strip().upper():
                ws_borrador.delete_rows(i)
                return True
        
        return False
    except Exception as e:
        st.error(f"Error eliminando de borrador: {e}")
        return False


# =========================
# SYNC - Actualiza registros y clientes (COMPLETO con formato)
# =========================

# Colores para formato
COLOR_YEAR_BG = "#8B0000"     # rojo oscuro
COLOR_Q_BG    = "#0B3D2E"     # verde oscuro
COLOR_HDR_BG  = "#1F4E79"     # azul
COLOR_WHITE   = "#FFFFFF"

# Columnas en REGISTRO
REG_COLUMNS = [
    "fecha", "tipo", "proveedor_cliente", "tax_id", "numero_factura",
    "base", "iva", "irpf", "total", "moneda", "ambito", "archivo_drive",
    "procesado_el", "anio_trimestre",
]

def hex_to_rgb01(hex_color: str) -> dict:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}

def fmt_request(sheet_id: int, r0: int, r1: int, c0: int, c1: int,
                bg: str, fg: str, bold: bool = True, center: bool = False):
    req = {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r0,
                "endRowIndex": r1,
                "startColumnIndex": c0,
                "endColumnIndex": c1,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": hex_to_rgb01(bg),
                    "textFormat": {"foregroundColor": hex_to_rgb01(fg), "bold": bold},
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    }
    if center:
        req["repeatCell"]["cell"]["userEnteredFormat"]["horizontalAlignment"] = "CENTER"
        req["repeatCell"]["fields"] += ",userEnteredFormat(horizontalAlignment)"
    return req

def reset_format_request(sheet_id: int, rows: int, cols: int):
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": rows,
                "startColumnIndex": 0,
                "endColumnIndex": cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": False},
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    }

def build_registro_rows_and_formats(movs: list, year: int, tipo_filter: str, title: str):
    """Construye filas con estructura Q1-Q4 y retorna posiciones para formato."""
    BLANK_LINES = 5
    
    # Agrupar por trimestre
    by_q = {1: [], 2: [], 3: [], 4: []}
    for m in movs:
        anio_trim = m.get("anio_trimestre", "")
        if not anio_trim.startswith(str(year)):
            continue
        tipo = m.get("tipo", "").lower()
        if tipo_filter and tipo != tipo_filter.lower():
            continue
        try:
            q = int(anio_trim.split("-Q")[1])
            if q in by_q:
                by_q[q].append(m)
        except:
            pass
    
    width = len(REG_COLUMNS)
    rows = []
    fmt = {"year_rows": [], "q_rows": [], "hdr_rows": []}
    
    # Cabecera
    rows.append([title] + [""] * (width - 1))
    rows.append([f"Año activo: {year}"] + [""] * (width - 1))
    rows.append([f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"] + [""] * (width - 1))
    rows.append([""] * width)
    
    current_row = 5  # 1-indexed para formato
    
    # Fila del año
    rows.append([str(year)] + [""] * (width - 1))
    fmt["year_rows"].append(current_row)
    current_row += 1
    rows.append([""] * width)
    current_row += 1
    
    # Por cada trimestre
    for q in [1, 2, 3, 4]:
        # Fila trimestre
        rows.append([f"{year} - Q{q}"] + [""] * (width - 1))
        fmt["q_rows"].append(current_row)
        current_row += 1
        
        # Headers
        rows.append(REG_COLUMNS)
        fmt["hdr_rows"].append(current_row)
        current_row += 1
        
        # Datos del trimestre
        items = sorted(by_q[q], key=lambda m: (m.get("fecha", ""), m.get("numero_factura", "")))
        if items:
            for m in items:
                rows.append([m.get(c, "") for c in REG_COLUMNS])
                current_row += 1
        else:
            rows.append([""] * width)
            current_row += 1
        
        # Líneas en blanco
        for _ in range(BLANK_LINES):
            rows.append([""] * width)
            current_row += 1
    
    return rows, fmt

def run_sync(year: int):
    """Ejecuta sincronización completa con formato."""
    import gspread
    
    gc = get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)
    
    # Leer movimientos
    ws_mov = sh.worksheet(WS_MOVIMIENTOS)
    all_values = ws_mov.get_all_values()
    
    if len(all_values) < 2:
        return "No hay datos para sincronizar"
    
    headers = all_values[0]
    hm = {h.strip(): i for i, h in enumerate(headers) if h and str(h).strip()}
    
    def get_val(row, key):
        idx = hm.get(key)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()
    
    # Construir lista de movimientos como dicts
    movs = []
    for row in all_values[1:]:
        fecha = get_val(row, "fecha")
        anio_trim = get_val(row, "anio_trimestre")
        if not fecha and not anio_trim:
            continue
        m = {h: get_val(row, h) for h in hm.keys()}
        
        # Calcular anio_trimestre si no existe
        if fecha and not anio_trim:
            try:
                y = int(fecha[:4])
                mes = int(fecha[5:7])
                q = (mes - 1) // 3 + 1
                m["anio_trimestre"] = f"{y}-Q{q}"
            except:
                pass
        movs.append(m)
    
    results = []
    registro_written = []
    
    time.sleep(1)
    
    # CLIENTES
    try:
        ws_cli = sh.worksheet("clientes")
        
        # Calcular clientes desde ingresos
        clientes_data = {}
        for m in movs:
            if m.get("tipo", "").lower() != "ingreso":
                continue
            if not m.get("anio_trimestre", "").startswith(str(year)):
                continue
            cliente = m.get("proveedor_cliente", "").strip()
            if not cliente:
                continue
            if cliente not in clientes_data:
                clientes_data[cliente] = {"tax_id": m.get("tax_id", ""), "count": 0, "total": 0.0}
            clientes_data[cliente]["count"] += 1
            try:
                clientes_data[cliente]["total"] += float(m.get("total", "0").replace(",", ".") or 0)
            except:
                pass
        
        cli_rows = [["cliente", "tax_id", "n_facturas", "total_facturado"]]
        for cli, data in sorted(clientes_data.items()):
            cli_rows.append([cli, data["tax_id"], data["count"], round(data["total"], 2)])
        
        ws_cli.clear()
        ws_cli.update(range_name="A1", values=cli_rows, value_input_option="USER_ENTERED")
        results.append(f"✅ clientes: {len(clientes_data)} clientes")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ clientes: {e}")
    
    # REGISTRO INGRESOS
    try:
        ws_ing = sh.worksheet("registro_ingresos")
        ws_ing.clear()
        rows_ing, fmt_ing = build_registro_rows_and_formats(movs, year, "ingreso", "REGISTRO INGRESOS (auto)")
        ws_ing.update(range_name="A1", values=rows_ing, value_input_option="USER_ENTERED")
        registro_written.append((ws_ing, fmt_ing))
        results.append(f"✅ registro_ingresos: {len([m for m in movs if m.get('tipo','').lower()=='ingreso' and m.get('anio_trimestre','').startswith(str(year))])} filas")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ registro_ingresos: {e}")
    
    # REGISTRO GASTOS
    try:
        ws_gas = sh.worksheet("registro_gastos")
        ws_gas.clear()
        rows_gas, fmt_gas = build_registro_rows_and_formats(movs, year, "gasto", "REGISTRO GASTOS (auto)")
        ws_gas.update(range_name="A1", values=rows_gas, value_input_option="USER_ENTERED")
        registro_written.append((ws_gas, fmt_gas))
        results.append(f"✅ registro_gastos: {len([m for m in movs if m.get('tipo','').lower()=='gasto' and m.get('anio_trimestre','').startswith(str(year))])} filas")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ registro_gastos: {e}")
    
    # CONFIG - Actualizar año
    try:
        ws_cfg = sh.worksheet("config")
        ws_cfg.update(range_name="B2", values=[[year]], value_input_option="USER_ENTERED")
        results.append(f"✅ config: año {year}")
        time.sleep(1)
    except Exception as e:
        results.append(f"⚠️ config: {e}")
    
    # FORMATO (colores)
    requests = []
    
    # Header movimientos
    try:
        mov_sheet_id = ws_mov.id
        n_mov_cols = len(headers)
        requests.append(fmt_request(mov_sheet_id, 0, 1, 0, n_mov_cols, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    except:
        pass
    
    # Header clientes
    try:
        ws_cli = sh.worksheet("clientes")
        cli_sheet_id = ws_cli.id
        requests.append(fmt_request(cli_sheet_id, 0, 1, 0, 4, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    except:
        pass
    
    # Registros (ingresos y gastos)
    for ws, fmt in registro_written:
        reg_sheet_id = ws.id
        width = len(REG_COLUMNS)
        
        # Reset formato
        requests.append(reset_format_request(reg_sheet_id, rows=200, cols=width))
        
        # Año (rojo)
        for r in fmt["year_rows"]:
            requests.append(fmt_request(reg_sheet_id, r - 1, r, 0, width, COLOR_YEAR_BG, COLOR_WHITE, bold=True))
        
        # Trimestres (verde)
        for r in fmt["q_rows"]:
            requests.append(fmt_request(reg_sheet_id, r - 1, r, 0, width, COLOR_Q_BG, COLOR_WHITE, bold=True))
        
        # Headers (azul)
        for r in fmt["hdr_rows"]:
            requests.append(fmt_request(reg_sheet_id, r - 1, r, 0, width, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    
    # Aplicar formato
    if requests:
        try:
            sh.batch_update({"requests": requests})
            results.append("✅ Formato aplicado")
        except Exception as e:
            results.append(f"⚠️ Formato: {e}")
    
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
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Resumen IVA", "📄 Facturas", "📤 Subir", "📝 Crear Factura", "⏳ Pendientes", "⚙️ Config"])
    
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
    
    # TAB 4: Crear Factura
    with tab4:
        st.subheader("📝 Crear Factura")
        
        st.markdown("Genera una nueva factura de ingresos.")
        
        # Obtener clientes existentes
        clientes_list = []
        if not df.empty and 'proveedor_cliente' in df.columns:
            clientes_list = df[df['tipo'].str.lower() == 'ingreso']['proveedor_cliente'].dropna().unique().tolist()
        
        # Obtener números de factura existentes para calcular el siguiente
        existing_numbers = []
        if not df.empty and 'numero_factura' in df.columns:
            existing_numbers = df['numero_factura'].dropna().tolist()
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Número de factura (auto-generado)
            current_year = datetime.now().year
            suggested_number = get_next_invoice_number(current_year, existing_numbers)
            numero_factura = st.text_input("Número de Factura", value=suggested_number)
            
            # Fecha
            fecha_factura = st.date_input("Fecha", value=date.today())
        
        with col2:
            # Cliente
            cliente_opcion = st.selectbox(
                "Cliente",
                options=["-- Nuevo cliente --"] + clientes_list,
                index=0
            )
            
            if cliente_opcion == "-- Nuevo cliente --":
                cliente_nombre = st.text_input("Nombre del cliente")
            else:
                cliente_nombre = cliente_opcion
        
        cliente_direccion = st.text_input("Dirección del cliente", placeholder="C/ Example, 123 - 28000 Madrid")
        cliente_cif = st.text_input("CIF/NIF del cliente", placeholder="B12345678")
        
        st.divider()
        
        # Conceptos
        st.markdown("### Conceptos")
        
        # Inicializar conceptos en session_state
        if "conceptos" not in st.session_state:
            st.session_state.conceptos = [{"descripcion": "", "unidades": 1, "precio": 0.0}]
        
        total_subtotal = 0
        conceptos_validos = []
        
        for i, concepto in enumerate(st.session_state.conceptos):
            col1, col2, col3, col4 = st.columns([4, 1, 2, 1])
            
            with col1:
                desc = st.text_input(f"Descripción", key=f"desc_{i}", value=concepto.get("descripcion", ""))
            with col2:
                unid = st.number_input(f"Uds", key=f"unid_{i}", value=concepto.get("unidades", 1), min_value=1)
            with col3:
                precio = st.number_input(f"Precio €", key=f"precio_{i}", value=concepto.get("precio", 0.0), min_value=0.0, step=10.0)
            with col4:
                subtotal_linea = unid * precio
                st.markdown(f"**{subtotal_linea:.2f} €**")
            
            if desc and precio > 0:
                conceptos_validos.append({"descripcion": desc, "unidades": unid, "precio": precio})
                total_subtotal += subtotal_linea
            
            st.session_state.conceptos[i] = {"descripcion": desc, "unidades": unid, "precio": precio}
        
        col_add, col_remove = st.columns(2)
        with col_add:
            if st.button("➕ Añadir línea"):
                st.session_state.conceptos.append({"descripcion": "", "unidades": 1, "precio": 0.0})
                st.rerun()
        with col_remove:
            if len(st.session_state.conceptos) > 1 and st.button("➖ Quitar última"):
                st.session_state.conceptos.pop()
                st.rerun()
        
        st.divider()
        
        # Resumen
        col1, col2 = st.columns(2)
        
        with col1:
            irpf_percent = st.selectbox("IRPF", [0.15, 0.07, 0.0], format_func=lambda x: f"{int(x*100)}%")
            iva_percent = st.selectbox("IVA", [0.21, 0.10, 0.04, 0.0], format_func=lambda x: f"{int(x*100)}%")
        
        with col2:
            irpf_amount = round(total_subtotal * irpf_percent, 2)
            iva_amount = round(total_subtotal * iva_percent, 2)
            total_final = round(total_subtotal - irpf_amount + iva_amount, 2)
            
            st.metric("Subtotal", f"{total_subtotal:.2f} €")
            st.metric("IRPF", f"-{irpf_amount:.2f} €")
            st.metric("IVA", f"+{iva_amount:.2f} €")
            st.metric("**TOTAL**", f"**{total_final:.2f} €**")
        
        st.divider()
        
        # Generar factura
        if st.button("🚀 Generar Factura", type="primary", use_container_width=True):
            # Validaciones
            if not numero_factura:
                st.error("Falta el número de factura")
            elif not cliente_nombre:
                st.error("Falta el nombre del cliente")
            elif not conceptos_validos:
                st.error("Añade al menos un concepto con descripción y precio")
            else:
                with st.spinner("Generando factura..."):
                    try:
                        # Generar PDF
                        pdf_bytes = generate_invoice_pdf(
                            numero_factura=numero_factura,
                            fecha=fecha_factura.strftime("%Y-%m-%d"),
                            cliente_nombre=cliente_nombre,
                            cliente_direccion=cliente_direccion or "",
                            cliente_cif=cliente_cif or "",
                            conceptos=conceptos_validos,
                            irpf_percent=irpf_percent,
                            iva_percent=iva_percent,
                        )
                        
                        filename = f"{numero_factura}.pdf"
                        
                        # Calcular año/trimestre
                        fecha_str = fecha_factura.strftime("%Y-%m-%d")
                        y = fecha_factura.year
                        m = fecha_factura.month
                        q = (m - 1) // 3 + 1
                        anio_trimestre = f"{y}-Q{q}"
                        
                        # Construir descripción concatenada
                        descripcion = "; ".join([c["descripcion"] for c in conceptos_validos])
                        
                        # Guardar en borrador_emitidas
                        data_borrador = {
                            "procesado_el": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "anio_trimestre": anio_trimestre,
                            "fecha": fecha_str,
                            "tipo": "ingreso",
                            "subtipo": "factura",
                            "proveedor_cliente": cliente_nombre,
                            "tax_id": cliente_cif or "",
                            "numero_factura": numero_factura,
                            "base": total_subtotal,
                            "iva": iva_amount,
                            "irpf": irpf_amount,
                            "total": total_final,
                            "moneda": "EUR",
                            "ambito": "NACIONAL" if (cliente_cif or "").startswith(("A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P", "Q", "R", "S", "U", "V", "W")) else "COMUNITARIO",
                            "categoria": descripcion[:100],
                            "archivo_drive": filename,
                            "drive_file_id": "",
                            "review_reason": "",
                            "extraction_mode": "generado",
                            "iva_deducible": "",
                        }
                        
                        saved = save_to_borrador(data_borrador)
                        
                        if saved:
                            st.success(f"✅ Factura {numero_factura} creada y guardada en Pendientes")
                            
                            # Guardar PDF en session_state para envío posterior
                            st.session_state['ultimo_pdf'] = pdf_bytes
                            st.session_state['ultimo_pdf_nombre'] = filename
                            st.session_state['ultimo_cliente'] = cliente_nombre
                            st.session_state['ultimo_total'] = total_final
                            st.session_state['ultimo_numero'] = numero_factura
                            
                            # Botón de descarga
                            st.download_button(
                                "📥 Descargar PDF",
                                data=pdf_bytes,
                                file_name=filename,
                                mime="application/pdf",
                                type="primary"
                            )
                            
                            st.info("💡 Ve a la pestaña **⏳ Pendientes** para confirmar y registrar en movimientos")
                            
                            # Limpiar formulario
                            st.session_state.conceptos = [{"descripcion": "", "unidades": 1, "precio": 0.0}]
                        else:
                            st.error("Error guardando en borrador")
                            # Aun así permitir descarga
                            st.download_button(
                                "📥 Descargar PDF (sin guardar)",
                                data=pdf_bytes,
                                file_name=filename,
                                mime="application/pdf"
                            )
                    
                    except Exception as e:
                        st.error(f"Error generando factura: {e}")
        
        # Sección de envío de email (aparece si hay factura generada)
        if st.session_state.get('ultimo_pdf'):
            st.divider()
            st.markdown("### 📧 Enviar Factura por Email")
            
            # Obtener clientes con email
            clientes_email = get_clientes_con_email()
            
            # Selector de destinatario
            col1, col2 = st.columns([2, 2])
            
            with col1:
                ultimo_cliente = st.session_state.get('ultimo_cliente', '')
                email_cliente = clientes_email.get(ultimo_cliente, '')
                
                opciones_email = ["Escribir email manualmente"]
                if email_cliente:
                    opciones_email.insert(0, f"{ultimo_cliente} ({email_cliente})")
                
                # Añadir otros clientes con email
                for cli, email in clientes_email.items():
                    if email and cli != ultimo_cliente:
                        opciones_email.append(f"{cli} ({email})")
                
                seleccion_email = st.selectbox("Destinatario", opciones_email)
                
                if seleccion_email == "Escribir email manualmente":
                    email_destino = st.text_input("Email", placeholder="cliente@empresa.com")
                else:
                    # Extraer email del string "Cliente (email@...)"
                    email_destino = seleccion_email.split("(")[-1].replace(")", "").strip()
            
            with col2:
                asunto_default = f"Factura {st.session_state.get('ultimo_numero', '')}"
                asunto = st.text_input("Asunto", value=asunto_default)
            
            cuerpo_default = f"""Estimado/a cliente,

Adjunto le envío la factura {st.session_state.get('ultimo_numero', '')} por un total de {st.session_state.get('ultimo_total', 0):.2f} €.

Quedo a su disposición para cualquier consulta.

Un saludo,
Julio Taeño"""
            
            cuerpo = st.text_area("Mensaje", value=cuerpo_default, height=150)
            
            # Adjuntos adicionales
            adjuntos_extra = st.file_uploader(
                "Adjuntos adicionales (opcional)",
                accept_multiple_files=True,
                help="Puedes adjuntar más archivos además de la factura"
            )
            
            # Botón enviar
            if st.button("📧 Enviar Email", type="primary"):
                if not email_destino or "@" not in email_destino:
                    st.error("Introduce un email válido")
                else:
                    with st.spinner("Enviando email..."):
                        # Preparar adjuntos
                        adjuntos = [(st.session_state['ultimo_pdf_nombre'], st.session_state['ultimo_pdf'])]
                        
                        # Añadir adjuntos extra
                        for adj in adjuntos_extra:
                            adjuntos.append((adj.name, adj.read()))
                        
                        # Enviar
                        ok, msg = send_email_with_attachments(
                            to_email=email_destino,
                            subject=asunto,
                            body=cuerpo,
                            attachments=adjuntos
                        )
                        
                        if ok:
                            st.success(f"✅ Email enviado a {email_destino}")
                            # Limpiar session
                            del st.session_state['ultimo_pdf']
                            del st.session_state['ultimo_pdf_nombre']
                        else:
                            st.error(msg)
    
    # TAB 5: Pendientes
    with tab5:
        st.subheader("⏳ Facturas Pendientes de Confirmar")
        
        st.markdown("""
        Facturas creadas que aún no están registradas en movimientos.
        Revisa que estén correctas y confírmalas.
        """)
        
        # Cargar borrador
        df_borrador, headers_borrador = load_borrador()
        
        if df_borrador.empty:
            st.success("✅ No hay facturas pendientes. Todas están confirmadas.")
        else:
            st.warning(f"**{len(df_borrador)} factura(s) pendiente(s) de confirmar**")
            
            # Mostrar tabla resumen
            cols_mostrar = ['numero_factura', 'fecha', 'proveedor_cliente', 'total']
            cols_exist = [c for c in cols_mostrar if c in df_borrador.columns]
            
            if cols_exist:
                st.dataframe(
                    df_borrador[cols_exist],
                    use_container_width=True,
                    hide_index=True
                )
            
            st.divider()
            
            # Selección para confirmar
            st.markdown("### Confirmar facturas")
            
            numeros_pendientes = df_borrador['numero_factura'].tolist() if 'numero_factura' in df_borrador.columns else []
            
            seleccionados = st.multiselect(
                "Selecciona las facturas a confirmar:",
                options=numeros_pendientes,
                default=[]
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                if seleccionados and st.button("✅ Confirmar seleccionadas", type="primary"):
                    progress = st.progress(0)
                    resultados = []
                    
                    for i, num in enumerate(seleccionados):
                        ok, msg = move_borrador_to_movimientos(num)
                        resultados.append({"numero": num, "ok": ok, "msg": msg})
                        progress.progress((i + 1) / len(seleccionados))
                        time.sleep(0.5)
                    
                    # Mostrar resultados
                    for r in resultados:
                        if r["ok"]:
                            st.success(f"✅ {r['numero']} → Registrada en movimientos")
                        else:
                            st.error(f"❌ {r['numero']}: {r['msg']}")
                    
                    # Limpiar caché
                    load_movimientos.clear()
                    st.info("Recarga la página para ver los cambios")
            
            with col2:
                if seleccionados and st.button("🗑️ Eliminar seleccionadas", type="secondary"):
                    for num in seleccionados:
                        delete_from_borrador(num)
                    st.warning(f"Eliminadas {len(seleccionados)} factura(s) del borrador")
                    st.info("Recarga la página para ver los cambios")
            
            st.divider()
            
            # Detalle de factura seleccionada
            if len(seleccionados) == 1:
                st.markdown("### Detalle")
                factura = df_borrador[df_borrador['numero_factura'] == seleccionados[0]]
                if not factura.empty:
                    row = factura.iloc[0]
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Número:** {row.get('numero_factura', '')}")
                        st.write(f"**Fecha:** {row.get('fecha', '')}")
                        st.write(f"**Cliente:** {row.get('proveedor_cliente', '')}")
                        st.write(f"**CIF:** {row.get('tax_id', '')}")
                    with col2:
                        st.write(f"**Base:** {row.get('base', '')} €")
                        st.write(f"**IVA:** {row.get('iva', '')} €")
                        st.write(f"**IRPF:** {row.get('irpf', '')} €")
                        st.write(f"**Total:** {row.get('total', '')} €")
    
    # TAB 6: Config
    with tab6:
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
