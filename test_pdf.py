# test_pdf.py - ejecuta esto en la carpeta del proyecto
import pdfplumber

pdf_path = r"C:\Users\lilpa\OneDrive\Escritorio\facturas-drive\FACTURAS\REVIEW\590F2F.pdf"  # ajusta la ruta

with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        print(f"--- Página {i+1} ({len(text)} chars) ---")
        print(text[:500] if text else "(vacío)")