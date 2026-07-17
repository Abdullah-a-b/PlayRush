// ============================================================
// settings.js — نظام الإعدادات المشترك (الأفاتار، الأمان، الصوت)
// يُستخدم في: categories.js و lobby.js
// المتطلبات: utils.js يجب تحميله أولاً
// ============================================================


// ============================================================
//  مودال اختيار الأفاتار
// ============================================================

/** قائمة الصور الجاهزة المتاحة للاختيار */
const ONLINE_AVATARS = Array.from({ length: 60 }, (_, i) => `../assets/avatars/avatar_${i + 1}.svg`);

//  الأفاتارات التي تُشترى من المتجر (16-60). الأفاتارات 1-15 مجانية.
const PURCHASABLE_AVATARS = {};
for (let n = 16; n <= 60; n++) {
  PURCHASABLE_AVATARS[`avatar_${n}.svg`] = `avatar_${n}`;
}
window.OWNED_AVATAR_FILES = [];

function _isAvatarLocked(file) {
  return PURCHASABLE_AVATARS[file] && !(window.OWNED_AVATAR_FILES || []).includes(file);
}

let _lastAvatarGridOpts = null;
let _avatarListenerBound = false;
let _skipNextOwnedRequest = false;

function _requestOwnedAvatars() {
  if (typeof socket === 'undefined' || !socket) { setTimeout(_requestOwnedAvatars, 400); return; }
  const t = (typeof getToken === 'function') ? getToken() : (localStorage.getItem('token') || sessionStorage.getItem('token'));
  socket.emit('get_owned_avatars', { token: t });
  if (!_avatarListenerBound) {
    _avatarListenerBound = true;
    socket.on('owned_avatars_data', (data) => {
      if (data && Array.isArray(data.files)) {
        window.OWNED_AVATAR_FILES = data.files;
        if (_lastAvatarGridOpts && _lastAvatarGridOpts.wrapper && _lastAvatarGridOpts.wrapper.offsetParent !== null) {
          _skipNextOwnedRequest = true;  // إعادة الرسم دون طلب جديد (منع حلقة)
          renderAvatarGrid(_lastAvatarGridOpts);
        }
      }
    });
    // عند شراء أفاتار → نحدّث القائمة فوراً (بلا تحديث صفحة)
    socket.on('purchase_result', (data) => {
      if (data && data.ok && data.category === 'avatar') {
        const t = (typeof getToken === 'function') ? getToken() : (localStorage.getItem('token') || sessionStorage.getItem('token'));
        setTimeout(() => socket.emit('get_owned_avatars', { token: t }), 200);
      }
    });
  }
}
_requestOwnedAvatars();

/**
 * يرسم شبكة الصور داخل مودال الاختيار مع Lazy Loading.
 */
function renderAvatarGrid({ wrapper, confirmBtn, onSelect }) {
    _lastAvatarGridOpts = { wrapper, confirmBtn, onSelect };
    // نحدّث قائمة المملوكة في كل فتح (لتظهر المشتراة حديثاً) — إلا لو الاستدعاء من المستمع
    if (!_skipNextOwnedRequest && typeof socket !== 'undefined' && socket) {
      const t = (typeof getToken === 'function') ? getToken() : (localStorage.getItem('token') || sessionStorage.getItem('token'));
      socket.emit('get_owned_avatars', { token: t });
    }
    _skipNextOwnedRequest = false;
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
        const file = url.split('/').pop();
        const locked = _isAvatarLocked(file);
        const cell = document.createElement('div');
        cell.style.position = 'relative';
        cell.style.display = 'inline-block';

        const img = document.createElement('img');
        img.src          = PLACEHOLDER;
        img.dataset.src  = url;
        img.className    = 'avatar-option';
        Object.assign(img.style, {
            width: '70px', height: '70px', borderRadius: '50%',
            cursor: locked ? 'not-allowed' : 'pointer', objectFit: 'cover',
            border: '2px solid transparent', transition: 'all 0.2s ease-in-out',
            background: 'rgba(255,255,255,0.05)',
            filter: locked ? 'grayscale(0.8) brightness(0.5)' : 'none',
        });

        // تمييز الصورة المحددة حالياً (غير المقفولة فقط)
        if (!locked && file === currentFile && currentFile) {
            applyAvatarSelectedStyle(img);
            confirmBtn.style.display = 'inline-block';
            onSelect(url);
        }

        if (locked) {
            const lock = document.createElement('span');
            lock.textContent = '🔒';
            Object.assign(lock.style, {
                position: 'absolute', top: '50%', left: '50%',
                transform: 'translate(-50%,-50%)', fontSize: '22px', pointerEvents: 'none',
            });
            cell.appendChild(img);
            cell.appendChild(lock);
            img.addEventListener('click', () => {
                if (typeof showToast === 'function') showToast('🔒 هذا الأفاتار يُشترى من المتجر', 'info');
            });
        } else {
            img.addEventListener('click', () => {
                wrapper.querySelectorAll('.avatar-option').forEach(el => clearAvatarStyle(el));
                applyAvatarSelectedStyle(img);
                confirmBtn.style.display = 'inline-block';
                onSelect(img.dataset.src);
            });
            cell.appendChild(img);
        }

        wrapper.appendChild(cell);
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
//  نظام OTP (أمان الحساب)
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
//  حفظ الملف الشخصي
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

    // ✏️💎 تغيير الاسم يمر عبر نظام الجواهر (أول مرة مجاناً ثم 25💎)
    const currentName = sessionStorage.getItem('playerName') || '';
    if (newName !== currentName && currentName) {
        try {
            const nfd = new FormData();
            nfd.append('new_name', newName);
            const nres = await fetch(`${API_URL}/auth/settings/change-name`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: nfd,
            });
            const nd = await nres.json();
            if (!nd.ok) return showToast(nd.error || 'تعذّر تغيير الاسم', 'error');
            sessionStorage.setItem('playerName', nd.new_name);
            showToast(nd.msg, 'success');
        } catch (e) {
            return showToast('خطأ بالاتصال أثناء تغيير الاسم', 'error');
        }
    }

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
//  إعدادات الصوت
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

    // مساعد: هل نحن الآن في مزامنة DOM من sound.js؟ (نتجنب الحلقة)
    const _isSyncing = () => window.PRSound?.isSyncingSliders?.() === true;

    if (musicSlider) {
        const saved = localStorage.getItem('musicSlider');
        if (saved) musicSlider.value = saved;
        // إذا كان الصوت مكتوماً → أظهر 0 في السلايدر
        if (window.PRSound?.isMuted()) musicSlider.value = '0';
        updateVolumeUI(musicSlider, musicValue, musicIcon, '#facc15');
        musicSlider.addEventListener('input', () => {
            updateVolumeUI(musicSlider, musicValue, musicIcon, '#facc15');
            if (_isSyncing()) return;
            const mv = parseInt(musicSlider.value);
            const sv = parseInt(sfxSlider?.value ?? '0');
            if (mv > 0 && window.PRSound?.isMuted()) {
                // رُفع الموسيقى فوق 0 → ارفع الكتم
                window.PRSound.setMuted(false, true);
            } else if (mv === 0 && sv === 0 && !window.PRSound?.isMuted()) {
                // كلا السلايدرين وصلا 0 → شغّل الكتم
                window.PRSound.setMuted(true, true);
            }
        });
    }

    if (sfxSlider) {
        const saved = localStorage.getItem('sfxSlider');
        if (saved) sfxSlider.value = saved;
        // إذا كان الصوت مكتوماً → أظهر 0 في السلايدر
        if (window.PRSound?.isMuted()) sfxSlider.value = '0';
        updateVolumeUI(sfxSlider, sfxValue, sfxIcon, '#00d2ff');
        sfxSlider.addEventListener('input', () => {
            updateVolumeUI(sfxSlider, sfxValue, sfxIcon, '#00d2ff');
            if (_isSyncing()) return;
            const sv = parseInt(sfxSlider.value);
            const mv = parseInt(musicSlider?.value ?? '0');
            if (sv > 0 && window.PRSound?.isMuted()) {
                // رُفع SFX فوق 0 → ارفع الكتم
                window.PRSound.setMuted(false, true);
            } else if (sv === 0 && mv === 0 && !window.PRSound?.isMuted()) {
                // كلا السلايدرين وصلا 0 → شغّل الكتم
                window.PRSound.setMuted(true, true);
            }
        });
    }
}


// ============================================================
// ✏️ تغيير اسم اللاعب (أول مرة مجاناً ثم 25💎)
// ============================================================
window.changePlayerName = async function () {
    const token = sessionStorage.getItem('token');
    const current = sessionStorage.getItem('playerName') || '';
    const input = prompt('الاسم الجديد (أول تغيير مجاني، بعدها 25💎):', current);
    if (!input || input.trim() === current) return;
    try {
        const fd = new FormData();
        fd.append('new_name', input.trim());
        const res = await fetch(`${API_URL}/auth/settings/change-name`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: fd,
        });
        const d = await res.json();
        if (d.ok) {
            sessionStorage.setItem('playerName', d.new_name);
            if (typeof showToast === 'function') showToast(d.msg);
            setTimeout(() => location.reload(), 900);
        } else {
            alert(d.error || 'تعذّر تغيير الاسم');
        }
    } catch (e) { alert('خطأ بالاتصال'); }
};
