# Technical Support AI Assistant / Asistente IA de Soporte Técnico

Este proyecto es un asistente técnico genérico orientado a manuales y documentación de producto, diseñado para ayudar al personal de soporte con problemas técnicos.

## Descripción General

Technical Support AI Assistant es una aplicación web basada en FastAPI que integra Azure AI Foundry, Azure AI Search y Redis para proporcionar un asistente virtual capaz de:

- Responder consultas técnicas sobre productos documentados en manuales
- Buscar información en manuales técnicos
- Procesar imágenes para análisis visual
- Mantener conversaciones contextuales
- Almacenar y recuperar historiales de conversación

## Características Principales

- **Interfaz de Chat**: Interfaz web intuitiva para interactuar con el asistente
- **Procesamiento de Lenguaje Natural**: Utiliza despliegues de modelos en Azure AI Foundry
- **Búsqueda Cognitiva**: Integración con Azure Cognitive Search para consultar manuales técnicos
- **Análisis de Imágenes**: Capacidad para procesar y analizar imágenes adjuntas
- **Persistencia de Datos**: Almacenamiento de conversaciones en Redis
- **Optimización para HTTPS**: Implementa redirecciones y políticas de seguridad para entornos de producción

## Arquitectura

La aplicación sigue una arquitectura modular con los siguientes componentes principales:

- **Backend**: Implementado con FastAPI (Python)
- **Servicios de IA**: Integración Microsoft-first con Azure AI Foundry
- **Almacenamiento de Datos**: Redis para caché y persistencia
- **Búsqueda**: Azure Cognitive Search para indexación y búsqueda de documentos
- **Frontend**: Interfaz web implementada con HTML, CSS y JavaScript

## Requisitos

- Python 3.8+
- Redis
- Acceso a servicios de Azure (AI Foundry, AI Search, Redis)
- Variables de entorno configuradas (ver archivo `.env.example`)

## Instalación

1. Clonar el repositorio
2. Instalar dependencias: `pip install -r requirements.txt`
3. Configurar variables de entorno en un archivo `.env`
4. Ejecutar la aplicación: `python run.py`
5. Abrir `http://127.0.0.1:8000`

## Despliegue

La aplicación está configurada para desplegarse en Azure App Service, con soporte para:

- Docker (ver `Dockerfile` y `docker-compose.yml`)
- Despliegue directo mediante Git
- Configuración para entornos de producción

## Consideraciones de seguridad del MVP

- Los endpoints de debug y diagnóstico quedan desactivados por defecto y solo se habilitan con `ENABLE_DEBUG_ENDPOINTS=true`.
- El runtime local usa el puerto `8000` de forma consistente con `run.py`, `README.md` y el contenedor.
- En producción conviene declarar `ALLOWED_HOSTS` y `CORS_ALLOW_ORIGINS` de forma explícita.

## Documentación Adicional

Para información más detallada sobre los componentes y funcionalidades del asistente, consulte los siguientes documentos:

- [Arquitectura](./arquitectura.md)
- [Arquitectura Azure MVP](./arquitectura_azure_mvp.md)
- [Servicios](./servicios.md)
- [API](./api.md)
- [Configuración](./configuracion.md)
- [Despliegue](./despliegue.md)
- [Guía de Desarrollo](./desarrollo.md)
- [Resolución de Problemas](./troubleshooting.md)
