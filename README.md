# Technical Support AI Assistant / Asistente IA de Soporte Técnico

[English](#english) · [Español](#español)

---

## English

### Overview

Technical Support AI Assistant is a FastAPI-based reference project for building a support assistant over technical manuals and product documentation, positioned as a Microsoft-first MVP on Azure.

It combines:

- **Azure AI Foundry model deployments** for response generation and multimodal reasoning
- **Azure AI Search** for retrieval over indexed manuals
- **Redis** for short-term memory and response caching
- **Jinja2 + Tailwind CSS** for a lightweight web UI

This repository has been sanitized to be **generic and reusable**. It is no longer tied to any specific company or product catalog.

The codebase still contains some Azure OpenAI-compatible transport and environment variable names. That compatibility layer is intentional for now to keep the MVP functional while the remaining migration to the latest Foundry patterns is completed incrementally.

### Current status

This is a **reference implementation / MVP codebase**. It is useful for learning, experimentation, and as a starting point for enterprise support copilots, but it still needs hardening before a production-grade public release.

### Key features

- Chat-style technical support interface
- Retrieval over manuals and structured support content
- Optional image analysis / multimodal extensions
- Redis-backed session and response caching
- FastAPI backend with HTML frontend served from the same app
- Microsoft-first deployment path

### Tech stack

- **Backend**: FastAPI, Jinja2, Python
- **AI**: Azure AI Foundry model deployments
- **Search**: Azure AI Search
- **Cache**: Redis
- **Frontend styling**: Tailwind CSS
- **Deployment**: Azure App Service or Azure Container Apps
- **Recommended security/compliance add-ons**: Azure Key Vault, Application Insights, Microsoft Entra ID

### Quick start

```bash
git clone https://github.com/Nambu89/Asistente-IA-SAT.git
cd Asistente-IA-SAT

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
npm install

cp .env.example .env
# fill in your Azure + Redis values

python run.py
```

Open:

`http://127.0.0.1:8000`

### Environment variables

Use `.env.example` as the reference template.

Main variables:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `PORT`
- `ENABLE_DEBUG_ENDPOINTS`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `AZURE_SEARCH_INDEX_NAME`
- `REDIS_HOST`
- `REDIS_PASSWORD`
- `REDIS_PORT`

### Security defaults in this repo

- debug and diagnostic endpoints are disabled by default via `ENABLE_DEBUG_ENDPOINTS=false`
- the local runtime and docs now use port `8000` consistently
- `TrustedHostMiddleware` defaults to explicit local hosts instead of wildcard hosts
- the container filesystem no longer relies on world-writable `777` permissions

### Recommended Microsoft deployment path

#### Option A — Azure App Service

Good for:
- fast deployment
- simple hosting
- small/medium workloads

#### Option B — Azure Container Apps

Good for:
- container-first deployments
- more control over scaling
- cleaner path to background jobs and future microservices

### Recommended Microsoft production services

- **Azure AI Foundry**
- **Azure AI Search**
- **Azure Cache for Redis**
- **Azure Key Vault**
- **Azure Monitor + Application Insights**
- **Microsoft Entra ID** (optional authentication layer)

### Repository hygiene notes

Before making this repository public, you should still:

1. rotate any credentials that may have been committed in history
2. purge git history if required
3. remove any non-source artifacts still tracked locally
4. add tests and CI
5. validate all prompts and public-facing copy

### Open-source roadmap

Suggested next steps:

- complete the remaining migration from Azure OpenAI-compatible transport to the latest Foundry calling pattern (`/openai/v1/`)
- replace legacy prompt/config coupling with cleaner adapters
- add tests for routes, retrieval, and caching
- add GitHub Actions CI
- optionally split backend services more clearly

### Documentation / Documentación

- [Documentation index / Índice de documentación](docs/README.md)
- [Azure MVP architecture diagram / Diagrama Azure MVP](docs/arquitectura_azure_mvp.md)
- [Diagram placeholders / Marcadores para diagramas](docs/diagrams/README.md)

### License

MIT

---

## Español

### Descripción general

Technical Support AI Assistant es un proyecto de referencia basado en FastAPI para construir un asistente de soporte técnico sobre manuales y documentación de producto, planteado como un MVP Microsoft-first sobre Azure.

Combina:

- **Despliegues de modelos en Azure AI Foundry** para generación de respuestas y razonamiento multimodal
- **Azure AI Search** para recuperación sobre manuales indexados
- **Redis** para memoria de corto plazo y caché de respuestas
- **Jinja2 + Tailwind CSS** para una interfaz web ligera

Este repositorio ha sido saneado para que sea **genérico y reutilizable**. Ya no está ligado a una empresa ni a un catálogo concreto.

El código todavía conserva parte del transporte y algunas variables de entorno con naming compatible con Azure OpenAI. Esa capa de compatibilidad se mantiene de forma deliberada para no romper el MVP mientras la migración restante al patrón más actual de Foundry se hace por fases.

### Estado actual

Se trata de una **implementación de referencia / MVP**. Es útil para aprendizaje, experimentación y como punto de partida para copilotos de soporte enterprise, pero aún necesita endurecimiento antes de considerarse una release pública lista para producción.

### Funcionalidades principales

- Interfaz conversacional de soporte técnico
- Recuperación sobre manuales y documentación estructurada
- Extensión opcional a análisis de imágenes / multimodalidad
- Caché de sesiones y respuestas con Redis
- Backend FastAPI con frontend HTML servido desde la misma aplicación
- Ruta de despliegue orientada a tecnologías Microsoft

### Stack tecnológico

- **Backend**: FastAPI, Jinja2, Python
- **IA**: despliegues de modelos en Azure AI Foundry
- **Búsqueda**: Azure AI Search
- **Caché**: Redis
- **Estilos frontend**: Tailwind CSS
- **Despliegue**: Azure App Service o Azure Container Apps
- **Servicios recomendados de seguridad/operación**: Azure Key Vault, Application Insights, Microsoft Entra ID

### Inicio rápido

```bash
git clone https://github.com/Nambu89/Asistente-IA-SAT.git
cd Asistente-IA-SAT

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
npm install

cp .env.example .env
# rellena las variables de Azure + Redis

python run.py
```

Abrir en navegador:

`http://127.0.0.1:8000`

### Variables de entorno

Usa `.env.example` como plantilla de referencia.

Variables principales:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `PORT`
- `ENABLE_DEBUG_ENDPOINTS`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `AZURE_SEARCH_INDEX_NAME`
- `REDIS_HOST`
- `REDIS_PASSWORD`
- `REDIS_PORT`

### Defaults de seguridad aplicados en este repo

- los endpoints de debug y diagnóstico vienen desactivados por defecto con `ENABLE_DEBUG_ENDPOINTS=false`
- runtime local y documentación quedan alineados en el puerto `8000`
- `TrustedHostMiddleware` deja de permitir wildcard por defecto en local
- el contenedor ya no depende de permisos globales `777`

### Ruta recomendada de despliegue en Microsoft

#### Opción A — Azure App Service

Buena para:
- despliegue rápido
- hosting sencillo
- cargas pequeñas o medias

#### Opción B — Azure Container Apps

Buena para:
- despliegues container-first
- mayor control del escalado
- evolución futura hacia jobs o microservicios

### Servicios Microsoft recomendados para producción

- **Azure AI Foundry**
- **Azure AI Search**
- **Azure Cache for Redis**
- **Azure Key Vault**
- **Azure Monitor + Application Insights**
- **Microsoft Entra ID** (opcional como capa de autenticación)

### Notas de higiene del repositorio

Antes de hacer este repositorio público conviene todavía:

1. rotar cualquier credencial que haya podido quedar en el historial
2. purgar el historial git si hace falta
3. eliminar artefactos no fuente aún trackeados localmente
4. añadir tests y CI
5. revisar prompts y textos públicos

### Hoja de ruta open-source

Siguientes pasos recomendados:

- completar la migración restante desde transporte compatible con Azure OpenAI al patrón actual de Foundry (`/openai/v1/`)
- desacoplar prompts y configuración legacy
- añadir tests de rutas, retrieval y caché
- añadir GitHub Actions CI
- opcionalmente separar mejor los servicios del backend

### Licencia

MIT
