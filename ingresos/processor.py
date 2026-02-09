# ingresos/processor.py
"""
Procesador principal de ingresos para PERSONAL.
"""
import os
from datetime import datetime
from typing import Dict, Any

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.ocr import extract_text_any_with_mode
from core.file_utils import move_to
from core.sheets import append_movimiento_with_dedupe

from .parser import (
    find_date_invoice,
    find_invoice_number_invoice,
    find_counterparty_invoice,
    find_tax_id_near_counterparty,
    find_base_invoice,
    find_iva_invoice,
    find_irpf_invoice,
    find_total_invoice,
)
from .rules import validate_ingreso, determine_ambito_ingreso


def process_ingreso(path: str, scope: str = "personal") -> Dict[str, Any]:
    """
    Procesa una factura de ingreso (emitida por nosotros).
    
    Args:
        path: Ruta al archivo PDF/imagen
        scope: Siempre "personal" en este proyecto
    
    Returns:
        {"status": "processed" | "duplicate" | "review" | "error", ...}
    """
    # 1. Extraer texto
    text, mode = extract_text_any_with_mode(path)
    
    if not text or len(text.strip()) < 20:
        move_to(path, ok=False)
        return {"status": "review", "reason": "sin_texto_extraido"}
    
    # 2. Parsear campos
    fecha = find_date_invoice(text)
    numero = find_invoice_number_invoice(text)
    cliente = find_counterparty_invoice(text)
    tax_id = find_tax_id_near_counterparty(text, cliente, scope)
    base = find_base_invoice(text)
    iva = find_iva_invoice(text, base)
    irpf = find_irpf_invoice(text)
    total = find_total_invoice(text)
    
    # 3. Construir data
    now = datetime.now()
    filename = os.path.basename(path)
    
    # Calcular año/trimestre
    anio_trimestre = ""
    if fecha:
        try:
            y = int(fecha[:4])
            m = int(fecha[5:7])
            q = (m - 1) // 3 + 1
            anio_trimestre = f"{y}-Q{q}"
        except:
            pass
    
    # Determinar ámbito
    ambito = determine_ambito_ingreso(tax_id)
    
    data = {
        "procesado_el": now.strftime("%Y-%m-%d %H:%M:%S"),
        "anio_trimestre": anio_trimestre,
        "fecha": fecha or "",
        "tipo": "ingreso",
        "subtipo": "",
        "proveedor_cliente": cliente or "",
        "tax_id": tax_id or "",
        "numero_factura": numero or "",
        "base": base if base else "",
        "iva": iva if iva else "",
        "irpf": irpf if irpf else "",
        "total": total if total else "",
        "moneda": "EUR",
        "ambito": ambito,
        "categoria": "",
        "archivo_drive": filename,
        "drive_file_id": "",
        "review_reason": "",
        "extraction_mode": mode,
    }
    
    # 4. Validar
    data = validate_ingreso(data)
    
    # 5. Si hay errores de validación, mover a review
    if data.get("review_reason"):
        move_to(path, ok=False)
        return {"status": "review", "reason": data["review_reason"], "data": data}
    
    # 6. Insertar en Sheet (con dedupe)
    status, row = append_movimiento_with_dedupe(data, scope)
    
    if status == "duplicate":
        move_to(path, ok=True, duplicate=True)
        return {"status": "duplicate", "data": data}
    
    if status == "error":
        move_to(path, ok=False)
        return {"status": "error", "reason": "error_sheets", "data": data}
    
    # 7. Mover a procesadas
    move_to(path, ok=True)
    
    return {"status": "processed", "row": row, "data": data}
