// ============================================================
// social_bar.js — شريط حسابات التواصل الاجتماعي في كل صفحة
// يقرأ الروابط من SOCIAL_LINKS (config.js)، ويُحقن تلقائياً.
// لا يظهر داخل اللعبة الفعلية (body.in-game) كي لا يشتت اللاعب.
// المسارات في صفحات /games/ تُدار تلقائياً (أيقونات FontAwesome محمّلة أصلاً).
// ============================================================

(function () {
    if (document.querySelector('.social-bar')) return;  // لا تكرار

    //  لا نظهر داخل صفحات اللعبة الفعلية (يشتت اللاعب أثناء المباراة)
    if (/\/games\//.test(window.location.pathname)) return;

    // بيانات المنصات: المفتاح (يطابق SOCIAL_LINKS) + الأيقونة + الاسم + اللون
    var PLATFORMS = [
        { key: 'twitter',   icon: 'fa-x-twitter',   label: 'X',        color: '#ffffff' },
        { key: 'instagram', icon: 'fa-instagram',   label: 'إنستغرام', color: '#e1306c' },
        { key: 'tiktok',    icon: 'fa-tiktok',      label: 'تيك توك',  color: '#00f2ea' },
        { key: 'snapchat',  icon: 'fa-snapchat',    label: 'سناب شات', color: '#fffc00' },
        { key: 'threads',   icon: 'fa-threads',     label: 'ثريدز',    color: '#ffffff' },
        { key: 'facebook',  icon: 'fa-facebook-f',  label: 'فيسبوك',   color: '#1877f2' },
    ];

    function build() {
        var links = (typeof SOCIAL_LINKS !== 'undefined') ? SOCIAL_LINKS : {};
        var active = PLATFORMS.filter(function (p) {
            return links[p.key] && String(links[p.key]).trim() !== '';
        });
        if (active.length === 0) return;  // لا روابط مضبوطة

        var bar = document.createElement('div');
        bar.className = 'social-bar';
        bar.setAttribute('role', 'navigation');
        bar.setAttribute('aria-label', 'حسابات التواصل الاجتماعي');

        var label = document.createElement('span');
        label.className = 'social-bar-label';
        label.textContent = 'تابعنا';
        bar.appendChild(label);

        active.forEach(function (p) {
            var a = document.createElement('a');
            a.className = 'social-icon social-' + p.key;
            a.href = links[p.key];
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            a.title = p.label;
            a.setAttribute('aria-label', p.label);
            a.style.setProperty('--sc', p.color);

            var i = document.createElement('i');
            i.className = 'fa-brands ' + p.icon;
            a.appendChild(i);
            bar.appendChild(a);
        });

        document.body.appendChild(bar);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();
