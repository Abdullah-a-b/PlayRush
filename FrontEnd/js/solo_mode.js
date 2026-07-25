/* ============================================================
   الوضع الفردي — شاشة اختيار المستوى والإطلاق
   ------------------------------------------------------------
   يعرض 4 مستويات، ثم يفتح صفحة حروف بوضع فردي عبر رابط الصفحة.
   ============================================================ */
(function () {
    var LEVELS = [
        { id: 'beginner', label: 'مبتدئ',  desc: 'البوت يخطئ كثيراً — مثالي للتعلّم', icon: '🌱' },
        { id: 'medium',   label: 'متوسط',  desc: 'منافسة متوازنة',                    icon: '⚖️' },
        { id: 'hard',     label: 'صعب',    desc: 'البوت سريع ودقيق — ركّز جيداً',    icon: '🔥' },
        { id: 'expert',   label: 'خبير',   desc: 'نادراً ما يخطئ — تحدٍّ حقيقي',      icon: '👑' },
    ];

    function launch(gameMode, difficulty) {
        // نمرّر الوضع الفردي عبر رابط صفحة اللعبة
        window.location.href = 'games/' + gameMode + '.html?solo=1&difficulty=' + difficulty;
    }

    function openLevelPicker(gameMode) {
        if (document.getElementById('soloPickerOverlay')) return;

        var overlay = document.createElement('div');
        overlay.id = 'soloPickerOverlay';
        overlay.style.cssText =
            'position:fixed;inset:0;z-index:10001;background:rgba(8,3,15,.85);' +
            'display:flex;align-items:center;justify-content:center;padding:18px;';

        var box = document.createElement('div');
        box.style.cssText =
            'max-width:380px;width:100%;background:linear-gradient(180deg,#2a0d40,#1a0828);' +
            'border:1px solid rgba(250,204,21,.35);border-radius:18px;padding:22px 18px;' +
            'color:#f3e9ff;font-family:inherit;box-shadow:0 20px 55px rgba(0,0,0,.6);';

        var title = document.createElement('div');
        title.innerHTML = '<div style="font-size:1.6rem;margin-bottom:4px;">🤖</div>' +
            '<h3 style="margin:0 0 4px;color:#ffe14d;">الوضع الفردي</h3>' +
            '<p style="margin:0 0 16px;font-size:.9rem;color:#cbb8e6;">' +
            'العب خلية الحروف ضد الكمبيوتر — اختر مستوى التحدّي</p>';
        box.appendChild(title);

        LEVELS.forEach(function (lv) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.style.cssText =
                'display:flex;align-items:center;gap:12px;width:100%;text-align:right;' +
                'margin-bottom:9px;padding:13px 14px;border:1px solid rgba(255,255,255,.12);' +
                'border-radius:13px;background:rgba(255,255,255,.05);color:#f3e9ff;' +
                'font-family:inherit;cursor:pointer;transition:.15s;';
            btn.onmouseenter = function () { btn.style.background = 'rgba(250,204,21,.14)'; };
            btn.onmouseleave = function () { btn.style.background = 'rgba(255,255,255,.05)'; };
            btn.innerHTML =
                '<span style="font-size:1.5rem;">' + lv.icon + '</span>' +
                '<span style="flex:1;"><b style="display:block;font-size:1rem;">' + lv.label + '</b>' +
                '<span style="font-size:.78rem;color:#bda9d6;">' + lv.desc + '</span></span>';
            btn.onclick = function () { launch(gameMode, lv.id); };
            box.appendChild(btn);
        });

        var cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.textContent = 'إلغاء';
        cancel.style.cssText =
            'width:100%;margin-top:6px;padding:11px;border:none;border-radius:12px;' +
            'background:rgba(255,255,255,.1);color:#e8dcff;font-family:inherit;cursor:pointer;';
        cancel.onclick = function () { overlay.remove(); };
        box.appendChild(cancel);

        overlay.appendChild(box);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.remove();
        });
        document.body.appendChild(overlay);
    }

    function init() {
        document.querySelectorAll('.solo-btn[data-solo]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();   // لا يفتح اللوبي
                openLevelPicker(btn.getAttribute('data-solo'));
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
