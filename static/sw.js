const CACHE_NAME = 'lendogo-v1';
const urlsToCache = [
  '/',
  '/static/icons/icon-192.png',
  '/static/icons/icon-192-maskable.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-512-maskable.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon.ico'
];

// 1. Install - save files to cache
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Caching files');
        return cache.addAll(urlsToCache);
      })
  );
  self.skipWaiting();
});

// 2. Activate - clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

// 3. Fetch - if offline, serve from cache
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached file OR fetch from internet
        return response || fetch(event.request);
      })
  );
});