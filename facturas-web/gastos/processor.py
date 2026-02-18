# gastos/processor.py
"""
Procesador de gastos - versión WEB.
Recibe bytes del archivo en vez de path.
"""
from datetime import datetime
from typing import Dict, Any

from core.ocr import extract_text_from_bytes
from core.sheets import append_movimiento_with_dedupe
from core.drive import upload_to_drive

from .parser import (
    find_date_gasto,
    find_invoice_number_gasto,
    find_vendor_gasto,
    find_tax_id_gasto,
    find_base_gasto,
    find_iva_gasto,
    find_total_gasto,
)
from .rules import enforce_gastos_rules, determine_ambito, determine_iva_deducible


def process_gasto(
    file_bytes: bytes, 
    filename: str, 
    subtipo: str = "factura"
) -> Dict[str, Any]:
    """
    Procesa una factura o ticket de gasto.
    
    Args:
        file_bytes: Contenido del archivo en bytes
        filename: Nombre del archivo
        subtipo: "factura" o "ticket"
    
    Returns:
        {"status": "processed" | "duplicate" | "review" | "error", ...}
    """
    # 1. Extraer texto
    text, mode = extract_text_from_bytes(file_bytes, filename)
    
    if not text or len(text.strip()) < 20:
        # Subir a REVIEW
        upload_to_drive(file_bytes, filename, "review")
        return {"status": "review", "reason": "sin_texto_extraido", "extraction_mode": mode}
    
    # 2. Parsear campos
    fecha = find_date_gasto(text)
    numero = find_invoice_number_gasto(text)
    vendor = find_vendor_gasto(text)
    tax_id = find_tax_id_gasto(text, vendor)
    base = find_base_gasto(text)
    iva = find_iva_gasto(text, base)
    total = find_total_gasto(text)
    
    # 3. Construir data
    now = datetime.now()
    
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
    ambito = determine_ambito(tax_id, text)
    
    data = {
        "procesado_el": now.strftime("%Y-%m-%d %H:%M:%S"),
        "anio_trimestre": anio_trimestre,
        "fecha": fecha or "",
        "tipo": "gasto",
        "subtipo": subtipo,
        "proveedor_cliente": vendor or "",
        "tax_id": tax_id or "",
        "numero_factura": numero or "",
        "base": base if base else "",
        "iva": iva if iva else "",
        "irpf": "",
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
    data = enforce_gastos_rules(data, subtipo)
    data["iva_deducible"] = determine_iva_deducible(data)
    
    # 5. Si hay errores de validación, subir a REVIEW
    if data.get("review_reason"):
        file_id = upload_to_drive(file_bytes, filename, "review")
        data["drive_file_id"] = file_id or ""
        return {"status": "review", "reason": data["review_reason"], "data": data}
    
    # 6. Insertar en Sheet (con dedupe)
    status, row = append_movimiento_with_dedupe(data)
    
    if status == "duplicate":
        # Subir a DUPLICADOS
        file_id = upload_to_drive(file_bytes, filename, "duplicados")
        data["drive_file_id"] = file_id or ""
        return {"status": "duplicate", "data": data}
    
    if status == "error":
        # Subir a REVIEW
        file_id = upload_to_drive(file_bytes, filename, "review")
        data["drive_file_id"] = file_id or ""
        return {"status": "error", "reason": "error_sheets", "data": data}
    
    # 7. Subir a PROCESADAS
    file_id = upload_to_drive(file_bytes, filename, "procesadas")
    data["drive_file_id"] = file_id or ""
    
    return {"status": "processed", "row": row, "data": data}
