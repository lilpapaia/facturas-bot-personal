# core/sheets.py
"""
Operaciones con Google Sheets para PERSONAL.
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
    WS_MOVIMIENTOS, WS_PROVEEDORES
)


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


def gspread_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=GOOGLE_SCOPES)
    return gspread.authorize(creds)


def get_header_map(ws) -> Dict[str, int]:
    """Obtiene mapa de columna {nombre: índice_1_based}."""
    header = ws.row_values(1)
    return {h.strip(): i + 1 for i, h in enumerate(header) if h and str(h).strip()}


def get_next_row(ws, col_idx: int) -> int:
    """Obtiene la siguiente fila vacía en una columna."""
    vals = ws.col_values(col_idx)
    i = len(vals)
    while i > 1 and _safe_str(vals[i - 1]) == "":
        i -= 1
    return i + 1


# =========================
# DEDUPLICACIÓN
# =========================
def _existing_invoice_keys(ws, hm: Dict[str, int]) -> set:
    """Obtiene las claves de facturas existentes para dedupe."""
    num_col = hm.get("numero_factura")
    tipo_col = hm.get("tipo")
    
    if not num_col:
        return set()
    
    numeros = ws.col_values(num_col)[1:]
    tipos = ws.col_values(tipo_col)[1:] if tipo_col else None
    
    out = set()
    for i, raw_num in enumerate(numeros):
        nid = _norm_invoice_id(raw_num)
        if not nid:
            continue
        if tipos is not None and i < len(tipos):
            t = _safe_str(tipos[i]).lower()
            out.add((t, nid))
        else:
            out.add(("", nid))
    return out


def _existing_ticket_keys(ws, hm: Dict[str, int]) -> set:
    """Obtiene las claves de tickets existentes para dedupe."""
    archivo_col = hm.get("archivo_drive")
    subtipo_col = hm.get("subtipo")
    total_col = hm.get("total")
    
    if not archivo_col:
        return set()
    
    archivos = ws.col_values(archivo_col)[1:]
    subtipos = ws.col_values(subtipo_col)[1:] if subtipo_col else None
    totales = ws.col_values(total_col)[1:] if total_col else None
    
    out = set()
    for i, raw_archivo in enumerate(archivos):
        if subtipos is not None and i < len(subtipos):
            subtipo = _safe_str(subtipos[i]).lower()
            if subtipo != "ticket":
                continue
        
        filename = _norm_filename(raw_archivo)
        if not filename:
            continue
        
        total_norm = ""
        if totales is not None and i < len(totales):
            total_str = _safe_str(totales[i])
            total_str = total_str.replace("€", "").replace("EUR", "").strip().replace(" ", "")
            if "," in total_str and "." in total_str:
                total_str = total_str.replace(".", "").replace(",", ".")
            elif "," in total_str:
                total_str = total_str.replace(",", ".")
            try:
                total_norm = f"{float(total_str):.2f}"
            except:
                total_norm = total_str
        
        out.add((filename, total_norm))
    
    return out


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
# APPEND MOVIMIENTO
# =========================
def append_movimiento_with_dedupe(data: Dict[str, Any], scope: str = "personal") -> Tuple[str, Optional[int]]:
    """
    Inserta en 'movimientos' con dedupe.
    
    Returns:
        ("inserted", row_number) | ("duplicate", None) | ("error", None)
    """
    try:
        gc = gspread_client()
        sh = gc.open_by_key(SHEET_ID_PERSONAL)
        ws = sh.worksheet(WS_MOVIMIENTOS)

        hm = get_header_map(ws)
        if not hm:
            print("ERROR: movimientos sin cabecera en fila 1")
            return "error", None

        headers = ws.row_values(1)
        
        tipo = _safe_str(data.get("tipo")).lower()
        subtipo = _safe_str(data.get("subtipo")).lower()
        
        is_ticket = (subtipo == "ticket")
        
        if is_ticket:
            existing_tickets = _existing_ticket_keys(ws, hm)
            archivo = _norm_filename(data.get("archivo_drive"))
            
            total_raw = _safe_str(data.get("total"))
            total_raw = total_raw.replace("€", "").replace("EUR", "").strip().replace(" ", "")
            if "," in total_raw and "." in total_raw:
                total_raw = total_raw.replace(".", "").replace(",", ".")
            elif "," in total_raw:
                total_raw = total_raw.replace(",", ".")
            try:
                total_norm = f"{float(total_raw):.2f}"
            except:
                total_norm = total_raw
            
            if archivo and (archivo, total_norm) in existing_tickets:
                return "duplicate", None
        else:
            existing_invoices = _existing_invoice_keys(ws, hm)
            num = _norm_invoice_id(data.get("numero_factura"))
            
            if num:
                if ("", num) in existing_invoices or (tipo, num) in existing_invoices:
                    return "duplicate", None

        anchor_col = hm.get("fecha") or hm.get("procesado_el") or 1
        row_idx = get_next_row(ws, anchor_col)

        row_values = _build_row_from_data(headers, data)

        a1_start = gspread.utils.rowcol_to_a1(row_idx, 1)
        a1_end = gspread.utils.rowcol_to_a1(row_idx, len(headers))

        ws.update(range_name=f"{a1_start}:{a1_end}", values=[row_values], value_input_option="USER_ENTERED")
        return "inserted", row_idx

    except Exception as e:
        print(f"ERROR: append_movimiento_with_dedupe: {e}")
        return "error", None


# =========================
# PROVEEDORES
# =========================
def get_proveedor_categoria(tax_id: str, scope: str = "personal") -> Optional[str]:
    """Obtiene la categoría de un proveedor desde la pestaña 'proveedores'."""
    if not tax_id or not tax_id.strip():
        return None
    
    tax_id = tax_id.strip().upper()
    
    try:
        gc = gspread_client()
        sh = gc.open_by_key(SHEET_ID_PERSONAL)
        ws = sh.worksheet(WS_PROVEEDORES)
        
        hm = get_header_map(ws)
        tax_col = hm.get("tax_id") or hm.get("cif")
        cat_col = hm.get("categoria")
        
        if not tax_col or not cat_col:
            return None
        
        tax_ids = ws.col_values(tax_col)
        categorias = ws.col_values(cat_col)
        
        for i, tid in enumerate(tax_ids):
            if tid.strip().upper() == tax_id:
                if i < len(categorias):
                    return categorias[i].strip() or None
        
        return None
        
    except Exception:
        return None


def upsert_proveedor(data: Dict[str, Any], scope: str = "personal"):
    """Actualiza o inserta un proveedor."""
    tax_id = _safe_str(data.get("tax_id")).upper()
    if not tax_id:
        return
    
    try:
        gc = gspread_client()
        sh = gc.open_by_key(SHEET_ID_PERSONAL)
        ws = sh.worksheet(WS_PROVEEDORES)
        
        hm = get_header_map(ws)
        tax_col = hm.get("tax_id") or hm.get("cif")
        
        if not tax_col:
            return
        
        tax_ids = ws.col_values(tax_col)
        
        for i, tid in enumerate(tax_ids):
            if tid.strip().upper() == tax_id:
                return  # Ya existe
        
        # Insertar nuevo
        nombre = _safe_str(data.get("proveedor_cliente"))
        categoria = _safe_str(data.get("categoria"))
        
        headers = ws.row_values(1)
        new_row = [""] * len(headers)
        
        for i, h in enumerate(headers):
            h_lower = h.lower().strip()
            if h_lower in ("tax_id", "cif"):
                new_row[i] = tax_id
            elif h_lower in ("nombre", "proveedor"):
                new_row[i] = nombre
            elif h_lower == "categoria":
                new_row[i] = categoria
        
        next_row = len(tax_ids) + 1
        a1 = gspread.utils.rowcol_to_a1(next_row, 1)
        a2 = gspread.utils.rowcol_to_a1(next_row, len(headers))
        ws.update(range_name=f"{a1}:{a2}", values=[new_row], value_input_option="USER_ENTERED")
        
    except Exception as e:
        print(f"WARN: upsert_proveedor: {e}")
