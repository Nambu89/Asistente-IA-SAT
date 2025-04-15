# app/services/azure_ai_foundry_service.py (simplificado)
import json
import logging
import os
from typing import List, Dict, Any, Optional
import requests
from app.core.settings import Settings
from app.services.azure_search_service import AzureSearchService

logger = logging.getLogger(__name__)

class AzureAIFoundryService:
    def __init__(self):
        self.settings = Settings()
        self.api_key = self.settings.OPENAI_API_KEY
        self.endpoint = self.settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
        self.api_version = self.settings.AZURE_OPENAI_API_VERSION
        self.deployment_name = self.settings.AZURE_OPENAI_DEPLOYMENT_NAME
        self.search_service = AzureSearchService()

        if not all([self.api_key, self.endpoint, self.deployment_name]):
            error_msg = "Azure OpenAI credentials not found in environment variables"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initialized AzureAIFoundryService with endpoint: {self.endpoint}, deployment: {self.deployment_name}")

    async def chat_completion_with_data(self, 
                                   messages: List[Dict[str, str]], 
                                   query: str = None,
                                   model_number: str = None,
                                   temperature: float = 0.7, 
                                   max_tokens: int = 2000) -> Optional[str]:
        """
        Obtiene una respuesta del modelo de chat de Azure OpenAI
        """
        try:
            # Si tenemos un modelo, buscar información primero
            if model_number:
                logger.info(f"Buscando información para el modelo: {model_number}")
                manual = await self.search_service.get_manual_by_model(model_number)
                
                if manual and manual.get('content'):
                    # Verificar si el contenido está en chino o no parece ser útil
                    content = manual.get('content', '')
                    
                    # Detectar caracteres chinos comunes
                    chinese_chars = ['产品', '名称', '型号', '文件', '编制', '技术', '冷藏', '冷冻']
                    appears_to_be_chinese = any(char in content for char in chinese_chars)
                    
                    if appears_to_be_chinese:
                        logger.warning(f"El manual para {model_number} parece estar en chino o no ser útil")
                        # Añadir mensaje indicando el problema
                        messages.append({
                            "role": "system", 
                            "content": f"Se ha encontrado un manual para el modelo {model_number}, pero parece estar en chino o no contener información útil en español. Por favor, indícale al usuario que el manual técnico parece no estar disponible en español."
                        })
                    else:
                        logger.info(f"Encontrado manual para {model_number}, longitud: {len(content)} caracteres")
                        
                        # Determinar marca y tipo
                        brand_map = {'A': 'ASPES', 'S': 'SVAN', 'W': 'WONDER', 'H': 'HYUNDAI'}
                        brand = brand_map.get(model_number[0], 'Desconocida')
                        
                        # Añadir información del manual al contexto
                        # Limitar el tamaño para evitar exceder límites de tokens
                        max_content_length = 15000  # Limitar a ~15K caracteres
                        if len(content) > max_content_length:
                            content = content[:max_content_length] + "... (Contenido truncado por límite de tamaño)"
                        
                        context_msg = {
                            "role": "system", 
                            "content": f"""Modelo: {model_number}
                            Marca: {brand}
                            Tipo: electrodoméstico

                            Manual técnico:
                            {content}"""
                        }
                        
                        # Insertar este mensaje como segundo mensaje del sistema
                        has_inserted = False
                        for i in range(len(messages)):
                            if i > 0 and messages[i-1]['role'] == 'system' and messages[i]['role'] != 'system':
                                messages.insert(i, context_msg)
                                has_inserted = True
                                break
                        
                        # Si no se pudo insertar, añadirlo al final
                        if not has_inserted:
                            messages.append(context_msg)
                else:
                    logger.warning(f"No se encontró manual para el modelo {model_number}")
                    # Añadir mensaje indicando que no se encontró el manual
                    messages.append({
                        "role": "system", 
                        "content": f"No se encontró información técnica para el modelo {model_number}. Por favor, indícale al usuario que el manual técnico no está disponible."
                    })
            
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

            # Construir la URL para la API de ChatCompletion
            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            
            logger.info(f"Enviando solicitud a Azure OpenAI: {self.deployment_name} con {len(messages)} mensajes")
            
            response = requests.post(
                url,
                headers=headers,
                json=body
            )
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Recibida respuesta de Azure OpenAI con código 200")
                
                # Extraer el texto de la respuesta
                assistant_message = response_data["choices"][0]["message"]["content"]
                return assistant_message
            elif response.status_code == 429:
                # Error de límite de velocidad
                logger.error(f"Error de límite de cuota: {response.text}")
                return "Lo siento, estamos experimentando una alta demanda en este momento. Por favor, intentalo de nuevo en unos minutos."
            else:
                logger.error(f"Error from Azure OpenAI API: {response.status_code}, {response.text}")
                return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, intentalo de nuevo."
                
        except Exception as e:
            logger.error(f"Error in chat_completion_with_data: {str(e)}", exc_info=True)
            return "Lo siento, ha ocurrido un error inesperado. Por favor, intentalo de nuevo."