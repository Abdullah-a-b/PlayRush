// ============================================================================
//  Frontend Anti-Cheat — Server-as-Source-of-Truth
// ============================================================================
// التغييرات الرئيسية:
//   1. السيرفر هو مصدر الحقيقة — نسأل /auth/ban-status عند التحميل
//   2. لو السيرفر قال "غير محظور" → نمسح أي flag محلي قديم
//   3. blur يرفع حساسية الكاشف فقط (مش ban مباشر)
//   4. fast detection بعد blur (200ms, 500ms, 1000ms) لاكتشاف DevTools
// ============================================================================

(function() {
    'use strict';

    //  وضع التطوير يُقرأ من السيرفر (ALLOW_SAME_IP في .env) — اللاعب لا يتحكم به
    // يُضبط بعد رد /auth/ban-status. حتى يصل الرد، الحماية مفعّلة احتياطاً.
    let DEV_MODE = false;

    const MAX_VIOLATIONS = 3;
    const STORAGE_KEY = 'cv';
    const BAN_KEY = 'cb';

    let violations = 0;
    try {
        violations = parseInt(localStorage.getItem(STORAGE_KEY)) || 0;
    } catch (e) {}

    // ============================================================
    //  الخطوة الأولى: مزامنة مع السيرفر
    // قبل ما نطبّق أي ban من localStorage، نسأل السيرفر
    // لو السيرفر قال "غير محظور" → نمسح أي flag قديم
    // ============================================================
    async function syncBanStatusWithServer() {
        const apiUrl = getApiUrl();
        const token = getStoredToken();

        if (!apiUrl) return null;  // لا يمكن السؤال

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = 'Bearer ' + token;

            const response = await fetch(apiUrl + '/auth/ban-status', {
                method: 'GET',
                headers: headers,
            });

            if (!response.ok) return null;
            const data = await response.json();
            return data;
        } catch (e) {
            return null;
        }
    }

    // ============================================================
    //  نقطة البداية الذكية
    // 1. نسأل السيرفر أولاً
    // 2. لو "غير محظور" → نمسح أي ban flag محلي
    // 3. لو "محظور" → نطبّق الـ ban
    // 4. لو فشل الاتصال → نعتمد على localStorage (الوضع الافتراضي)
    // ============================================================
    async function initialize() {
        const status = await syncBanStatusWithServer();

        //  نضبط وضع التطوير من رد السيرفر (مصدر موثوق)
        if (status && status.dev_mode === true) {
            DEV_MODE = true;
            try { console.log('%c🛠️ DEV MODE: anti-cheat معطّل بالكامل', 'color:#ff9800;font-weight:bold;font-size:14px;'); } catch(e){}
            startDevModeWatcher();  // نراقب لو المطور أوقف الوضع لاحقاً
            return;  // لا نفعّل أي حماية — وضع تطوير
        }

        //  ليس وضع تطوير → نفعّل كل وسائل الحماية الآن
        activateProtections();

        if (status !== null) {
            //  السيرفر استجاب — هو مصدر الحقيقة
            if (status.banned === true) {
                executeBan('server_confirmed:' + (status.reason || 'banned'));
                return;
            } else {
                try {
                    localStorage.removeItem(BAN_KEY);
                    if (status.anticheat_score === 0) {
                        localStorage.setItem(STORAGE_KEY, '0');
                        violations = 0;
                    }
                } catch (e) {}
            }
        } else {
            try {
                if (localStorage.getItem(BAN_KEY) === '1') {
                    executeBan('previously_banned_persistent');
                    return;
                }
            } catch (e) {}
        }

        startMonitoring();
    }

    // ============================================================
    //  الكاشف الرئيسي: window size delta
    // ============================================================
    let devToolsOpen = false;
    let detectionStartTime = Date.now();
    let strictMode = false;  //  يصبح true عند blur — حساسية أعلى

    function detectDevToolsBySize() {
        if (Date.now() - detectionStartTime < 2000) return;

        const widthDiff = window.outerWidth - window.innerWidth;
        const heightDiff = window.outerHeight - window.innerHeight;
        const opened = (widthDiff > 200 || heightDiff > 200);

        if (opened && !devToolsOpen) {
            devToolsOpen = true;
            triggerViolation('devtools_size_detected' + (strictMode ? '_during_blur' : ''));
        } else if (!opened) {
            devToolsOpen = false;
        }
    }

    // ============================================================
    //  الكاشف الثاني: console timing
    // ============================================================
    function detectDevToolsByTiming() {
        const start = performance.now();
        for (let i = 0; i < 100; i++) {
            console.log('%c', '');
        }
        const elapsed = performance.now() - start;
        if (elapsed > 50) {
            triggerViolation('devtools_timing_detected' + (strictMode ? '_during_blur' : ''));
        }
        try { console.clear(); } catch (e) {}
    }

    function runDetections() {
        if (DEV_MODE) return;  //  وضع التطوير — لا كشف
        try {
            detectDevToolsBySize();
            detectDevToolsByTiming();
        } catch (e) {
            triggerViolation('detection_error:' + (e.message || 'unknown'));
        }
    }

    // ============================================================
    //  Blur/Focus — مراقبة شديدة عند فقدان الـ focus
    // الفلسفة: blur وحده ≠ خطر (الناس يفتحون tabs ثانية)
    // لكن blur + DevTools = ban
    // ============================================================
    let blurDetectionTimers = [];

    function clearBlurTimers() {
        blurDetectionTimers.forEach(clearTimeout);
        blurDetectionTimers = [];
    }

    function startBlurMonitoring() {
        //  نُفعّل strict mode (الكاشف يضيف "_during_blur" للسبب لتمييزه)
        strictMode = true;
        clearBlurTimers();

        // فحوصات سريعة متعاقبة لاكتشاف DevTools لو فُتحت أثناء الـ blur
        const intervals = [50, 200, 500, 1000, 2000, 4000];
        intervals.forEach(function(delay) {
            const t = setTimeout(runDetections, delay);
            blurDetectionTimers.push(t);
        });
    }

    function stopBlurMonitoring() {
        //  بعد رجوع الـ focus، نفحص مرة أخيرة ثم نعود للوضع العادي
        clearBlurTimers();
        runDetections();
        setTimeout(runDetections, 200);
        setTimeout(runDetections, 800);
        setTimeout(function() {
            strictMode = false;
        }, 1500);
    }

    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            startBlurMonitoring();
        } else {
            stopBlurMonitoring();
        }
    });

    window.addEventListener('blur', startBlurMonitoring);
    window.addEventListener('focus', stopBlurMonitoring);

    // ============================================================
    //  mousemove نحو الـ tabs/url bar = شك إضافي
    // ============================================================
    document.addEventListener('mousemove', function(e) {
        if (e.clientY < 0) {
            setTimeout(runDetections, 200);
            setTimeout(runDetections, 600);
            setTimeout(runDetections, 1200);
        }
    });

    // ============================================================
    //  كل وسائل الحماية (تُفعّل فقط بعد التأكد أنه ليس وضع تطوير)
    // ============================================================
    function activateProtections() {
        // keyboard shortcuts
        window.addEventListener('keydown', function(e) {
            if (DEV_MODE) return;
            if (e.repeat) return;

            const key = (e.key || '').toLowerCase();
            const isF12 = e.keyCode === 123;
            const isCtrlShift = e.ctrlKey && e.shiftKey;
            const isCtrl = e.ctrlKey;

            const blocked =
                isF12 ||
                (isCtrlShift && (key === 'i' || key === 'j' || key === 'c' || key === 'k')) ||
                (isCtrl && (key === 'u' || key === 's')) ||
                (e.metaKey && (key === 'i' || key === 'j' || key === 'c'));

            if (blocked) {
                e.preventDefault();
                e.stopPropagation();
                triggerViolation('keyboard_shortcut:' + key);
                return false;
            }
        }, true);

        window.addEventListener('contextmenu', function(e) {
            if (DEV_MODE) return;
            e.preventDefault();
        }, true);

        window.addEventListener('dragstart', function(e) {
            if (DEV_MODE) return;
            e.preventDefault();
        });
        window.addEventListener('selectstart', function(e) {
            if (DEV_MODE) return;
            if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
            if (e.target && e.target.closest && e.target.closest('.chat-message-text')) return;
            e.preventDefault();
        });

        // تعطيل console (فقط في الإنتاج)
        if (!DEV_MODE && typeof window.console !== 'undefined') {
            const noop = function() {};
            try {
                ['log', 'debug', 'info', 'warn', 'table', 'trace', 'dir', 'group', 'groupEnd'].forEach(function(method) {
                    window.console[method] = noop;
                });
            } catch (e) {}
        }
    }

    // ============================================================
    // Continuous Monitoring (يبدأ بعد الـ sync مع السيرفر)
    // ============================================================
    function startMonitoring() {
        setInterval(runDetections, 1000);
        setTimeout(runDetections, 500);
        setTimeout(runDetections, 1500);
        setTimeout(runDetections, 3000);
        window.addEventListener('resize', detectDevToolsBySize);
        startDevModeWatcher();
    }

    // ============================================================
    //  مراقب وضع التطوير — يعيد فحص dev_mode من السيرفر دورياً
    // لو تغيّرت الحالة (مطور عدّل .env) → نعيد تحميل الصفحة لتطبيقها نظيفاً
    // ============================================================
    function startDevModeWatcher() {
        setInterval(async function() {
            const status = await syncBanStatusWithServer();
            if (!status) return;
            const serverDev = status.dev_mode === true;
            // تغيّرت الحالة عمّا بدأنا به → إعادة تحميل لتطبيق نظيف
            if (serverDev !== DEV_MODE) {
                window.location.reload();
            }
        }, 5000);  // كل 5 ثوانٍ
    }

    // ============================================================
    //  Violation Handler
    // ============================================================
    let violationDebounce = 0;
    function triggerViolation(reason) {
        if (DEV_MODE) return;  //  وضع التطوير — لا عقوبات
        const now = Date.now();
        if (now - violationDebounce < 3000) return;
        violationDebounce = now;

        violations++;
        try {
            localStorage.setItem(STORAGE_KEY, violations);
        } catch (e) {}

        reportToServer(reason);

        if (violations >= MAX_VIOLATIONS) {
            executeBan(reason);
        } else {
            const remaining = MAX_VIOLATIONS - violations;
            showWarning('⚠️ تحذير: تم رصد محاولة وصول غير مصرح به. تتبقى ' + remaining + ' محاولات قبل الحظر.');
        }
    }

    function reportToServer(reason) {
        try {
            const apiUrl = getApiUrl();
            const token = getStoredToken();
            if (!apiUrl || !token) return;

            const data = new FormData();
            data.append('reason', reason);
            data.append('token', token);

            if (navigator.sendBeacon) {
                navigator.sendBeacon(apiUrl + '/auth/anticheat-report', data);
            } else {
                fetch(apiUrl + '/auth/anticheat-report', {
                    method: 'POST',
                    body: data,
                    keepalive: true,
                }).catch(function() {});
            }
        } catch (e) {}
    }

    function getApiUrl() {
        if (typeof API_URL !== 'undefined' && API_URL) return API_URL;
        if (typeof window.API_URL !== 'undefined' && window.API_URL) return window.API_URL;
        if (typeof CONFIG !== 'undefined' && CONFIG.API_URL) return CONFIG.API_URL;
        return '';
    }

    function getStoredToken() {
        try {
            return sessionStorage.getItem('token') || localStorage.getItem('token') || '';
        } catch (e) {
            return '';
        }
    }

    function showWarning(message) {
        // بانر تحذيري أنيق — لا يعتمد على أي مكتبة، لا alert
        try {
            let banner = document.getElementById('ac-warning-banner');
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'ac-warning-banner';
                banner.style.cssText = [
                    'position:fixed', 'top:20px', 'left:50%', 'transform:translateX(-50%) translateY(-120%)',
                    'background:linear-gradient(135deg,#d32f2f,#b71c1c)', 'color:#fff',
                    'padding:16px 24px', 'border-radius:12px', 'font-family:Tajawal,sans-serif',
                    'font-size:15px', 'font-weight:600', 'z-index:999999', 'direction:rtl',
                    'box-shadow:0 8px 30px rgba(0,0,0,0.4)', 'max-width:90%', 'text-align:center',
                    'transition:transform 0.4s cubic-bezier(0.18,0.89,0.32,1.28)',
                    'display:flex', 'align-items:center', 'gap:10px'
                ].join(';');
                banner.innerHTML = '<i class="fa-solid fa-shield-halved"></i><span id="ac-warning-text"></span>';
                document.body.appendChild(banner);
            }
            const txt = banner.querySelector('#ac-warning-text');
            if (txt) txt.textContent = message;
            // نُظهر بانزلاق ناعم
            requestAnimationFrame(() => {
                banner.style.transform = 'translateX(-50%) translateY(0)';
            });
            clearTimeout(banner._hideTimer);
            banner._hideTimer = setTimeout(() => {
                banner.style.transform = 'translateX(-50%) translateY(-120%)';
            }, 4000);
        } catch (e) {}
    }

    async function executeBan(reason) {
        if (DEV_MODE && !String(reason).startsWith('server_confirmed')) return;  //  تطوير
        try {
            localStorage.setItem(BAN_KEY, '1');
        } catch (e) {}

        const token = getStoredToken();
        const apiUrl = getApiUrl();

        if (token && apiUrl) {
            try {
                const fd = new FormData();
                fd.append('token', token);
                fd.append('reason', reason);
                await fetch(apiUrl + '/auth/self-ban', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token },
                    body: fd,
                    keepalive: true,
                });
            } catch (err) {}
        }

        if (typeof socket !== 'undefined' && socket && socket.connected) {
            try {
                socket.emit('severe_security_breach', { reason: reason });
            } catch (err) {}
        }

        try {
            sessionStorage.setItem('banReason', 'تم تقييد حسابك بسبب محاولات وصول غير مصرّح بها لأدوات المطور.');
            localStorage.removeItem('token');
            localStorage.removeItem('userData');
        } catch (e) {}

        // شاشة انتقالية بسيطة ثم توجيه لصفحة الحظر اللائقة
        document.body.innerHTML =
            '<div style="height:100vh;display:flex;flex-direction:column;justify-content:center;align-items:center;background:#0d0d1a;color:#ddd;text-align:center;direction:rtl;font-family:Tajawal,sans-serif;">' +
                '<div style="font-size:3rem;color:#f44336;">🚫</div>' +
                '<p style="font-size:1.1rem;margin-top:16px;">جارٍ تحويلك...</p>' +
            '</div>';

        setTimeout(function() {
            const path = window.location.pathname;
            const isInSubfolder = path.includes('/games/');
            window.location.replace(isInSubfolder ? '../banned.html' : 'banned.html');
        }, 800);
    }

    // ============================================================
    //  Start: نسأل السيرفر أولاً ثم نبدأ المراقبة
    // ============================================================
    initialize();

})();
