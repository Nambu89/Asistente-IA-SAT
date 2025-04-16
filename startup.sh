#!/bin/bash

# Verificar directorios y permisos
echo "===== CHECKING DIRECTORIES ====="
ls -la /app
ls -la /app/uploads /app/Manuales /app/temp /app/logs

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
python --version
echo "Python path: $PYTHONPATH"

# Verificar que se pueden importar módulos críticos
python -c "import fastapi; import redis; import azure; import cachetools; import tenacity; import httpx; import psutil; print(\"All critical imports successful!\")" || echo "ERROR: Failed to import critical modules"

# Iniciar la aplicación con configuración productiva
echo "===== STARTING APPLICATION ====="
export PYTHONPATH=/app
exec gunicorn \
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
    app.main:app