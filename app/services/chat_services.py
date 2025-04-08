import logging
from typing import Optional, List, Tuple
from pathlib import Path
import re
from fastapi import HTTPException
from app.core.settings import Settings
from app.services.azure_search_service import AzureSearchService  # Mantener como respaldo
from app.services.azure_ai_foundry_service import AzureAIFoundryService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.settings = Settings()
        self.ai_foundry = AzureAIFoundryService()
        self.search_service = AzureSearchService()  # Mantener como respaldo
        self.current_model = None
        self.conversation_history = []

    async def get_chat_response(self, message: str) -> str:
        """
        Procesa un mensaje del usuario y retorna una respuesta
        """
        try:
            # Detectar modelo en el mensaje
            model = self._extract_model_from_message(message)
            if model:
                self.current_model = model
            
            # Preparar contexto para el modelo
            context = ""
            if self.current_model:
                # Intentar buscar información del modelo usando AI Foundry primero
                manual = await self.ai_foundry.search_manual_by_model(self.current_model)
                
                # Si no se encuentra en AI Foundry, intentar con Azure Search (respaldo)
                if not manual:
                    manual = await self.search_service.get_manual_by_model(self.current_model)
                
                # Construir el contexto si se encontró información
                if manual and manual.get('content'):
                    brand, product_type = self._get_brand_and_type(self.current_model)
                    context = f"""Modelo: {self.current_model}
Marca: {brand if brand else 'Desconocida'}
Tipo: {product_type if product_type else 'electrodoméstico'}

Manual técnico:
{manual['content']}"""
                else:
                    context = f"No se encontró el manual para el modelo {self.current_model}"
            else:
                context = "No se ha especificado un modelo válido"

            # Mantener historial de conversación
            self.conversation_history.append({"role": "user", "content": message})
            
            # Preparar mensajes para Azure AI Foundry
            messages = [
                {"role": "system", "content": self.settings.SYSTEM_PROMPT},
                {"role": "system", "content": context}
            ]
            messages.extend(self.conversation_history[-5:])  # Últimos 5 mensajes

            # Llamar a Azure AI Foundry con datos del modelo específico
            assistant_response = await self.ai_foundry.chat_completion_with_data(
                messages=messages,
                query=message,  # Usar el mensaje del usuario como consulta para el índice vectorial
                model_number=self.current_model,
                temperature=0.7,
                max_tokens=2000
            )
            
            if not assistant_response:
                raise HTTPException(status_code=500, detail="No se pudo obtener una respuesta del modelo")

            # Guardar respuesta en el historial
            self.conversation_history.append({"role": "assistant", "content": assistant_response})

            return assistant_response

        except Exception as e:
            logger.error(f"Error en get_chat_response: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _extract_model_from_message(self, message: str) -> Optional[str]:
        """
        Extrae el número de modelo del mensaje del usuario
        """
        # Patrones de modelo (S/W/A/H seguido de números y letras)
        patterns = [
            r'[SWAH][A-Z0-9]{2,}[A-Z0-9]*(?:ENF|ENFX|AIDV|AIDVB|DGX|DGN|EX|EDC|PB|DTD|DDTD)?'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            if matches:
                # Filtrar palabras comunes que podrían coincidir por error
                filtered_matches = [m for m in matches if m not in ['HOLA', 'HACE', 'SABE']]
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

    async def process_attachment(self, file_path: Path) -> None:
        """
        Procesa un archivo adjunto
        """
        # Implementación básica
        pass