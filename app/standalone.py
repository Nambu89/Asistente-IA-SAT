# app/standalone.py - Versión mejorada
import logging
import re
import json
import secrets
import time
import base64
import hashlib
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

import redis
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from openai import OpenAI
from PIL import Image

from app.services.azure_search_service import AzureSearchService
from app.services.azure_blob_service import AzureBlobService  # Nuevo servicio para manejar blobs
from app.core.settings import Settings
import os

# Configuración
settings = Settings()
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Configuración de Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_SSL = os.getenv("REDIS_SSL", "False").lower() == "true"

# Configuración de la sesión
SESSION_EXPIRY = 86400 * 14  # 2 semanas en segundos
CONTEXT_WINDOW_MESSAGES = 25  # Mensajes a mantener en el contexto

# Configuración para GPT-4o-mini
GPT_MODEL = "gpt-4o-mini"
MAX_TOKENS = 4000
DEFAULT_TEMPERATURE = 0.7

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

# Inicializar el servicio de blob de Azure
blob_service = AzureBlobService()

async def get_session_id(request: Request) -> str:
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

async def get_conversation_history(session_id: str) -> Dict:
    """
    Recupera el historial de conversación desde Redis o memoria.
    Implementa mecanismos de recuperación y respaldo.
    """
    if redis_available:
        try:
            # Intentar obtener datos de Redis
            history_key = f"svan:chat:{session_id}"
            data = redis_client.get(history_key)
            
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    logger.error(f"Error al decodificar JSON de Redis para sesión {session_id[:8]}")
        except Exception as e:
            logger.error(f"Error recuperando datos de Redis: {str(e)}")
    
    # Fallback a memoria o inicializar nuevo historial
    if session_id not in conversation_history:
        conversation_history[session_id] = {
            "current_model": None,
            "messages": [],
            "context_summary": "",
            "last_summary_time": time.time(),
            "important_details": {},
            "last_active": datetime.now().isoformat()
        }
    
    return conversation_history[session_id]

async def save_conversation_history(session_id: str, history_data: Dict) -> bool:
    """
    Guarda el historial de conversación en Redis y respaldo en memoria.
    Implementa mecanismos de seguridad y verificación.
    """
    # Actualizar timestamp de actividad
    history_data["last_active"] = datetime.now().isoformat()
    
    # Siempre actualizamos la copia en memoria como fallback
    conversation_history[session_id] = history_data
    
    if redis_available:
        try:
            # Guardar en Redis con expiración
            history_key = f"svan:chat:{session_id}"
            # Comprimir contenido antes de guardar si es muy grande
            history_json = json.dumps(history_data)
            if len(history_json) > 500000:  # Si es mayor a 500KB, comprimimos el historial
                # Conservamos solo los mensajes más recientes
                if len(history_data.get("messages", [])) > CONTEXT_WINDOW_MESSAGES * 2:
                    history_data["messages"] = history_data["messages"][-CONTEXT_WINDOW_MESSAGES:]
                    history_json = json.dumps(history_data)
                    logger.info(f"Historia comprimida a {len(history_json)} bytes para sesión {session_id[:8]}")
            
            redis_client.set(
                history_key,
                history_json,
                ex=SESSION_EXPIRY
            )
            return True
        except Exception as e:
            logger.error(f"Error guardando datos en Redis: {str(e)}")
            return False
    
    return True

async def generate_context_summary(messages: List[Dict[str, str]]) -> str:
    """
    Genera un resumen del contexto de la conversación para mantener coherencia.
    """
    if len(messages) < 4:  # Si hay muy pocos mensajes, no es necesario un resumen
        return ""
    
    try:
        # Extraer los últimos N mensajes para resumir
        last_messages = messages[-CONTEXT_WINDOW_MESSAGES:] if len(messages) > CONTEXT_WINDOW_MESSAGES else messages
        
        # Preparar el prompt para el resumen
        summary_prompt = [
            {"role": "system", "content": "Eres un asistente que resume contextos de conversación. Crea un resumen conciso de los puntos clave mencionados en la conversación, incluyendo problemas específicos, modelos de productos, síntomas, soluciones discutidas y cualquier otro detalle importante que debería recordarse para mantener la coherencia."},
            {"role": "user", "content": "Resume esta conversación en un párrafo conciso capturando los detalles más importantes:\n\n" + "\n".join([f"{m['role']}: {m['content']}" for m in last_messages])}
        ]
        
        # Generar el resumen con un modelo más económico
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",  # Modelo más ligero para resumir
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

async def extract_images_from_content(content: str) -> List[Dict[str, str]]:
    """
    Extrae referencias a imágenes del contenido de un manual.
    Retorna una lista de diccionarios con detalles de las imágenes encontradas.
    """
    # Patrones comunes para referencias a figuras en manuales técnicos
    patterns = [
        r'[Ff]ig(?:ura)?\s*\.?\s*(\d+)[^\n.]*',
        r'[Dd]iagrama\s*(\d+)[^\n.]*',
        r'[Ii]magen\s*(\d+)[^\n.]*',
        r'[Ee]squema\s*(\d+)[^\n.]*',
        r'[Ff]igure\s*(\d+)[^\n.]*',
        r'[Dd]iagram\s*(\d+)[^\n.]*',
        r'[Ii]llustration\s*(\d+)[^\n.]*'
    ]
    
    image_references = []
    
    for pattern in patterns:
        matches = re.finditer(pattern, content)
        for match in matches:
            # Extraer contexto alrededor de la referencia a la imagen (50 caracteres antes y después)
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 50)
            context = content[start:end].strip()
            
            # Obtener el número de figura
            figure_number = match.group(1) if len(match.groups()) > 0 else "desconocido"
            
            # Encontrar la descripción de la figura si está disponible
            description = ""
            desc_match = re.search(rf'{match.group(0)}[^\n.]*[:]\s*([^\n.]+)', content[match.start():match.start()+200])
            if desc_match:
                description = desc_match.group(1).strip()
            
            image_references.append({
                "reference": match.group(0),
                "figure_number": figure_number,
                "context": context,
                "description": description
            })
    
    # Eliminar duplicados basados en el número de figura
    unique_references = []
    seen_numbers = set()
    for ref in image_references:
        if ref["figure_number"] not in seen_numbers:
            seen_numbers.add(ref["figure_number"])
            unique_references.append(ref)
    
    return unique_references[:5]  # Limitar a 5 imágenes para no sobrecargar la respuesta

async def search_manual_with_semantic(model: str, query: str = None) -> Dict[str, Any]:
    """
    Búsqueda mejorada de manuales con capacidades semánticas.
    Combina la búsqueda exacta por modelo con la búsqueda semántica basada en la consulta.
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
                # Extraer palabras clave de la consulta
                keywords = query.lower().split()
                content = manual['content']
                
                # Buscar párrafos relevantes
                paragraphs = content.split('\n\n')
                relevant_paragraphs = []
                
                for paragraph in paragraphs:
                    paragraph_lower = paragraph.lower()
                    relevance_score = sum(1 for keyword in keywords if keyword in paragraph_lower)
                    # Dar más peso a párrafos que contienen múltiples palabras clave juntas
                    for i in range(len(keywords)-1):
                        if f"{keywords[i]} {keywords[i+1]}" in paragraph_lower:
                            relevance_score += 3
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
                
                # Extraer referencias a imágenes del manual
                image_references = await extract_images_from_content(content)
                if image_references:
                    manual['image_references'] = image_references
                    logger.info(f"Extraídas {len(image_references)} referencias a imágenes del manual")
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

async def extract_model_from_message(message: str) -> Optional[str]:
    """
    Extrae el número de modelo del mensaje del usuario con lógica mejorada.
    """
    # Patrones de modelo (S/W/A/H seguido de letras y números)
    patterns = [
        r'[SWAH][A-Z0-9]{2,}[0-9]+(?:[A-Z0-9]*(?:ENF|ENFX|AIDV|AIDVB|DGX|DGN|EX|EDC|PB|DTD|DDTD)?)?'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, message.upper())
        if matches:
            # Filtrar falsos positivos, requiriendo al menos un dígito en el modelo
            valid_models = [m for m in matches if re.search(r'[0-9]', m)]
            # Filtrar palabras comunes que podrían coincidir por error
            common_words = ['HOLA', 'HACE', 'SABE', 'HUELE', 'HABER']
            valid_models = [m for m in valid_models if m not in common_words]
            
            if valid_models:
                return valid_models[0]
    
    return None

async def process_images_for_analysis(attachments: List[UploadFile]) -> List[Dict[str, Any]]:
    """
    Procesa las imágenes adjuntadas para análisis con GPT-4o-mini.
    Retorna las imágenes en formato base64 para incluir en el prompt.
    """
    processed_images = []
    
    for attachment in attachments:
        try:
            if attachment.content_type.startswith('image/'):
                content = await attachment.read()
                
                # Procesar la imagen con PIL para optimizar tamaño
                with Image.open(BytesIO(content)) as img:
                    # Redimensionar si es demasiado grande
                    max_dimension = 800
                    if img.width > max_dimension or img.height > max_dimension:
                        img.thumbnail((max_dimension, max_dimension))
                    
                    # Convertir a JPEG con calidad optimizada
                    output = BytesIO()
                    img.convert('RGB').save(output, format='JPEG', quality=75)
                    optimized_content = output.getvalue()
                    
                    # Convertir a base64
                    base64_image = base64.b64encode(optimized_content).decode('utf-8')
                    
                    # Generar un hash único para la imagen
                    image_hash = hashlib.md5(optimized_content).hexdigest()
                    
                    processed_images.append({
                        "filename": attachment.filename,
                        "content_type": "image/jpeg",
                        "base64": base64_image,
                        "hash": image_hash
                    })
                    
                    logger.info(f"Imagen {attachment.filename} procesada para análisis")
        except Exception as e:
            logger.error(f"Error procesando imagen {attachment.filename}: {str(e)}")
    
    return processed_images

def get_brand_and_type(model: str) -> Tuple[str, str]:
    """
    Determina la marca y tipo de producto basado en el modelo.
    """
    # Mapeo de letras iniciales a marcas
    brand_map = {'A': 'ASPES', 'S': 'SVAN', 'W': 'WONDER', 'H': 'HYUNDAI'}
    brand = brand_map.get(model[0].upper(), 'Desconocida')
    
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
    
    # Manejo especial para productos Hyundai
    if model.startswith('HY') or (model.startswith('H') and not model.startswith('HY')):
        # Para modelos que empiezan con HY, usar los primeros 3 caracteres
        if model.startswith('HY'):
            product_code = model[:3]
        # Para modelos que empiezan con H o HL, usar los primeros 2 caracteres
        else:
            product_code = model[:2]
            
        for prefix, type_name in product_prefixes.items():
            if prefix == product_code:
                product_type = type_name
                break
    else:
        # Ordenar por longitud del prefijo (más largo primero) para evitar coincidencias parciales
        sorted_prefixes = sorted(product_prefixes.items(), key=lambda x: len(x[0]), reverse=True)
        # Proceso normal para otras marcas
        for prefix, type_name in sorted_prefixes:
            if model.startswith(prefix):
                product_type = type_name
                break
    
    return brand, product_type

async def check_general_question(message: str) -> bool:
    """
    Detecta si una pregunta es general sobre electrodomésticos y no requiere
    un modelo específico.
    """
    general_question_patterns = [
        r'temperatura', r'normal', r'recomendada', r'estándar', r'media', 
        r'consumo', r'ahorro', r'mantenimiento', r'limpieza', 
        r'general', r'común', r'típico', r'habitual', r'estándar',
        r'cuánto', r'cuanto', r'cómo', r'como', r'mejor', r'cuál', r'cual',
        r'diferencia', r'comparativa', r'vida útil', r'duración',
        r'eficiencia', r'energética', r'consejos', r'tips', r'recomendaciones'
    ]
    
    # Verificar si es una pregunta general sobre electrodomésticos
    return any(re.search(pattern, message.lower()) for pattern in general_question_patterns)

async def is_greeting(message: str) -> bool:
    """
    Detecta si el mensaje es un saludo.
    """
    greetings = ['hola', 'buenas', 'buenos días', 'buenas tardes', 'buenas noches', 
                'saludos', 'hey', 'qué tal', 'que tal', 'hi', 'hello']
    return any(greeting in message.lower() for greeting in greetings)

async def fetch_blob_urls(references: List[Dict]) -> List[Dict]:
    """
    Busca las URLs de las imágenes en Azure Blob Storage basadas en las referencias
    del manual.
    """
    result = []
    if not references:
        return result
        
    try:
        for ref in references:
            # Crear un patrón de búsqueda basado en el número de figura
            figure_number = ref.get("figure_number", "")
            search_pattern = f"fig{figure_number}"
            
            # Buscar en el blob storage
            urls = await blob_service.find_images_by_pattern(search_pattern)
            
            if urls:
                ref["image_urls"] = urls
                result.append(ref)
            else:
                # Intentar con otros patrones si no se encuentra
                alt_patterns = [
                    f"figura{figure_number}",
                    f"figure{figure_number}",
                    f"diag{figure_number}",
                    f"diagram{figure_number}",
                    f"img{figure_number}"
                ]
                
                for pattern in alt_patterns:
                    urls = await blob_service.find_images_by_pattern(pattern)
                    if urls:
                        ref["image_urls"] = urls
                        result.append(ref)
                        break
    except Exception as e:
        logger.error(f"Error buscando imágenes en blob storage: {str(e)}")
    
    return result

@router.post("/fullchat")
async def fullchat(request: Request, message: str = Form(None), attachments: list[UploadFile] = File(None)):
    """
    Endpoint mejorado que implementa el chat completo con manejo robusto de contexto,
    procesamiento de imágenes, y uso del modelo GPT-4o-mini para reducir costos.
    """
    try:
        # Obtener o generar ID de sesión
        session_id = await get_session_id(request) if request else "default_session"
        
        # Recuperar historial para esta sesión
        session_data = await get_conversation_history(session_id)
            
        # Log de inicio
        logger.info(f"========== INICIO PROCESAMIENTO /fullchat SESIÓN: {session_id[:8]} ==========")
        
        if not message and not attachments:
            return {"response": "¡Hola! Soy SvanIA, el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?"}
            
        if message:
            logger.info(f"Mensaje recibido: {message[:100]}" + ("..." if len(message) > 100 else ""))
        
        if attachments:
            logger.info(f"Archivos adjuntos recibidos: {[a.filename for a in attachments]}")
        
        # Crear una respuesta que incluirá la cookie de sesión
        json_response = None
        
        # 1. Procesar las imágenes para análisis si hay archivos adjuntos
        processed_images = []
        if attachments:
            processed_images = await process_images_for_analysis(attachments)
        
        # 2. Extraer el modelo mencionado en el mensaje
        model = None
        if message:
            extracted_model = await extract_model_from_message(message)
            if extracted_model:
                # Si encontramos un nuevo modelo en el mensaje, actualizamos
                model = extracted_model
                # Si teníamos un modelo previo y es diferente, guardamos el cambio
                if session_data.get("current_model") and session_data["current_model"] != model:
                    logger.info(f"Cambiando de modelo: {session_data['current_model']} -> {model}")
                    if "important_details" not in session_data:
                        session_data["important_details"] = {}
                    session_data["important_details"]["previous_model"] = session_data["current_model"]
                
                session_data["current_model"] = model
                logger.info(f"Modelo establecido/actualizado a: {model}")
            else:
                # Si no encontramos modelo en este mensaje, usar el último conocido
                model = session_data.get("current_model")
        else:
            # Si no hay mensaje, intentar usar el modelo guardado
            model = session_data.get("current_model")
        
        # 3. Verificar si necesitamos generar un resumen de contexto
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
        
        # 4. Determinar si podemos responder sin modelo específico
        if not model:
            # Si es un saludo
            if message and await is_greeting(message):
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
            if message and await check_general_question(message):
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
                recent_history = session_data["messages"][-CONTEXT_WINDOW_MESSAGES:] if session_data["messages"] else []
                general_messages.extend(recent_history)
                
                try:
                    # Llamar a OpenAI con GPT-4o-mini
                    logger.info(f"Procesando pregunta general con OpenAI: {message}")
                    response_openai = openai_client.chat.completions.create(
                        model=GPT_MODEL,
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
                    
            # Si no hay modelo, solicitar al usuario que proporcione uno
            if not model:
                basic_response = "Para poder ayudarte de forma más precisa, necesito conocer el modelo específico de tu electrodoméstico. ¿Podrías indicarme el modelo exacto? Debe comenzar con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
                
                # Guardar mensaje en el historial
                if message:
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
        
        # 5. Buscar el manual cuando tenemos un modelo
        manual = await search_manual_with_semantic(model, message)
        
        if not manual:
            error_response = f"Lo siento, no he encontrado un manual para el modelo {model}. Por favor, verifica que el código sea correcto."
            # Guardar mensaje del usuario en el historial
            if message:
                session_data["messages"].append({"role": "user", "content": message})
            session_data["messages"].append({"role": "assistant", "content": error_response})
            await save_conversation_history(session_id, session_data)
            
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
            # Guardar mensaje del usuario en el historial
            if message:
                session_data["messages"].append({"role": "user", "content": message})
            session_data["messages"].append({"role": "assistant", "content": error_response})
            await save_conversation_history(session_id, session_data)
            
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
            
        # Determinar marca y tipo de producto
        brand, product_type = get_brand_and_type(model)
        
        # Extraer palabras clave del mensaje del usuario para mejor comprensión
        problem_focus = ""
        if message:
            user_message_lower = message.lower()
            problem_keywords = {
                "chispa": "problemas de ignición, encendido o chispas",
                "no enciende": "problemas de encendido",
                "llama": "problemas con la llama o quemadores",
                "gas": "problemas relacionados con gas o fugas",
                "huele": "problemas de olor a gas u olores extraños",
                "ruido": "problemas de ruidos extraños",
                "error": "códigos de error",
                "fallo": "fallos o averías",
                "pantalla": "problemas con la pantalla o display",
                "luces": "problemas con las luces o LEDs indicadores",
                "agua": "problemas relacionados con fugas de agua",
                "calor": "problemas relacionados con calentamiento",
                "frío": "problemas relacionados con refrigeración"
            }
            
            detected_problems = []
            for keyword, description in problem_keywords.items():
                if keyword in user_message_lower:
                    detected_problems.append(description)
            
            if detected_problems:
                problem_focus = "Específicamente, el usuario está preguntando sobre: " + ", ".join(detected_problems)
        
        # 6. Si hay referencias a imágenes, buscar las URLs
        image_references = manual.get('image_references', [])
        referenced_images = []
        
        if image_references:
            # Buscar URLs en Azure Blob Storage
            referenced_images = await fetch_blob_urls(image_references)
            if referenced_images:
                logger.info(f"Encontradas {len(referenced_images)} imágenes referenciadas en el manual")
        
        # 7. Construir el contexto del manual con instrucciones mejoradas
        full_manual_context = f"""Modelo actual: {model}
Marca: {brand}
Tipo: {product_type}

INSTRUCCIONES CRÍTICAS:
1. Eres SvanIA, un asistente técnico especializado. Usa ÚNICAMENTE la información del manual técnico proporcionado a continuación.
2. DEBES leer y analizar TODO el manual completo que se proporciona.
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
"""

        # Añadir información sobre imágenes disponibles si existen
        if referenced_images:
            full_manual_context += "\n\nREFERENCIAS A IMÁGENES EN EL MANUAL:\n"
            for i, ref in enumerate(referenced_images, 1):
                full_manual_context += f"{i}. {ref['reference']} - {ref['description']}\n"
            full_manual_context += "\nSi el usuario pregunta por estas figuras o diagramas, puedes indicar que hay imágenes disponibles en el manual y ofrecer mostrarlas."

        # Añadir el contenido completo del manual
        full_manual_context += "\n\nMANUAL TÉCNICO COMPLETO:\n" + content

        # Evitar contextos demasiado largos
        max_context = 100000  # Límite razonable 
        if len(full_manual_context) > max_context:
            logger.warning(f"El contexto es muy largo ({len(full_manual_context)} caracteres). Truncando a {max_context}.")
            full_manual_context = full_manual_context[:max_context]
        
        # Asegurar que sabemos el tamaño exacto
        logger.info(f"Tamaño del contexto final enviado: {len(full_manual_context)} caracteres")
        
        # 8. Obtener historial de conversación reciente
        recent_history = session_data["messages"][-CONTEXT_WINDOW_MESSAGES:] if session_data["messages"] else []
        
        # 9. Construir mensajes para OpenAI
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
        
        # Añadir el manual completo
        messages.append({"role": "system", "content": full_manual_context})
        
        # Añadir historial reciente
        messages.extend(recent_history)
        
        # 10. Preparar el mensaje final del usuario
        if processed_images and message:
            # Mensaje con texto e imágenes
            user_message_content = [
                {"type": "text", "text": message},
                *[{"type": "image_url", "image_url": {"url": f"data:{img['content_type']};base64,{img['base64']}"}} for img in processed_images]
            ]
            messages.append({"role": "user", "content": user_message_content})
            
            # Guardar en el historial (sin las imágenes base64)
            session_data["messages"].append({"role": "user", "content": message + " [Imagen adjunta]"})
        elif processed_images:
            # Solo imágenes
            user_message_content = [
                {"type": "text", "text": "Analiza estas imágenes, por favor."},
                *[{"type": "image_url", "image_url": {"url": f"data:{img['content_type']};base64,{img['base64']}"}} for img in processed_images]
            ]
            messages.append({"role": "user", "content": user_message_content})
            
            # Guardar en el historial (sin las imágenes base64)
            session_data["messages"].append({"role": "user", "content": "[Imagen adjunta]"})
        elif message:
            # Solo texto
            messages.append({"role": "user", "content": message})
            
            # Guardar en el historial
            session_data["messages"].append({"role": "user", "content": message})
        
        # 11. Llamar a OpenAI con GPT-4o-mini
        logger.info(f"Enviando solicitud a OpenAI con modelo {GPT_MODEL}")
        response_openai = openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=DEFAULT_TEMPERATURE,
        )
        
        # 12. Extraer y procesar la respuesta
        response = response_openai.choices[0].message.content.strip()
        logger.info(f"Respuesta generada: {len(response)} caracteres")
        
        # Si hay imágenes referenciadas, procesar la respuesta para incluir información sobre las mismas
        if referenced_images:
            # Comprobar si la respuesta menciona alguna figura o diagrama
            for ref in referenced_images:
                if ref["reference"] in response and "image_urls" in ref:
                    # Si se menciona una figura y tenemos URLs, añadir información sobre disponibilidad
                    figure_info = f"\n\nHay imágenes disponibles para {ref['reference']}. Si deseas verlas, puedes solicitarlas."
                    if figure_info not in response:
                        response += figure_info
                        break  # Solo añadir una vez
        
        # 13. Actualizar historial de conversación
        session_data["messages"].append({"role": "assistant", "content": response})
        
        # 14. Limitar tamaño del historial
        if len(session_data["messages"]) > CONTEXT_WINDOW_MESSAGES * 2:
            session_data["messages"] = session_data["messages"][-CONTEXT_WINDOW_MESSAGES:]
        
        # 15. Guardar el historial actualizado
        await save_conversation_history(session_id, session_data)
        
        # 16. Crear respuesta con cookie
        json_response = {"response": response}
        
        # 17. Si hay imágenes referenciadas, incluir información en la respuesta
        if referenced_images:
            # Filtrar solo las que tienen URLs
            image_data = [
                {
                    "reference": ref["reference"],
                    "description": ref["description"],
                    "urls": ref["image_urls"][:1]  # Limitar a 1 URL por referencia
                }
                for ref in referenced_images
                if "image_urls" in ref and ref["image_urls"]
            ]
            if image_data:
                json_response["has_images"] = True
                json_response["images"] = image_data
        
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

@router.get("/show-image/{image_id}")
async def get_image(image_id: str):
    """
    Endpoint para recuperar una imagen específica de Azure Blob Storage.
    Permite al frontend mostrar imágenes de los manuales técnicos.
    """
    try:
        # Decodificar el ID de la imagen (podría estar codificado por seguridad)
        decoded_id = image_id
        
        # Obtener la URL de la imagen desde Azure Blob Storage
        image_url = await blob_service.get_image_url(decoded_id)
        
        if not image_url:
            return JSONResponse(
                status_code=404,
                content={"error": "Imagen no encontrada"}
            )
            
        # Devolver la URL de la imagen o redirigir directamente
        return JSONResponse(content={"url": image_url})
    except Exception as e:
        logger.error(f"Error recuperando imagen {image_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error al recuperar la imagen"}
        )

@router.post("/request-image")
async def request_image(request: Request, reference: str = Form(...), session_id: str = Form(None)):
    """
    Endpoint para solicitar una imagen específica mencionada en una conversación.
    """
    try:
        # Si no tenemos session_id, intentar obtenerlo de la cookie
        if not session_id:
            session_id = request.cookies.get("svan_session")
            
        if not session_id:
            return JSONResponse(
                status_code=400,
                content={"error": "No se pudo identificar la sesión"}
            )
        
        # Recuperar la sesión
        session_data = await get_conversation_history(session_id)
        current_model = session_data.get("current_model")
        
        if not current_model:
            return JSONResponse(
                status_code=400,
                content={"error": "No hay modelo asociado a esta sesión"}
            )
        
        # Buscar imágenes relacionadas con la referencia
        search_pattern = reference.replace(" ", "").lower()
        
        # Buscar en el blob storage
        image_urls = await blob_service.find_images_by_pattern(search_pattern)
        
        if not image_urls:
            # Intentar patrones alternativos
            alt_patterns = []
            # Extraer números
            numbers = re.findall(r'\d+', reference)
            if numbers:
                fig_num = numbers[0]
                alt_patterns = [
                    f"fig{fig_num}",
                    f"figura{fig_num}",
                    f"figure{fig_num}",
                    f"diagram{fig_num}",
                    f"diagrama{fig_num}",
                    f"img{fig_num}",
                    f"image{fig_num}",
                    f"{current_model.lower()}_fig{fig_num}"
                ]
                
                for pattern in alt_patterns:
                    urls = await blob_service.find_images_by_pattern(pattern)
                    if urls:
                        image_urls = urls
                        break
        
        if not image_urls:
            return JSONResponse(
                status_code=404,
                content={"error": "No se encontraron imágenes para esta referencia"}
            )
        
        # Registrar la solicitud en el historial
        user_request = f"Solicito ver la imagen {reference}"
        assistant_response = f"Aquí está la imagen solicitada para {reference} del modelo {current_model}."
        
        session_data["messages"].append({"role": "user", "content": user_request})
        session_data["messages"].append({"role": "assistant", "content": assistant_response})
        
        # Guardar el historial actualizado
        await save_conversation_history(session_id, session_data)
        
        return JSONResponse(content={
            "success": True,
            "image_urls": image_urls[:5],  # Limitar a 5 imágenes máximo
            "reference": reference,
            "model": current_model
        })
    except Exception as e:
        logger.error(f"Error procesando solicitud de imagen: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error al procesar la solicitud de imagen"}
        )
                
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
                    
            # Si tenemos imágenes pero no modelo, intentar hacer análisis de la imagen
            if processed_images and not model:
                logger.info("Procesando imágenes sin modelo específico")
                
                # Guardar este mensaje en el historial
                if message:
                    session_data["messages"].append({"role": "user", "content": message if message else "Aquí tienes una imagen para analizar."})
                else:
                    session_data["messages"].append({"role": "user", "content": "Aquí tienes una imagen para analizar."})
                
                # Preparar mensajes para OpenAI con las imágenes
                image_analysis_messages = [
                    {"role": "system", "content": settings.SYSTEM_PROMPT},
                    {"role": "system", "content": """
                    Analiza las imágenes adjuntas en detalle buscando:
                    1. Códigos de error visibles en pantallas o displays
                    2. Modelos de electrodomésticos visibles (busca etiquetas o placas de características)
                    3. Problemas visibles o anomalías en las piezas
                    4. Estado general del aparato
                    5. Si ves un código de error, explica su significado
                    
                    Si identificas un modelo específico, inclúyelo en tu respuesta. Recuerda que el código suele comenzar con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI).
                    """}
                ]
                
                # Añadir resumen del contexto si existe
                if session_data.get("context_summary"):
                    image_analysis_messages.append({"role": "system", "content": f"Contexto de la conversación previa: {session_data['context_summary']}"})
                
                # Añadir el mensaje del usuario
                if message:
                    image_analysis_messages.append({"role": "user", "content": [
                        {"type": "text", "text": message},
                        *[{"type": "image_url", "image_url": {"url": f"data:{img['content_type']};base64,{img['base64']}"}} for img in processed_images]
                    ]})
                else:
                    image_analysis_messages.append({"role": "user", "content": [
                        {"type": "text", "text": "Analiza estas imágenes de electrodomésticos, por favor."},
                        *[{"type": "image_url", "image_url": {"url": f"data:{img['content_type']};base64,{img['base64']}"}} for img in processed_images]
                    ]})
                
                try:
                    # Llamar a OpenAI con GPT-4o-mini para análisis de imágenes
                    logger.info(f"Analizando imágenes con OpenAI")
                    response_openai = openai_client.chat.completions.create(
                        model=GPT_MODEL,
                        messages=image_analysis_messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                    
                    response = response_openai.choices[0].message.content.strip()
                    logger.info(f"Respuesta generada para análisis de imágenes: {len(response)} caracteres")
                    
                    # Extraer posible modelo de la respuesta
                    possible_model = await extract_model_from_message(response)
                    if possible_model:
                        logger.info(f"Modelo extraído de la respuesta: {possible_model}")
                        session_data["current_model"] = possible_model
                        
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
                    logger.error(f"Error analizando imágenes: {str(e)}", exc_info=True)
                    response = "Lo siento, ha ocurrido un error al analizar las imágenes. ¿Podrías intentarlo de nuevo?"
                    
                    # Crear respuesta con cookie
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response