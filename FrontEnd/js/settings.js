// ============================================================
// settings.js — نظام الإعدادات المشترك (الأفاتار، الأمان، الصوت)
// يُستخدم في: categories.js و lobby.js
// المتطلبات: utils.js يجب تحميله أولاً
// ============================================================


// ============================================================
// 🖼️ مودال اختيار الأفاتار
// ============================================================

/** قائمة الصور الجاهزة المتاحة للاختيار */
const ONLINE_AVATARS = Array.from({ length: 60 }, (_, i) => `../assets/avatars/avatar_${i + 1}.svg`);

/**
 * يرسم شبكة الصور داخل مودال الاختيار مع Lazy Loading.
 * @param {object} opts
 * @param {HTMLElement} opts.wrapper    - حاوية الصور
 * @param {HTMLElement} opts.confirmBtn - زر التأكيد
 * @param {Function}   opts.onSelect   - تُستدعى بمسار الصورة عند الاختيار
 */
function renderAvatarGrid({ wrapper, confirmBtn, onSelect }) {
    const currentSrc = document.getElementById('settingsAvatarPreview')?.src || '';
    const currentFile = currentSrc.split('/').pop();

    wrapper.innerHTML = '';

    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                obs.unobserve(img);
            }
        });
    }, { root: wrapper, rootMargin: '50px' });

    const PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 70 70'%3E%3Crect width='70' height='70' fill='%2327272a' rx='35'/%3E%3C/svg%3E";

    ONLINE_AVATARS.forEach(url => {
        const img = document.createElement('img');
        img.src          = PLACEHOLDER;
        img.dataset.src  = url;
        img.className    = 'avatar-option';
        Object.assign(img.style, {
            width: '70px', height: '70px', borderRadius: '50%',
            cursor: 'pointer', objectFit: 'cover',
            border: '2px solid transparent', transition: 'all 0.2s ease-in-out',
            background: 'rgba(255,255,255,0.05)',
        });

        // تمييز الصورة المحددة حالياً
        if (url.split('/').pop() === currentFile && currentFile) {
            applyAvatarSelectedStyle(img);
            confirmBtn.style.display = 'inline-block';
            onSelect(url);
        }

        img.addEventListener('click', () => {
            wrapper.querySelectorAll('.avatar-option').forEach(el => clearAvatarStyle(el));
            applyAvatarSelectedStyle(img);
            confirmBtn.style.display = 'inline-block';
            onSelect(img.dataset.src);
        });

        wrapper.appendChild(img);
        observer.observe(img);
    });
}

function applyAvatarSelectedStyle(img) {
    img.style.border     = '3px solid #00ff88';
    img.style.transform  = 'scale(1.1)';
    img.style.boxShadow  = '0 0 15px rgba(0,255,136,0.4)';
}

function clearAvatarStyle(img) {
    img.style.border     = '2px solid transparent';
    img.style.transform  = 'scale(1)';
    img.style.boxShadow  = 'none';
}


// ============================================================
// 🔐 نظام OTP (أمان الحساب)
// ============================================================

/**
 * يُشغّل عداد تنازلي على الزر ويوقفه عند الوصول للصفر.
 * @param {HTMLElement} btn          - الزر المراد تعطيله مؤقتاً
 * @param {string}      originalText - النص الأصلي للزر
 * @param {number}      [timeLeft=60]
 */
function startCooldown(btn, originalText, timeLeft = 60) {
    if (btn.dataset.timerId) clearInterval(btn.dataset.timerId);
    btn.disabled = true;
    btn.style.opacity = '0.5';

    const id = setInterval(() => {
        btn.textContent = `إعادة الإرسال (${timeLeft} ثانية)`;
        timeLeft--;
        if (timeLeft < 0) resetSecurityBtn(btn, originalText);
    }, 1000);

    btn.dataset.timerId = id;
}

/**
 * يُعيد الزر لحالته الطبيعية ويُلغي أي عداد نشط.
 */
function resetSecurityBtn(btn, originalText) {
    if (btn.dataset.timerId) {
        clearInterval(btn.dataset.timerId);
        delete btn.dataset.timerId;
    }
    btn.disabled      = false;
    btn.textContent   = originalText;
    btn.style.opacity = '1';
}

/**
 * يُطبّق تلقائياً عداد الانتظار على أزرار OTP
 * إذا كان الوقت المنقضي منذ آخر إرسال أقل من 60 ثانية.
 * @param {HTMLElement} emailBtn
 * @param {HTMLElement} passBtn
 */
function checkAndApplyCooldowns(emailBtn, passBtn) {
    const lastOtp = localStorage.getItem('lastOtpTime');
    if (!lastOtp) return;

    const passed    = Math.floor((Date.now() - parseInt(lastOtp)) / 1000);
    const remaining = 60 - passed;
    if (remaining <= 0) return;

    if (emailBtn && !emailBtn.dataset.timerId) startCooldown(emailBtn, 'إرسال رمز التحقق', remaining);
    if (passBtn  && !passBtn.dataset.timerId)  startCooldown(passBtn,  'إرسال رمز التحقق', remaining);
}

/**
 * يُرسل طلب OTP للسيرفر ويُشغّل عداد الانتظار.
 * @param {HTMLElement} btn
 * @param {HTMLElement} otpFlowEl - العنصر الذي يظهر بعد الإرسال
 * @param {string}      token
 */
async function requestOtp(btn, otpFlowEl, token) {
    btn.disabled    = true;
    btn.textContent = 'جاري الإرسال...';

    const fd = new FormData();
    fd.append('token', token);

    try {
        const res = await fetch(`${API_URL}/auth/settings/request-otp`, { method: 'POST', body: fd });
        if (res.ok) {
            showToast('تم إرسال الرمز', 'success');
            localStorage.setItem('lastOtpTime', Date.now().toString());
            startCooldown(btn, 'إرسال رمز التحقق', 60);
            if (otpFlowEl) otpFlowEl.style.display = 'block';
        } else {
            showToast('حدث خطأ', 'error');
            resetSecurityBtn(btn, 'إرسال رمز التحقق');
        }
    } catch {
        showToast('خطأ في الاتصال', 'error');
        resetSecurityBtn(btn, 'إرسال رمز التحقق');
    }
}

/**
 * يُرسل طلب تحديث الإيميل أو كلمة المرور بعد التحقق من OTP.
 * @param {'email'|'password'} action
 * @param {string} otp
 * @param {string} newValue
 * @param {string} token
 * @param {Function} onSuccess - دالة تُنفَّذ عند النجاح
 */
async function confirmSecurityChange(action, otp, newValue, token, onSuccess) {
    if (!otp || !newValue) return showToast('يرجى تعبئة الحقول', 'error');

    const fd = new FormData();
    fd.append('token',     token);
    fd.append('otp',       otp);
    fd.append('action',    action);
    fd.append('new_value', newValue);

    try {
        const res  = await fetch(`${API_URL}/auth/settings/update-security`, { method: 'POST', body: fd });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            onSuccess?.();
        } else {
            showToast(data.detail || 'حدث خطأ', 'error');
        }
    } catch {
        showToast('خطأ في الاتصال', 'error');
    }
}


// ============================================================
// 💾 حفظ الملف الشخصي
// ============================================================

/**
 * يُرسل بيانات الملف الشخصي المحدثة (اسم + صورة) للسيرفر.
 * @param {object} opts
 * @param {string}   opts.token
 * @param {string}   opts.newName
 * @param {File|null} opts.avatarFile  - ملف الصورة المرفوع (أو null)
 * @param {string}   opts.avatarUrl   - مسار الصورة الجاهزة (إذا لم يكن هناك ملف)
 * @param {string}   opts.country
 * @param {Function} opts.onSuccess   - تُستدعى بـ (data) عند نجاح الحفظ
 */
async function saveProfile({ token, newName, avatarFile, avatarUrl, country, onSuccess }) {
    if (newName.length < 3) return showToast('الاسم يجب أن يكون 3 أحرف على الأقل', 'error');

    const fd = new FormData();
    fd.append('token',       token);
    fd.append('player_name', newName);
    fd.append('country',     country);

    if (avatarFile) {
        fd.append('avatar_file', avatarFile);
    } else {
        fd.append('avatar_url', avatarUrl);
    }

    try {
        const res  = await fetch(`${API_URL}/auth/setup-profile`, { method: 'POST', body: fd });
        const data = await res.json();

        if (res.ok) {
            onSuccess?.(data);
        } else {
            // معالجة ذكية لرسالة الخطأ (نص / مصفوفة FastAPI / كائن)
            let msg = 'حدث خطأ غير معروف';
            if (typeof data.detail === 'string') {
                msg = data.detail;
            } else if (Array.isArray(data.detail)) {
                msg = data.detail.map(e => `${e.loc[1]}: ${e.msg}`).join(' | ');
            } else if (data.detail) {
                msg = JSON.stringify(data.detail);
            }
            showToast(`❌ فشل الحفظ: ${msg}`, 'error');
        }
    } catch (err) {
        console.error('saveProfile error:', err);
        showToast('❌ فشل الاتصال بالسيرفر', 'error');
    }
}


// ============================================================
// 🔊 إعدادات الصوت
// ============================================================

/**
 * يُحدّث أيقونة الصوت والنص ويحفظ القيمة في localStorage.
 * @param {HTMLInputElement} slider
 * @param {HTMLElement}      valueSpan
 * @param {HTMLElement}      icon
 * @param {string}           activeColor - لون الأيقونة عند التشغيل
 */
function updateVolumeUI(slider, valueSpan, icon, activeColor) {
    const val = parseInt(slider.value);
    valueSpan.textContent = `${val}%`;

    if (val === 0) {
        icon.className    = 'fa-solid fa-volume-xmark';
        icon.style.color  = '#555';
    } else if (val < 50) {
        icon.className    = 'fa-solid fa-volume-low';
        icon.style.color  = activeColor;
    } else {
        icon.className    = 'fa-solid fa-volume-high';
        icon.style.color  = activeColor;
    }

    localStorage.setItem(slider.id, val);
}

/**
 * يُهيئ أشرطة التحكم في الصوت ويسترجع القيم المحفوظة.
 */
function initVolumeControls() {
    const musicSlider = document.getElementById('musicSlider');
    const musicValue  = document.getElementById('musicValue');
    const musicIcon   = document.getElementById('musicIcon');
    const sfxSlider   = document.getElementById('sfxSlider');
    const sfxValue    = document.getElementById('sfxValue');
    const sfxIcon     = document.getElementById('sfxIcon');

    if (musicSlider) {
        const saved = localStorage.getItem('musicSlider');
        if (saved) musicSlider.value = saved;
        updateVolumeUI(musicSlider, musicValue, musicIcon, '#facc15');
        musicSlider.addEventListener('input', () => updateVolumeUI(musicSlider, musicValue, musicIcon, '#facc15'));
    }

    if (sfxSlider) {
        const saved = localStorage.getItem('sfxSlider');
        if (saved) sfxSlider.value = saved;
        updateVolumeUI(sfxSlider, sfxValue, sfxIcon, '#00d2ff');
        sfxSlider.addEventListener('input', () => updateVolumeUI(sfxSlider, sfxValue, sfxIcon, '#00d2ff'));
    }
}
