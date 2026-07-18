from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Dict, Optional, List
from dotenv import load_dotenv
import os
import logging

# Configurar logging básico para esta clase
logger = logging.getLogger(__name__)

# Cargar variables de entorno desde .env
load_dotenv()

class Settings(BaseSettings):
    # Versión de la aplicación
    APP_VERSION: str = "1.1.0"
    
    # Azure AI Foundry model deployment (with Azure OpenAI-compatible settings)
    OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    AZURE_OPENAI_DEPLOYMENT_NAME: str = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4000"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))

    # Configuración de LangChain
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME: str = os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME", "text-embedding-ada-002")
    USE_LANGCHAIN: bool = os.getenv("USE_LANGCHAIN", "true").lower() == "true"
    LANGCHAIN_VECTORSTORE_DIR: str = os.getenv("LANGCHAIN_VECTORSTORE_DIR", "data/vectorstores")
    LANGCHAIN_CHUNK_SIZE: int = int(os.getenv("LANGCHAIN_CHUNK_SIZE", "1000"))
    LANGCHAIN_CHUNK_OVERLAP: int = int(os.getenv("LANGCHAIN_CHUNK_OVERLAP", "200"))

    # Directorios del proyecto
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    PDF_DIR: Path = BASE_DIR / 'Manuales'
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # Configuración del chatbot
    SYSTEM_PROMPT: str = """
    Eres un asistente IA de soporte técnico especializado en manuales técnicos y documentación de producto. Tu función es ayudar al personal de soporte con problemas técnicos, diagnóstico inicial y uso de manuales.
    [Resto del prompt omitido por brevedad]
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
    CONTEXT_WINDOW_MESSAGES: int = int(os.getenv("CONTEXT_WINDOW_MESSAGES", "15"))

    # Configuración de la aplicación
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    ALLOWED_HOSTS: List[str] = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,::1,testserver").split(",")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Archivos permitidos
    ALLOWED_EXTENSIONS: List[str] = [
        "jpg", "jpeg", "png", "gif", "bmp",
        "pdf", "doc", "docx", "txt",
        "mp4", "avi", "mov", "wmv",
        "mp3", "wav", "m4a"
    ]
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB por defecto
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'allow'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.OPENAI_API_KEY:
            raise ValueError("No se encontró la clave de API para Azure AI Foundry / Azure OpenAI")
        if not self.AZURE_OPENAI_ENDPOINT:
            raise ValueError("No se encontró el endpoint de Azure AI Foundry / Azure OpenAI")
        
        # Asegurar que existen los directorios necesarios
        self.PDF_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(exist_ok=True)
        self.LOGS_DIR.mkdir(exist_ok=True)
        
        # Crear directorio para vectorstores de LangChain si está habilitado
        if self.USE_LANGCHAIN:
            vectorstore_dir = Path(self.LANGCHAIN_VECTORSTORE_DIR)
            vectorstore_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directorio para vectorstores creado: {vectorstore_dir}")
        
        # Registrar inicialización sin exponer variables sensibles
        logger.info("Settings initialized successfully")
