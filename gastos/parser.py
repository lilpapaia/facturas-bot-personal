# gastos/parser.py
"""
Parser para facturas de GASTOS - versión PERSONAL.
Soporta facturas normales y recibos bancarios (autónomos, domiciliaciones).
"""
import re
import calendar
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
    
    # 1) Detectar recibos de autónomos (TGSS)
    if re.search(r"TGSS.*COTIZACION.*AUTONOMOS", text, re.IGNORECASE):
        return "TGSS - Seguridad Social"
    
    if re.search(r"R\.?E\.?\s*AUT[OÓ]NOMOS", text, re.IGNORECASE):
        return "TGSS - Seguridad Social"
    
    def looks_like_company(s: str) -> bool:
        s2 = (s or "").strip()
        if len(s2) < 4:
            return False
        return bool(re.search(
            r"\b(S\.?L\.?U?|S\.?L\.?|S\.?A\.?U?|SA|SL|SAU|LTD|LIMITED|GMBH|BV|B\.?V\.?|LLC|INC|SRL|SAS|PBC)\b",
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
    
    def clean_vendor_name(s: str) -> str:
        """Limpia el nombre del proveedor de basura."""
        if not s:
            return s
        # Quitar todo después de NUM. FACTURA, CIF, NIF, etc.
        s = re.sub(r"\s+(NUM\.?\s*FACTURA|CIF|NIF|VAT|FECHA|DATE)[:\s].*$", "", s, flags=re.IGNORECASE)
        # Quitar números de factura sueltos
        s = re.sub(r"\s+\d{10,}.*$", "", s)
        return s.strip()

    lines = [re.sub(r"\s+", " ", l.strip()) for l in text.splitlines() if l.strip()]

    # 2) Buscar bloque CIF/VAT y mirar hacia arriba
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
                        return clean_vendor_name(cand)
                return clean_vendor_name(candidates[-1])

    # 3) Buscar primera empresa con terminación típica
    for ln in lines:
        if looks_like_company(ln) and not is_noise_line(ln):
            return clean_vendor_name(ln.strip())

    # 4) Detectar bancos
    if re.search(r"\bCaixaBank\b", text, re.IGNORECASE):
        return "CaixaBank"
    if re.search(r"\bBBVA\b", text, re.IGNORECASE):
        return "BBVA"
    if re.search(r"\bSantander\b", text, re.IGNORECASE):
        return "Santander"

    # 5) Fallback: primera línea no vacía
    for ln in lines[:5]:
        if len(ln.strip()) >= 4 and not is_noise_line(ln):
            return clean_vendor_name(ln.strip())

    return None


# =========================
# CIF / TAX ID
# =========================
def find_tax_id_gasto(text: str, vendor: Optional[str] = None) -> Optional[str]:
    """Busca CIF/NIF/VAT del proveedor."""
    if not text:
        return None
    
    # TGSS tiene un identificador especial
    if vendor and "TGSS" in vendor:
        m = re.search(r"ES\d{11}[A-Z]", text)
        if m:
            return m.group(0)
        return "Q2827003A"  # CIF de la TGSS

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
    
    # VAT europeo (EU OSS)
    m = re.search(r"EU\s*OSS\s*VAT\s*([A-Z]{2}\d+)", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    return None


# =========================
# NÚMERO DE FACTURA
# =========================
def find_invoice_number_gasto(text: str) -> Optional[str]:
    """Busca el número de factura en gastos."""
    
    # Recibos de autónomos: usar período de liquidación
    m = re.search(r"PERIODO\s*LIQUIDACION[:\s]*(\d{2}/\d{4})[^\d]*(\d{2}/\d{4})?", text, re.IGNORECASE)
    if m:
        return f"TGSS-{m.group(1).replace('/', '')}"
    
    # Patrones ordenados por especificidad
    patterns = [
        # McDonald's específico
        r"NUM\.?\s*FACTURA[:\s]*(\d{10,}[A-Z0-9]*)",
        # Formatos comunes
        r"N[uú]mero\s+de\s+Factura[:\s]*([A-Z0-9\-\/]+)",
        r"N[uú]mero\s+Factura[:\s]*([A-Z0-9\-\/]+)",
        r"\bFactura\s*N[º°o]?\.?[:\s]*([A-Z0-9\-\/]+)",
        r"\bN[º°o]\s*Factura[:\s]*([A-Z0-9\-\/]+)",
        r"\bInvoice\s*number\s*([A-Z0-9\-\/]+)",
        r"\bInvoice\s*N[º°o]?\.?[:\s]*#?\s*([A-Z0-9\-\/]+)",
        r"\bReceipt\s*#?\s*([A-Z0-9\-\/]+)",
        r"\bRef(?:erencia)?[:\s]*([A-Z0-9\-\/]+)",
    ]
    
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            result = m.group(1).strip().upper()
            # Filtrar resultados inválidos
            if len(result) >= 3 and not result.startswith(('EUR', 'USD', 'GBP', 'VAT')):
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
    
    # 1) Recibos TGSS: usar fecha del cargo (dd.mm.yy al inicio)
    if re.search(r"TGSS|COTIZACION.*AUTONOMOS", text, re.IGNORECASE):
        # Formato CaixaBank: "31.10.25" o "2.01.26"
        m = re.search(r"\b(\d{1,2}\.\d{2}\.\d{2})\b", text)
        if m:
            try:
                parsed = dateparser.parse(m.group(1), dayfirst=True)
                if parsed and 2015 <= parsed.year <= 2030:
                    return parsed.date().isoformat()
            except:
                pass
        # Alternativa: usar período de liquidación como fecha (último día del mes)
        m = re.search(r"PERIODO\s*LIQUIDACION[:\s]*(\d{2})/(\d{4})", text, re.IGNORECASE)
        if m:
            try:
                mes = int(m.group(1))
                anio = int(m.group(2))
                # Último día del mes
                import calendar
                ultimo_dia = calendar.monthrange(anio, mes)[1]
                return f"{anio}-{mes:02d}-{ultimo_dia:02d}"
            except:
                pass
    
    # 2) Formato ISO (YYYY-MM-DD)
    iso_match = re.search(r"\b(20[12]\d[-/][01]?\d[-/][0-3]?\d)\b", text)
    if iso_match:
        try:
            parsed = dateparser.parse(iso_match.group(1))
            if parsed and 2015 <= parsed.year <= 2030:
                return parsed.date().isoformat()
        except:
            pass
    
    # 3) Formato banco genérico: dd.mm.yy
    m = re.search(r"\b(\d{1,2}\.\d{2}\.\d{2})\b", text)
    if m:
        try:
            parsed = dateparser.parse(m.group(1), dayfirst=True)
            if parsed and 2015 <= parsed.year <= 2030:
                return parsed.date().isoformat()
        except:
            pass
    
    # 4) Formatos con etiqueta
    for pat in [
        r"\bFecha\s+Factura\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFecha\s+Emisi[oó]n\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFECHA\s+EXPEDICI[OÓ]N\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFECHA\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFecha\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bDate\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                parsed = dateparser.parse(m.group(1), dayfirst=True)
                if parsed and 2015 <= parsed.year <= 2030:
                    return parsed.date().isoformat()
            except:
                pass

    # 5) Formato inglés: "January 25, 2026" o "Jan 25, 2026"
    eng_months = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    eng_pat = rf"\b({eng_months})\s+(\d{{1,2}}),?\s+(\d{{4}})\b"
    m = re.search(eng_pat, text, flags=re.IGNORECASE)
    if m:
        try:
            date_str = f"{m.group(1)} {m.group(2)}, {m.group(3)}"
            parsed = dateparser.parse(date_str)
            if parsed and 2015 <= parsed.year <= 2030:
                return parsed.date().isoformat()
        except:
            pass
    
    # 6) "Date of issue January 25, 2026" (OpenAI/Anthropic)
    m = re.search(rf"Date\s+of\s+issue\s+({eng_months})\s+(\d{{1,2}}),?\s+(\d{{4}})", text, flags=re.IGNORECASE)
    if m:
        try:
            date_str = f"{m.group(1)} {m.group(2)}, {m.group(3)}"
            parsed = dateparser.parse(date_str)
            if parsed and 2015 <= parsed.year <= 2030:
                return parsed.date().isoformat()
        except:
            pass

    # 7) Fallback: cualquier fecha dd/mm/yyyy o dd.mm.yy
    m = re.search(r"([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})", text)
    if m:
        try:
            parsed = dateparser.parse(m.group(1), dayfirst=True)
            if parsed and 2015 <= parsed.year <= 2030:
                return parsed.date().isoformat()
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
        r"\bTotal\s+excluding\s+tax\b.*?([\-]?\d[\d\.\,]*)",
    ]:
        matches = re.findall(pat, text, flags=re.IGNORECASE)
        if matches:
            return normalize_amount(matches[-1])
    return None


def find_total_gasto(text: str) -> Optional[float]:
    """Busca el total de la factura/recibo."""
    
    # Recibos de autónomos TGSS: buscar patrón específico
    if re.search(r"TGSS|R\.?E\.?\s*AUT[OÓ]NOMOS|COTIZACION.*005", text, re.IGNORECASE):
        # Buscar el importe después de la cuenta bancaria (formato: 03607-00 379,67)
        m = re.search(r"\d{5}-\d{2}\s+(\d{1,3}(?:\.\d{3})*,\d{2})", text)
        if m:
            return normalize_amount(m.group(1))
        # Buscar "Total" seguido de importe
        m = re.search(r"\bTotal\s*\n?\s*(\d{1,3}(?:[.,]\d{2,3})*[.,]\d{2})", text, re.IGNORECASE)
        if m:
            val = normalize_amount(m.group(1))
            if val and val < 1000:  # Los recibos de autónomos son < 1000€
                return val
        # Buscar importe suelto razonable (entre 100 y 500)
        amounts = re.findall(r"(\d{2,3},\d{2})\b", text)
        for amt in amounts:
            val = normalize_amount(amt)
            if val and 100 < val < 500:
                return val
        return None
    
    # Recibos bancarios genéricos
    if re.search(r"Domiciliaci[oó]n|Cargo", text, re.IGNORECASE):
        m = re.search(r"Importe\s*\n?\s*(\d{1,3}(?:[.,]\d{2,3})*[.,]\d{2})", text, re.IGNORECASE)
        if m:
            return normalize_amount(m.group(1))
        m = re.search(r"\bTotal\s*\n?\s*(\d{1,3}(?:[.,]\d{2,3})*[.,]\d{2})", text, re.IGNORECASE)
        if m:
            return normalize_amount(m.group(1))
    
    for pat in [
        r"\bTotal\s+Factura\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bImporte\s+Total\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bTotal\s+a\s+Pagar\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bAmount\s+due\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bGrand\s+Total\b.*?([\-]?\d[\d\.\,\s]*)",
        r"\bTotal\b[:\s]*(EUR\s*)?([\-]?\d[\d\.\,\s]*)",
        r"\bTOTAL\b\s*([\-]?\$?\€?\s*[\-]?\d[\d\.\,\s]*)",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            groups = m.groups()
            for g in reversed(groups):
                if g and re.search(r'\d', g):
                    # Limpiar símbolos de moneda
                    g = re.sub(r'[$€]', '', g)
                    val = normalize_amount(g)
                    if val and val > 0:
                        return val
    return None


def find_iva_gasto(text: str, base: Optional[float] = None) -> Optional[float]:
    """Busca el IVA de la factura."""
    
    # Recibos de autónomos no tienen IVA
    if re.search(r"TGSS.*AUTONOMOS|R\.?E\.?\s*AUT[OÓ]NOMOS", text, re.IGNORECASE):
        return 0.0
    
    lines = text.splitlines()
    candidates = []

    for ln in lines:
        if not re.search(r"\b(?:IVA|TVA|VAT)\b", ln, flags=re.IGNORECASE):
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
