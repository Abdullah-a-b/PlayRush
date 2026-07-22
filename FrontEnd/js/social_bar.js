// ============================================================
// social_bar.js — شريط السوشال ميديا
// ديسكتوب: يحقن .social-bar المستقل كما كان
// جوال: يحقن الأيقونات داخل #prSocialSlot (شريط brand الموحّد)
// ============================================================

(function () {
    if (document.querySelector('.social-bar')) return;
    if (/\/games\//.test(window.location.pathname)) return;

    var PLATFORMS = [
        { key: 'twitter',   icon: 'fa-x-twitter',   label: 'X',        color: '#ffffff' },
        { key: 'instagram', icon: 'fa-instagram',   label: 'إنستغرام', color: '#e1306c' },
        { key: 'tiktok',    icon: 'fa-tiktok',      label: 'تيك توك',  color: '#00f2ea' },
        { key: 'snapchat',  icon: 'fa-snapchat',    label: 'سناب شات', color: '#fffc00' },
        { key: 'threads',   icon: 'fa-threads',     label: 'ثريدز',    color: '#ffffff' },
        { key: 'facebook',  icon: 'fa-facebook-f',  label: 'فيسبوك',   color: '#1877f2' },
    ];

    function buildIcons(container) {
        var links = (typeof SOCIAL_LINKS !== 'undefined') ? SOCIAL_LINKS : {};
        var active = PLATFORMS.filter(function(p) {
            return links[p.key] && String(links[p.key]).trim() !== '';
        });
        if (active.length === 0) return false;

        active.forEach(function(p) {
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
            container.appendChild(a);
        });
        return true;
    }

    function build() {
        var IS_MOBILE = window.innerWidth <= 640;

        if (IS_MOBILE) {
            // انتظر الشريط الموحّد من brand.js ثم احقن فيه
            function trySlot(attempts) {
                var slot = document.getElementById('prSocialSlot');
                if (slot) {
                    buildIcons(slot);
                } else if (attempts > 0) {
                    setTimeout(function() { trySlot(attempts - 1); }, 80);
                }
            }
            trySlot(15);
        } else {
            // ديسكتوب: الشريط المستقل القديم
            var bar = document.createElement('div');
            bar.className = 'social-bar';
            bar.setAttribute('role', 'navigation');
            bar.setAttribute('aria-label', 'حسابات التواصل الاجتماعي');

            var label = document.createElement('span');
            label.className = 'social-bar-label';
            label.textContent = 'تابعنا';
            bar.appendChild(label);

            if (buildIcons(bar)) {
                document.body.appendChild(bar);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();