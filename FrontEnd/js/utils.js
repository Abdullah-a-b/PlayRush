// ============================================================
// utils.js — دوال مشتركة بين جميع الصفحات
// يجب تحميل هذا الملف قبل أي ملف JS آخر (بعد config.js)
// ============================================================


// ============================================================
// 🌐 إعداد الاتصال بالسيرفر
// ============================================================

/** رابط الـ API حسب البيئة (محلي / شبكة محلية / إنتاج) */
const _h = window.location.hostname;
const isLocal = _h === '127.0.0.1' || _h === 'localhost';
// عنوان شبكة محلية (هاتف عبر WiFi): 192.168.x.x أو 10.x.x.x أو 172.16-31.x.x
const isLAN = /^192\.168\.\d+\.\d+$/.test(_h)
           || /^10\.\d+\.\d+\.\d+$/.test(_h)
           || /^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$/.test(_h);
// محلي أو شبكة محلية → نستخدم CONFIG (نفس العنوان+المنفذ). غير ذلك (دومين عام) → الإنتاج.
const API_URL = (isLocal || isLAN) ? CONFIG.API_URL : 'https://api.your-real-domain.com';


// ============================================================
// 🗺️ قاموس أسماء الدول بالعربية
// ============================================================

const COUNTRY_NAMES = {
    SA: 'السعودية', EG: 'مصر',    IQ: 'العراق',     YE: 'اليمن',
    SY: 'سوريا',    MA: 'المغرب', DZ: 'الجزائر',    SD: 'السودان',
    JO: 'الأردن',   AE: 'الإمارات', LB: 'لبنان',   LY: 'ليبيا',
    PS: 'فلسطين',   OM: 'عمان',   KW: 'الكويت',     TN: 'تونس',
    QA: 'قطر',      BH: 'البحرين', MR: 'موريتانيا', SO: 'الصومال',
    DJ: 'جيبوتي',  TR: 'تركيا',   GL: 'عالمي',
};

/** أسماء ألعاب المنصة */
const GAME_THEMES = {
    huroof: { title: 'خلية الحروف',   color: '#facc15', icon: '🔠' },
    bank:   { title: 'بنك',         color: '#00ff88', icon: '🏦' },
    career: { title: 'مسيرة لاعب', color: '#00d2ff', icon: '⚽' },
    whoami: { title: 'من أنا؟',     color: '#f43f5e', icon: '🕵️‍♂️' },
    whatdo: { title: 'ماذا تعرف؟',  color: '#a855f7', icon: '🧠' },
};


// ============================================================
// 🖼️ معالجة مسارات الصور
// ============================================================

/**
 * يُعيد الرابط الصحيح لصورة اللاعب بغض النظر عن مصدرها.
 * 🛡️ مُحكم ضد XSS عبر avatar URL خبيث (javascript:, data:image/svg+xml, إلخ).
 * @param {string} path - المسار المخزّن في قاعدة البيانات
 */
function getCorrectAvatarUrl(path) {
    // إذا لم يكن هناك مسار، أو كان المسار به خلل، نرجع الصورة الافتراضية الأولى
    if (!path || path === 'undefined' || path === 'null' || path === 'custom' || String(path).trim() === '') {
        return `assets/avatars/avatar_1.svg`;
    }

    const p = String(path).trim();
    const lower = p.toLowerCase();

    // 🛡️ نمنع كل البروتوكولات الخطيرة (javascript:, data:, vbscript:, file:, إلخ)
    // ونسمح فقط بـ http/https + المسارات النسبية
    const dangerousProtocols = ['javascript:', 'vbscript:', 'data:', 'file:', 'ftp:', 'about:'];
    for (const proto of dangerousProtocols) {
        if (lower.startsWith(proto)) {
            console.warn('[SECURITY] avatar URL blocked:', p);
            return `assets/avatars/avatar_1.svg`;
        }
    }

    // 🔧 روابط قديمة ثابتة (127.0.0.1/localhost) محفوظة قبل التحديث → نصلحها للعنوان الحالي
    const staleMatch = p.match(/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/.*)$/i);
    if (staleMatch) {
        const sp = staleMatch[3];
        if (sp.startsWith('/uploads')) return `${API_URL}${sp}`;
        const fn = sp.split('/').pop();
        if (/^[a-zA-Z0-9_-]+\.(svg|png|jpg|jpeg|webp)$/i.test(fn)) return `assets/avatars/${fn}`;
        return `assets/avatars/avatar_1.svg`;
    }

    // إذا كان رابط https/http آمن
    if (lower.startsWith('https://') || lower.startsWith('http://')) {
        return p;
    }

    // إذا كان ملف مرفوع على السيرفر
    if (p.startsWith('/uploads')) return `${API_URL}${p}`;

    // 🛡️ مسارات نسبية فقط — نأخذ اسم الملف فقط لمنع path traversal
    const fileName = p.split('/').pop();
    // نسمح فقط بأسماء ملفات شرعية (حروف/أرقام/_/-/. ثم svg/png/jpg/jpeg/webp)
    if (!/^[a-zA-Z0-9_-]+\.(svg|png|jpg|jpeg|webp)$/i.test(fileName)) {
        return `assets/avatars/avatar_1.svg`;
    }
    return `assets/avatars/${fileName}`;
}

/**
 * نسخة مبسطة تُستخدم في اللوبي وصفحات اللعبة (مجلد واحد أعمق).
 * تُرجع رابط Dicebear كاحتياط إذا لم تجد صورة.
 */
function fixLobbyAvatar(avatarValue, fallbackName) {
    if (!avatarValue || String(avatarValue).trim() === '') {
        return `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(fallbackName || 'Player')}`;
    }

    const v = String(avatarValue).trim();
    const lower = v.toLowerCase();

    // 🛡️ نمنع البروتوكولات الخطيرة
    const dangerousProtocols = ['javascript:', 'vbscript:', 'data:', 'file:', 'ftp:', 'about:'];
    for (const proto of dangerousProtocols) {
        if (lower.startsWith(proto)) {
            return `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(fallbackName || 'Player')}`;
        }
    }

    if (lower.startsWith('https://') || lower.startsWith('http://')) return v;

    let name = v.split('/').pop();
    if (!name.includes('.')) name += '.svg';
    // 🛡️ تحقق من اسم الملف
    if (!/^[a-zA-Z0-9_-]+\.(svg|png|jpg|jpeg|webp)$/i.test(name)) {
        return `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(fallbackName || 'Player')}`;
    }
    return `../assets/avatars/${name}`;
}


// ============================================================
// 🔒 الحماية من XSS
// ============================================================

/**
 * ينظّف النص من أكواد HTML الخطرة باستخدام DOMPurify.
 * إذا لم يكن DOMPurify محملاً بعد (تأخر defer)، يُعيد النص كـ plain text آمن.
 * @param {string} str - النص المراد تنظيفه
 * @returns {string} نص آمن خالٍ من XSS
 */
function sanitizeHTML(str) {
    if (str === null || str === undefined) return '';
    const s = String(str);
    if (typeof DOMPurify !== 'undefined' && DOMPurify.isSupported) {
        return DOMPurify.sanitize(s, { USE_PROFILES: { html: true } });
    }
    // احتياط: تحويل المحارف الخطرة إلى HTML entities
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;')
        .replace(/\//g, '&#x2F;');
}

/**
 * ينظّف النص ويُعيده كنص عادي فقط (بدون أي HTML) — للأسماء والقيم الحرجة.
 * @param {string} str
 * @returns {string}
 */
function sanitizeText(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.textContent;
}


// ============================================================
// 🔔 نظام التنبيهات (Toast)
// ============================================================

/**
 * يُظهر رسالة تنبيه مؤقتة في أسفل الشاشة.
 * @param {string} message - نص الرسالة
 * @param {'info'|'success'|'error'} [type='info'] - نوع التنبيه
 */
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const iconMap = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info' };
    const toast = document.createElement('div');
    toast.className = `toast ${sanitizeText(type)}`;
    // نبني الـ toast بـ DOM API لمنع XSS بدلاً من innerHTML
    const icon = document.createElement('i');
    icon.className = `fa-solid ${iconMap[type] || iconMap.info}`;
    const span = document.createElement('span');
    span.textContent = message; // النص الخام — لا نريد HTML في الـ toast
    toast.appendChild(icon);
    toast.appendChild(document.createTextNode(' '));
    toast.appendChild(span);
    container.appendChild(toast);

    setTimeout(() => {
        if (container.contains(toast)) container.removeChild(toast);
    }, 3000);
}


// ============================================================
// ✅ نافذة التأكيد المخصصة
// ============================================================

/**
 * يفتح نافذة تأكيد مخصصة بدلاً من confirm() الافتراضية.
 * @param {string} title   - عنوان النافذة
 * @param {string} message - نص السؤال
 * @param {Function} onConfirm - دالة تُنفَّذ عند الضغط على "نعم"
 */
function showConfirm(title, message, onConfirm, onCancel) {
    const modal = document.getElementById('customConfirm');
    document.getElementById('confirmTitle').textContent   = title;
    document.getElementById('confirmMessage').textContent = message;
    modal.style.display = 'flex';

    // استنساخ الأزرار لإزالة أي event listeners سابقة
    const yesBtn = document.getElementById('confirmYes');
    const noBtn  = document.getElementById('confirmNo');
    const newYes = yesBtn.cloneNode(true);
    const newNo  = noBtn.cloneNode(true);
    yesBtn.parentNode.replaceChild(newYes, yesBtn);
    noBtn.parentNode.replaceChild(newNo, noBtn);

    newYes.addEventListener('click', () => { modal.style.display = 'none'; onConfirm(); });
    newNo.addEventListener('click',  () => { modal.style.display = 'none'; if (typeof onCancel === 'function') onCancel(); });
}


// ============================================================
// 💬 الدردشة العامة
// ============================================================

/**
 * يضيف رسالة إلى صندوق الدردشة العامة.
 * يحذف أقدم رسالة تلقائياً إذا تجاوز العدد 50.
 */
function addGlobalChatMessage(sender, text, isSystem = false, senderId = null, emojiId = null) {
    const container = document.getElementById('globalChatMessages');
    if (!container) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg';

    if (isSystem) {
        msgDiv.style.borderRightColor = '#00ff88';
        const userSpan = document.createElement('span');
        userSpan.className = 'user';
        userSpan.style.color = '#00ff88';
        userSpan.textContent = `${sanitizeText(sender)}:`;
        const textSpan = document.createElement('span');
        textSpan.style.color = '#fff';
        textSpan.textContent = sanitizeText(text);
        msgDiv.appendChild(userSpan);
        msgDiv.appendChild(document.createTextNode(' '));
        msgDiv.appendChild(textSpan);
    } else {
        const userSpan = document.createElement('span');
        userSpan.className = 'user';
        userSpan.textContent = `${sanitizeText(sender)}:`;
        if (senderId && typeof openPlayerProfileById === 'function') {
            userSpan.style.cursor = 'pointer';
            userSpan.style.textDecoration = 'underline';
            userSpan.style.textDecorationStyle = 'dotted';
            userSpan.addEventListener('click', () => openPlayerProfileById(senderId));
        }
        msgDiv.appendChild(userSpan);
        msgDiv.appendChild(document.createTextNode(' '));

        // رسالة إيموجي → Lottie متحرك (مع إعادة محاولة لو المكتبة لم تجهز)
        if (emojiId) {
            const holder = document.createElement('span');
            holder.style.display = 'inline-block';
            holder.style.width = '38px';
            holder.style.height = '38px';
            holder.style.verticalAlign = 'middle';
            holder.style.fontSize = '26px';
            msgDiv.appendChild(holder);
            const inGames = window.location.pathname.includes('/games/');
            const path = `${inGames ? '../' : ''}assets/emojis/${emojiId}.json`;
            (function tryLoad(tries) {
                if (typeof window.lottie !== 'undefined' && window.lottie.loadAnimation) {
                    try {
                        const anim = window.lottie.loadAnimation({
                            container: holder, renderer: 'svg', loop: false, autoplay: true, path,
                        });
                        // تكرار ديناميكي خفيف: يعيد التشغيل بعد فترات عشوائية (لا يلفت النظر)
                        let _plays = 0;
                        anim.addEventListener('complete', function _onDone() {
                            _plays++;
                            if (_plays >= 6) return; // يتوقف بعد عدة مرات
                            // انتظار عشوائي ثم إعادة (إيقاع غير منتظم = طبيعي)
                            const wait = 2500 + Math.random() * 4000;
                            setTimeout(() => {
                                try { anim.goToAndPlay(0, true); } catch (_) {}
                            }, wait);
                        });
                    } catch (_) { holder.textContent = sanitizeText(text); }
                } else if (tries < 20) {
                    setTimeout(() => tryLoad(tries + 1), 250);
                } else {
                    holder.textContent = sanitizeText(text);
                }
            })(0);
        } else {
            const textSpan = document.createElement('span');
            textSpan.style.color = '#ddd';
            textSpan.textContent = sanitizeText(text);
            msgDiv.appendChild(textSpan);
        }
    }

    container.appendChild(msgDiv);
    if (container.children.length > 50) container.removeChild(container.firstElementChild);
    container.scrollTop = container.scrollHeight;
}


// ============================================================
// 📊 حساب المستوى والـ XP
// ============================================================

/**
 * يحسب المستوى الحالي ونسبة تقدم الـ XP بداخله.
 * الصعوبة تتضاعف: 2000 → 4000 → 8000 → ...
 * @param {number} totalXp - مجموع نقاط الخبرة
 * @returns {{ level: number, progress: number }} - المستوى ونسبة التقدم (0-100)
 */
function calcXpProgress(totalXp) {
    let required    = 2000;
    let accumulated = 0;
    let level       = 0;

    while (totalXp >= accumulated + required) {
        accumulated += required;
        required    *= 2;
        level++;
    }

    const progress = ((totalXp - accumulated) / required) * 100;
    return { level, progress };
}


// ============================================================
// 🏴 عرض علم الدولة
// ============================================================

/**
 * يُنشئ HTML لعلم الدولة داخل العنصر المُمرَّر.
 * @param {HTMLElement} el       - عنصر الاحتواء
 * @param {string}      country  - سلسلة الدولة المخزنة (مثل "ye Yemen")
 * @param {string}      [flagPrefix='../'] - مسار مجلد الأعلام
 */
function renderPlayerFlag(el, country, flagPrefix = '../') {
    if (!el || !country) return;

    const code       = sanitizeText(country.split(' ')[0].toUpperCase());
    const arabicName = sanitizeText(COUNTRY_NAMES[code] || code);

    // نبني العنصر بـ DOM API لتجنب injection في attributes
    const img = document.createElement('img');
    img.src   = `${flagPrefix}assets/flags/${code}.svg`;
    img.alt   = arabicName;
    img.title = arabicName;
    img.style.cssText = 'width:28px; height:auto; border-radius:4px; box-shadow:0 1px 3px rgba(0,0,0,0.2);';
    img.addEventListener('error', () => { img.style.display = 'none'; });

    el.innerHTML = '';
    el.appendChild(img);
    el.style.display = 'inline-block';
}


// ============================================================
// 🗑️ حذف الحساب
// ============================================================

/**
 * يطلب تأكيداً ثم يرسل طلب حذف الحساب للسيرفر.
 * يُستدعى من زر "حذف الحساب" في صفحات الإعدادات.
 */
function deleteAccount() {
    showConfirm(
        '⚠️ تحذير خطير',
        'هل أنت متأكد 100% أنك تريد حذف حسابك نهائياً؟ سيتم مسح اسمك، صورتك، ونقاطك بالكامل ولا يمكن التراجع!',
        async () => {
            const token = getToken();
            try {
                const res = await fetch(`${API_URL}/auth/delete-account`, {
                    method: 'DELETE',
                    headers: { Authorization: `Bearer ${token}` },
                });

                if (res.ok) {
                    showToast('تم حذف حسابك بنجاح، نتمنى أن نراك مجدداً!', 'success');
                    if (typeof closeSettings === 'function') closeSettings();
                    setTimeout(() => {
                        sessionStorage.clear();
                        localStorage.clear();
                        window.location.replace('./index.html');
                    }, 2000);
                } else {
                    const data = await res.json();
                    showToast(`❌ حدث خطأ: ${data.detail || 'لم نتمكن من الحذف'}`, 'error');
                }
            } catch (err) {
                console.error('deleteAccount error:', err);
                showToast('❌ حدث خطأ في الاتصال بالخادم.', 'error');
            }
        }
    );
}


// ============================================================
// 🚫 معالج الحظر الإجباري (force_logout)
// يُستدعى من السيرفر عند حظر اللاعب — يجب أن يعمل في كل صفحة فيها socket
// ============================================================

/**
 * يربط معالج 'force_logout' بأي socket — يجب استدعاؤه بعد إنشاء socket.
 * يعرض رسالة الحظر، يمسح الجلسة، ويعيد التوجيه لصفحة login.
 * @param {Socket} socketInstance - الـ socket المُنشأ
 */
function attachForceLogoutHandler(socketInstance) {
    if (!socketInstance) return;
    socketInstance.on('force_logout', (data) => {
        const message = (data && data.message) || 'تم تقييد حسابك.';
        try {
            sessionStorage.setItem('banReason', message);
            sessionStorage.removeItem('token');
            localStorage.removeItem('token');
        } catch (e) {}

        // صفحة حظر لائقة بدل رسالة خام
        const path = window.location.pathname;
        const isInSubfolder = path.includes('/games/');
        const banPage = isInSubfolder ? '../banned.html' : 'banned.html';

        try {
            document.body.innerHTML = `
                <div style="height:100vh; display:flex; flex-direction:column; justify-content:center; align-items:center; background:#0d0d1a; color:#ddd; text-align:center; direction:rtl; font-family:Tajawal, sans-serif;">
                    <div style="font-size:3rem; color:#f44336;">🚫</div>
                    <p style="font-size:1.1rem; margin-top:16px;">جارٍ تحويلك...</p>
                </div>`;
        } catch (e) {}

        setTimeout(() => { window.location.replace(banPage); }, 800);
    });
}