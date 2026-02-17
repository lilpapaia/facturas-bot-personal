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
FOLDER_PROCESADAS = "1UkSSx87nmyaqTnKvQ6y7D9wZSh4PnV0A"
FOLDER_DUPLICADOS = "19MjOtuCtPpmJisnOf8yP_eN9wP-llBGr"
FOLDER_REVIEW = "15W_-ChsyTvd7Rz7cKZG46glspryQ7Uu7"

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
