/**
 * 🎬 شاشات الانطلاق — مفصولة حسب الصفحة (بلا إزعاج):
 *   index.html      → أنيميشن الشركة (Isolated Person)
 *   categories.html → أنيميشن اسم المنصة (PlayRush بالخلايا)
 * كلٌّ يظهر مرة واحدة لكل جلسة متصفح، ويُتخطى بأي نقرة.
 * مع مؤثرات صوتية خفيفة (best-effort — تُحجب قبل أول تفاعل بسياسة المتصفح).
 */
(function () {
    // 🩹 السبب الجذري: Cloudflare Pages يقدّم الروابط النظيفة بلا امتداد
    // (playrush.pages.dev/categories) بينما التطبيق يفتح ملفاً باسم
    // categories.html — فكانت المقارنة تفشل على الويب فقط، ويخرج السكربت
    // صامتاً بلا أي أنيميشن. نُطبّع الاسم: نحذف .html ونعالج المسار الفارغ.
    const page = (location.pathname.split('/').pop() || '')
        .toLowerCase().replace(/\.html$/, '') || 'index';
    let mode = null;
    if (page === 'index') mode = 'company';
    else if (page === 'categories') mode = 'platform';
    if (!mode) return;

    const FLAG = mode === 'company' ? 'pr_splash_company' : 'pr_splash_platform';

    // ============================================================
    // 🩹 السبب الحقيقي لاختفاء أنيميشن المنصة:
    // كان الشرط الوحيد هو علم في sessionStorage «مرة لكل جلسة».
    // لكن sessionStorage لا يموت كما نظن:
    //   • يبقى عبر كل التنقلات في نفس التبويب (categories → لوبي → رجوع)
    //   • ويعيده كروم كما هو عند «استعادة التبويبات» بعد إغلاق المتصفح
    // فمن أول زيارة واحدة لصفحة categories يُدفن الأنيميشن للأبد.
    //
    // الحل: «تذكرة» تُصدر عند كل دخول حقيقي (login / تسجيل / استئناف
    // جلسة / OAuth). وجود التذكرة يفرض العرض متجاوزاً العلم.
    // ============================================================
    let ticket = false;
    if (mode === 'platform') {
        try { ticket = sessionStorage.getItem('pr_splash_ticket') === '1'; } catch (e) {}
        // عودة جوجل: ?token=... في الرابط = دخول جديد بالتأكيد
        if (!ticket && /[?&]token=/.test(location.search)) ticket = true;
        if (ticket) { try { sessionStorage.removeItem('pr_splash_ticket'); } catch (e) {} }
    }
    if (!ticket) {
        try {
            if (sessionStorage.getItem(FLAG)) return;
        } catch (e) { return; }
    }
    // حارس ضد تركيب مزدوج داخل نفس الصفحة
    if (window.__prSplashMounted) return;
    window.__prSplashMounted = true;

    // ============================================================
    // 🔉 نغمات الأنيميشن
    // كانت تُلغى بصمت: `if (a.state === 'suspended') return;` — وعند الوصول
    // إلى categories بعد تنقّل، المستند جديد ولم يقع فيه أي تفاعل بعد،
    // فالسياق مُعلّق دائماً ← أنيميشن بلا صوت. الآن:
    //   ١) نستخدم السياق المشترك مع sound.js/music.js
    //   ٢) نحاول إيقاظه (resume) فوراً وبمحاولات متكرّرة قصيرة
    //   ٣) لو ظلّ محجوباً، نصفّ النغمات في طابور يُفرَّغ عند أول لمسة
    // ============================================================
    function actx() {
        try {
            return window.__prAudioCtx
                || (window.__prAudioCtx = new (window.AudioContext || window.webkitAudioContext)());
        } catch (e) { return null; }
    }

    let _queue = [], _flushed = false;

    function _emit(freq, dur, vol, when, type) {
        // يحترم زر الكتم العام لو كان sound.js قد حُمّل
        if (window.PRSound && window.PRSound.isMuted && window.PRSound.isMuted()) return;
        const a = actx(); if (!a || a.state !== 'running') return;
        try {
            const t0 = a.currentTime + (when || 0);
            const o = a.createOscillator(); const g = a.createGain();
            o.type = type || 'sine'; o.frequency.value = freq;
            g.gain.setValueAtTime(0.0001, t0);
            g.gain.exponentialRampToValueAtTime(vol || 0.1, t0 + 0.02);
            g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
            o.connect(g); g.connect(a.destination);
            o.start(t0); o.stop(t0 + dur + 0.05);
        } catch (e) {}
    }

    function _flush() {
        if (_flushed) return;
        const a = actx(); if (!a || a.state !== 'running') return;
        _flushed = true;
        _queue.forEach((t) => _emit(t[0], t[1], t[2], t[3], t[4]));
        _queue = [];
    }

    function blip(freq, dur, vol, when, type) {
        const a = actx(); if (!a) return;
        if (a.state === 'running') { _flushed = true; _emit(freq, dur, vol, when, type); return; }
        _queue.push([freq, dur, vol, when, type]);
        try { a.resume().then(_flush).catch(() => {}); } catch (e) {}
    }

    // محاولات إيقاظ متكرّرة أثناء عرض الأنيميشن (كروم قد يمنح السماح متأخراً)
    let _tries = 0;
    const _wake = setInterval(() => {
        const a = window.__prAudioCtx;
        if (_flushed || ++_tries > 14) { clearInterval(_wake); return; }
        if (!a) return;
        if (a.state === 'running') _flush();
        else { try { a.resume().then(_flush).catch(() => {}); } catch (e) {} }
    }, 150);

    // شبكة أمان: أول لمسة/ضغطة في الصفحة تفتح الصوت وتُفرّغ الطابور
    ['pointerdown', 'touchstart', 'keydown'].forEach((ev) =>
        document.addEventListener(ev, () => {
            const a = actx(); if (!a) return;
            if (a.state === 'running') _flush();
            else { try { a.resume().then(_flush).catch(() => {}); } catch (e) {} }
        }, { capture: true, once: false }));

    const style = document.createElement('style');
    style.textContent = `
#prSplash{position:fixed;inset:0;background:#0b0e14;z-index:99999;display:flex;
  flex-direction:column;align-items:center;justify-content:center;gap:26px;
  transition:opacity .5s ease;cursor:pointer}
#prSplash.hide{opacity:0;pointer-events:none}
.pr-sp-company{font-size:1.35rem;letter-spacing:5px;color:#c9d1d9;font-weight:700;
  text-transform:uppercase;opacity:0;animation:prFadeUp .9s ease .3s forwards}
.pr-sp-sub{font-size:.85rem;letter-spacing:3px;color:#8b949e;
  opacity:0;animation:prFadeUp .8s ease .9s forwards}
.pr-sp-hexes{display:flex;gap:10px}
.pr-sp-hex{width:26px;height:30px;background:#facc15;
  clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%);
  opacity:0;transform:translateY(24px) scale(.4) rotate(45deg);
  animation:prHexIn .55s cubic-bezier(.34,1.56,.64,1) forwards}
.pr-sp-hex:nth-child(1){animation-delay:.4s}
.pr-sp-hex:nth-child(2){animation-delay:.55s;background:#38bdf8}
.pr-sp-hex:nth-child(3){animation-delay:.7s;background:#4ade80}
.pr-sp-hex:nth-child(4){animation-delay:.85s;background:#f472b6}
.pr-sp-hex:nth-child(5){animation-delay:1s;background:#facc15}
.pr-sp-name{font-size:2.6rem;font-weight:900;color:#fff;letter-spacing:1px;
  opacity:0;animation:prFadeUp .7s ease 1.15s forwards}
.pr-sp-name span{color:#facc15}
.pr-sp-skip{position:absolute;bottom:26px;font-size:.8rem;color:#8b949e;
  opacity:0;animation:prFadeUp .6s ease 1.4s forwards}
@keyframes prHexIn{to{opacity:1;transform:translateY(0) scale(1) rotate(0)}}
@keyframes prFadeUp{from{opacity:0;transform:translateY(14px)}
  to{opacity:1;transform:translateY(0)}}`;
    document.head.appendChild(style);

    const el = document.createElement('div');
    el.id = 'prSplash';
    if (mode === 'company') {
        el.innerHTML = `
      <div class="pr-sp-company">Isolated Person</div>
      <div class="pr-sp-sub">G A M E &nbsp; S T U D I O</div>
      <div class="pr-sp-skip">اضغط للتخطي</div>`;
    } else {
        el.innerHTML = `
      <div class="pr-sp-hexes">
        <div class="pr-sp-hex"></div><div class="pr-sp-hex"></div>
        <div class="pr-sp-hex"></div><div class="pr-sp-hex"></div>
        <div class="pr-sp-hex"></div>
      </div>
      <div class="pr-sp-name">Play<span>Rush</span></div>
      <div class="pr-sp-skip">اضغط للتخطي</div>`;
        // 🔉 نغمة لكل خلية تقفز + وميض الاسم
        [523, 587, 659, 784, 880].forEach((f, i) => blip(f, 0.12, 0.08, 0.4 + i * 0.15, 'triangle'));
        blip(1047, 0.4, 0.1, 1.2, 'triangle');
    }
    const mount = () => {
        document.body.appendChild(el);
        // نعلن أن الأنيميشن نشط — ليؤجّل session_resume إعادة التوجيه
        window.__prSplashActive = true;
        const close = () => {
            try { sessionStorage.setItem(FLAG, '1'); } catch (e) {}   // 🩹 الآن فقط
            el.classList.add('hide');
            setTimeout(() => el.remove(), 550);
            window.__prSplashActive = false;
            // نُشعر من ينتظر (إعادة التوجيه) بأن الأنيميشن انتهى
            try { window.dispatchEvent(new Event('pr-splash-done')); } catch (e) {}
        };
        // 📱 داخل التطبيق: قيد التشغيل التلقائي للصوت غير موجود، وشاشة
        // «المس للبدء» تبدو تعليقاً. لذلك نبدأ فوراً وبمدة أقصر.
        var IS_APP = window.PR_IS_APP === true || (typeof window.Capacitor !== 'undefined');

        if (mode === 'company' && IS_APP) {
            try {
                const _a = actx(); if (_a) _a.resume().then(_flush).catch(() => {});
            } catch (e) {}
            blip(392, 0.5, 0.07, 0.25, 'sine');
            blip(587, 0.7, 0.07, 0.7, 'sine');
            el.addEventListener('click', close);   // نقرة = تخطٍّ فوري
            setTimeout(close, 1400);
        } else if (mode === 'company') {
            // 🔓 حل autoplay الجذري: شاشة «المس للبدء» — النقرة الأولى
            // تفتح الصوت شرعاً (سياسة المتصفح) ثم يبدأ الأنيميشن بصوته كاملاً.
            const anims = el.querySelectorAll('.pr-sp-company, .pr-sp-sub, .pr-sp-skip');
            anims.forEach((a) => { a.style.animationPlayState = 'paused'; });
            const tap = document.createElement('div');
            tap.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;'
                + 'justify-content:center;flex-direction:column;gap:14px;background:#0b0e14;z-index:2;';
            tap.innerHTML = '<div style="font-size:2rem;">🎮</div>'
                + '<div style="color:#c9d1d9;font-weight:700;letter-spacing:2px;">المس للبدء</div>'
                + '<div style="color:#8b949e;font-size:.75rem;">Isolated Person · PlayRush</div>';
            el.appendChild(tap);
            let started = false;
            el.addEventListener('click', () => {
                if (!started) {
                    started = true;
                    // النقرة فتحت الصوت — نوقظ السياق ونشغّل الأنيميشن والنغمات
                    try {
                        const _a = actx(); if (_a) _a.resume().then(_flush).catch(() => {});
                    } catch (e) {}
                    tap.remove();
                    anims.forEach((a) => { a.style.animationPlayState = 'running'; });
                    blip(392, 0.5, 0.07, 0.35, 'sine');
                    blip(587, 0.7, 0.07, 0.9, 'sine');
                    setTimeout(close, 2400);
                } else {
                    close();  // نقرة ثانية = تخطٍّ
                }
            });
        } else {
            // categories: وصل بعد نقرات (الصوت مسموح غالباً) — تلقائي كما هو
            el.addEventListener('click', close);
            setTimeout(close, 2400);
        }
    };
    if (document.body) mount();
    else document.addEventListener('DOMContentLoaded', mount);
})();