# gastos/rules_tickets.py
"""
Reglas de validación específicas para TICKETS de gastos personales.
"""
from typing import Dict, Any


def validate_ticket(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida un ticket de gasto.
    
    Los tickets tienen requisitos más relajados que las facturas:
    - Necesitan fecha y total
    - El proveedor es deseable pero no obligatorio
    """
    reasons = []
    
    # Campos obligatorios para tickets
    if not data.get("fecha"):
        reasons.append("sin_fecha")
    
    total = data.get("total")
    if total is None or total == 0:
        reasons.append("sin_total")
    
    # Resultado
    if reasons:
        data["review_reason"] = ", ".join(reasons)
    else:
        data["review_reason"] = ""
    
    # Los tickets generalmente no tienen IVA deducible
    data["iva_deducible"] = "NO"
    
    return data
