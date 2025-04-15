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

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar los recursos compilados desde la etapa de build
COPY --from=builder /app/static /app/static

# Copiar el resto del código
COPY . .

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

# Documentar variables de entorno esperadas
# En Azure App Service, configura estas variables en el portal:
# APP_INSIGHTS_INSTRUMENTATION_KEY=YOUR_KEY
# REDIS_HOST=svania.northeurope.redis.azure.net
# REDIS_PORT=6380
# REDIS_PASSWORD=<tu-clave-primaria>
# REDIS_SSL=True
# WEB_CONCURRENCY=4

# Comando para ejecutar la aplicación con Gunicorn (Punto 8)
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000", "--log-level", "info"]