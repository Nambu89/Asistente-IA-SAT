import os
import sys
from pathlib import Path
import logging
import re
import json
import secrets
from fastapi import Form, File, UploadFile, Request, Cookie, Depends
from fastapi.responses import JSONResponse
from app.services.azure_openai_service import AzureOpenAIService
from app.services.azure_ai_foundry_service import AzureAIFoundryService
from app.services.azure_search_service import AzureSearchService
from app.core.settings import Settings
import redis
from typing import Optional

# Configuración
settings = Settings()
ai_foundry_service = AzureAIFoundryService()
search_service = AzureSearchService()  # Mantener como respaldo

# Configuración de Redis (ajusta estos parámetros según tu entorno)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_SSL = os.getenv("REDIS_SSL", "False").lower() == "true"

# Configuración de la sesión
SESSION_EXPIRY = 86400 * 7  # 1 semana en segundos

# Inicializar cliente Redis
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        ssl=REDIS_SSL,
        decode_responses=True
    )
    redis_client.ping()  # Verificar conexión
    redis_available = True
    logging.info("Conexión a Redis establecida correctamente")
except Exception as e:
    logging.error(f"Error al conectar con Redis: {str(e)}")
    logging.warning("Utilizando almacenamiento en memoria como fallback")
    redis_available = False

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Historial de conversación para mantener contexto (fallback si Redis no está disponible)
conversation_history = {}

async def get_session_id(request: Request):
    """
    Obtiene o crea un identificador de sesión para el usuario.
    Busca primero en cookies, luego crea uno nuevo si es necesario.
    """
    session_cookie = request.cookies.get("svan_session")
    
    if session_cookie:
        logger.info(f"Usando session_id existente de cookie: {session_cookie[:8]}...")
        return session_cookie
    
    # Si no hay cookie, creamos un nuevo ID de sesión
    new_session_id = f"session_{secrets.token_hex(16)}"
    logger.info(f"Creando nuevo session_id: {new_session_id[:8]}...")
    
    return new_session_id

async def get_conversation_history(session_id: str):
    """
    Recupera el historial de conversación desde Redis o memoria.
    """
    if redis_available:
        try:
            # Intentar obtener datos de Redis
            history_key = f"svan:chat:{session_id}"
            data = redis_client.get(history_key)
            
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error recuperando datos de Redis: {str(e)}")
    
    # Fallback a memoria o inicializar nuevo historial
    if session_id not in conversation_history:
        conversation_history[session_id] = {
            "current_model": None,
            "messages": []
        }
    
    return conversation_history[session_id]

async def save_conversation_history(session_id: str, history_data):
    """
    Guarda el historial de conversación en Redis y respaldo en memoria.
    """
    # Siempre actualizamos la copia en memoria como fallback
    conversation_history[session_id] = history_data
    
    if redis_available:
        try:
            # Guardar en Redis con expiración
            history_key = f"svan:chat:{session_id}"
            redis_client.set(
                history_key,
                json.dumps(history_data),
                ex=SESSION_EXPIRY
            )
            return True
        except Exception as e:
            logger.error(f"Error guardando datos en Redis: {str(e)}")
            return False
    
    return True

async def chat_endpoint(request: Request = None, message: str = Form(None), attachments: list[UploadFile] = File(None)):
    """
    Endpoint de chat que usa Azure AI Foundry con búsqueda de datos integrada
    """
    try:
        # Respuesta inicial si no hay mensaje
        if not message:
            return {"response": "¡Hola! Soy el Asistente IA de Soporte Técnico. ¿En qué puedo ayudarte hoy?"}
            
        logger.info(f"Mensaje recibido: {message}")
        
        # Obtener o generar ID de sesión
        session_id = await get_session_id(request) if request else "default_session"
        
        # Recuperar historial para esta sesión
        session_data = await get_conversation_history(session_id)
        
        # Crear una respuesta que incluirá la cookie de sesión
        json_response = None
        
        # Buscar patrones de modelo (letras seguidas de números)
        models = re.findall(r'[SWAH][A-Z0-9]{2,}', message.upper())
        logger.info(f"Modelos detectados: {models}")
        
        # Filtrar modelos para evitar falsos positivos (palabras comunes)
        common_words = ['HACE', 'HUELE', 'HOLA', 'HABER', 'SABER', 'SOBRE', 'ALGO']
        filtered_models = [m for m in models if m not in common_words]
        
        # Si se detecta un modelo en este mensaje, actualizamos el modelo actual
        if filtered_models:
            model = filtered_models[0]
            session_data["current_model"] = model
            logger.info(f"Modelo actualizado a: {model}")
        else:
            # Si no se detecta un modelo, usamos el último conocido
            model = session_data["current_model"]
            logger.info(f"Usando modelo previo: {model}")
        
        # Si no hay modelo (ni en este mensaje ni en mensajes anteriores)
        if not model:
            # Si el mensaje actual es solo un problema técnico genérico, preguntar por el modelo
            problem_patterns = [
                r'error', r'no funciona', r'no enciende', r'no hace', r'problema', 
                r'fallo', r'avería', r'huele', r'olor', r'ruido', r'fugas'
            ]
            
            if any(re.search(pattern, message.lower()) for pattern in problem_patterns):
                logger.info("Detectada consulta técnica sin modelo específico")
                
                # Guardar este mensaje en el historial
                session_data["messages"].append({"role": "user", "content": message})
                
                response = "Para poder ayudarte con ese problema técnico, necesito saber el modelo específico del producto. Si lo tienes a mano, comparte la referencia exacta que aparece en la etiqueta o en el manual."
                
                session_data["messages"].append({"role": "assistant", "content": response})
                
                # Guardar el historial actualizado
                await save_conversation_history(session_id, session_data)
                
                # Crear respuesta con cookie
                json_response = {"response": response}
                if request:
                    response_obj = JSONResponse(content=json_response)
                    response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                    return response_obj
                return json_response
            
            # Para conversaciones generales sin modelo
            basic_response = "Por favor, indícame el modelo específico del producto sobre el que necesitas información. Si no lo conoces, comparte una foto de la etiqueta o la referencia que aparece en el manual."
            
            # Crear respuesta con cookie
            json_response = {"response": basic_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
        
        # Mantener historial de conversación
        session_data["messages"].append({"role": "user", "content": message})
        
        # Preparar mensajes para enviar a AI Foundry
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
        ]
        
        # Añadir historial reciente
        recent_messages = session_data["messages"][-10:] if len(session_data["messages"]) > 10 else session_data["messages"]
        messages.extend(recent_messages)
        
        # Llamar a AI Foundry con búsqueda de datos integrada
        logger.info(f"Consultando Azure AI Foundry para el modelo: {model}")
        
        response = await ai_foundry_service.chat_completion_with_data(
            messages=messages,
            query=message,
            model_number=model,
            temperature=0.7,
            max_tokens=2000
        )
        
        if not response:
            error_response = "Lo siento, ha ocurrido un error. Por favor, intenta nuevamente."
            json_response = {"response": error_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                return response_obj
            return json_response
            
        # Guardar respuesta en el historial
        session_data["messages"].append({"role": "assistant", "content": response})
        
        # Guardar historial actualizado
        await save_conversation_history(session_id, session_data)
        
        # Crear respuesta con cookie
        json_response = {"response": response}
        if request:
            response_obj = JSONResponse(content=json_response)
            response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
            return response_obj
        return json_response
        
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}", exc_info=True)
        error_response = {"response": "Lo siento, ha ocurrido un error. Por favor, intenta nuevamente."}
        if request:
            response_obj = JSONResponse(content=error_response)
            return response_obj
        return error_response
