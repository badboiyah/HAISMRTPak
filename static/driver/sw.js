const CACHE='haismrtpak-driver-v23-car-loop-pause';
const SHELL=['/static/brand/driver-logo.gif','/static/driver/scanner.js','/static/vendor/jsQR.js','/static/driver/entry.js','/static/entry.css','/static/brand/parked-car.svg','/driver/','/static/vi.js','/static/driver/style.css','/static/driver/app.js','/static/driver/icon-192.png','/static/driver/icon-512.png','/static/brand/theme.css','/static/brand/logo.png','/static/brand/car.png','/static/brand/app-icon.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>(key.startsWith('parksense-driver-')||key.startsWith('haismrtpak-driver-'))&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==self.location.origin||!SHELL.includes(url.pathname))return;
  // Never cache API responses, credentials, user identity or parking availability.
  event.respondWith(fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(event.request,copy)));}return response;}).catch(()=>caches.match(event.request).then(cached=>cached||Response.error())));
});
