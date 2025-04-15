# Usar una imagen base de Python 3.12
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
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar los archivos de requisitos primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Tesseract OCR para procesamiento de imágenes
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Copiar el resto del código
COPY . .

# Crear directorios necesarios
RUN mkdir -p /app/uploads /app/Manuales /app/temp /app/logs

# Compilar los recursos estáticos (CSS, JavaScript)
RUN npm install
RUN npm run build:css

# Exponer el puerto que usa la aplicación
EXPOSE 8000

# Crear un usuario no root
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Verificar la salud de la aplicación
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando para ejecutar la aplicación
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]