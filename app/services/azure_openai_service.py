# app/services/azure_openai_service.py
import logging
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.settings import Settings

logger = logging.getLogger(__name__)

class AzureOpenAIService:
    def __init__(self):
        self.settings = Settings()
        self.api_key = self.settings.OPENAI_API_KEY
        self.endpoint = self.settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
        self.api_version = self.settings.AZURE_OPENAI_API_VERSION
        self.deployment_name = self.settings.AZURE_OPENAI_DEPLOYMENT_NAME
        self.max_retries = 3
        
        if not all([self.api_key, self.endpoint, self.deployment_name]):
            error_msg = "Azure OpenAI credentials not found in environment variables"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initialized AzureOpenAIService with endpoint: {self.endpoint} and deployment: {self.deployment_name}")
        self.client = httpx.AsyncClient(timeout=60.0)
        
        # Valor de tokens máximos configurados (con valor por defecto)
        self.max_tokens = int(self.settings.MAX_TOKENS) if hasattr(self.settings, 'MAX_TOKENS') else 2000

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = None) -> Optional[str]:
        """
        Obtiene una respuesta del modelo de chat de Azure OpenAI de forma asíncrona.
        """
        try:
            if max_tokens is None:
                max_tokens = self.max_tokens
                
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key
            }

            body = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 1,
                "stream": False
            }

            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            
            logger.info(f"Sending request to Azure OpenAI: {self.deployment_name}, tokens: {max_tokens}")
            
            response = await self.client.post(
                url,
                headers=headers,
                json=body,
                timeout=90.0  # Timeout extendido para solicitudes grandes
            )
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Received response from Azure OpenAI with status code 200")
                assistant_message = response_data["choices"][0]["message"]["content"]
                
                # Log de tokens utilizados si está disponible en la respuesta
                if "usage" in response_data:
                    usage = response_data["usage"]
                    logger.info(f"Tokens: prompt={usage.get('prompt_tokens', 0)}, "
                                f"completion={usage.get('completion_tokens', 0)}, "
                                f"total={usage.get('total_tokens', 0)}")
                
                return assistant_message
            elif response.status_code == 429:
                logger.error(f"Error de límite de cuota: {response.text}")
                raise Exception(f"Límite de cuota alcanzado: {response.text}")
            else:
                logger.error(f"Error from Azure OpenAI API: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error in chat_completion: {str(e)}")
            return None
    
    async def chat_completion_streaming(self, messages: List[Dict[str, str]], 
                                 temperature: float = 0.7, 
                                 max_tokens: int = None) -> AsyncGenerator[str, None]:
        """
        Versión streaming de chat_completion que devuelve la respuesta incrementalmente.
        """
        if max_tokens is None:
            max_tokens = self.max_tokens
            
        try:
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key,
                "Accept": "text/event-stream"
            }

            body = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 1,
                "stream": True  # Habilitar streaming
            }

            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            
            logger.info(f"Starting streaming request to Azure OpenAI: {self.deployment_name}")
            
            async with self.client.stream("POST", url, headers=headers, json=body, timeout=120.0) as response:
                if response.status_code != 200:
                    error_text = await response.text()
                    logger.error(f"Error en streaming: {response.status_code}, {error_text}")
                    yield f"Error: {response.status_code}"
                    return
                
                # Procesar la respuesta en streaming
                buffer = ""
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                        try:
                            json_str = line[6:]  # Remover 'data: '
                            chunk = json.loads(json_str)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    content = delta["content"]
                                    buffer += content
                                    yield content
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.error(f"Error procesando chunk: {str(e)}")
                            continue
            
            logger.info(f"Finished streaming, total length: {len(buffer)} chars")
            
        except Exception as e:
            logger.error(f"Error in streaming chat completion: {str(e)}")
            yield f"Error: {str(e)}"