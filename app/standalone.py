"""
app/standalone.py - Servicio de chat mejorado con GPT-4o-mini

Este módulo implementa un servicio de chat completo que integra:
- Procesamiento de mensajes de texto
- Manejo de imágenes y archivos adjuntos
- Búsqueda inteligente en manuales técnicos
- Mantenimiento de contexto de conversación
"""
import logging
import re
import json
import secrets
import time
import base64
import hashlib
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime
import aiofiles
import asyncio
import os
from pathlib import Path
from retrying import retry
import traceback

# Importar servicios optimizados
from app.services.redis_service import RedisService
from app.services.azure_search_service import AzureSearchService
from app.services.azure_ai_foundry_service import AzureAIFoundryService
from app.services.azure_openai_service import AzureOpenAIService
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import JSONResponse
from PIL import Image

from app.core.settings import Settings

# Configuración
settings = Settings()

# Constantes (leer desde variables de entorno si es posible)
GPT_MODEL = "gpt-4o-mini"
SMALL_MODEL_FOR_SUMMARIES = "gpt-3.5-turbo"
MAX_TOKENS = int(os.getenv("AZURE_OPENAI_MAX_TOKENS", "800"))
DEFAULT_TEMPERATURE = float(os.getenv("AZURE_OPENAI_TEMPERATURE", "0.7"))
SESSION_EXPIRY = int(os.getenv("SESSION_EXPIRY", "1209600"))  # 2 semanas en segundos por defecto
CONTEXT_WINDOW_MESSAGES = int(os.getenv("CONTEXT_WINDOW_MESSAGES", "25"))  # Mensajes a mantener en el contexto
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "8000"))  # Límite aproximado de tokens para historia
MAX_CONTEXT_LENGTH = int(os.getenv("MAX_CONTEXT_LENGTH", "15000"))  # Caracteres máximos para contexto de manuales

# Configurar logging detallado
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO if os.getenv("PRODUCTION") else logging.DEBUG)

# Directorio para almacenar archivos temporales
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Crear router para integrarlo en la aplicación principal
router = APIRouter()

# Inicializar servicios de forma óptima
redis_service = RedisService()
search_service = AzureSearchService()
ai_foundry_service = AzureAIFoundryService()
openai_service = ai_foundry_service
azure_openai_service = AzureOpenAIService()

# Memoria caché para historial de conversaciones - usada solo como fallback
conversation_history = {}

class SessionManager:
    """Clase para gestionar sesiones y mantener contexto de conversación"""
    
    @staticmethod
    async def get_session_id(request: Request) -> str:
        """
        Obtiene o crea un identificador de sesión para el usuario.
        Busca primero en cookies, luego crea uno nuevo si es necesario.
        """
        session_cookie = request.cookies.get("svan_session")
        
        if session_cookie:
            logger.info(f"Usando session_id existente de cookie: {session_cookie[:8]}...")
            return session_cookie
        
        new_session_id = f"session_{secrets.token_hex(16)}"
        logger.info(f"Creando nuevo session_id: {new_session_id[:8]}...")
        
        return new_session_id
    
    @staticmethod
    async def get_conversation_history(session_id: str) -> Dict:
        """
        Recupera el historial de conversación desde Redis o memoria.
        Implementa mecanismos de recuperación y respaldo.
        """
        history_key = f"svan:chat:{session_id}"
        
        # Intentar obtener de Redis primero
        if redis_service.connected:
            data = redis_service.get_json(history_key)
            if data and isinstance(data, dict) and "messages" in data:
                return data
        
        # Si no está en Redis o hay un error, usar memoria
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
    
    @staticmethod
    async def save_conversation_history(session_id: str, history_data: Dict) -> bool:
        """
        Guarda el historial de conversación en Redis y respaldo en memoria.
        Implementa mecanismos de seguridad y verificación.
        """
        history_data["last_active"] = datetime.now().isoformat()
        
        # Siempre guardar en memoria local como respaldo
        conversation_history[session_id] = history_data.copy()
        
        # Gestionar tamaño máximo de la conversación
        if len(history_data.get("messages", [])) > CONTEXT_WINDOW_MESSAGES * 2:
            # Reducir tamaño si es muy grande
            history_data["messages"] = history_data["messages"][-CONTEXT_WINDOW_MESSAGES:]
        
        # Guardar en Redis si está disponible
        if redis_service.connected:
            # Verificar tamaño del JSON antes de guardar
            try:
                history_key = f"svan:chat:{session_id}"
                return redis_service.set_json(history_key, history_data, ex=SESSION_EXPIRY)
            except Exception as e:
                logger.error(f"Error guardando datos en Redis: {str(e)}")
                return False
        
        return True
    
    @staticmethod
    async def cleanup_old_sessions(background_tasks: BackgroundTasks):
        """Limpia sesiones antiguas para liberar memoria"""
        if redis_service.connected:
            background_tasks.add_task(SessionManager._do_cleanup_sessions)
    
    @staticmethod
    async def _do_cleanup_sessions():
        """Tarea en segundo plano para limpiar sesiones antiguas"""
        try:
            # Buscar sesiones antiguas en Redis
            session_keys = redis_service.keys("svan:chat:*")
            now = datetime.now()
            count = 0
            
            for key in session_keys:
                try:
                    data = redis_service.get_json(key)
                    if not data or "last_active" not in data:
                        continue
                    
                    last_active = datetime.fromisoformat(data["last_active"]) if isinstance(data["last_active"], str) else now
                    days_inactive = (now - last_active).days
                    
                    # Eliminar sesiones inactivas por más de 14 días
                    if days_inactive > 14:
                        redis_service.delete(key)
                        count += 1
                        
                except Exception as e:
                    logger.error(f"Error procesando sesión {key}: {str(e)}")
            
            logger.info(f"Limpieza completada: {count} sesiones eliminadas")
            
            # Limpiar memoria local
            local_count = 0
            for session_id in list(conversation_history.keys()):
                if session_id not in [k.split(":")[-1] for k in session_keys]:
                    del conversation_history[session_id]
                    local_count += 1
            
            if local_count > 0:
                logger.info(f"Limpieza de memoria local: {local_count} sesiones eliminadas")
                
        except Exception as e:
            logger.error(f"Error en limpieza de sesiones: {str(e)}")

class ConversationHandler:
    """Clase para manejar la lógica de conversación"""
    
    @staticmethod
    async def extract_model_from_message(message: str) -> Optional[str]:
        """
        Extrae el número de modelo del mensaje del usuario con lógica mejorada.
        """
        if not message:
            return None
            
        patterns = [
            r'[SWAH][A-Z0-9]{2,}[0-9]+(?:[A-Z0-9]*(?:ENF|ENFX|AIDV|AIDVB|DGX|DGN|EX|EDC|PB|DTD|DDTD)?)?'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            if matches:
                valid_models = [m for m in matches if re.search(r'[0-9]', m)]
                common_words = ['HOLA', 'HACE', 'SABE', 'HUELE', 'HABER', 'SOBRE']
                valid_models = [m for m in valid_models if m not in common_words]
                
                if valid_models:
                    return valid_models[0]
        
        return None
    
    @staticmethod
    async def get_brand_and_type(model: str) -> Tuple[str, str]:
        """
        Determina la marca y tipo de producto basado en el modelo.
        """
        series_map = {'A': 'Serie A', 'S': 'Serie S', 'W': 'Serie W', 'H': 'Serie H'}
        brand = series_map.get(model[0].upper(), 'Serie no identificada')
        
        product_prefixes = {
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
        
        product_type = "electrodoméstico"
        if model.startswith('HY') or (model.startswith('H') and not model.startswith('HY')):
            product_code = model[:3] if model.startswith('HY') else model[:2]
            for prefix, type_name in product_prefixes.items():
                if prefix == product_code:
                    product_type = type_name
                    break
        else:
            sorted_prefixes = sorted(product_prefixes.items(), key=lambda x: len(x[0]), reverse=True)
            for prefix, type_name in sorted_prefixes:
                if model.startswith(prefix):
                    product_type = type_name
                    break
        
        return brand, product_type
    
    @staticmethod
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
        
        return any(re.search(pattern, message.lower()) for pattern in general_question_patterns)
    
    @staticmethod
    async def is_greeting(message: str) -> bool:
        """
        Detecta si el mensaje es un saludo.
        """
        if not message:
            return False
            
        greetings = ['hola', 'buenas', 'buenos días', 'buenas tardes', 'buenas noches', 
                    'saludos', 'hey', 'qué tal', 'que tal', 'hi', 'hello']
        
        message_lower = message.lower()
        return any(greeting in message_lower for greeting in greetings) and len(message_lower.split()) < 5
    
    @staticmethod
    async def is_help_request(message: str) -> bool:
        """
        Detecta si el mensaje es una solicitud de ayuda genérica.
        """
        if not message:
            return False
            
        help_patterns = [
            r'ayuda', r'cómo funciona', r'como funciona', r'qué puedes hacer', 
            r'que puedes hacer', r'instrucciones', r'cómo te uso', r'como te uso'
        ]
        
        return any(re.search(pattern, message.lower()) for pattern in help_patterns)
    
    @staticmethod
    async def generate_context_summary(messages: List[Dict[str, str]]) -> str:
        """
        Genera un resumen del contexto de la conversación para mantener coherencia.
        Usa un modelo más económico para este proceso.
        """
        if len(messages) < 4:
            return ""
        
        try:
            # Crear un resumen más simple y rápido sin usar OpenAI
            topics = set()
            models = set()
            problems = set()
            
            for msg in messages[-10:]:
                content = msg.get('content', '')
                if isinstance(content, str):
                    # Extraer modelos mencionados
                    model_matches = re.findall(r'[SWAH][A-Z0-9]{2,}[0-9]+', content)
                    models.update(model_matches)
                    
                    # Extraer problemas comunes
                    for keyword in ['error', 'fallo', 'problema', 'no funciona', 'reparación', 
                                   'no enciende', 'código', 'alarma', 'pantalla', 'ruido']:
                        if keyword in content.lower():
                            problems.add(keyword)
                    
                    # Extraer temas generales
                    for topic in ['lavado', 'temperatura', 'programa', 'motor', 'placa', 'puerta',
                                 'agua', 'calentamiento', 'instalación', 'componente', 'luz']:
                        if topic in content.lower():
                            topics.add(topic)
            
            summary_parts = []
            if models:
                summary_parts.append(f"Modelos mencionados: {', '.join(models)}")
            if problems:
                summary_parts.append(f"Problemas: {', '.join(problems)}")
            if topics:
                summary_parts.append(f"Temas: {', '.join(topics)}")
                
            return ". ".join(summary_parts) if summary_parts else ""
            
        except Exception as e:
            logger.error(f"Error generando resumen de contexto: {str(e)}")
            return ""

class FileProcessor:
    """Clase para procesar archivos e imágenes"""
    
    @staticmethod
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
                    with Image.open(BytesIO(content)) as img:
                        # Redimensionar para reducir tamaño
                        max_dimension = 800
                        if img.width > max_dimension or img.height > max_dimension:
                            ratio = min(max_dimension / img.width, max_dimension / img.height)
                            new_size = (int(img.width * ratio), int(img.height * ratio))
                            img = img.resize(new_size, Image.LANCZOS)
                        
                        # Optimizar imagen
                        output = BytesIO()
                        img.convert('RGB').save(output, format='JPEG', quality=75, optimize=True)
                        optimized_content = output.getvalue()
                        base64_image = base64.b64encode(optimized_content).decode('utf-8')
                        image_hash = hashlib.md5(optimized_content).hexdigest()
                        
                        processed_images.append({
                            "filename": attachment.filename,
                            "content_type": "image/jpeg",
                            "base64": base64_image,
                            "hash": image_hash
                        })
                        
                        logger.info(f"Imagen {attachment.filename} procesada para análisis ({len(base64_image) // 1024}KB)")
                elif attachment.content_type == 'application/pdf':
                    logger.info(f"PDF detectado: {attachment.filename} - procesamiento pendiente")
            except Exception as e:
                logger.error(f"Error procesando imagen {attachment.filename}: {str(e)}")
        
        return processed_images
    
    @staticmethod
    async def save_uploaded_file(upload_file: UploadFile) -> Optional[Path]:
        """
        Guarda un archivo subido en el directorio temporal y retorna su ruta.
        """
        try:
            ext = Path(upload_file.filename).suffix
            unique_filename = f"{int(time.time())}_{secrets.token_hex(8)}{ext}"
            file_path = TEMP_DIR / unique_filename
            
            async with aiofiles.open(file_path, 'wb') as f:
                content = await upload_file.read()
                await f.write(content)
            
            logger.info(f"Archivo {upload_file.filename} guardado como {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error guardando archivo {upload_file.filename}: {str(e)}")
            return None

@router.post("/fullchat")
async def fullchat(
    request: Request, 
    message: str = Form(None), 
    attachments: list[UploadFile] = File(None),
    background_tasks: BackgroundTasks = None
):
    """
    Endpoint mejorado que implementa el chat completo con manejo robusto de contexto
    y procesamiento de imágenes adjuntadas por el usuario.
    """
    start_time = time.time()
    try:
        session_id = await SessionManager.get_session_id(request) if request else "default_session"
        session_data = await SessionManager.get_conversation_history(session_id)
        
        # Programar limpieza de sesiones antiguas ocasionalmente (1 de cada 100 solicitudes)
        if background_tasks and (int(time.time()) % 100 == 0):
            await SessionManager.cleanup_old_sessions(background_tasks)
            
        logger.info(f"========== INICIO PROCESAMIENTO /fullchat SESIÓN: {session_id[:8]} ==========")
        
        if not message and not attachments:
            return {"response": "¡Hola! Soy el Asistente IA de Soporte Técnico. ¿En qué puedo ayudarte hoy?"}
            
        if message:
            logger.info(f"Mensaje recibido: {message[:100]}" + ("..." if len(message) > 100 else ""))
        
        if attachments:
            logger.info(f"Archivos adjuntos recibidos: {[a.filename for a in attachments]}")
        
        json_response = None
        
        processed_images = []
        if attachments:
            processed_images = await FileProcessor.process_images_for_analysis(attachments)
        
        model = None
        if message:
            if "modelo es el" in message.lower():
                model_match = re.search(r'(S|W|A|H)\w+', message, re.IGNORECASE)
                if model_match:
                    identified_model = model_match.group(0).upper()
                    session_data["current_model"] = identified_model
                    session_data["messages"].append({"role": "user", "content": message})
                    
                    brand, product_type = await ConversationHandler.get_brand_and_type(identified_model)
                    
                    response = f"Entendido, el modelo {identified_model} de {brand} es un {product_type}. Por favor, indícame específicamente cuál es el problema que estás experimentando, como si hay algún código de error en el display, si no enciende, o cualquier otro detalle que puedas proporcionar. Esto me ayudará a ofrecerte una solución adecuada."
                    session_data["messages"].append({"role": "assistant", "content": response})
                    await SessionManager.save_conversation_history(session_id, session_data)
                    
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
            
            extracted_model = await ConversationHandler.extract_model_from_message(message)
            if extracted_model:
                model = extracted_model
                if session_data.get("current_model") and session_data["current_model"] != model:
                    logger.info(f"Cambiando de modelo: {session_data['current_model']} -> {model}")
                    if "important_details" not in session_data:
                        session_data["important_details"] = {}
                    session_data["important_details"]["previous_model"] = session_data["current_model"]
                
                session_data["current_model"] = model
                logger.info(f"Modelo establecido/actualizado a: {model}")
            else:
                model = session_data.get("current_model")
        else:
            model = session_data.get("current_model")
            
        # Generar resumen periódicamente para mantener contexto compacto
        current_time = time.time()
        messages_since_last_summary = len(session_data.get("messages", [])) - (session_data.get("last_summary_message_count", 0) or 0)
        time_since_last_summary = current_time - session_data.get("last_summary_time", 0)
        
        if (messages_since_last_summary >= 10 or time_since_last_summary > 600) and len(session_data.get("messages", [])) >= 6:
            logger.info("Generando resumen periódico del contexto")
            context_summary = await ConversationHandler.generate_context_summary(session_data["messages"])
            session_data["context_summary"] = context_summary
            session_data["last_summary_time"] = current_time
            session_data["last_summary_message_count"] = len(session_data["messages"])
            logger.info(f"Resumen actualizado: {len(context_summary)} caracteres")
        
        # Manejar casos sin modelo
        if not model:
            if message and await ConversationHandler.is_greeting(message):
                response = "¡Hola! Me alegro de saludarte. ¿En qué puedo ayudarte hoy? Puedo responder preguntas sobre electrodomésticos, manuales técnicos y ayudarte con problemas específicos a partir de la documentación disponible."
                
                session_data["messages"].append({"role": "user", "content": message})
                session_data["messages"].append({"role": "assistant", "content": response})
                
                await SessionManager.save_conversation_history(session_id, session_data)
                
                json_response = {"response": response}
                if request:
                    response_obj = JSONResponse(content=json_response)
                    response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                    return response_obj
                return json_response
            
            if message and await ConversationHandler.is_help_request(message):
                help_response = """
Soy el Asistente IA de Soporte Técnico. Puedo ayudarte de las siguientes maneras:

1. **Consultas técnicas**: Pregúntame sobre cualquier modelo o referencia específica que aparezca en el equipo o en el manual.

2. **Análisis de imágenes**: Puedes subir fotos de:
   - Códigos de error en displays
   - Electrodomésticos con fallas
   - Piezas o componentes

3. **Manuales técnicos**: Puedo buscar información en los manuales oficiales.

4. **Solución de problemas**: Indícame el modelo y el problema que experimentas para ofrecerte soluciones específicas.

Para obtener la mejor ayuda, menciona siempre el modelo específico del electrodoméstico.
"""
                session_data["messages"].append({"role": "user", "content": message})
                session_data["messages"].append({"role": "assistant", "content": help_response})
                
                await SessionManager.save_conversation_history(session_id, session_data)
                
                json_response = {"response": help_response}
                if request:
                    response_obj = JSONResponse(content=json_response)
                    response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                    return response_obj
                return json_response
                
            if message and await ConversationHandler.check_general_question(message):
                logger.info("Detectada consulta general sobre electrodomésticos")
                
                session_data["messages"].append({"role": "user", "content": message})
                
                general_messages = [
                    {"role": "system", "content": settings.SYSTEM_PROMPT},
                    {"role": "system", "content": "Esta es una pregunta general sobre electrodomésticos que no requiere información específica de un modelo. Proporciona información basada en estándares generales y buenas prácticas del sector. Debes aclarar que se trata de información general y que puede variar según el modelo específico."}
                ]
                
                if session_data.get("context_summary"):
                    general_messages.append({"role": "system", "content": f"Contexto de la conversación previa: {session_data['context_summary']}"})
                
                recent_history = session_data["messages"][-CONTEXT_WINDOW_MESSAGES:] if session_data["messages"] else []
                general_messages.extend(recent_history)
                
                try:
                    # Buscar respuesta en caché para consultas similares
                    cache_key = f"svan:general:{hashlib.md5(message.lower().encode()).hexdigest()[:8]}"
                    cached_response = None
                    
                    if redis_service.connected:
                        cached_response = redis_service.get(cache_key)
                    
                    if cached_response:
                        logger.info(f"Usando respuesta en caché para pregunta general")
                        response = cached_response
                    else:
                        logger.info(f"Procesando pregunta general con OpenAI: {message}")
                        response = await ai_foundry_service.chat_completion_with_data(
                            messages=general_messages,
                            max_tokens=1000,
                            temperature=0.7
                        )
                        
                        # Guardar en caché si es válida
                        if response and redis_service.connected:
                            redis_service.set(cache_key, response, ex=3600)  # 1 hora
                    
                    logger.info(f"Respuesta generada para pregunta general: {len(response)} caracteres")
                    
                    session_data["messages"].append({"role": "assistant", "content": response})
                    
                    await SessionManager.save_conversation_history(session_id, session_data)
                    
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
                    
                except Exception as e:
                    logger.error(f"Error procesando pregunta general: {str(e)}", exc_info=True)
                    response = "Lo siento, ha ocurrido un error al procesar tu pregunta. ¿Podrías intentarlo de nuevo?"
                    
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
                    
            if processed_images and not model:
                logger.info("Procesando imágenes sin modelo específico")
                
                if message:
                    session_data["messages"].append({"role": "user", "content": message if message else "Aquí tienes una imagen para analizar."})
                else:
                    session_data["messages"].append({"role": "user", "content": "Aquí tienes una imagen para analizar."})
                
                image_analysis_messages = [
                    {"role": "system", "content": settings.SYSTEM_PROMPT},
                    {"role": "system", "content": """
                    Analiza las imágenes adjuntas en detalle buscando:
                    1. Códigos de error visibles en pantallas o displays
                    2. Modelos de electrodomésticos visibles (busca etiquetas o placas de características)
                    3. Problemas visibles o anomalías en las piezas
                    4. Estado general del aparato
                    5. Si ves un código de error, explica su significado si lo conoces
                    
                    Si identificas un modelo específico, inclúyelo en tu respuesta. Si aparece una referencia de serie, cítala tal y como se vea en la etiqueta o en el display.
                    """}
                ]
                
                if session_data.get("context_summary"):
                    image_analysis_messages.append({"role": "system", "content": f"Contexto de la conversación previa: {session_data['context_summary']}"})
                
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
                    logger.info(f"Analizando imágenes con OpenAI")
                    response = await ai_foundry_service.chat_completion_with_data(
                        messages=image_analysis_messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                    
                    logger.info(f"Respuesta generada para análisis de imágenes: {len(response)} caracteres")
                    
                    possible_model = await ConversationHandler.extract_model_from_message(response)
                    if possible_model:
                        logger.info(f"Modelo extraído de la respuesta: {possible_model}")
                        session_data["current_model"] = possible_model
                        
                    session_data["messages"].append({"role": "assistant", "content": response})
                    
                    await SessionManager.save_conversation_history(session_id, session_data)
                    
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
                
                except Exception as e:
                    logger.error(f"Error analizando imágenes: {str(e)}", exc_info=True)
                    response = "Lo siento, ha ocurrido un error al analizar las imágenes. ¿Podrías intentarlo de nuevo o proporcionar más detalles?"
                    
                    json_response = {"response": response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
            
            if not model:
                basic_response = "Para poder ayudarte de forma más precisa, necesito conocer el modelo específico de tu electrodoméstico. ¿Podrías indicarme la referencia exacta que aparece en la etiqueta o en el manual?"
                
                if message:
                    session_data["messages"].append({"role": "user", "content": message})
                session_data["messages"].append({"role": "assistant", "content": basic_response})
                
                await SessionManager.save_conversation_history(session_id, session_data)
                
                json_response = {"response": basic_response}
                if request:
                    response_obj = JSONResponse(content=json_response)
                    response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                    return response_obj
                return json_response
        
        # Buscar información del manual (con caché y optimización)
        cache_key = f"svan:manual:{model}"
        manual = None
        manual_from_cache = False
        
        # Comprobar caché primero
        if redis_service.connected:
            manual = redis_service.get_json(cache_key)
            if manual:
                manual_from_cache = True
                logger.info(f"Manual para modelo {model} recuperado de caché")
        
        # Si no está en caché, buscarlo
        if not manual:
            logger.info(f"Buscando manual para modelo {model} (no estaba en caché)")
            try:
                # Buscar en el servicio de búsqueda principal - más confiable
                manual = await search_service.get_manual_by_model(model)
                
                # Si no se encuentra, intentar con la búsqueda semántica
                if not manual:
                    manual = await search_service.search_manual_with_semantic(model, message)
                
                # Guardar en caché si se encontró
                if manual and redis_service.connected:
                    redis_service.set_json(cache_key, manual, ex=3600*24)  # 24 horas
            except Exception as e:
                logger.error(f"Error buscando manual: {str(e)}")
                manual = None
        
        if not manual:
            error_response = f"Lo siento, no he encontrado un manual para el modelo {model}. Por favor, verifica que el código sea correcto o proporciona más detalles sobre el electrodoméstico."
            if message:
                session_data["messages"].append({"role": "user", "content": message})
            session_data["messages"].append({"role": "assistant", "content": error_response})
            await SessionManager.save_conversation_history(session_id, session_data)
            
            json_response = {"response": error_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
        
        content = manual.get('content')
        if not content:
            error_response = f"He encontrado la referencia del modelo {model}, pero parece que hay un problema con la documentación técnica. Por favor, contacta con nuestro servicio técnico para que podamos ayudarte mejor."
            if message:
                session_data["messages"].append({"role": "user", "content": message})
            session_data["messages"].append({"role": "assistant", "content": error_response})
            await SessionManager.save_conversation_history(session_id, session_data)
            
            json_response = {"response": error_response}
            if request:
                response_obj = JSONResponse(content=json_response)
                response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                return response_obj
            return json_response
            
        logger.info(f"Contenido recuperado, longitud: {len(content)} caracteres")
        
        # Truncar contenido si es excesivamente largo
        if len(content) > MAX_CONTEXT_LENGTH:
            logger.info(f"Truncando contenido del manual de {len(content)} a {MAX_CONTEXT_LENGTH} caracteres")
            content = content[:MAX_CONTEXT_LENGTH] + "\n\n... [Contenido truncado por límite de tamaño]"
            
        brand, product_type = await ConversationHandler.get_brand_and_type(model)
        
        # Comprobar caché para pares de modelo+mensaje similares
        if message:
            message_hash = hashlib.md5(message.lower().encode()).hexdigest()[:8]
            response_cache_key = f"svan:resp:{model}:{message_hash}"
            
            if redis_service.connected and not processed_images:
                cached_response = redis_service.get(response_cache_key)
                if cached_response:
                    logger.info(f"Usando respuesta en caché para modelo {model} y consulta similar")
                    
                    if message:
                        session_data["messages"].append({"role": "user", "content": message})
                    session_data["messages"].append({"role": "assistant", "content": cached_response})
                    await SessionManager.save_conversation_history(session_id, session_data)
                    
                    json_response = {"response": cached_response}
                    if request:
                        response_obj = JSONResponse(content=json_response)
                        response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                        return response_obj
                    return json_response
        
        initial_manual_context = f"""Modelo actual: {model}
Marca: {brand}
Tipo: {product_type}

INSTRUCCIONES CRÍTICAS:
1. Eres un asistente IA de soporte técnico especializado. Usa UNICAMENTE la información del manual técnico proporcionado.
2. DEBES leer y analizar el manual completo solo cuando sea necesario para responder a preguntas específicas.
3. ATENCIÓN: El manual puede contener soluciones para problemas comunes incluso si no están codificados como errores (E1, E2, etc.):
   - Si el usuario menciona problemas como "no hace chispa", "huele a gas", "no enciende", busca estas palabras clave en el manual.
   - Busca secciones como "Troubleshooting", "Problemas y soluciones", "Mantenimiento" o similares.
   - Proporciona soluciones ESPECÍFICAS basadas en el manual para cada problema.
4. Para códigos de error específicos (si existen en este modelo):
   - Busca y lista TODOS los códigos de error mencionados en el manual.
   - Incluye las descripciones EXACTAS de cada código.
5. IMPORTANTE: Recuerda los detalles de la conversación anterior para mantener el contexto.
6. Si el usuario pregunta sobre un tema técnico o valor específico (como "valor de NTC"), encuentra esta información en el manual y responde con precisión.
7. Usa ÚNICAMENTE información del manual - NO INVENTES ni añadas información que no esté explícitamente en el documento.

RESUMEN DEL MANUAL:
El manual técnico para el modelo {model} contiene información sobre seguridad, especificaciones, características del producto, mantenimiento, y solución de problemas. Si necesitas información específica (como códigos de error o procedimientos de mantenimiento), por favor indícalos en tu pregunta.
"""
        full_manual_context = initial_manual_context
        
        # Optimización: usar solo mensajes recientes para conservar espacio
        recent_history = session_data["messages"][-3:] if session_data["messages"] else []
        
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": "IMPORTANTE: Eres el Asistente IA de Soporte Técnico. Tienes la capacidad de analizar imágenes. Cuando los usuarios pregunten si puedes procesar o analizar imágenes, debes responder que SI y explicar tus capacidades de análisis visual."},
        ]
        
        if session_data.get("context_summary"):
            messages.append({"role": "system", "content": f"CONTEXTO DE LA CONVERSACIÓN ANTERIOR:\n{session_data['context_summary']}\n\nRecuerda estos detalles al responder al usuario."})
        
        if session_data.get("important_details"):
            details_str = "\n".join([f"{k}: {v}" for k, v in session_data["important_details"].items()])
            if details_str:
                messages.append({"role": "system", "content": f"DETALLES IMPORTANTES:\n{details_str}"})
        
        # Enriquecer contexto con contenido del manual
        messages.append({"role": "system", "content": full_manual_context})
        messages.extend(recent_history)
        
        # Preparar mensaje del usuario con imágenes si existen
        if processed_images and message:
            user_message_content = [
                {"type": "text", "text": message},
                *[{"type": "image_url", "image_url": {"url": f"data:{img['content_type']};base64,{img['base64']}"}} for img in processed_images]
            ]
            messages.append({"role": "user", "content": user_message_content})
            session_data["messages"].append({"role": "user", "content": message + " [Imagen adjunta]"})
        elif processed_images:
            user_message_content = [
                {"type": "text", "text": "Analiza estas imágenes, por favor."},
                *[{"type": "image_url", "image_url": {"url": f"data:{img['content_type']};base64,{img['base64']}"}} for img in processed_images]
            ]
            messages.append({"role": "user", "content": user_message_content})
            session_data["messages"].append({"role": "user", "content": "[Imagen adjunta]"})
        elif message:
            messages.append({"role": "user", "content": message})
            session_data["messages"].append({"role": "user", "content": message})
        
        # Estimar tokens para ajustar max_tokens
        input_tokens = sum(len(str(msg.get("content", ""))) for msg in messages) // 4 + 8 * len(messages)
        adjusted_max_tokens = min(MAX_TOKENS, 4000 - min(input_tokens, 3000))
        if adjusted_max_tokens < 100:
            adjusted_max_tokens = 100
        logger.info(f"Tokens estimados: ~{input_tokens}, max_tokens ajustado a {adjusted_max_tokens}")
        
        # Obtener respuesta de OpenAI
        logger.info(f"Enviando solicitud a OpenAI con modelo {GPT_MODEL}")
        start_openai_time = time.time()
        
        response = await ai_foundry_service.chat_completion_with_data(
            messages=messages,
            query=message,
            model_number=model,
            max_tokens=adjusted_max_tokens,
            temperature=DEFAULT_TEMPERATURE,
        )
        logger.info(f"Tiempo de respuesta de OpenAI: {time.time() - start_openai_time:.2f}s")
        
        if not response:
            response = "Lo siento, ha ocurrido un error al generar la respuesta. Por favor, intenta nuevamente."
        else:
            # Guardar en caché si no hay imágenes (las respuestas con imágenes son muy específicas)
            if redis_service.connected and message and not processed_images:
                message_hash = hashlib.md5(message.lower().encode()).hexdigest()[:8]
                response_cache_key = f"svan:resp:{model}:{message_hash}"
                redis_service.set(response_cache_key, response, ex=3600*24)  # 24 horas
            
        logger.info(f"Respuesta generada: {len(response)} caracteres")
        
        # Guardar respuesta en historial
        session_data["messages"].append({"role": "assistant", "content": response})
        
        # Optimizar el tamaño del historial si es muy grande
        if len(session_data["messages"]) > CONTEXT_WINDOW_MESSAGES * 2:
            old_msgs = session_data["messages"][:-CONTEXT_WINDOW_MESSAGES]
            new_summary = await ConversationHandler.generate_context_summary(old_msgs)
            
            session_data["context_summary"] = new_summary + "\n\n" + (session_data.get("context_summary") or "")
            session_data["messages"] = session_data["messages"][-CONTEXT_WINDOW_MESSAGES:]
            session_data["last_summary_time"] = time.time()
            session_data["last_summary_message_count"] = len(session_data["messages"])
        
        # Guardar historial actualizado
        await SessionManager.save_conversation_history(session_id, session_data)
        
        # Preparar respuesta
        json_response = {"response": response}
        
        # Registrar tiempo total
        processing_time = time.time() - start_time
        logger.info(f"Tiempo total de procesamiento: {processing_time:.2f}s")
        
        # Devolver respuesta
        if request:
            response_obj = JSONResponse(content=json_response)
            response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
            return response_obj
        return json_response
        
    except Exception as e:
        # Capturar y registrar el error completo
        error_trace = traceback.format_exc()
        logger.error(f"Error procesando consulta: {str(e)}\n{error_trace}")
        
        try:
            if 'session_id' in locals() and 'session_data' in locals():
                session_data["error_occurred"] = True
                await SessionManager.save_conversation_history(session_id, session_data)
        except Exception as inner_e:
            logger.error(f"Error secundario al guardar estado de error: {str(inner_e)}")
        
        error_response = {"response": "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, intenta nuevamente en unos momentos."}
        if request:
            response_obj = JSONResponse(content=error_response)
            return response_obj
        return error_response

@router.post("/analyze-image")
async def analyze_image(image: UploadFile = File(...)):
    """Endpoint para analizar imágenes con OCR."""
    try:
        file_path = await FileProcessor.save_uploaded_file(image)
        if not file_path:
            raise HTTPException(status_code=500, detail="Error al guardar la imagen")
        
        async with aiofiles.open(file_path, 'rb') as f:
            content = await f.read()
            
        # Buscar códigos de error comunes en la imagen
        # Nota: Aquí asumimos que tienes implementado un servicio de OCR
        # Si no tienes un servicio OCR, puedes eliminarlo o adaptarlo
        try:
            error_codes = []
            # Código de ejemplo - reemplazar por tu implementación real
            # result = await asyncio.get_event_loop().run_in_executor(None, lambda: Tesseract.recognize(content, 'spa'))
            # text = result.data.text
            # error_codes = re.findall(r'[EF][0-9]{2,3}', text) or []
            return {"error_codes": error_codes}
        except Exception as e:
            logger.error(f"Error en OCR: {str(e)}")
            return {"error_codes": []}
    except Exception as e:
        logger.error(f"Error al analizar imagen: {str(e)}")
        return {"error_codes": []}

# Endpoint de salud
@router.get("/health")
async def healthcheck():
    """Verificar el estado de salud del servicio"""
    try:
        # Verificar Redis
        redis_status = "OK" if redis_service.connected else "ERROR"
        
        # Verificar OpenAI
        openai_status = "OK"
        try:
            # Verificación rápida de OpenAI
            response = await azure_openai_service.chat_completion(
                messages=[{"role": "system", "content": "Test"}],
                max_tokens=10
            )
            if not response:
                openai_status = "ERROR: No response from OpenAI"
        except Exception as e:
            openai_status = f"ERROR: {str(e)[:100]}"
        
        # Verificar Azure Search
        search_status = "OK"
        try:
            # Verificación rápida de Search
            test_result = await search_service.search_manuals(limit=1)
            if test_result is None:
                search_status = "ERROR: No response from Search service"
        except Exception as e:
            search_status = f"ERROR: {str(e)[:100]}"
        
        # Métricas para monitoreo
        metrics = {
            "conversation_history_size": len(conversation_history),
            "redis_available": redis_service.connected,
            "memory_usage_mb": f"{get_process_memory_usage():.1f}"
        }
        
        return {
            "status": "healthy" if all([redis_status == "OK", openai_status == "OK", search_status == "OK"]) else "degraded",
            "services": {
                "redis": redis_status,
                "openai": openai_status,
                "azure_search": search_status
            },
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"Error en healthcheck: {str(e)}")
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Utilidad para obtener uso de memoria del proceso
def get_process_memory_usage():
    """Obtiene el uso de memoria del proceso actual en MB"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        return 0
