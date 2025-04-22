import logging
import redis.asyncio as redis
import time
import traceback
from app.core.settings import Settings

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self):
        self.settings = Settings()
        self.client = None
        self.connected = False
        self._initialize()

    def _initialize(self):
        try:
            logger.info(f"Inicializando Redis con host={self.settings.REDIS_HOST}, port={self.settings.REDIS_PORT}")
            
            if not self.settings.REDIS_HOST:
                logger.error("REDIS_HOST no está configurado")
                self.client = None
                return
                
            if not self.settings.REDIS_PASSWORD:
                logger.warning("REDIS_PASSWORD no está configurado, intentando conectar sin contraseña")
            
            self.client = redis.Redis(
                host=self.settings.REDIS_HOST,
                port=self.settings.REDIS_PORT,
                password=self.settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=15
            )
            logger.info("Redis client initialized successfully")
        except Exception as e:
            logger.error(f"Error al inicializar Redis: {str(e)}")
            logger.error(f"Detalles del error: {traceback.format_exc()}")
            self.client = None

    async def ensure_connection(self):
        if self.client is None:
            logger.warning("Redis no está disponible - Operando sin caché")
            self.connected = False
            return False
        try:
            start_time = time.time()
            await self.client.ping()
            elapsed = time.time() - start_time
            
            self.connected = True
            logger.info(f"Conexión con Redis verificada en {elapsed:.2f}s")
            
            try:
                test_key = "redis:test:connection"
                await self.client.set(test_key, "test_value", ex=60)
                test_value = await self.client.get(test_key)
                if test_value == "test_value":
                    logger.info("Operaciones básicas de Redis funcionan correctamente")
                else:
                    logger.warning(f"Valor recuperado de Redis no coincide: {test_value}")
            except Exception as e:
                logger.warning(f"Error en operaciones básicas de Redis: {str(e)}")
                
            return True
        except Exception as e:
            logger.error(f"Error al conectar con Redis: {str(e)}")
            logger.error(f"Detalles del error de conexión: {traceback.format_exc()}")
            self.connected = False
            return False

    async def set(self, key: str, value: str, ex: int = None):
        if not self.connected:
            logger.debug(f"No se puede establecer clave {key} - Redis no disponible")
            return False
        try:
            logger.debug(f"Estableciendo clave en Redis: {key} (TTL: {ex}s)")
            
            start_time = time.time()
            result = await self.client.set(key, value, ex=ex)
            elapsed = time.time() - start_time
            
            if result:
                logger.debug(f"Clave {key} establecida correctamente en {elapsed:.2f}s")
            else:
                logger.warning(f"No se pudo establecer la clave {key} en Redis (result={result})")
                
            return result
        except Exception as e:
            logger.error(f"Error al establecer clave {key} en Redis: {str(e)}")
            logger.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    async def get(self, key: str):
        if not self.connected:
            logger.debug(f"No se puede obtener clave {key} - Redis no disponible")
            return None
        try:
            logger.debug(f"Obteniendo clave de Redis: {key}")
            
            start_time = time.time()
            value = await self.client.get(key)
            elapsed = time.time() - start_time
            
            if value is not None:
                logger.debug(f"Clave {key} obtenida correctamente en {elapsed:.2f}s")
            else:
                logger.debug(f"Clave {key} no encontrada en Redis")
                
            return value
        except Exception as e:
            logger.error(f"Error al obtener clave {key} de Redis: {str(e)}")
            logger.error(f"Detalles del error: {traceback.format_exc()}")
            return None