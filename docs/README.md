# SvanIA - Asistente Técnico

SvanIA es un asistente técnico especializado en productos del Grupo SVAN (SVAN, WONDER, ASPES e HYUNDAI), diseñado para ayudar al personal del SAT (Servicio de Asistencia Técnica) con problemas técnicos.

## Descripción General

SvanIA es una aplicación web basada en FastAPI que integra servicios de Azure OpenAI, Azure Cognitive Search y Azure AI Foundry para proporcionar un asistente virtual capaz de:

- Responder consultas técnicas sobre productos del Grupo SVAN
- Buscar información en manuales técnicos
- Procesar imágenes para análisis visual
- Mantener conversaciones contextuales
- Almacenar y recuperar historiales de conversación

## Características Principales

- **Interfaz de Chat**: Interfaz web intuitiva para interactuar con el asistente
- **Procesamiento de Lenguaje Natural**: Utiliza modelos avanzados de OpenAI (GPT-4o-mini)
- **Búsqueda Cognitiva**: Integración con Azure Cognitive Search para consultar manuales técnicos
- **Análisis de Imágenes**: Capacidad para procesar y analizar imágenes adjuntas
- **Persistencia de Datos**: Almacenamiento de conversaciones en Redis
- **Optimización para HTTPS**: Implementa redirecciones y políticas de seguridad para entornos de producción

## Arquitectura

La aplicación sigue una arquitectura modular con los siguientes componentes principales:

- **Backend**: Implementado con FastAPI (Python)
- **Servicios de IA**: Integración con Azure OpenAI y Azure AI Foundry
- **Almacenamiento de Datos**: Redis para caché y persistencia
- **Búsqueda**: Azure Cognitive Search para indexación y búsqueda de documentos
- **Frontend**: Interfaz web implementada con HTML, CSS y JavaScript

## Requisitos

- Python 3.8+
- Redis
- Acceso a servicios de Azure (OpenAI, Cognitive Search, AI Foundry)
- Variables de entorno configuradas (ver archivo `.env.example`)

## Instalación

1. Clonar el repositorio
2. Instalar dependencias: `pip install -r requirements.txt`
3. Configurar variables de entorno en un archivo `.env`
4. Ejecutar la aplicación: `python run.py`

## Despliegue

La aplicación está configurada para desplegarse en Azure App Service, con soporte para:

- Docker (ver `Dockerfile` y `docker-compose.yml`)
- Despliegue directo mediante Git
- Configuración para entornos de producción

## Documentación Adicional

Para información más detallada sobre los componentes y funcionalidades de SvanIA, consulte los siguientes documentos:

- [Arquitectura](./arquitectura.md)
- [Servicios](./servicios.md)
- [API](./api.md)
- [Configuración](./configuracion.md)
- [Despliegue](./despliegue.md)
- [Guía de Desarrollo](./desarrollo.md)
- [Resolución de Problemas](./troubleshooting.md)
