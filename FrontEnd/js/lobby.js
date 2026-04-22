// ============================================================
// lobby.js — صفحة اللوبي (انتظار الأصدقاء / البحث عن منافس)
// المتطلبات: config.js → utils.js → settings.js
// ============================================================


// حماية المسار
const token = sessionStorage.getItem('token');
if (!token) window.location.replace('login.html');

// الاتصال بالسوكيت
const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });

// قراءة وضع اللعبة من الرابط أو الجلسة
const urlParams = new URLSearchParams(window.location.search);
let selectedGameMode = urlParams.get('game');
if (selectedGameMode) {
    sessionStorage.setItem('selectedGameMode', selectedGameMode);
} else {
    selectedGameMode = sessionStorage.getItem('selectedGameMode');
}
if (!selectedGameMode) window.location.replace('categories.html');

// حالة الصفحة
let userDataCache    = null;
let codeInterval     = null;
let customAvatarFile = null;


// ============================================================
// 🚀 بدء التشغيل
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
    // 🌍 السوكيت: اللاعبين المتصلين
    // ----------------------------------------
    // ✅ نحتفظ بآخر قائمة وصلت لإعادة رسمها بعد تحميل userDataCache
    let lastPlayersSnapshot = [];

    function renderLobbyPlayers(allPlayers) {
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

        list.innerHTML = '';
        lobbyPlayers.forEach(p => {
            let locationText = `لوبي ${GAME_THEMES[selectedGameMode]?.title || 'اللعبة'}`;
            let statusColor  = '#facc15';

            if (p.location === `playing_${selectedGameMode}`) {
                locationText = `⚔️ يخوض معركة (${GAME_THEMES[selectedGameMode]?.title || 'اللعبة'})`;
                statusColor  = '#f43f5e';
            } else if (p.location === `party_${selectedGameMode}`) {
                locationText = 'في وضع الجمعات 🎮';
                statusColor  = '#ff9800';
            }

            const div = document.createElement('div');
            div.className = 'online-player-item';
            if (userDataCache && p.name === userDataCache.player_name) div.classList.add('is-me');

            // نبني العنصر بـ DOM API لمنع XSS من بيانات اللاعبين
            const img = document.createElement('img');
            img.src       = getCorrectAvatarUrl(p.avatar);
            img.className = 'online-player-avatar';
            img.alt       = 'Avatar';

            const info     = document.createElement('div');
            info.className = 'online-player-info';

            const nameSpan     = document.createElement('span');
            nameSpan.className = 'online-player-name';
            nameSpan.textContent = sanitizeText(p.name);

            const statusSpan     = document.createElement('span');
            statusSpan.className = 'online-player-status';

            const dot = document.createElement('div');
            dot.className            = 'status-dot';
            dot.style.backgroundColor = sanitizeText(statusColor);

            const locSpan = document.createElement('span');
            locSpan.style.color  = sanitizeText(statusColor);
            locSpan.textContent  = sanitizeText(locationText);

            statusSpan.appendChild(dot);
            statusSpan.appendChild(locSpan);
            info.appendChild(nameSpan);
            info.appendChild(statusSpan);
            div.appendChild(img);
            div.appendChild(info);
            list.appendChild(div);
        });
    }

    socket.on('update_online_players', (allPlayers) => {
        // ✅ احفظ آخر snapshot دائماً
        lastPlayersSnapshot = allPlayers;
        // ارسم فقط لو userDataCache جاهز، وإلا يرسم بعدين
        renderLobbyPlayers(allPlayers);
    });

    socket.on('game_chat_history', (history) => {
        const container = document.getElementById('globalChatMessages');
        if (container) container.innerHTML = '';
        history.forEach(msg => addGlobalChatMessage(msg.sender, msg.text, msg.isSystem));
    });

    socket.on('new_game_chat_message', (msg) => {
        const safeSender = sanitizeText(msg.sender);
        const safeText   = sanitizeText(msg.text);

        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            const el = document.createElement('div');
            el.className = `chat-message ${msg.isSystem ? 'system' : ''}`;
            const senderSpan = document.createElement('span');
            senderSpan.className = 'sender';
            senderSpan.textContent = `${safeSender}:`;
            const textSpan = document.createElement('span');
            textSpan.className = 'text';
            textSpan.textContent = safeText;
            el.appendChild(senderSpan);
            el.appendChild(document.createTextNode(' '));
            el.appendChild(textSpan);
            chatMessages.appendChild(el);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        addGlobalChatMessage(msg.sender, msg.text, msg.isSystem);
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
    // 📱 زر الجمعات (الـ Party)
    // ----------------------------------------
    const localPartyBtn    = document.getElementById('localPartyBtn');
    const partyModeModal   = document.getElementById('partyModeModal');

    if (localPartyBtn) {
        localPartyBtn.style.display = selectedGameMode === 'huroof' ? 'flex' : 'none';
        localPartyBtn.addEventListener('click', () => {
            if (partyModeModal) partyModeModal.style.display = 'flex';
        });
    }

    // ----------------------------------------
    // 👤 جلب بيانات الحساب
    // ----------------------------------------
    try {
        const res = await fetch(`${API_URL}/auth/me?token=${token}`);
        if (!res.ok) {
            sessionStorage.removeItem('token');
            return window.location.replace('login.html');
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

        // ✅ إعادة رسم القائمة بعد تحميل بيانات المستخدم
        // (قد تكون update_online_players وصلت قبل userDataCache)
        if (lastPlayersSnapshot.length > 0) {
            renderLobbyPlayers(lastPlayersSnapshot);
        }

    } catch {
        showToast('خطأ في الاتصال بالسيرفر', 'error');
    }

    // الرجوع للساحة
    document.getElementById('backToCategoriesBtn')?.addEventListener('click', () => {
        window.location.replace('categories.html');
    });

    // ----------------------------------------
    // 🔔 التنبيهات
    // ----------------------------------------
    const notificationsBtn   = document.getElementById('notificationsBtn');
    const notificationsModal = document.getElementById('notificationsModal');
    const closeNotifications = document.getElementById('closeNotifications');

    notificationsBtn?.addEventListener('click', () => { notificationsModal.style.display = 'flex'; });
    closeNotifications?.addEventListener('click', () => { notificationsModal.style.display = 'none'; });

    // ----------------------------------------
    // ⚙️ الإعدادات
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
    // 🛡️ الأمان
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
    // 🖼️ تغيير الأفاتار
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
    // 💾 حفظ الملف الشخصي
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
    // 🔊 إعدادات الصوت
    // ----------------------------------------
    initVolumeControls();

    // ----------------------------------------
    // ⚡ اللعب السريع (Matchmaking)
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
        mmRadar.style.display            = 'block';
        mmTeamsPreview.style.display     = 'none';
        mmCountdown.style.display        = 'none';
        cancelMatchmakingBtn.style.display = 'block';
        mmStatusTitle.textContent = 'البحث عن منافس...';
        mmStatusDesc.textContent  = 'جاري البحث عن لاعبين في نفس مستواك';
        socket.emit('quick_play_search', {
            player_name: userDataCache.player_name,
            game_mode:   selectedGameMode,
            avatar:      userDataCache.avatar,
        });
    });

    cancelMatchmakingBtn?.addEventListener('click', () => {
        socket.emit('cancel_quick_play');
        matchmakingScreen.style.display = 'none';
        lobbyMainContent.style.display  = 'block';
    });

    socket.on('match_found', (data) => {
        try {
            sessionStorage.setItem('gameRoomCode', data.room_code);
            sessionStorage.setItem('myRole', data.role || 'guest');

            mmRadar.style.display          = 'none';
            mmTeamsPreview.style.display   = 'flex';
            cancelMatchmakingBtn.style.display = 'none';
            mmStatusTitle.textContent = 'تم إيجاد منافس!';
            mmStatusTitle.style.color = '#00ff88';
            mmStatusDesc.textContent  = 'الاستعداد للمعركة...';

            const players = Array.isArray(data.players)
                ? data.players
                : Object.values(data.players || {});

            players.forEach((p, i) => {
                const color = p.color || p.team || (i === 0 ? 'green' : 'orange');
                if (color === 'green') {
                    document.getElementById('mmGreenName').textContent = p.name || 'لاعب';
                    document.getElementById('mmGreenAvatar').src  = getCorrectAvatarUrl(p.avatar);
                } else {
                    document.getElementById('mmOrangeName').textContent = p.name || 'لاعب';
                    document.getElementById('mmOrangeAvatar').src = getCorrectAvatarUrl(p.avatar);
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
                    setTimeout(() => window.location.assign(`games/${selectedGameMode}.html`), 500);
                }
            }, 1000);

        } catch (err) {
            console.error('match_found error:', err);
            setTimeout(() => window.location.assign(`games/${selectedGameMode}.html`), 1000);
        }
    });

    // ----------------------------------------
    // 🎮 الغرف الخاصة
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
            const color      = sanitizeText(p.color || p.team || (i === 0 ? 'green' : 'orange'));
            const colorEmoji = color === 'green' ? '🟢' : '🟠';
            const themeColor = sanitizeText(GAME_THEMES[selectedGameMode]?.color || '#fff');
            const slot       = document.createElement('div');
            slot.className   = 'player-slot';

            const img = document.createElement('img');
            img.src = getCorrectAvatarUrl(p.avatar);
            img.style.cssText = `width:60px;height:60px;border-radius:50%;border:2px solid ${themeColor};margin-bottom:10px;object-fit:cover;`;

            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'color:#fff;font-size:14px;font-weight:bold;display:block;';
            nameSpan.textContent   = `${sanitizeText(p.name)} ${colorEmoji}`;

            slot.appendChild(img);
            slot.appendChild(nameSpan);
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
    // 💬 الدردشة
    // ----------------------------------------
    const sendBtn   = document.getElementById('sendGlobalChatBtn');
    const chatInput = document.getElementById('globalChatInput');

    sendBtn?.addEventListener('click', () => {
        const text = chatInput?.value.trim();
        if (text) {
            socket.emit('send_game_chat_message', { gameMode: selectedGameMode, sender: userDataCache.player_name, text });
            chatInput.value = '';
        }
    });
    chatInput?.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendBtn?.click(); });

    // ----------------------------------------
    // 📱 وضع الجمعات (Telegram Bot)
    // ----------------------------------------
    const generateBtn = document.getElementById('generateCodeBtn');
    const codeArea    = document.getElementById('codeDisplayArea');
    const codeText    = document.getElementById('secretCodeText');
    const timerText   = document.getElementById('timerText');

    generateBtn?.addEventListener('click', () => {
        socket.emit('generate_host_code', {});
        generateBtn.style.display = 'none';
        codeArea.style.display    = 'block';
        codeText.innerText        = 'جاري...';
        timerText.innerText       = 'يرجى الانتظار...';
        timerText.style.color     = 'red';
    });

    socket.on('receive_host_code', (data) => {
        codeText.innerText = data.code;

        let totalTime   = 20;
        let displayTime = 5;

        timerText.innerText   = `يختفي العرض بعد: ${displayTime}`;
        timerText.style.color = 'red';
        codeText.style.display = 'block';

        if (codeInterval) clearInterval(codeInterval);

        codeInterval = setInterval(() => {
            totalTime--;
            displayTime--;

            if (displayTime > 0) {
                timerText.innerText = `يختفي العرض بعد: ${displayTime}`;
            } else if (displayTime === 0) {
                codeText.innerText    = '****';
                timerText.innerText   = `الرمز فعال لمدة ${totalTime} ثانية...`;
                timerText.style.color = '#bbb';
            } else if (totalTime > 0) {
                timerText.innerText = `الرمز فعال لمدة ${totalTime} ثانية...`;
            } else {
                clearInterval(codeInterval);
                codeText.innerText    = '❌';
                timerText.innerText   = 'انتهت صلاحية الرمز!';
                timerText.style.color = 'red';
                setTimeout(() => {
                    if (generateBtn) generateBtn.style.display = 'block';
                    if (codeArea)    codeArea.style.display    = 'none';
                }, 2000);
            }
        }, 1000);
    });

    socket.on('host_linked_success', () => {
        if (codeInterval) clearInterval(codeInterval);
        if (partyModeModal) {
            partyModeModal.innerHTML = '';
            const box = document.createElement('div');
            box.style.cssText = 'background:#1a1a2e;padding:40px;border-radius:20px;color:white;width:90%;max-width:500px;box-shadow:0 0 30px rgba(0,255,136,0.5);border:2px solid #00ff88;';

            const icon = document.createElement('h1');
            icon.style.cssText = 'color:#00ff88;font-size:60px;margin:0;';
            icon.textContent   = '✅';

            const title = document.createElement('h2');
            title.style.cssText = 'color:white;margin-top:10px;';
            title.textContent   = 'تم ربط المضيف بنجاح!';

            const sub = document.createElement('p');
            sub.style.color  = '#bbb';
            sub.textContent  = 'تبدأ اللعبة الآن...';

            box.appendChild(icon);
            box.appendChild(title);
            box.appendChild(sub);
            partyModeModal.appendChild(box);

            setTimeout(() => {
                partyModeModal.style.display = 'none';
                window.location.href = 'games/huroof_party.html';
            }, 2000);
        }
    });

    // ----------------------------------------
    // 🖱️ إغلاق النوافذ عند النقر خارجها
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