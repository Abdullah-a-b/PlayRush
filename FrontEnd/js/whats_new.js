/* ============================================================
   PlayRush — "جديدنا" (إعلان التحديثات)
   ------------------------------------------------------------
   يعرض ما استجدّ مرة واحدة لكل إصدار، على الموقع والتطبيق معاً.
   يظهر تلقائياً حين يتغيّر رقم النسخة (WHATS_NEW.version).
   المستخدم يراه مرة، ثم يُحفظ أنه شاهده فلا يتكرّر.
   ============================================================ */
(function () {
    // ═══ حدّث هذا عند كل ميزة جديدة ═══
    var WHATS_NEW = {
        version: '2026.07.27',      // معرّف الإصدار (غيّره ليظهر الإعلان)
        title: '🎉 جديد في PlayRush',
        items: [
            { icon: '🤖', text: 'الوضع الفردي: العب خلية الحروف ضد الكمبيوتر بأربعة مستويات!' },
            { icon: '⚡', text: 'أسئلة جديدة تُولّد تلقائياً — تكرار أقل ومتعة أكثر.' },
            { icon: '✨', text: 'تحسينات في الأداء وثبات أفضل في كل الألعاب.' },
        ],
    };

    var SEEN_KEY = 'pr_whatsnew_seen';

    function alreadySeen() {
        try { return localStorage.getItem(SEEN_KEY) === WHATS_NEW.version; }
        catch (e) { return true; }
    }
    function markSeen() {
        try { localStorage.setItem(SEEN_KEY, WHATS_NEW.version); } catch (e) {}
    }

    function show() {
        if (document.getElementById('whatsNewOverlay')) return;

        var overlay = document.createElement('div');
        overlay.id = 'whatsNewOverlay';
        overlay.style.cssText =
            'position:fixed;inset:0;z-index:10002;background:rgba(8,3,15,.82);' +
            'display:flex;align-items:center;justify-content:center;padding:18px;' +
            'animation:prwnFade .25s ease;';

        var box = document.createElement('div');
        box.style.cssText =
            'max-width:380px;width:100%;background:linear-gradient(180deg,#3a1257,#22093a);' +
            'border:1px solid rgba(250,204,21,.4);border-radius:20px;padding:24px 20px;' +
            'color:#f3e9ff;font-family:inherit;box-shadow:0 22px 60px rgba(0,0,0,.6);';

        var html = '<h2 style="margin:0 0 18px;text-align:center;color:#ffe14d;' +
                   'font-size:1.3rem;">' + WHATS_NEW.title + '</h2>';
        WHATS_NEW.items.forEach(function (it) {
            html += '<div style="display:flex;gap:12px;align-items:flex-start;' +
                    'margin-bottom:14px;padding:12px;background:rgba(255,255,255,.05);' +
                    'border-radius:12px;">' +
                    '<span style="font-size:1.5rem;flex-shrink:0;">' + it.icon + '</span>' +
                    '<span style="font-size:.94rem;line-height:1.6;">' + it.text + '</span></div>';
        });
        box.innerHTML = html;

        var btn = document.createElement('button');
        btn.textContent = 'يلا نلعب! 🚀';
        btn.style.cssText =
            'width:100%;margin-top:8px;padding:13px;border:none;border-radius:13px;' +
            'background:linear-gradient(180deg,#ffd93d,#f0a500);color:#2a0d40;' +
            'font-family:inherit;font-weight:800;font-size:1.05rem;cursor:pointer;';
        btn.onclick = function () { markSeen(); overlay.remove(); };
        box.appendChild(btn);

        overlay.appendChild(box);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { markSeen(); overlay.remove(); }
        });
        document.body.appendChild(overlay);

        if (!document.getElementById('prwnStyle')) {
            var st = document.createElement('style');
            st.id = 'prwnStyle';
            st.textContent = '@keyframes prwnFade{from{opacity:0}to{opacity:1}}';
            document.head.appendChild(st);
        }
    }

    function init() {
        if (alreadySeen()) return;
        setTimeout(show, 1000);   // بعد استقرار الصفحة
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
