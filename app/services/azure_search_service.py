"""
Servicio para interactuar con Azure Cognitive Search.
Permite buscar y recuperar manuales técnicos.
"""

import os
import logging
import asyncio
import re
import time
import json
from typing import Optional, List, Dict, Any
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# Importar nuevo servicio Redis
from app.services.redis_service import RedisService

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

            # Inicializar servicio Redis para caché distribuida
            self.redis = RedisService()
            self.cache_ttl = 3600  # 1 hora
            
            # Mantener una caché en memoria mínima como respaldo
            self.memory_cache = {}
            self.memory_cache_size = 20  # Número máximo de entradas en memoria

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
        cache_key = f"svan:search:{query if query else 'all'}_{limit if limit else 50}"
        
        # Intentar obtener de Redis
        if self.redis.connected:
            cached_data = self.redis.get_json(cache_key)
            if cached_data:
                logger.info(f"Usando caché Redis para búsqueda: {query}")
                return cached_data
        
        # Intentar obtener de memoria como respaldo
        if cache_key in self.memory_cache:
            logger.info(f"Usando caché memoria para búsqueda: {query}")
            return self.memory_cache[cache_key]['data']

        start_time = time.time()
        try:
            logger.info(f"Buscando manuales con query: {query}")
            
            # Usar el query si está presente, de lo contrario buscar todos los documentos
            search_text = query if query else "*"
            # Optimizar búsqueda especificando campos relevantes
            search_fields = ["metadata_storage_name", "modelo", "content"] if query else None
            
            # Limitar número de resultados si se especifica
            top = min(limit or 50, 50)  # Máximo 50 resultados
            
            # Construir filtro si el query parece un modelo
            filter_condition = None
            if query and re.match(r'[SWAH][A-Z0-9]{2,}', query.upper()):
                # Es un posible modelo, optimizamos la búsqueda
                query_upper = query.upper()
                filter_condition = f"modelo eq '{query_upper}' or modelo eq '{query_upper}*'"
                logger.info(f"Aplicando filtro para modelo: {filter_condition}")
            
            all_results = list(self.client.search(
                search_text=search_text,
                query_type="simple", 
                search_fields=search_fields,
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo", "metadata_storage_size"],
                top=top,
                include_total_count=True,
                filter=filter_condition
            ))
            
            logger.info(f"Total de documentos encontrados: {len(all_results)}")
            
            # Procesamiento más simplificado para mejorar rendimiento
            documents = []
            for result in all_results:
                doc = {
                    "name": result.get("metadata_storage_name", None),
                    "modelo": result.get("modelo", "No model"),
                    "content": result.get("content", "No content"),
                    "path": result.get("metadata_storage_path", "No path"),
                    "size": result.get("metadata_storage_size", 0)
                }
                documents.append(doc)
            
            # Almacenar en Redis si está disponible
            if self.redis.connected:
                self.redis.set_json(cache_key, documents, ex=self.cache_ttl)
            
            # Almacenar en memoria como respaldo (con gestión de tamaño)
            self.memory_cache[cache_key] = {
                'data': documents,
                'timestamp': time.time()
            }
            self._manage_memory_cache()
            
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
        if not model:
            return None
            
        # Normalizar modelo
        model_normalized = model.upper().strip()
        cache_key = f"svan:manual:{model_normalized}"
        
        # Intentar obtener de Redis
        if self.redis.connected:
            cached_data = self.redis.get_json(cache_key)
            if cached_data:
                logger.info(f"Usando manual desde Redis para {model}")
                return cached_data
        
        # Intentar obtener de memoria como respaldo
        if cache_key in self.memory_cache:
            logger.info(f"Usando manual desde memoria para {model}")
            return self.memory_cache[cache_key]['data']
        
        start_time = time.time()
        try:
            logger.info(f"Buscando manual para modelo: {model_normalized}")
            
            # Estrategia 1: Buscar modelo exacto
            filter_expr = f"modelo eq '{model_normalized}'"
            results = list(self.client.search(
                search_text="*",
                filter=filter_expr,
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                top=1
            ))
            if results:
                logger.info(f"Manual encontrado con búsqueda exacta para {model_normalized}")
                manual_data = results[0]
                self._cache_result(cache_key, manual_data)
                logger.info(f"Manual para {model_normalized} recuperado en {time.time() - start_time:.2f}s")
                return manual_data
            else:
                logger.info(f"No se encontró coincidencia exacta para {model_normalized}, probando con comodín")
                # Estrategia 2: Búsqueda con comodín
                filter_expr_wildcard = f"modelo eq '{model_normalized}*'"
                results_wildcard = list(self.client.search(
                    search_text="*",
                    filter=filter_expr_wildcard,
                    select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                    top=1
                ))
                if results_wildcard:
                    logger.info(f"Manual encontrado con búsqueda con comodín para {model_normalized}")
                    manual_data = results_wildcard[0]
                    self._cache_result(cache_key, manual_data)
                    logger.info(f"Manual para {model_normalized} recuperado en {time.time() - start_time:.2f}s")
                    return manual_data
                else:
                    logger.info(f"No se encontró coincidencia con comodín para {model_normalized}, último intento: búsqueda de texto completo")
                    # Estrategia 3: Último intento - búsqueda de texto completo
                    results_fulltext = list(self.client.search(
                        search_text=model_normalized,
                        select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                        top=1
                    ))
                    if results_fulltext:
                        logger.info(f"Manual encontrado con búsqueda de texto completo para {model_normalized}")
                        manual_data = results_fulltext[0]
                        self._cache_result(cache_key, manual_data)
                        logger.info(f"Manual para {model_normalized} recuperado en {time.time() - start_time:.2f}s")
                        return manual_data
                    else:
                        logger.warning(f"No se encontró manual para el modelo: {model_normalized} después de todas las estrategias")
                        return None
        except Exception as e:
            logger.error(f"Error al buscar manual para {model_normalized}: {str(e)}")
            return None

    def _cache_result(self, cache_key, result):
        manual_data = {
            "name": result.get("metadata_storage_name", None),
            "modelo": result.get("modelo", "No model"),
            "content": result.get("content", ""),
            "path": result.get("metadata_storage_path", "No path")
        }
        # Guardar en Redis si está disponible
        if self.redis.connected:
            self.redis.set_json(cache_key, manual_data, ex=self.cache_ttl)
        # Guardar en memoria como respaldo
        self.memory_cache[cache_key] = {
            'data': manual_data,
            'timestamp': time.time()
        }
        self._manage_memory_cache()

    def _manage_memory_cache(self):
        """Gestiona el tamaño de la caché en memoria, eliminando entradas antiguas si es necesario"""
        if len(self.memory_cache) <= self.memory_cache_size:
            return
            
        # Eliminar entradas más antiguas
        sorted_entries = sorted(
            self.memory_cache.items(),
            key=lambda x: x[1]['timestamp']
        )
        
        # Mantener solo las más recientes
        to_remove = len(self.memory_cache) - self.memory_cache_size
        for i in range(to_remove):
            key = sorted_entries[i][0]
            del self.memory_cache[key]
            
        logger.debug(f"Limpieza de caché en memoria: eliminadas {to_remove} entradas antiguas")