# SvanIA - Asistente Técnico

![SvanIA Logo](static/images/logo.png)

SvanIA es un asistente técnico especializado en productos del Grupo SVAN (SVAN, WONDER, ASPES e HYUNDAI), diseñado para ayudar al personal del SAT (Servicio de Asistencia Técnica) con problemas técnicos.

## Descripción

SvanIA utiliza tecnologías avanzadas de inteligencia artificial para proporcionar asistencia técnica precisa y contextual. La aplicación integra:

- **Azure OpenAI (GPT-4o-mini)** para generación de respuestas inteligentes
- **LangChain** para mejorar el contexto y la búsqueda semántica
- **Azure Cognitive Search** para búsqueda en manuales técnicos
- **Azure AI Foundry** para análisis de imágenes
- **Redis** para caché y persistencia de datos

## Características Principales

- 💬 **Chat Interactivo**: Interfaz de conversación natural y contextual
- 🧠 **Contexto Mejorado**: LangChain mantiene mejor el hilo de las conversaciones
- 🔍 **Búsqueda Vectorial**: Encuentra información semánticamente relevante en manuales técnicos
- 📊 **Análisis de Imágenes**: Procesa imágenes para diagnóstico visual
- 📱 **Diseño Responsivo**: Funciona en dispositivos móviles y de escritorio
- 🔒 **Seguridad Optimizada**: Implementa HTTPS y políticas de seguridad

## Inicio Rápido

```bash
# Clonar el repositorio
git clone <url-del-repositorio>
cd SvanIA

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con las credenciales necesarias

# Ejecutar la aplicación
python run.py
```

## Documentación

La documentación completa está disponible en el directorio [docs](./docs):

- [Guía General](./docs/README.md)
- [Arquitectura](./docs/arquitectura.md)
- [Servicios](./docs/servicios.md)
- [API](./docs/api.md)
- [Configuración](./docs/configuracion.md)
- [Despliegue](./docs/despliegue.md)
- [Guía de Desarrollo](./docs/desarrollo.md)
- [Resolución de Problemas](./docs/troubleshooting.md)

## Requisitos

- Python 3.8+
- Redis
- LangChain 0.3.25+
- Acceso a servicios de Azure (OpenAI, Cognitive Search, AI Foundry)
- Variables de entorno configuradas (ver archivo `.env.example`)
- Modelo de embeddings para búsqueda vectorial (por defecto: text-embedding-ada-002)

## Despliegue

SvanIA está optimizado para desplegarse en Azure App Service. Consulte la [guía de despliegue](./docs/despliegue.md) para obtener instrucciones detalladas.

## Seguridad

La aplicación implementa diversas medidas de seguridad:

- Forzado de HTTPS en producción
- Configuración restrictiva de CORS
- Middleware de hosts confiables
- Manejo seguro de errores

Consulte la [documentación de seguridad](./docs/configuracion.md#configuración-de-seguridad) para más detalles.

## Contribuir

Si desea contribuir al desarrollo de SvanIA, consulte la [guía de desarrollo](./docs/desarrollo.md) para obtener información sobre el entorno de desarrollo, estructura del proyecto y mejores prácticas.

## Licencia

Propiedad de Fernando Prada. Todos los derechos reservados.

## Contacto

Para soporte o consultas, contacte con el equipo de desarrollo de SvanIA.
