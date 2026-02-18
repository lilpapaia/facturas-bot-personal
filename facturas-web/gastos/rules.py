# gastos/rules.py
"""
Reglas de validación para gastos PERSONAL.
"""
import re
from typing import Dict, Any

from .rules_facturas import validate_factura
from .rules_tickets import validate_ticket


def enforce_gastos_rules(data: Dict[str, Any], subtipo: str = "factura") -> Dict[str, Any]:
    """
    Aplica reglas de validación según el subtipo.
    
    Args:
        data: Diccionario con los datos extraídos
        subtipo: "factura" o "ticket"
    
    Returns:
        data actualizado con review_reason si hay problemas
    """
    if subtipo == "ticket":
        return validate_ticket(data)
    else:
        return validate_factura(data)


def determine_ambito(tax_id: str, text: str = "") -> str:
    """
    Determina el ámbito geográfico según el CIF/NIF.
    
    Returns:
        "NACIONAL" | "INTRACOMUNITARIO" | "EXTRACOMUNITARIO"
    """
    if not tax_id:
        return "NACIONAL"
    
    tax_id = tax_id.strip().upper()
    
    # CIF español (A/B + 8 dígitos) o NIF (8 dígitos + letra)
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
    
    # Si tiene formato VAT pero no es ES ni EU
    if re.match(r"^[A-Z]{2}", tax_id):
        return "EXTRACOMUNITARIO"
    
    return "NACIONAL"


def determine_iva_deducible(data: Dict[str, Any]) -> str:
    """
    Determina si el IVA es deducible para gastos personales.
    
    Para autónomos (persona física), el IVA es deducible si:
    - El gasto está relacionado con la actividad profesional
    - Tiene factura completa con CIF del proveedor
    """
    subtipo = (data.get("subtipo") or "").lower()
    iva = data.get("iva")
    tax_id = data.get("tax_id") or data.get("proveedor_tax_id")
    
    # Si no hay IVA, no hay nada que deducir
    if not iva or iva == 0:
        return "N/A"
    
    # Tickets generalmente no son deducibles (no tienen CIF del receptor)
    if subtipo == "ticket":
        return "NO"
    
    # Facturas con CIF del proveedor son potencialmente deducibles
    if tax_id:
        return "SI"
    
    return "NO"
