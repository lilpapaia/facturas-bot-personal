# 🧾 Facturas Bot - Panel Web

Panel de control personal para ver tus facturas y resúmenes de IVA/IRPF.

## 🚀 Desplegar en Streamlit Cloud (GRATIS)

### Paso 1: Subir archivos a GitHub

Copia estos archivos a tu repo `facturas-bot-personal`:
- `app.py`
- `requirements.txt`

```bash
git add app.py requirements.txt
git commit -m "Añadir panel web Streamlit"
git push
```

### Paso 2: Conectar con Streamlit Cloud

1. Ve a [share.streamlit.io](https://share.streamlit.io)
2. Haz login con tu cuenta de GitHub
3. Click en **"New app"**
4. Selecciona:
   - Repository: `tu-usuario/facturas-bot-personal`
   - Branch: `main`
   - Main file path: `app.py`
5. Click en **"Deploy"**

### Paso 3: Configurar Secrets

1. En Streamlit Cloud, ve a tu app > **Settings** > **Secrets**
2. Pega este contenido (modificando los valores):

```toml
[auth]
username = "julio"
password = "TuContraseñaSegura123"

[gcp_service_account]
type = "service_account"
project_id = "facturas-bot-ocr-vision-scraper"
private_key_id = "COPIA_DE_TU_JSON"
private_key = "-----BEGIN PRIVATE KEY-----\nCOPIA_DE_TU_JSON\n-----END PRIVATE KEY-----\n"
client_email = "COPIA_DE_TU_JSON"
client_id = "COPIA_DE_TU_JSON"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "COPIA_DE_TU_JSON"
```

**IMPORTANTE:** Copia los valores de tu archivo `service_account.json` (el que usas en el bot).

3. Click en **"Save"**

### Paso 4: ¡Listo!

Tu app estará en: `https://tu-usuario-facturas-bot-personal.streamlit.app`

## 🔒 Seguridad

- ✅ Usuario/contraseña obligatorio
- ✅ HTTPS automático
- ✅ Secrets encriptados (nunca se suben a GitHub)
- ✅ Solo lectura del Google Sheet

## 📱 Funciones

| Pestaña | Descripción |
|---------|-------------|
| 📊 Resumen IVA | Tabla trimestral para modelo 303 |
| 📄 Facturas | Lista de todas las facturas |
| 📤 Subir | Zona para subir PDFs (próximamente) |
