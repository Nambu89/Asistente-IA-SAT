"""
main.py - Punto de entrada principal de la aplicación SvanIA

Configura la aplicación FastAPI, middleware, y rutas.
"""
import os
import sys
from pathlib import Path
import time
import cachetools

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
import uvicorn
from typing import List
import re
import json
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure import metrics_exporter

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

# Configurar logging
logging.basicConfig(
    level=logging.INFO if os.getenv("PRODUCTION") else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Reducir nivel de logging para bibliotecas ruidosas
if os.getenv("PRODUCTION", "False").lower() == "true":
    for noisy_logger in ['azure.core', 'httpx', 'httpcore', 'multipart.multipart', 'urllib3', 'asyncio']:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# Logger principal de la aplicación
logger = logging.getLogger("app")

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

# Integrar Application Insights
app_insights_key = os.getenv("APP_INSIGHTS_INSTRUMENTATION_KEY")
if app_insights_key:
    logger.addHandler(AzureLogHandler(connection_string=f'InstrumentationKey={app_insights_key}'))
    feedback_logger.addHandler(AzureLogHandler(connection_string=f'InstrumentationKey={app_insights_key}'))
    exporter = metrics_exporter.new_metrics_exporter(connection_string=f'InstrumentationKey={app_insights_key}')
else:
    logger.warning("No se proporcionó APP_INSIGHTS_INSTRUMENTATION_KEY, monitoreo con Application Insights desactivado")

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
                redis_available = app.state.redis_service.ensure_connection()
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

# Configurar middleware de seguridad
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "svania.azurewebsites.net",
        "b2b.gruposvan.com",
        "*"
    ] if not os.getenv("PRODUCTION", False) else [
        "svanartificialintelligence.azurewebsites.net",
        "svania.azurewebsites.net",
        "b2b.gruposvan.com",
        "*"  # Temporalmente permite todos para diagnosticar
    ]
)

# Configurar CORS
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
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get('/health')
def health_check():
    """Endpoint para verificar el estado del servicio"""
    try:
        checks = {
            "app": "healthy",
            "redis": "initialized" if hasattr(app.state, 'redis_service') and app.state.redis_service.connected else "degraded",
            "search_service": "initialized" if hasattr(app.state, 'search_service') else "missing",
            "openai_service": "initialized" if hasattr(app.state, 'openai_service') else "missing",
            "ai_foundry_service": "initialized" if hasattr(app.state, 'ai_foundry_service') else "missing",
        }
        # Métricas adicionales para monitoreo
        metrics = {
            "services_initialized": all(status == "initialized" for status in checks.values()),
            "timestamp": datetime.now().isoformat()
        }
        
        # Verificar estado general
        is_healthy = all(status in ["initialized", "healthy"] for status in checks.values())
        
        return {
            "status": "healthy" if is_healthy else "degraded",
            "checks": checks,
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"Error en healthcheck: {str(e)}")
        return {
            "status": "degraded",
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
        limit_concurrency = 50
        timeout_keep_alive = 5
        backlog = 2048  # Cola de conexiones pendientes
    else:
        workers = 1
        log_level = "debug"
        reload = False
        limit_concurrency = None
        timeout_keep_alive = 5
        backlog = 1024
    
    logger.info(f"Iniciando servidor con {workers} workers en modo {'producción' if os.getenv('PRODUCTION') else 'desarrollo'}")
    
    # Nota: En Azure App Service, se debe usar Gunicorn como comando de inicio
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