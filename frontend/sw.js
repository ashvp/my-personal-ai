const CACHE_NAME = 'assistant-pwa-v2';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/css/custom.css',
  '/static/js/app.js',
  '/static/js/pwa.js'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Network-first strategy so UI updates are always instantly visible
self.addEventListener('fetch', (event) => {
  if (
    event.request.url.includes('/chat') ||
    event.request.url.includes('/api') ||
    event.request.url.includes('/gmail') ||
    event.request.method !== 'GET'
  ) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});
