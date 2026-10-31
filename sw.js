const CACHE = "trendscout-20261030-194912";
function bust(url) { return url + (url.indexOf("?") === -1 ? "?" : "&") + "_sw=" + Date.now(); }
const APP_SHELL = ["./", "./index.html", "./wire.html", "./watchlist.html", "./diagnostics.html",
  "./manifest.webmanifest", "./free.json", "./icons/icon-192.png", "./icons/icon-512.png",
  "./icons/apple-touch-icon.png", "./icons/favicon-32.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    // Every app on this github.io address shares one cache store (HLSA included), so only ever
    // clear TrendScout's own older caches.
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("trendscout-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // The update check itself must never come from a cache.
  if (url.pathname.endsWith("version.json")) {
    event.respondWith(fetch(bust(req.url), { cache: "no-store" }));
    return;
  }

  const pathname = url.pathname;
  const isFresh = req.mode === "navigate" || pathname.endsWith(".webmanifest") || pathname.endsWith("free.json");
  if (isFresh) {
    // Network-first so a newly published snapshot shows on the very next open; the cache
    // (stored under the clean URL) is only the offline fallback.
    const key = req.url.split("#")[0].split("?")[0];
    event.respondWith(
      fetch(bust(req.url), { cache: "no-store" })
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(key, copy));
          }
          return response;
        })
        .catch(() => caches.match(key).then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }

  // Icons: cache-first, refreshed in the background.
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return response;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
