#!/usr/bin/env python3
# daily_run.py
"""
Ejecución diaria/manual - versión PERSONAL.

Carpetas procesadas (3):
- INBOX/INGRESOS/
- INBOX/GASTOS/FACTURAS/
- INBOX/GASTOS/TICKETS/
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))

from config.settings import (
    INBOX_INGRESOS,
    INBOX_GASTOS_FACTURAS,
    INBOX_GASTOS_TICKETS,
    SUPPORTED_EXTENSIONS,
    SERVICE_ACCOUNT_FILE,
)
from core.ocr import ensure_adc
from core.file_utils import (
    wait_file_ready, 
    infer_tipo_from_path, 
    infer_subtipo_from_path,
)
from ingresos.processor import process_ingreso
from gastos.processor import process_gasto


def process_file(path: str) -> dict:
    """Procesa un archivo según su ubicación."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {"status": "skipped", "reason": "extension_no_soportada"}

    if not wait_file_ready(path, timeout_s=60):
        return {"status": "skipped", "reason": "archivo_no_listo"}

    tipo = infer_tipo_from_path(path)
    subtipo = infer_subtipo_from_path(path)
    
    try:
        if tipo == "ingreso":
            return process_ingreso(path, scope="personal")
        else:
            return process_gasto(path, scope="personal", subtipo=subtipo)
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "reason": str(e)}


def scan_folder(folder: str, folder_name: str) -> dict:
    """Procesa todos los archivos de una carpeta."""
    stats = {"processed": 0, "duplicate": 0, "review": 0, "skipped": 0, "error": 0}
    
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
        return stats
    
    files = [f for f in os.listdir(folder) 
             if os.path.isfile(os.path.join(folder, f)) 
             and os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS]
    
    if not files:
        print(f"  {folder_name}: (vacío)")
        return stats
    
    print(f"  {folder_name}: {len(files)} archivo(s)")
    
    for fname in files:
        path = os.path.join(folder, fname)
        print(f"    Procesando: {fname}")
        
        result = process_file(path)
        status = result.get("status", "error")
        
        if status == "processed":
            stats["processed"] += 1
            print(f"      ✓ OK")
        elif status == "duplicate":
            stats["duplicate"] += 1
            print(f"      ⚠ Duplicado")
        elif status == "review":
            stats["review"] += 1
            print(f"      ✗ Review: {result.get('reason', '')}")
        elif status == "skipped":
            stats["skipped"] += 1
            print(f"      - Saltado: {result.get('reason', '')}")
        else:
            stats["error"] += 1
            print(f"      ✗ Error: {result.get('reason', '')}")
    
    return stats


def main():
    print("=" * 60)
    print("FACTURAS BOT PERSONAL - DAILY RUN")
    print("=" * 60)
    
    ensure_adc(SERVICE_ACCOUNT_FILE)
    
    total_stats = {"processed": 0, "duplicate": 0, "review": 0, "skipped": 0, "error": 0}
    
    folders = [
        (INBOX_INGRESOS, "INGRESOS"),
        (INBOX_GASTOS_FACTURAS, "GASTOS/FACTURAS"),
        (INBOX_GASTOS_TICKETS, "GASTOS/TICKETS"),
    ]
    
    print("\nProcesando carpetas:")
    for folder, name in folders:
        stats = scan_folder(folder, name)
        for k, v in stats.items():
            total_stats[k] += v
    
    if total_stats["processed"] > 0:
        print("\n" + "=" * 60)
        print("EJECUTANDO SYNC")
        print("=" * 60)
        try:
            from sync_reporting import sync_sheet
            from config.settings import SHEET_ID_PERSONAL, BACKUP_PERSONAL
            
            sync_sheet(SHEET_ID_PERSONAL, "PERSONAL", BACKUP_PERSONAL)
            print("✓ Sync completado")
        except Exception as e:
            print(f"✗ Error en sync: {e}")
    
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Procesados:  {total_stats['processed']}")
    print(f"  Duplicados:  {total_stats['duplicate']}")
    print(f"  Review:      {total_stats['review']}")
    print(f"  Saltados:    {total_stats['skipped']}")
    print(f"  Errores:     {total_stats['error']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
