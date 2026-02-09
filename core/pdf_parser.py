# core/pdf_parser.py
"""
Funciones genéricas de parsing: normalización, fechas, importes, clasificación.
"""
import re
import os
import hashlib
from typing import Optional, Tuple
from dateutil import parser as dateparser


# =========================
# NORMALIZACIÓN DE IMPORTES
# =========================
def normalize_amount(s: Optional[str]) -> Optional[float]:
    """Convierte un string de importe a float."""
    if not s:
        return None
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
        return None


# =========================
# FECHAS Y TRIMESTRES
# =========================
def compute_year_quarter(fecha_iso: Optional[str]) -> Tuple[Optional[int], Optional[int], str]:
    """Calcula año, trimestre y string 'YYYY-QN' desde fecha ISO."""
    if not fecha_iso:
        return None, None, ""
    try:
        anio = int(fecha_iso[:4])
        mes = int(fecha_iso[5:7])
        trimestre = (mes - 1) // 3 + 1
        return anio, trimestre, f"{anio}-Q{trimestre}"
    except Exception:
        return None, None, ""


def find_date_generic(text: str) -> Optional[str]:
    """Busca una fecha en el texto (genérico)."""
    for pat in [
        r"\bFecha\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bDate\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bDatum\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
            except Exception:
                pass

    # Fallback: primera fecha razonable
    m = re.search(r"([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})", text)
    if m:
        try:
            return dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
        except Exception:
            return None
    return None


# =========================
# MONEDA
# =========================
def infer_currency(text: str) -> str:
    """Infiere la moneda del texto."""
    t = text.upper()
    if "DKK" in t:
        return "DKK"
    if "USD" in t or "$" in t:
        return "USD"
    if "GBP" in t or "£" in t:
        return "GBP"
    return "EUR"


# =========================
# ÁMBITO (ES / EXTRANJERO)
# =========================
def compute_ambito_from_tax_id(tax_id: Optional[str]) -> str:
    """Devuelve 'ES' o 'EXTRANJERO' según el CIF/NIF/VAT."""
    t = (tax_id or "").strip().upper().replace(" ", "")
    if not t:
        return "ES"
    if t.startswith("ES"):
        return "ES"
    # VAT con prefijo país distinto de ES
    if re.match(r"^[A-Z]{2}", t) and not t.startswith("ES") and len(t) >= 8:
        return "EXTRANJERO"
    # CIF español (letra + 7 dígitos + control)
    if re.match(r"^[A-HJ-NP-SUVW]\d{7}[0-9A-J]$", t):
        return "ES"
    # NIF español (8 dígitos + letra)
    if re.match(r"^\d{8}[A-Z]$", t):
        return "ES"
    # NIE español (X/Y/Z + 7 dígitos + letra)
    if re.match(r"^[XYZ]\d{7}[A-Z]$", t):
        return "ES"
    return "EXTRANJERO"


# =========================
# CLASIFICACIÓN DE DOCUMENTOS
# =========================
SCREENSHOT_MARKERS = [
    "booking.com", "booking", "google play", "google commerce", "google payments",
    "apple.com/bill", "app store"
]

OFFICIAL_MARKERS = [
    "tesoreria general", "tgss", "seguridad social",
    "documento de pago", "domiciliacion de pagos", "periodo liquidacion"
]

def classify_doc(text: str) -> str:
    """Clasifica el tipo de documento."""
    t = text.lower()

    score_receipt = 0
    score_screenshot = 0
    score_official = 0

    if any(m in t for m in SCREENSHOT_MARKERS):
        score_screenshot += 10

    if any(m in t for m in OFFICIAL_MARKERS):
        score_official += 10

    if re.search(r"\b(TTC|TVA|SIRET|MASTERCARD|VISA|CB)\b", text, flags=re.IGNORECASE):
        score_receipt += 6

    euro_lines = sum(1 for l in text.splitlines() if "€" in l)
    if euro_lines >= 4:
        score_receipt += 4

    if re.search(r"\b\d+[.,]\d{2}\b.*\b\d+[.,]\d{2}\b", text):
        score_receipt += 2

    scores = {
        "RECEIPT_THERMAL": score_receipt,
        "SCREENSHOT_APP": score_screenshot,
        "OFFICIAL_PDF": score_official,
        "OTHER": 0
    }
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] < 6:
        return "OTHER"
    return best[0]


# =========================
# TICKET ID ESTABLE (para gastos sin nº factura)
# =========================
def build_stable_ticket_id(date_iso: Optional[str], total: Optional[float], vendor: str, source_file: str) -> str:
    """Genera un ID estable para tickets sin número de factura."""
    base = f"{date_iso or ''}|{total or ''}|{vendor or ''}|{os.path.basename(source_file)}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10].upper()
    cents = int(round((total or 0) * 100))
    d = (date_iso or "0000-00-00").replace("-", "")
    return f"TICKET-{d}-{cents}-{h}"


# =========================
# REGEX DE IMPORTES
# =========================
AMOUNT_RE = re.compile(r'(?<!\d)(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2})?)(?!\d)')
