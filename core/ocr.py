# core/ocr.py
"""
OCR con Google Vision y extracción de texto de PDFs.
"""
import os
import re
from typing import Tuple
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from google.cloud import vision

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import LANG_HINTS


def ensure_adc(service_account_path: str):
    """Configura las credenciales de Google Cloud."""
    if service_account_path and os.path.exists(service_account_path):
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", service_account_path)


def ocr_image_bytes(content: bytes) -> str:
    """Ejecuta OCR en bytes de imagen usando Google Vision."""
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=content)
    ctx = vision.ImageContext(language_hints=LANG_HINTS)
    resp = client.document_text_detection(image=image, image_context=ctx)
    if resp.error.message:
        raise RuntimeError(resp.error.message)
    return resp.full_text_annotation.text or ""


def extract_text_any_with_mode(path: str) -> Tuple[str, str]:
    """
    Extrae texto de un archivo (PDF o imagen).
    
    Returns:
        (text, mode) donde mode es:
        - "pdf_text": PDF con texto embebido legible
        - "pdf_ocr": PDF escaneado (se usó OCR)
        - "image_ocr": Imagen (se usó OCR)
        - "none": No se pudo extraer
    """
    ext = os.path.splitext(path)[1].lower()

    # IMÁGENES -> OCR directo
    if ext in [".jpg", ".jpeg", ".png"]:
        try:
            with open(path, "rb") as f:
                return ocr_image_bytes(f.read()), "image_ocr"
        except Exception:
            return "", "none"

    # PDFs
    if ext == ".pdf":
        # 1) Intentar texto embebido con pdfplumber
        try:
            import pdfplumber
            parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text() or ""
                    if not txt.strip():
                        # Fallback a extract_words
                        words = page.extract_words() or []
                        if words:
                            txt = " ".join(w.get("text", "") for w in words)
                    if txt.strip():
                        parts.append(txt)
            joined = "\n".join(parts).strip()
            
            if joined:
                # Verificar que el texto sea "útil" (tiene marcadores de factura)
                compact = re.sub(r"\s+", " ", joined)
                markers = re.search(
                    r"\b(factura|invoice|subtotal|base imponible|iva|vat|total factura|no\.\s*document|n[uú]mero)\b",
                    joined, re.IGNORECASE
                )
                if len(compact) >= 80 and markers:
                    return joined, "pdf_text"
        except Exception:
            pass

        # 2) PDF escaneado -> renderizar con PyMuPDF y OCR
        try:
            import fitz  # pymupdf
            doc = fitz.open(path)
            texts = []
            for i in range(min(len(doc), 5)):  # Máximo 5 páginas
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=200)
                texts.append(ocr_image_bytes(pix.tobytes("png")))
            out = "\n".join(t for t in texts if t.strip()).strip()
            return out, "pdf_ocr"
        except Exception:
            return "", "none"

    return "", "none"
