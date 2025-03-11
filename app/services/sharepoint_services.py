import requests
import logging
from pathlib import Path
from typing import Optional, List
from app.core.settings import Settings
import msal
import urllib.parse

logger = logging.getLogger(__name__)

class SharePointService:
    def __init__(self):
        self.settings = Settings()
        self.base_url = self.settings.SHAREPOINT_URL
        self.site_url = f"{self.base_url}{self.settings.SHAREPOINT_SITE}"
        self.docs_url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{urllib.parse.quote(self.settings.SHAREPOINT_DOC_LIBRARY)}')/Files"
        self.session = requests.Session()
        self._setup_auth()
    
    def _setup_auth(self):
        """Configura la autenticación con SharePoint"""
        try:
            # Configuración de la aplicación
            self.client_id = self.settings.SHAREPOINT_CLIENT_ID
            self.client_secret = self.settings.SHAREPOINT_CLIENT_SECRET
            self.tenant_id = self.settings.SHAREPOINT_TENANT_ID
            
            # Verificar que tenemos todas las credenciales necesarias
            if not all([self.client_id, self.client_secret, self.tenant_id]):
                logger.error("Faltan credenciales de SharePoint")
                raise ValueError("Faltan credenciales de SharePoint")
            
            logger.info(f"Configurando autenticación para tenant: {self.tenant_id}")
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            logger.info(f"Usando authority URL: {authority}")
            
            # Inicializar MSAL con la configuración completa
            self.app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret,
            )
            
            # Obtener token para SharePoint
            self.token = self._get_token()
            if self.token:
                self.session.headers.update({
                    'Authorization': f'Bearer {self.token}',
                    'Accept': 'application/json',
                    'Content-type': 'application/json'
                })
                logger.info("Autenticación de SharePoint configurada correctamente")
            else:
                logger.error("No se pudo obtener el token de SharePoint")
                raise ValueError("No se pudo obtener el token de SharePoint")
                
        except Exception as e:
            logger.error(f"Error en la configuración de autenticación: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise
    
    def _get_token(self) -> Optional[str]:
        """Obtiene el token de acceso para SharePoint"""
        try:
            # Intentar primero con el scope de SharePoint
            scope = ["https://tef950226415.sharepoint.com/.default"]
            logger.info(f"Solicitando token con scope: {scope}")
            
            result = self.app.acquire_token_for_client(scopes=scope)
            
            if "access_token" in result:
                logger.info("Token obtenido correctamente")
                return result["access_token"]
            
            # Si falla, intentar con Graph API
            scope = ["https://graph.microsoft.com/.default"]
            logger.info(f"Intentando con scope alternativo: {scope}")
            
            result = self.app.acquire_token_for_client(scopes=scope)
            
            if "access_token" in result:
                logger.info("Token obtenido correctamente con scope alternativo")
                return result["access_token"]
            else:
                logger.error(f"Error obteniendo token: {result.get('error_description', 'Unknown error')}")
                return None
        except Exception as e:
            logger.error(f"Error en la obtención del token: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text}")
            return None
        
    async def get_manual_by_model(self, model_number: str) -> Optional[bytes]:
        """Busca y descarga el manual técnico para un modelo específico"""
        try:
            # Renovar token si es necesario
            if not self._get_token():
                self._setup_auth()
                
            # Normalizar el número de modelo
            model_number = model_number.upper().strip()
            
            # Usar la API REST de SharePoint directamente
            files_url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{urllib.parse.quote(self.settings.SHAREPOINT_DOC_LIBRARY)}')/Files"
            logger.info(f"Buscando manual para el modelo {model_number} en: {files_url}")
            
            response = self.session.get(files_url)
            response.raise_for_status()
            
            files = response.json().get('value', [])
            logger.info(f"Total de archivos encontrados: {len(files)}")
            
            # Buscar el archivo que coincida con el modelo
            matching_files = [
                f for f in files 
                if model_number in f['Name'].upper() 
                and ('MANUAL' in f['Name'].upper() or 'SERVICIO' in f['Name'].upper())
            ]
            
            if not matching_files:
                logger.info(f"No se encontró manual para el modelo {model_number}")
                return None
                
            # Descargar el primer archivo que coincida
            file = matching_files[0]
            download_url = f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{urllib.parse.quote(file['ServerRelativeUrl'])}')/OpenBinaryStream"
            
            file_response = self.session.get(download_url)
            file_response.raise_for_status()
            
            logger.info(f"Manual descargado correctamente: {file['Name']}")
            return file_response.content
            
        except Exception as e:
            logger.error(f"Error accediendo a SharePoint: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text}")
            return None
    
    async def search_manuals(self, query: str) -> List[dict]:
        """Busca manuales que coincidan con una consulta específica"""
        try:
            # Renovar token si es necesario
            if not self._get_token():
                self._setup_auth()
                
            # Usar la API REST de SharePoint directamente
            files_url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{urllib.parse.quote(self.settings.SHAREPOINT_DOC_LIBRARY)}')/Files"
            logger.info(f"Buscando archivos en: {files_url}")
            
            response = self.session.get(files_url)
            response.raise_for_status()
            
            files = response.json().get('value', [])
            logger.info(f"Total de archivos encontrados: {len(files)}")
            logger.info(f"Nombres de archivos: {[f.get('Name', '') for f in files]}")
            
            # Filtrar archivos que coincidan con la búsqueda
            matching_files = [
                {
                    'name': f['Name'],
                    'size': f.get('Length', 0),
                    'lastModified': f.get('TimeLastModified', ''),
                    'downloadUrl': f"{self.site_url}/_api/web/GetFileByServerRelativeUrl('{urllib.parse.quote(f['ServerRelativeUrl'])}')/OpenBinaryStream",
                    'webUrl': f"{self.site_url}{f['ServerRelativeUrl']}"
                }
                for f in files 
                if (not query or query.upper() in f['Name'].upper())
            ]
            
            logger.info(f"Archivos que coinciden con '{query}': {[f['name'] for f in matching_files]}")
            return matching_files
            
        except Exception as e:
            logger.error(f"Error buscando manuales: {str(e)}")
            logger.error(f"Detalles completos del error: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text}")
            return [] 