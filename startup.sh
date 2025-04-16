#!/bin/bash

# Habilitar modo de depuración para mostrar cada comando ejecutado
set -x

# Verificar directorios y permisos
echo "===== CHECKING DIRECTORIES ====="
ls -la /app || echo "WARNING: Failed to list /app directory"
ls -la /app/uploads /app/Manuales /app/temp /app/logs || echo "WARNING: Failed to list subdirectories"

# Verificar variables de entorno críticas (sin exponer valores completos)
echo "===== CHECKING ENVIRONMENT VARIABLES ====="
if [ -n "$AZURE_OPENAI_API_KEY" ]; then 
    echo "AZURE_OPENAI_API_KEY: [CONFIGURED]"
else
    echo "ERROR: AZURE_OPENAI_API_KEY not set!"
fi

if [ -n "$AZURE_OPENAI_ENDPOINT" ]; then 
    echo "AZURE_OPENAI_ENDPOINT: [CONFIGURED]"
else
    echo "ERROR: AZURE_OPENAI_ENDPOINT not set!"
fi

if [ -n "$AZURE_SEARCH_ENDPOINT" ]; then 
    echo "AZURE_SEARCH_ENDPOINT: [CONFIGURED]"
else
    echo "ERROR: AZURE_SEARCH_ENDPOINT not set!"
fi

# Verificar Python y dependencias críticas
echo "===== CHECKING PYTHON SETUP ====="
python --version || echo "ERROR: Python not found!"
echo "Python path: $PYTHONPATH"

# Verificar que se pueden importar módulos críticos
# Verificar que se pueden importar módulos críticos
python -c "import fastapi; import redis; import azure.storage.blob; import azure.search.documents; import cachetools; import tenacity; import httpx; import psutil; print(\"All critical imports successful!\")" || {
    echo "ERROR: Failed to import critical modules!"
    echo "Checking individual imports:"
    python -c "import fastapi" || echo "Failed to import fastapi"
    python -c "import redis" || echo "Failed to import redis"
    python -c "import azure.storage.blob" || echo "Failed to import azure.storage.blob"
    python -c "import azure.search.documents" || echo "Failed to import azure.search.documents"
    python -c "import cachetools" || echo "Failed to import cachetools"
    python -c "import tenacity" || echo "Failed to import tenacity"
    python -c "import httpx" || echo "Failed to import httpx"
    python -c "import psutil" || echo "Failed to import psutil"
}

# Iniciar la aplicación con configuración productiva
echo "===== STARTING APPLICATION ====="
export PYTHONPATH=/app
gunicorn \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --timeout 90 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --capture-output \
    --bind 0.0.0.0:8000 \
    app.main:app || echo "ERROR: Failed to start gunicorn!"