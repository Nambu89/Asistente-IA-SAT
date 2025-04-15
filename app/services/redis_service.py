"""
Servicio unificado para gestionar conexiones a Redis.
Implementa patrón singleton y manejo de errores.
"""
import os
import redis
import logging
import json
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

class RedisService:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(RedisService, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if self.initialized:
            return
            
        # Configuración desde variables de entorno
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.password = os.getenv("REDIS_PASSWORD", "")
        self.ssl = os.getenv("REDIS_SSL", "False").lower() == "true"
        self.connected = False
        self.client = None
        self.ttl = int(os.getenv("REDIS_TTL", "3600"))  # Default 1 hora
        
        # Intentar conexión inicial
        self._connect()
        self.initialized = True
    
    def _connect(self):
        """Inicializa conexión a Redis con manejo de errores."""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                ssl=self.ssl,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30
            )
            # Verificar conexión
            self.client.ping()
            self.connected = True
            logger.info(f"Conexión a Redis establecida correctamente: {self.host}:{self.port}")
        except Exception as e:
            self.connected = False
            logger.error(f"Error al conectar con Redis: {str(e)}")
    
    def ensure_connection(self):
        """Verifica y restablece la conexión si es necesario."""
        if not self.connected or not self.client:
            self._connect()
        return self.connected
    
    def get(self, key: str) -> Optional[str]:
        """Obtiene un valor de Redis con manejo de errores."""
        if not self.ensure_connection():
            return None
            
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Error al obtener valor de Redis: {str(e)}")
            self.connected = False
            return None
    
    def set(self, key: str, value: str, ex: int = None) -> bool:
        """Establece un valor en Redis con TTL opcional."""
        if not self.ensure_connection():
            return False
            
        try:
            return self.client.set(key, value, ex=ex or self.ttl)
        except Exception as e:
            logger.error(f"Error al establecer valor en Redis: {str(e)}")
            self.connected = False
            return False
    
    def delete(self, key: str) -> bool:
        """Elimina una clave de Redis."""
        if not self.ensure_connection():
            return False
            
        try:
            return self.client.delete(key) > 0
        except Exception as e:
            logger.error(f"Error al eliminar clave de Redis: {str(e)}")
            self.connected = False
            return False
    
    def get_json(self, key: str) -> Optional[Dict]:
        """Obtiene y deserializa un valor JSON de Redis."""
        data = self.get(key)
        if not data:
            return None
            
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"Error deserializando JSON de Redis: {str(e)}")
            return None
    
    def set_json(self, key: str, value: Dict, ex: int = None) -> bool:
        """Serializa y guarda un valor JSON en Redis."""
        try:
            json_data = json.dumps(value)
            return self.set(key, json_data, ex=ex)
        except Exception as e:
            logger.error(f"Error serializando JSON para Redis: {str(e)}")
            return False
    
    def keys(self, pattern: str) -> list:
        """Obtiene claves que coinciden con un patrón."""
        if not self.ensure_connection():
            return []
            
        try:
            return self.client.keys(pattern)
        except Exception as e:
            logger.error(f"Error buscando claves en Redis: {str(e)}")
            self.connected = False
            return []