# core/sheets.py
"""
Operaciones con Google Sheets para PERSONAL.
Versión optimizada con rate limiting.
"""
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import (
    SERVICE_ACCOUNT_FILE, GOOGLE_SCOPES, SHEET_ID_PERSONAL,
    WS_MOVIMIENTOS
)


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


# Cache para evitar reconexiones
_gc_cache = None
_gc_cache_time = 0
_CACHE_TTL = 300  # 5 minutos


def gspread_client():
    """Obtiene cliente gspread con cache."""
    global _gc_cache, _gc_cache_time
    
    now = time.time()
    if _gc_cache is not None and (now - _gc_cache_time) < _CACHE_TTL:
        return _gc_cache
    
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=GOOGLE_SCOPES)
    _gc_cache = gspread.authorize(creds)
    _gc_cache_time = now
    return _gc_cache


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


# =========================
# APPEND MOVIMIENTO - VERSIÓN SIMPLIFICADA
# =========================
def append_movimiento_with_dedupe(data: Dict[str, Any], scope: str = "personal") -> Tuple[str, Optional[int]]:
    """
    Inserta en 'movimientos' con dedupe básico.
    
    Returns:
        ("inserted", row_number) | ("duplicate", None) | ("error", None)
    """
    try:
        gc = gspread_client()
        sh = gc.open_by_key(SHEET_ID_PERSONAL)
        ws = sh.worksheet(WS_MOVIMIENTOS)
        
        time.sleep(API_DELAY)

        # Leer todo de una sola vez para minimizar llamadas
        all_data = ws.get_all_values()
        
        if not all_data:
            print("ERROR: movimientos sin datos")
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
        print(f"ERROR: append_movimiento_with_dedupe: {e}")
        return "error", None
