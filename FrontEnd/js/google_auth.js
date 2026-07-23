/* ============================================================
   PlayRush — تسجيل الدخول بجوجل (ويب + تطبيق)
   ------------------------------------------------------------
   على الويب: رابط عادي يفتح صفحة مصادقة جوجل.

   داخل التطبيق: جوجل يرفض المصادقة داخل WebView المدمج، لذلك:
     ١) نفتح المصادقة في متصفح النظام (Custom Tab) عبر Capacitor Browser.
     ٢) نمرّر client=app ليعرف الخادم أن يعيد التوجيه لرابط عميق.
     ٣) نلتقط playrush://auth?token=... عبر مستمع appUrlOpen.
     ٤) نخزّن التوكن، نغلق المتصفح، وننتقل للصفحة المطلوبة.

   يُستدعى تلقائياً: يكفي وجود زر/رابط بالمعرّف google-login-btn.
   ============================================================ */
(function () {
    var isApp = window.PR_IS_APP === true || (typeof window.Capacitor !== 'undefined');

    function api() {
        return (typeof CONFIG !== 'undefined' && CONFIG.API_URL) ? CONFIG.API_URL : '';
    }

    /* ---------- التقاط الرابط العميق العائد من المتصفح ---------- */
    function handleDeepLink(url) {
        if (!url || url.indexOf('auth') === -1) return;
        var token = null, page = 'categories';
        try {
            // playrush://auth?token=...&page=...
            var q = url.split('?')[1] || '';
            q.split('&').forEach(function (pair) {
                var kv = pair.split('=');
                if (kv[0] === 'token') token = decodeURIComponent(kv[1] || '');
                if (kv[0] === 'page')  page  = decodeURIComponent(kv[1] || 'categories');
            });
        } catch (e) { return; }

        if (!token) return;

        // نخزّن التوكن بنفس آلية بقية المنصة
        try {
            sessionStorage.setItem('token', token);
            localStorage.setItem('token', token);
        } catch (e) {}

        // نغلق متصفح النظام إن كان مفتوحاً
        try {
            var B = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Browser;
            if (B && B.close) B.close();
        } catch (e) {}

        window.location.replace(page + '.html?token=' + encodeURIComponent(token));
    }

    if (isApp) {
        var App = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App;
        if (App && App.addListener) {
            App.addListener('appUrlOpen', function (data) {
                handleDeepLink(data && data.url);
            });
        }
    }

    /* ---------- ربط الزر ---------- */
    function wireButton() {
        var el = document.getElementById('google-login-btn');
        if (!el) return;

        if (!isApp) {
            // الويب: رابط مباشر كما كان
            el.href = api() + '/auth/google/login';
            return;
        }

        // التطبيق: نمنع فتح الرابط داخل WebView ونستخدم متصفح النظام
        el.removeAttribute('href');
        el.style.cursor = 'pointer';
        el.addEventListener('click', function (e) {
            e.preventDefault();
            var url = api() + '/auth/google/login?client=app';
            var B = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Browser;
            if (B && B.open) {
                B.open({ url: url, presentationStyle: 'popover' });
            } else {
                // احتياط: لو لم تُثبَّت إضافة Browser
                window.open(url, '_system');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireButton);
    } else {
        wireButton();
    }
})();
