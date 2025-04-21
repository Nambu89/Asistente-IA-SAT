# Etapa 1: Compilar recursos estáticos (CSS, JavaScript) con Node.js
FROM node:18 AS builder

WORKDIR /app

# Copiar package.json y package-lock.json para instalar dependencias
COPY package.json package-lock.json ./

# Instalar dependencias de Node.js
RUN npm install

# Copiar el resto del código para la compilación de assets
COPY static/ ./static/
COPY postcss.config.js tailwind.config.js ./

# Compilar los recursos estáticos
RUN npm run build:css

# Etapa 2: Construir la imagen final con Python
FROM python:3.12-slim

# Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRODUCTION=true \
    PORT=8000 \
    PYTHONPATH=/app

# Instalar dependencias del sistema incluyendo herramientas de depuración
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libmagic1 \
    procps \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Instalar Tesseract OCR y dependencias para procesamiento de imágenes
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar requirements.txt y garantizar que contenga todas las dependencias necesarias
COPY requirements.txt .

# Asegurar que las dependencias críticas estén en requirements.txt
RUN grep -q "cachetools" requirements.txt || echo "cachetools>=5.3.0" >> requirements.txt && \
    grep -q "tenacity" requirements.txt || echo "tenacity>=8.2.0" >> requirements.txt && \
    grep -q "httpx" requirements.txt || echo "httpx>=0.24.0" >> requirements.txt && \
    grep -q "psutil" requirements.txt || echo "psutil>=5.9.0" >> requirements.txt

# Instalación de dependencias con logs menos verbosos para un inicio más rápido
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn==21.0.1 uvicorn==0.27.1

# Copiar los recursos estáticos compilados desde la etapa de build
COPY --from=builder /app/static/css/styles.min.css /app/static/css/

# Copiar el script de inicio
COPY startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Crear directorios necesarios con permisos amplios
RUN mkdir -p /app/uploads /app/Manuales /app/temp /app/logs && \
    chmod -R 777 /app/uploads /app/Manuales /app/temp /app/logs

# Copiar el resto del código de la aplicación
COPY app/ /app/app/
COPY templates/ /app/templates/
COPY static/ /app/static/

# Crear usuario no root, pero mantener permisos amplios para directorios críticos
RUN adduser --disabled-password --gecos '' --uid 1000 appuser
RUN chown -R appuser:appuser /app

# Cambiar al usuario no root
USER appuser

# Exponer el puerto que usa la aplicación
EXPOSE 8000

# Verificar la salud de la aplicación con tiempo de inicio más amplio
HEALTHCHECK --interval=30s --timeout=10s --start-period=240s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Usar el script de inicio
CMD ["/app/startup.sh"]