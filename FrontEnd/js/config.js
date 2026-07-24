// FrontEnd/js/config.js

//  اكتشاف عنوان الخادم تلقائياً:
// - من localhost/127.0.0.1 → خادم محلي على نفس الجهاز
// - من عنوان شبكة (هاتف عبر WiFi مثل 192.168.x.x) → نفس العنوان + المنفذ 8000
// هذا يتيح فتح المشروع من الهاتف بلا تعديل يدوي.
// 🌐 دومين الإنتاج — عدّله هنا مرة واحدة عند إطلاق الدومينات
// (يُستخدم تلقائياً في الإنتاج وفي تطبيقات Android/iOS)
const PROD_API_ORIGIN = 'https://playrush-api.azurewebsites.net';   // ← ضع دومين الباك إند الفعلي

// 📱 كشف بيئة التطبيق (Capacitor/WebView): التطبيق يحمّل الواجهة من
// حزمة محلية. مع androidScheme:"https" يكون العنوان https://localhost،
// فلا يكفي فحص البروتوكول — نعتمد جسر Capacitor نفسه (window.Capacitor)
// وهو يُحقن دائماً داخل التطبيق ولا يوجد إطلاقاً في متصفح عادي.
const PR_IS_APP = window.PR_IS_APP === true
    || (typeof window.Capacitor !== 'undefined')
    || /^(capacitor|file|ionic):$/.test(window.location.protocol);

window.PR_IS_APP = PR_IS_APP;  // متاح لكل المنصة (الجلسات/الواجهات)

// صنف على <html> تستهدفه css/app_perf.css لتخفيف المؤثرات داخل التطبيق
// (الموقع على المتصفح يبقى بكامل مؤثراته).
try {
    if (PR_IS_APP) document.documentElement.classList.add('pr-app');
    var _coarse = (typeof window.matchMedia === 'function'
                    && window.matchMedia('(pointer: coarse)').matches)
                  || ('ontouchstart' in window)
                  || (navigator.maxTouchPoints > 0);
    if (_coarse) document.documentElement.classList.add('pr-touch');
} catch (e) {}

const _host = window.location.hostname;
const _isLocalHost = (_host === '127.0.0.1' || _host === 'localhost' || _host === '');
const _isLanIp = /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(_host);
const _backendOrigin =
    PR_IS_APP        ? PROD_API_ORIGIN                     // 📱 تطبيق → دومين الإنتاج
    : _isLocalHost   ? 'http://127.0.0.1:8000'             // 💻 تطوير محلي
    : _isLanIp       ? `http://${_host}:8000`              // 📶 هاتف عبر WiFi للتطوير
    : PROD_API_ORIGIN;                                     // 🌐 الويب بالإنتاج → دومين API

const CONFIG = {
    // الدومين الخاص بالباك إند (API)
    API_URL: _backendOrigin,

    // الدومين الخاص بالاتصال المباشر (Socket.io)
    WS_URL: _backendOrigin
};

// ============================================================
//  روابط التواصل الاجتماعي — مصدر واحد لكل المنصة
// عدّل الروابط هنا فقط، وستتحدّث في كل الصفحات تلقائياً.
// لإخفاء منصة: اجعل رابطها '' (فراغ) أو احذف السطر.
// ============================================================
const SOCIAL_LINKS = {
    twitter:   'https://x.com/PlayRushApp',      // X (تويتر)
    instagram: 'https://www.instagram.com/playrush_app?igsh=MWhuZnQyb3ByN2V6aQ==',    // إنستغرام
    tiktok:    'https://www.tiktok.com/@playrushapp',      // تيك توك
    snapchat:  'https://www.snapchat.com/add/playrushapp?share_id=vLlm4hBExyw&locale=ar-EG', // سناب شات
    threads:   'https://www.threads.com/@playrush_app',     // ثريدز
    facebook:  'https://www.facebook.com/share/1E4AC4MxYV/',     // فيسبوك
};
//  استبدل "PlayRush" أعلاه باسم المستخدم الفعلي لكل حساب.

// دالة مساعدة لتسهيل جلب التوكن من أي مكان
const getToken = () => localStorage.getItem('token') || sessionStorage.getItem('token');

document.addEventListener('click', function(e) {
    // نراقب أي نقرة في الموقع، وإذا كانت النقرة على "زر رفع ملف/صورة"
    if (e.target && e.target.type === 'file') {
        // نقوم بتفريغ ذاكرة الزر في نفس اللحظة (قبل أن تفتح نافذة اختيار الصور)
        // هذا يخدع المتصفح ويجعله يعتقد أن الصورة التي ستختارها هي "تغيير جديد" دائماً!
        e.target.value = '';
    }
});

// ===== PR_SESSION_BRIDGE: تذكُّر الدخول (زي المواقع العالمية) =====
// من فعّل "تذكرني": توكنه في localStorage (يعيش 7 أيام = صلاحية التوكن
// بالخادم). عند فتح تبويب/جلسة جديدة ننسخه لsessionStorage فيعمل كل
// الكود القديم كما هو بلا تعديل. الخادم يرفض التوكن المنتهي تلقائياً.
(function () {
    try {
        var lt = localStorage.getItem('token');
        if (lt && !sessionStorage.getItem('token')) {
            sessionStorage.setItem('token', lt);
        }
    } catch (e) { /* متصفح يمنع التخزين */ }
})();
