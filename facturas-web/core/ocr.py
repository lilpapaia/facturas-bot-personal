# core/ocr.py
"""
OCR con Google Vision y extracción de texto de PDFs.
Versión WEB - usa Streamlit secrets para credenciales.
"""
import io
import re
from typing import Tuple

import streamlit as st
from google.cloud import vision
from google.oauth2.service_account import Credentials

from config.settings import LANG_HINTS, GOOGLE_SCOPES


def get_vision_client():
    """Obtiene cliente de Vision API usando Streamlit secrets."""
    gcp_secrets = st.secrets["gcp_service_account"]
    
    # Arreglar private_key si tiene formato incorrecto
    creds_dict = dict(gcp_secrets)
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        # Reconstruir si tiene espacios en vez de saltos de línea
        match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
        if match:
            content = match.group(1)
            content_clean = re.sub(r'\s+', '', content)
            lines = [content_clean[i:i+64] for i in range(0, len(content_clean), 64)]
            creds_dict["private_key"] = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
    return vision.ImageAnnotatorClient(credentials=creds)


def ocr_image_bytes(content: bytes) -> str:
    """Ejecuta OCR en bytes de imagen usando Google Vision."""
    client = get_vision_client()
    image = vision.Image(content=content)
    ctx = vision.ImageContext(language_hints=LANG_HINTS)
    resp = client.document_text_detection(image=image, image_context=ctx)
    if resp.error.message:
        raise RuntimeError(resp.error.message)
    return resp.full_text_annotation.text or ""


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Extrae texto de bytes de archivo (PDF o imagen).
    
    Args:
        file_bytes: Contenido del archivo en bytes
        filename: Nombre del archivo (para detectar extensión)
    
    Returns:
        (text, mode) donde mode es:
        - "pdf_text": PDF con texto embebido legible
        - "pdf_ocr": PDF escaneado (se usó OCR)
        - "image_ocr": Imagen (se usó OCR)
        - "none": No se pudo extraer
    """
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    # IMÁGENES -> OCR directo
    if ext in ["jpg", "jpeg", "png"]:
        try:
            return ocr_image_bytes(file_bytes), "image_ocr"
        except Exception as e:
            st.error(f"Error en OCR de imagen: {e}")
            return "", "none"

    # PDFs
    if ext == "pdf":
        # 1) Intentar texto embebido con pdfplumber (GRATIS)
        try:
            import pdfplumber
            parts = []
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
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
                # Verificar que el texto sea "útil" (tiene marcadores de factura/recibo)
                compact = re.sub(r"\s+", " ", joined)
                markers = re.search(
                    r"\b(factura|invoice|subtotal|base imponible|iva|vat|total|"
                    r"no\.\s*document|n[uú]mero|importe|cargo|abono|"
                    r"domiciliaci[oó]n|tgss|aut[oó]nomos|cotizaci[oó]n|"
                    r"periodo|liquidaci[oó]n|caixabank|banco|transferencia)\b",
                    joined, re.IGNORECASE
                )
                # Si hay suficiente texto (>50 chars), aceptarlo aunque no tenga marcadores
                if len(compact) >= 50 and (markers or len(compact) >= 200):
                    return joined, "pdf_text"
        except Exception:
            pass

        # 2) PDF escaneado -> renderizar con PyMuPDF y OCR
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texts = []
            for i in range(min(len(doc), 5)):  # Máximo 5 páginas
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=200)
                texts.append(ocr_image_bytes(pix.tobytes("png")))
            doc.close()
            out = "\n".join(t for t in texts if t.strip()).strip()
            return out, "pdf_ocr"
        except Exception as e:
            st.error(f"Error procesando PDF: {e}")
            return "", "none"

    return "", "none"
