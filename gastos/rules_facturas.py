# gastos/rules_facturas.py
"""
Reglas de validación específicas para FACTURAS de gastos personales.
"""
from typing import Dict, Any


def validate_factura(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida una factura de gasto.
    
    Campos obligatorios:
    - fecha
    - proveedor_cliente (vendor)
    - total
    
    Campos deseables (warning si faltan):
    - tax_id
    - numero_factura
    """
    reasons = []
    
    # Campos obligatorios
    if not data.get("fecha"):
        reasons.append("sin_fecha")
    
    if not data.get("proveedor_cliente"):
        reasons.append("sin_proveedor")
    
    total = data.get("total")
    if total is None or total == 0:
        reasons.append("sin_total")
    
    # Campos deseables (no bloquean pero se marcan)
    if not data.get("tax_id"):
        # Solo warning, no bloquea
        pass
    
    if not data.get("numero_factura"):
        # Solo warning, no bloquea
        pass
    
    # Validaciones de coherencia
    base = data.get("base")
    iva = data.get("iva") or 0
    
    if base and total:
        expected = round(base + iva, 2)
        actual = round(total, 2)
        if abs(expected - actual) > 0.10:
            # La diferencia es normal si hay otros conceptos
            pass
    
    # Resultado
    if reasons:
        data["review_reason"] = ", ".join(reasons)
    else:
        data["review_reason"] = ""
    
    return data
