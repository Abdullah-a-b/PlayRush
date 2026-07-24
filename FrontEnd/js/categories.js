// ============================================================
// categories.js — صفحة الساحة الرئيسية (اختيار الألعاب)
// المتطلبات: config.js → utils.js → settings.js
// ============================================================


// ============================================================
//  استخراج التوكن من رابط Google OAuth وتنظيف الـ URL
// ============================================================
(function extractGoogleToken() {
    const params = new URLSearchParams(window.location.search);
    const t = params.get('token');
    if (t) {
        sessionStorage.setItem('token', t);
        window.history.replaceState({}, document.title, window.location.pathname);
    }
})();

// حماية المسار
const token = getToken();
if (!token) window.location.replace('login.html');

// الاتصال بالسوكيت (يحتاج API_URL من utils.js)
const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });

// بروفايل الإشعارات في categories: إحصائيات عامة فقط (لا لعبة محددة)
window.PROFILE_GAME_MODE = null;
// المتجر في categories: كل المساعدات + كل التجميليات
window.STORE_CONTEXT = 'categories';
//  ربط معالج الحظر الإجباري — يستجيب لرسائل force_logout من السيرفر
if (typeof attachForceLogoutHandler === 'function') attachForceLogoutHandler(socket);

// ============================================================
//  إعداد الإشعارات (مستوى أعلى — مستقل عن أي كود async قد يفشل)
// ============================================================
function renderNotifications(items, unread) {
    const list = document.getElementById('notificationsList');
    if (list) {
        if (!items || items.length === 0) {
            list.innerHTML = '<div style="color:#888;text-align:center;padding:20px;">لا توجد إشعارات</div>';
        } else {
            list.style.textAlign = 'right';
            list.style.color = '#ddd';
            list.innerHTML = items.map(n => {
                const clickable = n.sender_id && (n.type === 'friend_request' || n.type === 'friend_accepted');
                const cursor = clickable ? 'cursor:pointer;' : '';
                const hint = clickable ? '<i class="fa-solid fa-circle-user" style="color:#4a90e2;margin-right:6px;font-size:13px;"></i>' : '';
                return `
                <div class="notif-item" ${clickable ? `data-sender="${n.sender_id}"` : ''} style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.08);${cursor}
                            ${n.is_read ? '' : 'background:rgba(255,235,59,0.06);'}">
                    <i class="fa-solid fa-bell" style="color:#ff9800;margin-left:6px;"></i>
                    ${typeof sanitizeHTML === 'function' ? sanitizeHTML(n.message) : n.message}
                    ${hint}
                </div>`;
            }).join('');
            list.querySelectorAll('.notif-item[data-sender]').forEach(el => {
                el.addEventListener('click', () => {
                    const senderId = parseInt(el.dataset.sender);
                    if (senderId && typeof openPlayerProfileById === 'function') {
                        openPlayerProfileById(senderId);
                    }
                });
            });
        }
    }
    const badge = document.getElementById('notifBadge');
    if (badge) {
        badge.style.display = unread > 0 ? 'flex' : 'none';
        if (unread > 0) badge.textContent = unread > 9 ? '9+' : unread;
    }
}
socket.on('notifications_list', (data) => {
    renderNotifications(data.items, data.unread);
});
socket.on('new_notification', (notif) => {
    const badge = document.getElementById('notifBadge');
    if (badge) {
        const cur = parseInt(badge.textContent) || 0;
        badge.textContent = (cur + 1) > 9 ? '9+' : (cur + 1);
        badge.style.display = 'flex';
    }
    window.PRSound?.playNotif?.();
    if (notif?.message && typeof showGlobalToast === 'function') showGlobalToast('🔔 ' + notif.message);
    fetchNotifs();
});
let _lastNotifFetch = 0;
function fetchNotifs() {
    const now = Date.now();
    if (now - _lastNotifFetch < 3000) return;
    _lastNotifFetch = now;
    if (token && socket.connected) socket.emit('fetch_notifications', { token });
}
if (socket.connected) fetchNotifs();
socket.on('connect', fetchNotifs);

// عرض الأفاتار المحفوظ في الجلسة فوراً قبل انتهاء تحميل البيانات
const cachedAvatar = sessionStorage.getItem('playerAvatar');
if (cachedAvatar) {
    const el = document.getElementById('playerAvatar');
    if (el) el.src = getCorrectAvatarUrl(cachedAvatar);
}

// حالة الصفحة
let userDataCache   = null;
let customAvatarFile = null;


// ============================================================
//  بدء التشغيل
// ============================================================
window.addEventListener('DOMContentLoaded', async () => {

    // ----------------------------------------
    //  السوكيت: اللاعبين المتصلين والدردشة
    // ----------------------------------------
    //  نظام الحضور بالفروقات (presence.js) — بدل بث القائمة الكاملة
    initPresence(socket, (players) => {
        const countEl = document.getElementById('globalOnlineCount');
        if (countEl) countEl.textContent = players.length;

        const list = document.getElementById('globalPlayersList');
        if (!list) return;

        //  ترتيب: اللاعب الحالي أولاً ثم البقية كما هم
        // نستخدم نسخة جديدة بدل تعديل الأصلية (نفس مفهوم immutability)
        const myName = userDataCache?.player_name;
        const sorted = myName
            ? [...players].sort((a, b) => {
                if (a.name === myName) return -1;
                if (b.name === myName) return 1;
                return 0;
              })
            : players;

        list.innerHTML = '';
        //  سقف الرسم: العدّاد يعرض الكل، لكن القائمة ترسم أول 100 فقط —
        // آلاف عناصر DOM تجمّد المتصفح (خصوصاً الجوالات) عند 5000 متصل.
        const MAX_RENDER = 100;
        const hiddenCount = Math.max(0, sorted.length - MAX_RENDER);
        sorted.slice(0, MAX_RENDER).forEach(p => {
            let locationText = 'الساحة العامة';
            let statusColor  = '#00ff88';

            if (p.location && p.location !== 'global') {
                if (p.location.startsWith('playing_')) {
                    const game = p.location.split('_')[1];
                    const isFriendly = p.location.endsWith('_friendly');
                    if (isFriendly) {
                        locationText = `⚔️ معركة ودية (${GAME_THEMES[game]?.title || game}) ضد صديق`;
                    } else {
                        locationText = `⚔️ يخوض معركة (${GAME_THEMES[game]?.title || game})`;
                    }
                    statusColor  = '#f43f5e';
                } else if (p.location.startsWith('party_')) {
                    const game = p.location.split('_')[1];
                    locationText = `في وضع الجمعات 🎮 (${GAME_THEMES[game]?.title || game})`;
                    statusColor  = '#ff9800';
                } else if (p.location !== 'global') {
                    locationText = `لوبي ${GAME_THEMES[p.location]?.title || p.location}`;
                    statusColor  = '#facc15';
                }
            }

            const div = document.createElement('div');
            div.className = 'online-player-item';
            //  تمييز اللاعب الحالي بنفس CSS class الموجود في categories.css
            if (myName && p.name === myName) div.classList.add('is-me');

            //  نبني العناصر بـ DOM API بدل innerHTML لمنع XSS
            const img = document.createElement('img');
            img.src = getCorrectAvatarUrl(p.avatar);
            img.className = 'online-player-avatar';
            img.alt = 'Avatar';

            const infoDiv = document.createElement('div');
            infoDiv.className = 'online-player-info';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'online-player-name';
            nameSpan.textContent = p.name || '';

            const statusSpan = document.createElement('span');
            statusSpan.className = 'online-player-status';

            const dot = document.createElement('div');
            dot.className = 'status-dot';
            dot.style.backgroundColor = statusColor;

            const locSpan = document.createElement('span');
            locSpan.style.color = statusColor;
            locSpan.textContent = locationText;

            statusSpan.appendChild(dot);
            statusSpan.appendChild(document.createTextNode(' '));
            statusSpan.appendChild(locSpan);

            infoDiv.appendChild(nameSpan);
            infoDiv.appendChild(statusSpan);

            div.appendChild(img);
            div.appendChild(infoDiv);
            list.appendChild(div);
        });

        if (hiddenCount > 0) {
            const more = document.createElement('div');
            more.className = 'online-player-item';
            more.style.justifyContent = 'center';
            more.style.opacity = '0.7';
            more.textContent = `و ${hiddenCount} لاعب آخر متصل...`;
            list.appendChild(more);
        }
    });

    socket.on('chat_history', (history) => {
        const container = document.getElementById('globalChatMessages');
        if (container) container.innerHTML = '';
        history.forEach(msg => addGlobalChatMessage(msg.sender, msg.text, msg.isSystem, msg.sender_id, msg.emojiId));
    });

    socket.on('new_chat_message', (msg) => {
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            //  نبني العنصر بـ DOM API لمنع XSS تماماً
            const el = document.createElement('div');
            el.className = `chat-message ${msg.isSystem ? 'system' : ''}`;
            if (msg.id) el.dataset.msgId = msg.id;

            const senderSpan = document.createElement('span');
            senderSpan.className = 'sender';
            senderSpan.textContent = `${msg.sender || ''}:`;

            const textSpan = document.createElement('span');
            textSpan.className = 'text';
            textSpan.textContent = msg.text || '';

            el.appendChild(senderSpan);
            el.appendChild(document.createTextNode(' '));
            el.appendChild(textSpan);

            chatMessages.appendChild(el);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        addGlobalChatMessage(msg.sender, msg.text, msg.isSystem, msg.sender_id, msg.emojiId);
    });

    // تنبيه خطأ الدردشة (محتوى مرفوض/كتم)
    socket.on('chat_error', (data) => {
        if (typeof showToast === 'function') showToast(data.msg || 'تعذّر إرسال الرسالة', 'error');
    });

    function joinGlobalLobby() {
        if (userDataCache) {
            socket.emit('join_global_lobby', {
                token:  token,
                name:   userDataCache.player_name,
                avatar: userDataCache.avatar,
            });
        }
    }

    socket.on('connect', joinGlobalLobby);

    // ----------------------------------------
    //  جلب بيانات الحساب
    // ----------------------------------------
    try {
        const res= await fetch(`${API_URL}/auth/me`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (!res.ok) {
            // 401/403 = التوكن فعلاً غير صالح → نمسح الجلسة ونعيد لتسجيل الدخول.
            // أي شيء آخر (429 تجاوز حدّ، 5xx ازدحام، تعثّر لحظي) = عطل مؤقت،
            // فلا نمسح "تذكّرني" — وإلا خرج المستخدم من حسابه بلا سبب حقيقي.
            if (res.status === 401 || res.status === 403) {
                sessionStorage.removeItem('token');
                try { localStorage.removeItem('token'); } catch (e) {}
                return window.location.replace('login.html');
            }

            if (typeof showToast === 'function') {
                showToast('تعذّر تحميل بياناتك مؤقتاً. أعد تحميل الصفحة بعد قليل.', 'error');
            }
            return;
        }

        userDataCache = await res.json();

        // 📆 مكافأة تتابع الدخول اليومي (5→50🪙)
        if (userDataCache.login_streak_reward) {
            const r = userDataCache.login_streak_reward;
            setTimeout(() => {
                if (typeof showToast === 'function') showToast(r.msg || `📆 +${r.coins}🪙`);
            }, 1200);
        }

        // الاسم
        const nameEl = document.getElementById('playerName');
        if (nameEl) nameEl.textContent = userDataCache.player_name || 'لاعب مجهول';

        // العلم
        renderPlayerFlag(document.getElementById('playerFlag'), userDataCache.country);

        // ID
        const idEl = document.getElementById('playerIdDisplay');
        if (idEl) idEl.textContent = userDataCache.player_id || '#PR-00000';

        // الأفاتار
        const avatarUrl = getCorrectAvatarUrl(userDataCache.avatar);
        const avatarEl  = document.getElementById('playerAvatar');
        if (avatarEl) avatarEl.src = avatarUrl;

        // حفظ البيانات للصفحات الأخرى
        sessionStorage.setItem('playerName',   userDataCache.player_name);
        sessionStorage.setItem('playerAvatar', userDataCache.avatar);

        // العملات والجواهر
        const coinsEl = document.getElementById('coins');
        const gemsEl  = document.getElementById('gems');
        if (coinsEl) coinsEl.textContent = userDataCache.coins ?? 0;
        if (gemsEl)  gemsEl.textContent  = userDataCache.gems  ?? 0;

        // المستوى وشريط الـ XP
        const { level, progress } = calcXpProgress(userDataCache.xp || 0);
        const levelEl  = document.getElementById('playerLevel');
        const xpBarEl  = document.getElementById('xpFill');
        if (levelEl) levelEl.textContent    = userDataCache.level ?? level;
        if (xpBarEl) xpBarEl.style.width    = `${progress}%`;

        // تعبئة نموذج الإعدادات
        const editNameEl = document.getElementById('editPlayerName');
        if (editNameEl) editNameEl.value = userDataCache.player_name;

        const settingsPreview = document.getElementById('settingsAvatarPreview');
        if (settingsPreview) settingsPreview.src = avatarUrl;

        if (document.getElementById('currentEmailDisplay')) {
            document.getElementById('currentEmailDisplay').textContent = userDataCache.email;
        }

        // إظهار/إخفاء حقول Google
        const isGoogle = userDataCache.auth_provider === 'google';
        document.getElementById('googleAuthBadge').style.display = isGoogle ? 'block' : 'none';
        document.getElementById('localAuthFields').style.display = isGoogle ? 'none'  : 'block';

        if (socket.connected) joinGlobalLobby();

    } catch {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }

    // ----------------------------------------
    //  التنقل بين الأقسام (ألعاب، متجر، أصدقاء)
    // ----------------------------------------
    const navBtns   = document.querySelectorAll('.nav-btn');
    const sections  = document.querySelectorAll('.content-section');
    // 🎫 وصول مباشر لقسم (مثل زر الباس من اللوبي: categories.html#pass)
    const _hashSec = (location.hash || '').replace('#', '');
    if (_hashSec) {
        setTimeout(() => {
            const btn = document.querySelector(`.nav-btn[data-section="${_hashSec}"]`);
            if (btn) btn.click();
        }, 300);
    }

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            navBtns.forEach(b => b.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`${btn.dataset.section}-section`)?.classList.add('active');
        });
    });

    document.querySelectorAll('.game-card').forEach(card => {
        card.addEventListener('click', () => {
            const mode = card.getAttribute('data-game');
            if (mode) window.location.href = `lobby.html?game=${mode}`;
            else showToast('حدث خطأ، يرجى المحاولة لاحقاً.', 'error');
        });
    });

    // ----------------------------------------
    //  الإعدادات
    // ----------------------------------------
    const settingsModal      = document.getElementById('settingsModal');
    const globalSettingsBtn  = document.getElementById('globalSettingsBtn');
    const openProfileSettings = document.getElementById('openProfileSettings');
    const closeSettingsModal = document.getElementById('closeSettingsModal');

    function openSettings() {
        if (!settingsModal) return;
        if (userDataCache) {
            document.getElementById('editPlayerName').value = userDataCache.player_name;
            document.getElementById('settingsAvatarPreview').src = getCorrectAvatarUrl(userDataCache.avatar);
        }
        settingsModal.style.display = 'flex';
    }

    function closeSettings() {
        if (!settingsModal) return;
        settingsModal.style.display = 'none';
        resetSecurityViews();
        if (userDataCache) {
            document.getElementById('editPlayerName').value = userDataCache.player_name;
            document.getElementById('settingsAvatarPreview').src = getCorrectAvatarUrl(userDataCache.avatar);
        }
    }

    globalSettingsBtn?.addEventListener('click', openSettings);
    openProfileSettings?.addEventListener('click', openSettings);
    closeSettingsModal?.addEventListener('click', closeSettings);

    // تبويبات الإعدادات
    const settingTabs   = document.querySelectorAll('.setting-tab:not(.logout-tab)');
    const settingPanels = document.querySelectorAll('.setting-panel');

    settingTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            settingTabs.forEach(t => t.classList.remove('active'));
            settingPanels.forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab)?.classList.add('active');
            resetSecurityViews();
        });
    });

    document.getElementById('logoutSettingsBtn')?.addEventListener('click', () => {
        showConfirm('تسجيل الخروج', 'هل أنت متأكد أنك تريد الخروج؟', () => {
            sessionStorage.removeItem('token');
            window.location.replace('login.html');
        });
    });

    // ----------------------------------------
    //  الأمان: تغيير الإيميل وكلمة المرور
    // ----------------------------------------
    const securityMainView = document.getElementById('securityMainView');
    const emailChangeView  = document.getElementById('emailChangeView');
    const passChangeView   = document.getElementById('passChangeView');
    const emailOtpFlow     = document.getElementById('emailOtpFlow');
    const passOtpFlow      = document.getElementById('passOtpFlow');
    const reqEmailOtpBtn   = document.getElementById('reqEmailOtpBtn');
    const reqPassOtpBtn    = document.getElementById('reqPassOtpBtn');

    function resetSecurityViews() {
        if (emailChangeView)  emailChangeView.style.display  = 'none';
        if (passChangeView)   passChangeView.style.display   = 'none';
        if (securityMainView) securityMainView.style.display = 'block';
        if (emailOtpFlow)     emailOtpFlow.style.display     = 'none';
        if (passOtpFlow)      passOtpFlow.style.display      = 'none';
        ['emailOtpInput', 'newEmailInput', 'passOtpInput', 'newPassInput'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        if (reqEmailOtpBtn) resetSecurityBtn(reqEmailOtpBtn, 'إرسال رمز التحقق');
        if (reqPassOtpBtn)  resetSecurityBtn(reqPassOtpBtn,  'إرسال رمز التحقق');
    }

    document.getElementById('btnOpenEmailChange')?.addEventListener('click', () => {
        securityMainView.style.display = 'none';
        emailChangeView.style.display  = 'block';
        checkAndApplyCooldowns(reqEmailOtpBtn, reqPassOtpBtn);
    });

    document.getElementById('btnOpenPassChange')?.addEventListener('click', () => {
        securityMainView.style.display = 'none';
        passChangeView.style.display   = 'block';
        checkAndApplyCooldowns(reqEmailOtpBtn, reqPassOtpBtn);
    });

    ['backFromEmailBtn', 'backFromPassBtn', 'cancelEmailFlowBtn', 'cancelPassFlowBtn'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', (e) => { e.preventDefault(); resetSecurityViews(); });
    });

    checkAndApplyCooldowns(reqEmailOtpBtn, reqPassOtpBtn);

    reqEmailOtpBtn?.addEventListener('click', () => requestOtp(reqEmailOtpBtn, emailOtpFlow, token));
    reqPassOtpBtn?.addEventListener('click',  () => requestOtp(reqPassOtpBtn,  passOtpFlow,  token));

    document.getElementById('confirmEmailChangeBtn')?.addEventListener('click', async () => {
        const otp      = document.getElementById('emailOtpInput').value;
        const newEmail = document.getElementById('newEmailInput').value;
        await confirmSecurityChange('email', otp, newEmail, token, async () => {
            document.getElementById('currentEmailDisplay').textContent = newEmail;
            resetSecurityViews();
            // تحديث التوكن إذا أرسل السيرفر واحداً جديداً
            const res  = await fetch(`${API_URL}/auth/settings/update-security`, {});
            const data = res.ok ? await res.json() : {};
            if (data.new_token) {
                sessionStorage.setItem('token', data.new_token);
                setTimeout(() => window.location.reload(), 1500);
            }
        });
    });

    document.getElementById('confirmPassChangeBtn')?.addEventListener('click', async () => {
        const otp     = document.getElementById('passOtpInput').value;
        const newPass = document.getElementById('newPassInput').value;
        if (newPass.length < 6) return showToast('كلمة المرور 6 أحرف على الأقل', 'error');
        await confirmSecurityChange('password', otp, newPass, token, () => resetSecurityViews());
    });

    // ----------------------------------------
    //  تغيير الأفاتار
    // ----------------------------------------
    let selectedTempAvatar = null;
    const avatarModal           = document.getElementById('avatarModal');
    const closeAvatarModal      = document.getElementById('closeAvatarModal');
    const changeAvatarBtn       = document.getElementById('changeAvatarBtn');
    const modalAvatarsWrapper   = document.getElementById('modalAvatarsWrapper');
    const confirmAvatarSelection = document.getElementById('confirmAvatarSelection');

    changeAvatarBtn?.addEventListener('click', () => {
        avatarModal.style.display           = 'flex';
        confirmAvatarSelection.style.display = 'none';
        renderAvatarGrid({
            wrapper:    modalAvatarsWrapper,
            confirmBtn: confirmAvatarSelection,
            onSelect:   (url) => { selectedTempAvatar = url; customAvatarFile = null; },
        });
    });

    closeAvatarModal?.addEventListener('click', () => { avatarModal.style.display = 'none'; });

    confirmAvatarSelection?.addEventListener('click', () => {
        if (!selectedTempAvatar) return;
        document.getElementById('settingsAvatarPreview').src = selectedTempAvatar;
        showToast('تم تغيير الصورة مؤقتاً! اضغط (حفظ التغييرات) لاعتمادها.', 'success');
        avatarModal.style.display = 'none';
    });

    // رفع صورة مخصصة
    const customAvatarInput = document.getElementById('customAvatarInput');
    document.getElementById('triggerAvatarUpload')?.addEventListener('click', () => customAvatarInput?.click());

    customAvatarInput?.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
            showToast('حجم الصورة يجب أن لا يتجاوز 2 ميجابايت', 'error');
            this.value = '';
            return;
        }
        customAvatarFile   = file;
        selectedTempAvatar = null;

        const reader = new FileReader();
        reader.onload = (ev) => {
            document.getElementById('settingsAvatarPreview').src = ev.target.result;
            avatarModal.style.display = 'none';
            showToast('تم رفع الصورة بنجاح! اضغط (حفظ التغييرات) لتثبيتها.', 'success');
        };
        reader.readAsDataURL(file);
    });

    // ----------------------------------------
    //  حفظ الملف الشخصي
    // ----------------------------------------
    document.getElementById('saveProfileBtn')?.addEventListener('click', () => {
        saveProfile({
            token:      token,
            newName:    document.getElementById('editPlayerName').value.trim(),
            avatarFile: customAvatarFile,
            avatarUrl:  document.getElementById('settingsAvatarPreview').getAttribute('src'),
            country:    sessionStorage.getItem('country') || userDataCache?.country || 'SA',
            onSuccess: (data) => {
                const newAvatar = data.new_avatar || data.avatar;
                userDataCache.avatar      = newAvatar;
                userDataCache.player_name = document.getElementById('editPlayerName').value.trim();

                const correctUrl = getCorrectAvatarUrl(newAvatar);
                document.getElementById('playerAvatar').src = correctUrl;

                // تحديث السوكيت
                joinGlobalLobby();

                closeSettings();
                showToast('تم حفظ التغييرات بنجاح', 'success');
            },
        });
    });

    // ----------------------------------------
    //  إعدادات الصوت
    // ----------------------------------------
    initVolumeControls();

    // ----------------------------------------
    //  التنبيهات
    // ----------------------------------------
    const notificationsBtn   = document.getElementById('notificationsBtn');
    const notificationsModal = document.getElementById('notificationsModal');
    const closeNotifications = document.getElementById('closeNotifications');

    notificationsBtn?.addEventListener('click', () => {
        notificationsModal.style.display = 'flex';
        socket.emit('mark_notifications_read', { token });
        const badge = document.getElementById('notifBadge');
        if (badge) badge.style.display = 'none';
    });
    closeNotifications?.addEventListener('click', () => { notificationsModal.style.display = 'none'; });

    // ----------------------------------------
    //  الرسائل الجاهزة (Quick Chat) — بديل آمن للدردشة الحرة
    // (الدردشة الحرة مؤجّلة، ستُضاف لاحقاً مع نظام إشراف)
    // ----------------------------------------
    const quickChatBtn = document.getElementById('globalQuickChatBtn');
    if (quickChatBtn && window.QuickChat) {
        QuickChat.init({
            socket,
            triggerBtn: quickChatBtn,
            event: 'send_chat_message',   // دردشة عامة في الـ lobby
        });
    }

    // ----------------------------------------
    //  إغلاق النوافذ عند النقر خارجها
    // ----------------------------------------
    window.addEventListener('click', (e) => {
        if (e.target === settingsModal)      closeSettings();
        if (e.target === notificationsModal) notificationsModal.style.display = 'none';
        if (e.target === avatarModal)        avatarModal.style.display = 'none';
        const confirm = document.getElementById('customConfirm');
        if (e.target === confirm) confirm.style.display = 'none';
    });
});
