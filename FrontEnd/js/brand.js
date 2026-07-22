// ============================================================
// brand.js — شريط الهوية + الشريط السفلي الموحّد على الجوال
// على الديسكتوب: يحقن .brand-footer كما كان
// على الجوال (≤640px): يحقن .pr-unified-bar يجمع:
//   [البراند] .......... [زر الصوت] .......... [السوشال]
// ============================================================

(function() {
    if (document.querySelector('.brand-footer') || document.querySelector('.pr-unified-bar')) return;

    //  داخل صفحات الألعاب لا نُظهر أي شريط سفلي (لا براند ولا سوشال) —
    //  كتم الصوت يظهر كزر عائم مستقل من sound.js. هذا يزيل الشريط السفلي المزعج.
    if (/\/games\//.test(window.location.pathname)) return;

    const IS_MOBILE = () => window.innerWidth <= 640;

    function injectDesktop() {
        const footer = document.createElement('div');
        footer.className = 'brand-footer';

        const bySpan = document.createElement('span');
        bySpan.className = 'brand-by';
        bySpan.textContent = 'Powered by';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'brand-name';
        nameSpan.textContent = 'Isolated Person';

        footer.appendChild(bySpan);
        footer.appendChild(document.createTextNode(' '));
        footer.appendChild(nameSpan);
        document.body.appendChild(footer);
    }

    function injectMobileBar() {
        // لا نكرر
        if (document.querySelector('.pr-unified-bar')) return;

        const bar = document.createElement('div');
        bar.className = 'pr-unified-bar';

        // ── يسار: البراند ──
        const brand = document.createElement('span');
        brand.className = 'pub-brand';
        brand.innerHTML = '<span class="pub-by">Powered by</span> <span class="pub-name">Isolated Person</span>';
        bar.appendChild(brand);

        // ── وسط: زر الصوت (placeholder — sound.js يعبّئه لاحقاً) ──
        const soundSlot = document.createElement('span');
        soundSlot.id = 'prSoundSlot';
        soundSlot.className = 'pub-sound';
        bar.appendChild(soundSlot);

        // ── يمين: السوشال (placeholder — social_bar.js يعبّئه لاحقاً) ──
        const socialSlot = document.createElement('span');
        socialSlot.id = 'prSocialSlot';
        socialSlot.className = 'pub-social';
        bar.appendChild(socialSlot);

        document.body.appendChild(bar);
    }

    function init() {
        if (IS_MOBILE()) {
            injectMobileBar();
        } else {
            injectDesktop();
        }

        // إعادة حساب لو غيّر المستخدم اتجاه الشاشة
        let lastMobile = IS_MOBILE();
        window.addEventListener('resize', function() {
            const nowMobile = IS_MOBILE();
            if (nowMobile !== lastMobile) {
                lastMobile = nowMobile;
                // أزل الإصدار القديم واحقن الصح
                const old = document.querySelector('.brand-footer, .pr-unified-bar');
                if (old) old.remove();
                nowMobile ? injectMobileBar() : injectDesktop();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();