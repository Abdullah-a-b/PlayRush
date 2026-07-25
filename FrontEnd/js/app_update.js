/* ============================================================
   PlayRush — تنبيه تحديث التطبيق
   ------------------------------------------------------------
   التطبيق يُوزَّع خارج المتاجر (رابط مباشر)، فلا يوجد تحديث تلقائي.
   هنا نسأل الخادم عن أحدث إصدار ونقارنه بالمثبَّت:

     • أحدث متوفر  → تنبيه لطيف يمكن تأجيله
     • أقل من الحد الأدنى → تنبيه إلزامي لا يُغلق
       (لحالات مثل عطل يمنع التطبيق من العمل)

   الرابط ثابت: استبدل الملف نفسه في Google Drive
   (كليك يمين ← إدارة الإصدارات ← رفع إصدار جديد) فيبقى المعرّف
   كما هو ولا تحتاج توزيع رابط جديد أبداً.
   ============================================================ */
(function () {
    var SNOOZE_KEY = 'pr_update_snooze';
    var SNOOZE_MS  = 24 * 60 * 60 * 1000;   // تأجيل يوم واحد

    function isApp() {
        return window.PR_IS_APP === true || (typeof window.Capacitor !== 'undefined');
    }
    function api() {
        return (typeof CONFIG !== 'undefined' && CONFIG.API_URL) ? CONFIG.API_URL : '';
    }

    /** يقارن إصدارين بصيغة x.y.z → 1 لو a أحدث، -1 لو أقدم، 0 لو متساويان */
    function cmp(a, b) {
        var pa = String(a || '0').split('.').map(function (n) { return parseInt(n, 10) || 0; });
        var pb = String(b || '0').split('.').map(function (n) { return parseInt(n, 10) || 0; });
        for (var i = 0; i < Math.max(pa.length, pb.length); i++) {
            var x = pa[i] || 0, y = pb[i] || 0;
            if (x > y) return 1;
            if (x < y) return -1;
        }
        return 0;
    }

    function installedVersion() {
        try {
            var App = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App;
            if (App && App.getInfo) return App.getInfo().then(function (i) { return i.version; });
        } catch (e) {}
        return Promise.resolve(null);
    }

    function openLink(url) {
        // نجرّب عدة طرق بالترتيب — بعض WebViews القديمة تحجب بعضها
        try {
            var B = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Browser;
            if (B && B.open) { B.open({ url: url }); return; }
        } catch (e) {}
        try {
            var w = window.open(url, '_system');
            if (w) return;
        } catch (e) {}
        try { window.open(url, '_blank'); } catch (e) {}
        // الملاذ الأخير: التنقّل المباشر
        try { window.location.href = url; } catch (e) {}
    }

    function show(info, mandatory) {
        if (document.getElementById('prUpdateBox')) return;

        var overlay = document.createElement('div');
        overlay.id = 'prUpdateBox';
        overlay.style.cssText =
            'position:fixed;inset:0;background:rgba(8,3,15,.85);z-index:2147483600;' +
            'display:flex;align-items:center;justify-content:center;padding:20px;';

        var box = document.createElement('div');
        box.style.cssText =
            'max-width:340px;width:100%;background:linear-gradient(180deg,#3a1257,#2a0d40);' +
            'border:1px solid rgba(255,235,59,.4);border-radius:18px;padding:22px 18px;' +
            'color:#f3e9ff;text-align:center;font-family:inherit;' +
            'box-shadow:0 18px 50px rgba(0,0,0,.6);';

        var notes = info.notes ? '<p style="font-size:.88rem;color:#cbb8e6;margin:0 0 14px;">'
                                 + info.notes + '</p>' : '';
        box.innerHTML =
            '<div style="font-size:2rem;margin-bottom:6px;">⬆️</div>' +
            '<h3 style="margin:0 0 8px;color:#ffe14d;font-size:1.05rem;">' +
              (mandatory ? 'تحديث ضروري' : 'يتوفّر تحديث جديد') + '</h3>' +
            '<p style="margin:0 0 10px;font-size:.94rem;line-height:1.6;">' +
              (mandatory
                ? 'نسختك الحالية لم تعد مدعومة. حمّل النسخة الجديدة للمتابعة.'
                : 'نسخة أحدث من PlayRush متاحة الآن.') +
            '</p>' + notes;

        var dl = document.createElement('button');
        dl.textContent = '📥 تحميل التحديث';
        dl.style.cssText =
            'width:100%;padding:13px;border:none;border-radius:12px;font-family:inherit;' +
            'font-weight:800;font-size:1rem;cursor:pointer;' +
            'background:linear-gradient(180deg,#ffd93d,#f0a500);color:#2a0d40;';
        dl.onclick = function () { openLink(info.url); };
        box.appendChild(dl);

        // رابط ظاهر يمكن نسخه — ملاذ أخير لو فشلت كل طرق الفتح
        var linkRow = document.createElement('div');
        linkRow.style.cssText =
            'margin-top:12px;padding:9px;border-radius:9px;background:rgba(0,0,0,.28);' +
            'font-size:.72rem;color:#cbb8e6;word-break:break-all;direction:ltr;text-align:center;';
        linkRow.textContent = info.url;
        linkRow.onclick = function () {
            try {
                if (navigator.clipboard) navigator.clipboard.writeText(info.url);
            } catch (e) {}
        };
        box.appendChild(linkRow);

        if (!mandatory) {
            var later = document.createElement('button');
            later.textContent = 'لاحقاً';
            later.style.cssText =
                'width:100%;margin-top:9px;padding:11px;border:none;border-radius:12px;' +
                'font-family:inherit;font-size:.95rem;cursor:pointer;' +
                'background:rgba(255,255,255,.12);color:#e8dcff;';
            later.onclick = function () {
                try { localStorage.setItem(SNOOZE_KEY, String(Date.now())); } catch (e) {}
                overlay.remove();
            };
            box.appendChild(later);
        }

        overlay.appendChild(box);
        document.body.appendChild(overlay);
    }

    async function check() {
        if (!isApp() || !api()) return;          // التنبيه للتطبيق فقط

        var current = await installedVersion();   // قد تكون null في نسخ قديمة جداً

        var info;
        try {
            var res = await fetch(api() + '/app-version');
            if (!res.ok) return;
            info = await res.json();
        } catch (e) { return; }                  // بلا إنترنت — لا نزعج المستخدم

        if (!info || !info.url) return;

        // لو تعذّر معرفة الإصدار المثبَّت (إضافة App غير متوفرة في نسخة
        // قديمة)، نفترض أنها قديمة ونعرض التنبيه إن كان هناك حدّ أدنى
        // مطلوب — فالهدف إيصال رابط التحميل لمن لا يستطيع التحديث تلقائياً.
        if (!current) {
            if (info.min_supported && info.min_supported !== '0.0.0') {
                show(info, true);                 // إلزامي مع زر التحميل
            }
            return;
        }

        var mandatory = cmp(current, info.min_supported) < 0;
        var outdated  = cmp(current, info.latest) < 0;
        if (!outdated) return;

        if (!mandatory) {
            try {
                var last = parseInt(localStorage.getItem(SNOOZE_KEY), 10) || 0;
                if (Date.now() - last < SNOOZE_MS) return;   // أجّله المستخدم اليوم
            } catch (e) {}
        }
        show(info, mandatory);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { setTimeout(check, 1500); });
    } else {
        setTimeout(check, 1500);
    }
})();
