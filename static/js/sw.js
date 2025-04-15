// Service Worker para SvanIA

const CACHE_NAME = 'svania-cache-v1';
const OFFLINE_URL = '/offline.html';

// Recursos para almacenar en caché
const CACHE_ASSETS = [
  '/',
  '/offline.html',
  '/static/js/chat.js',
  '/static/css/styles.min.css',
  '/static/css/mobile.css',
  '/static/images/favicon.ico',
  '/static/images/apple-touch-icon.png',
  '/static/images/offline.svg',
  '/static/images/image-error.svg',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/webfonts/fa-solid-900.woff2',
  'https://cdn.jsdelivr.net/npm/marked/marked.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/github-dark.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js'
];

// Instalar el Service Worker
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Caché abierta');
        return cache.addAll(CACHE_ASSETS);
      })
      .then(() => {
        // Forzar la activación inmediata
        return self.skipWaiting();
      })
  );
});

// Activar el Service Worker
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          // Eliminar cachés antiguas
          if (cacheName !== CACHE_NAME) {
            console.log('Eliminando caché antigua:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      // Garantizar que el SW se active inmediatamente en todos los clientes
      return self.clients.claim();
    })
  );
});

// Estrategia de manejo de peticiones: "Stale While Revalidate"
self.addEventListener('fetch', (event) => {
  // Solo interceptar peticiones GET
  if (event.request.method !== 'GET') return;
  
  // No interceptar peticiones a la API
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/') || 
      url.pathname.startsWith('/chat') || 
      url.pathname.startsWith('/fullchat')) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then((cachedResponse) => {
        // Usar la versión en caché si existe
        const fetchPromise = fetch(event.request)
          .then((networkResponse) => {
            // Actualizar la caché con la nueva versión
            if (networkResponse && networkResponse.status === 200) {
              const responseClone = networkResponse.clone();
              caches.open(CACHE_NAME)
                .then((cache) => {
                  cache.put(event.request, responseClone);
                });
            }
            return networkResponse;
          })
          .catch((error) => {
            console.log('Error en fetch:', error);
            
            // Si la solicitud es para una página HTML, mostrar la página offline
            if (event.request.headers.get('Accept').includes('text/html')) {
              return caches.match(OFFLINE_URL);
            }
            
            // Para otros recursos, retornar un error apropiado
            return new Response('Error de red', {
              status: 503,
              statusText: 'Servicio no disponible'
            });
          });
        
        // Retornar la versión en caché o esperar la respuesta de la red
        return cachedResponse || fetchPromise;
      })
  );
});

// Manejo de mensajes desde los clientes
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});