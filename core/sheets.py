# core/sheets.py
"""
Operaciones con Google Sheets.
Versión WEB - usa Streamlit secrets para credenciales.
"""
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config.settings import SHEET_ID, WS_MOVIMIENTOS, GOOGLE_SCOPES


# Rate limit: espera entre llamadas a la API
API_DELAY = 1.5  # segundos


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _norm_invoice_id(s: Any) -> str:
    s = _safe_str(s).upper()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^A-Z0-9\-\/]", "", s)
    return s


def _norm_filename(s: Any) -> str:
    s = _safe_str(s).lower()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fix_private_key(pk: str) -> str:
    """Arregla el formato de la private_key si tiene espacios en vez de saltos de línea."""
    match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
    if not match:
        return pk
    content = match.group(1)
    content_clean = re.sub(r'\s+', '', content)
    lines = [content_clean[i:i+64] for i in range(0, len(content_clean), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


@st.cache_resource
def get_gspread_client():
    """Obtiene cliente gspread usando Streamlit secrets."""
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


def get_header_map(ws) -> Dict[str, int]:
    """Obtiene mapa de columna {nombre: índice_1_based}."""
    header = ws.row_values(1)
    return {h.strip(): i + 1 for i, h in enumerate(header) if h and str(h).strip()}


def _build_row_from_data(headers: List[str], data: Dict[str, Any]) -> List[Any]:
    """Construye una fila de valores a partir de los headers y data."""
    row = []
    for h in headers:
        val = data.get(h, "")
        if val is None:
            val = ""
        row.append(val)
    return row


def append_movimiento_with_dedupe(data: Dict[str, Any]) -> Tuple[str, Optional[int]]:
    """
    Inserta en 'movimientos' con dedupe básico.
    
    Returns:
        ("inserted", row_number) | ("duplicate", None) | ("error", None)
    """
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WS_MOVIMIENTOS)
        
        time.sleep(API_DELAY)

        # Leer todo de una sola vez para minimizar llamadas
        all_data = ws.get_all_values()
        
        if not all_data:
            return "error", None
        
        headers = all_data[0]
        hm = {h.strip(): i for i, h in enumerate(headers) if h and str(h).strip()}
        
        # Preparar datos para dedupe
        tipo = _safe_str(data.get("tipo")).lower()
        subtipo = _safe_str(data.get("subtipo")).lower()
        num_factura = _norm_invoice_id(data.get("numero_factura"))
        archivo = _norm_filename(data.get("archivo_drive"))
        
        # Verificar duplicado
        num_col = hm.get("numero_factura")
        tipo_col = hm.get("tipo")
        archivo_col = hm.get("archivo_drive")
        
        is_ticket = (subtipo == "ticket")
        
        for row in all_data[1:]:
            if is_ticket:
                # Para tickets: comparar por archivo
                if archivo_col is not None and archivo_col < len(row):
                    existing_archivo = _norm_filename(row[archivo_col])
                    if existing_archivo and existing_archivo == archivo:
                        return "duplicate", None
            else:
                # Para facturas: comparar por número de factura + tipo
                if num_col is not None and num_col < len(row):
                    existing_num = _norm_invoice_id(row[num_col])
                    if existing_num and existing_num == num_factura:
                        # Verificar también el tipo si está disponible
                        if tipo_col is not None and tipo_col < len(row):
                            existing_tipo = _safe_str(row[tipo_col]).lower()
                            if existing_tipo == tipo:
                                return "duplicate", None
                        else:
                            return "duplicate", None
        
        # No es duplicado, insertar
        row_idx = len(all_data) + 1
        row_values = _build_row_from_data(headers, data)
        
        a1_start = gspread.utils.rowcol_to_a1(row_idx, 1)
        a1_end = gspread.utils.rowcol_to_a1(row_idx, len(headers))
        
        time.sleep(API_DELAY)
        ws.update(range_name=f"{a1_start}:{a1_end}", values=[row_values], value_input_option="USER_ENTERED")
        
        return "inserted", row_idx

    except Exception as e:
        st.error(f"Error en sheets: {e}")
        return "error", None
