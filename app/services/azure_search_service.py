"""
Servicio para interactuar con Azure Cognitive Search.
Permite buscar y recuperar manuales técnicos.
"""

import os
import logging
import asyncio
import re
import time
from typing import Optional, List, Dict, Any
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# Configurar logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Reducido a INFO para menos verbosidad

# Configurar handler solo si no tiene ya uno
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def singleton(cls):
    """Decorador para implementar el patrón Singleton."""
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class AzureSearchService:
    """
    Servicio para interactuar con Azure Cognitive Search.
    Optimizado para minimizar latencia y maximizar el uso de caché.
    """

    def __init__(self):
        logger.info("Inicializando AzureSearchService")
        # Limpiar las comillas que puedan venir en las variables de entorno
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip('"')
        self.key = os.getenv("AZURE_SEARCH_API_KEY", "").strip('"')
        self.index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "azureblob-index").strip('"')

        logger.info(f"Endpoint: {self.endpoint}")
        logger.info(f"Index name: {self.index_name}")
        logger.info(f"API Key: {'*' * 5 + self.key[-5:] if self.key else 'No key found'}")

        if not self.endpoint or not self.key:
            error_msg = "Azure Search credentials not found in environment variables"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            self.credential = AzureKeyCredential(self.key)
            self.client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.index_name,
                credential=self.credential
            )
            logger.info("AzureSearchService inicializado correctamente")

            # Inicializar caché en memoria
            self.manual_cache = {}
            self.cache_ttl = 3600  # 1 hora
            self.last_cache_cleanup = time.time()

        except Exception as e:
            logger.error(f"Error inicializando AzureSearchService: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise

    async def search_manuals(self, query: str = None, limit: int = None) -> List[Dict[str, Any]]:
        """
        Busca manuales usando Azure Search con caché para consultas frecuentes.
        
        Args:
            query: Texto de búsqueda opcional
            limit: Número máximo de resultados a devolver
            
        Returns:
            Lista de documentos encontrados
        """
        cache_key = f"search_{query}_{limit}"
        if cache_key in self.manual_cache:
            cache_entry = self.manual_cache[cache_key]
            if time.time() - cache_entry['timestamp'] < self.cache_ttl:
                logger.info(f"Usando caché para búsqueda: {query}")
                return cache_entry['data']

        start_time = time.time()
        try:
            logger.info(f"Buscando manuales con query: {query}")
            
            # Usar el query si está presente, de lo contrario buscar todos los documentos
            search_text = query if query else "*"
            # Optimizar búsqueda especificando campos relevantes
            search_fields = ["metadata_storage_name", "modelo", "content"] if query else None
            
            # Limitar número de resultados si se especifica
            top = min(limit, 50) if limit else 50  # Reducido de 100 a 50 para mejorar rendimiento
            
            all_results = list(self.client.search(
                search_text=search_text,
                query_type="simple",  # Usar búsqueda simple para mayor velocidad
                search_fields=search_fields,
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo", "metadata_storage_size"],
                top=top,
                include_total_count=True
            ))
            
            logger.info(f"Total de documentos encontrados: {len(all_results)}")
            
            # Procesamiento más simplificado para mejorar rendimiento
            documents = []
            for result in all_results:
                doc = {
                    "name": result.get("metadata_storage_name", None),  # Manejar None explícitamente
                    "modelo": result.get("modelo", "No model"),
                    "content": result.get("content", "No content"),
                    "path": result.get("metadata_storage_path", "No path"),
                    "size": result.get("metadata_storage_size", 0)
                }
                documents.append(doc)
            
            # Almacenar en caché
            self.manual_cache[cache_key] = {
                'data': documents,
                'timestamp': time.time()
            }
            
            # Log de rendimiento
            elapsed = time.time() - start_time
            logger.info(f"Búsqueda completada en {elapsed:.2f}s")
            
            return documents

        except Exception as e:
            logger.error(f"Error buscando manuales: {str(e)}", exc_info=True)
            return []

    async def get_manual_by_model(self, model: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un manual específico por modelo con optimización de caché.
        
        Args:
            model: Código de modelo a buscar
            
        Returns:
            Diccionario con información del manual o None si no se encuentra
        """
        # Verificar caché
        cache_key = f"manual_{model.upper().strip()}"
        if cache_key in self.manual_cache:
            cache_entry = self.manual_cache[cache_key]
            if time.time() - cache_entry['timestamp'] < self.cache_ttl:
                logger.info(f"Usando manual desde caché para {model}")
                return cache_entry['data']
        
        # Limpiar caché antigua cada hora
        current_time = time.time()
        if current_time - self.last_cache_cleanup > 3600:
            self._cleanup_cache()
            self.last_cache_cleanup = current_time
        
        start_time = time.time()
        try:
            logger.info(f"Buscando manual para modelo: {model}")
            
            # Normalizar el modelo (eliminar espacios y convertir a mayúsculas)
            model_normalized = model.upper().strip()
            model_with_wildcard = f"{model_normalized}*"
            
            # Estrategia optimizada: búsqueda directa en el campo 'modelo' para mayor velocidad
            results = list(self.client.search(
                search_text=model_with_wildcard,
                query_type="simple",  # Usar búsqueda simple para mayor velocidad
                search_fields=["modelo"],  # Buscar solo en el campo 'modelo'
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                top=1
            ))
            
            if not results:
                logger.warning(f"No se encontró manual para el modelo: {model}")
                return None
            
            # Procesar resultado
            result = results[0]
            name = result.get("metadata_storage_name", None)  # Manejar None explícitamente
            modelo = result.get("modelo", "No model")
            content = result.get("content", "")
            
            if not content:
                logger.warning(f"No hay contenido disponible para el modelo: {model}")
                return None
            
            # Limpiar el contenido de espacios en blanco excesivos
            content = re.sub(r'\n\s*\n', '\n\n', content)
            content = re.sub(r' +', ' ', content)
            content = re.sub(r'^\s+|\s+$', '', content, flags=re.MULTILINE)
            
            manual_data = {
                "name": name,  # Puede ser None, lo cual es válido ya que no se buscan imágenes
                "modelo": modelo,
                "content": content,
                "path": result.get("metadata_storage_path", "No path")
            }
            
            # Guardar en caché
            self.manual_cache[cache_key] = {
                'data': manual_data,
                'timestamp': time.time()
            }
            
            # Log de rendimiento
            elapsed = time.time() - start_time
            logger.info(f"Manual para {model} recuperado en {elapsed:.2f}s")
            
            return manual_data

        except Exception as e:
            logger.error(f"Error buscando manual: {str(e)}", exc_info=True)
            return None

    def _cleanup_cache(self):
        """Limpia entradas caducadas de la caché"""
        current_time = time.time()
        expired_keys = [
            k for k, v in self.manual_cache.items()
            if current_time - v['timestamp'] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.manual_cache[key]
        logger.info(f"Caché limpiada: eliminadas {len(expired_keys)} entradas antiguas")

if __name__ == "__main__":
    # Ejemplo de uso para depuración
    async def main():
        start = time.time()
        service = AzureSearchService()
        manuals = await service.search_manuals()
        print(f"Manuales encontrados: {len(manuals)}")
        manual = await service.get_manual_by_model("AI2300")
        print(f"Manual para AI2300: {manual is not None}")
        print(f"Tiempo total: {time.time() - start:.2f}s")

    asyncio.run(main())