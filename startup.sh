#!/bin/bash

# Redirigir toda la salida del script a stdout/stderr para que Azure la capture
exec 1>&1 2>&2

# Habilitar modo de depuración para mostrar cada comando ejecutado
set -x

# Mostrar información del sistema para depuración
echo "===== SYSTEM INFORMATION ====="
echo "Memory Info:"
free -h || echo "WARNING: Failed to get memory info"
echo "CPU Info:"
cat /proc/cpuinfo | grep "model name" || echo "WARNING: Failed to get CPU info"
echo "Running Processes:"
ps aux || echo "WARNING: Failed to list processes"

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

# Mostrar otras variables de entorno relevantes
echo "PORT: ${PORT:-8000}"
echo "PYTHONPATH: $PYTHONPATH"
echo "PRODUCTION: $PRODUCTION"

# Verificar Python y dependencias críticas
echo "===== CHECKING PYTHON SETUP ====="
python --version || echo "ERROR: Python not found!"
echo "Python path: $PYTHONPATH"

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

# Verificar que el puerto 8000 no esté ocupado
echo "===== CHECKING NETWORK ====="
if netstat -tuln | grep ':8000'; then
    echo "WARNING: Port 8000 is already in use!"
else
    echo "Port 8000 is available"
fi

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
    app.main:app &
    
# Guardar el PID de gunicorn
GUNICORN_PID=$!

# Esperar unos segundos y verificar que gunicorn esté corriendo
sleep 5
if ps -p $GUNICORN_PID > /dev/null; then
    echo "Gunicorn started successfully with PID $GUNICORN_PID"
else
    echo "ERROR: Gunicorn failed to start!"
    exit 1
fi

# Mantener el script en ejecución (foreground) para que el contenedor no se detenga
wait $GUNICORN_PID || echo "ERROR: Gunicorn process terminated!"