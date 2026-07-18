"""
langchain_service.py - Servicio para integrar LangChain con el asistente técnico

Este servicio proporciona funcionalidades avanzadas de procesamiento de lenguaje natural
y gestión de contexto utilizando la biblioteca LangChain.
"""

import logging
import json
import os
import time
from typing import List, Dict, Any, Optional, Tuple

# Importaciones de LangChain
from langchain.chat_models import AzureChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.embeddings import AzureOpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

# Importaciones locales
from app.core.settings import Settings
from app.services.azure_search_service import AzureSearchService
from app.services.redis_service import RedisService

# Configurar logging
logger = logging.getLogger(__name__)

class LangChainService:
    """
    Servicio para integrar LangChain con el asistente técnico.
    
    Este servicio proporciona funcionalidades avanzadas de procesamiento de lenguaje natural
    y gestión de contexto utilizando la biblioteca LangChain, manteniendo compatibilidad
    con los servicios existentes.
    """
    
    def __init__(self):
        """Inicializa el servicio de LangChain."""
        logger.info("Inicializando LangChainService")
        self.settings = Settings()
        self.search_service = AzureSearchService()
        self.redis = RedisService()
        
        # Configurar modelo de LangChain para Azure OpenAI
        try:
            self.llm = AzureChatOpenAI(
                openai_api_version=self.settings.AZURE_OPENAI_API_VERSION,
                azure_deployment=self.settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                openai_api_key=self.settings.OPENAI_API_KEY,
                azure_endpoint=self.settings.AZURE_OPENAI_ENDPOINT,
                temperature=0.7
            )
            logger.info(f"Modelo LLM inicializado: {self.settings.AZURE_OPENAI_DEPLOYMENT_NAME}")
            
            # Inicializar embeddings si están configurados
            if hasattr(self.settings, 'AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME'):
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_deployment=self.settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME,
                    openai_api_key=self.settings.OPENAI_API_KEY,
                    azure_endpoint=self.settings.AZURE_OPENAI_ENDPOINT,
                    openai_api_version=self.settings.AZURE_OPENAI_API_VERSION,
                )
                logger.info(f"Embeddings inicializados: {self.settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME}")
            else:
                logger.warning("No se encontró configuración para embeddings, algunas funciones no estarán disponibles")
                self.embeddings = None
                
        except Exception as e:
            logger.error(f"Error al inicializar LangChain: {str(e)}")
            raise
            
        # Diccionario para almacenar vectorstores por modelo
        self.vectorstores = {}
        
        # Modelo actual (se establecerá durante las conversaciones)
        self.current_model = None
        
        # Prompt del sistema
        self.system_prompt = self.settings.SYSTEM_PROMPT
        
        logger.info("LangChainService inicializado correctamente")
    
    async def get_or_create_vectorstore(self, model_number: str) -> Optional[FAISS]:
        """
        Obtiene o crea un vectorstore para un modelo específico.
        
        Args:
            model_number: Número de modelo para el cual crear el vectorstore
            
        Returns:
            Instancia de FAISS o None si no se puede crear
        """
        # Verificar si ya tenemos un vectorstore para este modelo
        cache_key = f"svan:vectorstore:{model_number}"
        
        # Intentar cargar desde caché en memoria
        if model_number in self.vectorstores:
            logger.info(f"Usando vectorstore en memoria para modelo {model_number}")
            return self.vectorstores[model_number]
            
        # Intentar cargar desde Redis
        if self.redis.connected and self.embeddings:
            try:
                vectorstore_path = self.redis.get(cache_key)
                if vectorstore_path:
                    # Verificar si el archivo existe
                    if os.path.exists(vectorstore_path):
                        logger.info(f"Cargando vectorstore desde {vectorstore_path}")
                        vectorstore = FAISS.load_local(vectorstore_path, self.embeddings)
                        self.vectorstores[model_number] = vectorstore
                        return vectorstore
            except Exception as e:
                logger.error(f"Error al cargar vectorstore desde Redis: {str(e)}")
        
        # Si no tenemos embeddings configurados, no podemos crear vectorstores
        if not self.embeddings:
            logger.warning("No se pueden crear vectorstores sin embeddings configurados")
            return None
            
        # Obtener manual del modelo
        try:
            logger.info(f"Buscando manual para modelo {model_number}")
            manual = await self.search_service.get_manual_by_model(model_number)
            if not manual or not manual.get('content'):
                logger.warning(f"No se encontró manual para el modelo {model_number}")
                return None
                
            # Dividir el contenido en chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            logger.info(f"Dividiendo contenido del manual en chunks (longitud: {len(manual['content'])})")
            texts = text_splitter.split_text(manual['content'])
            logger.info(f"Contenido dividido en {len(texts)} chunks")
            
            # Crear vectorstore
            logger.info("Creando vectorstore con embeddings...")
            vectorstore = FAISS.from_texts(texts, self.embeddings)
            self.vectorstores[model_number] = vectorstore
            
            # Guardar en disco y en Redis para futuras consultas
            if self.redis.connected:
                try:
                    # Crear directorio para vectorstores si no existe
                    vectorstore_dir = os.path.join(os.getcwd(), "data", "vectorstores")
                    os.makedirs(vectorstore_dir, exist_ok=True)
                    
                    # Guardar vectorstore
                    vectorstore_path = os.path.join(vectorstore_dir, f"vectorstore_{model_number}")
                    vectorstore.save_local(vectorstore_path)
                    logger.info(f"Vectorstore guardado en {vectorstore_path}")
                    
                    # Guardar ruta en Redis
                    self.redis.set(cache_key, vectorstore_path, ex=86400)  # 24 horas
                except Exception as e:
                    logger.error(f"Error al guardar vectorstore: {str(e)}")
            
            return vectorstore
            
        except Exception as e:
            logger.error(f"Error al crear vectorstore: {str(e)}")
            return None
    
    def _extract_model_from_message(self, message: str) -> Optional[str]:
        """
        Extrae el número de modelo de un mensaje.
        
        Esta función es similar a la implementada en chat_services.py para mantener
        la compatibilidad.
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Número de modelo o None si no se encuentra
        """
        import re
        # Patrones para detectar modelos
        patterns = [
            r'\b([SWA][A-Z0-9]{2,})\b',  # Modelos que empiezan con S, W o A seguidos de letras/números
            r'\b(H[A-Z]{2}[0-9]{2,})\b'  # Modelos que empiezan con H seguido de 2 letras y números
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, message.upper())
            if matches:
                model = matches[0]
                logger.info(f"Modelo detectado en mensaje: {model}")
                return model
                
        return None
    
    async def create_memory_from_history(self, session_id: str) -> Optional[ConversationBufferMemory]:
        """
        Crea un objeto de memoria de LangChain a partir del historial guardado.
        
        Args:
            session_id: ID de sesión para recuperar el historial
            
        Returns:
            Objeto ConversationBufferMemory o None si no hay historial
        """
        if not session_id or not self.redis.connected:
            return ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True
            )
            
        try:
            stored_history = self.redis.get(f"svan:session:{session_id}:history")
            if not stored_history:
                return ConversationBufferMemory(
                    memory_key="chat_history",
                    return_messages=True
                )
                
            # Crear memoria
            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True
            )
            
            # Cargar historial
            history = json.loads(stored_history)
            for msg in history:
                if msg["role"] == "user":
                    memory.chat_memory.add_user_message(msg["content"])
                elif msg["role"] == "assistant":
                    memory.chat_memory.add_ai_message(msg["content"])
                elif msg["role"] == "system":
                    memory.chat_memory.add_message(SystemMessage(content=msg["content"]))
            
            logger.info(f"Memoria creada con {len(history)} mensajes del historial")
            return memory
            
        except Exception as e:
            logger.error(f"Error al crear memoria desde historial: {str(e)}")
            return ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True
            )
    
    async def get_chat_response(self, message: str, session_id: str = None) -> str:
        """
        Procesa un mensaje del usuario y retorna una respuesta utilizando LangChain.
        
        Esta función es compatible con la interfaz de chat_services.py para facilitar
        la integración.
        
        Args:
            message: Mensaje del usuario
            session_id: ID de sesión opcional
            
        Returns:
            Respuesta del asistente
        """
        start_time = time.time()
        
        try:
            # Intentar recuperar modelo de sesiones anteriores
            if session_id and self.redis.connected:
                stored_model = self.redis.get(f"svan:session:{session_id}:model")
                if stored_model:
                    self.current_model = stored_model
                    logger.info(f"Recuperado modelo de sesión anterior: {stored_model}")
            
            # Detectar modelo en el mensaje actual
            model = self._extract_model_from_message(message)
            if model:
                self.current_model = model
                logger.info(f"Modelo detectado en el mensaje actual: {model}")
                
                # Guardar el modelo en Redis si tenemos session_id
                if session_id and self.redis.connected:
                    self.redis.set(f"svan:session:{session_id}:model", model, ex=3600)  # 1 hora
            
            # Crear memoria desde historial si existe
            memory = await self.create_memory_from_history(session_id)
            
            # Si tenemos un modelo, intentar usar RAG
            if self.current_model and self.embeddings:
                # Intentar obtener vectorstore
                vectorstore = await self.get_or_create_vectorstore(self.current_model)
                
                if vectorstore:
                    logger.info(f"Usando RAG con vectorstore para modelo {self.current_model}")
                    
                    # Crear cadena de recuperación conversacional
                    qa_chain = ConversationalRetrievalChain.from_llm(
                        llm=self.llm,
                        retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
                        memory=memory,
                        return_source_documents=True,
                        verbose=True
                    )
                    
                    # Obtener respuesta
                    result = await qa_chain.ainvoke({"question": message})
                    response = result["answer"]
                    
                    # Log de tiempo
                    elapsed = time.time() - start_time
                    logger.info(f"Respuesta RAG generada en {elapsed:.2f}s")
                    
                    # Guardar en Redis si hay session_id
                    if session_id and self.redis.connected:
                        self._save_history_to_redis(session_id, memory)
                    
                    return response
            
            # Si no tenemos vectorstore o no tenemos modelo, usar enfoque tradicional
            logger.info("Usando enfoque tradicional (sin RAG)")
            
            # Preparar contexto para el modelo
            context = ""
            if self.current_model:
                # Buscar información del modelo
                manual = await self.search_service.get_manual_by_model(self.current_model)
                
                if manual and manual.get('content'):
                    logger.info(f"Manual encontrado para {self.current_model}")
                    
                    # Limitar tamaño del contexto
                    content = manual['content']
                    max_context_length = 8000  # Mismo valor que en chat_services.py
                    if len(content) > max_context_length:
                        logger.info(f"Contenido truncado de {len(content)} a {max_context_length} caracteres")
                        content = content[:max_context_length] + "...[Contenido truncado por límite de tamaño]"
                    
                    context = f"Modelo: {self.current_model}\n\nManual técnico:\n{content}"
                else:
                    logger.warning(f"No se encontró manual para el modelo {self.current_model}")
                    context = f"No se encontró el manual para el modelo {self.current_model}"
            else:
                logger.info("No se ha especificado un modelo válido")
                context = "No se ha especificado un modelo válido"
            
            # Crear prompt
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(self.system_prompt),
                SystemMessagePromptTemplate.from_template(context),
                HumanMessagePromptTemplate.from_template("{question}")
            ])
            
            # Crear cadena
            chain = prompt | self.llm
            
            # Obtener respuesta
            response = await chain.ainvoke({"question": message})
            
            # Guardar en memoria
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(response.content)
            
            # Guardar en Redis si hay session_id
            if session_id and self.redis.connected:
                self._save_history_to_redis(session_id, memory)
            
            # Log de tiempo
            elapsed = time.time() - start_time
            logger.info(f"Respuesta tradicional generada en {elapsed:.2f}s")
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error en get_chat_response: {str(e)}", exc_info=True)
            return f"Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."
    
    def _save_history_to_redis(self, session_id: str, memory: ConversationBufferMemory) -> None:
        """
        Guarda el historial de conversación en Redis.
        
        Args:
            session_id: ID de sesión
            memory: Objeto de memoria de LangChain
        """
        try:
            # Convertir mensajes de LangChain a formato compatible con el sistema actual
            history = []
            for msg in memory.chat_memory.messages:
                if isinstance(msg, HumanMessage):
                    history.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    history.append({"role": "assistant", "content": msg.content})
                elif isinstance(msg, SystemMessage):
                    history.append({"role": "system", "content": msg.content})
            
            # Limitar el tamaño del historial para evitar problemas de memoria
            history_to_save = history[-15:] if len(history) > 15 else history
            
            # Guardar en Redis
            self.redis.set(f"svan:session:{session_id}:history", json.dumps(history_to_save), ex=7200)  # 2 horas
            logger.info(f"Historial guardado en sesión {session_id}: {len(history_to_save)} mensajes")
            
            # Guardar modelo actual si existe
            if self.current_model:
                self.redis.set(f"svan:session:{session_id}:model", self.current_model, ex=7200)  # 2 horas
                
        except Exception as e:
            logger.error(f"Error al guardar historial en Redis: {str(e)}")
