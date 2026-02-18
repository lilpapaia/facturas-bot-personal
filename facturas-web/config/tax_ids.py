# config/tax_ids.py
"""
CIFs/NIFs para facturas PERSONAL de Julio Taeño.
"""

# NIF personal (Julio Taeño)
PERSONAL_TAX_IDS = {
    "05337839E",
}

# CIFs de empresas propias (para excluir como clientes)
EMPRESA_TAX_IDS = {
    "B72704653",   # DIGITAL ADVERTISING SOCIAL SERVICES S.L.
    "B75781906",   # DAZZLE AGENCY SL
}

# Todos los CIFs propios
OWN_TAX_IDS = EMPRESA_TAX_IDS | PERSONAL_TAX_IDS

# Prefijos de facturas propias (para validación de ingresos)
OWN_INVOICE_PREFIXES = ("DAZZ",)

# Elite Management (excepción para ingresos personales)
ELITE_TAX_IDS = {"A61139754"}
ELITE_KEYWORDS = ("elite management", "elite")


def normalize_tax_id(s: str) -> str:
    """Normaliza un CIF/NIF para comparación."""
    if not s:
        return ""
    s = str(s).strip().upper().replace(" ", "").replace("-", "")
    if s.startswith("ES") and len(s) > 2:
        s = s[2:]
    return s


def is_own_tax_id(tax_id: str) -> bool:
    """Comprueba si un CIF/NIF es nuestro."""
    norm = normalize_tax_id(tax_id)
    return norm in {normalize_tax_id(x) for x in OWN_TAX_IDS}


def is_empresa_tax_id(tax_id: str) -> bool:
    """Comprueba si un CIF es de nuestras empresas."""
    norm = normalize_tax_id(tax_id)
    return norm in {normalize_tax_id(x) for x in EMPRESA_TAX_IDS}


def is_personal_tax_id(tax_id: str) -> bool:
    """Comprueba si un NIF es el personal de Julio."""
    norm = normalize_tax_id(tax_id)
    return norm in {normalize_tax_id(x) for x in PERSONAL_TAX_IDS}


def is_elite_tax_id(tax_id: str) -> bool:
    """Comprueba si un CIF es de Elite."""
    norm = normalize_tax_id(tax_id)
    return norm in {normalize_tax_id(x) for x in ELITE_TAX_IDS}


def is_elite(vendor: str, tax_id: str, text: str) -> bool:
    """Comprueba si una factura es de/para Elite Management."""
    v = (vendor or "").lower()
    if any(k in v for k in ELITE_KEYWORDS):
        return True
    if is_elite_tax_id(tax_id):
        return True
    text_upper = (text or "").upper().replace(" ", "").replace("-", "")
    for tid in ELITE_TAX_IDS:
        if normalize_tax_id(tid) in text_upper:
            return True
    return False
