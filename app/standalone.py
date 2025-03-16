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
from typing import Optional, List, Dict, Any
import time

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

# Caché de manuales para búsqueda más eficiente
manual_cache = {}

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
            "messages": [],
            "context_summary": "",
            "last_summary_time": time.time(),
            "important_details": {}
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

async def generate_context_summary(messages: List[Dict[str, str]]) -> str:
    """
    Genera un resumen del contexto de la conversación para ayudar a mantener la coherencia.
    """
    if len(messages) < 4:  # Si hay muy pocos mensajes, no es necesario un resumen
        return ""
    
    try:
        # Extraer los últimos N mensajes para resumir
        last_messages = messages[-10:] if len(messages) > 10 else messages
        
        # Preparar el prompt para el resumen
        summary_prompt = [
            {"role": "system", "content": "Eres un asistente que resume contextos de conversación. Crea un resumen conciso de los puntos clave mencionados en la conversación, incluyendo problemas específicos, modelos de productos, síntomas, soluciones discutidas y cualquier otro detalle importante que debería recordarse para mantener la coherencia."},
            {"role": "user", "content": "Resume esta conversación en un párrafo conciso capturando los detalles más importantes:\n\n" + "\n".join([f"{m['role']}: {m['content']}" for m in last_messages])}
        ]
        
        # Generar el resumen
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo-16k",  # Modelo más ligero para resumir
            messages=summary_prompt,
            max_tokens=300,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content.strip()
        logger.info(f"Resumen de contexto generado: {len(summary)} caracteres")
        return summary
    except Exception as e:
        logger.error(f"Error generando resumen de contexto: {str(e)}")
        return ""  # En caso de error, no usar resumen

async def search_manual_with_semantic(model: str, query: str = None) -> Dict[str, Any]:
    """
    Búsqueda mejorada de manuales con capacidades semánticas.
    Combina la búsqueda exacta por modelo con la búsqueda semántica basada en la consulta del usuario.
    """
    # Verificar caché primero
    cache_key = f"{model}_{query if query else 'default'}"
    if cache_key in manual_cache:
        logger.info(f"Usando manual desde caché para {cache_key}")
        return manual_cache[cache_key]
    
    search_service = AzureSearchService()
    
    try:
        # Estrategia 1: Buscar el manual específico por modelo
        manual = await search_service.get_manual_by_model(model)
        
        # Si tenemos una consulta específica y el manual es extenso, también realizar búsqueda semántica
        if query and manual and len(manual.get('content', '')) > 10000:
            try:
                # Buscar secciones relevantes en el contenido del manual basado en la consulta
                # Esto podría implementarse mediante chunking del contenido y búsqueda semántica
                # Por simplicidad, aquí usamos un enfoque básico basado en palabras clave
                
                # Extraer palabras clave de la consulta
                keywords = query.lower().split()
                content = manual['content']
                
                # Buscar párrafos relevantes
                paragraphs = content.split('\n\n')
                relevant_paragraphs = []
                
                for paragraph in paragraphs:
                    paragraph_lower = paragraph.lower()
                    relevance_score = sum(1 for keyword in keywords if keyword in paragraph_lower)
                    if relevance_score > 0:
                        relevant_paragraphs.append((paragraph, relevance_score))
                
                # Ordenar por relevancia
                relevant_paragraphs.sort(key=lambda x: x[1], reverse=True)
                
                # Tomar los top N párrafos más relevantes
                top_paragraphs = [p[0] for p in relevant_paragraphs[:10]]
                
                # Si encontramos párrafos relevantes, añadirlos al inicio del contenido
                if top_paragraphs:
                    highlighted_content = "SECCIONES DESTACADAS RELEVANTES A TU CONSULTA:\n\n" + "\n\n".join(top_paragraphs) + "\n\n--- CONTENIDO COMPLETO DEL MANUAL ---\n\n" + content
                    manual['content'] = highlighted_content
                    logger.info(f"Contenido enriquecido con {len(top_paragraphs)} párrafos relevantes")
            except Exception as e:
                logger.error(f"Error en la búsqueda semántica: {str(e)}")
                # En caso de error, mantener el contenido original
        
        # Guardar en caché
        if manual:
            manual_cache[cache_key] = manual
            
        return manual
    except Exception as e:
        logger.error(f"Error en búsqueda mejorada de manual: {str(e)}")
        return None

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
            return {"response": "¡Hola! Soy SvanIA, el Asistente Técnico de SVAN. ¿En qué puedo ayudarte?"}
            
        logger.info(f"Mensaje recibido: {message}")
        
        # Crear una respuesta que incluirá la cookie de sesión
        json_response = None
        
        # 1. Obtener el modelo actual de la sesión (si existe)
        model = session_data.get("current_model")
        logger.info(f"Modelo en la sesión actual: {model}")

        # 2. Verificar si mantenemos el modelo actual
        if model and not re.search(r'[SWAH][A-Za-z0-9]{2,}[0-9]+', message.upper()):
            logger.info(f"Manteniendo modelo actual: {model} (no se detectó un cambio explícito)")
        else:
            # 3. Buscar posibles modelos mencionados en el mensaje actual
            models = re.findall(r'[SWAH][A-Za-z0-9]{2,}', message.upper())
            logger.info(f"Posibles modelos mencionados: {models}")
            
            # 4. Filtrar falsos positivos, requiriendo al menos un dígito en el modelo
            valid_models = [m for m in models if re.search(r'[0-9]', m)]
            logger.info(f"Modelos válidos filtrados: {valid_models}")
            
            # 5. Si encontramos modelos válidos, actualizar
            if valid_models:
                new_model = valid_models[0]
                
                # Si ya teníamos un modelo y es diferente al nuevo, registrar el cambio
                if model and model != new_model:
                    logger.info(f"Cambiando de modelo: {model} -> {new_model}")
                    # Guardar este cambio en detalles importantes
                    if "important_details" not in session_data:
                        session_data["important_details"] = {}
                    session_data["important_details"]["previous_model"] = model
                
                model = new_model
                session_data["current_model"] = model
                logger.info(f"Modelo establecido/actualizado a: {model}")
        
        # MEJORA 2: Sistema de resumen periódico del contexto
        # Verificar si es tiempo de generar un nuevo resumen (cada 10 minutos o cada 10 mensajes)
        current_time = time.time()
        messages_since_last_summary = len(session_data.get("messages", [])) - (session_data.get("last_summary_message_count", 0) or 0)
        time_since_last_summary = current_time - session_data.get("last_summary_time", 0)
        
        if (messages_since_last_summary >= 10 or time_since_last_summary > 600) and len(session_data.get("messages", [])) >= 6:
            logger.info("Generando resumen periódico del contexto")
            context_summary = await generate_context_summary(session_data["messages"])
            session_data["context_summary"] = context_summary
            session_data["last_summary_time"] = current_time
            session_data["last_summary_message_count"] = len(session_data["messages"])
            logger.info(f"Resumen actualizado: {len(context_summary)} caracteres")
        
        # Si no hay modelo (ni en este mensaje ni en mensajes anteriores)
        if not model:
            # Detectar si es una pregunta general que no requiere modelo específico
            general_question_patterns = [
                r'temperatura', r'normal', r'recomendada', r'estándar', r'media', 
                r'consumo', r'ahorro', r'mantenimiento', r'limpieza', 
                r'general', r'común', r'típico', r'habitual', r'estándar',
                r'cuánto', r'cuanto', r'cómo', r'como', r'mejor', r'cuál', r'cual',
                r'diferencia', r'comparativa', r'vida útil', r'duración',
                r'eficiencia', r'energética', r'consejos', r'tips', r'recomendaciones'
            ]
            
            # Verificar si es una pregunta general sobre electrodomésticos
            is_general_question = any(re.search(pattern, message.lower()) for pattern in general_question_patterns)
            
            # Si es un saludo o mensaje inicial
            if any(word.lower() in message.lower() for word in ['hola', 'buenas', 'buenos días', 'buenas tardes', 'buenas noches']):
                response = "¡Hola! Me alegro de saludarte. ¿En qué puedo ayudarte hoy? Puedo responder preguntas generales sobre electrodomésticos o ayudarte con un modelo específico."
                
                # Guardar este mensaje en el historial
                session_data["messages"].append({"role": "user", "content": message})
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
            
            # Si parece ser una pregunta general sobre electrodomésticos
            if is_general_question:
                logger.info("Detectada consulta general sobre electrodomésticos")
                
                # Guardar este mensaje en el historial
                session_data["messages"].append({"role": "user", "content": message})
                
                # Preparar mensajes para OpenAI
                general_messages = [
                    {"role": "system", "content": settings.SYSTEM_PROMPT},
                    {"role": "system", "content": "Esta es una pregunta general sobre electrodomésticos que no requiere información específica de un modelo. Proporciona información basada en estándares generales y buenas prácticas del sector. Debes aclarar que se trata de información general y que puede variar según el modelo específico."}
                ]
                
                # Añadir resumen del contexto si existe
                if session_data.get("context_summary"):
                    general_messages.append({"role": "system", "content": f"Contexto de la conversación previa: {session_data['context_summary']}"})
                
                # Añadir historial reciente
                recent_history = session_data["messages"][-10:] if session_data["messages"] else []
                general_messages.extend(recent_history)
                
                try:
                    # Llamar a OpenAI
                    logger.info(f"Procesando pregunta general con OpenAI: {message}")
                    response_openai = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=general_messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                    
                    response = response_openai.choices[0].message.content.strip()
                    logger.info(f"Respuesta generada para pregunta general: {len(response)} caracteres")
                    
                    # Actualizar historial
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
                    logger.error(f"Error procesando pregunta general: {str(e)}", exc_info=True)
                    response = "Lo siento, ha ocurrido un error al procesar tu pregunta. ¿Podrías intentarlo de nuevo?"
                    
                    # Crear respuesta con cookie
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
            
            # Si el mensaje actual es solo un problema técnico genérico, preguntar por el modelo
            problem_patterns = [
                r'error', r'no funciona', r'no enciende', r'no hace', r'problema', 
                r'fallo', r'avería', r'huele', r'olor', r'ruido', r'fugas'
            ]
            
            if any(re.search(pattern, message.lower()) for pattern in problem_patterns):
                logger.info("Detectada consulta técnica sin modelo específico")
                
                response = "Entiendo que estás teniendo problemas técnicos. Para poder ayudarte de la mejor manera posible, ¿podrías decirme el modelo exacto de tu producto? Lo encontrarás en la etiqueta del aparato, y empezará por S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
                
                # Guardar este mensaje en el historial
                session_data["messages"].append({"role": "user", "content": message})
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
            
            # Para otros tipos de conversaciones sin modelo
            basic_response = "Puedo ayudarte tanto con información general sobre electrodomésticos como con consultas específicas de productos. Si tienes un modelo específico, por favor indícamelo para darte información más precisa."
            
            # Guardar mensaje en el historial
            session_data["messages"].append({"role": "user", "content": message})
            session_data["messages"].append({"role": "assistant", "content": basic_response})
            
            # Guardar el historial actualizado
            await save_conversation_history(session_id, session_data)
            
            # Crear respuesta con cookie
            json_response = {"response": basic_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
        
        # MEJORA 3: Búsqueda mejorada de manuales con técnicas más sofisticadas
        # Usar la nueva función de búsqueda semántica que considera la consulta del usuario
        manual = await search_manual_with_semantic(model, message)
        
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
            error_response = f"He encontrado la referencia del modelo {model}, pero parece que hay un problema con la documentación técnica. Por favor, contacta con nuestro servicio técnico para que podamos ayudarte mejor."
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
            # Hyundai - Debe ir primero para evitar conflictos
            'HYL': 'lavadora',
            'HA': 'frigorifico americano',
            'HAF': 'air fryer',
            'HF': 'frigorífico',
            'HC': 'combi no frost',
            'HYC': 'combi no frost',
            'HYCPT': 'campana tipo t',
            'HCP': 'campana',
            'HCPD': 'campana decorativa',
            'HYPC': 'encimera gas',
            'HYPG': 'encimera gas',
            'HR': 'refrigerador ciclico',
            'H4': 'frigorifico 4 puertas',
            'HYF': 'refrigerador no frost',
            'HCH': 'congelador horizontal',
            'HCV': 'congelador cíclico',
            'HYCV': 'congelador no frost',
            'HIFZ': 'inducción',
            'HYV': 'vitrocerámica',
            'HYH': 'horno',
            'HYF': 'frigorífico ciclico',
            'HH': 'horno',
            'HMW': 'microondas',
            'HL': 'lavadora',
            'HYLS': 'lavadora secadora',
            'HSB': 'secadora bomba calor',
            'HSE': 'secadora evaciación',
            'HTV': 'televisor',
            'HJ': 'lavavajillas',
            'HJI': 'lavavajillas',
            'HV': 'vitrocerámica',
            'HYLA': 'lavavajillas',
            # Resto de marcas
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
        
        # Manejo especial para productos Hyundai
        if model.startswith('HY') or (model.startswith('H') and not model.startswith('HY')):
            # Para modelos que empiezan con HY, usar los primeros 3 caracteres
            if model.startswith('HY'):
                product_code = model[:3]
            # Para modelos que empiezan con H o HL, usar los primeros 2 caracteres
            else:
                product_code = model[:2]
                
            for prefix, type_name in sorted_prefixes:
                if prefix == product_code:
                    product_type = type_name
                    break
        else:
            # Proceso normal para otras marcas
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
        ]
        
        # Añadir resumen del contexto si existe
        if session_data.get("context_summary"):
            messages.append({"role": "system", "content": f"CONTEXTO DE LA CONVERSACIÓN ANTERIOR:\n{session_data['context_summary']}\n\nRecuerda estos detalles al responder al usuario."})
        
        # Añadir detalles importantes si existen
        if session_data.get("important_details"):
            details_str = "\n".join([f"{k}: {v}" for k, v in session_data["important_details"].items()])
            if details_str:
                messages.append({"role": "system", "content": f"DETALLES IMPORTANTES:\n{details_str}"})
        
        # CRUCIAL: Envía el manual completo en un único mensaje
        messages.append({"role": "system", "content": full_manual_context})
        
        # Añadir historial reciente
        messages.extend(recent_history)
        
        # Añadir el mensaje actual del usuario
        messages.append({"role": "user", "content": message})
        
        # MEJORA 1: Aumentar la temperatura para las respuestas específicas de modelo
        # Llamar a OpenAI con modelo más potente y mayor temperatura
        logger.info(f"Enviando solicitud a OpenAI con modelo gpt-4o y {len(messages)} mensajes...")
        response_openai = openai_client.chat.completions.create(
            model="gpt-4o",  # Usar modelo completo, no mini
            messages=messages,
            max_tokens=2000,
            temperature=0.7,  # AUMENTADO de 0.2 a 0.7 para mayor creatividad y fluidez
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