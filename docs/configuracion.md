# Configuración de SvanIA

Este documento describe las opciones de configuración disponibles para la aplicación SvanIA, incluyendo variables de entorno, archivos de configuración y ajustes recomendados.

## Índice

1. [Variables de Entorno](#variables-de-entorno)
2. [Archivo .env](#archivo-env)
3. [Configuración de Servicios](#configuración-de-servicios)
4. [Configuración de Seguridad](#configuración-de-seguridad)
5. [Configuración de Logging](#configuración-de-logging)
6. [Configuración de Rendimiento](#configuración-de-rendimiento)

## Variables de Entorno

SvanIA utiliza variables de entorno para configurar su comportamiento. A continuación se detallan las principales variables y sus valores recomendados.

### Configuración General

| Variable | Descripción | Valor Predeterminado | Recomendado |
|----------|-------------|----------------------|-------------|
| `DEBUG` | Habilita el modo de depuración | `False` | `False` en producción |
| `PRODUCTION` | Indica si la aplicación está en producción | `False` | `True` en producción |
| `PORT` | Puerto para el servidor web | `8000` | `8000` |
| `WEBSITES_PORT` | Puerto para Azure App Service | - | `8000` |
| `LOG_LEVEL` | Nivel de logging | `INFO` | `INFO` en producción, `DEBUG` en desarrollo |
| `ALLOWED_HOSTS` | Hosts permitidos (separados por comas) | `*` | Lista específica en producción |

### Azure OpenAI

| Variable | Descripción | Valor Predeterminado |
|----------|-------------|----------------------|
| `AZURE_OPENAI_API_KEY` | Clave de API para Azure OpenAI | - |
| `AZURE_OPENAI_ENDPOINT` | URL del endpoint de Azure OpenAI | - |
| `AZURE_OPENAI_API_VERSION` | Versión de la API | `2025-01-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Nombre del despliegue del modelo | `gpt-4o-mini` |
| `OPENAI_MODEL` | Modelo de OpenAI a utilizar | `gpt-4o-mini` |
| `MAX_TOKENS` | Número máximo de tokens para la respuesta | `4000` |
| `TEMPERATURE` | Temperatura para la generación de texto | `0.7` |

### Azure Cognitive Search

| Variable | Descripción | Valor Predeterminado |
|----------|-------------|----------------------|
| `AZURE_SEARCH_ENDPOINT` | URL del endpoint de Azure Cognitive Search | - |
| `AZURE_SEARCH_API_KEY` | Clave de API para Azure Cognitive Search | - |
| `AZURE_SEARCH_INDEX_NAME` | Nombre del índice de búsqueda | `azureblob-index` |

### Redis

| Variable | Descripción | Valor Predeterminado |
|----------|-------------|----------------------|
| `REDIS_HOST` | Host del servidor Redis | `localhost` |
| `REDIS_PORT` | Puerto del servidor Redis | `6379` |
| `REDIS_PASSWORD` | Contraseña para autenticación | - |
| `REDIS_SSL` | Habilita SSL para conexiones seguras | `False` |

### Configuración de Chat

| Variable | Descripción | Valor Predeterminado |
|----------|-------------|----------------------|
| `SESSION_EXPIRY` | Tiempo de expiración de sesiones (segundos) | `1209600` (2 semanas) |
| `CONTEXT_WINDOW_MESSAGES` | Número de mensajes a mantener en el contexto | `15` |
| `MAX_HISTORY_TOKENS` | Límite de tokens para el historial | `8000` |
| `MAX_CONTEXT_LENGTH` | Caracteres máximos para contexto de manuales | `15000` |

### Archivos y Almacenamiento

| Variable | Descripción | Valor Predeterminado |
|----------|-------------|----------------------|
| `MAX_FILE_SIZE` | Tamaño máximo de archivo (bytes) | `10485760` (10MB) |
| `CACHE_EXPIRY` | Tiempo de expiración de caché (segundos) | `86400` (24 horas) |

## Archivo .env

SvanIA utiliza un archivo `.env` para cargar variables de entorno. A continuación se muestra un ejemplo de archivo `.env`:

```dotenv
# Configuración General
DEBUG=False
PRODUCTION=True
PORT=8000
LOG_LEVEL=INFO
ALLOWED_HOSTS=svania.azurewebsites.net,b2b.gruposvan.com

# Azure OpenAI
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/
AZURE_OPENAI_API_VERSION=2025-01-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
OPENAI_MODEL=gpt-4o-mini
MAX_TOKENS=4000
TEMPERATURE=0.7

# Azure Cognitive Search
AZURE_SEARCH_ENDPOINT=https://your-search-instance.search.windows.net
AZURE_SEARCH_API_KEY=your_search_api_key_here
AZURE_SEARCH_INDEX_NAME=azureblob-index

# Redis
REDIS_HOST=your-redis-instance.redis.cache.windows.net
REDIS_PORT=6380
REDIS_PASSWORD=your_redis_password_here
REDIS_SSL=True

# Configuración de Chat
SESSION_EXPIRY=1209600
CONTEXT_WINDOW_MESSAGES=15
MAX_HISTORY_TOKENS=8000
MAX_CONTEXT_LENGTH=15000

# Archivos y Almacenamiento
MAX_FILE_SIZE=10485760
CACHE_EXPIRY=86400
```

## Configuración de Servicios

### Redis

Redis se utiliza para almacenar sesiones, historiales de conversación y caché. Para un rendimiento óptimo, se recomienda:

- Utilizar una instancia de Redis dedicada en producción
- Habilitar SSL para conexiones seguras
- Configurar una política de persistencia adecuada
- Monitorear el uso de memoria y establecer límites apropiados

### Azure OpenAI

Para optimizar el uso de Azure OpenAI:

- Seleccionar el modelo adecuado según las necesidades (gpt-4o-mini recomendado)
- Ajustar `MAX_TOKENS` según la longitud esperada de las respuestas
- Configurar `TEMPERATURE` según la creatividad deseada (valores más bajos para respuestas más deterministas)
- Implementar estrategias de reintentos para manejar errores temporales

### Azure Cognitive Search

Para un rendimiento óptimo de búsqueda:

- Indexar correctamente los documentos con metadatos relevantes
- Configurar sinónimos para términos técnicos comunes
- Implementar caché para consultas frecuentes
- Monitorear el uso de cuota y rendimiento

## Configuración de Seguridad

### HTTPS

SvanIA implementa un middleware para forzar HTTPS en producción:

```python
# Middleware para manejar X-Forwarded-Proto y forzar HTTPS
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Detectar si estamos en producción (Azure)
        is_production = not (request.url.hostname == 'localhost' or request.url.hostname == '127.0.0.1')
        
        # Comprobar si ya estamos en HTTPS o si hay un proxy que indica HTTPS
        is_https = request.url.scheme == 'https' or request.headers.get("X-Forwarded-Proto") == "https"
        
        # Solo redirigir si estamos en producción, la solicitud es HTTP, y no hay indicación de HTTPS en los encabezados
        if is_production and not is_https and request.url.scheme == 'http':
            # Evitar bucles de redirección comprobando encabezados adicionales
            redirect_count = int(request.headers.get("X-Redirect-Count", "0"))
            if redirect_count < 3:  # Limitar a un máximo de 3 redirecciones
                https_url = str(request.url).replace('http://', 'https://', 1)
                headers = {'Location': https_url, 'X-Redirect-Count': str(redirect_count + 1)}
                return Response(status_code=301, headers=headers)
        
        # Establecer el esquema a HTTPS en producción para las URLs generadas
        if is_production:
            request.scope["scheme"] = "https"
            
        response = await call_next(request)
        return response
```

### CORS

La configuración de CORS se realiza mediante middleware:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://b2b.gruposvan.com",
        "https://svania.azurewebsites.net"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    max_age=86400
)
```

### TrustedHost

Se implementa el middleware TrustedHost para restringir los hosts permitidos:

```python
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "svania.azurewebsites.net",
        "b2b.gruposvan.com"
    ]
)
```

## Configuración de Logging

SvanIA implementa un sistema de logging detallado para facilitar el diagnóstico de problemas:

```python
# Configurar logging (simplificado para Azure)
log_level_name = os.getenv("LOG_LEVEL", "INFO" if os.getenv("PRODUCTION") else "DEBUG")
log_level = getattr(logging, log_level_name.upper())

# Configurar formato de logs
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Configurar logging solo con handler para consola (Azure captura stdout/stderr)
logging.basicConfig(
    level=log_level,
    format=log_format,
    handlers=[
        # Handler para stdout
        logging.StreamHandler(sys.stdout)
    ]
)
```

### Recomendaciones para Logging

- Utilizar `INFO` en producción para reducir el volumen de logs
- Configurar `DEBUG` en desarrollo para obtener información detallada
- Reducir el nivel de logging para bibliotecas ruidosas:
  ```python
  for noisy_logger in ['azure.core', 'httpx', 'httpcore', 'multipart.multipart', 'urllib3', 'asyncio']:
      logging.getLogger(noisy_logger).setLevel(logging.WARNING)
  ```

## Configuración de Rendimiento

### Caché

SvanIA implementa estrategias de caché para mejorar el rendimiento:

- **Redis**: Caché distribuida para entornos de producción
- **Memoria**: Caché en memoria como fallback
- **Tiempos de Expiración**: Configurables mediante variables de entorno

### Asincronía

La aplicación utiliza operaciones asíncronas para mejorar el rendimiento:

- **FastAPI**: Framework asíncrono para manejar solicitudes
- **HTTPX**: Cliente HTTP asíncrono para llamadas a APIs externas
- **Redis Async**: Cliente asíncrono para Redis

### Compresión

Se implementa compresión Gzip para reducir el tamaño de las respuestas:

```python
# Agregar compresión Gzip
app.add_middleware(GZipMiddleware, minimum_size=1000)
```
