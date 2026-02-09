# config/settings.py
"""
Configuración central para FACTURAS-BOT-PERSONAL.
Solo Google Sheets, solo ámbito personal.
"""
import os

# =========================
# GOOGLE SHEETS
# =========================
SHEET_ID_PERSONAL = "1putS_YxGiLGiBzaFxCIzrF6p5AsNxQJoX0EYTDsfen0"

# Alias para compatibilidad
SHEET_ID = SHEET_ID_PERSONAL

# Pestañas
WS_MOVIMIENTOS = "movimientos"
WS_GASTOS = "registro_gastos"
WS_INGRESOS = "registro_ingresos"
WS_REGISTRO_GASTOS = "registro_gastos"
WS_REGISTRO_INGRESOS = "registro_ingresos"
WS_CLIENTES = "clientes"
WS_PROVEEDORES = "proveedores"
WS_CONFIG = "config"
WS_HACIENDA = "hacienda"

# Celda con año activo
CFG_YEAR_CELL = "B2"

# =========================
# RUTAS DE ARCHIVOS
# =========================
POSSIBLE_ROOTS = [
    r"C:\Users\lilpa\OneDrive\Escritorio\facturas-drive",  # Portátil
    r"G:\Otros ordenadores\Mi portátil\facturas-drive",    # Torre
]

def _detect_facturas_root() -> str:
    """Detecta automáticamente qué path existe."""
    env_root = os.getenv("FACTURAS_DRIVE_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root
    
    for path in POSSIBLE_ROOTS:
        if os.path.isdir(path):
            return path
    
    return POSSIBLE_ROOTS[0]

FACTURAS_DRIVE_ROOT = _detect_facturas_root()

def _resolve_base_sync() -> str:
    root = (FACTURAS_DRIVE_ROOT or "").replace("/", "\\").rstrip("\\")
    if not root:
        return POSSIBLE_ROOTS[0] + "\\FACTURAS"
    if root.lower().endswith("\\facturas"):
        return root
    return os.path.join(root, "FACTURAS")

BASE_SYNC = _resolve_base_sync()
INBOX_DIR = os.path.join(BASE_SYNC, "INBOX")
PROCESADAS_DIR = os.path.join(BASE_SYNC, "PROCESADAS")
DUPLICADOS_DIR = os.path.join(PROCESADAS_DIR, "DUPLICADOS")
REVIEW_DIR = os.path.join(BASE_SYNC, "REVIEW")

# =========================
# CARPETAS DE INBOX
# =========================
INBOX_INGRESOS = os.path.join(INBOX_DIR, "INGRESOS")
INBOX_GASTOS_FACTURAS = os.path.join(INBOX_DIR, "GASTOS", "FACTURAS")
INBOX_GASTOS_TICKETS = os.path.join(INBOX_DIR, "GASTOS", "TICKETS")

# Lista de todas las carpetas de INBOX
ALL_INBOX_FOLDERS = [
    INBOX_INGRESOS,
    INBOX_GASTOS_FACTURAS,
    INBOX_GASTOS_TICKETS,
]

# =========================
# BACKUP LOCAL
# =========================
EXCELS_LOCAL_DIR = os.path.join(BASE_SYNC, "EXCELS LOCAL")
BACKUP_PERSONAL = os.path.join(EXCELS_LOCAL_DIR, "Contabilidad_Personal.xlsx")

# =========================
# SERVICE ACCOUNT
# =========================
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "service_account.json")

# =========================
# SCOPES GOOGLE
# =========================
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# EXTENSIONES SOPORTADAS
# =========================
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

# =========================
# CONFIGURACIÓN OCR
# =========================
LANG_HINTS = ["es", "ca", "en", "fr", "de", "it", "pt", "nl", "da"]
