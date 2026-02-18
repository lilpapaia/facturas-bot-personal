# ingresos/parser.py
"""
Parser específico para facturas de INGRESOS.
Funciones de extracción de cliente, CIF, número de factura, etc.
"""
import re
from typing import Optional, List

from config.tax_ids import OWN_TAX_IDS
from core.pdf_parser import normalize_amount, AMOUNT_RE
from dateutil import parser as dateparser


# =========================
# CLIENTE / CONTRAPARTE
# =========================
def find_counterparty_invoice(text: str) -> Optional[str]:
    """
    Busca el nombre del cliente en una factura de INGRESOS.
    El cliente es A QUIEN SE FACTURA (no el emisor).
    
    En facturas personales de Julio Taeño, el cliente suele ser DAZZLE AGENCY.
    """
    
    def looks_like_company(s: str) -> bool:
        s2 = (s or "").strip()
        if len(s2) < 4:
            return False
        return bool(re.search(
            r"\b(S\.?L\.?U?|S\.?L\.?|S\.?A\.?|SA|SL|LTD|LIMITED|GMBH|BV|B\.?V\.?|LLC|INC|SRL|SAS)\b",
            s2, re.IGNORECASE
        ))

    def is_emisor(s: str) -> bool:
        """
        Determina si es el EMISOR (no el cliente).
        El emisor es Julio Taeño (persona física que emite facturas personales).
        """
        s_upper = (s or "").upper()
        emisor_names = ["JULIO TAEÑO", "JULIO TAENO"]
        return any(name in s_upper for name in emisor_names)
    
    def clean_company_name(s: str) -> str:
        s = s.strip()
        s = re.sub(r"\bCliente\b", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\bSPAIN\b", "", s, flags=re.IGNORECASE).strip()
        return s

    lines = [re.sub(r"\s+", " ", l.strip()) for l in text.splitlines() if l.strip()]
    
    # 1) Buscar empresa seguida de CIF (formato típico de cliente)
    #    DAZZLE AGENCY S.L.
    #    B75781906
    for i, ln in enumerate(lines):
        if looks_like_company(ln) and not is_emisor(ln):
            # Verificar si la siguiente línea tiene un CIF
            if i + 1 < len(lines):
                next_ln = lines[i + 1]
                if re.search(r"\b[AB]\d{8}\b", next_ln):
                    return clean_company_name(ln)
            # O si la misma línea tiene empresa + CIF
            if re.search(r"\b[AB]\d{8}\b", ln):
                # Extraer solo el nombre
                name = re.sub(r"\b[AB]\d{8}\b", "", ln).strip()
                if looks_like_company(name) and not is_emisor(name):
                    return clean_company_name(name)
    
    # 2) Buscar después de palabra "Cliente"
    for i, ln in enumerate(lines):
        if re.search(r"\bCliente\b", ln, re.IGNORECASE):
            for j in range(i + 1, min(i + 4, len(lines))):
                cand = lines[j].strip()
                
                # Extraer empresa después de número (dirección mezclada)
                m = re.search(r"\d+\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s\.,&-]*(?:S\.?L\.?U?|S\.?A\.?|SL|SA)\.?)\s*$", cand, re.IGNORECASE)
                if m:
                    name = m.group(1).strip()
                    if not is_emisor(name):
                        return clean_company_name(name)
                
                # Si la línea es empresa pura
                if looks_like_company(cand) and not is_emisor(cand):
                    if not re.match(r"^(C/|CALLE|AVDA|AVENIDA|PLAZA|PASEO|PINTO|MADRID|\d{5})", cand, re.IGNORECASE):
                        return clean_company_name(cand)

    # 3) Caso Elite: "Name: ..."
    m = re.search(r"^\s*Name:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if m:
        return m.group(1).strip()

    # 4) Última opción: buscar cualquier empresa que no sea el emisor
    for ln in lines:
        if looks_like_company(ln) and not is_emisor(ln):
            if not re.match(r"^(C/|CALLE|AVDA|AVENIDA|PLAZA|PASEO|PINTO|MADRID|\d{5})", ln, re.IGNORECASE):
                return clean_company_name(ln)

    return None


# =========================
# CIF / TAX ID
# =========================
def find_all_tax_ids(text: str) -> List[str]:
    """
    Extrae TODOS los CIFs/NIFs del texto EN ORDEN DE APARICIÓN.
    
    Returns:
        Lista de CIFs encontrados en orden de aparición (sin duplicados)
    """
    if not text:
        return []
    
    # Buscar todos los patrones con su posición
    findings = []
    
    # CIFs españoles (A o B + 8 dígitos)
    for m in re.finditer(r"\b([AB]\d{8})\b", text):
        findings.append((m.start(), m.group(1).upper()))
    
    # NIFs (8 dígitos + letra) - con o sin prefijo ES
    for m in re.finditer(r"\b(?:ES)?(\d{8}[A-Z])\b", text):
        findings.append((m.start(), m.group(1).upper()))
    
    # VAT con CIF/NIF español
    for m in re.finditer(r"\bVAT\s+([AB]\d{8})\b", text, re.IGNORECASE):
        findings.append((m.start(), m.group(1).upper()))
    
    # Ordenar por posición
    findings.sort(key=lambda x: x[0])
    
    # Deduplicar manteniendo orden
    seen = set()
    result = []
    for pos, tid in findings:
        if tid not in seen:
            seen.add(tid)
            result.append(tid)
    
    return result


def find_tax_id_near_counterparty(text: str, counterparty: Optional[str], scope: str = "personal") -> Optional[str]:
    """
    Busca CIF/NIF/VAT del cliente (no del emisor).
    
    Args:
        scope: "empresa" excluye todos los OWN_TAX_IDS
               "personal" solo excluye el DNI personal (05337839E)
    """
    if not text:
        return None

    lines = [re.sub(r"\s+", " ", l.strip()) for l in text.splitlines() if l.strip()]
    if not lines:
        return None

    # Definir qué CIFs excluir según el scope
    if scope.lower() == "personal":
        exclude_cifs = {"05337839E"}
    else:
        exclude_cifs = OWN_TAX_IDS

    # 1) Si hay bloque "Cliente", buscar CIF en las líneas siguientes
    for i, ln in enumerate(lines):
        if re.search(r"\bCliente\b", ln, re.IGNORECASE):
            for j in range(i + 1, min(i + 7, len(lines))):
                cif_match = re.search(r"\b([AB]\d{8})\b", lines[j])
                if cif_match:
                    cif = cif_match.group(1)
                    if cif not in exclude_cifs:
                        return cif.upper()

    # 2) Si tenemos el nombre del cliente, buscar CIF cerca
    if counterparty:
        cp_lower = counterparty.strip().lower()
        for i, ln in enumerate(lines):
            if cp_lower in ln.lower():
                for j in range(i, min(i + 4, len(lines))):
                    cif_match = re.search(r"\b([AB]\d{8})\b", lines[j])
                    if cif_match:
                        cif = cif_match.group(1)
                        if cif not in exclude_cifs:
                            return cif.upper()

    # 3) Buscar todos los CIFs y devolver el que NO esté excluido
    all_cifs = re.findall(r"\b([AB]\d{8})\b", text)
    for cif in all_cifs:
        if cif not in exclude_cifs:
            return cif.upper()

    # 4) VAT extranjero
    vat_match = re.search(r"\bVAT(?:\s*ID)?[:\s]*([A-Z]{2}[A-Z0-9]{6,})", text, re.IGNORECASE)
    if vat_match:
        vat = vat_match.group(1).upper()
        if not vat.startswith("ES") or vat[2:] not in exclude_cifs:
            return vat
    
    # 5) VAT sin etiqueta (Elite)
    m = re.search(r"\bVAT\s+([A-Z]\d{8})", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    return None


# =========================
# NÚMERO DE FACTURA
# =========================
def find_invoice_number_invoice(text: str) -> Optional[str]:
    """
    Busca el número de factura en el texto.
    Prioriza patrones específicos sobre genéricos.
    """
    # 0) Patrón Elite: "No. Document XXXXXX" (sin dos puntos)
    m = re.search(r"No\.\s*Document\s+(\d{6}[A-Z]{2,3})\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    
    # 1) Patrón específico: "Número: XXXX" o "Número # XXXX"
    m = re.search(r"N[uú]mero\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9_\-]+)", text, flags=re.IGNORECASE)
    if m:
        result = m.group(1).strip()
        # Limpiar "SPAIN" u otros sufijos
        result = re.sub(r"\s+SPAIN.*$", "", result, flags=re.IGNORECASE)
        if len(result) >= 3:
            return result
    
    # 2) Patrón DAZZ_xxxx_xxx o DAZZ-xxxx-xxx (formato personal)
    m = re.search(r"\bDAZZ[_\-]\d{4}[_\-]\d{3}\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(0).upper()
    
    # 3) Patrón DAZZ-yyyynnn (otro formato)
    m = re.search(r"\bDAZZ[_\-]\d{7}\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(0).upper()
    
    # 4) Patrón DAZ-yyyynnnn o DZ-yyyynnnn (formato empresa)
    m = re.search(r"\b(?:DAZ|DZ)[_\-]?\d+\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(0).upper().replace("–", "-")
    
    # 5) Patrones genéricos con etiqueta
    for pat in [
        r"\bFactura\s*(?:N[oº°]?\.?|#)?[:\s]*([A-Z0-9][A-Z0-9_\-\/]+)",
        r"\bInvoice\s*(?:No\.?|#)?[:\s]*([A-Z0-9][A-Z0-9_\-\/]+)",
        r"No\.\s*Documento?[:\s]*([A-Z0-9][A-Z0-9_\-\/]+)",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            result = m.group(1).strip()
            if len(result) >= 3:
                return result
    
    return None


def norm_invoice_id(s: Optional[str]) -> Optional[str]:
    """Normaliza un número de factura para comparación y almacenamiento."""
    if not s:
        return None
    s = str(s).strip().upper()
    # Normalizar guiones especiales
    s = s.replace("–", "-").replace("—", "-")
    # Quitar espacios
    s = re.sub(r"\s+", "", s)
    # Mantener solo: letras, números, guiones, guiones bajos, barras
    s = re.sub(r"[^A-Z0-9_\-\/]", "", s)
    return s if s else None


# =========================
# FECHA
# =========================
def find_date_invoice(text: str) -> Optional[str]:
    """Busca la fecha de factura."""
    for pat in [
        r"\bFecha\s*Valor\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bInvoice\s*Date[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bFecha\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
        r"\bDate\b[:\s]*([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
            except Exception:
                pass

    m = re.search(r"([0-3]?\d[\.\/\-][01]?\d[\.\/\-]\d{2,4})", text)
    if m:
        try:
            return dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
        except Exception:
            return None
    return None


# =========================
# IMPORTES
# =========================
def find_base_invoice(text: str) -> Optional[float]:
    """Busca la base imponible."""
    matches = re.findall(r"\bSubtotal\b\s*([\-]?\d[\d\.\,]*)", text, flags=re.IGNORECASE)
    if matches:
        return normalize_amount(matches[-1])
    matches = re.findall(r"\bSub-?Total\b.*?([\-]?\d[\d\.\,]*)", text, flags=re.IGNORECASE)
    if matches:
        return normalize_amount(matches[-1])
    matches = re.findall(r"\bBase\s+Imponible\b.*?([\-]?\d[\d\.\,]*)", text, flags=re.IGNORECASE)
    if matches:
        return normalize_amount(matches[-1])
    return None


def find_total_invoice(text: str) -> Optional[float]:
    """Busca el total de la factura."""
    for pat in [
        r"\bTOTAL\s+FACTURA\b\s*([\-]?\d[\d\.\,]*)",
        r"\bTOTAL\s+IN\s+EUROS\b\s*([\-]?\d[\d\.\,]*)",
        r"\bImporte\s+Total\b.*?([\-]?\d[\d\.\,]*)",
        r"\bTOTAL\b\s*([\-]?\d[\d\.\,]*)",
    ]:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return normalize_amount(m.group(1))
    return None


def find_iva_invoice(text: str, base: Optional[float] = None) -> Optional[float]:
    """Busca el IVA de la factura."""
    lines = text.splitlines()
    candidates: List[float] = []

    for ln in lines:
        if not re.search(r"\b(?:IVA|VAT|TVA)\b", ln, flags=re.IGNORECASE):
            continue
        if re.search(r"inclu", ln, flags=re.IGNORECASE):
            continue

        nums = [m.group(1) for m in AMOUNT_RE.finditer(ln)]
        if not nums:
            continue

        cand = normalize_amount(nums[-1])
        if cand is None or cand < 0:
            continue
        candidates.append(cand)

    if not candidates:
        return None

    if base is not None and base > 0:
        lim = base * 0.60
        filtered = [c for c in candidates if c <= lim]
        if filtered:
            candidates = filtered

    # Dedupe
    seen = set()
    uniq = []
    for c in candidates:
        k = f"{c:.2f}"
        if k not in seen:
            seen.add(k)
            uniq.append(c)

    return round(sum(uniq), 2)


def find_irpf_invoice(text: str) -> float:
    """Busca la retención IRPF."""
    if not text:
        return 0.0
    candidates: List[float] = []
    for ln in text.splitlines():
        if not re.search(r"\b(IRPF|RETENCI[ÓO]N|WITHHOLD)\b", ln, flags=re.IGNORECASE):
            continue
        nums = [m.group(1) for m in AMOUNT_RE.finditer(ln)]
        if not nums:
            continue
        v = normalize_amount(nums[-1])
        if v is None:
            continue
        if v < 0:
            v = abs(v)
        candidates.append(v)

    if not candidates:
        return 0.0

    seen = set()
    uniq = []
    for v in candidates:
        k = f"{v:.2f}"
        if k not in seen:
            seen.add(k)
            uniq.append(v)

    return round(max(uniq), 2)
