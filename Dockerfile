# Etapa 1: Compilar recursos estáticos (CSS, JavaScript) con Node.js
FROM node:18 AS builder

WORKDIR /app

# Copiar package.json y package-lock.json para instalar dependencias
COPY package.json package-lock.json ./

# Instalar dependencias de Node.js
RUN npm install

# Copiar el resto del código
COPY . .

# Compilar los recursos estáticos
RUN npm run build:css

# Etapa 2: Construir la imagen final con Python
FROM python:3.12-slim

# Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRODUCTION=true \
    PORT=8000

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libmagic1 \
    vim \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Instalar Tesseract OCR y dependencias para procesamiento de imágenes (Punto 7)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar Gunicorn para producción (Punto 8)
RUN pip install gunicorn

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar los archivos de requisitos primero para aprovechar la caché de Docker
COPY requirements.txt .

# Añadir dependencias faltantes al requirements.txt
RUN echo "cachetools>=5.3.0" >> requirements.txt && \
    echo "tenacity>=8.2.0" >> requirements.txt && \
    echo "httpx>=0.24.0" >> requirements.txt && \
    echo "psutil>=5.9.0" >> requirements.txt

# Instalación de dependencias con logs verbosos
RUN pip install --no-cache-dir -v -r requirements.txt 2>&1 | tee /app/pip_install_log.txt

# Verificar que las dependencias clave estén instaladas
RUN pip list | grep cachetools || echo "ERROR: cachetools NO INSTALADO" && \
    pip list | grep tenacity || echo "ERROR: tenacity NO INSTALADO" && \
    pip list | grep httpx || echo "ERROR: httpx NO INSTALADO" && \
    pip list | grep psutil || echo "ERROR: psutil NO INSTALADO" && \
    pip list > /app/installed_packages.txt

# Copiar los recursos compilados desde la etapa de build
COPY --from=builder /app/static /app/static

# Copiar el resto del código
COPY . .

# Crear script de verificación de importaciones para el debuggeo
RUN echo "import sys; print('Python version:', sys.version); print('Sys path:', sys.path); import cachetools; print('cachetools version:', cachetools.__version__); print('cachetools imported successfully!')" > /app/verify_imports.py

# Crear directorios necesarios y establecer permisos
RUN mkdir -p /app/uploads /app/Manuales /app/temp /app/logs && \
    chown -R 1000:1000 /app/uploads /app/Manuales /app/temp /app/logs

# Crear un usuario no root
RUN adduser --disabled-password --gecos '' --uid 1000 appuser
RUN chown -R appuser:appuser /app
USER appuser

# Exponer el puerto que usa la aplicación
EXPOSE 8000

# Verificar la salud de la aplicación
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Crear un script para depurar el arranque
RUN echo '#!/bin/bash\necho "===== CHECKING PYTHON IMPORTS ====="\npython /app/verify_imports.py\necho "===== INSTALLED PACKAGES ====="\ncat /app/installed_packages.txt\necho "===== PIP INSTALL LOG ====="\ncat /app/pip_install_log.txt\necho "===== STARTING APPLICATION ====="\nexec gunicorn -w 4 -k uvicorn.workers.UvicornWorker --timeout 90 --graceful-timeout 30 --keep-alive 5 --max-requests 1000 --max-requests-jitter 50 app.main:app --bind 0.0.0.0:8000 --log-level debug' > /app/startup.sh && \
    chmod +x /app/startup.sh

# Comando para ejecutar la aplicación con Gunicorn (Punto 8)
CMD ["/app/startup.sh"]