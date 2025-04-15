import os
import sys
from pathlib import Path

# Configurar el PYTHONPATH para que encuentre los módulos
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))
os.environ["PYTHONPATH"] = str(root_dir)

import logging
from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi import HTTPException
import uvicorn
from app.services.azure_search_service import AzureSearchService
from typing import List
import re
# Eliminar la importación de OpenAI
# from openai import OpenAI
# Importar servicios de Azure
from app.services.azure_openai_service import AzureOpenAIService
from app.services.azure_ai_foundry_service import AzureAIFoundryService
#from app.hotfix import chat_endpoint as hotfix_chat
from app.standalone import router as standalone_router
import uuid
from datetime import datetime
from fastapi import Depends
from app.models.feedback_models import Feedback
import json
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO if os.getenv("PRODUCTION") else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Configurar un logger específico para feedback
feedback_logger = logging.getLogger("feedback")
feedback_logger.setLevel(logging.INFO)

# Crear un manejador de archivo para guardar el feedback
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
feedback_handler = logging.FileHandler(log_dir / "feedback.log")
feedback_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
feedback_logger.addHandler(feedback_handler)

# Configurar loggers específicos
for logger_name in ['azure.core.pipeline.policies.http_logging_policy', 'app.services.azure_search_service']:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO if os.getenv("PRODUCTION") else logging.DEBUG)
    logger.propagate = True

# Importar módulos de la aplicación
from app.core.settings import Settings
from app.api.routes import router as api_router
from app.routers import manuals

# Inicializar FastAPI con documentación personalizada
app = FastAPI(
    title="SvanIA - Asistente técnico",
    description="Asistente técnico especializado en productos del Grupo SVAN",
    version="1.0.0",
    docs_url="/api/docs" if not os.getenv("PRODUCTION", False) else None,  # Deshabilitar docs en producción
    redoc_url="/api/redoc" if not os.getenv("PRODUCTION", False) else None  # Deshabilitar redoc en producción
)

# Configuración
settings = Settings()
# Reemplazar OpenAI por servicios de Azure
azure_openai_service = AzureOpenAIService()
ai_foundry_service = AzureAIFoundryService()

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
        "svania.azurewebsites.net",  # Añadido el dominio actual
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

#@app.post("/chat")
# async def chat(request: Request, message: str = Form(None), attachments: list[UploadFile] = File(None)):
#    """Endpoint principal del chat"""
#    return await hotfix_chat(request, message, attachments)

@app.get("/debug/list_all_documents")
async def list_all_documents():
    """Endpoint de diagnóstico para listar todos los documentos en el índice"""
    if os.getenv("PRODUCTION"):
        raise HTTPException(status_code=404, detail="Endpoint no disponible en producción")
    try:
        search_service = AzureSearchService()
        all_docs = await search_service.search_manuals()
        
        return {
            "total_documents": len(all_docs),
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
    return {"status": "OK"}  # Corregido para retornar un diccionario

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
async def submit_feedback(feedback_data: dict):
    try:
        # Añadir timestamp
        feedback_data["timestamp"] = datetime.now().isoformat()
        
        # Guardar en archivo de log como JSON
        feedback_logger.info(json.dumps(feedback_data))
        
        # Log normal para monitoreo
        logger.info(f"Feedback recibido: Rating={feedback_data.get('rating')}, Comment={feedback_data.get('comment', '')[:30]}")
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error al procesar feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar feedback")

if __name__ == "__main__":
    # Determinar el puerto - Azure App Service usa la variable WEBSITES_PORT
    port = int(os.getenv("WEBSITES_PORT", os.getenv("PORT", 8000)))
    
    # Configuración de uvicorn para producción
    workers = int(os.getenv("WEB_CONCURRENCY", "4")) if os.getenv("PRODUCTION") else 1
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info" if os.getenv("PRODUCTION") else "debug",
        access_log=True,
        reload=not os.getenv("PRODUCTION", False)
    )