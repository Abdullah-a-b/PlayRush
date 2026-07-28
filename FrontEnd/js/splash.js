/**
 * 🎬 شاشات الانطلاق — PlayRush
 *   index.html      → أنيميشن الشركة (Isolated Person)
 *   categories.html → أنيميشن اسم المنصة (PlayRush بالخلايا)
 *
 * ⚠️ سياسة الصوت في المتصفحات: لا يُسمح بأي صوت في مستند لم يقع فيه
 * تفاعل. النقرة على «تسجيل الدخول» تحدث في مستند login، وتموت معه؛
 * فحين تصل categories يكون المستند «بكراً» ← أنيميشن صامت دائماً.
 *
 * الحل: نعرض أنيميشن المنصة في *صفحة الدخول نفسها* بعد نجاح الدخول
 * (حيث التفعيل اللاصق للمستند قائم فيعمل الصوت)، ثم ننتقل. لذلك يصدّر
 * هذا الملف واجهة:  PRSplash.show(mode, onDone)
 * وتبقى النسخة التلقائية على categories كشبكة أمان (مثلاً عودة OAuth).
 */
(function () {
    // ============================================================
    // 🔉 الصوت — سياق مشترك مع sound.js/music.js + طابور عند الحجب
    // ============================================================
    function actx() {
        try {
            return window.__prAudioCtx
                || (window.__prAudioCtx = new (window.AudioContext || window.webkitAudioContext)());
        } catch (e) { return null; }
    }

    let _queue = [], _flushed = false;

    function _emit(freq, dur, vol, when, type) {
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
        const q = _queue; _queue = [];
        q.forEach((t) => _emit(t[0], t[1], t[2], t[3], t[4]));
    }

    function _wake() {
        const a = actx(); if (!a) return;
        if (a.state === 'running') _flush();
        else { try { a.resume().then(_flush).catch(() => {}); } catch (e) {} }
    }

    function blip(freq, dur, vol, when, type) {
        const a = actx(); if (!a) return;
        if (a.state === 'running' && _queue.length === 0) { _flushed = true; _emit(freq, dur, vol, when, type); return; }
        _queue.push([freq, dur, vol, when, type]);
        _wake();
    }

    // محاولات إيقاظ متكرّرة + أول لمسة كشبكة أمان
    let _tries = 0;
    const _iv = setInterval(() => { if (_flushed || ++_tries > 14) return clearInterval(_iv); _wake(); }, 150);
    ['pointerdown', 'touchstart', 'keydown'].forEach((ev) =>
        document.addEventListener(ev, _wake, true));

    // ============================================================
    // 🎨 التنسيق (يُحقن مرة واحدة)
    // ============================================================
    function injectStyle() {
        if (document.getElementById('prSplashStyle')) return;
        const style = document.createElement('style');
        style.id = 'prSplashStyle';
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
    }

    // ============================================================
    // 🎬 العرض — قابل للاستدعاء من أي صفحة
    //    PRSplash.show('platform', () => { ... })
    // ============================================================
    let _chain = Promise.resolve();
    function show(mode, onDone) {
        // لو كان أنيميشن آخر يُعرض (الشركة على index) ننتظره ثم نعرض — لا نُلغي
        _chain = _chain.then(() => new Promise((resolve) => {
            _show(mode, () => { try { onDone && onDone(); } catch (e) {} resolve(); });
        }));
    }

    function _show(mode, done) {
        injectStyle();
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
        }

        const mount = () => {
            document.body.appendChild(el);
            _wake();   // نطلب الإذن فوراً — على صفحة الدخول يكون ممنوحاً
            if (mode === 'platform') {
                // عُرض فعلاً → لا يتكرّر في categories
                try {
                    sessionStorage.setItem('pr_splash_platform', '1');
                    sessionStorage.removeItem('pr_splash_ticket');
                } catch (e) {}
            }

            let closed = false;
            const close = () => {
                if (closed) return; closed = true;
                el.classList.add('hide');
                setTimeout(() => el.remove(), 550);
                setTimeout(done, 350);   // ننتقل أثناء التلاشي = انتقال ناعم
            };

            const IS_APP = window.PR_IS_APP === true || (typeof window.Capacitor !== 'undefined');

            if (mode === 'platform') {
                // نُجمّد الحركة حتى نعرف هل الصوت متاح، كي لا يمضي
                // الأنيميشن صامتاً بينما ننتظر إذن المتصفح.
                const anims = el.querySelectorAll('.pr-sp-hex, .pr-sp-name, .pr-sp-skip');
                anims.forEach((a) => { a.style.animationPlayState = 'paused'; });

                let started = false;
                const run = () => {
                    if (started) return; started = true;
                    if (gate && gate.parentNode) gate.remove();
                    anims.forEach((a) => { a.style.animationPlayState = 'running'; });
                    blip(523, 0.12, 0.08, 0.40, 'triangle');
                    blip(587, 0.12, 0.08, 0.55, 'triangle');
                    blip(659, 0.12, 0.08, 0.70, 'triangle');
                    blip(784, 0.12, 0.08, 0.85, 'triangle');
                    blip(880, 0.12, 0.08, 1.00, 'triangle');
                    blip(1047, 0.40, 0.10, 1.20, 'triangle');
                    el.addEventListener('click', close);
                    setTimeout(close, 2400);
                };

                // بوابة «المس للبدء» — تظهر فقط لو رفض المتصفح فتح الصوت
                // (الحالة الوحيدة عملياً: العودة من مصادقة جوجل على الويب،
                //  فالمستند جديد بعد تنقّل خارجي ولا تفاعل فيه).
                let gate = null;
                const showGate = () => {
                    if (started || gate) return;
                    gate = document.createElement('div');
                    gate.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;'
                        + 'justify-content:center;flex-direction:column;gap:14px;background:#0b0e14;z-index:2;';
                    gate.innerHTML = '<div style="font-size:2rem;">🎮</div>'
                        + '<div style="color:#c9d1d9;font-weight:700;letter-spacing:2px;">المس للبدء</div>'
                        + '<div style="color:#8b949e;font-size:.75rem;">PlayRush</div>';
                    el.appendChild(gate);
                    el.addEventListener('click', () => { _wake(); run(); }, { once: true });
                    setTimeout(run, 2500);   // لا نحبس أحداً: يمضي صامتاً لو لم يلمس
                };

                _wake();
                let waited = 0;
                const poll = setInterval(() => {
                    const a = window.__prAudioCtx;
                    if (started) { clearInterval(poll); return; }
                    if (a && a.state === 'running') { clearInterval(poll); run(); }
                    else if ((waited += 60) >= 300) { clearInterval(poll); showGate(); }
                }, 60);
                return;
            }

            // ---- mode === 'company' ----
            if (IS_APP) {
                blip(392, 0.5, 0.07, 0.25, 'sine');
                blip(587, 0.7, 0.07, 0.70, 'sine');
                el.addEventListener('click', close);
                setTimeout(close, 1400);
                return;
            }
            // على الويب: index مستند بكر أيضاً → شاشة «المس للبدء» تمنح الإذن
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
                if (started) { close(); return; }
                started = true;
                _wake();
                tap.remove();
                anims.forEach((a) => { a.style.animationPlayState = 'running'; });
                blip(392, 0.5, 0.07, 0.35, 'sine');
                blip(587, 0.7, 0.07, 0.90, 'sine');
                setTimeout(close, 2400);
            });
        };

        if (document.body) mount();
        else document.addEventListener('DOMContentLoaded', mount);
    }

    window.PRSplash = {
        show: show,
        // يُستدعى من login/profile-setup/session_resume قبل الانتقال
        playPlatformThen: function (redirect) {
            // التذكرة تُستهلك عند العرض الفعلي فقط؛ لو تعذّر العرض هنا
            // (مهلة الأمان) تبقى فيظهر الأنيميشن في categories بدل ضياعه.
            try { sessionStorage.setItem('pr_splash_ticket', '1'); } catch (e) {}
            let went = false;
            const go = () => { if (went) return; went = true; redirect(); };
            setTimeout(go, 4000);        // أمان: لا نعلّق المستخدم أبداً
            show('platform', go);
        }
    };

    // ============================================================
    // التشغيل التلقائي حسب الصفحة (شبكة أمان: OAuth، فتح مباشر…)
    // ============================================================
    const page = (location.pathname.split('/').pop() || '')
        .toLowerCase().replace(/\.html$/, '') || 'index';
    let mode = null;
    if (page === 'index') mode = 'company';
    else if (page === 'categories') mode = 'platform';
    if (!mode) return;

    const FLAG = mode === 'company' ? 'pr_splash_company' : 'pr_splash_platform';
    let ticket = false;
    if (mode === 'platform') {
        try { ticket = sessionStorage.getItem('pr_splash_ticket') === '1'; } catch (e) {}
        if (!ticket && /[?&]token=/.test(location.search)) ticket = true;   // عودة جوجل
        if (ticket) { try { sessionStorage.removeItem('pr_splash_ticket'); } catch (e) {} }
    }
    if (!ticket) {
        try { if (sessionStorage.getItem(FLAG)) return; } catch (e) { return; }
    }
    show(mode, function () {
        if (mode === 'company') { try { sessionStorage.setItem(FLAG, '1'); } catch (e) {} }
    });
})();