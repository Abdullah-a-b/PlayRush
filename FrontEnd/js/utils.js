// ============================================================
// utils.js — دوال مشتركة بين جميع الصفحات
// يجب تحميل هذا الملف قبل أي ملف JS آخر (بعد config.js)
// ============================================================


// ============================================================
// 🌐 إعداد الاتصال بالسيرفر
// ============================================================

/** رابط الـ API حسب البيئة (محلي أو إنتاج) */
const isLocal = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost';
const API_URL  = isLocal ? CONFIG.API_URL : 'https://api.your-real-domain.com';


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
    huroof: { title: 'حروف',        color: '#facc15', icon: '🔠' },
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
 * @param {string} path - المسار المخزّن في قاعدة البيانات
 * @param {string} [prefix='../'] - البادئة المناسبة لمجلد الصفحة الحالية
 */
function getCorrectAvatarUrl(path) {
    // إذا لم يكن هناك مسار، أو كان المسار به خلل، نرجع الصورة الافتراضية الأولى
    if (!path || path === 'undefined' || path === 'null' || path === 'custom' || path.trim() === '') {
        return `assets/avatars/avatar_1.svg`;
    }
    // إذا كان رابط خارجي أو Base64
    if (path.startsWith('http') || path.startsWith('data:')) return path;
    // إذا كان ملف مرفوع على السيرفر
    if (path.startsWith('/uploads')) return `${API_URL}${path}`;

    // استخراج اسم الملف فقط لضمان المسار الصحيح دائماً (بدون ../)
    const fileName = path.split('/').pop();
    return `assets/avatars/${fileName}`;
}

/**
 * نسخة مبسطة تُستخدم في اللوبي وصفحات اللعبة (مجلد واحد أعمق).
 * تُرجع رابط Dicebear كاحتياط إذا لم تجد صورة.
 */
function fixLobbyAvatar(avatarValue, fallbackName) {
    if (!avatarValue || avatarValue.trim() === '') {
        return `https://api.dicebear.com/7.x/bottts/svg?seed=${fallbackName || 'Player'}`;
    }
    if (avatarValue.startsWith('http') || avatarValue.startsWith('data:')) return avatarValue;

    let name = avatarValue.split('/').pop();
    if (!name.includes('.')) name += '.svg';
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
function showConfirm(title, message, onConfirm) {
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
    newNo.addEventListener('click',  () => { modal.style.display = 'none'; });
}


// ============================================================
// 💬 الدردشة العامة
// ============================================================

/**
 * يضيف رسالة إلى صندوق الدردشة العامة.
 * يحذف أقدم رسالة تلقائياً إذا تجاوز العدد 50.
 */
function addGlobalChatMessage(sender, text, isSystem = false) {
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
        const textSpan = document.createElement('span');
        textSpan.style.color = '#ddd';
        textSpan.textContent = sanitizeText(text);
        msgDiv.appendChild(userSpan);
        msgDiv.appendChild(document.createTextNode(' '));
        msgDiv.appendChild(textSpan);
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