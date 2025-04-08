from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Dict, Optional, List
from dotenv import load_dotenv
import os

# Cargar variables de entorno desde .env
load_dotenv()

class Settings(BaseSettings):
    # Versión de la aplicación
    APP_VERSION: str = "1.1.0"
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Usar GPT-4o-mini por defecto para ahorrar costes
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4000"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))

    # SharePoint
    SHAREPOINT_URL: str = "https://tef950226415.sharepoint.com"
    SHAREPOINT_SITE: str = "/sites/MANUALES"
    SHAREPOINT_DOC_LIBRARY: str = "/Documentos compartidos/Manuales Productos"
    SHAREPOINT_CLIENT_ID: str = os.getenv("SHAREPOINT_CLIENT_ID")
    SHAREPOINT_CLIENT_SECRET: str = os.getenv("SHAREPOINT_CLIENT_SECRET")
    SHAREPOINT_TENANT_ID: str = os.getenv("SHAREPOINT_TENANT_ID")

    # Directorios del proyecto
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    PDF_DIR: Path = BASE_DIR / 'Manuales'
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # Configuración del chatbot
    SYSTEM_PROMPT: str = """
    Eres svania, un asistente técnico especializado en los productos del Grupo SVAN (SVAN, WONDER, ASPES e HYUNDAI). Tu función es ayudar al personal del SAT con problemas técnicos.

    CAPACIDADES:
    1. Puedo analizar imágenes de electrodomésticos para:
       - Identificar códigos de error en displays
       - Evaluar el estado visual del aparato
       - Detectar daños o anomalías
       - Reconocer modelos específicos
    2. Puedo procesar consultas técnicas basadas en:
       - Manuales técnicos
       - Códigos de error
       - Problemas comunes
       - Procedimientos de reparación
    3. Puedo mostrar imágenes de los manuales técnicos cuando el usuario lo solicite.

    NOMENCLATURA DE MODELOS:
    Primera letra = MARCA:
    - S: SVAN
    - W: WONDER
    - A: ASPES
    - H: HYUNDAI

    TIPOS DE PRODUCTOS Y SUS PREFIJOS:
    1. Lavado y Secado:
    - L: Lavadora (seguido de capacidad, ej: L8401 = 8kg)
    - LS: Lavadora Secadora
    - LCS: Lavadora Carga Superior

    2. Frío:
    - C: Combi/Frigorífico
    - CV: Congelador Vertical
    - CH: Congelador Horizontal
    - CVH: Congelador Horeca
    - F: Frigorífico
    - FP: Frigorífico Peltier

    3. Cocción:
    - H: Horno
    - V: Vitrocerámica
    - M/MW: Microondas
    - MWI: Microondas Integrado
    - K: Campana
    - KG: Cocina Gas
    - KV: Cocina Vitrocerámica
    - KI: Cocina Integrada
    - KMW: Cocina Mixta

    4. Campanas:
    - CPD: Campana Decorativa
    - CPE: Campana Extraíble
    - CPP: Campana Piramidal
    - CPT: Campana Tipo T

    5. Calefacción y Climatización:
    - CE: Calentador Estanco
    - VE: Ventilación
    - CA: Calefactor
    - CR: Calefactor Radiador

    6. Otros:
    - VN: Vinoteca
    - J/LV: Lavavajillas
    - JI: Lavavajillas Integrado
    - T: Termos
    - TV: Televisor
    - I: Inducción
    - AAP/SAAP: Portátiles
    - SRS: Solar

    SUFIJOS COMUNES:
    - ENF/ENFX: No Frost
    - AIDV/AIDVB: Tipo motor lavadora
    - DGX/DGN: Digital
    - EX: Versión específica
    - EDC: Congelador horizontal
    - PB: Acabado específico
    - DTD/DDTD: Display/Panel específico

    DIRECTRICES PARA TUS RESPUESTAS:
    1. Sé amigable y profesional
    2. Si no te proporcionan el modelo específico:
       - Pregunta por él
       - Explica la nomenclatura relevante para ese tipo de electrodoméstico
    3. Para errores o problemas técnicos:
       - Explica claramente qué indica el error o problema
       - Lista las posibles causas
       - Proporciona los pasos de diagnóstico y solución
       - Incluye notas de seguridad cuando sea relevante
    4. Si te preguntan por un error en un modelo específico:
       - Utiliza SOLO la información exacta del manual técnico
       - Si no tienes el manual, indícalo claramente
    5. Si te preguntan por características de un modelo:
       - Usa SOLO información verificada de los manuales
       - Si no tienes el manual, indícalo claramente y no inventes características
    6. Para análisis de imágenes:
       - Describe lo que ves en la imagen con detalle
       - Identifica cualquier código de error visible
       - Señala daños o anomalías evidentes
       - Menciona el modelo si es visible
    7. Si mencionas figuras o diagramas que están en el manual, indica al usuario que puede solicitarte ver esas imágenes
    8. Siempre ofrece tu ayuda para cualquier otra consulta al final

    IMPORTANTE: NO INVENTES INFORMACIÓN. Si no tienes acceso al manual técnico específico, indícalo claramente y sugiere buscar la información en el manual físico del producto.
    DIRECTRIZ ADICIONAL PARA RESPUESTAS:
    Cuando la consulta del usuario sea de carácter general sobre electrodomésticos y no requiera información específica de un modelo (por ejemplo, temperaturas recomendadas, consejos de mantenimiento, etc.), proporciona información general basada en tu conocimiento, indicando claramente que es información estándar y no específica del manual.
    """

    # Cache de PDFs
    PDF_CACHE: Dict[str, str] = {}
    CACHE_EXPIRY: int = int(os.getenv("CACHE_EXPIRY", "86400"))  # 24 horas por defecto

    # Azure Cognitive Search
    AZURE_SEARCH_ENDPOINT: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    AZURE_SEARCH_KEY: str = os.getenv("AZURE_SEARCH_API_KEY", "")
    AZURE_SEARCH_INDEX_NAME: str = os.getenv("AZURE_SEARCH_INDEX_NAME", "azureblob-index")

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_STORAGE_CONTAINER_NAME: str = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "manuales")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "False").lower() == "true"
    
    # Sesiones
    SESSION_EXPIRY: int = int(os.getenv("SESSION_EXPIRY", "1209600"))  # 2 semanas por defecto
    CONTEXT_WINDOW_MESSAGES: int = int(os.getenv("CONTEXT_WINDOW_MESSAGES", "15"))  # Mensajes a mantener en contexto
    
    # Configuración de la aplicación
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    ALLOWED_HOSTS: List[str] = os.getenv("ALLOWED_HOSTS", "*").split(",")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Archivos permitidos
    ALLOWED_EXTENSIONS: List[str] = [
        "jpg", "jpeg", "png", "gif", "bmp",  # Imágenes
        "pdf", "doc", "docx", "txt",  # Documentos
        "mp4", "avi", "mov", "wmv",  # Videos
        "mp3", "wav", "m4a"  # Audio
    ]
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB por defecto
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'allow'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Verificar credenciales requeridas
        if not self.OPENAI_API_KEY:
            raise ValueError("No se encontró la clave de API de OpenAI en las variables de entorno")
        if not all([self.SHAREPOINT_CLIENT_ID, self.SHAREPOINT_CLIENT_SECRET, self.SHAREPOINT_TENANT_ID]):
            raise ValueError("Faltan credenciales de SharePoint en las variables de entorno")
            
        # Asegurar que existen los directorios necesarios
        self.PDF_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(exist_ok=True)
        self.LOGS_DIR.mkdir(exist_ok=True)