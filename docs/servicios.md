# Servicios de SvanIA

Este documento describe los principales servicios que componen la aplicación SvanIA, su funcionalidad y cómo interactúan entre sí.

## Índice

1. [Redis Service](#redis-service)
2. [Azure Search Service](#azure-search-service)
3. [Azure OpenAI Service](#azure-openai-service)
4. [Azure AI Foundry Service](#azure-ai-foundry-service)
5. [Chat Services](#chat-services)

## Redis Service

El servicio de Redis proporciona capacidades de caché y almacenamiento para la aplicación.

### Características

- **Almacenamiento de Sesiones**: Mantiene el historial de conversaciones de los usuarios
- **Caché de Respuestas**: Almacena respuestas frecuentes para mejorar el rendimiento
- **Persistencia de Datos**: Garantiza que los datos importantes se conserven entre reinicios
- **Manejo de Fallos**: Implementa estrategias de reintentos y fallback a caché en memoria

### Métodos Principales

- `ensure_connection()`: Verifica y establece la conexión con Redis
- `set()`: Almacena un valor en Redis con tiempo de expiración opcional
- `get()`: Recupera un valor de Redis
- `set_json()`: Serializa y almacena un objeto JSON
- `get_json()`: Recupera y deserializa un objeto JSON

### Configuración

El servicio se configura mediante las siguientes variables de entorno:

- `REDIS_HOST`: Host del servidor Redis
- `REDIS_PORT`: Puerto del servidor Redis
- `REDIS_PASSWORD`: Contraseña para autenticación
- `REDIS_SSL`: Habilita SSL para conexiones seguras

## Azure Search Service

Este servicio integra Azure Cognitive Search para buscar información relevante en manuales técnicos.

### Características

- **Búsqueda Semántica**: Encuentra documentos relacionados con consultas en lenguaje natural
- **Filtrado por Modelo**: Optimiza búsquedas cuando se menciona un modelo específico
- **Caché de Resultados**: Almacena resultados frecuentes para mejorar el rendimiento
- **Paginación**: Maneja grandes conjuntos de resultados de manera eficiente

### Métodos Principales

- `search_manuals()`: Busca en todos los manuales disponibles
- `get_manual_by_model()`: Recupera un manual específico por código de modelo
- `search_with_query()`: Realiza una búsqueda con una consulta específica
- `extract_context_for_query()`: Extrae contexto relevante para una consulta

### Configuración

El servicio se configura mediante las siguientes variables de entorno:

- `AZURE_SEARCH_ENDPOINT`: URL del endpoint de Azure Cognitive Search
- `AZURE_SEARCH_API_KEY`: Clave de API para autenticación
- `AZURE_SEARCH_INDEX_NAME`: Nombre del índice de búsqueda

## Azure OpenAI Service

Este servicio integra Azure OpenAI para generar respuestas contextuales utilizando modelos avanzados de lenguaje.

### Características

- **Generación de Respuestas**: Utiliza GPT-4o-mini para generar respuestas precisas
- **Streaming**: Soporta respuestas en tiempo real mediante streaming
- **Reintentos**: Implementa estrategias de reintento para manejar errores temporales
- **Control de Tokens**: Gestiona límites de tokens para optimizar costos

### Métodos Principales

- `chat_completion()`: Genera una respuesta completa a partir de un conjunto de mensajes
- `chat_completion_streaming()`: Genera una respuesta en tiempo real mediante streaming

### Configuración

El servicio se configura mediante las siguientes variables de entorno:

- `AZURE_OPENAI_API_KEY`: Clave de API para autenticación
- `AZURE_OPENAI_ENDPOINT`: URL del endpoint de Azure OpenAI
- `AZURE_OPENAI_API_VERSION`: Versión de la API
- `AZURE_OPENAI_DEPLOYMENT_NAME`: Nombre del despliegue del modelo
- `MAX_TOKENS`: Número máximo de tokens para la respuesta

## Azure AI Foundry Service

Este servicio proporciona capacidades de análisis de imágenes y OCR utilizando Azure AI Foundry.

### Características

- **Análisis de Imágenes**: Procesa imágenes para extraer información visual
- **OCR (Reconocimiento Óptico de Caracteres)**: Extrae texto de imágenes
- **Detección de Objetos**: Identifica objetos y componentes en imágenes
- **Integración con Chat**: Permite incorporar análisis visual en conversaciones

### Métodos Principales

- `analyze_image()`: Analiza una imagen y extrae información relevante
- `extract_text_from_image()`: Extrae texto de una imagen mediante OCR
- `process_image_for_chat()`: Prepara una imagen para su uso en el contexto de chat

### Configuración

El servicio se configura mediante variables de entorno específicas para Azure AI Foundry.

## Chat Services

Este servicio implementa la lógica principal de conversación, integrando todos los servicios anteriores.

### Características

- **Manejo de Contexto**: Mantiene el contexto de la conversación
- **Procesamiento de Mensajes**: Analiza y procesa mensajes de usuario
- **Integración de Servicios**: Coordina los diferentes servicios para generar respuestas
- **Manejo de Sesiones**: Gestiona sesiones de usuario y persistencia

### Componentes Principales

- `SessionManager`: Gestiona sesiones de usuario y almacenamiento de historiales
- `ConversationHandler`: Implementa la lógica de procesamiento de conversaciones
- `FileProcessor`: Maneja el procesamiento de archivos e imágenes

### Configuración

El servicio utiliza configuraciones de todos los servicios anteriores, además de:

- `CONTEXT_WINDOW_MESSAGES`: Número de mensajes a mantener en el contexto
- `MAX_HISTORY_TOKENS`: Límite de tokens para el historial
- `SESSION_EXPIRY`: Tiempo de expiración de sesiones
