/**
 * 🎵 PlayRush Music — موسيقى خلفية توليدية (WebAudio، صفر ملفات = صفر حقوق)
 *
 * الأجواء:
 *   calm   → صفحات التسجيل (index/login/register/…): pads هادئة بطيئة.
 *   menu   → categories + اللوبيات: لحن موحّد **مستمر عبر التنقل**
 *            (نحفظ موضع العزف في sessionStorage ونستأنف من نفس الخطوة —
 *             فلا تشعر أن الصفحة تغيّرت).
 *   لكل لعبة سمتها الخاصة: huroof/career/bank/knowledge/whoami.
 *
 * صُمّمت بحذر ضد الإزعاج: سلالم پنتاتونية (لا نشاز)، مستوى منخفض جداً،
 * إيقاع بطيء، وتتبع زر الكتم العام 🔊 (PRSound). تبدأ بعد أول تفاعل
 * (سياسة المتصفحات) بتلاشٍ ناعم.
 */
(function () {
    // ===== تحديد الجو من الصفحة =====
    const path = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
    let THEME = null;
    if (/^(index|login|register|forgot-password|reset-password|verify-code|profile-setup)\.html$/.test(path) || path === '') THEME = 'calm';
    else if (/^(categories|lobby)\.html$/.test(path)) THEME = 'menu';
    else {
        const m = path.match(/^(huroof|career|bank|knowledge|whoami)(_party)?\.html$/);
        if (m) THEME = 'g_' + m[1];
    }
    if (!THEME) return;

    // ===== السمات (سلم + إيقاع + طابع) =====
    // النغمات: أرقام MIDI؛ السلالم پنتاتونية/مقامية مأمونة النشاز
    const THEMES = {
        calm:        { scale: [57, 60, 62, 64, 67, 69, 72], step: 900,  padEvery: 8,  bass: false, type: 'sine',     vol: 0.035, padVol: 0.05 },
        menu:        { scale: [60, 62, 65, 67, 69, 72, 74], step: 520,  padEvery: 8,  bass: true,  type: 'triangle', vol: 0.045, padVol: 0.045 },
        g_huroof:    { scale: [62, 64, 66, 69, 71, 74, 76], step: 450,  padEvery: 8,  bass: true,  type: 'triangle', vol: 0.045, padVol: 0.04 },
        g_career:    { scale: [55, 60, 62, 64, 67, 72, 74], step: 400,  padEvery: 4,  bass: true,  type: 'square',   vol: 0.028, padVol: 0.035 },
        g_bank:      { scale: [57, 60, 63, 65, 67, 70, 72], step: 480,  padEvery: 8,  bass: true,  type: 'triangle', vol: 0.045, padVol: 0.04 },
        g_knowledge: { scale: [60, 64, 65, 67, 71, 72, 76], step: 750,  padEvery: 8,  bass: false, type: 'sine',     vol: 0.04,  padVol: 0.05 },
        g_whoami:    { scale: [57, 58, 62, 64, 65, 69, 70], step: 620,  padEvery: 8,  bass: true,  type: 'sine',     vol: 0.04,  padVol: 0.045 },
    };
    const T = THEMES[THEME];
    const midi = (n) => 440 * Math.pow(2, (n - 69) / 12);

    // تسلسل حتمي (نفس اللحن دائماً → الاستئناف بالخطوة يعطي استمرارية حقيقية)
    function seededNote(step) {
        // مولّد شبه عشوائي حتمي بالخطوة (LCG مصغّر)
        const r = Math.abs(Math.sin(step * 12.9898 + 78.233) * 43758.5453) % 1;
        return T.scale[Math.floor(r * T.scale.length)];
    }

    let ctx = null, master = null, running = false, step = 0, timer = null;
    const POS_KEY = 'pr_music_pos_' + (THEME === 'menu' ? 'menu' : THEME);

    function ac() {
        if (!ctx) {
            try {
                ctx = new (window.AudioContext || window.webkitAudioContext)();
                master = ctx.createGain();
                master.gain.value = 0.0001;
                master.connect(ctx.destination);
            } catch (e) { return null; }
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }

    function _userVol() {
        // 🎚️ سلايدر الموسيقى بالإعدادات (0-100) — يُقرأ حياً مع كل نغمة
        try { const v = localStorage.getItem('musicSlider'); return v === null ? 1 : (parseInt(v, 10) / 100); }
        catch (e) { return 1; }
    }

    function note(freq, dur, vol, type, when) {
        const a = ac(); if (!a) return;
        vol = vol * _userVol();
        if (vol <= 0.0005) return;
        const t0 = a.currentTime + (when || 0);
        const o = a.createOscillator(); const g = a.createGain();
        o.type = type; o.frequency.value = freq;
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.exponentialRampToValueAtTime(vol, t0 + 0.03);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        o.connect(g); g.connect(master);
        o.start(t0); o.stop(t0 + dur + 0.05);
    }

    function tick() {
        if (window.PRSound && window.PRSound.isMuted()) {
            if (!window.__musicDiag1) { window.__musicDiag1 = 1; console.log('[music] صامت: PRSound مكتوم'); }
            return;  // يتبع الكتم العام
        }
        if (_userVol() <= 0.0005) {
            if (!window.__musicDiag2) { window.__musicDiag2 = 1; console.log('[music] صامت: musicSlider =', localStorage.getItem('musicSlider')); }
            return;
        }
        const n = seededNote(step);
        // اللحن (أرپيجيو ناعم)
        note(midi(n), T.step / 1000 * 1.6, T.vol, T.type);
        // بيس خفيف كل 4 خطوات
        if (T.bass && step % 4 === 0) {
            note(midi(T.scale[0] - 12), T.step / 1000 * 2.2, T.vol * 0.9, 'sine');
        }
        // pad طويل كل N خطوات (عمق هادئ)
        if (step % T.padEvery === 0) {
            note(midi(T.scale[2]), T.step / 1000 * T.padEvery * 0.9, T.padVol, 'sine');
            note(midi(T.scale[4]), T.step / 1000 * T.padEvery * 0.9, T.padVol * 0.8, 'sine', 0.05);
        }
        step = (step + 1) % 64;  // حلقة 64 خطوة
        // 🔗 استمرارية menu عبر الصفحات: نحفظ الموضع باستمرار
        try { sessionStorage.setItem(POS_KEY, String(step)); } catch (e) {}
    }

    function start() {
        if (running) return;
        const a = ac(); if (!a) { if(!window.__musicDiag3){window.__musicDiag3=1;console.log('[music] لا AudioContext');} return; }
        if (a.state === 'suspended') {
            // resume غير متزامن — ننتظر نجاحه ثم نبدأ (كان سبب التأخر!)
            a.resume().then(() => { if (a.state === 'running') start(); }).catch(() => {});
            return;
        }
        console.log('[music] بدأت — THEME:', THEME);
        running = true;
        // استئناف من موضع الجلسة (menu: نفس اللحن يكمل بين categories واللوبي)
        let resumed = false;
        try {
            const saved = sessionStorage.getItem(POS_KEY);
            if (saved !== null) { step = parseInt(saved, 10) % 64; resumed = true; }
        } catch (e) {}
        master.gain.cancelScheduledValues(a.currentTime);
        master.gain.setValueAtTime(0.0001, a.currentTime);
        // 🔗 صفحة متابعة (نفس الجو): دخول شبه فوري — يخفي إحساس التنقل
        master.gain.exponentialRampToValueAtTime(1.0, a.currentTime + (resumed ? 0.25 : 0.9));
        timer = setInterval(tick, T.step);
        tick();
    }

    // تبدأ بأبكر تفاعل (pointerdown أسبق من click) أو فوراً لو المتصفح سمح
    ['pointerdown', 'click', 'keydown', 'touchstart'].forEach((ev) =>
        document.addEventListener(ev, () => { ac(); start(); }, true));
    // ⚡ محاولات مبكرة كثيفة أول 5 ثوانٍ: كروم يمنح الموقع سماح autoplay
    // بعد تفاعلات سابقة (Media Engagement) — نلتقط السماح لحظة توفره
    let _tries = 0;
    const _early = setInterval(() => {
        if (running || ++_tries > 20) { clearInterval(_early); return; }
        ac(); start();
    }, 120);

    // تنظيف عند مغادرة الصفحة (يمنع طقطقة)
    window.addEventListener('pagehide', () => {
        if (timer) clearInterval(timer);
        try {
            if (master && ctx) {
                master.gain.cancelScheduledValues(ctx.currentTime);
                master.gain.setValueAtTime(master.gain.value, ctx.currentTime);
                master.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.15);
            }
        } catch (e) {}
    });
})();
