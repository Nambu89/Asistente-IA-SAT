# app/standalone.py
import logging
import re
from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from app.services.azure_search_service import AzureSearchService
from app.core.settings import Settings

# Configuración
settings = Settings()
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Configurar logging detallado
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Crear router para integrarlo en la aplicación principal
router = APIRouter()

# Historial de conversación para mantener contexto
conversation_history = {}

@router.post("/fullchat")
async def fullchat(request: Request, message: str = Form(None), attachments: list[UploadFile] = File(None)):
    """
    Endpoint independiente que garantiza enviar el manual completo a OpenAI.
    Este endpoint utiliza GPT-4o y asegura que se lea todo el contenido del manual.
    También mantiene el contexto de la conversación.
    """
    try:
        # Obtener una identificación única para la sesión (IP del cliente + user agent)
        client_host = request.client.host
        user_agent = request.headers.get("user-agent", "")
        session_id = f"{client_host}_{user_agent[:20]}"
        
        if session_id not in conversation_history:
            conversation_history[session_id] = {
                "current_model": None,
                "messages": []
            }
            
        # Log de inicio
        logger.info("========== INICIO PROCESAMIENTO /fullchat ==========")
        
        if not message:
            return {"response": "¡Hola! Soy el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?"}
            
        logger.info(f"Mensaje recibido: {message}")
        
        # 1. Obtener el modelo actual de la conversación (si existe)
        model = conversation_history[session_id]["current_model"]
        logger.info(f"Modelo en la sesión actual: {model}")
        
        # 2. Buscar patrones de modelo (letras seguidas de números)
        models = re.findall(r'[SWAH][A-Z0-9]{2,}', message.upper())
        logger.info(f"Modelos detectados inicialmente: {models}")
        
        # 3. Filtrar modelos para que sean válidos (contienen al menos un número)
        valid_models = []
        for potential_model in models:
            if re.search(r'[0-9]', potential_model):
                valid_models.append(potential_model)
        
        logger.info(f"Modelos válidos (contienen números): {valid_models}")
        
        # 4. Actualizar el modelo sólo si encontramos uno válido
        if valid_models:
            new_model = valid_models[0]
            # Si ya teníamos un modelo y es diferente al nuevo, registrar el cambio
            if model and model != new_model:
                logger.info(f"Cambiando de modelo: {model} -> {new_model}")
            
            model = new_model
            conversation_history[session_id]["current_model"] = model
            logger.info(f"Modelo establecido/actualizado a: {model}")
        else:
            # Si no se detecta un modelo válido, mantenemos el actual
            logger.info(f"No se detectaron modelos válidos, manteniendo modelo actual: {model}")
        
        # Procesar mensajes con o sin modelo
        if not model:
            # Si el mensaje actual es solo un problema técnico genérico, preguntar por el modelo
            problem_patterns = [
                r'error', r'no funciona', r'no enciende', r'no hace', r'problema', 
                r'fallo', r'avería', r'huele', r'olor', r'ruido', r'fugas'
            ]
            
            if any(re.search(pattern, message.lower()) for pattern in problem_patterns):
                logger.info("Detectada consulta técnica sin modelo específico")
                
                # Guardar este mensaje en el historial
                conversation_history[session_id]["messages"].append({"role": "user", "content": message})
                
                response = "Para poder ayudarte con ese problema técnico, necesito saber el modelo específico del producto. Los modelos comienzan con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
                
                conversation_history[session_id]["messages"].append({"role": "assistant", "content": response})
                logger.info("Solicitando modelo para la consulta técnica")
                return {"response": response}
            
            # Si es una consulta general, procesamos sin referencia a un manual específico
            logger.info("Procesando como consulta general")
            return await process_general_query(message, conversation_history[session_id])
        
        # Inicializar servicio de búsqueda
        search_service = AzureSearchService()
        
        # Buscar el manual con verificación exhaustiva
        logger.info(f"Buscando manual para modelo: {model}")
        manual = await search_service.get_manual_by_model(model)
        
        if not manual:
            logger.warning(f"No se encontró manual para el modelo: {model}")
            
            # Guardar mensaje en historial aunque no tengamos manual
            conversation_history[session_id]["messages"].append({"role": "user", "content": message})
            
            # Intentamos responder lo mejor posible sin manual
            return await process_fallback_query(message, model, conversation_history[session_id])
            
        # Extraer y verificar el contenido
        content = manual.get('content')
        if not content:
            logger.warning(f"Manual encontrado para {model}, pero sin contenido")
            conversation_history[session_id]["messages"].append({"role": "user", "content": message})
            response = f"He encontrado el manual para {model}, pero no contiene información. Por favor, contacta con soporte técnico."
            conversation_history[session_id]["messages"].append({"role": "assistant", "content": response})
            return {"response": response}
            
        # Log detallado del contenido para verificación
        content_length = len(content)
        logger.info(f"Contenido recuperado, longitud: {content_length} caracteres")
        logger.info(f"Primeros 200 caracteres:\n{content[:200]}")
        logger.info(f"Últimos 200 caracteres:\n{content[-200:] if content_length > 200 else content}")
        
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
            "fallo": "fallos o averías",
            "e": "códigos de error que empiecen por E",
            "f": "códigos de error que empiecen por F"
        }
        
        detected_problems = []
        for keyword, description in problem_keywords.items():
            if keyword in user_message_lower:
                detected_problems.append(description)
        
        problem_focus = ""
        if detected_problems:
            problem_focus = "Específicamente, el usuario está preguntando sobre: " + ", ".join(detected_problems)
        
        is_asking_about_manuals = False
        user_message_lower = message.lower()
        manual_keywords = [
            "manuales disponibles", 
            "manuales tienes", 
            "qué manuales", 
            "que manuales",
            "cuáles manuales",
            "cuales manuales",
            "a qué manuales",
            "a que manuales",
            "acceso a manuales",
            "qué modelos",
            "que modelos"
        ]

        # Verificación más exhaustiva
        if any(keyword in user_message_lower for keyword in manual_keywords):
            is_asking_about_manuals = True
            logger.info(f"Usuario preguntando por manuales disponibles. Mensaje: '{message}'")

        if is_asking_about_manuals:
            logger.info("Procesando solicitud de listado de manuales disponibles")
            try:
                search_service = AzureSearchService()
                all_docs = await search_service.search_manuals()
                logger.info(f"Total de documentos encontrados: {len(all_docs)}")
                
                # Imprimir todos los documentos para depuración
                for i, doc in enumerate(all_docs):
                    modelo = doc.get('modelo', 'Sin modelo')
                    nombre = doc.get('name', 'Sin nombre')
                    logger.info(f"Documento {i+1}: Modelo={modelo}, Nombre={nombre}")
                
                # Extraer solo los modelos de los documentos
                available_models = []
                for doc in all_docs:
                    model = doc.get('modelo')
                    if model and model not in available_models:
                        available_models.append(model)
                
                logger.info(f"Modelos disponibles encontrados: {available_models}")
                
                if available_models:
                    response = "Actualmente tengo acceso a los manuales de los siguientes modelos:\n\n"
                    for model_name in available_models:
                        response += f"- {model_name}\n"
                    response += "\n¿Con cuál de estos modelos necesitas ayuda?"
                else:
                    logger.warning("No se encontraron modelos disponibles en el índice")
                    response = "Lo siento, no puedo acceder a la lista de manuales disponibles en este momento. Sin embargo, puedo ayudarte con algunos modelos específicos como SL8401AIDVBX, SGW4600X, WI3600, entre otros. Por favor, indícame el modelo específico con el que necesitas ayuda."
            except Exception as e:
                logger.error(f"Error obteniendo manuales disponibles: {str(e)}", exc_info=True)
                response = "Lo siento, no puedo acceder a la lista de manuales disponibles en este momento debido a un error técnico. Sin embargo, puedo ayudarte con algunos modelos específicos. Por favor, indícame el modelo con el que necesitas ayuda."
            
            # Actualizar historial de conversación
            conversation_history[session_id]["messages"].append({"role": "user", "content": message})
            conversation_history[session_id]["messages"].append({"role": "assistant", "content": response})
            
            return {"response": response}
        
        # MANUAL COMPLETO - Con instrucciones explícitas y enfáticas
        full_manual_context = f"""Modelo actual: {model}
Marca: {brand}
Tipo: {product_type}

INSTRUCCIONES CRÍTICAS PARA EL ASISTENTE:
1. DEBES LEER EL MANUAL TÉCNICO COMPLETO proporcionado a continuación.
2. NO OMITAS NI IGNORES NINGUNA PARTE del manual, es ESENCIAL que proceses TODO el contenido.
3. ATENCIÓN: Este manual puede contener soluciones para problemas comunes incluso si no están codificados como errores (E1, E2, etc.):
   - Si el usuario menciona problemas como "no hace chispa", "huele a gas", "no enciende", busca estas palabras clave en el manual.
   - Busca secciones como "Troubleshooting", "Problemas y soluciones", "Mantenimiento" o similares.
   - Proporciona soluciones ESPECÍFICAS basadas en el manual para cada problema.
4. Para códigos de error específicos (si existen en este modelo):
   - Busca y lista TODOS los códigos de error mencionados en el manual.
   - Incluye las descripciones EXACTAS de cada código.
5. {problem_focus}
6. Usa ÚNICAMENTE información del manual - NO INVENTES ni añadas información que no esté explícitamente en el documento.

MANUAL TÉCNICO COMPLETO PARA MODELO {model}:
{content}"""

        # Verificar tamaño del contexto antes de enviar
        max_context = 100000  # Límite razonable
        context_length = len(full_manual_context)
        
        if context_length > max_context:
            logger.warning(f"¡ADVERTENCIA! El contexto es muy largo ({context_length} caracteres). Truncando a {max_context}.")
            full_manual_context = full_manual_context[:max_context]
            logger.info("Contexto truncado")
        
        # Log detallado del tamaño final
        logger.info(f"Tamaño del contexto final enviado: {len(full_manual_context)} caracteres")
        
        # Obtener historial de conversación reciente (últimos 4 mensajes)
        recent_history = conversation_history[session_id]["messages"][-4:] if conversation_history[session_id]["messages"] else []
        
        # Construir mensajes con instrucciones enfáticas
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": "IMPORTANTE: Tienes la capacidad de analizar imágenes. Cuando los usuarios pregunten si puedes procesar o analizar imágenes, debes responder que SÍ y explicar tus capacidades de análisis visual."},
            # CRUCIAL: Envía el manual completo en un único mensaje con instrucciones claras
            {"role": "system", "content": full_manual_context}
        ]
        
        # Añadir historial reciente
        messages.extend(recent_history)
        
        # Añadir el mensaje actual del usuario
        messages.append({"role": "user", "content": message})
        
        # Log detallado de la cantidad de mensajes
        logger.info(f"Total de mensajes enviados a OpenAI: {len(messages)}")
        
        # Llamar a OpenAI con modelo potente y parámetros optimizados
        logger.info("Enviando solicitud a OpenAI con modelo gpt-4o...")
        response_openai = openai_client.chat.completions.create(
            model="gpt-4o",  # Modelo completo para mayor capacidad
            messages=messages,
            max_tokens=2000,
            temperature=0.2,  # Temperatura baja para respuestas más precisas
        )
        
        # Extraer respuesta
        response = response_openai.choices[0].message.content.strip()
        logger.info(f"Respuesta recibida de OpenAI: {len(response)} caracteres")
        
        # Actualizar historial de conversación
        conversation_history[session_id]["messages"].append({"role": "user", "content": message})
        conversation_history[session_id]["messages"].append({"role": "assistant", "content": response})
        
        # Limitar tamaño del historial (mantener últimos 10 mensajes)
        if len(conversation_history[session_id]["messages"]) > 10:
            conversation_history[session_id]["messages"] = conversation_history[session_id]["messages"][-10:]
        
        logger.info("========== FIN PROCESAMIENTO /fullchat ==========")
        
        return {"response": response}

    except Exception as e:
        logger.error(f"Error procesando consulta en /fullchat: {str(e)}", exc_info=True)
        return {"response": "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, intenta nuevamente."}


async def process_general_query(message: str, session_data: dict):
    """
    Procesa consultas generales sin necesidad de un manual específico
    """
    try:
        # Construir mensajes para consulta general
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": """
            INSTRUCCIONES: 
            - Eres un asistente técnico especializado en productos del Grupo SVAN.
            - Para consultas técnicas específicas, debes solicitar el modelo del electrodoméstico.
            - Solo para preguntas generales, responde con información general sin solicitar el modelo.
            """}
        ]
        
        # Añadir historial reciente (últimos 4 mensajes)
        if session_data["messages"]:
            messages.extend(session_data["messages"][-4:])
        
        # Añadir el mensaje actual del usuario
        messages.append({"role": "user", "content": message})
        
        # Llamar a OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Modelo más pequeño para consultas generales
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Actualizar historial
        session_data["messages"].append({"role": "user", "content": message})
        session_data["messages"].append({"role": "assistant", "content": response_text})
        
        # Limitar tamaño del historial
        if len(session_data["messages"]) > 10:
            session_data["messages"] = session_data["messages"][-10:]
        
        return {"response": response_text}
        
    except Exception as e:
        logger.error(f"Error procesando consulta general: {str(e)}", exc_info=True)
        return {"response": "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, intenta nuevamente."}

async def get_available_manuals():
    """
    Obtiene la lista de todos los manuales disponibles en el sistema
    """
    try:
        search_service = AzureSearchService()
        all_docs = await search_service.search_manuals()
        
        # Extraer solo los modelos de los documentos
        available_models = []
        for doc in all_docs:
            model = doc.get('modelo')
            if model and model not in available_models:
                available_models.append(model)
        
        return available_models
    except Exception as e:
        logger.error(f"Error obteniendo manuales disponibles: {str(e)}")
        return []


async def process_fallback_query(message: str, model: str, session_data: dict):
    """
    Procesa consultas cuando no se encuentra el manual específico
    """
    try:
        # Construir mensajes para fallback
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": f"""
            INSTRUCCIONES:
            - El usuario ha preguntado sobre el modelo {model}, pero no tenemos el manual específico.
            - Debes informar que no tienes el manual para ese modelo específico.
            - Puedes ofrecer información general sobre el tipo de producto si lo sabes.
            - Sugieres contactar al soporte técnico oficial para información más específica.
            """}
        ]
        
        # Añadir historial reciente
        if session_data["messages"]:
            messages.extend(session_data["messages"][-4:])
        
        # Añadir el mensaje actual
        messages.append({"role": "user", "content": message})
        
        # Llamar a OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Actualizar historial
        session_data["messages"].append({"role": "user", "content": message})
        session_data["messages"].append({"role": "assistant", "content": response_text})
        
        # Limitar tamaño del historial
        if len(session_data["messages"]) > 10:
            session_data["messages"] = session_data["messages"][-10:]
        
        return {"response": response_text}
        
    except Exception as e:
        logger.error(f"Error procesando fallback query: {str(e)}", exc_info=True)
        return {"response": f"Lo siento, no tengo información específica sobre el modelo {model}. ¿Hay algo más en lo que pueda ayudarte?"}