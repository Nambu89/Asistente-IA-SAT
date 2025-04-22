"""
main.py - Punto de entrada principal de la aplicación SvanIA

Configura la aplicación FastAPI, middleware, y rutas.
"""
import os
import sys
from pathlib import Path
import time

# Importación segura de cachetools
try:
    import cachetools
except ImportError:
    # Fallback si cachetools no está disponible
    class LRUCache(dict):
        def __init__(self, maxsize=128, *args, **kwargs):
            self.maxsize = maxsize
            super().__init__(*args, **kwargs)
        
        def __setitem__(self, key, value):
            if len(self) >= self.maxsize:
                self.pop(next(iter(self)), None)
            super().__setitem__(key, value)
    
    # Crear un módulo simulado
    class CacheToolsModule:
        def __init__(self):
            self.LRUCache = LRUCache
    
    cachetools = CacheToolsModule()
    print("WARNING: Using simplified cachetools implementation")

# Configurar el PYTHONPATH para que encuentre los módulos
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))
os.environ["PYTHONPATH"] = str(root_dir)

import logging
from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import uvicorn
from typing import List
import re
import json
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager

# Importar servicios y modelos
from app.services.redis_service import RedisService
from app.services.azure_search_service import AzureSearchService
from app.services.azure_openai_service import AzureOpenAIService
from app.services.azure_ai_foundry_service import AzureAIFoundryService
from app.standalone import router as standalone_router
from app.models.feedback_models import Feedback
from app.core.settings import Settings
from app.api.routes import router as api_router
from app.routers import manuals
from dotenv import load_dotenv

load_dotenv()

# Configurar logging (simplificado para Azure)
# Determinar el nivel de logging desde variables de entorno
log_level_name = os.getenv("LOG_LEVEL", "INFO" if os.getenv("PRODUCTION") else "DEBUG")
log_level = getattr(logging, log_level_name.upper())

# Configurar formato de logs
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Configurar logging solo con handler para consola (Azure captura stdout/stderr)
logging.basicConfig(
    level=log_level,
    format=log_format,
    handlers=[
        # Handler para stdout
        logging.StreamHandler(sys.stdout)
    ]
)

# Reducir nivel de logging para bibliotecas ruidosas
if os.getenv("PRODUCTION", "False").lower() == "true":
    for noisy_logger in ['azure.core', 'httpx', 'httpcore', 'multipart.multipart', 'urllib3', 'asyncio']:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# Logger principal de la aplicación
logger = logging.getLogger("app")
logging.getLogger("httpx.client").setLevel(logging.WARNING)

# Configurar un logger específico para feedback
feedback_logger = logging.getLogger("feedback")
feedback_logger.setLevel(logging.INFO)

# Crear un manejador de archivo para guardar el feedback
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
feedback_handler = logging.FileHandler(log_dir / "feedback.log")
feedback_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
feedback_logger.addHandler(feedback_handler)

# Configurar loggers específicos con niveles adecuados
for logger_name in ['azure.core.pipeline.policies.http_logging_policy', 'app.services.azure_search_service']:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO if os.getenv("PRODUCTION") else logging.DEBUG)
    logger.propagate = True

logger.info("Application Insights no está configurado y no se utilizará.")

# Variables globales para servicios (singleton)
settings = Settings()

# Funciones para inicialización y limpieza de recursos
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización al arranque
    await startup()
    
    # Ceder control a FastAPI
    yield
    
    # Limpieza al cierre
    await shutdown()

async def startup():
    """Inicialización asíncrona de servicios y recursos."""
    logger.info("Iniciando servicios de la aplicación...")
    start_time = time.time()
    
    # Inicializar Redis
    redis_service = RedisService()
    app.state.redis_service = redis_service
    
    # Inicializar servicios de forma paralela
    await asyncio.gather(
        initialize_search_service(),
        initialize_openai_service(),
        initialize_ai_foundry_service()
    )
    
    elapsed = time.time() - start_time
    logger.info(f"Servicios inicializados en {elapsed:.2f} segundos")
    
    # Iniciar verificación periódica de salud
    asyncio.create_task(periodic_health_check())

async def shutdown():
    """Limpieza y liberación de recursos."""
    logger.info("Cerrando servicios...")

async def initialize_search_service():
    app.state.search_service = AzureSearchService()
    logger.info("Servicio de búsqueda inicializado")

async def initialize_openai_service():
    app.state.openai_service = AzureOpenAIService()
    logger.info("Servicio de OpenAI inicializado")

async def initialize_ai_foundry_service():
    app.state.ai_foundry_service = AzureAIFoundryService()
    logger.info("Servicio de AI Foundry inicializado")

async def periodic_health_check():
    """Ejecuta verificaciones periódicas de salud de los servicios."""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutos
            
            # Verificar Redis
            if hasattr(app.state, 'redis_service'):
                redis_available = await app.state.redis_service.ensure_connection()
                logger.info(f"Redis disponible: {redis_available}")
            
            # Verificar otros servicios
            logger.info("Verificación periódica de salud completada")
        except Exception as e:
            logger.error(f"Error en verificación periódica: {str(e)}")

# Inicializar FastAPI con documentación personalizada
app = FastAPI(
    title="SvanIA - Asistente técnico",
    description="Asistente técnico especializado en productos del Grupo SVAN",
    version="1.0.0",
    docs_url="/api/docs" if not os.getenv("PRODUCTION", False) else None,
    redoc_url="/api/redoc" if not os.getenv("PRODUCTION", False) else None,
    lifespan=lifespan  # Usar el gestor de contexto para lifecycle events
)

# Middleware para manejar X-Forwarded-Proto y forzar HTTPS en las URLs generadas
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Detectar si estamos en producción (Azure)
        is_production = not (request.url.hostname == 'localhost' or request.url.hostname == '127.0.0.1')
        
        # Comprobar si ya estamos en HTTPS o si hay un proxy que indica HTTPS
        is_https = request.url.scheme == 'https' or request.headers.get("X-Forwarded-Proto") == "https"
        
        # Solo redirigir si estamos en producción, la solicitud es HTTP, y no hay indicación de HTTPS en los encabezados
        if is_production and not is_https and request.url.scheme == 'http':
            # Evitar bucles de redirección comprobando encabezados adicionales
            redirect_count = int(request.headers.get("X-Redirect-Count", "0"))
            if redirect_count < 3:  # Limitar a un máximo de 3 redirecciones
                https_url = str(request.url).replace('http://', 'https://', 1)
                headers = {'Location': https_url, 'X-Redirect-Count': str(redirect_count + 1)}
                return Response(status_code=301, headers=headers)
        
        # Establecer el esquema a HTTPS en producción para las URLs generadas
        if is_production:
            request.scope["scheme"] = "https"
            
        response = await call_next(request)
        return response

# Añadir el middleware para manejar HTTPS
app.add_middleware(HTTPSRedirectMiddleware)

# Configurar middleware de seguridad
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "svania.azurewebsites.net",
        "b2b.gruposvan.com",
        "*"  # Temporalmente para desarrollo
    ] if not os.getenv("PRODUCTION", False) else [
        "svania.azurewebsites.net",
        "b2b.gruposvan.com"
    ]
)

# Configurar CORS (alineado con cors.json)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "https://b2b.gruposvan.com",
        "https://svania.azurewebsites.net"
    ] if not os.getenv("PRODUCTION", False) else [
        "https://b2b.gruposvan.com",
        "https://svania.azurewebsites.net"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    max_age=86400
)

# Agregar compresión Gzip
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory=str(root_dir / "static")), name="static")

# Configurar templates
templates = Jinja2Templates(directory=str(root_dir / "templates"))

# Incluir rutas de la API
app.include_router(api_router)
app.include_router(manuals.router)
app.include_router(standalone_router)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Ruta principal que sirve la interfaz de chat"""
    return templates.TemplateResponse("chat.html", {"request": request})

@app.get("/debug/list_all_documents")
async def list_all_documents():
    """Endpoint de diagnóstico para listar todos los documentos en el índice"""
    if os.getenv("PRODUCTION"):
        raise HTTPException(status_code=404, detail="Endpoint no disponible en producción")
    try:
        start_time = time.time()
        all_docs = await app.state.search_service.search_manuals()
        elapsed = time.time() - start_time
        
        return {
            "total_documents": len(all_docs),
            "time_elapsed_seconds": elapsed,
            "documents": [
                {
                    "name": doc["name"],
                    "modelo": doc.get("modelo", ""),
                    "path": doc.get("path", "")
                }
                for doc in all_docs
            ]
        }
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}", exc_info=True)
        return {"error": str(e)}

@app.get('/health', response_class=JSONResponse)
async def health_check():
    """Endpoint para verificar el estado del servicio."""
    try:
        # Verificar estado de servicios
        services_status = {
            "app": "ok",
            "version": settings.APP_VERSION,
            "timestamp": datetime.now().isoformat(),
            "services": {}
        }
        
        # Verificar Redis si está disponible
        if hasattr(app.state, 'redis_service'):
            try:
                redis_available = await app.state.redis_service.ensure_connection()
                services_status["services"]["redis"] = "ok" if redis_available else "error"
            except Exception as e:
                services_status["services"]["redis"] = f"error: {str(e)}"
        else:
            services_status["services"]["redis"] = "not_initialized"
            
        # Verificar Azure Search
        if hasattr(app.state, 'search_service'):
            try:
                # Verificación simple
                services_status["services"]["azure_search"] = "ok"
            except Exception as e:
                services_status["services"]["azure_search"] = f"error: {str(e)}"
        else:
            services_status["services"]["azure_search"] = "not_initialized"
            
        return services_status
    except Exception as e:
        logger.error(f"Error en health check: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/diagnostico/redis", response_class=JSONResponse)
async def redis_diagnostico():
    """Endpoint para diagnóstico detallado de Redis."""
    try:
        import socket
        import platform
        import subprocess
        
        # Información básica del sistema
        diagnostico = {
            "timestamp": datetime.now().isoformat(),
            "sistema": platform.system(),
            "version": platform.version(),
            "configuracion_redis": {
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "ssl": settings.REDIS_SSL
            },
            "conectividad": {}
        }
        
        # Verificar si el host es resoluble
        try:
            ip_address = socket.gethostbyname(settings.REDIS_HOST)
            diagnostico["conectividad"]["dns_resolucion"] = {
                "status": "ok",
                "ip": ip_address
            }
        except Exception as e:
            diagnostico["conectividad"]["dns_resolucion"] = {
                "status": "error",
                "mensaje": str(e)
            }
        
        # Verificar conectividad TCP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            start_time = time.time()
            result = s.connect_ex((settings.REDIS_HOST, settings.REDIS_PORT))
            connect_time = time.time() - start_time
            s.close()
            
            diagnostico["conectividad"]["tcp_conexion"] = {
                "status": "ok" if result == 0 else "error",
                "codigo_resultado": result,
                "tiempo_conexion": f"{connect_time:.2f}s"
            }
        except Exception as e:
            diagnostico["conectividad"]["tcp_conexion"] = {
                "status": "error",
                "mensaje": str(e)
            }
        
        # Intentar ping al host
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '3', settings.REDIS_HOST]
            ping_result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            
            diagnostico["conectividad"]["ping"] = {
                "status": "ok" if ping_result.returncode == 0 else "error",
                "codigo_resultado": ping_result.returncode,
                "salida": ping_result.stdout[:500]  # Limitar tamaño de la salida
            }
        except Exception as e:
            diagnostico["conectividad"]["ping"] = {
                "status": "error",
                "mensaje": str(e)
            }
        
        # Verificar Redis con la biblioteca
        if hasattr(app.state, 'redis_service'):
            try:
                start_time = time.time()
                redis_available = await app.state.redis_service.ensure_connection()
                redis_time = time.time() - start_time
                
                diagnostico["redis_cliente"] = {
                    "status": "ok" if redis_available else "error",
                    "tiempo_conexion": f"{redis_time:.2f}s",
                    "connected": app.state.redis_service.connected
                }
                
                # Si la conexión fue exitosa, intentar operaciones básicas
                if redis_available:
                    try:
                        test_key = "redis:diagnostico:test"
                        test_value = f"test-{datetime.now().isoformat()}"
                        
                        # Probar SET
                        set_start = time.time()
                        set_result = await app.state.redis_service.client.set(test_key, test_value, ex=60)
                        set_time = time.time() - set_start
                        
                        # Probar GET
                        get_start = time.time()
                        get_result = await app.state.redis_service.client.get(test_key)
                        get_time = time.time() - get_start
                        
                        diagnostico["redis_operaciones"] = {
                            "set": {
                                "status": "ok" if set_result else "error",
                                "tiempo": f"{set_time:.2f}s"
                            },
                            "get": {
                                "status": "ok" if get_result == test_value else "error",
                                "tiempo": f"{get_time:.2f}s",
                                "valor_esperado": test_value,
                                "valor_recibido": get_result
                            }
                        }
                    except Exception as e:
                        diagnostico["redis_operaciones"] = {
                            "status": "error",
                            "mensaje": str(e)
                        }
            except Exception as e:
                diagnostico["redis_cliente"] = {
                    "status": "error",
                    "mensaje": str(e)
                }
        else:
            diagnostico["redis_cliente"] = {
                "status": "error",
                "mensaje": "Redis service not initialized"
            }
        
        return diagnostico
    except Exception as e:
        logger.error(f"Error en diagnóstico de Redis: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get('/debug/logs')
def view_logs():
    """Endpoint para ver los últimos logs de la aplicación"""
    try:
        # Verificar si estamos en producción y si el usuario tiene acceso
        # En un entorno real, deberías implementar autenticación aquí
        
        # Obtener los últimos logs
        log_dir = Path("logs")
        log_files = []
        
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))
        
        # Si no hay archivos de log en el directorio logs, buscar en stdout/stderr
        if not log_files:
            # En Azure App Service, los logs están en /home/LogFiles
            azure_logs = Path("/home/LogFiles")
            if azure_logs.exists():
                log_files.extend(list(azure_logs.glob("*.log")))
                log_files.extend(list(azure_logs.glob("*/*.log")))
        
        logs_data = {}
        
        for log_file in log_files:
            try:
                # Leer las últimas 100 líneas de cada archivo de log
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    logs_data[str(log_file)] = lines[-100:] if len(lines) > 100 else lines
            except Exception as e:
                logs_data[str(log_file)] = [f"Error al leer el archivo: {str(e)}"]
        
        # Añadir información sobre Redis
        if hasattr(app.state, 'redis_service'):
            redis_info = {
                "connected": app.state.redis_service.connected,
                "host": app.state.redis_service.settings.REDIS_HOST,
                "port": app.state.redis_service.settings.REDIS_PORT
            }
            logs_data["redis_info"] = redis_info
        
        # Añadir información sobre el entorno
        logs_data["environment"] = {
            "production": os.getenv("PRODUCTION", "False"),
            "python_version": sys.version,
            "timestamp": datetime.now().isoformat()
        }
        
        return logs_data
    except Exception as e:
        logger.error(f"Error al obtener logs: {str(e)}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Manejadores de errores personalizados
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Manejador personalizado para excepciones HTTP"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Manejador para excepciones generales"""
    logger.error(f"Error no manejado: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "detail": str(exc) if not os.getenv("PRODUCTION") else "Contacte con el administrador"
        }
    )

@app.post("/api/feedback")
async def submit_feedback(feedback_data: dict, background_tasks: BackgroundTasks):
    """Endpoint para enviar feedback del usuario"""
    try:
        feedback_data["timestamp"] = datetime.now().isoformat()
        
        # Procesar feedback en segundo plano para no bloquear la respuesta
        background_tasks.add_task(process_feedback, feedback_data)
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error al procesar feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar feedback")

async def process_feedback(feedback_data: dict):
    """Procesa el feedback en segundo plano."""
    try:
        feedback_logger.info(json.dumps(feedback_data))
        logger.info(f"Feedback recibido: Rating={feedback_data.get('rating')}, Comment={feedback_data.get('comment', '')[:30]}")
    except Exception as e:
        logger.error(f"Error procesando feedback en segundo plano: {str(e)}")

if __name__ == "__main__":
    # Determinar el puerto - Azure App Service usa la variable WEBSITES_PORT
    port = int(os.getenv("WEBSITES_PORT", os.getenv("PORT", 8000)))
    
    # Configuración optimizada de uvicorn para producción
    if os.getenv("PRODUCTION", "False").lower() == "true":
        # Usar 2 x núcleos + 1 para aprovechar mejor los recursos
        num_cores = os.cpu_count() or 1
        workers = min(int(os.getenv("WEB_CONCURRENCY", num_cores * 2 + 1)), num_cores * 4)
        log_level = "info"
        reload = False
        limit_concurrency = 100
        timeout_keep_alive = 5
        backlog = 4096   # Cola de conexiones pendientes
    else:
        workers = 1
        log_level = "debug"
        reload = False
        limit_concurrency = None
        timeout_keep_alive = 5
        backlog = 1024
    
    logger.info(f"Iniciando servidor con {workers} workers en modo {'producción' if os.getenv('PRODUCTION') else 'desarrollo'}")
    
    # Nota: En Azure App Service, se debe usar Gunicorn como comando de inicio (definido en startup.sh)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=log_level,
        access_log=True,
        reload=reload,
        limit_concurrency=limit_concurrency,
        timeout_keep_alive=timeout_keep_alive,
        backlog=backlog
    )