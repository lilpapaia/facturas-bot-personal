# gastos/parser.py
"""
Parser para facturas de GASTOS - versión PERSONAL.
"""
import re
from typing import Optional, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.pdf_parser import normalize_amount, AMOUNT_RE
from dateutil import parser as dateparser


# =========================
# PROVEEDOR / VENDOR
# =========================
def find_vendor_gasto(text: str) -> Optional[str]:
    """Busca el nombre del proveedor en una factura de GASTO."""
    
    def looks_like_company(s: str) -> bool:
        s2 = (s or "").strip()
        if len(s2) < 4:
            return False
        return bool(re.search(
            r"\b(S\.?L\.?U?|S\.?L\.?|S\.?A\.?|SA|SL|LTD|LIMITED|GMBH|BV|B\.?V\.?|LLC|INC|SRL|SAS)\b",
            s2, re.IGNORECASE
        ))

    def is_noise_line(s: str) -> bool:
        s2 = (s or "").strip().lower()
        if not s2:
            return True
        noise = ["españa", "spain", "madrid", "barcelona", "address", "dirección", "postal"]
        if any(w in s2 for w in noise):
            return True
        if re.match(r"^\d{4,5}\b", s2):
            return True
        if re.match(r"^(c/|calle|av\.|avda|avenida|plaza)", s2, re.IGNORECASE):
            return True
        return False

    lines = [re.sub(r"\s+", " ", l.strip()) for l in text.splitlines() if l.strip()]

    # 1) Buscar bloque CIF/VAT y mirar hacia arriba
    for i, ln in enumerate(lines):
        if re.search(r"\b(CIF|CIF\/NIF|VAT(?:\s*ID)?)\b\s*[:]", ln, re.IGNORECASE):
            candidates = []
            for j in range(max(0, i - 6), i):
                cand = lines[j].strip()
                if len(cand) < 4 or is_noise_line(cand):
                    continue
                candidates.append(cand)

            if candidates:
                for cand in reversed(candidates):
                    if looks_like_company(cand):
                        return cand
                return candidates[-1]

    # 2) Buscar primera empresa con terminación típica
    for ln in lines:
        if looks_like_company(ln) and not is_noise_line(ln):
            return ln.strip()

    # 3) Fallback: primera línea no vacía
    for ln in lines[:5]:
        if len(ln.strip()) >= 4 and not is_noise_line(ln):
            return ln.strip()

    return None


# =========================
# CIF / TAX ID
# =========================
def find_tax_id_gasto(text: str, vendor: Optional[str] = None) -> Optional[str]:
    """Busca CIF/NIF/VAT del proveedor."""
    if not text:
        return None

    lines = [re.sub(r"\s+", " ", l.strip()) for l in text.splitlines() if l.strip()]
    if not lines:
        return None

    start_idx = 0
    if vendor:
        vl = vendor.strip().lower()
        for i, ln in enumerate(lines):
            if vl and vl in ln.lower():
                start_idx = i
                break

    window = lines[start_idx : start_idx + 15]
    block = "\n".join(window)

    patterns = [
        r"\bCIF(?:\/NIF)?[:\s]*([A-Z0-9\-]{6,})",
        r"\bNIF[:\s]*([A-Z0-9\-]{6,})",
        r"\bVAT(?:\s*ID)?[:\s]*([A-Z]{1,2}[A-Z0-9]{6,})",
        r"\bTax\s*ID[:\s]*([A-Z0-9\-]{6,})",
    ]
    for pat in patterns:
        m = re.search(pat, block, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().upper()

    # CIF español suelto
    m = re.search(r"\b([AB]\d{8})\b", block)
    if m:
        return m.group(1).upper()

    return None


# =========================
# NÚMERO DE FACTURA
# =========================
def find_invoice_number_gasto(text: str) -> Optional[str]:
    """Busca el número de factura en gastos."""
    for pat in [
        r"N[uú]mero\s+de\s+Factura[:\s]*([A-Z0-9\-\/]+)",
        r"N[uú]mero\s+Factura[:\s]*([A-Z0-9\-\/]+)",
        r"\bFactura\s*N[º°o]?\.?[:\s]*([A-Z0-9\-\/]+)",
        r"\bN[º°o]\s*Factura[:\s]*([A-Z0-9\-\/]+)",
        r"\bReceipt\s*#?\s*([A-Z0-9\-\/]+)",
        r"\bInvoice\s*N[º°o]?\.?[:\s]*#?\s*([A-Z0-9\-\/]+)",
        r"\bRef(?:erencia)?[:\s]*([A-Z0-9\-\/]+)",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            result = m.group(1).strip().upper()
            if len(result) >= 3 and not result.startswith(('EUR', 'USD', 'GBP')):
                return result
    return None


def norm_invoice_id(s: Optional[str]) -> Optional[str]:
    """Normaliza un número de factura."""
    if not s:
        return None
    s = s.strip().upper().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^A-Z0-9\-\/]", "", s)
    return s or None


# =========================
# FECHA
# =========================
def find_date_gasto(text: str) -> Optional[str]:
    """Busca la fecha de factura."""
    for pat in [
        r"\bFecha\s+Factura\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFecha\s+Emisi[oó]n\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFECHA\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFecha\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bDate\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
            except:
                pass

    m = re.search(r"([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})", text)
    if m:
        try:
            return dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
        except:
            return None
    return None


# =========================
# IMPORTES
# =========================
def find_base_gasto(text: str) -> Optional[float]:
    """Busca la base imponible."""
    for pat in [
        r"\bBase\s+Imponible\b.*?([\-]?\d[\d\.\,]*)",
        r"\bSubtotal\b.*?([\-]?\d[\d\.\,]*)",
        r"\bImporte\s+Neto\b.*?([\-]?\d[\d\.\,]*)",
    ]:
        matches = re.findall(pat, text, flags=re.IGNORECASE)
        if matches:
            return normalize_amount(matches[-1])
    return None


def find_total_gasto(text: str) -> Optional[float]:
    """Busca el total de la factura."""
    for pat in [
        r"\bTotal\s+Factura\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bImporte\s+Total\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bTotal\s+a\s+Pagar\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bGrand\s+Total\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bTotal\b[:\s]*(EUR\s*)?([\-]?\d[\d\.\,\s]*)",
        r"\bTOTAL\b\s*([\-]?\d[\d\.\,\s]*)",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            groups = m.groups()
            for g in reversed(groups):
                if g and re.search(r'\d', g):
                    val = normalize_amount(g)
                    if val and val > 0:
                        return val
    return None


def find_iva_gasto(text: str, base: Optional[float] = None) -> Optional[float]:
    """Busca el IVA de la factura."""
    lines = text.splitlines()
    candidates = []

    for ln in lines:
        if not re.search(r"\b(?:IVA|TVA)\b", ln, flags=re.IGNORECASE):
            continue
        if re.search(r"inclu", ln.lower()):
            continue
        if re.search(r"n[uú]mero|number", ln.lower()):
            continue

        amounts = re.findall(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})", ln)
        for amt_str in amounts:
            cand = normalize_amount(amt_str)
            if cand and cand > 0 and cand < 100000:
                candidates.append(cand)

    if not candidates:
        return None

    if base is not None and base > 0:
        lim = base * 0.60
        filtered = [c for c in candidates if c <= lim]
        if filtered:
            candidates = filtered

    if candidates:
        return round(candidates[0], 2)
    
    return None
