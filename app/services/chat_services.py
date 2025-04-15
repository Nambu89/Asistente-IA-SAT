import logging
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import re
import json
import time
from fastapi import HTTPException
from app.core.settings import Settings
from app.services.azure_search_service import AzureSearchService
from app.services.azure_ai_foundry_service import AzureAIFoundryService 
from app.services.redis_service import RedisService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.settings = Settings()
        self.ai_foundry = AzureAIFoundryService()
        self.search_service = AzureSearchService()
        self.redis = RedisService()
        self.current_model = None
        self.conversation_history = []
        self.max_context_length = 8000  # Número máximo de caracteres a enviar a OpenAI

    async def get_chat_response(self, message: str) -> str:
        """
        Procesa un mensaje del usuario y retorna una respuesta
        """
        start_time = time.time()
        try:
            # Detectar modelo en el mensaje
            model = self._extract_model_from_message(message)
            if model:
                self.current_model = model
                logger.info(f"Modelo detectado en el mensaje: {model}")
            
            # Preparar contexto para el modelo
            context = ""
            manual_found = False
            manual_source = ""
            
            if self.current_model:
                # Crear cache key para mensajes similares
                message_hash = self._get_message_hash(message)
                cache_key = f"svan:chat:{self.current_model}:{message_hash}"
                
                # Verificar si tenemos una respuesta en caché para esta combinación modelo+mensaje
                cached_response = None
                if self.redis.connected:
                    cached_response = self.redis.get(cache_key)
                    if cached_response:
                        logger.info(f"Usando respuesta en caché para {self.current_model} y mensaje similar")
                        elapsed = time.time() - start_time
                        logger.info(f"Tiempo total (caché): {elapsed:.2f}s")
                        return cached_response
                
                # Intentar buscar información del modelo 
                manual = None
                
                # Intentar con Azure Search primero (más rápido y robusto)
                manual = await self.search_service.get_manual_by_model(self.current_model)
                manual_source = "search"
                
                # Si no se encuentra, intentar con AI Foundry como respaldo
                if not manual:
                    try:
                        manual = await self.ai_foundry.search_manual_by_model(self.current_model)
                        manual_source = "foundry"
                    except Exception as e:
                        logger.error(f"Error al buscar en AI Foundry: {str(e)}")
                
                # Construir el contexto si se encontró información
                if manual and manual.get('content'):
                    manual_found = True
                    logger.info(f"Manual encontrado a través de {manual_source}, longitud: {len(manual['content'])} caracteres")
                    
                    # Obtener información de marca y tipo
                    brand, product_type = self._get_brand_and_type(self.current_model)
                    
                    # Limitar tamaño del contexto 
                    content = manual['content']
                    if len(content) > self.max_context_length:
                        logger.info(f"Contenido truncado de {len(content)} a {self.max_context_length} caracteres")
                        content = content[:self.max_context_length] + "...[Contenido truncado por límite de tamaño]"
                    
                    context = f"""Modelo: {self.current_model}
Marca: {brand if brand else 'Desconocida'}
Tipo: {product_type if product_type else 'electrodoméstico'}

Manual técnico:
{content}"""
                else:
                    logger.warning(f"No se encontró manual para el modelo {self.current_model}")
                    context = f"No se encontró el manual para el modelo {self.current_model}"
            else:
                logger.info("No se ha especificado un modelo válido")
                context = "No se ha especificado un modelo válido"

            # Mantener historial de conversación limitado
            self.conversation_history.append({"role": "user", "content": message})
            if len(self.conversation_history) > 10:  # Limitar a últimos 10 mensajes
                self.conversation_history = self.conversation_history[-10:]
            
            # Preparar mensajes para Azure AI Foundry
            messages = [
                {"role": "system", "content": self.settings.SYSTEM_PROMPT},
                {"role": "system", "content": context}
            ]
            
            # Añadir historial reciente
            messages.extend(self.conversation_history[-5:])  # Últimos 5 mensajes
            
            # Medir tamaño de los mensajes para optimización
            total_tokens = sum(len(msg.get("content", "")) for msg in messages) // 4  # Estimación aproximada
            logger.info(f"Tokens estimados: ~{total_tokens}")
            
            # Ajustar max_tokens según el tamaño del input
            max_tokens = 2000
            if total_tokens > 6000:  # Si el input es muy grande
                max_tokens = 1000
                logger.info(f"Reduciendo max_tokens a {max_tokens} debido al tamaño del input")

            # Reporte de progreso
            search_elapsed = time.time() - start_time
            logger.info(f"Búsqueda completada en {search_elapsed:.2f}s, enviando a AI Foundry")

            # Llamar a Azure AI Foundry con datos del modelo específico
            assistant_response = await self.ai_foundry.chat_completion_with_data(
                messages=messages,
                query=message,  # Usar el mensaje del usuario como consulta para el índice vectorial
                model_number=self.current_model,
                temperature=0.7,
                max_tokens=max_tokens
            )
            
            if not assistant_response:
                raise HTTPException(status_code=500, detail="No se pudo obtener una respuesta del modelo")

            # Guardar respuesta en el historial
            self.conversation_history.append({"role": "assistant", "content": assistant_response})
            
            # Si teníamos un modelo, guardar en caché para futuras consultas similares
            if self.current_model and manual_found and self.redis.connected:
                # Solo guardar en caché respuestas para mensajes con manual encontrado
                message_hash = self._get_message_hash(message)
                cache_key = f"svan:chat:{self.current_model}:{message_hash}"
                self.redis.set(cache_key, assistant_response, ex=3600)  # 1 hora de caché
                logger.info(f"Respuesta guardada en caché con clave: {cache_key}")
            
            # Reportar tiempo total
            elapsed = time.time() - start_time
            logger.info(f"Tiempo total de procesamiento: {elapsed:.2f}s")

            return assistant_response

        except Exception as e:
            logger.error(f"Error en get_chat_response: {str(e)}")
            elapsed = time.time() - start_time
            logger.error(f"Error después de {elapsed:.2f}s")
            raise HTTPException(status_code=500, detail=str(e))

    def _extract_model_from_message(self, message: str) -> Optional[str]:
        """
        Extrae el número de modelo del mensaje del usuario
        """
        if not message:
            return None
            
        # Patrones de modelo (S/W/A/H seguido de números y letras)
        patterns = [
            r'[SWAH][A-Z0-9]{2,}[A-Z0-9]*(?:ENF|ENFX|AIDV|AIDVB|DGX|DGN|EX|EDC|PB|DTD|DDTD)?'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            if matches:
                # Filtrar palabras comunes que podrían coincidir por error
                filtered_matches = [m for m in matches if m not in ['HOLA', 'HACE', 'SABE', 'SOBRE', 'HASTA']]
                if filtered_matches:
                    return filtered_matches[0]
        
        return None

    def _get_brand_and_type(self, model: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Determina la marca y tipo de producto basado en el modelo
        """
        # Mapeo de letras iniciales a marcas
        brands = {
            'S': 'SVAN',
            'W': 'WONDER',
            'A': 'ASPES',
            'H': 'HYUNDAI'
        }
        
        # Mapeo de códigos a tipos de producto
        product_types = {
            # Lavado
            'L': 'lavadora',
            'LS': 'lavadora secadora',
            'LCS': 'lavadora carga superior',
            
            # Frío
            'C': 'combi',
            'CV': 'congelador vertical',
            'CH': 'congelador horizontal',
            'F': 'frigorífico',
            'FP': 'frigorífico peltier',
            
            # Cocción
            'H': 'horno',
            'V': 'vitrocerámica',
            'M': 'microondas',
            'MW': 'microondas',
            'MWI': 'microondas integrado',
            'SGW': 'placa de gas',
            
            # Campanas
            'K': 'campana',
            'CPD': 'campana decorativa',
            'CPE': 'campana extraíble',
            'CPP': 'campana piramidal',
            'CPT': 'campana tipo t',
            
            # Otros
            'VN': 'vinoteca',
            'J': 'lavavajillas',
            'LV': 'lavavajillas',
            'T': 'termo',
            'TV': 'televisor'
        }

        brand = brands.get(model[0].upper())
        
        # Intentar encontrar el tipo de producto
        product_type = None
        if len(model) >= 3:
            # Primero intentar con 3 letras
            type_code = model[:3].upper()
            if type_code in product_types:
                product_type = product_types[type_code]
            else:
                # Intentar con 2 letras
                type_code = model[:2].upper()
                if type_code in product_types:
                    product_type = product_types[type_code]
                else:
                    # Intentar con 1 letra
                    type_code = model[0].upper()
                    if type_code in product_types:
                        product_type = product_types[type_code]
        
        return brand, product_type
    
    def _get_message_hash(self, message: str) -> str:
        """
        Crea un hash simple del mensaje para caché.
        Normaliza el mensaje para que consultas similares generen el mismo hash.
        """
        # Normalizar: convertir a minúsculas y quitar puntuación no esencial
        normalized = message.lower()
        normalized = re.sub(r'[.,;:!?]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Usar solo las primeras palabras para capturar la esencia
        words = normalized.split()[:10]
        key_part = ' '.join(words)
        
        # Crear un hash MD5 más corto (primeros 8 caracteres)
        import hashlib
        hash_obj = hashlib.md5(key_part.encode())
        return hash_obj.hexdigest()[:8]

    async def process_attachment(self, file_path: Path) -> None:
        """
        Procesa un archivo adjunto
        """
        # Implementación básica de ejemplo que registra el archivo
        try:
            logger.info(f"Procesando archivo adjunto: {file_path}")
            # Aquí podría ir código para extraer información del archivo
            # y añadirla al contexto de la conversación
        except Exception as e:
            logger.error(f"Error procesando archivo: {str(e)}")