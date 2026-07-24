// ============================================================
// lobby.js — صفحة اللوبي (انتظار الأصدقاء / البحث عن منافس)
// المتطلبات: config.js → utils.js → settings.js
// ============================================================


// حماية المسار
const token = (typeof getToken === 'function') ? getToken() : (localStorage.getItem('token') || sessionStorage.getItem('token'));
if (!token) window.location.replace('login.html');

// الاتصال بالسوكيت
const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });

// ============================================================
//  رمز جلسة ثابت لوضع الجمعات — ينجو من إعادة اتصال السوكت
//  (لو خرجت لتليجرام ورجعت وقد تغيّر sid، يظل الربط يوصل للصفحة)
// ============================================================
function getPartyToken() {
    let t = sessionStorage.getItem('partyToken');
    if (!t) {
        t = 'pt_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
        sessionStorage.setItem('partyToken', t);
    }
    return t;
}
socket.on('connect', () => {
    const t = getPartyToken();
    socket.emit('register_party_token', { party_token: t });
    socket.emit('check_host_link',      { party_token: t });
});
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        socket.emit('check_host_link', { party_token: getPartyToken() });
    }
});
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
            // ربط النقر لفتح بروفايل المُرسِل
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
    if (typeof showGlobalToast === 'function') showGlobalToast('🔔 ' + notif.message);
    fetchNotifs();  // نعيد جلب القائمة (مع throttle)
});

//  throttle: يمنع الجلب المتكرر السريع (مثلاً عند إعادة اتصال متكررة)
let _lastNotifFetch = 0;
function fetchNotifs() {
    const now = Date.now();
    if (now - _lastNotifFetch < 3000) return;  // مرة كل 3 ثوانٍ كحد أقصى
    _lastNotifFetch = now;
    if (token && socket.connected) socket.emit('fetch_notifications', { token });
}
if (socket.connected) fetchNotifs();
socket.on('connect', fetchNotifs);

// قراءة وضع اللعبة من الرابط أو الجلسة
const urlParams = new URLSearchParams(window.location.search);
let selectedGameMode = urlParams.get('game');
if (selectedGameMode) {
    sessionStorage.setItem('selectedGameMode', selectedGameMode);
} else {
    selectedGameMode = sessionStorage.getItem('selectedGameMode');
}
if (!selectedGameMode) window.location.replace('categories.html');

// بروفايل الإشعارات: في اللوبي نعرض إحصائيات اللعبة المحددة + العامة
window.PROFILE_GAME_MODE = selectedGameMode || null;
// المتجر في اللوبي: مساعدات هذه اللعبة + كل التجميليات
window.STORE_CONTEXT = selectedGameMode || 'huroof';
window.CURRENT_GAME = selectedGameMode || 'huroof';
window.openStoreModal = function () {
    const m = document.getElementById('storeModal');
    if (m) m.style.display = 'flex';
    if (typeof openStore === 'function') openStore();
};

// حالة الصفحة
let userDataCache    = null;
let codeInterval     = null;
let customAvatarFile = null;


// ============================================================
//  بدء التشغيل
// ============================================================
window.addEventListener('DOMContentLoaded', async () => {

    // تطبيق ثيم اللعبة المختارة
    const theme = GAME_THEMES[selectedGameMode];
    if (theme) {
        const titleEl = document.getElementById('lobbyMainTitle');
        if (titleEl) { titleEl.textContent = theme.title; titleEl.style.color = theme.color; }
        const iconEl = document.getElementById('gameIconDisplay');
        if (iconEl) iconEl.textContent = theme.icon;
    }

    // ----------------------------------------
    //  السوكيت: اللاعبين المتصلين
    // ----------------------------------------
    //  نظام الحضور بالفروقات (presence.js) — بدل بث القائمة الكاملة
    initPresence(socket, (allPlayers) => {
        const lobbyPlayers = allPlayers.filter(p =>
            p.location === selectedGameMode ||
            p.location === `playing_${selectedGameMode}` ||
            p.location === `party_${selectedGameMode}`
        );

        const countEl = document.getElementById('globalOnlineCount');
        if (countEl) countEl.textContent = lobbyPlayers.length;

        // تحديث أفاتار الهيدر
        const me = allPlayers.find(p => p.name === userDataCache?.player_name);
        if (me) {
            const avatarEl = document.getElementById('playerAvatar');
            if (avatarEl) avatarEl.src = getCorrectAvatarUrl(me.avatar);
        }

        const list = document.getElementById('globalPlayersList');
        if (!list) return;

        //  ترتيب: اللاعب الحالي أولاً
        const myName = userDataCache?.player_name;
        const sortedLobbyPlayers = myName
            ? [...lobbyPlayers].sort((a, b) => {
                if (a.name === myName) return -1;
                if (b.name === myName) return 1;
                return 0;
              })
            : lobbyPlayers;

        list.innerHTML = '';
        //  سقف الرسم: العدّاد يعرض الكل، والقائمة ترسم أول 100 فقط
        const MAX_RENDER = 100;
        const hiddenCount = Math.max(0, sortedLobbyPlayers.length - MAX_RENDER);
        sortedLobbyPlayers.slice(0, MAX_RENDER).forEach(p => {
            let locationText = `لوبي ${GAME_THEMES[selectedGameMode]?.title || 'اللعبة'}`;
            let statusColor  = '#facc15';

            if (p.location === `playing_${selectedGameMode}`) {
                locationText = `⚔️ يخوض معركة (${GAME_THEMES[selectedGameMode]?.title || 'اللعبة'})`;
                statusColor  = '#f43f5e';
            } else if (p.location === `playing_${selectedGameMode}_friendly`) {
                locationText = `⚔️ معركة ودية (${GAME_THEMES[selectedGameMode]?.title || 'اللعبة'}) ضد صديق`;
                statusColor  = '#f43f5e';
            } else if (p.location === `party_${selectedGameMode}`) {
                locationText = 'في وضع الجمعات 🎮';
                statusColor  = '#ff9800';
            }

            const div = document.createElement('div');
            div.className = 'online-player-item';
            if (userDataCache && p.name === userDataCache.player_name) div.classList.add('is-me');

            //  نبني العناصر بـ DOM API بدل innerHTML لمنع XSS
            const img = document.createElement('img');
            img.src = getCorrectAvatarUrl(p.avatar);
            img.className = 'online-player-avatar';
            img.alt = 'Avatar';

            const infoDiv = document.createElement('div');
            infoDiv.className = 'online-player-info';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'online-player-name';
            nameSpan.textContent = p.name || '';  // textContent آمن من XSS

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

    socket.on('game_chat_history', (history) => {
        const container = document.getElementById('globalChatMessages');
        if (container) container.innerHTML = '';
        history.forEach(msg => addGlobalChatMessage(msg.sender, msg.text, msg.isSystem, msg.sender_id, msg.emojiId));
    });

    socket.on('new_game_chat_message', (msg) => {
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            //  نبني العنصر بـ DOM API لمنع XSS تماماً (textContent آمن)
            const el = document.createElement('div');
            el.className = `chat-message ${msg.isSystem ? 'system' : ''}`;

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

    function joinLobby() {
        if (userDataCache && selectedGameMode) {
            socket.emit('join_game_lobby', {
                gameMode: selectedGameMode,
                name:     userDataCache.player_name,
                avatar:   userDataCache.avatar,
                token,
            });
            document.title = `لوبي ${GAME_THEMES[selectedGameMode]?.title || 'اللعبة'}`;
        }
    }

    socket.on('connect', () => { if (userDataCache) joinLobby(); });

    // ----------------------------------------
    //  زر الجمعات (الـ Party)
    // ----------------------------------------
    const localPartyBtn    = document.getElementById('localPartyBtn');
    const partyModeModal   = document.getElementById('partyModeModal');

    if (localPartyBtn) {
        //  وضع الجمعات حصري للعبة "خلية الحروف" فقط
        localPartyBtn.style.display = (selectedGameMode === 'huroof') ? 'flex' : 'none';
        localPartyBtn.addEventListener('click', () => {
            if (partyModeModal) partyModeModal.style.display = 'flex';
        });
    }

    // ----------------------------------------
    //  جلب بيانات الحساب
    // ----------------------------------------
    try {
        const res= await fetch(`${API_URL}/auth/me`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (!res.ok) {
            // 401/403 فقط تعني توكناً غير صالح؛ غيرها عطل مؤقت لا يستوجب الخروج
            if (res.status === 401 || res.status === 403) {
                sessionStorage.removeItem('token');
                try { localStorage.removeItem('token'); } catch (e) {}
                return window.location.replace('login.html');
            }
            if (typeof showToast === 'function') {
                showToast('تعذّر تحميل بياناتك مؤقتاً. أعد المحاولة بعد قليل.', 'error');
            }
            return;
        }

        userDataCache = await res.json();

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

        // حفظ في الجلسة للعبة
        sessionStorage.setItem('playerName',   userDataCache.player_name);
        sessionStorage.setItem('playerAvatar', userDataCache.avatar);

        // العملات والجواهر
        const coinsEl = document.getElementById('coins');
        const gemsEl  = document.getElementById('gems');
        if (coinsEl) coinsEl.textContent = userDataCache.coins ?? 0;
        if (gemsEl)  gemsEl.textContent  = userDataCache.gems  ?? 0;

        // المستوى وشريط الـ XP
        const { level, progress } = calcXpProgress(userDataCache.xp || 0);
        const levelEl = document.getElementById('playerLevel');
        const xpBarEl = document.getElementById('xpFill');
        if (levelEl) levelEl.textContent = userDataCache.level ?? level;
        if (xpBarEl) xpBarEl.style.width = `${progress}%`;

        // تعبئة نموذج الإعدادات
        const editNameEl = document.getElementById('editPlayerName');
        if (editNameEl) editNameEl.value = userDataCache.player_name;

        const settingsPreview = document.getElementById('settingsAvatarPreview');
        if (settingsPreview) settingsPreview.src = avatarUrl;

        const isGoogle = userDataCache.auth_provider === 'google';
        document.getElementById('googleAuthBadge').style.display = isGoogle ? 'block' : 'none';
        document.getElementById('localAuthFields').style.display = isGoogle ? 'none'  : 'block';

        if (socket.connected) joinLobby();
        else socket.once('connect', joinLobby);

    } catch {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }

    // الرجوع للساحة
    document.getElementById('backToCategoriesBtn')?.addEventListener('click', () => {
        window.location.replace('categories.html');
    });

    // ----------------------------------------
    //  التنبيهات (مستمعات السوكيت مسجّلة في أعلى الملف)
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
    //  الإعدادات
    // ----------------------------------------
    const settingsModal       = document.getElementById('settingsModal');
    const globalSettingsBtn   = document.getElementById('globalSettingsBtn');
    const openProfileSettings = document.getElementById('openProfileSettings');
    const closeSettingsModal  = document.getElementById('closeSettingsModal');

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
        showConfirm('تسجيل الخروج', 'هل أنت متأكد من رغبتك في تسجيل الخروج؟', () => {
            sessionStorage.clear();
            window.location.replace('login.html');
        });
    });

    // ----------------------------------------
    //  الأمان
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
        await confirmSecurityChange('email', otp, newEmail, token, () => {
            document.getElementById('currentEmailDisplay').textContent = newEmail;
            resetSecurityViews();
        });
    });

    document.getElementById('confirmPassChangeBtn')?.addEventListener('click', async () => {
        const otp     = document.getElementById('passOtpInput').value;
        const newPass = document.getElementById('newPassInput').value;
        await confirmSecurityChange('password', otp, newPass, token, () => resetSecurityViews());
    });

    // ----------------------------------------
    //  تغيير الأفاتار
    // ----------------------------------------
    let selectedTempAvatar   = null;
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

                document.getElementById('playerAvatar').src = getCorrectAvatarUrl(newAvatar);
                socket.emit('update_player_info', { name: userDataCache.player_name, avatar: newAvatar });
                closeSettings();
                showToast('تم التحديث اللحظي!', 'success');
            },
        });
    });

    // ----------------------------------------
    //  إعدادات الصوت
    // ----------------------------------------
    initVolumeControls();

    // ----------------------------------------
    //  اللعب السريع (Matchmaking)
    // ----------------------------------------
    const quickPlayBtn        = document.getElementById('quickPlayBtn');
    const lobbyMainContent    = document.getElementById('lobbyMainContent');
    const matchmakingScreen   = document.getElementById('matchmakingScreen');
    const cancelMatchmakingBtn = document.getElementById('cancelMatchmakingBtn');
    const mmRadar             = document.getElementById('mmRadar');
    const mmTeamsPreview      = document.getElementById('mmTeamsPreview');
    const mmStatusTitle       = document.getElementById('mmStatusTitle');
    const mmStatusDesc        = document.getElementById('mmStatusDesc');
    const mmCountdown         = document.getElementById('mmCountdown');

    quickPlayBtn?.addEventListener('click', () => {
        lobbyMainContent.style.display   = 'none';
        matchmakingScreen.style.display  = 'flex';
        document.body.classList.add('mm-active');
        mmRadar.style.display            = 'block';
        mmTeamsPreview.style.display     = 'none';
        mmCountdown.style.display        = 'none';
        cancelMatchmakingBtn.style.display = 'block';
        mmStatusTitle.textContent = 'البحث عن منافس...';
        mmStatusDesc.textContent  = 'جاري البحث عن لاعبين في نفس مستواك';
        socket.emit('quick_play_search', {
            token:       token,
            player_name: userDataCache.player_name,
            game_mode:   selectedGameMode,
            avatar:      userDataCache.avatar,
        });
    });

    cancelMatchmakingBtn?.addEventListener('click', () => {
        socket.emit('cancel_quick_play');
        matchmakingScreen.style.display = 'none';
        document.body.classList.remove('mm-active');
        lobbyMainContent.style.display  = 'block';
    });

    // 🆕 معالج الخطأ — يطلع للاعب بدل ما يبقى عالق في "جاري البحث"
    socket.on('quick_play_error', (data) => {
        const msg = (data && data.msg) ? data.msg : 'تعذّر البحث عن مباراة';
        mmStatusTitle.textContent = 'تعذّر البحث';
        mmStatusTitle.style.color = '#f44336';
        mmStatusDesc.textContent  = msg;
        cancelMatchmakingBtn.style.display = 'block';
        cancelMatchmakingBtn.textContent = 'رجوع';
    });


    // مساعدة: معالجة مسار الأفاتار للعرض في شاشة التطابق
    function mmAvatarSrc(src) {
        if (!src || String(src).trim() === '') return 'assets/avatars/avatar_1.svg';
        let v = String(src).trim();
        // نعالج الروابط القديمة الثابتة (127.0.0.1/localhost)
        const staleMatch = v.match(/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/.*)$/i);
        if (staleMatch) {
            const path = staleMatch[3];
            if (path.startsWith('/uploads')) return (typeof API_URL !== 'undefined' ? API_URL : '') + path;
            const fn = path.split('/').pop();
            return `assets/avatars/${fn}`;
        }
        if (v.startsWith('/uploads')) return (typeof API_URL !== 'undefined' ? API_URL : '') + v;
        if (v.startsWith('http') || v.startsWith('data:') || v.startsWith('/') || v.startsWith('../')) return v;
        const name = v.split('/').pop();
        return `assets/avatars/${name.includes('.') ? name : name + '.svg'}`;
    }
    socket.on('match_found', (data) => {
        try {
            sessionStorage.setItem('gameRoomCode', data.room_code);
            sessionStorage.setItem('myRole', data.role || 'guest');
            // دعوة صديق: نخزّن وضع اللعبة + علامة الودية + أنهما صديقان
            const gameMode = data.gameMode || selectedGameMode;
            sessionStorage.setItem('selectedGameMode', gameMode);
            sessionStorage.setItem('isFriendly', data.friendly ? '1' : '0');

            // لو كانت لوحة الأصدقاء مفتوحة (دعوة صديق) نغلقها ونُظهر شاشة التطابق
            const fm = document.getElementById('friendsModal');
            if (fm) fm.style.display = 'none';
            lobbyMainContent.style.display  = 'none';
            matchmakingScreen.style.display = 'flex';
            document.body.classList.add('mm-active');

            mmRadar.style.display          = 'none';
            mmTeamsPreview.style.display   = 'flex';
            cancelMatchmakingBtn.style.display = 'none';
            mmStatusTitle.textContent = data.friendly ? 'مباراة ودية مع صديق!' : 'تم إيجاد منافس!';
            mmStatusTitle.style.color = '#00ff88';
            mmStatusDesc.textContent  = 'الاستعداد للمعركة...';

            const players = Array.isArray(data.players)
                ? data.players
                : Object.values(data.players || {});

            players.forEach((p, i) => {
                const color = p.color || p.team || (i === 0 ? 'green' : 'orange');
                if (color === 'green') {
                    document.getElementById('mmGreenName').textContent = p.name || 'لاعب';
                    document.getElementById('mmGreenAvatar').src       = mmAvatarSrc(p.avatar);
                } else {
                    document.getElementById('mmOrangeName').textContent = p.name || 'لاعب';
                    document.getElementById('mmOrangeAvatar').src       = mmAvatarSrc(p.avatar);
                }
            });

            mmCountdown.style.display = 'block';
            let count = 3;
            mmCountdown.textContent   = count;

            const countInterval = setInterval(() => {
                count--;
                if (count > 0) {
                    mmCountdown.textContent = count;
                } else {
                    clearInterval(countInterval);
                    mmCountdown.textContent = 'انطلاق!';
                    setTimeout(() => window.location.assign(`games/${gameMode}.html`), 500);
                }
            }, 1000);

        } catch (err) {
            console.error('match_found error:', err);
            const gm = data.gameMode || selectedGameMode;
            setTimeout(() => window.location.assign(`games/${gm}.html`), 1000);
        }
    });

    // ----------------------------------------
    //  الغرف الخاصة
    // ----------------------------------------
    let currentRoomCode    = null;
    const waitingScreen    = document.getElementById('waitingScreen');

    document.getElementById('openCreateRoomBtn')?.addEventListener('click', () => {
        document.getElementById('createRoomModal').style.display = 'flex';
    });
    document.getElementById('closeCreateRoom')?.addEventListener('click', () => {
        document.getElementById('createRoomModal').style.display = 'none';
    });
    document.getElementById('openJoinRoomBtn')?.addEventListener('click', () => {
        document.getElementById('joinRoomModal').style.display = 'flex';
    });
    document.getElementById('closeJoinRoom')?.addEventListener('click', () => {
        document.getElementById('joinRoomModal').style.display = 'none';
    });

    document.getElementById('confirmCreateRoom')?.addEventListener('click', () => {
        socket.emit('create_room', {
            host_name: userDataCache.player_name,
            game_mode: selectedGameMode,
            avatar:    userDataCache.avatar,
        });
    });

    socket.on('room_created', (data) => {
        document.getElementById('createRoomModal').style.display = 'none';
        currentRoomCode = data.room_code;
        sessionStorage.setItem('gameRoomCode', currentRoomCode);
        sessionStorage.setItem('myRole', 'host');
        enterWaitingScreen(currentRoomCode, true);
        updateRoomPlayersUI(data.players);
        showToast('تم إنشاء الغرفة بنجاح!', 'success');
    });

    document.getElementById('confirmJoinRoom')?.addEventListener('click', () => {
        const code = document.getElementById('roomCodeInput').value.toUpperCase();
        if (code.length === 6) {
            socket.emit('join_room', { room_code: code, player_name: userDataCache.player_name, avatar: userDataCache.avatar });
        } else {
            showToast('يرجى إدخال كود من 6 أحرف', 'error');
        }
    });

    socket.on('room_joined', (data) => {
        document.getElementById('joinRoomModal').style.display = 'none';
        currentRoomCode = data.room_code;
        sessionStorage.setItem('gameRoomCode', currentRoomCode);
        sessionStorage.setItem('myRole', 'guest');
        enterWaitingScreen(currentRoomCode, data.is_host);
        updateRoomPlayersUI(data.players);
        showToast('تم الانضمام للغرفة!', 'success');
    });

    socket.on('error_message', (msg) => showToast(msg, 'error'));
    socket.on('update_room', (data) => {
        if (data.room_code === currentRoomCode) updateRoomPlayersUI(data.players);
    });

    function enterWaitingScreen(code, isHost) {
        lobbyMainContent.style.display   = 'none';
        matchmakingScreen.style.display  = 'none';
        document.body.classList.remove('mm-active');
        waitingScreen.style.display      = 'flex';
        document.getElementById('roomCodeDisplay').textContent = code;

        document.getElementById('startGameBtn').style.display  = 'none';
        document.getElementById('cancelWaitingBtn').style.display = 'inline-block';

        const statusText = document.getElementById('statusText');
        statusText.textContent  = 'بانتظار انضمام الخصم...';
        statusText.style.color  = '#fff';
        statusText.style.fontSize = '16px';
    }

    function updateRoomPlayersUI(players) {
        const safePlayers = Array.isArray(players) ? players : Object.values(players);

        document.getElementById('roomPlayersCount').textContent = safePlayers.length;

        const slots = document.getElementById('ffaSlots');
        slots.innerHTML = '';

        safePlayers.forEach((p, i) => {
            const color     = p.color || p.team || (i === 0 ? 'green' : 'orange');
            const colorEmoji = color === 'green' ? '🟢' : '🟠';
            const slot      = document.createElement('div');
            slot.className  = 'player-slot';
            slot.innerHTML  = `
                <img loading="lazy" src="${p.avatar || '../assets/avatars/avatar_1.svg'}"
                     style="width:60px;height:60px;border-radius:50%;border:2px solid ${GAME_THEMES[selectedGameMode].color};margin-bottom:10px;object-fit:cover;">
                <span style="color:#fff;font-size:14px;font-weight:bold;display:block;">${p.name} ${colorEmoji}</span>
            `;
            slots.appendChild(slot);
        });

        if (safePlayers.length >= 2) {
            const statusText  = document.getElementById('statusText');
            const cancelBtn   = document.getElementById('cancelWaitingBtn');
            if (cancelBtn) cancelBtn.style.display = 'none';

            statusText.style.color      = '#00ff88';
            statusText.style.fontSize   = '20px';
            statusText.style.fontWeight = 'bold';

            let count = 3;
            statusText.textContent = `اكتمل العدد! تبدأ المعركة خلال ${count}...`;

            const autoStart = setInterval(() => {
                count--;
                if (count > 0) {
                    statusText.textContent = `اكتمل العدد! تبدأ المعركة خلال ${count}...`;
                } else {
                    clearInterval(autoStart);
                    statusText.textContent = 'انطلاق!';
                    if (sessionStorage.getItem('myRole') === 'host') {
                        socket.emit('start_game', { room_code: currentRoomCode });
                    }
                    setTimeout(() => window.location.assign(`games/${selectedGameMode}.html`), 500);
                }
            }, 1000);
        }
    }

    document.getElementById('cancelWaitingBtn')?.addEventListener('click', () => {
        showConfirm('مغادرة الغرفة', 'هل تريد فعلاً مغادرة الغرفة؟', () => {
            waitingScreen.style.display    = 'none';
            lobbyMainContent.style.display = 'block';
            currentRoomCode                = null;
        });
    });

    document.getElementById('startGameBtn')?.addEventListener('click', () => {
        if (currentRoomCode) socket.emit('start_game', { room_code: currentRoomCode });
    });

    socket.on('game_started', (data) => {
        if (data?.roomCode === currentRoomCode) {
            window.location.assign(`games/${selectedGameMode}.html`);
        }
    });

    // ----------------------------------------
    //  الرسائل الجاهزة (Quick Chat) — بديل آمن للدردشة الحرة
    // ----------------------------------------
    const quickChatBtn = document.getElementById('globalQuickChatBtn');
    if (quickChatBtn && window.QuickChat) {
        QuickChat.init({
            socket,
            triggerBtn: quickChatBtn,
            event: 'send_game_chat_message',
            extra: () => ({ gameMode: selectedGameMode }),  // لوبي اللعبة الحالية
        });
    }

    //  العب مع صديق → يفتح لوحة الأصدقاء (نظام الدعوة الآمن)
    document.getElementById('playWithFriendBtn')?.addEventListener('click', () => {
        const navBtn = document.getElementById('friendsNavBtn');
        if (navBtn) {
            navBtn.click();  // يفتح اللوحة ويحمّل بيانات الأصدقاء
        } else {
            const fm = document.getElementById('friendsModal');
            if (fm) fm.style.display = 'flex';
        }
    });

    // ----------------------------------------
    //  وضع الجمعات (Telegram Bot)
    // ----------------------------------------
    const generateBtn = document.getElementById('generateCodeBtn');
    const codeArea    = document.getElementById('codeDisplayArea');
    const codeText    = document.getElementById('secretCodeText');
    const timerText   = document.getElementById('timerText');

    generateBtn?.addEventListener('click', () => {
        socket.emit('generate_host_code', { party_token: getPartyToken() });
        generateBtn.style.display = 'none';
        codeArea.style.display    = 'block';
        codeText.innerText        = 'جاري...';
        timerText.innerText       = 'يرجى الانتظار...';
        timerText.style.color     = 'red';
    });

    socket.on('receive_host_code', (data) => {
        codeText.innerText     = data.code;
        codeText.style.display = 'block';

        // زر فتح تليجرام تلقائياً بالرمز (رابط عميق) — ربط بضغطة بلا كتابة
        const botUser = (data.bot || '@p_rushbot').replace('@', '');
        let dl = document.getElementById('tgDeepLink');
        if (!dl) {
            dl = document.createElement('a');
            dl.id = 'tgDeepLink';
            dl.target = '_blank';
            dl.rel = 'noopener';
            dl.style.cssText = 'display:block;margin:16px auto 0;background:#229ED9;color:#fff;padding:13px 18px;border-radius:10px;font-weight:bold;text-decoration:none;max-width:340px;';
            if (codeArea) codeArea.appendChild(dl);
        }
        dl.href = `https://t.me/${botUser}?start=${data.code}`;
        dl.innerHTML = '📲 افتح تليجرام واربط تلقائياً';
        dl.style.display = 'block';

        let totalTime = 30; // 30 ثانية — قصيرة عمداً حتى لا يلتقط أحدٌ الرمز ويخرّب على المستضيف
        timerText.style.color = '#bbb';
        timerText.innerText   = `الرمز صالح لمدة ${totalTime} ثانية`;

        if (codeInterval) clearInterval(codeInterval);

        codeInterval = setInterval(() => {
            totalTime--;
            if (totalTime > 0) {
                timerText.innerText = `الرمز صالح لمدة ${totalTime} ثانية`;
            } else {
                clearInterval(codeInterval);
                codeText.innerText    = '❌';
                timerText.innerText   = 'انتهت صلاحية الرمز!';
                timerText.style.color = 'red';
                if (dl) dl.style.display = 'none';
                setTimeout(() => {
                    if (generateBtn) generateBtn.style.display = 'block';
                    if (codeArea)    codeArea.style.display    = 'none';
                }, 2000);
            }
        }, 1000);
    });

    socket.on('host_linked_success', () => {
        if (window.__hostLinkedHandled) return;   // مرة واحدة فقط لكل تحميل صفحة
        window.__hostLinkedHandled = true;
        if (codeInterval) clearInterval(codeInterval);
        // نمسح التوكن حتى لا يُعاد فحص الربط ويعيد فتح الصفحة عند الرجوع للوبي
        try { sessionStorage.removeItem('partyToken'); } catch (e) {}
        if (partyModeModal) {
            partyModeModal.innerHTML = `
                <div style="background:#1a1a2e;padding:40px;border-radius:20px;color:white;width:90%;max-width:500px;box-shadow:0 0 30px rgba(0,255,136,0.5);border:2px solid #00ff88;">
                    <h1 style="color:#00ff88;font-size:60px;margin:0;">✅</h1>
                    <h2 style="color:white;margin-top:10px;">تم ربط المضيف بنجاح!</h2>
                    <p style="color:#bbb;">تبدأ اللعبة الآن...</p>
                </div>
            `;
            setTimeout(() => {
                partyModeModal.style.display = 'none';
                window.location.href = 'games/huroof_party.html';
            }, 2000);
        }
    });

    // ----------------------------------------
    //  إغلاق النوافذ عند النقر خارجها
    // ----------------------------------------
    window.addEventListener('click', (e) => {
        if (e.target === settingsModal)      closeSettings();
        if (e.target === notificationsModal) notificationsModal.style.display = 'none';
        if (e.target === avatarModal)        avatarModal.style.display = 'none';
        const confirmEl = document.getElementById('customConfirm');
        if (e.target === confirmEl) confirmEl.style.display = 'none';
        if (e.target === partyModeModal) {
            partyModeModal.style.display = 'none';
            if (generateBtn) generateBtn.style.display = 'block';
            if (codeArea)    codeArea.style.display    = 'none';
        }
    });
});

// ============================================================
//  تحميل مسبق لشعارات أندية "مسيرة لاعب" (كاش المتصفح)
// يعمل فقط في لوبي career، بعد استقرار اللوبي (لا يبطئه).
// النتيجة: داخل اللعبة الشعارات تظهر فوراً (من الكاش/الملفات المحلية).
// ============================================================
(function preloadCareerLogos() {
    if (selectedGameMode !== 'career') return;
    setTimeout(async () => {
        try {
            const res = await fetch(`${API_URL}/career/logos`);
            if (!res.ok) return;
            const data = await res.json();
            const logos = data.logos || [];
            // نحمّل تدريجياً (5 بالتوازي) حتى لا نضغط الشبكة
            let idx = 0;
            function next() {
                if (idx >= logos.length) return;
                const img = new Image();
                img.onload = img.onerror = next;
                img.src = `assets/clubs/${logos[idx++]}`;
            }
            for (let k = 0; k < 5; k++) next();
            console.log(`⚽ تحميل مسبق: ${logos.length} شعار نادٍ`);
        } catch (_) { /* صامت — التحميل المسبق تحسين اختياري */ }
    }, 1200);
})();
