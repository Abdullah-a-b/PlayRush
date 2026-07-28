/* ============================================================
   PlayRush — استئناف الجلسة المحفوظة
   ------------------------------------------------------------
   صفحة البداية كانت تعرض «تسجيل الدخول / إنشاء حساب» دائماً،
   حتى لو كان المستخدم مفعّلاً «تذكرني» (أو داخل التطبيق حيث
   الجلسة محفوظة دائماً). فيظنّ أن المنصة لا تحفظ تسجيله.

   الآن: لو وُجد توكن صالح، نتحقق منه مع الخادم ثم ننقله مباشرة
   إلى صفحته. وإن كان منتهياً نمسحه ونُبقيه على صفحة البداية.
   ============================================================ */
(function () {
    function token() {
        try {
            return sessionStorage.getItem('token') || localStorage.getItem('token');
        } catch (e) { return null; }
    }

    function clearToken() {
        try {
            sessionStorage.removeItem('token');
            localStorage.removeItem('token');
        } catch (e) {}
    }

    function api() {
        return (typeof CONFIG !== 'undefined' && CONFIG.API_URL) ? CONFIG.API_URL : '';
    }

    async function resume() {
        // خرج المستخدم للتو صراحةً → لا نستأنف جلسته رغماً عنه.
        // (العلامة تُستهلك مرة واحدة ثم تُمسح)
        try {
            if (sessionStorage.getItem('pr_logged_out') === '1') {
                sessionStorage.removeItem('pr_logged_out');
                return;
            }
        } catch (e) {}

        var t = token();
        if (!t) return;                     // لا جلسة محفوظة — نعرض الصفحة عادةً
        if (!api()) return;

        // مؤشر بسيط حتى لا تبدو الصفحة جامدة أثناء التحقق
        var hint = document.createElement('div');
        hint.textContent = 'جارٍ استئناف جلستك...';
        hint.style.cssText =
            'position:fixed;bottom:18px;left:50%;transform:translateX(-50%);' +
            'background:rgba(24,24,27,.95);color:#facc15;padding:10px 18px;' +
            'border-radius:10px;font-family:inherit;font-size:.9rem;z-index:9999;';
        document.body.appendChild(hint);

        try {
            var res = await fetch(api() + '/auth/me', {
                headers: { 'Authorization': 'Bearer ' + t }
            });

            if (res.status === 401 || res.status === 403) {
                clearToken();                       // انتهت الصلاحية فعلاً
                hint.remove();
                return;
            }
            if (!res.ok) { hint.remove(); return; } // عطل مؤقت — نُبقي الجلسة

            var me = await res.json();
            // نضمن وجود التوكن في الجلسة الحالية لبقية الصفحات
            try { sessionStorage.setItem('token', t); } catch (e) {}

            var dest = (me && me.player_name) ? 'categories.html' : 'profile-setup.html';

            // 🎬 استئناف جلسة: نعرض أنيميشن المنصة هنا (بعد أنيميشن الشركة —
            // PRSplash يصفّهما بالترتيب) لأن الصوت مسموح في هذا المستند.
            if (dest === 'categories.html' && window.PRSplash) {
                hint.remove();
                window.PRSplash.playPlatformThen(function () {
                    window.location.replace(dest);
                });
                return;
            }

            window.location.replace(dest);
        } catch (e) {
            hint.remove();                          // بلا إنترنت — تبقى الصفحة كما هي
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', resume);
    } else {
        resume();
    }
})();