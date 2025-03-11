import logging
from pathlib import Path
from typing import Optional, List
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceExistsError
from app.core.settings import Settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.settings = Settings()
        self.connection_string = self.settings.AZURE_STORAGE_CONNECTION_STRING
        self.container_name = self.settings.AZURE_STORAGE_CONTAINER_NAME
        
        # Inicializar el cliente de Blob Storage
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.connection_string
        )
        
        # Asegurarse de que el contenedor existe
        self._ensure_container_exists()
        
    def _ensure_container_exists(self):
        """Asegura que el contenedor existe, si no lo crea"""
        try:
            container_client = self.blob_service_client.create_container(
                self.container_name
            )
            logger.info(f"Contenedor {self.container_name} creado")
        except ResourceExistsError:
            logger.info(f"Contenedor {self.container_name} ya existe")
            
    async def upload_manual(self, file_path: Path, model_number: str) -> Optional[str]:
        """
        Sube un manual al Blob Storage
        """
        try:
            # Crear un nombre único para el blob
            blob_name = f"manuales/{model_number}/{file_path.name}"
            
            # Obtener el cliente del blob
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            # Configurar el tipo de contenido
            content_settings = ContentSettings(content_type='application/pdf')
            
            # Subir el archivo
            with open(file_path, "rb") as data:
                blob_client.upload_blob(
                    data,
                    content_settings=content_settings,
                    overwrite=True
                )
                
            logger.info(f"Manual {file_path.name} subido correctamente como {blob_name}")
            return blob_client.url
            
        except Exception as e:
            logger.error(f"Error subiendo manual {file_path}: {str(e)}")
            return None
            
    async def download_manual(self, blob_name: str, destination: Path) -> bool:
        """
        Descarga un manual desde Blob Storage
        """
        try:
            # Obtener el cliente del blob
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            # Asegurarse de que el directorio destino existe
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Descargar el blob
            with open(destination, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
                
            logger.info(f"Manual {blob_name} descargado correctamente a {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Error descargando manual {blob_name}: {str(e)}")
            return False
            
    async def list_manuals(self, prefix: Optional[str] = None) -> List[str]:
        """
        Lista todos los manuales en el contenedor
        """
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            
            blobs = container_client.list_blobs(name_starts_with=prefix)
            manual_list = [blob.name for blob in blobs]
            
            logger.info(f"Listados {len(manual_list)} manuales")
            return manual_list
            
        except Exception as e:
            logger.error(f"Error listando manuales: {str(e)}")
            return []
            
    async def delete_manual(self, blob_name: str) -> bool:
        """
        Elimina un manual del Blob Storage
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            blob_client.delete_blob()
            logger.info(f"Manual {blob_name} eliminado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error eliminando manual {blob_name}: {str(e)}")
            return False 