// Info-Tag — lightweight service worker.
// Caches the app shell only; never the API responses.
const CACHE = "infotag-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.json"];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
        ),
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);
    // Never cache API calls.
    if (url.pathname.startsWith("/api/") || url.origin !== location.origin) return;
    // Network-first for navigations, cache fallback offline.
    if (event.request.mode === "navigate") {
        event.respondWith(
            fetch(event.request).catch(() => caches.match("/index.html")),
        );
        return;
    }
});

// ---------------------------------------------------------------------------
// Web Push — free scan/message alerts (see Settings → Phone & alerts)
// ---------------------------------------------------------------------------
self.addEventListener("push", (event) => {
    let payload = {};
    try {
        payload = event.data ? event.data.json() : {};
    } catch {
        payload = { title: "Info-Tag", body: event.data ? event.data.text() : "" };
    }
    const title = payload.title || "Info-Tag";
    event.waitUntil(
        self.registration.showNotification(title, {
            body: payload.body || "",
            icon: "/logo192.png",
            badge: "/logo192.png",
            data: { url: payload.url || "/inbox" },
        }),
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || "/inbox";
    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
            for (const w of wins) {
                if ("focus" in w) {
                    w.navigate(url);
                    return w.focus();
                }
            }
            return clients.openWindow(url);
        }),
    );
});
