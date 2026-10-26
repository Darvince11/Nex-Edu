/* Nex Edu service worker: shows push notifications and opens them. Nothing is cached. */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Nex Edu", {
      body: data.body || "",
      icon: "/icon.png",
      badge: "/icon.png",
      data: { url: data.url || "/inbox" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/inbox", self.location.origin);
  if (url.origin !== self.location.origin) return; // only ever open Nex Edu pages
  event.waitUntil(self.clients.openWindow(url.href));
});
