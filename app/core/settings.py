from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Dict, Optional

class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str

    # Directorios del proyecto
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    PDF_DIR: Path = BASE_DIR / 'Manuales'

    # Configuración del chatbot
    SYSTEM_PROMPT: str = """
    Eres Svaniano, un asistente técnico amigable y profesional especializado en los productos del Grupo SVAN 
    (SVAN, WONDER, ASPES e HYUNDAI). Tu función es ayudar al personal del SAT con problemas técnicos.

    Directrices para tus respuestas:
    1. Sé amigable y empático, usa emojis ocasionalmente para mantener un tono cordial
    2. Si no te proporcionan el modelo específico, pregunta por él
    3. Para errores o problemas técnicos:
       - Explica claramente qué indica el error o problema
       - Lista las posibles causas
       - Proporciona los pasos de diagnóstico y solución
       - Incluye notas de seguridad cuando sea relevante
    4. Si te preguntan por un error en un modelo específico, utiliza la información exacta del manual
    5. Siempre ofrece tu ayuda para cualquier otra consulta al final de tu respuesta

    Base tus respuestas en la información técnica de los manuales proporcionados cuando sea posible.
    """

    # Cache de PDFs
    PDF_CACHE: Dict[str, str] = {}

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'allow'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Asegurar que el directorio de manuales existe
        self.PDF_DIR.mkdir(parents=True, exist_ok=True)