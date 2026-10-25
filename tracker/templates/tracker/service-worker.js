const CACHE_NAME = "greenmove-tracker-v3";
const OFFLINE_URL = "/tracker/offline/";
const STATIC_URLS = [
  "/static/tracker/tracker.css",
  "/static/tracker/tracker.js",
  "/static/tracker/heatmap.js",
  "/static/tracker/greenmove.svg",
  OFFLINE_URL
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/tracker/trips/") || url.pathname.startsWith("/accounts/")) return;
  if (url.pathname.startsWith("/static/tracker/") || url.pathname === OFFLINE_URL) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request))
    );
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
  }
});
