/* ============================================================
   PlayRush — Service Worker
   ------------------------------------------------------------
   فلسفة متحفّظة عن قصد: هذه منصة لعب لحظية، والتخزين المؤقت
   العدواني يسبّب "نسخاً قديمة" لدى بعض اللاعبين (مشكلة واجهناها
   سابقاً). لذلك:

   • HTML / JS / CSS  → الشبكة أولاً دائماً (أحدث نسخة تصل فوراً).
                        الكاش يُستخدم فقط عند انقطاع الإنترنت.
   • الصور والخطوط   → الكاش أولاً (لا تتغيّر كثيراً = سرعة).
   • طلبات الـAPI والسوكِت → لا تُخزَّن إطلاقاً.
   • التحديث فوري (skipWaiting + clients.claim) بلا انتظار.
   ============================================================ */

const VERSION     = 'playrush-v1';
const SHELL_CACHE = `${VERSION}-shell`;
const ASSET_CACHE = `${VERSION}-assets`;

// أقل ما يلزم ليعمل التطبيق دون اتصال
const SHELL = [
    '/',
    '/index.html',
    '/manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then((c) => c.addAll(SHELL).catch(() => null))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

// يسمح للصفحة بطلب تفعيل نسخة جديدة فوراً
self.addEventListener('message', (e) => {
    if (e.data === 'SKIP_WAITING') self.skipWaiting();
});

function isAsset(url) {
    return /\.(png|jpg|jpeg|gif|svg|webp|woff2?|ttf|eot|mp3|ogg|wav)$/i.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;

    let url;
    try { url = new URL(req.url); } catch { return; }

    // لا نتدخّل إطلاقاً في نطاقات أخرى (الـAPI على Azure، السوكِت، جوجل…)
    if (url.origin !== self.location.origin) return;
    // ولا في مسارات الاتصال الحيّ
    if (url.pathname.startsWith('/socket.io')) return;

    // الصور/الخطوط: الكاش أولاً
    if (isAsset(url)) {
        event.respondWith(
            caches.match(req).then((hit) => hit || fetch(req).then((res) => {
                if (res && res.ok) {
                    const copy = res.clone();
                    caches.open(ASSET_CACHE).then((c) => c.put(req, copy));
                }
                return res;
            }).catch(() => hit))
        );
        return;
    }

    // كل ما عدا ذلك (HTML/JS/CSS): الشبكة أولاً، والكاش شبكة أمان فقط
    event.respondWith(
        fetch(req)
            .then((res) => {
                if (res && res.ok) {
                    const copy = res.clone();
                    caches.open(SHELL_CACHE).then((c) => c.put(req, copy));
                }
                return res;
            })
            .catch(() => caches.match(req).then((hit) => hit || caches.match('/index.html')))
    );
});
