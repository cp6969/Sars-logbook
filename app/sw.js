// Deliberately scoped down: this gives the app an install-shell + a thin
// offline fallback, NOT a general offline-first framework. No Background
// Sync registration (unreliable on iOS Safari), no runtime caching of
// /api/* responses -- the offline trip queue lives in IndexedDB
// (app/static/js/db.js) and is flushed explicitly by sync.js, not by the
// service worker itself.
const CACHE_NAME = "sars-logbook-v1";
const APP_SHELL = [
  "/dashboard",
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/db.js",
  "/static/js/gps.js",
  "/static/js/trip-capture.js",
  "/static/js/sync.js",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/dashboard")));
    return;
  }

  if (APP_SHELL.some((path) => req.url.endsWith(path))) {
    event.respondWith(caches.match(req).then((cached) => cached || fetch(req)));
  }
});
