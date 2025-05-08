from fastapi import APIRouter, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional
from app.services.chat_services import ChatService
import os
import logging
from pathlib import Path

# Importar rutas de LangChain si está disponible
try:
    from app.api.endpoints import langchain
    LANGCHAIN_ROUTES_AVAILABLE = True
    logging.getLogger(__name__).info("Rutas de LangChain disponibles")
except ImportError:
    LANGCHAIN_ROUTES_AVAILABLE = False
    logging.getLogger(__name__).warning("Rutas de LangChain no disponibles")

router = APIRouter()
templates = Jinja2Templates(directory="templates")
chat_service = ChatService()

# Configuración de directorios
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@router.post("/chat")
async def chat_endpoint(
    request: Request,
    message: Optional[str] = Form(None),
    attachments: List[UploadFile] = File(None),
    session_id: Optional[str] = Form(None)
):
    try:
        # Procesar archivos adjuntos si existen
        if attachments:
            for file in attachments:
                # Validar tipo de archivo
                if not file.content_type.startswith(('image/', 'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Tipo de archivo no permitido: {file.content_type}"
                    )
                
                # Validar tamaño (5MB máximo)
                if file.size > 5 * 1024 * 1024:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Archivo demasiado grande: {file.filename}"
                    )
                
                # Guardar archivo
                file_path = UPLOAD_DIR / file.filename
                with open(file_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
                
                # Procesar el archivo con el servicio de chat
                await chat_service.process_attachment(file_path)

        # Generar un ID de sesión si no existe
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
        
        # Procesar mensaje si existe
        if message:
            try:
                response = await chat_service.get_chat_response(message, session_id=session_id)
                
                # Preparar respuesta con información adicional
                response_data = {
                    "response": response,
                    "session_id": session_id  # Devolver el ID de sesión para que el cliente lo guarde
                }
                
                # Añadir el modelo actual si existe
                if chat_service.current_model:
                    response_data["current_model"] = chat_service.current_model
                    
                return JSONResponse(content=response_data)
            except HTTPException as e:
                return JSONResponse(
                    status_code=e.status_code,
                    content={"error": str(e.detail), "session_id": session_id}
                )
        
        return JSONResponse(content={"response": "Archivos procesados correctamente"})

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": e.detail}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error interno del servidor: {str(e)}"}
        )

@router.get("/health")
async def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {"status": "healthy"}
