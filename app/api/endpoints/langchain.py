"""
Endpoints específicos para LangChain.

Este módulo proporciona rutas para probar y utilizar las funcionalidades
de LangChain implementadas en el asistente técnico.
"""

import logging
import time
import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.services.langchain_service import LangChainService
from app.core.settings import Settings

# Configurar logging
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(prefix="/langchain", tags=["langchain"])

# Modelos de datos
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    model_detected: Optional[str] = None
    processing_time: float

# Inicializar servicios
settings = Settings()
langchain_service = LangChainService()

@router.post("/chat", response_model=ChatResponse)
async def langchain_chat(request: ChatRequest) -> ChatResponse:
    """
    Endpoint para chatear utilizando LangChain.
    
    Este endpoint procesa un mensaje del usuario y devuelve una respuesta
    utilizando LangChain para mejorar el contexto y la calidad de las respuestas.
    """
    start_time = time.time()
    
    try:
        # Procesar mensaje con LangChain
        response = await langchain_service.get_chat_response(
            message=request.message,
            session_id=request.session_id
        )
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Crear respuesta
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            model_detected=langchain_service.current_model,
            processing_time=processing_time
        )
    
    except Exception as e:
        logger.error(f"Error en langchain_chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al procesar el mensaje: {str(e)}")

@router.post("/chat/stream")
async def langchain_chat_stream(request: ChatRequest):
    """
    Endpoint para chatear utilizando LangChain con respuesta en streaming.
    
    Este endpoint procesa un mensaje del usuario y devuelve una respuesta
    en formato de streaming utilizando LangChain.
    """
    async def event_generator():
        start_time = time.time()
        try:
            # Procesar mensaje con LangChain
            response = await langchain_service.get_chat_response(
                message=request.message,
                session_id=request.session_id
            )
            
            # Calcular tiempo de procesamiento
            processing_time = time.time() - start_time
            
            # Enviar respuesta como evento
            yield json.dumps({
                "data": response,
                "session_id": request.session_id,
                "model_detected": langchain_service.current_model,
                "processing_time": processing_time
            })
            
        except Exception as e:
            logger.error(f"Error en langchain_chat_stream: {str(e)}", exc_info=True)
            yield json.dumps({
                "error": f"Error al procesar el mensaje: {str(e)}"
            })
    
    return EventSourceResponse(event_generator())

@router.get("/status")
async def langchain_status() -> Dict[str, Any]:
    """
    Comprueba el estado de LangChain.
    
    Devuelve información sobre la configuración y el estado de LangChain.
    """
    try:
        status = {
            "available": True,
            "version": "0.3.25",  # Actualizar según la versión instalada
            "embeddings_model": settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME,
            "llm_model": settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            "vectorstore_dir": settings.LANGCHAIN_VECTORSTORE_DIR,
            "chunk_size": settings.LANGCHAIN_CHUNK_SIZE,
            "chunk_overlap": settings.LANGCHAIN_CHUNK_OVERLAP
        }
        return status
    except Exception as e:
        logger.error(f"Error al obtener estado de LangChain: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al obtener estado: {str(e)}")
