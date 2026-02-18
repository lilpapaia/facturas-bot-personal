# core/drive.py
"""
Operaciones con Google Drive.
Versión WEB - usa Streamlit secrets para credenciales.
"""
import io
import re
from typing import Optional, List, Dict

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config.settings import (
    FOLDER_PROCESADAS, 
    FOLDER_DUPLICADOS, 
    FOLDER_REVIEW,
    FOLDER_EMITIDAS,
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
        folder_type: "procesadas", "duplicados", "review", o "emitidas"
    
    Returns:
        ID del archivo en Drive, o None si falla
    """
    # Determinar carpeta destino
    folder_map = {
        "procesadas": FOLDER_PROCESADAS,
        "duplicados": FOLDER_DUPLICADOS,
        "review": FOLDER_REVIEW,
        "emitidas": FOLDER_EMITIDAS,
    }
    folder_id = folder_map.get(folder_type, FOLDER_PROCESADAS)
    
    # DEBUG
    st.info(f"🔍 DEBUG: Intentando subir '{filename}' a carpeta '{folder_type}' (ID: {folder_id})")
    
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
        
        # DEBUG: Verificar permisos de la carpeta
        try:
            folder_info = service.files().get(fileId=folder_id, fields="id,name,owners,permissions").execute()
            st.info(f"🔍 DEBUG: Carpeta encontrada: {folder_info.get('name')}")
        except Exception as e:
            st.error(f"🔍 DEBUG: No puedo acceder a la carpeta: {e}")
        
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True
        )
        
        st.info(f"🔍 DEBUG: Ejecutando upload...")
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True  # Añadido para soportar shared drives
        ).execute()
        
        st.success(f"🔍 DEBUG: Archivo subido con ID: {file.get('id')}")
        return file.get("id")
    
    except Exception as e:
        st.error(f"Error subiendo a Drive: {e}")
        return None


def list_files_in_folder(folder_type: str = "emitidas") -> List[Dict]:
    """
    Lista archivos en una carpeta de Drive.
    
    Args:
        folder_type: "procesadas", "duplicados", "review", o "emitidas"
    
    Returns:
        Lista de dicts con id, name, createdTime
    """
    folder_map = {
        "procesadas": FOLDER_PROCESADAS,
        "duplicados": FOLDER_DUPLICADOS,
        "review": FOLDER_REVIEW,
        "emitidas": FOLDER_EMITIDAS,
    }
    folder_id = folder_map.get(folder_type, FOLDER_EMITIDAS)
    
    try:
        service = get_drive_service()
        
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, createdTime, mimeType)",
            orderBy="createdTime desc"
        ).execute()
        
        return results.get("files", [])
    
    except Exception as e:
        st.error(f"Error listando archivos: {e}")
        return []


def download_file_bytes(file_id: str) -> Optional[bytes]:
    """
    Descarga un archivo de Drive como bytes.
    
    Args:
        file_id: ID del archivo en Drive
    
    Returns:
        Contenido del archivo en bytes, o None si falla
    """
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        
        file_bytes = io.BytesIO()
        downloader = request.execute()
        
        return downloader
    
    except Exception as e:
        st.error(f"Error descargando archivo: {e}")
        return None
