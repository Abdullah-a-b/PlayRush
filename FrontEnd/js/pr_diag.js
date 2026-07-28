/* ============================================================
   PlayRush — لوحة تشخيص الصوت/الأنيميشن (مؤقتة، تُحذف بعد الحل)
   الاستخدام: أضف السطر التالي قبل </body> في categories.html:
       <script src="js/pr_diag.js" defer></script>
   تظهر لوحة صغيرة أسفل يمين الشاشة تعرض حالة كل بوابة صوت،
   وتُحدَّث كل نصف ثانية. زر «شغّل الموسيقى» يفرض التشغيل يدوياً.
   ============================================================ */
(function () {
    function el(tag, css, txt) {
        var e = document.createElement(tag);
        if (css) e.style.cssText = css;
        if (txt) e.textContent = txt;
        return e;
    }

    function mount() {
        var box = el('div',
            'position:fixed;bottom:8px;right:8px;z-index:2147483647;'
            + 'background:rgba(8,10,20,.94);color:#c9d1d9;border:1px solid #30363d;'
            + 'border-radius:10px;padding:10px 12px;font:12px/1.7 monospace;'
            + 'direction:ltr;text-align:left;max-width:300px;');

        var pre = el('div');
        var btn = el('button', 'margin-top:8px;width:100%;padding:6px;cursor:pointer;'
            + 'background:#facc15;border:0;border-radius:6px;font-weight:700;', 'FORCE MUSIC START');
        var hide = el('button', 'margin-top:4px;width:100%;padding:4px;cursor:pointer;'
            + 'background:#30363d;color:#c9d1d9;border:0;border-radius:6px;', 'hide');

        btn.onclick = function () {
            if (window.PRMusic) window.PRMusic.start();
            else alert('PRMusic غير موجود — music.js لم يُنفَّذ على هذه الصفحة!');
        };
        hide.onclick = function () { box.remove(); };

        box.appendChild(pre); box.appendChild(btn); box.appendChild(hide);
        document.body.appendChild(box);

        function ls(k) { try { var v = localStorage.getItem(k); return v === null ? 'null' : v; } catch (e) { return 'ERR'; } }
        function ss(k) { try { var v = sessionStorage.getItem(k); return v === null ? 'null' : v; } catch (e) { return 'ERR'; } }

        setInterval(function () {
            var lines = [];
            var _pg = (location.pathname.split('/').pop() || '').toLowerCase().replace(/\.html$/, '') || 'index';
            lines.push('page        : ' + _pg + '   (raw: ' + location.pathname + ')');
            lines.push('music.js run: ' + (window.PRMusic ? 'YES' : '*** NO ***'));
            if (window.PRMusic) {
                var st = window.PRMusic.state();
                Object.keys(st).forEach(function (k) {
                    lines.push(('m.' + k + '            ').slice(0, 12) + ': ' + st[k]);
                });
            }
            lines.push('PRSound     : ' + (window.PRSound ? 'yes' : 'NO'));
            lines.push('muted pref  : ' + ls('pr_sound_muted'));
            lines.push('musicSlider : ' + ls('musicSlider'));
            lines.push('sfxSlider   : ' + ls('sfxSlider'));
            lines.push('_prev_music : ' + ls('_prev_musicSlider'));
            lines.push('splash flag : ' + ss('pr_splash_platform'));
            lines.push('splash tick : ' + ss('pr_splash_ticket'));
            lines.push('SW ctrl     : ' + (navigator.serviceWorker && navigator.serviceWorker.controller ? 'yes' : 'no'));
            pre.textContent = lines.join('\n');
        }, 500);
    }

    if (document.body) mount();
    else document.addEventListener('DOMContentLoaded', mount);
})();