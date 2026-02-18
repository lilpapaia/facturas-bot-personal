# config/settings.py
"""
Configuración para FACTURAS-BOT-WEB.
Solo constantes necesarias para la versión web.
"""

# =========================
# GOOGLE SHEETS
# =========================
SHEET_ID = "1putS_YxGiLGiBzaFxCIzrF6p5AsNxQJoX0EYTDsfen0"

# Pestañas
WS_MOVIMIENTOS = "movimientos"

# =========================
# GOOGLE DRIVE - CARPETAS
# =========================
FOLDER_PROCESADAS = "1doiwiLU4RsSnWt_oCQgtxzleKeJwF7GW"
FOLDER_DUPLICADOS = "1XbkuCYPmSoIFAMnJeEMYuvjlXwGiEJ6p"
FOLDER_REVIEW = "1UkdmXDTew35o2gEubPQ4Uv1TL0gAphoQ"
FOLDER_EMITIDAS = "1AlVygh_Zuo8lKZiB7Tf6LWMSjFBHXLAy"

# =========================
# SCOPES GOOGLE
# =========================
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/cloud-vision",
]

# =========================
# EXTENSIONES SOPORTADAS
# =========================
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

# =========================
# CONFIGURACIÓN OCR
# =========================
LANG_HINTS = ["es", "ca", "en", "fr", "de", "it", "pt", "nl", "da"]
