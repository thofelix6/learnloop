// LearnLoop service worker: the shell is cached, everything live stays live.
// Bump CACHE when the shell changes so clients pick up the new files.
const CACHE = 'learnloop-v2';
const SHELL = [
  '/', '/static/style.css', '/static/app.js', '/static/icon.svg',
  '/static/icon-192.png', '/static/apple-touch-icon.png', '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;              // never cache API
  if (url.pathname.startsWith('/audio/') || url.pathname.startsWith('/video/')) return;

  // Navigations: network first (so a deploy is visible immediately), cache as offline fallback
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put('/', copy)).catch(() => {});
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || caches.match('/')))
    );
    return;
  }

  // Vendored pdf.js is large and never changes: cache first
  if (url.pathname.startsWith('/static/vendor/')) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    })));
    return;
  }

  // Other assets: cache first with a fresh copy kept in the background
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok && res.type === 'basic') {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    }))
  );
});
