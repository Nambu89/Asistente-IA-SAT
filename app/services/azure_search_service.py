import os
import logging
import asyncio
import re
from typing import Optional, List, Dict, Any
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# Configurar logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Asegurar que los logs se muestren en la consola
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class AzureSearchService:
    def __init__(self):
        print("\n=== INICIALIZANDO AZURE SEARCH SERVICE ===")
        logger.info("Inicializando AzureSearchService")
        
        # Limpiar las comillas que puedan venir en las variables de entorno
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip('"')
        self.key = os.getenv("AZURE_SEARCH_API_KEY", "").strip('"')
        self.index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "azureblob-index").strip('"')
        
        print(f"Endpoint: {self.endpoint}")
        print(f"Index name: {self.index_name}")
        print(f"API Key: {'*' * 5 + self.key[-5:] if self.key else 'No key found'}")
        
        logger.info(f"Endpoint: {self.endpoint}")
        logger.info(f"Index name: {self.index_name}")
        logger.info(f"API Key: {'*' * 5 + self.key[-5:] if self.key else 'No key found'}")
        
        if not self.endpoint or not self.key:
            error_msg = "Azure Search credentials not found in environment variables"
            print(f"ERROR: {error_msg}")
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            self.credential = AzureKeyCredential(self.key)
            self.client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.index_name,
                credential=self.credential
            )
            print("AzureSearchService inicializado correctamente")
            logger.info("AzureSearchService inicializado correctamente")
        except Exception as e:
            print(f"ERROR inicializando AzureSearchService: {str(e)}")
            logger.error(f"Error inicializando AzureSearchService: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Respuesta del servidor: {e.response.text}")
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise

    async def search_manuals(self, query: str = None) -> List[Dict[str, Any]]:
        """
        Busca manuales usando Azure Search
        """
        try:
            print("=== INICIO DE BÚSQUEDA DE MANUALES ===")
            print(f"Buscando manuales con query: {query}")
            logger.info(f"Buscando manuales con query: {query}")
            
            # Usar el query si está presente, de lo contrario buscar todos los documentos
            search_text = query if query else "*"
            search_fields = ["metadata_storage_name", "modelo", "content"] if query else None
            
            print("Obteniendo documentos del índice...")
            logger.info("Obteniendo documentos del índice...")
            
            all_results = list(self.client.search(
                search_text=search_text,
                search_fields=search_fields,
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                top=100,
                include_total_count=True
            ))
            
            print(f"Total de documentos en el índice: {len(all_results)}")
            logger.info(f"Total de documentos en el índice: {len(all_results)}")
            
            # Mostrar los campos disponibles del primer documento
            if all_results:
                print("\nPrimer documento encontrado:")
                logger.info("Primer documento encontrado:")
                first_doc = all_results[0]
                for field, value in first_doc.items():
                    truncated_value = value[:100] if isinstance(value, str) else value
                    print(f"Campo: {field} = {truncated_value}")
                    logger.info(f"Campo: {field} = {truncated_value}")
                # Mostrar específicamente el contenido
                content_sample = first_doc.get("content", "")[:200]
                print(f"Contenido (primeros 200 chars): {content_sample}")
                logger.info(f"Contenido (primeros 200 chars): {content_sample}")
            
            documents = []
            print("\nProcesando documentos:")
            logger.info("Procesando documentos:")
            
            for result in all_results:
                doc = {
                    "name": result.get("metadata_storage_name", "No name"),
                    "modelo": result.get("modelo", "No model"),
                    "content": result.get("content", "No content"),
                    "path": result.get("metadata_storage_path", "No path")
                }
                documents.append(doc)
                print(f"Documento encontrado: Nombre={doc['name']}, Modelo={doc['modelo']}")
                logger.info(f"Documento encontrado: Nombre={doc['name']}, Modelo={doc['modelo']}")
                # Añadir log del contenido para depuración
                content_sample = doc["content"][:200]
                print(f"Contenido (primeros 200 chars): {content_sample}")
                logger.info(f"Contenido (primeros 200 chars): {content_sample}")
            
            print("=== FIN DE BÚSQUEDA DE MANUALES ===\n")
            return documents

        except Exception as e:
            print(f"ERROR en search_manuals: {str(e)}")
            logger.error(f"Error searching manuals: {str(e)}", exc_info=True)
            if hasattr(e, 'response') and e.response is not None:
                print(f"Respuesta del servidor: {e.response.text}")
                logger.error(f"Respuesta del servidor: {e.response.text}")
            return []

    async def get_manual_by_model(self, model: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un manual específico por modelo, asegurando el contenido completo
        """
        try:
            print(f"\n=== BUSCANDO MANUAL PARA MODELO: {model} ===")
            logger.info(f"Buscando manual para modelo: {model}")
            
            # Normalizar el modelo
            model_normalized = model.upper().strip()
            print(f"Modelo normalizado: {model_normalized}")
            logger.info(f"Modelo normalizado: {model_normalized}")
            
            # Listar todos los documentos para depuración
            print("\nListando todos los documentos disponibles:")
            logger.info("Listando todos los documentos disponibles:")
            all_docs = list(self.client.search(
                search_text="*",
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                top=100
            ))
            print(f"Total documentos en el índice: {len(all_docs)}")
            logger.info(f"Total documentos en el índice: {len(all_docs)}")
            
            for doc in all_docs:
                name = doc.get("metadata_storage_name", "No name")
                modelo = doc.get("modelo", "No model")
                content_sample = doc.get("content", "")[:200]
                print(f"- Archivo: {name} -> Modelo extraído: {modelo}")
                print(f"  Contenido (primeros 200 chars): {content_sample}")
                logger.info(f"- Archivo: {name} -> Modelo extraído: {modelo}")
                logger.info(f"  Contenido (primeros 200 chars): {content_sample}")
            
            # Estrategias de búsqueda
            search_strategies = [
                # 1. Búsqueda en el campo modelo
                {
                    "name": "Búsqueda por modelo",
                    "search": lambda: list(self.client.search(
                        search_text=model_normalized,
                        search_fields=["modelo"],
                        select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                        top=1
                    ))
                },
                # 2. Búsqueda por nombre del archivo
                {
                    "name": "Búsqueda por nombre del archivo",
                    "search": lambda: list(self.client.search(
                        search_text=model_normalized,
                        search_fields=["metadata_storage_name"],
                        select=["metadata_storage_name", "metadata_storage_path", "content", "modelo"],
                        top=1
                    ))
                }
            ]
            
            for i, strategy in enumerate(search_strategies, 1):
                print(f"\nIntentando estrategia #{i}: {strategy['name']}")
                logger.info(f"Intentando estrategia #{i}: {strategy['name']}")
                try:
                    results = strategy["search"]()
                    print(f"Estrategia #{i} encontró {len(results)} resultados")
                    logger.info(f"Estrategia #{i} encontró {len(results)} resultados")
                    
                    if results:
                        for result in results:
                            name = result.get("metadata_storage_name", "No name")
                            modelo = result.get("modelo", "No model")
                            content = result.get("content", "")
                            print(f"Resultado encontrado: Archivo={name}, Modelo={modelo}")
                            print(f"Contenido disponible: {'Sí' if content else 'No'}")
                            print(f"Contenido (primeros 200 chars): {content[:200]}")
                            logger.info(f"Resultado encontrado: Archivo={name}, Modelo={modelo}")
                            logger.info(f"Contenido disponible: {'Sí' if content else 'No'}")
                            logger.info(f"Contenido (primeros 200 chars): {content[:200]}")
                            
                            # CRÍTICO: ASEGURAR QUE SE RECUPERE EL CONTENIDO COMPLETO
                            if content:
                                # Limpiar el contenido de espacios en blanco excesivos y líneas vacías
                                content = re.sub(r'\n\s*\n', '\n\n', content)  # Reemplazar múltiples líneas vacías con doble salto
                                content = re.sub(r' +', ' ', content)  # Reemplazar múltiples espacios con uno solo
                                content = re.sub(r'^\s+|\s+$', '', content, flags=re.MULTILINE)  # Eliminar espacios al inicio y final de cada línea
                                
                                # Intentar recuperar el contenido completo
                                logger.info(f"Intentando recuperar contenido completo para {name}")
                                try:
                                    # Recuperar el documento completo con otra llamada usando el nombre exacto
                                    full_doc = list(self.client.search(
                                        search_text=f'"{name}"',  # Búsqueda exacta del nombre
                                        search_fields=["metadata_storage_name"],
                                        select=["metadata_storage_name", "content"],
                                        top=1
                                    ))
                                    if full_doc and full_doc[0].get("content"):
                                        new_content = full_doc[0].get("content")
                                        # Limpiar también el nuevo contenido
                                        new_content = re.sub(r'\n\s*\n', '\n\n', new_content)
                                        new_content = re.sub(r' +', ' ', new_content)
                                        new_content = re.sub(r'^\s+|\s+$', '', new_content, flags=re.MULTILINE)
                                        
                                        if len(new_content) > len(content):
                                            content = new_content
                                            logger.info(f"Contenido completo recuperado. Longitud: {len(content)}")
                                            logger.info(f"Primeros 200 caracteres: {content[:200]}")
                                            logger.info(f"Últimos 200 caracteres: {content[-200:] if len(content) > 200 else content}")
                                except Exception as e:
                                    logger.error(f"Error recuperando contenido completo: {str(e)}")
                                    
                                # Verificar si el contenido parece incompleto o tiene demasiados espacios en blanco
                                if len(content) < 1000 or "..." in content or content.count('\n\n') > 50:
                                    logger.warning(f"El contenido parece incompleto o tiene demasiados espacios. Longitud: {len(content)}, Líneas vacías: {content.count('\n\n')}")
                                    # Intentar una búsqueda más agresiva
                                    try:
                                        aggressive_search = list(self.client.search(
                                            search_text=name,
                                            select=["content"],
                                            top=1,
                                            query_type="full"
                                        ))
                                        if aggressive_search and aggressive_search[0].get("content"):
                                            new_content = aggressive_search[0].get("content")
                                            # Limpiar el contenido agresivo
                                            new_content = re.sub(r'\n\s*\n', '\n\n', new_content)
                                            new_content = re.sub(r' +', ' ', new_content)
                                            new_content = re.sub(r'^\s+|\s+$', '', new_content, flags=re.MULTILINE)
                                            
                                            if len(new_content) > len(content):
                                                content = new_content
                                                logger.info(f"Contenido recuperado con búsqueda agresiva. Longitud: {len(content)}")
                                    except Exception as e:
                                        logger.error(f"Error en búsqueda agresiva: {str(e)}")
                            
                            # Usar el primer resultado si el modelo coincide o no está disponible
                            if not modelo or modelo.upper() == model_normalized:
                                print(f"¡Coincidencia encontrada o usando primer resultado!")
                                logger.info(f"¡Coincidencia encontrada o usando primer resultado!")
                                return {
                                    "name": name,
                                    "modelo": modelo,
                                    "content": content,
                                    "path": result.get("metadata_storage_path", "No path")
                                }
                        # Si no hay coincidencia exacta, usar el primer resultado
                        first_result = results[0]
                        print(f"No se encontró coincidencia exacta, usando el primer resultado")
                        logger.info(f"No se encontró coincidencia exacta, usando el primer resultado")
                        content = first_result.get("content", "")
                        print(f"Contenido (primeros 200 chars): {content[:200]}")
                        logger.info(f"Contenido (primeros 200 chars): {content[:200]}")
                        
                        return {
                            "name": first_result.get("metadata_storage_name", "No name"),
                            "modelo": first_result.get("modelo", "No model"),
                            "content": content,
                            "path": first_result.get("metadata_storage_path", "No path")
                        }
                except Exception as search_error:
                    print(f"Error en estrategia #{i}: {str(search_error)}")
                    logger.error(f"Error en estrategia #{i}: {str(search_error)}", exc_info=True)
                    continue
            
            print(f"\nNo se encontró manual para el modelo: {model}")
            logger.warning(f"No se encontró manual para el modelo: {model}")
            return None

        except Exception as e:
            print(f"Error buscando manual: {str(e)}")
            logger.error(f"Error buscando manual: {str(e)}", exc_info=True)
            if hasattr(e, 'response') and e.response is not None:
                print(f"Respuesta del servidor: {e.response.text}")
                logger.error(f"Respuesta del servidor: {e.response.text}")
            return None

if __name__ == "__main__":
    # Ejemplo de uso para depuración
    async def main():
        service = AzureSearchService()
        manuals = await service.search_manuals()
        print(f"Manuales encontrados: {len(manuals)}")
        manual = await service.get_manual_by_model("AI2300")
        print(f"Manual para AI2300: {manual}")

    asyncio.run(main())