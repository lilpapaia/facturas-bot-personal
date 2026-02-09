# core/file_utils.py
"""
Utilidades de manejo de archivos para PERSONAL.
"""
import os
import re
import time
import shutil
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import PROCESADAS_DIR, DUPLICADOS_DIR, REVIEW_DIR


def wait_file_ready(path: str, timeout_s: int = 60) -> bool:
    """Espera a que un archivo esté listo (no se esté escribiendo)."""
    start = time.time()
    last_size = -1
    stable = 0
    
    while time.time() - start < timeout_s:
        if not os.path.exists(path):
            time.sleep(0.3)
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            time.sleep(0.3)
            continue
        
        if size == last_size and size > 0:
            stable += 1
        else:
            stable = 0
            last_size = size
        
        if stable >= 3:
            try:
                with open(path, "rb") as f:
                    f.read(256)
                return True
            except OSError:
                pass
        time.sleep(0.3)
    
    return False


def move_to(path: str, ok: bool, duplicate: bool = False) -> str:
    """Mueve un archivo a la carpeta correspondiente."""
    if not ok:
        dest_dir = REVIEW_DIR
    else:
        dest_dir = DUPLICADOS_DIR if duplicate else PROCESADAS_DIR

    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(path)
    dest = os.path.join(dest_dir, name)

    if os.path.exists(dest):
        root, ext = os.path.splitext(name)
        dest = os.path.join(dest_dir, f"{root}__dup_{int(time.time())}{ext}")

    shutil.move(path, dest)
    return dest


def infer_tipo_from_path(path: str) -> str:
    """Infiere el tipo (ingreso/gasto) desde la ruta."""
    p = path.replace("\\", "/").lower()
    if "/inbox/ingresos/" in p:
        return "ingreso"
    return "gasto"


def infer_scope_from_path(path: str) -> str:
    """Siempre devuelve 'personal' en este proyecto."""
    return "personal"


def infer_subtipo_from_path(path: str) -> str:
    """Infiere el subtipo (factura/ticket) desde la ruta."""
    p = path.replace("\\", "/").lower()
    
    if "/gastos/tickets/" in p:
        return "ticket"
    if "/gastos/facturas/" in p:
        return "factura"
    
    return "factura"  # Default


def infer_all_from_path(path: str) -> dict:
    """Infiere tipo, scope y subtipo desde la ruta."""
    return {
        "tipo": infer_tipo_from_path(path),
        "scope": "personal",
        "subtipo": infer_subtipo_from_path(path),
    }
