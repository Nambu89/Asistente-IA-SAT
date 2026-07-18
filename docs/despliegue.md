# Guía de Despliegue de Technical Support AI Assistant

Este documento describe los pasos para desplegar la aplicación en diferentes entornos, con énfasis en Azure App Service.

## Índice

1. [Requisitos Previos](#requisitos-previos)
2. [Despliegue Local](#despliegue-local)
3. [Despliegue en Azure App Service](#despliegue-en-azure-app-service)
4. [Despliegue con Docker](#despliegue-con-docker)
5. [Configuración Post-Despliegue](#configuración-post-despliegue)
6. [Solución de Problemas de Despliegue](#solución-de-problemas-de-despliegue)

## Requisitos Previos

Antes de desplegar la aplicación, asegúrese de tener:

- Acceso a los servicios de Azure necesarios:
  - Azure OpenAI
  - Azure Cognitive Search
  - Azure Cache for Redis
  - Azure App Service (para despliegue en la nube)
- Variables de entorno configuradas (ver [Configuración](./configuracion.md))
- Python 3.8+ instalado (para despliegue local)
- Docker instalado (para despliegue con contenedores)
- Git instalado (para despliegue mediante Git)

## Despliegue Local

Para desplegar la aplicación en un entorno local:

1. Clone el repositorio:
   ```bash
   git clone <url-del-repositorio>
   cd Asistente-IA-SAT
   ```

2. Cree y active un entorno virtual:
   ```bash
   python -m venv venv
   # En Windows
   venv\Scripts\activate
   # En Linux/Mac
   source venv/bin/activate
   ```

3. Instale las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Cree un archivo `.env` con las variables de entorno necesarias (ver [Configuración](./configuracion.md))

5. Ejecute la aplicación:
   ```bash
   python run.py
   ```

6. Acceda a la aplicación en `http://localhost:8000`

## Despliegue en Azure App Service

La aplicación está optimizada para desplegarse en Azure App Service. Siga estos pasos:

### Opción 1: Despliegue mediante Git

1. Cree un App Service en Azure Portal:
   - Seleccione Python 3.8 o superior como runtime
   - Configure el plan de servicio según sus necesidades

2. Configure la integración continua:
   - En la sección "Deployment Center", seleccione Git como fuente
   - Configure las credenciales de despliegue
   - Conecte su repositorio Git

3. Configure las variables de entorno:
   - En la sección "Configuration", añada todas las variables de entorno necesarias
   - Asegúrese de establecer `PRODUCTION=True`

4. Despliegue la aplicación:
   ```bash
   git push azure main
   ```

### Opción 2: Despliegue mediante Azure CLI

1. Instale Azure CLI y inicie sesión:
   ```bash
   az login
   ```

2. Cree un grupo de recursos (si no existe):
   ```bash
    az group create --name support-ai-assistant-rg --location westeurope
   ```

3. Cree un plan de App Service:
   ```bash
    az appservice plan create --name support-ai-assistant-plan --resource-group support-ai-assistant-rg --sku B1 --is-linux
   ```

4. Cree la App Service:
   ```bash
    az webapp create --name support-ai-assistant --resource-group support-ai-assistant-rg --plan support-ai-assistant-plan --runtime "PYTHON|3.8"
   ```

5. Configure las variables de entorno:
   ```bash
    az webapp config appsettings set --name support-ai-assistant --resource-group support-ai-assistant-rg --settings PRODUCTION=True WEBSITES_PORT=8000 ...
   ```

6. Despliegue el código:
   ```bash
    az webapp deployment source config --name support-ai-assistant --resource-group support-ai-assistant-rg --repo-url <url-del-repositorio> --branch main --manual-integration
   ```

### Configuración del Archivo .deployment

El archivo `.deployment` en la raíz del proyecto configura cómo Azure App Service despliega la aplicación:

```
[config]
SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

### Configuración del Archivo web.config

El archivo `web.config` configura el servidor web en Azure App Service:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="PythonHandler" path="*" verb="*" modules="httpPlatformHandler" resourceType="Unspecified"/>
    </handlers>
    <httpPlatform processPath="%HOME%\site\wwwroot\startup.sh"
                  arguments=""
                  stdoutLogEnabled="true"
                  stdoutLogFile="%HOME%\LogFiles\stdout"
                  startupTimeLimit="60"
                  processesPerApplication="1">
      <environmentVariables>
        <environmentVariable name="PYTHONPATH" value="%HOME%\site\wwwroot"/>
        <environmentVariable name="PORT" value="%HTTP_PLATFORM_PORT%"/>
      </environmentVariables>
    </httpPlatform>
  </system.webServer>
</configuration>
```

### Script de Inicio (startup.sh)

El script `startup.sh` se ejecuta al iniciar la aplicación en Azure App Service:

```bash
#!/bin/bash

# Activar entorno virtual si existe, o crear uno nuevo
if [ -d "venv" ]; then
    echo "Activando entorno virtual existente..."
    source venv/bin/activate
else
    echo "Creando nuevo entorno virtual..."
    python -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Iniciar la aplicación
echo "Iniciando aplicación..."
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind=0.0.0.0:$PORT
```

## Despliegue con Docker

El proyecto incluye configuración para despliegue con Docker:

### Dockerfile

```dockerfile
FROM python:3.8-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Variables de entorno
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Exponer puerto
EXPOSE 8000

# Comando de inicio
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]
```

### Docker Compose

```yaml
version: '3'

services:
  support-ai-assistant:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
```

### Pasos para Despliegue con Docker

1. Construya la imagen:
   ```bash
   docker-compose build
   ```

2. Inicie los contenedores:
   ```bash
   docker-compose up -d
   ```

3. Verifique los logs:
   ```bash
   docker-compose logs -f
   ```

## Configuración Post-Despliegue

Después de desplegar la aplicación, realice las siguientes configuraciones:

### Configuración de HTTPS

Asegúrese de que HTTPS esté habilitado:

1. En Azure App Service, vaya a "TLS/SSL settings" y habilite "HTTPS Only"
2. Configure un certificado SSL (Azure proporciona uno por defecto para *.azurewebsites.net)
3. Verifique que el middleware HTTPSRedirectMiddleware esté funcionando correctamente

### Configuración de CORS

Actualice la configuración de CORS según sea necesario:

1. Edite el archivo `cors.json` para incluir los dominios permitidos
2. Asegúrese de que la configuración de CORS en `main.py` coincida con `cors.json`

### Monitoreo y Logging

Configure el monitoreo y logging:

1. En Azure App Service, habilite "Application Insights" para monitoreo avanzado
2. Configure alertas para errores y problemas de rendimiento
3. Revise los logs regularmente a través del endpoint `/logs` o en Azure Portal

## Solución de Problemas de Despliegue

### Problemas de Contenido Mixto HTTP/HTTPS

Si experimenta problemas de contenido mixto HTTP/HTTPS:

1. Asegúrese de que el middleware HTTPSRedirectMiddleware esté configurado correctamente
2. Añada un meta tag Content-Security-Policy con upgrade-insecure-requests en las plantillas HTML:
   ```html
   <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
   ```
3. Implemente la función ensureHttps() en el frontend para asegurar que todas las URLs sean HTTPS en producción
4. Cree una función secureAllResources() para convertir automáticamente todos los recursos a HTTPS

### Problemas de Conexión con Redis

Si experimenta problemas de conexión con Redis:

1. Verifique las credenciales y configuración de Redis en las variables de entorno
2. Asegúrese de que el firewall permita conexiones desde Azure App Service
3. Utilice el endpoint `/diagnostico/redis` para obtener información detallada sobre la conexión

### Problemas de Memoria

Si experimenta problemas de memoria:

1. Ajuste el número de workers en gunicorn según los recursos disponibles
2. Configure límites de memoria adecuados en Azure App Service
3. Implemente limpieza periódica de caché y sesiones antiguas

### Problemas de Rendimiento

Si experimenta problemas de rendimiento:

1. Ajuste la configuración de caché para optimizar el rendimiento
2. Verifique el rendimiento de Azure Cognitive Search y optimice las consultas
3. Monitoree el uso de CPU y memoria en Azure Portal
