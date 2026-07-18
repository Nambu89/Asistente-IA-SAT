# Guía de Resolución de Problemas de Technical Support AI Assistant

Este documento proporciona información para diagnosticar y resolver problemas comunes en la aplicación.

## Índice

1. [Problemas de Conexión](#problemas-de-conexión)
2. [Problemas de Rendimiento](#problemas-de-rendimiento)
3. [Problemas de Seguridad](#problemas-de-seguridad)
4. [Problemas con Servicios de Azure](#problemas-con-servicios-de-azure)
5. [Problemas de Frontend](#problemas-de-frontend)
6. [Herramientas de Diagnóstico](#herramientas-de-diagnóstico)
7. [Preguntas Frecuentes](#preguntas-frecuentes)

## Problemas de Conexión

### Problemas de Conexión con Redis

**Síntoma**: La aplicación no puede conectarse a Redis o muestra errores de timeout.

**Soluciones**:

1. **Verificar Configuración**:
   - Comprobar las variables de entorno `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` y `REDIS_SSL`
   - Asegurarse de que la instancia de Redis esté en ejecución

2. **Verificar Conectividad de Red**:
   - Utilizar el endpoint `/diagnostico/redis` para obtener información detallada
   - Comprobar si el firewall permite conexiones al puerto de Redis

3. **Verificar SSL**:
   - Si `REDIS_SSL=True`, asegurarse de que Redis esté configurado para SSL
   - Si hay problemas con SSL, intentar desactivarlo temporalmente para diagnóstico

4. **Reiniciar Servicios**:
   - Reiniciar la aplicación para forzar una nueva conexión
   - Reiniciar la instancia de Redis si es posible

### Problemas de Contenido Mixto HTTP/HTTPS

**Síntoma**: El navegador bloquea recursos o muestra advertencias de contenido mixto.

**Soluciones**:

1. **Verificar Middleware HTTPS**:
   - Comprobar que `HTTPSRedirectMiddleware` esté configurado correctamente
   - Asegurarse de que `is_production` se detecte correctamente

2. **Añadir Meta Tag CSP**:
   - Añadir a las plantillas HTML:
     ```html
     <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
     ```

3. **Implementar Funciones de Seguridad**:
   - Utilizar `ensureHttps()` en el frontend para convertir URLs a HTTPS
   - Implementar `secureAllResources()` para asegurar todos los recursos

4. **Verificar URLs Hardcodeadas**:
   - Buscar URLs con "http://" hardcodeadas en el código
   - Reemplazar por URLs relativas o con "https://"

## Problemas de Rendimiento

### Tiempos de Respuesta Lentos

**Síntoma**: La aplicación responde lentamente o los tiempos de carga son excesivos.

**Soluciones**:

1. **Optimizar Caché**:
   - Verificar que Redis esté funcionando correctamente
   - Ajustar los tiempos de expiración de caché según necesidad
   - Implementar caché para consultas frecuentes

2. **Optimizar Consultas de Búsqueda**:
   - Revisar y optimizar las consultas a Azure Cognitive Search
   - Implementar filtros más específicos para reducir resultados

3. **Ajustar Configuración de Servidor**:
   - Aumentar el número de workers en gunicorn
   - Ajustar timeouts para conexiones lentas

4. **Monitorear Recursos**:
   - Verificar uso de CPU y memoria
   - Escalar recursos si es necesario

### Consumo Excesivo de Memoria

**Síntoma**: La aplicación consume demasiada memoria o muestra errores de memoria insuficiente.

**Soluciones**:

1. **Limitar Tamaño de Contexto**:
   - Ajustar `CONTEXT_WINDOW_MESSAGES` y `MAX_HISTORY_TOKENS`
   - Implementar limpieza periódica de sesiones antiguas

2. **Optimizar Procesamiento de Archivos**:
   - Limitar el tamaño máximo de archivos subidos
   - Liberar recursos después de procesar archivos

3. **Monitorear Fugas de Memoria**:
   - Utilizar herramientas como `memory_profiler`
   - Implementar logging de uso de memoria

## Problemas de Seguridad

### Problemas de CORS

**Síntoma**: Errores de CORS en el navegador al realizar solicitudes.

**Soluciones**:

1. **Verificar Configuración de CORS**:
   - Comprobar que los dominios correctos estén en `allow_origins`
   - Asegurarse de que los métodos necesarios estén en `allow_methods`

2. **Actualizar cors.json**:
   - Sincronizar `cors.json` con la configuración en `main.py`
   - Reiniciar la aplicación después de cambios

### Problemas de Autenticación

**Síntoma**: Errores de autenticación al acceder a servicios de Azure.

**Soluciones**:

1. **Verificar Claves de API**:
   - Comprobar que las claves de API sean válidas y no hayan expirado
   - Regenerar claves si es necesario

2. **Verificar Permisos**:
   - Asegurarse de que los servicios tengan los permisos necesarios
   - Verificar roles y políticas de acceso

## Problemas con Servicios de Azure

### Problemas con Azure OpenAI

**Síntoma**: Errores al generar respuestas o tiempos de espera excesivos.

**Soluciones**:

1. **Verificar Cuota y Límites**:
   - Comprobar si se ha alcanzado el límite de cuota
   - Solicitar aumento de cuota si es necesario

2. **Verificar Configuración**:
   - Comprobar que el modelo especificado exista y esté disponible
   - Verificar que la versión de API sea compatible

3. **Implementar Reintentos**:
   - Utilizar estrategias de reintento con backoff exponencial
   - Manejar errores 429 (Too Many Requests) adecuadamente

### Problemas con Azure Cognitive Search

**Síntoma**: Búsquedas que no devuelven resultados esperados o errores en consultas.

**Soluciones**:

1. **Verificar Índice**:
   - Comprobar que el índice exista y contenga documentos
   - Verificar la estructura del índice y campos

2. **Optimizar Consultas**:
   - Revisar y ajustar los parámetros de búsqueda
   - Implementar filtros más específicos

3. **Reindexar Contenido**:
   - Si es necesario, reindexar el contenido para actualizar
   - Verificar que los documentos se indexen correctamente

## Problemas de Frontend

### Problemas de Visualización

**Síntoma**: Elementos de la interfaz que no se muestran correctamente o errores de JavaScript.

**Soluciones**:

1. **Verificar Compatibilidad de Navegador**:
   - Probar en diferentes navegadores
   - Implementar polyfills para navegadores antiguos

2. **Depurar JavaScript**:
   - Utilizar las herramientas de desarrollo del navegador
   - Verificar errores en la consola

3. **Verificar Recursos Estáticos**:
   - Comprobar que los archivos CSS y JavaScript se carguen correctamente
   - Verificar rutas relativas y absolutas

### Problemas de Responsividad

**Síntoma**: La interfaz no se adapta correctamente a diferentes tamaños de pantalla.

**Soluciones**:

1. **Verificar CSS Responsivo**:
   - Implementar media queries para diferentes tamaños
   - Utilizar unidades relativas (%, em, rem) en lugar de absolutas

2. **Probar en Diferentes Dispositivos**:
   - Utilizar herramientas de emulación de dispositivos
   - Realizar pruebas en dispositivos reales

## Herramientas de Diagnóstico

### Endpoints de Diagnóstico

La aplicación proporciona varios endpoints para diagnóstico:

1. **GET /health**:
   - Verificar el estado general de la aplicación
   - Comprobar el estado de los servicios

2. **GET /diagnostico/redis**:
   - Obtener información detallada sobre la conexión a Redis
   - Verificar conectividad y configuración

3. **GET /logs**:
   - Ver los últimos logs de la aplicación
   - Filtrar por nivel de log

4. **GET /debug/list_all_documents**:
   - Listar todos los documentos en el índice de búsqueda
   - Verificar que los documentos se indexen correctamente

### Logs

Los logs son una herramienta esencial para diagnóstico:

1. **Ubicación de Logs**:
   - Logs de aplicación: directorio `logs/`
   - Logs de feedback: `logs/feedback.log`

2. **Niveles de Log**:
   - DEBUG: Información detallada para depuración
   - INFO: Información general sobre operaciones
   - WARNING: Advertencias sobre posibles problemas
   - ERROR: Errores que no impiden la operación
   - CRITICAL: Errores críticos que impiden la operación

3. **Configuración de Logging**:
   - Ajustar nivel de log con la variable `LOG_LEVEL`
   - Reducir nivel de logging para bibliotecas ruidosas

## Preguntas Frecuentes

### ¿Por qué la aplicación no se conecta a Redis?

**Respuesta**: Verifique la configuración de Redis en el archivo `.env`. Asegúrese de que:
- Las credenciales sean correctas
- La instancia de Redis esté en ejecución
- No haya restricciones de firewall
- Si usa SSL, la configuración sea correcta

### ¿Cómo puedo mejorar el rendimiento de búsqueda?

**Respuesta**: Para mejorar el rendimiento de búsqueda:
- Implemente caché para consultas frecuentes
- Optimice las consultas con filtros específicos
- Ajuste los parámetros de búsqueda
- Considere reindexar el contenido si es necesario

### ¿Cómo soluciono problemas de contenido mixto HTTP/HTTPS?

**Respuesta**: Para solucionar problemas de contenido mixto:
- Verifique que `HTTPSRedirectMiddleware` esté configurado correctamente
- Añada un meta tag Content-Security-Policy con upgrade-insecure-requests
- Implemente funciones para convertir URLs a HTTPS
- Asegúrese de que todos los recursos se carguen con HTTPS

### ¿Cómo puedo monitorear el uso de recursos?

**Respuesta**: Para monitorear el uso de recursos:
- Utilice el endpoint `/health` para verificar el estado general
- Configure alertas en Azure Portal
- Implemente logging de uso de memoria y CPU
- Utilice herramientas como Application Insights

### ¿Qué hago si Azure OpenAI devuelve errores de cuota?

**Respuesta**: Si Azure OpenAI devuelve errores de cuota:
- Implemente estrategias de reintento con backoff exponencial
- Considere reducir la frecuencia de solicitudes
- Solicite un aumento de cuota
- Implemente caché para reducir solicitudes redundantes
