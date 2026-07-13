// FrontEnd/js/config.js

// 🌐 اكتشاف عنوان الخادم تلقائياً:
// - من localhost/127.0.0.1 → خادم محلي على نفس الجهاز
// - من عنوان شبكة (هاتف عبر WiFi مثل 192.168.x.x) → نفس العنوان + المنفذ 8000
// هذا يتيح فتح المشروع من الهاتف بلا تعديل يدوي.
const _host = window.location.hostname;
const _isLocalHost = (_host === '127.0.0.1' || _host === 'localhost' || _host === '');
const _backendOrigin = _isLocalHost
    ? 'http://127.0.0.1:8000'
    : `http://${_host}:8000`;   // نفس IP الذي فُتحت منه الصفحة (هاتف/شبكة محلية)

const CONFIG = {
    // الدومين الخاص بالباك إند (API)
    API_URL: _backendOrigin,

    // الدومين الخاص بالاتصال المباشر (Socket.io)
    WS_URL: _backendOrigin
};

// ============================================================
// 🌐 روابط التواصل الاجتماعي — مصدر واحد لكل المنصة
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
// ⚠️ استبدل "PlayRush" أعلاه باسم المستخدم الفعلي لكل حساب.

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