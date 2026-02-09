# Facturas Bot Personal

Bot de procesamiento automático de facturas para **contabilidad personal** de autónomo.

## Características

- **Google Sheets** como destino de datos
- Procesamiento de **ingresos** (facturas emitidas) y **gastos** (facturas/tickets recibidos)
- OCR con Google Vision para PDFs escaneados e imágenes
- Detección automática de duplicados
- Extracción de datos mediante regex
- Sync automático con backup local en Excel

## Estructura de Carpetas

```
facturas-drive/
└── FACTURAS/
    ├── INBOX/
    │   ├── INGRESOS/              ← Facturas emitidas (a clientes)
    │   └── GASTOS/
    │       ├── FACTURAS/          ← Facturas recibidas (de proveedores)
    │       └── TICKETS/           ← Tickets de compra
    ├── PROCESADAS/
    │   └── DUPLICADOS/
    ├── REVIEW/
    └── EXCELS LOCAL/
        └── Contabilidad_Personal.xlsx
```

## Instalación

1. **Clonar el repositorio** (o copiar los archivos)

2. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar credenciales de Google**:
   - Crear proyecto en Google Cloud Console
   - Habilitar APIs: Sheets, Drive, Vision
   - Crear Service Account y descargar JSON
   - Renombrar a `service_account.json` y poner en la raíz del proyecto
   - Compartir el Google Sheet con el email del Service Account

4. **Ajustar configuración** en `config/settings.py`:
   - `SHEET_ID_PERSONAL`: ID del Google Sheet
   - `POSSIBLE_ROOTS`: Rutas donde está tu carpeta facturas-drive

## Uso

### Monitor continuo (recomendado)
```bash
python watch_inbox.py
```
Monitoriza las carpetas INBOX y procesa archivos nuevos automáticamente.

### Ejecución manual
```bash
python daily_run.py
```
Procesa todos los archivos pendientes en INBOX.

### Solo sincronización
```bash
python sync_reporting.py
```
Actualiza registro_ingresos, registro_gastos, clientes, proveedores y genera backup Excel.

## Google Sheet

El Sheet debe tener estas pestañas:

| Pestaña | Descripción |
|---------|-------------|
| `movimientos` | Datos raw de todas las facturas |
| `registro_ingresos` | Vista visual de ingresos por trimestre |
| `registro_gastos` | Vista visual de gastos por trimestre |
| `clientes` | Resumen de clientes (auto) |
| `proveedores` | Catálogo de proveedores con categorías |
| `config` | Año activo en celda B2 |
| `hacienda` | Resúmenes para declaraciones |

## Flujo de Procesamiento

1. **Archivo llega a INBOX** → detectado por watchdog
2. **OCR/Extracción de texto** → pdfplumber o Google Vision
3. **Parsing** → extrae fecha, proveedor, CIF, importes, etc.
4. **Validación** → verifica campos obligatorios
5. **Dedupe** → comprueba si ya existe
6. **Inserción** → añade a pestaña `movimientos`
7. **Move** → mueve archivo a PROCESADAS (o REVIEW si hay errores)
8. **Sync** → actualiza pestañas de registro y estadísticas

## Archivos Principales

| Archivo | Función |
|---------|---------|
| `watch_inbox.py` | Monitor de carpetas con watchdog |
| `daily_run.py` | Procesamiento batch de archivos pendientes |
| `sync_reporting.py` | Sincronización de registros y backup |
| `gastos/processor.py` | Lógica de procesamiento de gastos |
| `ingresos/processor.py` | Lógica de procesamiento de ingresos |
| `core/sheets.py` | Operaciones con Google Sheets |
| `core/ocr.py` | Extracción de texto (OCR) |

## Troubleshooting

**Error "sin_texto_extraido"**:
- El PDF puede estar protegido o ser solo imagen
- Google Vision necesita acceso a internet
- Verificar que las credenciales son válidas

**Error "duplicate"**:
- El número de factura ya existe en el Sheet
- Normal si se reprocesa el mismo archivo

**Error de permisos en Google Sheet**:
- Compartir el Sheet con el email del Service Account (está en el JSON)
- Dar permisos de "Editor"

## Notas

- Este proyecto es **solo para contabilidad personal** (autónomo persona física)
- Para contabilidad de empresa, ver el proyecto `facturas-bot-empresa`
- Los tickets generalmente no son deducibles en IVA (no tienen CIF del receptor)
