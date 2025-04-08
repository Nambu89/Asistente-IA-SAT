"""
Servicio para interactuar con Azure Cognitive Search.
Permite buscar y recuperar manuales técnicos e imágenes relacionadas.
"""

import os
import logging
import asyncio
import re
from typing import Optional, List, Dict, Any
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

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
        self.index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "manuales-index").strip('"')
        
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
                select=["metadata_storage_name", "metadata_storage_path", "content", "modelo", "metadata_storage_size"],
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
                    "path": result.get("metadata_storage_path", "No path"),
                    "size": result.get("metadata_storage_size", 0)
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
            
            # Estrategias de búsqueda
            search_strategies = [
                # 1. Búsqueda en el campo modelo
                {
                    "name": "Búsqueda por modelo",
                    "search": lambda: list(self.client.search(
                        search_text=model_normalized,
                        search_fields=["modelo"],
                        select=["metadata_storage_name", "metadata_storage_path", "content", "modelo", "metadata_storage_size"],
                        top=1
                    ))
                },
                # 2. Búsqueda por nombre del archivo
                {
                    "name": "Búsqueda por nombre del archivo",
                    "search": lambda: list(self.client.search(
                        search_text=model_normalized,
                        search_fields=["metadata_storage_name"],
                        select=["metadata_storage_name", "metadata_storage_path", "content", "modelo", "metadata_storage_size"],
                        top=1
                    ))
                },
                # 3. Búsqueda semántica
                {
                    "name": "Búsqueda semántica",
                    "search": lambda: list(self.client.search(
                        search_text=f"manual técnico {model_normalized}",
                        search_mode="all",
                        select=["metadata_storage_name", "metadata_storage_path", "content", "modelo", "metadata_storage_size"],
                        top=3
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
                        # Si encontramos más de un resultado, priorizar el que tenga el modelo exacto
                        if len(results) > 1:
                            exact_match = next((r for r in results if r.get("modelo", "").upper() == model_normalized), None)
                            if exact_match:
                                results = [exact_match]
                            
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
                                
                                # Buscar imágenes relacionadas con este manual
                                image_references = await self.find_images_for_manual(name, model_normalized)
                                
                                return {
                                    "name": name,
                                    "modelo": modelo,
                                    "content": content,
                                    "path": result.get("metadata_storage_path", "No path"),
                                    "size": result.get("metadata_storage_size", 0),
                                    "image_references": image_references
                                }
                        
                        # Si no hay coincidencia exacta, usar el primer resultado
                        first_result = results[0]
                        print(f"No se encontró coincidencia exacta, usando el primer resultado")
                        logger.info(f"No se encontró coincidencia exacta, usando el primer resultado")
                        content = first_result.get("content", "")
                        print(f"Contenido (primeros 200 chars): {content[:200]}")
                        logger.info(f"Contenido (primeros 200 chars): {content[:200]}")
                        
                        # Búsqueda de imágenes relacionadas
                        name = first_result.get("metadata_storage_name", "No name")
                        image_references = await self.find_images_for_manual(name, model_normalized)
                        
                        return {
                            "name": name,
                            "modelo": first_result.get("modelo", "No model"),
                            "content": content,
                            "path": first_result.get("metadata_storage_path", "No path"),
                            "size": first_result.get("metadata_storage_size", 0),
                            "image_references": image_references
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

    async def find_images_for_manual(self, manual_name: str, model_code: str) -> List[Dict[str, Any]]:
        """
        Busca imágenes relacionadas con un manual específico.
        
        Args:
            manual_name: Nombre del archivo del manual
            model_code: Código del modelo del electrodoméstico
            
        Returns:
            Lista de referencias a imágenes encontradas
        """
        try:
            # Extraer la base del nombre del archivo (sin extensión)
            base_name = os.path.splitext(manual_name)[0]
            
            # Buscar documentos que podrían ser imágenes relacionadas con este manual
            # Primero por el nombre base del manual
            image_search_results = list(self.client.search(
                search_text=base_name,
                search_fields=["metadata_storage_name"],
                select=["metadata_storage_name", "metadata_storage_path", "metadata_storage_content_type", "metadata_storage_size"],
                filter="search.ismatch('image/*', 'metadata_content_type')",
                top=20
            ))
            
            # También buscar por el código del modelo
            model_image_results = list(self.client.search(
                search_text=model_code,
                search_fields=["metadata_storage_name"],
                select=["metadata_storage_name", "metadata_storage_path", "metadata_storage_content_type", "metadata_storage_size"],
                filter="search.ismatch('image/*', 'metadata_content_type')",
                top=20
            ))
            
            # Combinar resultados y eliminar duplicados
            all_results = image_search_results + model_image_results
            unique_results = {}
            for result in all_results:
                name = result.get("metadata_storage_name", "")
                if name and name not in unique_results:
                    unique_results[name] = result
            
            # Convertir a lista de referencias de imágenes
            image_references = []
            for name, result in unique_results.items():
                # Extraer información sobre la figura/diagrama del nombre del archivo
                figure_info = self._extract_figure_info(name)
                
                image_references.append({
                    "reference": figure_info["reference"],
                    "figure_number": figure_info["figure_number"],
                    "description": figure_info["description"],
                    "file_name": name,
                    "path": result.get("metadata_storage_path", ""),
                    "content_type": result.get("metadata_storage_content_type", "image/jpeg"),
                    "size": result.get("metadata_storage_size", 0)
                })
            
            logger.info(f"Encontradas {len(image_references)} imágenes relacionadas con el manual {manual_name}")
            return image_references
            
        except Exception as e:
            logger.error(f"Error buscando imágenes para manual {manual_name}: {str(e)}")
            return []
    
    def _extract_figure_info(self, file_name: str) -> Dict[str, str]:
        """
        Extrae información sobre la figura/diagrama a partir del nombre del archivo
        """
        # Patrones comunes en nombres de archivos de imágenes
        figure_patterns = [
            (r'fig(?:ura)?[\s_-]*(\d+)', 'Figura {}'),
            (r'diag(?:rama)?[\s_-]*(\d+)', 'Diagrama {}'),
            (r'esquema[\s_-]*(\d+)', 'Esquema {}'),
            (r'imagen[\s_-]*(\d+)', 'Imagen {}'),
            (r'photo[\s_-]*(\d+)', 'Foto {}'),
            (r'img[\s_-]*(\d+)', 'Imagen {}')
        ]
        
        lowercase_name = file_name.lower()
        
        for pattern, template in figure_patterns:
            match = re.search(pattern, lowercase_name)
            if match:
                figure_number = match.group(1)
                reference = template.format(figure_number)
                
                # Intentar extraer descripción del nombre del archivo
                desc_match = re.search(r'([a-z]+[_\s-][a-z]+)', lowercase_name.replace(match.group(0), ''))
                description = desc_match.group(1).replace('_', ' ').replace('-', ' ').strip() if desc_match else "Sin descripción"
                
                return {
                    "reference": reference,
                    "figure_number": figure_number,
                    "description": description
                }
        
        # Si no coincide con ningún patrón conocido
        return {
            "reference": "Imagen del manual",
            "figure_number": "N/A",
            "description": os.path.splitext(file_name)[0].replace('_', ' ').replace('-', ' ')
        }
    
    async def get_image_url(self, image_reference: Dict[str, Any]) -> Optional[str]:
        """
        Obtiene la URL de una imagen específica basada en su referencia
        
        Args:
            image_reference: Diccionario con la información de la referencia de la imagen
            
        Returns:
            URL de la imagen o None si no se encuentra
        """
        try:
            path = image_reference.get("path", "")
            if not path:
                return None
            
            # La URL completa depende de cómo se almacenan las imágenes en Azure Storage
            # Si el path ya es una URL completa, la devolvemos directamente
            if path.startswith("http"):
                return path
            
            # Si no, construimos la URL basada en el contenedor de Azure Storage
            storage_account = self.endpoint.split('.')[0].replace('https://', '')
            container_name = "manuales"  # Ajustar según tu configuración
            
            # Construir URL SAS (si es necesario)
            # Por ahora, retornamos una URL sin SAS para acceso público
            return f"https://{storage_account}.blob.core.windows.net/{container_name}/{image_reference['file_name']}"
            
        except Exception as e:
            logger.error(f"Error obteniendo URL para imagen: {str(e)}")
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