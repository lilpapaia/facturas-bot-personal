#!/usr/bin/env python3
# watch_inbox.py
"""
Watcher de carpetas INBOX - versión PERSONAL.

Carpetas monitorizadas (3):
- INBOX/INGRESOS/
- INBOX/GASTOS/FACTURAS/
- INBOX/GASTOS/TICKETS/
"""
import os
import sys
import time
import traceback
from threading import Timer, Lock, Event
from queue import Queue

sys.path.insert(0, os.path.dirname(__file__))

from config.settings import (
    ALL_INBOX_FOLDERS,
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

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAVE_WATCHDOG = True
except ImportError:
    HAVE_WATCHDOG = False


BATCH_WAIT_SECONDS = 3

_file_queue = Queue()
_is_processing = Event()
_stop_requested = Event()


# =========================
# PROCESAMIENTO
# =========================
def process_single_file(path: str) -> dict:
    """Procesa un único archivo."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {"status": "skip", "path": path, "reason": "extension_no_soportada"}

    if not os.path.exists(path):
        return {"status": "skip", "path": path, "reason": "archivo_no_existe"}

    if not wait_file_ready(path, timeout_s=60):
        return {"status": "error", "path": path, "reason": "archivo_no_listo"}

    tipo = infer_tipo_from_path(path)
    subtipo = infer_subtipo_from_path(path)
    
    try:
        if tipo == "ingreso":
            print(f"PROCESANDO INGRESO: {os.path.basename(path)}")
            result = process_ingreso(path, scope="personal")
        else:
            subtipo_info = f", {subtipo.upper()}" if subtipo else ""
            print(f"PROCESANDO GASTO{subtipo_info}: {os.path.basename(path)}")
            result = process_gasto(path, scope="personal", subtipo=subtipo)
        
        status = result.get("status", "error")
        if status == "processed":
            print(f"  ✓ Procesado correctamente")
        elif status == "duplicate":
            print(f"  ⚠ Duplicado")
        else:
            print(f"  ✗ Review: {result.get('reason', 'unknown')}")
        
        return {"status": status, "path": path, "result": result}
            
    except Exception as e:
        print(f"ERROR procesando {path}: {e}")
        traceback.print_exc()
        return {"status": "error", "path": path, "reason": str(e)}


def run_sync():
    """Ejecuta sync_reporting."""
    print("\n" + "=" * 50)
    print("EJECUTANDO SYNC")
    print("=" * 50)
    try:
        from sync_reporting import sync_sheet
        from config.settings import SHEET_ID_PERSONAL, BACKUP_PERSONAL
        
        sync_sheet(SHEET_ID_PERSONAL, "PERSONAL", BACKUP_PERSONAL)
        
        print("=" * 50)
        print("SYNC COMPLETADO")
        print("=" * 50 + "\n")
        return True
    except Exception as e:
        print(f"ERROR en sync: {e}")
        traceback.print_exc()
        return False


def process_batch():
    """Procesa todos los archivos en la cola."""
    if _is_processing.is_set():
        return
    
    _is_processing.set()
    
    try:
        files_to_process = []
        while not _file_queue.empty():
            try:
                path = _file_queue.get_nowait()
                files_to_process.append(path)
            except:
                break
        
        if not files_to_process:
            return
        
        files_to_process = list(dict.fromkeys(files_to_process))
        
        print(f"\n--- Procesando lote de {len(files_to_process)} archivo(s) ---")
        
        results = []
        for path in files_to_process:
            result = process_single_file(path)
            results.append(result)
        
        processed_count = sum(1 for r in results if r["status"] == "processed")
        duplicate_count = sum(1 for r in results if r["status"] == "duplicate")
        error_count = sum(1 for r in results if r["status"] in ("error", "review"))
        
        print(f"\n--- Lote completado: {processed_count} procesados, {duplicate_count} duplicados, {error_count} errores ---")
        
        if processed_count > 0:
            run_sync()
        else:
            print("No hay facturas nuevas, omitiendo sync.\n")
        
        if not _file_queue.empty():
            print("Hay más archivos en cola, procesando siguiente lote...")
            _is_processing.clear()
            process_batch()
    
    finally:
        _is_processing.clear()


# =========================
# SCAN INICIAL
# =========================
def scan_and_queue_existing():
    """Escanea carpetas y añade archivos existentes a la cola."""
    count = 0
    for folder in ALL_INBOX_FOLDERS:
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
            continue
        
        for fname in os.listdir(folder):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(folder, fname)
            if os.path.isfile(path):
                _file_queue.put(path)
                count += 1
    
    return count


# =========================
# WATCHDOG HANDLER
# =========================
if HAVE_WATCHDOG:
    class InboxHandler(FileSystemEventHandler):
        def __init__(self):
            self._batch_timer = None
            self._timer_lock = Lock()
        
        def _schedule_batch(self):
            with self._timer_lock:
                if self._batch_timer is not None:
                    try:
                        self._batch_timer.cancel()
                    except:
                        pass
                
                self._batch_timer = Timer(BATCH_WAIT_SECONDS, self._run_batch_safe)
                self._batch_timer.start()
        
        def _run_batch_safe(self):
            if not _stop_requested.is_set():
                process_batch()
        
        def _handle_file(self, path):
            ext = os.path.splitext(path)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                time.sleep(0.5)
                if os.path.exists(path):
                    _file_queue.put(path)
                    print(f"Encolado: {os.path.basename(path)}")
                    self._schedule_batch()
        
        def on_created(self, event):
            if not event.is_directory:
                self._handle_file(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._handle_file(event.dest_path)


# =========================
# MAIN
# =========================
def main():
    print("=" * 60)
    print("FACTURAS BOT PERSONAL - WATCH INBOX")
    print("=" * 60)
    
    ensure_adc(SERVICE_ACCOUNT_FILE)
    
    folders = [
        ("INGRESOS", INBOX_INGRESOS),
        ("GASTOS/FACTURAS", INBOX_GASTOS_FACTURAS),
        ("GASTOS/TICKETS", INBOX_GASTOS_TICKETS),
    ]
    
    print("\nCarpetas monitorizadas:")
    for name, path in folders:
        os.makedirs(path, exist_ok=True)
        print(f"  {name}: {path}")
    
    print("\n--- SCAN INICIAL ---")
    count = scan_and_queue_existing()
    print(f"Archivos encontrados: {count}")
    print("--- FIN SCAN ---")
    
    if count > 0:
        process_batch()
    
    if not HAVE_WATCHDOG:
        print("\nAVISO: watchdog no instalado. Ejecutando solo scan inicial.")
        print("Instala con: pip install watchdog")
        return
    
    print("\nIniciando monitor de carpetas (Ctrl+C para salir)...")
    print(f"Los archivos se procesan en lotes. Sync después de cada lote.\n")
    
    observer = Observer()
    handler = InboxHandler()
    
    for name, path in folders:
        observer.schedule(handler, path, recursive=False)
    
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo monitor...")
        _stop_requested.set()
        observer.stop()
    
    observer.join()
    print("Monitor detenido.")


if __name__ == "__main__":
    main()
