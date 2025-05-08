# Arquitectura de SvanIA

## Visión General

SvanIA sigue una arquitectura modular basada en servicios, diseñada para proporcionar un asistente técnico inteligente y escalable. La aplicación está construida sobre FastAPI y se integra con varios servicios de Azure para proporcionar funcionalidades avanzadas de IA.

## Diagrama de Arquitectura

```
+------------------+     +------------------+     +------------------+
|                  |     |                  |     |                  |
|  Cliente Web     |<--->|  Backend FastAPI |<--->|  Redis Cache     |
|  (HTML/JS/CSS)   |     |  (Python)        |     |                  |
|                  |     |                  |     |                  |
+------------------+     +--------+---------+     +------------------+
                                  |
                                  |
                         +--------v---------+
                         |                  |
                         |  Middleware      |
                         |  (HTTPS, CORS)   |
                         |                  |
                         +--------+---------+
                                  |
                                  |
          +---------------------+-+------------------+
          |                     |                    |
+---------v----------+ +--------v---------+ +--------v---------+
|                    | |                  | |                  |
| Azure OpenAI       | | Azure Cognitive  | | Azure AI Foundry |
| (GPT-4o-mini)      | | Search           | | (Análisis de     |
|                    | |                  | | imágenes)        |
+--------------------+ +------------------+ +------------------+
```

## Componentes Principales

### 1. Backend (FastAPI)

El backend está implementado con FastAPI, un framework moderno de Python para crear APIs con alto rendimiento. Los principales componentes del backend son:

- **main.py**: Punto de entrada principal que configura la aplicación, middleware y rutas
- **standalone.py**: Implementa el servicio de chat completo con procesamiento de mensajes y archivos
- **Servicios**: Módulos que encapsulan la lógica de integración con servicios externos
- **API Routes**: Endpoints que exponen las funcionalidades de la aplicación
- **Modelos**: Definiciones de datos utilizados en la aplicación

### 2. Servicios de IA

SvanIA integra varios servicios de IA de Azure:

- **Azure OpenAI**: Proporciona modelos de lenguaje avanzados (GPT-4o-mini) para generar respuestas contextuales
- **Azure Cognitive Search**: Permite buscar información relevante en manuales técnicos
- **Azure AI Foundry**: Proporciona capacidades de análisis de imágenes y OCR

### 3. Almacenamiento de Datos

- **Redis**: Utilizado para:
  - Caché de respuestas frecuentes
  - Almacenamiento de historiales de conversación
  - Persistencia de sesiones de usuario

### 4. Frontend

- **HTML/CSS/JavaScript**: Interfaz de usuario simple e intuitiva
- **Jinja2 Templates**: Sistema de plantillas para renderizar páginas HTML
- **Static Files**: Archivos CSS, JavaScript e imágenes

## Flujo de Datos

1. El usuario envía un mensaje a través de la interfaz web
2. El backend recibe la solicitud y extrae la información relevante
3. Si el mensaje contiene imágenes, se procesan con Azure AI Foundry
4. Se busca información relevante en manuales técnicos mediante Azure Cognitive Search
5. Se genera una respuesta utilizando Azure OpenAI
6. La respuesta se envía al usuario y se almacena en el historial de conversación
7. El historial se guarda en Redis para futuras referencias

## Consideraciones de Seguridad

- **HTTPS**: Middleware para forzar HTTPS en producción
- **CORS**: Configuración restrictiva para prevenir solicitudes no autorizadas
- **TrustedHost**: Limitación de hosts permitidos
- **Manejo de Errores**: Captura y registro de excepciones sin exponer detalles sensibles

## Escalabilidad

La arquitectura está diseñada para ser escalable:

- **Servicios Stateless**: Los componentes principales no mantienen estado
- **Caché Distribuida**: Redis permite escalar horizontalmente
- **Asincronía**: Uso extensivo de operaciones asíncronas para mejorar el rendimiento

## Patrones de Diseño

- **Singleton**: Utilizado para servicios que deben tener una única instancia
- **Repository**: Abstracción del acceso a datos
- **Dependency Injection**: Inyección de dependencias para facilitar pruebas y mantenimiento
- **Async/Await**: Patrón para operaciones asíncronas
