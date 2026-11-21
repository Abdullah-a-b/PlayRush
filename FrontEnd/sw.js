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

const VERSION     = 'playrush-v4-native-match';
const SHELL_CACHE = `${VERSION}-shell`;
const ASSET_CACHE = `${VERSION}-assets`;

// أقل ما يلزم ليعمل التطبيق دون اتصال
const SHELL = [
    "/",
    "/assets/avatars/avatar_1.svg",
    "/assets/avatars/avatar_2.svg",
    "/assets/favicon.svg",
    "/assets/flags/AE.svg",
    "/assets/flags/EARTH.svg",
    "/assets/flags/SA.svg",
    "/assets/fonts/Tajawal-Black.ttf",
    "/assets/fonts/Tajawal-Bold.ttf",
    "/assets/fonts/Tajawal-Regular.ttf",
    "/assets/icons/icon-192.png",
    "/categories.html",
    "/css/all.min.css",
    "/css/android_download.css",
    "/css/android_shell.css",
    "/css/app_perf.css",
    "/css/brand.css",
    "/css/categories.css",
    "/css/categories_hub.css",
    "/css/design-system.css",
    "/css/email_copy.css",
    "/css/games/bank.css",
    "/css/games/career.css",
    "/css/games/huroof.css?v=3",
    "/css/games/huroof_mobile.css?v=14",
    "/css/games/knowledge.css",
    "/css/games/mobile_match.css",
    "/css/games/whoami.css",
    "/css/guide_hint.css",
    "/css/index.css",
    "/css/leaderboard.css",
    "/css/lobby.css",
    "/css/platform_guide.css",
    "/css/playrush-surfaces.css",
    "/css/quick_chat.css",
    "/css/responsive.css",
    "/css/social_bar.css",
    "/css/theme_styles.css",
    "/games/career.html",
    "/games/huroof.html",
    "/games/knowledge.html",
    "/games/whoami.html",
    "/index.html",
    "/js/android_download.js",
    "/js/anti_cheat.js",
    "/js/app_startup.js",
    "/js/app_update.js",
    "/js/brand.js",
    "/js/categories.js",
    "/js/categories_hub.js",
    "/js/config.js",
    "/js/email_copy.js",
    "/js/emergency_entry.js",
    "/js/emergency_match.js",
    "/js/emoji_engine.js",
    "/js/friends_panel.js",
    "/js/games/career.js?v=career-pilot-1",
    "/js/games/game_emojis.js",
    "/js/games/huroof.js?v=opening-timer-2",
    "/js/games/knowledge.js",
    "/js/games/mobile_match.js",
    "/js/games/whoami.js",
    "/js/guide_hint.js",
    "/js/index.js",
    "/js/loadout.js",
    "/js/music.js",
    "/js/offline_deck.js",
    "/js/offline_entry.js",
    "/js/platform_guide.js",
    "/js/player_profile.js",
    "/js/practice_recovery.js",
    "/js/presence.js",
    "/js/progression_api.js",
    "/js/purify.min.js",
    "/js/pwa.js",
    "/js/quick_chat.js",
    "/js/session_resume.js",
    "/js/settings.js",
    "/js/social_bar.js",
    "/js/socket.io.min.js",
    "/js/solo_mode.js",
    "/js/sound.js",
    "/js/splash.js",
    "/js/stars.js",
    "/js/store.js",
    "/js/themes.js",
    "/js/ui_dialog.js",
    "/js/utils.js",
    "/js/whats_new.js",
    "/manifest.json",
    "/offline.html",
    "/webfonts/fa-brands-400.woff2",
    "/webfonts/fa-regular-400.woff2",
    "/webfonts/fa-solid-900.woff2",
    "/webfonts/fa-v4compatibility.woff2"
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then((c) => Promise.all(SHELL.map(path => c.add(path).catch(() => null))))
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

// ملفات الكود: نخدمها من الكاش فوراً ثم نحدّثها في الخلفية.
// هذا يجعل التنقّل بين الصفحات شبه فوري داخل التطبيق (الذي يحمّل
// من الشبكة بعد server.url)، ويصل التحديث في الفتحة التالية.
function isCode(url) {
    return /\.(css|js)$/i.test(url.pathname);
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

    // 🩹 CSS/JS: الشبكة أولاً فعلياً (يطابق التعليق أعلى الملف) — كانت
    // النسخة السابقة تخدم الكاش القديم فوراً وتحدّثه بصمت لاحقاً
    // (stale-while-revalidate)، فيبقى اللاعب نسخة كاملة متأخراً عن كل
    // نشر جديد بلا أي علامة على ذلك. الكاش هنا شبكة أمان لانقطاع النت فقط.
    if (isCode(url)) {
        event.respondWith(
            fetch(req).then((res) => {
                if (res && res.ok) {
                    const copy = res.clone();
                    caches.open(SHELL_CACHE).then((c) => c.put(req, copy));
                }
                return res;
            }).catch(() => caches.match(req))
        );
        return;
    }

    // كل ما عدا ذلك (HTML): الشبكة أولاً، والكاش شبكة أمان فقط
    event.respondWith(
        fetch(req)
            .then((res) => {
                if (res && res.ok) {
                    const copy = res.clone();
                    caches.open(SHELL_CACHE).then((c) => c.put(req, copy));
                }
                return res;
            })
            .catch(async () => {
                const path = url.pathname;
                const page = path === '/' ? '/index.html' : path.endsWith('.html') ? path : path + '.html';
                const hit = await caches.match(req) || await caches.match(page) || await caches.match('/index.html');
                if (hit?.redirected && req.mode === 'navigate') {
                    return new Response(hit.body, {status:hit.status, headers:hit.headers});
                }
                return hit || Response.error();
            })
    );
});
