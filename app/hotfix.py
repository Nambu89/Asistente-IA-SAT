# app/hotfix.py
import os
import sys
from pathlib import Path
import logging
import re
from fastapi import Form, File, UploadFile, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from app.services.azure_search_service import AzureSearchService
from app.core.settings import Settings

# Configuración
settings = Settings()
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Historial de conversación para mantener contexto
conversation_history = {}

async def chat_endpoint(request: Request = None, message: str = Form(None), attachments: list[UploadFile] = File(None)):
    """
    Hotfix para el endpoint de chat que asegura enviar el manual completo a OpenAI
    """
    try:
        if not message:
            return {"response": "¡Hola! Soy el Asistente Técnico de SVAN. ¿En qué puedo ayudarte hoy?"}
            
        logger.info(f"Mensaje recibido: {message}")
        
        # Obtener una identificación única para la sesión
        session_id = "default_session"
        if request:
            client_host = request.client.host
            user_agent = request.headers.get("user-agent", "")
            session_id = f"{client_host}_{user_agent[:20]}"
        
        if session_id not in conversation_history:
            conversation_history[session_id] = {
                "current_model": None,
                "messages": []
            }
        
        # Buscar patrones de modelo (letras seguidas de números)
        # Patrón más específico para modelos
        models = re.findall(r'[SWAH][A-Z0-9]{2,}', message.upper())
        logger.info(f"Modelos detectados: {models}")
        
        # Filtrar modelos para evitar falsos positivos (palabras comunes)
        common_words = ['HACE', 'HUELE', 'HOLA', 'HABER', 'SABER', 'SOBRE', 'ALGO']
        filtered_models = [m for m in models if m not in common_words]
        
        # Si se detecta un modelo en este mensaje, actualizamos el modelo actual
        if filtered_models:
            model = filtered_models[0]
            conversation_history[session_id]["current_model"] = model
            logger.info(f"Modelo actualizado a: {model}")
        else:
            # Si no se detecta un modelo, usamos el último conocido
            model = conversation_history[session_id]["current_model"]
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
                conversation_history[session_id]["messages"].append({"role": "user", "content": message})
                
                response = "Para poder ayudarte con ese problema técnico, necesito saber el modelo específico del producto. Los modelos comienzan con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."
                
                conversation_history[session_id]["messages"].append({"role": "assistant", "content": response})
                logger.info("Solicitando modelo para la consulta técnica")
                return {"response": response}
            
            # Para conversaciones generales
            return {"response": "Por favor, indícame el modelo específico del producto sobre el que necesitas información. Los modelos comienzan con S (SVAN), W (WONDER), A (ASPES) o H (HYUNDAI)."}
        
        # Inicializar servicio de búsqueda
        search_service = AzureSearchService()
        
        # Buscar el manual
        manual = await search_service.get_manual_by_model(model)
        
        if not manual:
            return {"response": f"Lo siento, no he encontrado un manual para el modelo {model}. Por favor, verifica que el código sea correcto."}
            
        # Asegurar que tenemos contenido
        content = manual.get('content')
        if not content:
            return {"response": f"He encontrado el manual para {model}, pero no contiene información. Por favor, contacta con soporte técnico."}
            
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
6. Usa ÚNICAMENTE información del manual - NO INVENTES ni añadas información que no esté explícitamente en el documento.

MANUAL TÉCNICO COMPLETO:
{content}"""

        # Evitar contextos demasiado largos
        max_context = 100000  # Límite razonable 
        if len(full_manual_context) > max_context:
            logger.warning(f"El contexto es muy largo ({len(full_manual_context)} caracteres). Truncando a {max_context}.")
            full_manual_context = full_manual_context[:max_context]
        
        # Asegurar que sabemos el tamaño exacto
        logger.info(f"Tamaño del contexto final enviado: {len(full_manual_context)} caracteres")
        
        # Obtener historial de conversación reciente
        recent_history = conversation_history[session_id]["messages"][-4:] if conversation_history[session_id]["messages"] else []
        
        # Construir mensajes
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {"role": "system", "content": "IMPORTANTE: Tienes la capacidad de analizar imágenes. Cuando los usuarios pregunten si puedes procesar o analizar imágenes, debes responder que SÍ y explicar tus capacidades de análisis visual."},
            # CRUCIAL: Envía el manual completo en un único mensaje
            {"role": "system", "content": full_manual_context}
        ]
        
        # Añadir historial reciente
        messages.extend(recent_history)
        
        # Añadir el mensaje actual del usuario
        messages.append({"role": "user", "content": message})
        
        # Llamar a OpenAI con modelo más potente
        logger.info("Enviando solicitud a OpenAI con modelo gpt-4o...")
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
        conversation_history[session_id]["messages"].append({"role": "user", "content": message})
        conversation_history[session_id]["messages"].append({"role": "assistant", "content": response})
        
        # Limitar tamaño del historial (mantener últimos 10 mensajes)
        if len(conversation_history[session_id]["messages"]) > 10:
            conversation_history[session_id]["messages"] = conversation_history[session_id]["messages"][-10:]
        
        return {"response": response}
        
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}", exc_info=True)
        return {"response": "Lo siento, ha ocurrido un error. Por favor, intenta nuevamente."}