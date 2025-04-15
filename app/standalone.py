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
import random
import os
from pathlib import Path

import redis
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Depends, Response
from fastapi.responses import JSONResponse
from openai import AzureOpenAI
from PIL import Image

from app.services.azure_search_service import AzureSearchService
from app.core.settings import Settings

# Configuración
settings = Settings()

# Inicializar cliente de Azure OpenAI
openai_client = AzureOpenAI(
    api_key=settings.OPENAI_API_KEY,
    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
    api_version=settings.AZURE_OPENAI_API_VERSION
)

# Constantes
GPT_MODEL = "gpt-4o-mini"
SMALL_MODEL_FOR_SUMMARIES = "gpt-3.5-turbo"  # Modelo de chat compatible para fallback
MAX_TOKENS = 4000
DEFAULT_TEMPERATURE = 0.7
SESSION_EXPIRY = 86400 * 14  # 2 semanas en segundos
CONTEXT_WINDOW_MESSAGES = 25  # Mensajes a mantener en el contexto
MAX_HISTORY_TOKENS = 8000  # Límite aproximado de tokens para historia de conversación

# Configurar logging detallado
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Directorio para almacenar archivos temporales
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Crear router para integrarlo en la aplicación principal
router = APIRouter()

# Configuración de Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_SSL = os.getenv("REDIS_SSL", "False").lower() == "true"

# Inicializar cliente Redis con reconexión automática
try:
    pool = redis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        max_connections=10,
        health_check_interval=30,
        retry_on_timeout=True
    )
    if REDIS_SSL:
        pool.connection_class = redis.SSLConnection
        pool.connection_kwargs.update({
            'ssl_cert_reqs': 'required',
            # Próximos certificados aquí
        })
    redis_client = redis.Redis(connection_pool=pool)
    redis_client.ping()
    redis_available = True
    logger.info("Conexión a Redis establecida correctamente")
except Exception as e:
    logger.error(f"Error al conectar con Redis: {str(e)}")
    logger.warning("Utilizando almacenamiento en memoria como fallback")
    redis_available = False

# Historial de conversación para mantener contexto (fallback si Redis no está disponible)
conversation_history = {}

# Caché de manuales para búsqueda más eficiente
manual_cache = {}

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
        
        # Si no hay cookie, creamos un nuevo ID de sesión
        new_session_id = f"session_{secrets.token_hex(16)}"
        logger.info(f"Creando nuevo session_id: {new_session_id[:8]}...")
        
        return new_session_id
    
    @staticmethod
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
                        parsed_data = json.loads(data)
                        # Verificar que los datos son válidos
                        if isinstance(parsed_data, dict) and "messages" in parsed_data:
                            return parsed_data
                        else:
                            logger.warning(f"Datos de sesión {session_id[:8]} malformados, inicializando nueva sesión")
                    except json.JSONDecodeError:
                        logger.error(f"Error al decodificar JSON de Redis para sesión {session_id[:8]}")
            except Exception as e:
                logger.error(f"Error recuperando datos de Redis: {str(e)}")
                # Intentar reconectar en segundo plano
                try:
                    redis_client.ping()
                except:
                    pass
        
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
    
    @staticmethod
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
                if len(history_json) > 500000:  # Si es mayor a 500KB
                    # Conservamos solo los mensajes más recientes
                    if len(history_data.get("messages", [])) > CONTEXT_WINDOW_MESSAGES:
                        history_data["messages"] = history_data["messages"][-CONTEXT_WINDOW_MESSAGES:]
                        # Generar un resumen del contexto anterior
                        await ConversationHandler.generate_context_summary(history_data["messages"])
                        history_json = json.dumps(history_data)
                        logger.info(f"Historia comprimida a {len(history_json)} bytes para sesión {session_id[:8]}")
                
                # Usar pipeline para operaciones atómicas
                pipe = redis_client.pipeline()
                pipe.set(history_key, history_json)
                pipe.expire(history_key, SESSION_EXPIRY)
                pipe.execute()
                
                return True
            except Exception as e:
                logger.error(f"Error guardando datos en Redis: {str(e)}")
                # Intentar reconectar en segundo plano
                try:
                    redis_client.ping()
                except:
                    pass
                return False
        
        return True


class ConversationHandler:
    """Clase para manejar la lógica de conversación"""
    
    @staticmethod
    async def extract_model_from_message(message: str) -> Optional[str]:
        """
        Extrae el número de modelo del mensaje del usuario con lógica mejorada.
        """
        if not message:
            return None
            
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
        
        # Verificar si es una pregunta general sobre electrodomésticos
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
        if len(messages) < 4:  # Si hay muy pocos mensajes, no es necesario un resumen
            return ""
        
        try:
            # Extraer los últimos N mensajes para resumir
            last_messages = messages[-CONTEXT_WINDOW_MESSAGES:] if len(messages) > CONTEXT_WINDOW_MESSAGES else messages
            
            # Preparar el prompt para el resumen
            summary_prompt = [
                {"role": "system", "content": "Eres un asistente que resume contextos de conversación. Crea un resumen conciso de los puntos clave mencionados en la conversación, incluyendo problemas específicos, modelos de productos, síntomas, soluciones discutidas y cualquier otro detalle importante que debería recordarse para mantener la coherencia."},
                {"role": "user", "content": "Resume esta conversación en un párrafo conciso capturando los detalles más importantes:\n\n" + "\n".join([f"{m['role']}: {m['content'][:300]}" for m in last_messages])}
            ]
            
            # Generar el resumen con un modelo más económico
            response = openai_client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,  # Usar el mismo deployment
                messages=summary_prompt,
                max_tokens=300,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info(f"Resumen de contexto generado: {len(summary)} caracteres")
            return summary
        except Exception as e:
            logger.error(f"Error generando resumen de contexto: {str(e)}")
            # En caso de error, crear un resumen básico manualmente
            try:
                topics = set()
                models = set()
                for msg in messages[-10:]:
                    # Extraer modelos
                    model_matches = re.findall(r'[SWAH][A-Z0-9]{2,}[0-9]+', msg.get('content', ''))
                    models.update(model_matches)
                    
                    # Extraer palabras clave (simplificado)
                    for keyword in ['error', 'fallo', 'problema', 'no funciona', 'reparación']:
                        if keyword in msg.get('content', '').lower():
                            topics.add(keyword)
                
                summary_parts = []
                if models:
                    summary_parts.append(f"Modelos mencionados: {', '.join(models)}")
                if topics:
                    summary_parts.append(f"Temas: {', '.join(topics)}")
                    
                return ". ".join(summary_parts) if summary_parts else ""
            except Exception:
                return ""  # Fallback final


class ManualSearchService:
    """Servicio para buscar y procesar manuales técnicos"""
    
    def __init__(self):
        self.search_service = AzureSearchService()
        self.cache = {}
        self.cache_ttl = 3600  # 1 hora
        self.last_cache_cleanup = time.time()
    
    async def search_manual_with_semantic(self, model: str, query: str = None) -> Dict[str, Any]:
        """
        Búsqueda mejorada de manuales con capacidades semánticas.
        Combina la búsqueda exacta por modelo con la búsqueda semántica basada en la consulta.
        """
        # Verificar caché primero
        cache_key = f"{model}_{query if query else 'default'}"
        current_time = time.time()
        
        # Limpiar caché antigua (cada hora)
        if current_time - self.last_cache_cleanup > 3600:
            self._cleanup_cache()
            self.last_cache_cleanup = current_time
        
        # Verificar si está en caché y no ha expirado
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if current_time - cache_entry['timestamp'] < self.cache_ttl:
                logger.info(f"Usando manual desde caché para {cache_key}")
                return cache_entry['data']
        
        try:
            # Estrategia 1: Buscar el manual específico por modelo
            manual = await self.search_service.get_manual_by_model(model)
            
            # Si tenemos una consulta específica y el manual es extenso, también realizar búsqueda semántica
            if query and manual and len(manual.get('content', '')) > 5000:
                try:
                    # Extraer palabras clave de la consulta
                    keywords = query.lower().split()
                    content = manual['content']
                    
                    # Buscar párrafos relevantes
                    paragraphs = content.split('\n\n')
                    relevant_paragraphs = []
                    
                    for paragraph in paragraphs:
                        if len(paragraph.strip()) < 20:  # Ignorar párrafos muy cortos
                            continue
                            
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
                except Exception as e:
                    logger.error(f"Error en la búsqueda semántica: {str(e)}")
                    # En caso de error, mantener el contenido original
            
            # Guardar en caché
            if manual:
                self.cache[cache_key] = {
                    'data': manual,
                    'timestamp': current_time
                }
                
            return manual
        except Exception as e:
            logger.error(f"Error en búsqueda mejorada de manual: {str(e)}")
            return None
    
    def _cleanup_cache(self):
        """Limpia entradas antiguas de la caché"""
        current_time = time.time()
        expired_keys = [k for k, v in self.cache.items() 
                       if current_time - v['timestamp'] > self.cache_ttl]
        
        for key in expired_keys:
            del self.cache[key]
        
        logger.info(f"Limpieza de caché: eliminadas {len(expired_keys)} entradas antiguas")


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
                    # Leer contenido
                    content = await attachment.read()
                    
                    # Procesar la imagen con PIL para optimizar tamaño
                    with Image.open(BytesIO(content)) as img:
                        # Redimensionar si es demasiado grande
                        max_dimension = 800
                        if img.width > max_dimension or img.height > max_dimension:
                            ratio = min(max_dimension / img.width, max_dimension / img.height)
                            new_size = (int(img.width * ratio), int(img.height * ratio))
                            img = img.resize(new_size, Image.LANCZOS)
                        
                        # Convertir a JPEG con calidad optimizada
                        output = BytesIO()
                        img.convert('RGB').save(output, format='JPEG', quality=75, optimize=True)
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
                        
                        logger.info(f"Imagen {attachment.filename} procesada para análisis ({len(base64_image) // 1024}KB)")
                elif attachment.content_type == 'application/pdf':
                    # Aquí podríamos procesar PDFs también
                    logger.info(f"PDF detectado: {attachment.filename} - procesamiento pendiente")
                    # TODO: Para una implementación futura
            except Exception as e:
                logger.error(f"Error procesando imagen {attachment.filename}: {str(e)}")
        
        return processed_images
    
    @staticmethod
    async def save_uploaded_file(upload_file: UploadFile) -> Optional[Path]:
        """
        Guarda un archivo subido en el directorio temporal y retorna su ruta.
        """
        try:
            # Generar un nombre de archivo único
            ext = Path(upload_file.filename).suffix
            unique_filename = f"{int(time.time())}_{secrets.token_hex(8)}{ext}"
            file_path = TEMP_DIR / unique_filename
            
            # Guardar el archivo
            async with aiofiles.open(file_path, 'wb') as f:
                content = await upload_file.read()
                await f.write(content)
            
            logger.info(f"Archivo {upload_file.filename} guardado como {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Error guardando archivo {upload_file.filename}: {str(e)}")
            return None


class OpenAIService:
    """Clase para interactuar con Azure OpenAI con manejo de errores mejorado"""
    
    def __init__(self):
        self.client = openai_client
        self.retry_attempts = 3
        self.backoff_factor = 1.5
    
    async def get_chat_completion(self, 
                                 messages: List[Dict], 
                                 model: str = GPT_MODEL,
                                 max_tokens: int = MAX_TOKENS,
                                 temperature: float = DEFAULT_TEMPERATURE,
                                 stream=False) -> Any:
        """
        Obtiene una respuesta de Azure OpenAI con reintentos y manejo de errores mejorado.
        """
        attempt = 0
        last_error = None
        
        while attempt < self.retry_attempts:
            try:
                logger.info(f"Enviando solicitud a Azure OpenAI con {len(messages)} mensajes ({model})")
                
                # Estimar tokens de entrada para ajustar max_tokens
                input_tokens = self._estimate_tokens(messages)
                if input_tokens > MAX_TOKENS * 0.6:  # Si los tokens de entrada son más del 60% del límite
                    adjusted_max_tokens = min(max_tokens, MAX_TOKENS - input_tokens)
                    if adjusted_max_tokens < 100:  # Permitir al menos 100 tokens para la respuesta
                        adjusted_max_tokens = 100
                    logger.info(f"Ajustando max_tokens de {max_tokens} a {adjusted_max_tokens} (entrada: {input_tokens})")
                    max_tokens = adjusted_max_tokens
                
                # Preparar parámetros para la llamada a la API
                params = {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": stream
                }
                
                response = self.client.chat.completions.create(
                    model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                    **params
                )
                
                if stream:
                    return response
                else:
                    return response.choices[0].message.content.strip()
                
            except Exception as e:
                attempt += 1
                last_error = e
                wait_time = self.backoff_factor ** attempt
                
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"Error Azure OpenAI ({error_type}): {error_msg}")
                
                if "401" in error_msg:
                    logger.error("Error de autenticación detectado. No se realizarán más intentos.")
                    break
                
                if "max_tokens" in error_msg:
                    max_tokens = int(max_tokens * 0.8)
                    if max_tokens < 100:
                        max_tokens = 100
                    logger.info(f"Reduciendo max_tokens a {max_tokens} para siguiente intento")
                elif "rate limit" in error_msg.lower() or "429" in error_msg:
                    # Obtener el tiempo de espera del encabezado Retry-After
                    retry_after = 60  # Valor por defecto
                    if hasattr(e, 'response') and e.response is not None:
                        retry_after = int(e.response.headers.get("Retry-After", 60))
                    wait_time = retry_after + random.uniform(1, 3)
                    logger.warning(f"Rate limit detectado, esperando {wait_time:.1f}s antes de reintentar")
                
                if attempt < self.retry_attempts:
                    logger.info(f"Reintentando en {wait_time:.1f}s (intento {attempt}/{self.retry_attempts})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Agotados todos los intentos. Último error: {error_msg}")
                    if model != SMALL_MODEL_FOR_SUMMARIES:
                        try:
                            logger.info(f"Intentando fallback con modelo {SMALL_MODEL_FOR_SUMMARIES}")
                            return await self.get_chat_completion(
                                messages=messages[:3] + messages[-2:],
                                model=SMALL_MODEL_FOR_SUMMARIES,
                                max_tokens=max(1000, max_tokens),
                                temperature=temperature
                            )
                        except Exception as fallback_error:
                            logger.error(f"Error en fallback: {str(fallback_error)}")
                    return "Lo siento, estoy experimentando dificultades técnicas debido a límites de uso. Por favor, intenta nuevamente en unos minutos."
    
    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """
        Estima aproximadamente el número de tokens en los mensajes.
        Esta es una estimación aproximada, no exacta.
        """
        # Aproximadamente 4 caracteres por token en promedio
        chars_per_token = 4
        total_chars = sum(len(msg.get("content", "")) for msg in messages if isinstance(msg.get("content", ""), str))
        
        # Añadir overhead por estructura de mensajes
        overhead = 8 * len(messages)
        
        return total_chars // chars_per_token + overhead


# Inicializar servicios
manual_search_service = ManualSearchService()
openai_service = OpenAIService()


@router.post("/fullchat")
async def fullchat(
    request: Request, 
    message: str = Form(None), 
    attachments: list[UploadFile] = File(None)
):
    """
    Endpoint mejorado que implementa el chat completo con manejo robusto de contexto
    y procesamiento de imágenes adjuntadas por el usuario.
    """
    start_time = time.time()
    try:
        # Obtener o generar ID de sesión
        session_id = await SessionManager.get_session_id(request) if request else "default_session"
        
        # Recuperar historial para esta sesión
        session_data = await SessionManager.get_conversation_history(session_id)
            
        # Log de inicio
        logger.info(f"========== INICIO PROCESAMIENTO /fullchat SESIÓN: {session_id[:8]} ==========")
        
        # Si no hay mensaje ni archivos, enviar saludo
        if not message and not attachments:
            return {"response": "¡Hola! Soy SvanIA, el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?"}
            
        # Logging de entradas
        if message:
            logger.info(f"Mensaje recibido: {message[:100]}" + ("..." if len(message) > 100 else ""))
        
        if attachments:
            logger.info(f"Archivos adjuntos recibidos: {[a.filename for a in attachments]}")
        
        # Crear una respuesta que incluirá la cookie de sesión
        json_response = None
        
        # 1. Procesar las imágenes para análisis si hay archivos adjuntos
        processed_images = []
        if attachments:
            processed_images = await FileProcessor.process_images_for_analysis(attachments)
        
        # 2. Extraer el modelo mencionado en el mensaje
        model = None
        if message:
            # Detectar si el mensaje es una identificación simple del modelo
            if "modelo es el" in message.lower():
                model_match = re.search(r'(S|W|A|H)\w+', message, re.IGNORECASE)
                if model_match:
                    identified_model = model_match.group(0).upper()
                    session_data["current_model"] = identified_model
                    session_data["messages"].append({"role": "user", "content": message})
                    
                    # Determinar marca y tipo de producto
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
            
            # Si no es una identificación simple, extraer el modelo normalmente
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
            
        # 3. Verificar si necesitamos generar un resumen de contexto
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
        
        # 4. Determinar si podemos responder sin modelo específico
        if not model:
            # Si es un saludo
            if message and await ConversationHandler.is_greeting(message):
                response = "¡Hola! Me alegro de saludarte. ¿En qué puedo ayudarte hoy? Puedo responder preguntas sobre electrodomésticos del Grupo SVAN (SVAN, WONDER, ASPES e HYUNDAI) y ayudarte con problemas técnicos específicos."
                
                session_data["messages"].append({"role": "user", "content": message})
                session_data["messages"].append({"role": "assistant", "content": response})
                
                await SessionManager.save_conversation_history(session_id, session_data)
                
                json_response = {"response": response}
                if request:
                    response_obj = JSONResponse(content=json_response)
                    response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
                    return response_obj
                return json_response
            
            # Si es una solicitud de ayuda
            if message and await ConversationHandler.is_help_request(message):
                help_response = """
Soy SvanIA, el Asistente Técnico especializado en productos del Grupo SVAN. Puedo ayudarte de las siguientes maneras:

1. **Consultas técnicas**: Pregúntame sobre cualquier modelo específico (empiezan con S para SVAN, W para WONDER, A para ASPES o H para HYUNDAI).

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
                
            # Si parece ser una pregunta general sobre electrodomésticos
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
                    logger.info(f"Procesando pregunta general con OpenAI: {message}")
                    response = await openai_service.get_chat_completion(
                        messages=general_messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                    
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
                    
            # Si tenemos imágenes pero no modelo, intentar hacer análisis de la imagen
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
                    
                    Si identificas un modelo específico, inclúyelo en tu respuesta. Recuerda que el código suele comenzar con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI).
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
                    response = await openai_service.get_chat_completion(
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
            
            # Si no hay modelo, solicitar al usuario que proporcione uno
            if not model:
                basic_response = "Para poder ayudarte de forma más precisa, necesito conocer el modelo específico de tu electrodoméstico. ¿Podrías indicarme el modelo exacto? Debe comenzar con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
                
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
        
        # 5. Buscar el manual cuando tenemos un modelo
        manual = await manual_search_service.search_manual_with_semantic(model, message)
        
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
        
        # Asegurar que tenemos contenido
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
        logger.info(f"Primeros 200 caracteres: {content[:200]}")
        logger.info(f"Últimos 200 caracteres: {content[-200:] if len(content) > 200 else content}")
            
        # Determinar marca y tipo de producto
        brand, product_type = await ConversationHandler.get_brand_and_type(model)
        
        # 6. Construir el contexto del manual con instrucciones mejoradas
        # Enviar solo un resumen inicial para reducir el uso de tokens
        initial_manual_context = f"""Modelo actual: {model}
Marca: {brand}
Tipo: {product_type}

INSTRUCCIONES CRÍTICAS:
1. Eres SvanIA, un asistente técnico especializado. Usa ÚNICAMENTE la información del manual técnico proporcionado.
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
        
        # 7. Obtener historial de conversación reciente
        recent_history = session_data["messages"][-3:] if session_data["messages"] else []
        
        # 8. Construir mensajes para OpenAI
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": "IMPORTANTE: Tu nombre es SvanIA, no Svaniano. Eres el Asistente Técnico de SVAN. Tienes la capacidad de analizar imágenes. Cuando los usuarios pregunten si puedes procesar o analizar imágenes, debes responder que SÍ y explicar tus capacidades de análisis visual."},
        ]
        
        if session_data.get("context_summary"):
            messages.append({"role": "system", "content": f"CONTEXTO DE LA CONVERSACIÓN ANTERIOR:\n{session_data['context_summary']}\n\nRecuerda estos detalles al responder al usuario."})
        
        if session_data.get("important_details"):
            details_str = "\n".join([f"{k}: {v}" for k, v in session_data["important_details"].items()])
            if details_str:
                messages.append({"role": "system", "content": f"DETALLES IMPORTANTES:\n{details_str}"})
        
        messages.append({"role": "system", "content": full_manual_context})
        messages.extend(recent_history)
        
        # 9. Preparar el mensaje final del usuario
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
        
        # 10. Llamar a OpenAI con GPT-4o-mini
        logger.info(f"Enviando solicitud a OpenAI con modelo {GPT_MODEL}")
        start_openai_time = time.time()
        
        # Ajustar max_tokens para permitir respuestas más útiles
        input_tokens = openai_service._estimate_tokens(messages)
        adjusted_max_tokens = min(MAX_TOKENS, 4000 - input_tokens)
        if adjusted_max_tokens < 100:
            adjusted_max_tokens = 100
        logger.info(f"Ajustando max_tokens de {MAX_TOKENS} a {adjusted_max_tokens} (entrada: {input_tokens})")
        
        response = await openai_service.get_chat_completion(
            messages=messages,
            max_tokens=adjusted_max_tokens,
            temperature=DEFAULT_TEMPERATURE,
        )
        logger.info(f"Tiempo de respuesta de OpenAI: {time.time() - start_openai_time:.2f}s")
        
        # 11. Extraer y procesar la respuesta
        if not response:
            response = "Lo siento, ha ocurrido un error al generar la respuesta. Por favor, intenta nuevamente."
            
        logger.info(f"Respuesta generada: {len(response)} caracteres")
        
        # 12. Actualizar historial de conversación
        session_data["messages"].append({"role": "assistant", "content": response})
        
        # 13. Limitar tamaño del historial
        if len(session_data["messages"]) > CONTEXT_WINDOW_MESSAGES * 2:
            old_msgs = session_data["messages"][:-CONTEXT_WINDOW_MESSAGES]
            new_summary = await ConversationHandler.generate_context_summary(old_msgs)
            
            session_data["context_summary"] = new_summary + "\n\n" + (session_data.get("context_summary") or "")
            session_data["messages"] = session_data["messages"][-CONTEXT_WINDOW_MESSAGES:]
            session_data["last_summary_time"] = time.time()
            session_data["last_summary_message_count"] = len(session_data["messages"])
        
        # 14. Guardar el historial actualizado
        await SessionManager.save_conversation_history(session_id, session_data)
        
        # 15. Crear respuesta con cookie
        json_response = {"response": response}
        
        # 16. Medir tiempo total de procesamiento
        processing_time = time.time() - start_time
        logger.info(f"Tiempo total de procesamiento: {processing_time:.2f}s")
        
        if request:
            response_obj = JSONResponse(content=json_response)
            response_obj.set_cookie(key="svan_session", value=session_id, max_age=SESSION_EXPIRY, httponly=True, samesite="lax")
            return response_obj
        return json_response
        
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}", exc_info=True)
        
        try:
            if 'session_id' in locals() and 'session_data' in locals():
                session_data["error_occurred"] = True
                await SessionManager.save_conversation_history(session_id, session_data)
        except:
            pass
        
        error_response = {"response": "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, intenta nuevamente en unos momentos."}
        if request:
            response_obj = JSONResponse(content=error_response)
            return response_obj
        return error_response


# Verificar estado de conexión a Redis de forma periódica
async def check_redis_connection():
    """Verificar el estado de la conexión a Redis de forma periódica"""
    global redis_available
    try:
        redis_client.ping()
        if not redis_available:
            logger.info("Conexión a Redis restaurada")
            redis_available = True
    except:
        if redis_available:
            logger.warning("Conexión a Redis perdida, usando almacenamiento en memoria")
            redis_available = False
    
    asyncio.create_task(asyncio.sleep(60))
    asyncio.create_task(check_redis_connection())

# Iniciar verificación periódica
@router.on_event("startup")
async def startup_redis_check():
    asyncio.create_task(check_redis_connection())

# Verificar estado de conexión a Redis de forma periódica
async def check_redis_connection():
    """Verificar el estado de la conexión a Redis de forma periódica"""
    global redis_available
    try:
        redis_client.ping()
        if not redis_available:
            logger.info("Conexión a Redis restaurada")
            redis_available = True
    except:
        if redis_available:
            logger.warning("Conexión a Redis perdida, usando almacenamiento en memoria")
            redis_available = False
    
    asyncio.create_task(asyncio.sleep(60))
    asyncio.create_task(check_redis_connection())

# Iniciar verificación periódica
@router.on_event("startup")
async def startup_redis_check():
    asyncio.create_task(check_redis_connection())

# Endpoint de salud
@router.get("/health")
async def healthcheck():
    """Verificar el estado de salud del servicio"""
    try:
        # Verificar Redis
        redis_status = "OK" if redis_available else "ERROR"
        
        # Verificar OpenAI
        openai_status = "OK"
        try:
            openai_client.models.list(limit=1)
        except Exception as e:
            openai_status = f"ERROR: {str(e)}"
        
        # Verificar Azure Search
        search_status = "OK"
        try:
            search_service = AzureSearchService()
            await search_service.search_manuals(limit=1)
        except Exception as e:
            search_status = f"ERROR: {str(e)}"
        
        return {
            "status": "healthy",
            "services": {
                "redis": redis_status,
                "openai": openai_status,
                "azure_search": search_status
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error en healthcheck: {str(e)}")
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }