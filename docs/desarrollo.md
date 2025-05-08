# Guía de Desarrollo de SvanIA

Este documento proporciona información para desarrolladores que deseen contribuir o extender la funcionalidad de SvanIA.

## Índice

1. [Entorno de Desarrollo](#entorno-de-desarrollo)
2. [Estructura del Proyecto](#estructura-del-proyecto)
3. [Patrones de Diseño](#patrones-de-diseño)
4. [Guía de Estilo](#guía-de-estilo)
5. [Pruebas](#pruebas)
6. [Extensión de Funcionalidades](#extensión-de-funcionalidades)
7. [Mejores Prácticas](#mejores-prácticas)

## Entorno de Desarrollo

### Configuración del Entorno

1. Clone el repositorio:
   ```bash
   git clone <url-del-repositorio>
   cd SvanIA
   ```

2. Cree y active un entorno virtual:
   ```bash
   python -m venv venv
   # En Windows
   venv\Scripts\activate
   # En Linux/Mac
   source venv/bin/activate
   ```

3. Instale las dependencias de desarrollo:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure las variables de entorno:
   - Cree un archivo `.env` basado en `.env.example`
   - Configure las credenciales para servicios locales o de desarrollo

5. Inicie la aplicación en modo desarrollo:
   ```bash
   python run.py
   ```

### Herramientas Recomendadas

- **IDE**: Visual Studio Code con extensiones para Python y FastAPI
- **Gestión de Dependencias**: pip y venv
- **Control de Versiones**: Git con GitHub/Azure DevOps
- **Linting**: flake8, pylint
- **Formateo**: black, isort
- **Pruebas**: pytest
- **Documentación**: Markdown, Sphinx

## Estructura del Proyecto

SvanIA sigue una estructura modular organizada por funcionalidad:

```
SvanIA/
├── app/                    # Código principal de la aplicación
│   ├── __init__.py         # Inicialización del paquete
│   ├── main.py             # Punto de entrada principal
│   ├── standalone.py       # Servicio de chat mejorado
│   ├── api/                # Definiciones de API
│   │   ├── __init__.py
│   │   ├── routes.py       # Rutas principales de la API
│   │   └── endpoints/      # Endpoints específicos
│   ├── core/               # Funcionalidades centrales
│   │   ├── __init__.py
│   │   └── settings.py     # Configuración de la aplicación
│   ├── models/             # Modelos de datos
│   │   ├── __init__.py
│   │   ├── chat_models.py
│   │   └── feedback_models.py
│   ├── routers/            # Rutas adicionales
│   │   ├── __init__.py
│   │   └── manuals.py      # Rutas para manuales
│   └── services/           # Servicios externos
│       ├── __init__.py
│       ├── redis_service.py
│       ├── azure_search_service.py
│       ├── azure_openai_service.py
│       └── azure_ai_foundry_service.py
├── static/                 # Archivos estáticos
│   ├── css/
│   ├── js/
│   └── images/
├── templates/              # Plantillas HTML
│   └── chat.html
├── tests/                  # Pruebas
│   ├── __init__.py
│   └── test_*.py
├── logs/                   # Directorio de logs
├── Manuales/               # Manuales técnicos
├── uploads/                # Archivos subidos por usuarios
├── .env                    # Variables de entorno
├── .gitignore              # Archivos ignorados por Git
├── Dockerfile              # Configuración de Docker
├── docker-compose.yml      # Configuración de Docker Compose
├── requirements.txt        # Dependencias de Python
└── run.py                  # Script para ejecutar la aplicación
```

## Patrones de Diseño

SvanIA implementa varios patrones de diseño para mantener el código organizado y mantenible:

### Singleton

Utilizado para servicios que deben tener una única instancia en toda la aplicación:

```python
def singleton(cls):
    """Decorador para implementar el patrón Singleton."""
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class AzureSearchService:
    # Implementación...
```

### Dependency Injection

FastAPI utiliza inyección de dependencias para proporcionar servicios a los endpoints:

```python
@app.get("/health")
async def health_check():
    # Los servicios se acceden a través de app.state
    redis_available = await app.state.redis_service.ensure_connection()
    # ...
```

### Repository Pattern

Abstracción del acceso a datos:

```python
class SessionManager:
    @staticmethod
    async def get_conversation_history(session_id: str) -> Dict:
        # Implementación que abstrae el acceso a Redis o memoria
```

### Factory Method

Creación de objetos según condiciones específicas:

```python
def create_openai_service(settings):
    if settings.USE_AI_FOUNDRY:
        return AzureAIFoundryService()
    else:
        return AzureOpenAIService()
```

## Guía de Estilo

SvanIA sigue las convenciones de estilo de Python (PEP 8) con algunas adaptaciones:

### Convenciones de Nomenclatura

- **Clases**: CamelCase (ej. `RedisService`)
- **Funciones y Métodos**: snake_case (ej. `get_manual_by_model`)
- **Variables**: snake_case (ej. `session_id`)
- **Constantes**: UPPER_CASE (ej. `MAX_TOKENS`)
- **Módulos**: snake_case (ej. `azure_search_service.py`)

### Docstrings

Utilizar docstrings en formato Google para documentar clases y funciones:

```python
def search_manuals(self, query: str = None, limit: int = None) -> List[Dict[str, Any]]:
    """
    Busca manuales usando Azure Search con caché para consultas frecuentes.
    
    Args:
        query: Texto de búsqueda opcional
        limit: Número máximo de resultados a devolver
        
    Returns:
        Lista de documentos encontrados
    """
```

### Imports

Organizar imports en el siguiente orden:

1. Módulos estándar de Python
2. Módulos de terceros
3. Módulos de la aplicación

```python
# Módulos estándar
import os
import logging
import json

# Módulos de terceros
from fastapi import FastAPI, Request
from azure.search.documents import SearchClient

# Módulos de la aplicación
from app.services.redis_service import RedisService
from app.core.settings import Settings
```

## Pruebas

SvanIA utiliza pytest para pruebas unitarias e integración:

### Estructura de Pruebas

```
tests/
├── __init__.py
├── conftest.py              # Configuración y fixtures compartidos
├── test_api/                # Pruebas de API
├── test_services/           # Pruebas de servicios
└── test_utils/              # Pruebas de utilidades
```

### Ejemplo de Prueba

```python
# tests/test_services/test_redis_service.py
import pytest
from unittest.mock import patch, MagicMock
from app.services.redis_service import RedisService

@pytest.fixture
def redis_service():
    with patch('redis.asyncio.Redis') as mock_redis:
        mock_redis.return_value.ping.return_value = True
        service = RedisService()
        yield service

async def test_ensure_connection(redis_service):
    # Configurar el mock
    redis_service.client.ping.return_value = True
    
    # Ejecutar la función a probar
    result = await redis_service.ensure_connection()
    
    # Verificar el resultado
    assert result is True
    redis_service.client.ping.assert_called_once()
```

### Ejecución de Pruebas

```bash
# Ejecutar todas las pruebas
pytest

# Ejecutar pruebas con cobertura
pytest --cov=app

# Ejecutar pruebas específicas
pytest tests/test_services/
```

## Extensión de Funcionalidades

### Añadir un Nuevo Servicio

1. Cree un nuevo archivo en `app/services/`:
   ```python
   # app/services/new_service.py
   import logging
   from app.core.settings import Settings
   
   logger = logging.getLogger(__name__)
   
   class NewService:
       def __init__(self):
           self.settings = Settings()
           # Inicialización
           
       async def some_method(self):
           # Implementación
   ```

2. Registre el servicio en `app/main.py`:
   ```python
   from app.services.new_service import NewService
   
   async def startup():
       # ...
       app.state.new_service = NewService()
   ```

### Añadir un Nuevo Endpoint

1. Cree un nuevo archivo en `app/api/endpoints/` o añada a un archivo existente:
   ```python
   # app/api/endpoints/new_endpoint.py
   from fastapi import APIRouter, Request
   
   router = APIRouter()
   
   @router.get("/new-endpoint")
   async def new_endpoint(request: Request):
       # Implementación
       return {"result": "success"}
   ```

2. Registre el router en `app/api/routes.py`:
   ```python
   from app.api.endpoints import new_endpoint
   
   router.include_router(new_endpoint.router, tags=["new"])
   ```

## Mejores Prácticas

### Manejo de Errores

Utilizar try-except para capturar y registrar errores:

```python
try:
    result = await some_function()
    return result
except Exception as e:
    logger.error(f"Error en some_function: {str(e)}", exc_info=True)
    raise HTTPException(status_code=500, detail="Error interno del servidor")
```

### Logging

Utilizar logging de manera efectiva:

```python
# Configurar logger
logger = logging.getLogger(__name__)

# Diferentes niveles según importancia
logger.debug("Información detallada para depuración")
logger.info("Información general sobre operaciones")
logger.warning("Advertencia sobre posibles problemas")
logger.error("Error que no impide la operación")
logger.critical("Error crítico que impide la operación")
```

### Operaciones Asíncronas

Utilizar async/await de manera consistente:

```python
async def some_function():
    # Operaciones asíncronas
    result1 = await async_operation1()
    result2 = await async_operation2()
    
    # Operaciones en paralelo
    results = await asyncio.gather(
        async_operation3(),
        async_operation4()
    )
    
    return process_results(result1, result2, results)
```

### Seguridad

Seguir buenas prácticas de seguridad:

- No hardcodear credenciales
- Utilizar HTTPS en producción
- Validar entradas de usuario
- Implementar límites de tasa (rate limiting)
- Seguir el principio de mínimo privilegio
