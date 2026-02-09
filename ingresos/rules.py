# ingresos/rules.py
"""
Reglas de validación para INGRESOS personales.
"""
import re
from typing import Dict, Any


def validate_ingreso(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida una factura de ingreso (emitida por nosotros).
    
    Campos obligatorios:
    - fecha
    - cliente (proveedor_cliente)
    - numero_factura
    - total
    """
    reasons = []
    
    # Campos obligatorios
    if not data.get("fecha"):
        reasons.append("sin_fecha")
    
    if not data.get("proveedor_cliente"):
        reasons.append("sin_cliente")
    
    if not data.get("numero_factura"):
        reasons.append("sin_numero_factura")
    
    total = data.get("total")
    if total is None or total == 0:
        reasons.append("sin_total")
    
    # Resultado
    if reasons:
        data["review_reason"] = ", ".join(reasons)
    else:
        data["review_reason"] = ""
    
    return data


def determine_ambito_ingreso(tax_id: str) -> str:
    """
    Determina el ámbito geográfico del cliente.
    """
    if not tax_id:
        return "NACIONAL"
    
    tax_id = tax_id.strip().upper()
    
    # CIF español
    if re.match(r"^[AB]\d{8}$", tax_id):
        return "NACIONAL"
    if re.match(r"^\d{8}[A-Z]$", tax_id):
        return "NACIONAL"
    if tax_id.startswith("ES"):
        return "NACIONAL"
    
    # VAT europeo
    eu_prefixes = [
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "FI",
        "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL",
        "PL", "PT", "RO", "SE", "SI", "SK"
    ]
    for prefix in eu_prefixes:
        if tax_id.startswith(prefix):
            return "INTRACOMUNITARIO"
    
    if re.match(r"^[A-Z]{2}", tax_id):
        return "EXTRACOMUNITARIO"
    
    return "NACIONAL"
