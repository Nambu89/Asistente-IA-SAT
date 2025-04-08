import json
import logging
import os
from typing import List, Dict, Any, Optional
import requests
from app.core.settings import Settings

logger = logging.getLogger(__name__)

class AzureOpenAIService:
    def __init__(self):
        self.settings = Settings()
        self.api_key = self.settings.AZURE_OPENAI_API_KEY
        self.endpoint = self.settings.AZURE_OPENAI_ENDPOINT.rstrip('/')  # Elimina la barra final si existe
        self.api_version = self.settings.AZURE_OPENAI_API_VERSION
        self.deployment_name = self.settings.AZURE_OPENAI_DEPLOYMENT_NAME

        if not all([self.api_key, self.endpoint, self.deployment_name]):
            error_msg = "Azure OpenAI credentials not found in environment variables"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Initialized AzureOpenAIService with endpoint: {self.endpoint} and deployment: {self.deployment_name}")

    async def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2000) -> Optional[str]:
        """
        Obtiene una respuesta del modelo de chat de Azure OpenAI
        """
        try:
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

            # Construir la URL para la API de ChatCompletion
            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            
            logger.info(f"Sending request to Azure OpenAI: {self.deployment_name}")
            
            response = requests.post(
                url,
                headers=headers,
                json=body
            )
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Received response from Azure OpenAI with status code 200")
                
                # Extraer el texto de la respuesta
                assistant_message = response_data["choices"][0]["message"]["content"]
                return assistant_message
            else:
                logger.error(f"Error from Azure OpenAI API: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error in chat_completion: {str(e)}")
            return None