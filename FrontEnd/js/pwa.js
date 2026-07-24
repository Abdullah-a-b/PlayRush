/* ============================================================
   PlayRush — تفعيل الـPWA
   • يسجّل الـservice worker (على الويب فقط، لا داخل تطبيق Capacitor).
   • يتحقق من التحديثات ويطبّقها فوراً بلا نسخ قديمة عالقة.
   • يوفّر prShowInstall() لعرض زر "تثبيت التطبيق" عند توفّره.
   ============================================================ */
(function () {
    // داخل تطبيق Capacitor الملفات محلية أصلاً — لا حاجة لـSW
    // (نفحص جسر Capacitor لأن androidScheme:"https" يجعل العنوان https://localhost)
    // نُسجّل الـservice worker كلما كانت الصفحة تُخدم عبر http(s) —
    // بما في ذلك داخل التطبيق. فبعد تحويله ليحمّل من الموقع (server.url)
    // صار كل انتقال بين الصفحات يُنزّل كل الملفات من جديد، فيبدو بطيئاً.
    // الكاش يجعل التنقّل شبه فوري. نتخطّاه فقط في المخططات المحلية
    // (capacitor:// أو file://) حيث لا ينطبق أصلاً.
    var localScheme = /^(capacitor|file|ionic):$/.test(window.location.protocol);
    if (localScheme || !('serviceWorker' in navigator)) return;

    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js').then(function (reg) {
            // لو وصلت نسخة جديدة، فعّلها فوراً وأعد التحميل مرة واحدة
            reg.addEventListener('updatefound', function () {
                var nw = reg.installing;
                if (!nw) return;
                nw.addEventListener('statechange', function () {
                    if (nw.state === 'installed' && navigator.serviceWorker.controller) {
                        nw.postMessage('SKIP_WAITING');
                    }
                });
            });
            reg.update();
        }).catch(function () { /* التسجيل ليس حرجاً */ });

        var reloaded = false;
        navigator.serviceWorker.addEventListener('controllerchange', function () {
            if (reloaded) return;
            reloaded = true;
            window.location.reload();
        });
    });

    // ---- زر التثبيت (أندرويد/كروم) ----
    var deferred = null;
    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferred = e;
        window.dispatchEvent(new CustomEvent('pr-install-available'));
    });

    window.prShowInstall = function () {
        if (!deferred) {
            // آيفون: لا يدعم التثبيت البرمجي — نرشد المستخدم
            var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
            if (isIOS && typeof prAlert === 'function') {
                prAlert('لتثبيت PlayRush على آيفون:\n\n١) افتح الموقع في Safari\n٢) اضغط زر المشاركة ⬆️\n٣) اختر «إضافة إلى الشاشة الرئيسية»', 'تثبيت التطبيق');
            }
            return Promise.resolve(false);
        }
        deferred.prompt();
        return deferred.userChoice.then(function (res) {
            deferred = null;
            return res && res.outcome === 'accepted';
        });
    };

    window.prCanInstall = function () { return !!deferred; };
})();
