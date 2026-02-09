#!/usr/bin/env python3
# sync_reporting.py
"""
Sincroniza registro_ingresos, registro_gastos, clientes + backup XLSX.
Versión PERSONAL - solo un Sheet.
"""
import os
import re
import io
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

sys.path.insert(0, os.path.dirname(__file__))
from config.settings import (
    SERVICE_ACCOUNT_FILE,
    SHEET_ID_PERSONAL,
    WS_MOVIMIENTOS,
    WS_INGRESOS,
    WS_GASTOS,
    WS_CLIENTES,
    WS_PROVEEDORES,
    WS_CONFIG,
    WS_HACIENDA,
    BACKUP_PERSONAL,
    EXCELS_LOCAL_DIR,
    GOOGLE_SCOPES,
)


# =========================
# CONFIG VISUAL
# =========================
CFG_YEAR_CELL = "B2"
BLANK_LINES_BETWEEN_QUARTERS = 5

# Colores (hex)
COLOR_YEAR_BG = "#8B0000"     # rojo oscuro
COLOR_Q_BG    = "#0B3D2E"     # verde oscuro
COLOR_HDR_BG  = "#1F4E79"     # azul
COLOR_WHITE   = "#FFFFFF"

# Columnas en REGISTRO
REG_COLUMNS = [
    "fecha",
    "tipo",
    "proveedor_cliente",
    "tax_id",
    "numero_factura",
    "base",
    "iva",
    "irpf",
    "total",
    "moneda",
    "ambito",
    "archivo_drive",
    "procesado_el",
    "anio_trimestre",
]


# =========================
# Utils
# =========================
def gspread_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=GOOGLE_SCOPES)
    return gspread.authorize(creds)


def parse_amount(x: Any) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return 0.0
    s = s.replace("€", "").replace("EUR", "").replace("EUROS", "").strip()
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[^\d,.\-]", "", s)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def safe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    s = str(x).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def build_a1_range(start_row: int, start_col: int, n_rows: int, n_cols: int) -> str:
    a1 = gspread.utils.rowcol_to_a1(start_row, start_col)
    b1 = gspread.utils.rowcol_to_a1(start_row + n_rows - 1, start_col + n_cols - 1)
    return f"{a1}:{b1}"


def chunked_update(ws, start_cell_a1: str, values: List[List[Any]], chunk_rows: int = 400):
    if not values:
        return
    start_row, start_col = gspread.utils.a1_to_rowcol(start_cell_a1)
    n_cols = max(len(r) for r in values)
    norm = [list(r) + [""] * (n_cols - len(r)) for r in values]
    for i in range(0, len(norm), chunk_rows):
        block = norm[i:i + chunk_rows]
        rng = build_a1_range(start_row + i, start_col, len(block), n_cols)
        ws.update(range_name=rng, values=block, value_input_option="USER_ENTERED")


def hex_to_rgb01(hex_color: str) -> Dict[str, float]:
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


# =========================
# Export backup
# =========================
def export_sheet_to_xlsx_local(sheet_id: str, out_path: str):
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=GOOGLE_SCOPES)
    drive = build("drive", "v3", credentials=creds)
    request = drive.files().export_media(
        fileId=sheet_id,
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(fh.getvalue())
    os.replace(tmp, out_path)


# =========================
# Read movimientos
# =========================
def read_movimientos(ws_mov) -> List[Dict[str, Any]]:
    raw = ws_mov.get_all_values()
    if not raw or len(raw) < 2:
        return []
    headers = [h.strip() for h in raw[0]]
    idx = {h: i for i, h in enumerate(headers) if h}

    def get(row: List[str], key: str) -> str:
        j = idx.get(key)
        if j is None or j >= len(row):
            return ""
        return row[j].strip()

    out: List[Dict[str, Any]] = []
    for r in raw[1:]:
        fecha = get(r, "fecha")
        if not fecha:
            continue
        row = {h: (r[idx[h]].strip() if idx[h] < len(r) else "") for h in idx.keys()}
        try:
            y = int(fecha[:4])
            mes = int(fecha[5:7])
            q = (mes - 1) // 3 + 1
            row["anio"] = str(y)
            row["trimestre"] = str(q)
            row["anio_trimestre"] = f"{y}-Q{q}"
        except Exception:
            pass
        out.append(row)
    return out


# =========================
# Active year
# =========================
def get_active_year(sh, movs: List[Dict[str, Any]]) -> int:
    try:
        ws_cfg = sh.worksheet(WS_CONFIG)
        val = ws_cfg.acell(CFG_YEAR_CELL).value
        if val:
            return int(val)
    except Exception:
        pass
    
    years = set()
    for m in movs:
        y = safe_int(m.get("anio"))
        if y and 2020 <= y <= 2030:
            years.add(y)
    return max(years) if years else datetime.now().year


# =========================
# Clientes
# =========================
def build_clientes_rows_for_year(movs: List[Dict[str, Any]], year: int) -> List[List[Any]]:
    ingresos = [m for m in movs if (m.get("tipo") or "").lower() == "ingreso" and safe_int(m.get("anio")) == year]
    
    cliente_data: Dict[str, Dict[str, Any]] = {}
    for m in ingresos:
        cli = (m.get("proveedor_cliente") or "").strip()
        if not cli:
            continue
        
        if cli not in cliente_data:
            cliente_data[cli] = {
                "tax_id": m.get("tax_id", ""),
                "n_facturas": 0,
                "total": 0.0,
            }
        
        cliente_data[cli]["n_facturas"] += 1
        cliente_data[cli]["total"] += parse_amount(m.get("total"))
    
    rows = [["cliente", "tax_id", "n_facturas", "total_facturado"]]
    for cli, data in sorted(cliente_data.items()):
        rows.append([cli, data["tax_id"], data["n_facturas"], round(data["total"], 2)])
    
    return rows


# =========================
# Proveedores stats
# =========================
def update_proveedores_stats(ws_prov, movs: List[Dict[str, Any]]):
    """Actualiza estadísticas de proveedores."""
    gastos = [m for m in movs if (m.get("tipo") or "").lower() == "gasto"]
    
    prov_stats: Dict[str, Dict[str, Any]] = {}
    for m in gastos:
        tid = (m.get("tax_id") or "").strip().upper()
        if not tid:
            continue
        
        if tid not in prov_stats:
            prov_stats[tid] = {
                "n_gastos": 0,
                "total": 0.0,
                "meses": set(),
                "fechas": [],
                "ultimo": None,
            }
        
        prov_stats[tid]["n_gastos"] += 1
        prov_stats[tid]["total"] += parse_amount(m.get("total"))
        
        fecha = m.get("fecha", "")
        if fecha:
            prov_stats[tid]["fechas"].append(fecha)
            try:
                mes = fecha[:7]
                prov_stats[tid]["meses"].add(mes)
            except:
                pass
            if not prov_stats[tid]["ultimo"] or fecha > prov_stats[tid]["ultimo"]:
                prov_stats[tid]["ultimo"] = fecha
    
    # Leer headers
    headers = ws_prov.row_values(1)
    hm = {h.lower().strip(): i + 1 for i, h in enumerate(headers)}
    
    tax_col = hm.get("tax_id") or hm.get("cif")
    n_col = hm.get("n_gastos")
    total_col = hm.get("total_gastado") or hm.get("total")
    rec_col = hm.get("recurrente")
    freq_col = hm.get("frecuencia")
    ultimo_col = hm.get("ultimo_gasto")
    
    if not tax_col:
        return
    
    tax_ids = ws_prov.col_values(tax_col)
    updates = []
    
    for row_idx, tid in enumerate(tax_ids[1:], start=2):
        tid_norm = tid.strip().upper()
        if tid_norm not in prov_stats:
            continue
        
        stats = prov_stats[tid_norm]
        
        if rec_col:
            recurrente = "SI" if len(stats["meses"]) >= 3 else "NO"
            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx, rec_col),
                "values": [[recurrente]]
            })
        
        if n_col:
            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx, n_col),
                "values": [[stats["n_gastos"]]]
            })
        
        if total_col:
            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx, total_col),
                "values": [[round(stats["total"], 2)]]
            })
        
        if ultimo_col and stats["ultimo"]:
            updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx, ultimo_col),
                "values": [[stats["ultimo"]]]
            })
    
    if updates:
        ws_prov.batch_update(updates, value_input_option="USER_ENTERED")


# =========================
# REGISTRO visual
# =========================
def build_registro_rows_and_formats_for_year(
    movs: List[Dict[str, Any]],
    year: int,
    tipo_filter: Optional[str] = None,
    title: str = "REGISTRO VISUAL (auto)",
) -> Tuple[List[List[Any]], Dict[str, List[int]]]:
    by_q: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: [], 4: []}
    for m in movs:
        y = safe_int(m.get("anio"))
        q = safe_int(m.get("trimestre"))
        if y != year or q not in (1, 2, 3, 4):
            continue
        if tipo_filter and (m.get("tipo") or "").strip().lower() != tipo_filter.lower():
            continue
        by_q[q].append(m)

    width = len(REG_COLUMNS)
    rows: List[List[Any]] = []
    fmt = {"year_rows": [], "q_rows": [], "hdr_rows": []}

    rows.append([title] + [""] * (width - 1))
    rows.append([f"Año activo: {year}"] + [""] * (width - 1))
    rows.append([f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"] + [""] * (width - 1))
    rows.append([""] * width)

    current_row = 5

    rows.append([str(year)] + [""] * (width - 1))
    fmt["year_rows"].append(current_row)
    current_row += 1
    rows.append([""] * width)
    current_row += 1

    for q in [1, 2, 3, 4]:
        rows.append([f"{year} - Q{q}"] + [""] * (width - 1))
        fmt["q_rows"].append(current_row)
        current_row += 1

        rows.append(REG_COLUMNS)
        fmt["hdr_rows"].append(current_row)
        current_row += 1

        items = sorted(by_q[q], key=lambda m: ((m.get("fecha") or ""), (m.get("numero_factura") or "")))
        if items:
            for m in items:
                rows.append([m.get(c, "") for c in REG_COLUMNS])
                current_row += 1
        else:
            rows.append([""] * width)
            current_row += 1

        for _ in range(BLANK_LINES_BETWEEN_QUARTERS):
            rows.append([""] * width)
            current_row += 1

    return rows, fmt


# =========================
# Sync Sheet
# =========================
def sync_sheet(sheet_id: str, name: str, backup_path: str):
    print(f"\n{'='*50}")
    print(f"SYNC: {name}")
    print(f"{'='*50}")
    
    gc = gspread_client()
    sh = gc.open_by_key(sheet_id)

    ws_mov = sh.worksheet(WS_MOVIMIENTOS)
    movs = read_movimientos(ws_mov)
    print(f"  Movimientos leídos: {len(movs)}")

    active_year = get_active_year(sh, movs)
    print(f"  Año activo: {active_year}")

    # CLIENTES
    try:
        ws_cli = sh.worksheet(WS_CLIENTES)
        ws_cli.clear()
        clientes_values = build_clientes_rows_for_year(movs, active_year)
        chunked_update(ws_cli, "A1", clientes_values, chunk_rows=400)
        print(f"  ✓ clientes: {len(clientes_values)} filas")
    except Exception as e:
        print(f"  ✗ clientes: {e}")

    # PROVEEDORES
    try:
        ws_prov = sh.worksheet(WS_PROVEEDORES)
        update_proveedores_stats(ws_prov, movs)
        n_prov = len(ws_prov.col_values(1)) - 1
        print(f"  ✓ proveedores: {n_prov} actualizados")
    except gspread.WorksheetNotFound:
        print(f"  - proveedores: pestaña no existe (omitido)")
    except Exception as e:
        print(f"  ✗ proveedores: {e}")

    # REGISTROS
    registro_targets = [
        (WS_INGRESOS, "ingreso", "REGISTRO INGRESOS (auto)"),
        (WS_GASTOS, "gasto", "REGISTRO GASTOS (auto)"),
    ]
    registro_written = []

    for ws_name, tipo_filter, title in registro_targets:
        try:
            ws = sh.worksheet(ws_name)
            ws.clear()
            registro_values, fmt = build_registro_rows_and_formats_for_year(
                movs, active_year, tipo_filter=tipo_filter, title=title
            )
            chunked_update(ws, "A1", registro_values, chunk_rows=400)
            registro_written.append((ws, fmt, len(registro_values)))
            print(f"  ✓ {ws_name}: {len(registro_values)} filas")
        except Exception as e:
            print(f"  ✗ {ws_name}: {e}")

    # FORMATO
    requests = []

    try:
        mov_sheet_id = ws_mov.id
        n_mov_cols = max(1, len(ws_mov.row_values(1)))
        requests.append(fmt_request(mov_sheet_id, 0, 1, 0, n_mov_cols, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    except Exception:
        pass

    try:
        ws_cli = sh.worksheet(WS_CLIENTES)
        cli_sheet_id = ws_cli.id
        n_cli_cols = max(1, len(ws_cli.row_values(1)))
        requests.append(fmt_request(cli_sheet_id, 0, 1, 0, n_cli_cols, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    except Exception:
        pass

    try:
        ws_prov = sh.worksheet(WS_PROVEEDORES)
        prov_sheet_id = ws_prov.id
        n_prov_cols = max(1, len(ws_prov.row_values(1)))
        requests.append(fmt_request(prov_sheet_id, 0, 1, 0, n_prov_cols, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    except Exception:
        pass

    try:
        ws_hac = sh.worksheet(WS_HACIENDA)
        hac_headers = ws_hac.row_values(4)
        n_hac_cols = max(1, len([x for x in hac_headers if x != ""]))
        requests.append(fmt_request(ws_hac.id, 3, 4, 0, n_hac_cols, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))
    except Exception:
        pass

    for ws, fmt, _nrows in registro_written:
        reg_sheet_id = ws.id
        width = len(REG_COLUMNS)
        requests.append(reset_format_request(reg_sheet_id, rows=4000, cols=width))
        for r in fmt["year_rows"]:
            requests.append(fmt_request(reg_sheet_id, r - 1, r, 0, width, COLOR_YEAR_BG, COLOR_WHITE, bold=True, center=False))
        for r in fmt["q_rows"]:
            requests.append(fmt_request(reg_sheet_id, r - 1, r, 0, width, COLOR_Q_BG, COLOR_WHITE, bold=True, center=False))
        for r in fmt["hdr_rows"]:
            requests.append(fmt_request(reg_sheet_id, r - 1, r, 0, width, COLOR_HDR_BG, COLOR_WHITE, bold=True, center=True))

    if requests:
        sh.batch_update({"requests": requests})
        print(f"  ✓ Formato aplicado")

    # BACKUP
    try:
        export_sheet_to_xlsx_local(sheet_id, backup_path)
        print(f"  ✓ Backup: {backup_path}")
    except Exception as e:
        print(f"  ✗ Backup: {e}")


# =========================
# Main
# =========================
def main():
    print("=" * 60)
    print("FACTURAS BOT PERSONAL - SYNC REPORTING")
    print("=" * 60)
    
    os.makedirs(EXCELS_LOCAL_DIR, exist_ok=True)
    sync_sheet(SHEET_ID_PERSONAL, "PERSONAL", BACKUP_PERSONAL)

    print("\n" + "=" * 60)
    print("✓ SYNC COMPLETADO")
    print("=" * 60)


if __name__ == "__main__":
    main()
