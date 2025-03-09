from openai import OpenAI
from app.core.settings import Settings
from app.services.pdf_services import PDFService
from typing import Dict, Optional
import re

class ChatService:
    def __init__(self):
        self.settings = Settings()
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.pdf_service = PDFService()
        self.conversation_context = {
            'current_model': None,
            'current_error': None,
            'history': []
        }

    def _extract_model_number(self, message: str) -> Optional[str]:
        """
        Extrae el número de modelo del mensaje usando varios patrones de búsqueda.
        Busca modelos que empiecen con prefijos conocidos como SC, SL, AI, etc.
        """
        message = message.upper()
        model_prefixes = ['SC', 'SL', 'AI', 'WL']
        
        # Patrones comunes en mensajes
        patterns = [
            r'(?:MODELO|PLACA|LAVADORA)\s+([A-Z0-9]+)',  # Busca "modelo XXX"
            r'([A-Z]{2}\d{4,}[A-Z0-9]*)'  # Busca patrones tipo SC1855...
        ]
        
        # Buscar usando patrones
        for pattern in patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                if any(match.startswith(prefix) for prefix in model_prefixes):
                    return match
        
        # Búsqueda palabra por palabra como respaldo
        words = message.split()
        for word in words:
            if any(word.startswith(prefix) for prefix in model_prefixes):
                return word
                
        return None

    def _extract_error_code(self, message: str) -> Optional[str]:
        """
        Extrae códigos de error del mensaje.
        Busca patrones como 'Error X', 'E0X', 'F0X', etc.
        """
        patterns = [
            r'([Ee]rror|[Ee]|[Ff])\s*(\d+)',
            r'([Ee][Rr][Rr][Oo][Rr])\s*([0-9]+)'
        ]
        
        for pattern in patterns:
            error_match = re.search(pattern, message)
            if error_match:
                return error_match.group(2)
        return None

    async def get_chat_response(self, message: str) -> Dict[str, str]:
        try:
            # Extraer información del mensaje
            new_model = self._extract_model_number(message)
            error_code = self._extract_error_code(message)
            
            # Actualizar contexto
            if new_model:
                self.conversation_context['current_model'] = new_model
            if error_code:
                self.conversation_context['current_error'] = error_code
            
            # Construir prompt del sistema
            system_message = """
            Eres un asistente técnico especializado del Grupo SVAN. Sigue estas pautas:
            1. Da respuestas directas y específicas
            2. Si ya tienes el modelo identificado, no preguntes por él
            3. Usa la información del manual cuando esté disponible
            4. Si necesitas más detalles, pregunta específicamente qué información falta
            5. Mantén un tono profesional y claro
            """
            
            if self.conversation_context['current_model']:
                system_message += f"\nModelo actual: {self.conversation_context['current_model']}"
            
            messages = [
                {"role": "system", "content": system_message}
            ]
            
            # Obtener información del manual
            context = await self.pdf_service.get_relevant_context(message, self.conversation_context['current_model'])
            if context:
                messages.append({"role": "system", "content": f"Información del manual: {context}"})
            
            messages.extend(self.conversation_context['history'][-3:])
            messages.append({"role": "user", "content": message})
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=messages,
                temperature=0.7
            )
            
            assistant_response = response.choices[0].message.content
            
            # Actualizar historial
            self.conversation_context['history'].append(
                {"role": "user", "content": message}
            )
            self.conversation_context['history'].append(
                {"role": "assistant", "content": assistant_response}
            )
            
            return {"response": assistant_response}
            
        except Exception as e:
            return {"error": str(e)}