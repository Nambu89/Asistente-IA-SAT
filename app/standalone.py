# app/standalone.py
import logging
import re
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from app.services.azure_search_service import AzureSearchService
from app.core.settings import Settings
import redis
import json
import secrets
import os
from typing import Optional

# Configuración
settings = Settings()
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

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

# Configurar logging detallado
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Crear router para integrarlo en la aplicación principal
router = APIRouter()

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

@router.post("/fullchat")
async def fullchat(request: Request, message: str = Form(None), attachments: list[UploadFile] = File(None)):
    """
    Endpoint independiente que garantiza enviar el manual completo a OpenAI.
    Este endpoint utiliza GPT-4o y asegura que se lea todo el contenido del manual.
    También mantiene el contexto de la conversación.
    """
    try:
        # Obtener o generar ID de sesión
        session_id = await get_session_id(request) if request else "default_session"
        
        # Recuperar historial para esta sesión
        session_data = await get_conversation_history(session_id)
            
        # Log de inicio
        logger.info("========== INICIO PROCESAMIENTO /fullchat ==========")
        
        if not message:
            return {"response": "¡Hola! Soy el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?"}
            
        logger.info(f"Mensaje recibido: {message}")
        
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
                
                response = "Para poder ayudarte con ese problema técnico, necesito saber el modelo específico del producto. Los modelos comienzan con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
                
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
            basic_response = "Por favor, indícame el modelo específico del producto sobre el que necesitas información. Los modelos comienzan con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
            
            # Crear respuesta con cookie
            json_response = {"response": basic_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
        
        # Inicializar servicio de búsqueda
        search_service = AzureSearchService()
        
        # Buscar el manual
        manual = await search_service.get_manual_by_model(model)
        
        if not manual:
            error_response = f"Lo siento, no he encontrado un manual para el modelo {model}. Por favor, verifica que el código sea correcto."
            json_response = {"response": error_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
            
        # Asegurar que tenemos contenido
        content = manual.get('content')
        if not content:
            error_response = f"He encontrado el manual para {model}, pero no contiene información. Por favor, contacta con soporte técnico."
            json_response = {"response": error_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
            
        # Log del contenido para verificación
        logger.info(f"Contenido recuperado, longitud: {len(content)} caracteres")
        logger.info(f"Primeros 200 caracteres: {content[:200]}")
        logger.info(f"Últimos 200 caracteres: {content[-200:] if len(content) > 200 else content}")
            
        # Determinar marca por la primera letra
        brand_map = {'A': 'ASPES', 'S': 'SVAN', 'W': 'WONDER', 'H': 'HYUNDAI'}
        brand = brand_map.get(model[0], 'Desconocida')
        
        # Diccionario de prefijos para todos los tipos de producto
        product_prefixes = {
            'SGW': 'cocina de gas',
            'SG': 'cocina de gas',
            'I': 'inducción',
            'AI': 'inducción',
            'SI': 'inducción',
            'WI': 'inducción',
            'L': 'lavadora',
            'LS': 'lavadora secadora',
            'LCS': 'lavadora carga superior',
            'C': 'combi/frigorífico',
            'CV': 'congelador vertical',
            'CH': 'congelador horizontal',
            'CVH': 'congelador horeca',
            'F': 'frigorífico',
            'FP': 'frigorífico peltier',
            'H': 'horno',
            'V': 'vitrocerámica',
            'M': 'microondas',
            'MW': 'microondas',
            'MWI': 'microondas integrado',
            'K': 'campana',
            'KG': 'cocina gas',
            'KV': 'cocina vitrocerámica',
            'KI': 'cocina integrada',
            'KMW': 'cocina mixta',
            'CPD': 'campana decorativa',
            'CPE': 'campana extraíble',
            'CPP': 'campana piramidal',
            'CPT': 'campana tipo t',
            'CE': 'calentador estanco',
            'VE': 'ventilación',
            'CA': 'calefactor',
            'CR': 'calefactor radiador',
            'VN': 'vinoteca',
            'J': 'lavavajillas',
            'LV': 'lavavajillas',
            'JI': 'lavavajillas integrado',
            'T': 'termo',
            'TV': 'televisor'
        }
        
        # Determinar tipo de producto a partir del prefijo
        product_type = "electrodoméstico"
        # Ordenar por longitud del prefijo (más largo primero) para evitar coincidencias parciales
        sorted_prefixes = sorted(product_prefixes.items(), key=lambda x: len(x[0]), reverse=True)
        for prefix, type_name in sorted_prefixes:
            if model.startswith(prefix):
                product_type = type_name
                break
        
        # Extraer palabras clave del mensaje del usuario para mejor comprensión
        user_message_lower = message.lower()
        problem_keywords = {
            "chispa": "problemas de ignición, encendido o chispas",
            "no enciende": "problemas de encendido",
            "llama": "problemas con la llama o quemadores",
            "gas": "problemas relacionados con gas o fugas",
            "huele": "problemas de olor a gas u olores extraños",
            "ruido": "problemas de ruidos extraños",
            "error": "códigos de error",
            "fallo": "fallos o averías"
        }
        
        detected_problems = []
        for keyword, description in problem_keywords.items():
            if keyword in user_message_lower:
                detected_problems.append(description)
        
        problem_focus = ""
        if detected_problems:
            problem_focus = "Específicamente, el usuario está preguntando sobre: " + ", ".join(detected_problems)
        
        # MANUAL COMPLETO - Instrucciones mejoradas
        full_manual_context = f"""Modelo actual: {model}
Marca: {brand}
Tipo: {product_type}

INSTRUCCIONES CRÍTICAS:
1. Eres un asistente técnico especializado. Usa ÚNICAMENTE la información del manual técnico proporcionado a continuación.
2. DEBES leer y analizar TODO el manual completo que se proporciona a continuación.
3. ATENCIÓN: Este manual puede contener soluciones para problemas comunes incluso si no están codificados como errores (E1, E2, etc.):
   - Si el usuario menciona problemas como "no hace chispa", "huele a gas", "no enciende", busca estas palabras clave en el manual.
   - Busca secciones como "Troubleshooting", "Problemas y soluciones", "Mantenimiento" o similares.
   - Proporciona soluciones ESPECÍFICAS basadas en el manual para cada problema.
4. Para códigos de error específicos (si existen en este modelo):
   - Busca y lista TODOS los códigos de error mencionados en el manual.
   - Incluye las descripciones EXACTAS de cada código.
5. {problem_focus}
6. IMPORTANTE: Recuerda los detalles de la conversación anterior para mantener el contexto. Si el usuario ya ha mencionado un problema o información técnica, tómalo en cuenta.
7. Si el usuario pregunta sobre un tema técnico o valor específico (como "valor de NTC"), encuentra esta información en el manual y responde con precisión.
8. Usa ÚNICAMENTE información del manual - NO INVENTES ni añadas información que no esté explícitamente en el documento.

MANUAL TÉCNICO COMPLETO:
{content}"""

        # Evitar contextos demasiado largos
        max_context = 100000  # Límite razonable 
        if len(full_manual_context) > max_context:
            logger.warning(f"El contexto es muy largo ({len(full_manual_context)} caracteres). Truncando a {max_context}.")
            full_manual_context = full_manual_context[:max_context]
        
        # Asegurar que sabemos el tamaño exacto
        logger.info(f"Tamaño del contexto final enviado: {len(full_manual_context)} caracteres")
        
        # Obtener historial de conversación reciente - AUMENTADO a 10 mensajes
        recent_history = session_data["messages"][-10:] if session_data["messages"] else []
        
        # Construir mensajes
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": "IMPORTANTE: Tu nombre es Svania, no Svaniano. Eres el Asistente Técnico de SVAN. Tienes la capacidad de analizar imágenes. Cuando los usuarios pregunten si puedes procesar o analizar imágenes, debes responder que SÍ y explicar tus capacidades de análisis visual."},
            # CRUCIAL: Envía el manual completo en un único mensaje
            {"role": "system", "content": full_manual_context}
        ]
        
        # Añadir historial reciente
        messages.extend(recent_history)
        
        # Añadir el mensaje actual del usuario
        messages.append({"role": "user", "content": message})
        
        # Llamar a OpenAI con modelo más potente
        logger.info(f"Enviando solicitud a OpenAI con modelo gpt-4o y {len(messages)} mensajes...")
        response_openai = openai_client.chat.completions.create(
            model="gpt-4o",  # Usar modelo completo, no mini
            messages=messages,
            max_tokens=2000,
            temperature=0.2,  # Baja temperatura para mayor precisión
        )
        
        # Extraer y retornar la respuesta
        response = response_openai.choices[0].message.content.strip()
        logger.info(f"Respuesta generada: {len(response)} caracteres")
        
        # Actualizar historial de conversación
        session_data["messages"].append({"role": "user", "content": message})
        session_data["messages"].append({"role": "assistant", "content": response})
        
        # Limitar tamaño del historial (mantener últimos 20 mensajes - AUMENTADO)
        if len(session_data["messages"]) > 20:
            session_data["messages"] = session_data["messages"][-20:]
        
        # Guardar el historial actualizado
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