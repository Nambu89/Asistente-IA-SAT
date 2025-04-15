# app/services/azure_ai_foundry_service.py
import logging
import time
from typing import List, Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.settings import Settings
from app.services.azure_search_service import AzureSearchService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

class AzureAIFoundryService:
    def __init__(self):
        self.settings = Settings()
        self.api_key = self.settings.OPENAI_API_KEY
        self.endpoint = self.settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
        self.api_version = self.settings.AZURE_OPENAI_API_VERSION
        self.deployment_name = self.settings.AZURE_OPENAI_DEPLOYMENT_NAME
        self.search_service = AzureSearchService()
        self.redis = RedisService()
        self.request_timeout = 60.0  # Timeout en segundos

        if not all([self.api_key, self.endpoint, self.deployment_name]):
            error_msg = "Azure OpenAI credentials not found in environment variables"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initialized AzureAIFoundryService with endpoint: {self.endpoint}, deployment: {self.deployment_name}")
        self.client = httpx.AsyncClient(timeout=self.request_timeout)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def chat_completion_with_data(self, 
                                   messages: List[Dict[str, str]], 
                                   query: str = None,
                                   model_number: str = None,
                                   temperature: float = 0.7, 
                                   max_tokens: int = 2000) -> Optional[str]:
        """
        Obtiene una respuesta del modelo de chat de Azure OpenAI de forma asíncrona con datos de contexto.
        """
        start_time = time.time()
        try:
            # Verificar si hay un modelo especificado para enriquecer el contexto
            if model_number:
                logger.info(f"Buscando información para el modelo: {model_number}")
                
                # Comprobar caché de Redis para este modelo
                cache_key = f"svan:manual:{model_number}"
                manual = None
                
                # Intentar obtener de Redis primero
                if self.redis.connected:
                    manual_json = self.redis.get_json(cache_key)
                    if manual_json:
                        logger.info(f"Manual para {model_number} recuperado de caché Redis")
                        manual = manual_json
                
                # Si no está en caché, buscarlo
                if not manual:
                    manual = await self.search_service.get_manual_by_model(model_number)
                    
                    # Si se encontró, guardar en Redis
                    if manual and self.redis.connected:
                        self.redis.set_json(cache_key, manual, ex=3600)  # 1 hora
                
                if manual and manual.get('content'):
                    content = manual.get('content', '')
                    chinese_chars = ['产品', '名称', '型号', '文件', '编制', '技术', '冷藏', '冷冻']
                    appears_to_be_chinese = any(char in content for char in chinese_chars)
                    
                    if appears_to_be_chinese:
                        logger.warning(f"El manual para {model_number} parece estar en chino o no ser útil")
                        messages.append({
                            "role": "system", 
                            "content": f"Se ha encontrado un manual para el modelo {model_number}, pero parece estar en chino o no contener información útil en español. Por favor, indícale al usuario que el manual técnico parece no estar disponible en español."
                        })
                    else:
                        logger.info(f"Encontrado manual para {model_number}, longitud: {len(content)} caracteres")
                        brand_map = {'A': 'ASPES', 'S': 'SVAN', 'W': 'WONDER', 'H': 'HYUNDAI'}
                        brand = brand_map.get(model_number[0], 'Desconocida')
                        
                        # Limitar tamaño del contenido para reducir tokens
                        max_content_length = min(15000, int(self.settings.MAX_TOKENS or 2000) * 4)
                        if len(content) > max_content_length:
                            content = content[:max_content_length] + "... (Contenido truncado por límite de tamaño)"
                            logger.info(f"Contenido truncado a {max_content_length} caracteres")
                        
                        context_msg = {
                            "role": "system", 
                            "content": f"""Modelo: {model_number}
                            Marca: {brand}
                            Tipo: electrodoméstico

                            Manual técnico:
                            {content}"""
                        }
                        
                        # Insertar contexto después del primer mensaje de sistema
                        has_inserted = False
                        for i in range(len(messages)):
                            if i > 0 and messages[i-1]['role'] == 'system' and messages[i]['role'] != 'system':
                                messages.insert(i, context_msg)
                                has_inserted = True
                                break
                        if not has_inserted:
                            messages.append(context_msg)
                else:
                    logger.warning(f"No se encontró manual para el modelo {model_number}")
                    messages.append({
                        "role": "system", 
                        "content": f"No se encontró información técnica para el modelo {model_number}. Por favor, indícale al usuario que el manual técnico no está disponible."
                    })
            
            logger.info(f"Preparación completada en {time.time() - start_time:.2f}s, enviando solicitud a OpenAI")
            
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key
            }

            body = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 1
            }

            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            
            logger.info(f"Enviando solicitud a Azure OpenAI: {self.deployment_name} con {len(messages)} mensajes")
            
            # Estimar tokens aproximados
            total_tokens = sum(len(msg.get("content", "")) for msg in messages) // 4
            logger.info(f"Tokens estimados: ~{total_tokens}")
            
            # Ajustar timeout basado en el tamaño de la solicitud
            adjusted_timeout = min(120.0, max(30.0, self.request_timeout * (total_tokens / 2000)))
            logger.info(f"Timeout ajustado a {adjusted_timeout:.1f}s")
            
            async with httpx.AsyncClient(timeout=adjusted_timeout) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=body
                )
            
            openai_time = time.time() - start_time
            logger.info(f"Respuesta recibida de OpenAI en {openai_time:.2f}s")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Recibida respuesta de Azure OpenAI con código 200")
                assistant_message = response_data["choices"][0]["message"]["content"]
                
                # Log de uso de tokens si está disponible
                if "usage" in response_data:
                    usage = response_data["usage"]
                    logger.info(f"Uso de tokens: prompt={usage.get('prompt_tokens', 0)}, "
                              f"completion={usage.get('completion_tokens', 0)}, "
                              f"total={usage.get('total_tokens', 0)}")
                
                return assistant_message
            elif response.status_code == 429:
                logger.error(f"Error de límite de cuota: {response.text}")
                return "Lo siento, estamos experimentando una alta demanda en este momento. Por favor, intentalo de nuevo en unos minutos."
            else:
                logger.error(f"Error from Azure OpenAI API: {response.status_code}, {response.text}")
                return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, intentalo de nuevo."
                
        except Exception as e:
            logger.error(f"Error in chat_completion_with_data: {str(e)}", exc_info=True)
            total_time = time.time() - start_time
            logger.error(f"Error después de {total_time:.2f}s")
            return "Lo siento, ha ocurrido un error inesperado. Por favor, intentalo de nuevo."
            
    async def search_manual_by_model(self, model: str) -> Optional[Dict[str, Any]]:
        """
        Busca un manual técnico por modelo.
        """
        logger.info(f"Buscando manual para modelo {model} en AI Foundry")
        return await self.search_service.get_manual_by_model(model)