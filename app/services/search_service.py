import logging
from typing import List, Optional, Dict
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import QueryType
from app.core.settings import Settings

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.settings = Settings()
        self.endpoint = self.settings.AZURE_SEARCH_ENDPOINT
        self.key = self.settings.AZURE_SEARCH_KEY
        self.index_name = self.settings.AZURE_SEARCH_INDEX_NAME
        self.credential = AzureKeyCredential(self.key)
        
        # Inicializar el cliente de búsqueda
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential
        )
        
    async def search_manuals(self, query: str = None) -> List[dict]:
        """
        Busca manuales que coincidan con la consulta
        """
        try:
            # Si no hay consulta, retornar todos los documentos
            if not query:
                results = self.search_client.search("*", top=100)
            else:
                results = self.search_client.search(
                    query,
                    query_type=QueryType.SEMANTIC,
                    query_language="es-ES",
                    top=10
                )
            
            # Convertir resultados a lista de diccionarios
            documents = []
            for doc in results:
                documents.append({
                    "id": doc.get("id", ""),
                    "name": doc.get("name", ""),
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {})
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"Error en búsqueda de manuales: {str(e)}")
            return []
            
    async def get_manual_by_id(self, manual_id: str) -> Optional[dict]:
        """
        Obtiene un manual específico por su ID
        """
        try:
            doc = self.search_client.get_document(manual_id)
            return {
                "id": doc.get("id", ""),
                "name": doc.get("name", ""),
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {})
            }
        except Exception as e:
            logger.error(f"Error obteniendo manual {manual_id}: {str(e)}")
            return None 