# core/drive.py
"""
Operaciones con Google Drive.
Versión WEB - usa Streamlit secrets para credenciales.
"""
import io
import re
from typing import Optional

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config.settings import (
    FOLDER_PROCESADAS, 
    FOLDER_DUPLICADOS, 
    FOLDER_REVIEW,
    GOOGLE_SCOPES,
)


def _fix_private_key(pk: str) -> str:
    """Arregla el formato de la private_key."""
    match = re.search(r'-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----', pk, re.DOTALL)
    if not match:
        return pk
    content = match.group(1)
    content_clean = re.sub(r'\s+', '', content)
    lines = [content_clean[i:i+64] for i in range(0, len(content_clean), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


def get_drive_service():
    """Obtiene servicio de Drive API usando Streamlit secrets."""
    gcp_secrets = st.secrets["gcp_service_account"]
    
    creds_dict = {
        "type": gcp_secrets["type"],
        "project_id": gcp_secrets["project_id"],
        "private_key_id": gcp_secrets["private_key_id"],
        "private_key": _fix_private_key(gcp_secrets["private_key"]),
        "client_email": gcp_secrets["client_email"],
        "client_id": gcp_secrets["client_id"],
        "auth_uri": gcp_secrets["auth_uri"],
        "token_uri": gcp_secrets["token_uri"],
        "auth_provider_x509_cert_url": gcp_secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": gcp_secrets["client_x509_cert_url"],
    }
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
    return build("drive", "v3", credentials=creds)


def upload_to_drive(
    file_bytes: bytes, 
    filename: str, 
    folder_type: str = "procesadas"
) -> Optional[str]:
    """
    Sube un archivo a Google Drive.
    
    Args:
        file_bytes: Contenido del archivo en bytes
        filename: Nombre del archivo
        folder_type: "procesadas", "duplicados", o "review"
    
    Returns:
        ID del archivo en Drive, o None si falla
    """
    # Determinar carpeta destino
    folder_map = {
        "procesadas": FOLDER_PROCESADAS,
        "duplicados": FOLDER_DUPLICADOS,
        "review": FOLDER_REVIEW,
    }
    folder_id = folder_map.get(folder_type, FOLDER_PROCESADAS)
    
    # Determinar MIME type
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    mime_types = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }
    mime_type = mime_types.get(ext, "application/octet-stream")
    
    try:
        service = get_drive_service()
        
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()
        
        return file.get("id")
    
    except Exception as e:
        st.error(f"Error subiendo a Drive: {e}")
        return None
