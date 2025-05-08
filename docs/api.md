# API de SvanIA

Este documento describe los endpoints de la API de SvanIA, sus parámetros, respuestas y ejemplos de uso.

## Índice

1. [Endpoints Principales](#endpoints-principales)
2. [Endpoints de Chat](#endpoints-de-chat)
3. [Endpoints de Diagnóstico](#endpoints-de-diagnóstico)
4. [Endpoints de Manuales](#endpoints-de-manuales)
5. [Manejo de Errores](#manejo-de-errores)

## Endpoints Principales

### GET /

**Descripción**: Ruta principal que sirve la interfaz de chat.

**Respuesta**: Retorna la página HTML de la interfaz de chat.

**Ejemplo de uso**:
```
GET /
```

### GET /health

**Descripción**: Endpoint para verificar el estado del servicio.

**Respuesta**: Retorna un objeto JSON con información sobre el estado de los servicios.

**Ejemplo de respuesta**:
```json
{
  "app": "ok",
  "version": "1.1.0",
  "timestamp": "2025-05-08T09:13:57+02:00",
  "services": {
    "redis": "ok",
    "azure_search": "ok"
  }
}
```

### POST /feedback

**Descripción**: Endpoint para enviar feedback del usuario.

**Parámetros**:
- `feedback_data` (JSON): Datos del feedback

**Ejemplo de solicitud**:
```json
{
  "session_id": "session_1234567890",
  "rating": 5,
  "comment": "Excelente respuesta, muy útil",
  "query": "¿Cómo solucionar error E4 en lavadora SVAN?",
  "response": "El error E4 en lavadoras SVAN indica un problema con..."
}
```

**Respuesta**:
```json
{
  "status": "success",
  "message": "Feedback recibido correctamente"
}
```

## Endpoints de Chat

### POST /chat/full

**Descripción**: Endpoint mejorado que implementa el chat completo con manejo robusto de contexto y procesamiento de imágenes.

**Parámetros**:
- `message` (Form): Mensaje del usuario
- `attachments` (File, opcional): Archivos adjuntos (imágenes)

**Respuesta**: Retorna un objeto JSON con la respuesta del asistente y metadatos.

**Ejemplo de solicitud**:
```
POST /chat/full
Content-Type: multipart/form-data

message=¿Cómo solucionar error E4 en lavadora SVAN?
```

**Ejemplo de respuesta**:
```json
{
  "response": "El error E4 en lavadoras SVAN indica un problema con el suministro de agua...",
  "session_id": "session_1234567890",
  "model": "gpt-4o-mini",
  "processing_time": 1.5,
  "context_used": true
}
```

### POST /analyze/image

**Descripción**: Endpoint para analizar imágenes con OCR.

**Parámetros**:
- `image` (File): Imagen para analizar

**Respuesta**: Retorna un objeto JSON con el texto extraído y análisis de la imagen.

**Ejemplo de respuesta**:
```json
{
  "text": "ERROR E4 - SUMINISTRO DE AGUA",
  "analysis": "La imagen muestra una pantalla de lavadora con código de error E4",
  "processing_time": 2.3
}
```

## Endpoints de Diagnóstico

### GET /debug/list_all_documents

**Descripción**: Endpoint de diagnóstico para listar todos los documentos en el índice.

**Nota**: No disponible en producción.

**Respuesta**: Retorna un objeto JSON con la lista de documentos.

**Ejemplo de respuesta**:
```json
{
  "total_documents": 150,
  "time_elapsed_seconds": 0.5,
  "documents": [
    {
      "name": "Manual_SVAN_LAV123.pdf",
      "modelo": "LAV123",
      "path": "/manuales/lavadoras/Manual_SVAN_LAV123.pdf"
    },
    ...
  ]
}
```

### GET /diagnostico/redis

**Descripción**: Endpoint para diagnóstico detallado de Redis.

**Respuesta**: Retorna un objeto JSON con información detallada sobre la conexión a Redis.

### GET /logs

**Descripción**: Endpoint para ver los últimos logs de la aplicación.

**Parámetros**:
- `lines` (Query, opcional): Número de líneas a mostrar (predeterminado: 100)
- `level` (Query, opcional): Nivel mínimo de log a mostrar (predeterminado: "INFO")

**Respuesta**: Retorna un objeto JSON con los logs de la aplicación.

## Endpoints de Manuales

### GET /manuales

**Descripción**: Lista todos los manuales disponibles.

**Parámetros**:
- `query` (Query, opcional): Texto para filtrar manuales
- `limit` (Query, opcional): Número máximo de resultados

**Respuesta**: Retorna un objeto JSON con la lista de manuales.

### GET /manuales/{modelo}

**Descripción**: Obtiene información sobre un manual específico.

**Parámetros**:
- `modelo` (Path): Código del modelo

**Respuesta**: Retorna un objeto JSON con información del manual.

## Manejo de Errores

La API implementa un manejo de errores consistente con los siguientes códigos HTTP:

- **400 Bad Request**: Solicitud incorrecta o parámetros inválidos
- **401 Unauthorized**: Autenticación requerida
- **403 Forbidden**: Acceso denegado
- **404 Not Found**: Recurso no encontrado
- **429 Too Many Requests**: Límite de cuota alcanzado
- **500 Internal Server Error**: Error interno del servidor

**Ejemplo de respuesta de error**:
```json
{
  "error": true,
  "code": 404,
  "message": "Manual no encontrado para el modelo especificado",
  "detail": "No se encontró ningún manual para el modelo XYZ123"
}
```
