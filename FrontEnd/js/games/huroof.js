// ============================================================
// games/huroof.js — لعبة حروف (المباراة المباشرة)
// المتطلبات: config.js → utils.js (يوفر API_URL, sanitizeHTML, getToken)
// ============================================================

// دالة مساعدة: تضع أيقونة FontAwesome ونصاً في زر بدون innerHTML
function setButtonWithIcon(btn, iconClass, label) {
    if (!btn) return;
    btn.innerHTML = '';
    const i = document.createElement('i');
    i.className = iconClass;
    btn.appendChild(i);
    btn.appendChild(document.createTextNode(' ' + label));
}

// ============================================================
// 🚀 الاتصال والجلسة
// ============================================================
const socket = io(API_URL, { transports: ['websocket'], upgrade: false });

const token        = getToken();
const playerName   = sessionStorage.getItem('playerName')   || sessionStorage.getItem('username')   || 'لاعب';
const playerAvatar = sessionStorage.getItem('playerAvatar') || sessionStorage.getItem('avatar')     || '';
const roomCode     = sessionStorage.getItem('gameRoomCode');

if (!token || !roomCode) window.location.href = '../lobby.html';


// ============================================================
// 🧱 بناء لوحة السداسيات
// ============================================================
const honeycomb = document.querySelector('.honeycomb');
if (honeycomb && honeycomb.children.length === 0) {
    for (let i = 0; i < 25; i++) {
        const hex = document.createElement('div');
        hex.className     = 'hex';
        hex.dataset.index = i;
        honeycomb.appendChild(hex);
    }
}


// ============================================================
// 🖥️ مراجع عناصر الواجهة
// ============================================================
const cells                = document.querySelectorAll('.hex');
const currentLetterDisplay = document.getElementById('currentLetterDisplay');
const systemMessageDisplay = document.getElementById('systemMessageDisplay');
const globalTimerDisplay   = document.getElementById('globalTimer');
const playerTimerDisplay   = document.getElementById('playerTimer');
const buzzerBtn            = document.getElementById('buzzerBtn');
const answerSection        = document.getElementById('answerSection');
const playerAnswerInput    = document.getElementById('playerAnswerInput');
const submitAnswerBtn      = document.getElementById('submitAnswerBtn');
const voteSkipBtn          = document.getElementById('voteSkipBtn');


// ============================================================
// 📊 حالة اللعبة
// ============================================================
let myColor             = null;
let currentTurnSid      = null;
let activeHexIndex      = null;
let isMyTurnToAnswer    = false;
let globalTimerInterval = null;
let playerTimerInterval = null;

// ✅ متغيرات التزامن — تضمن الترتيب الصحيح لأحداث البداية
let _roomJoinedReceived = false;  // هل وصل room_joined؟
let _pendingTurnSid     = null;   // الدور المنتظر إذا وصل new_round قبل room_joined
let _pendingBoard       = null;   // اللوحة المنتظرة إذا وصلت قبل room_joined

let playersStatsData = {
    me: {
        name: 'أنت', avatar: '../assets/avatars/avatar_1.svg',
        flag: '../assets/flags/SA.svg', rank: '--',
        huroof: { wins: 0, losses: 0, total: 0 },
        global:  { wins: 0, losses: 0, total: 0 },
        color: 'green',
    },
    opponent: {
        name: 'الخصم', avatar: '../assets/avatars/avatar_2.svg',
        flag: '../assets/flags/AE.svg', rank: '--',
        huroof: { wins: 0, losses: 0, total: 0 },
        global:  { wins: 0, losses: 0, total: 0 },
        color: 'orange',
    },
};

// التحديث الفوري: وضع بيانات اللاعب المحلي فور تحميل الصفحة
playersStatsData.me.name = playerName;
playersStatsData.me.avatar = getValidAvatarSrc(playerAvatar);
document.getElementById('myPlayerName').textContent = playerName;
document.getElementById('myAvatarImg').src = playersStatsData.me.avatar;

// وضع حالة تحميل مبدئية للخصم حتى تأتي بياناته من السيرفر
document.getElementById('opponentName').textContent = 'جاري البحث...';
document.getElementById('opponentAvatarImg').style.opacity = '0.5';

// ============================================================
// 🛠️ مسار الأفاتار (خاص بمجلد games/ حيث المسار ../../)
// ============================================================
function getValidAvatarSrc(avatarValue) {
    if (!avatarValue || avatarValue.trim() === '') return '../assets/avatars/avatar_1.svg';
    if (avatarValue.startsWith('http') || avatarValue.startsWith('data:')) return avatarValue;
    if (avatarValue.startsWith('/uploads')) return `${API_URL}${avatarValue}`;
    const name = avatarValue.split('/').pop();
    return `../assets/avatars/${name.includes('.') ? name : name + '.svg'}`;
}


// ============================================================
// 🔌 الاتصال والانضمام للغرفة
// ============================================================
// =========================================================
// 🚀 إرسال إشارة الجاهزية للسيرفر بشكل محصّن (يمنع التكرار)
// =========================================================
let isReadySignalSent = false;

function sendReadySignal() {
    if (isReadySignalSent) return; 
    
    const roomId = sessionStorage.getItem('gameRoomCode');
    const pName = sessionStorage.getItem('playerName') || sessionStorage.getItem('username') || localStorage.getItem('playerName');
    const pAvatar = sessionStorage.getItem('playerAvatar') || sessionStorage.getItem('avatar') || ''; 
    
    if (roomId && pName) {
        console.log("🚀 جاري إرسال إشارة الجاهزية للسيرفر...");
        
        // 💡 حل مشكلة "التأخير الوهمي": إظهار رسالة فورية ليعلم اللاعب أنه ينتظر الخصم فقط
        const sysMsg = document.getElementById('systemMessageDisplay');
        if (sysMsg) {
            sysMsg.textContent = '⏳ جاري انتظار دخول الخصم للمباراة...';
            sysMsg.style.color = '#FF9800';
        }

        socket.emit('huroof_player_ready', { 
            roomId: roomId, 
            roomCode: roomId,
            playerName: pName,
            avatar: pAvatar // 👈 إرسال الصورة الطازجة للسيرفر
        });
        isReadySignalSent = true;
    }
}

// 💡 تأمين الاتصال: نرسل الإشارة إذا كان متصلاً، وننتظر إذا لم يكن
if (socket.connected) {
    sendReadySignal();
}
socket.on('connect', () => {
    // ✅ إعادة تعيين متغيرات التزامن عند كل اتصال جديد
    _roomJoinedReceived = false;
    _pendingTurnSid     = null;
    _pendingBoard       = null;
    sendReadySignal();
});

socket.on('room_joined', (data) => {
    const me       = data.players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = data.players.find(p => p.sid !== socket.id && p.name !== playerName);

    if (me) {
        // ✅ تحديد اللون فوراً — اللعبة تبدأ هنا
        myColor = me.color;
        const gameTitle = document.querySelector('.game-title');
        if (gameTitle) {
            gameTitle.textContent = `حروف - أنت اللاعب ${myColor === 'green' ? 'الأخضر 🟢' : 'البرتقالي 🟠'}`;
            gameTitle.style.color = myColor === 'green' ? '#4CAF50' : '#FF9800';
        }
        // بيانات أساسية فورية (بدون إحصائيات)
        playersStatsData.me.name   = me.name   || playerName;
        playersStatsData.me.avatar = getValidAvatarSrc(me.avatar || playerAvatar);
        playersStatsData.me.color  = me.color;
    }
    if (opponent) {
        playersStatsData.opponent.name   = opponent.name   || 'الخصم';
        playersStatsData.opponent.avatar = getValidAvatarSrc(opponent.avatar || '');
        playersStatsData.opponent.color  = opponent.color;
        document.getElementById('opponentName').textContent = opponent.name || 'الخصم';
        document.getElementById('opponentAvatarImg').style.opacity = '1';
        if (opponent.avatar) document.getElementById('opponentAvatarImg').src = getValidAvatarSrc(opponent.avatar);
    }
    updateTopBarUI();

    // ✅ تمييز أننا استقبلنا room_joined
    _roomJoinedReceived = true;

    // ✅ إذا كانت اللوحة وصلت قبلنا، ارسمها الآن
    if (_pendingBoard) {
        const boardData = _pendingBoard;
        _pendingBoard = null;
        requestAnimationFrame(() => {
            boardData.forEach((hexData, index) => {
                if (cells[index]) {
                    cells[index].textContent = hexData.letter;
                    cells[index].dataset.index = hexData.index ?? index;
                    cells[index].classList.remove('active', 'green', 'orange');
                    if (hexData.color) cells[index].classList.add(hexData.color);
                }
            });
        });
    }

    // ✅ إذا كان الدور وصل قبلنا، طبّقه الآن
    if (_pendingTurnSid !== null) {
        currentTurnSid = _pendingTurnSid;
        _pendingTurnSid = null;
        document.getElementById('waiting-overlay').style.display = 'none';
        resetUIForNewTurn();
    }

    // تفعيل التفاعل مباشرة
    applyTurnUI();
});

socket.on('update_players_stats', (players) => {
    // الإحصائيات تصل لاحقاً من DB — نحدث بصمت بدون إعادة رسم اللوحة
    const me       = players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = players.find(p => p.sid !== socket.id && p.name !== playerName);
    if (me?.stats) {
        const freshMyAvatar = playerAvatar || me.stats.avatar;
        playersStatsData.me = { ...playersStatsData.me, ...me.stats, color: me.color, avatar: getValidAvatarSrc(freshMyAvatar) };
    }
    if (opponent?.stats) {
        playersStatsData.opponent = { ...playersStatsData.opponent, ...opponent.stats, color: opponent.color, avatar: getValidAvatarSrc(opponent.stats.avatar) };
    }
    updateTopBarUI();
});


// ============================================================
// 🎮 أحداث السيرفر — سير اللعبة
// ============================================================

socket.on('huroof_board_init', (data) => {
    console.log("🎨 استلام اللوحة، جاري الرسم...");
    
    const roundsDisplay = document.getElementById('rounds-display');
    if (roundsDisplay) roundsDisplay.style.display = 'flex';

    const sidebar = document.getElementById('questionSidebar');
    if (sidebar) {
        Object.assign(sidebar.style, { display: 'flex', visibility: 'visible', opacity: '1', pointerEvents: 'auto' });
        sidebar.classList.add('active');
    }
    const qText = document.getElementById('questionText');
    if (qText) {
        qText.innerHTML = '';
        const strong = document.createElement('strong');
        strong.textContent = '⏳ جاري تحضير الجولة...';
        qText.appendChild(strong);
        qText.style.display = 'block';
    }

    if (typeof systemMessageDisplay !== 'undefined') {
        systemMessageDisplay.textContent = 'اكتمل الاتصال! المعركة تبدأ الآن ⚔️';
        systemMessageDisplay.style.color = '#00ff88';
    }

    // 🚀 إذا وصل board_init قبل room_joined، نعرض اسم الخصم فوراً من بيانات الغرفة
    if (data.players) {
        const opp = data.players.find(p => p.name !== playerName);
        if (opp && document.getElementById('opponentName').textContent === 'جاري البحث...') {
            document.getElementById('opponentName').textContent = opp.name || 'الخصم';
            document.getElementById('opponentAvatarImg').style.opacity = '1';
            if (opp.avatar) document.getElementById('opponentAvatarImg').src = getValidAvatarSrc(opp.avatar);
        }
    }

    // ✅ إذا لم يصل room_joined بعد، احفظ اللوحة وارسمها بعد ما يصل
    if (!_roomJoinedReceived) {
        _pendingBoard = data.board;
        return;
    }

    requestAnimationFrame(() => {
        data.board.forEach((hexData, index) => {
            if (cells[index]) {
                cells[index].textContent = hexData.letter;
                cells[index].dataset.index = hexData.index ?? index;  // ✅ استخدام index من السيرفر
                cells[index].classList.remove('active', 'green', 'orange');
                if (hexData.color) cells[index].classList.add(hexData.color);
            }
        });
    });
});

socket.on('huroof_turn_changed', (data) => {
    currentTurnSid = data.turn_sid;
    resetUIForNewTurn();
    applyTurnUI();
});

socket.on('huroof_hex_locked', (data) => {
    activeHexIndex = data.hexIndex;
    cells[activeHexIndex].classList.add('active');
    currentLetterDisplay.textContent = `حرف ( ${data.letter} )`;
    currentLetterDisplay.style.color = '#FFF';
});

socket.on('huroof_new_question', (data) => {
    // ✅ إصلاح ٣: تحديث currentTurnSid من السيرفر حتى تعرف الواجهة من يملك الدور
    if (data.current_turn_sid) {
        currentTurnSid = data.current_turn_sid;
    }

    const sidebar = document.getElementById('questionSidebar');
    if (sidebar) {
        Object.assign(sidebar.style, { display: 'flex', visibility: 'visible', opacity: '1', pointerEvents: 'auto' });
        sidebar.classList.add('active');
    }

    const qText = document.getElementById('questionText');
    if (qText) qText.innerHTML = sanitizeHTML(data.questionData.question);

    // ✅ إصلاح ١: تفعيل زر "أنا أعرف" فقط لو السؤال وصل وكل شيء جاهز
    buzzerBtn.style.display  = 'block';
    buzzerBtn.disabled       = false;
    buzzerBtn.style.opacity  = '1';
    isMyTurnToAnswer = false;  // ← إعادة تعيين مهمة لمنع إرسال إجابة قديمة
    systemMessageDisplay.textContent = '';

    if (voteSkipBtn) {
        voteSkipBtn.style.display    = 'inline-block';
        voteSkipBtn.disabled         = false;
        setButtonWithIcon(voteSkipBtn, 'fa-solid fa-forward-step', 'اقتراح تغيير السؤال');
        voteSkipBtn.style.background = '#607d8b';
    }

    document.getElementById('answer-container').style.display = 'none';
    answerSection.style.display      = 'none';
    submitAnswerBtn.disabled         = false;  // ← إعادة تفعيل زر الإرسال
    playerAnswerInput.value          = '';     // ← مسح الإجابة القديمة
    globalTimerDisplay.style.display = 'block';
    startGlobalTimer(data.timer);
});

socket.on('huroof_buzzed', (data) => {
    clearInterval(globalTimerInterval);
    globalTimerDisplay.style.display = 'none';
    buzzerBtn.style.display          = 'none';
    if (voteSkipBtn) voteSkipBtn.style.display = 'none';

    const timeValue = parseInt(data.time || data.timer);
    if (isNaN(timeValue)) return;

    if (data.sid === socket.id) {
        isMyTurnToAnswer = true;
        submitAnswerBtn.disabled = false;  // ✅ تأكد من تفعيل الزر
        systemMessageDisplay.textContent = 'أسرع! اكتب إجابتك...';
        systemMessageDisplay.style.color = '#4CAF50';
        answerSection.style.display      = 'block';
        playerAnswerInput.value          = '';
        playerAnswerInput.focus();
        console.log('🎯 دورك للإجابة! isMyTurnToAnswer =', isMyTurnToAnswer);
    } else {
        isMyTurnToAnswer = false;
        systemMessageDisplay.textContent = 'الخصم يجيب الآن... استعد في حال أخطأ!';
        systemMessageDisplay.style.color = '#FF9800';
        answerSection.style.display      = 'none';
        console.log('⏳ دور الخصم للإجابة');
    }
    startPlayerTimer(timeValue);
});

socket.on('huroof_chance_transfer', (data) => {
    clearInterval(playerTimerInterval);
    if (data.to_sid === socket.id) {
        isMyTurnToAnswer = true;
        systemMessageDisplay.textContent = 'أخطأ الخصم! فرصتك الآن...';
        systemMessageDisplay.style.color = '#4CAF50';
        answerSection.style.display      = 'block';
        playerAnswerInput.value          = '';
        playerAnswerInput.focus();
    } else {
        isMyTurnToAnswer = false;
        systemMessageDisplay.textContent = 'أخطأت! فرصة الخصم الآن...';
        systemMessageDisplay.style.color = '#FF9800';
        answerSection.style.display      = 'none';
    }
    startPlayerTimer(data.timer);
});

socket.on('huroof_last_chance', (data) => {
    clearInterval(playerTimerInterval);
    systemMessageDisplay.textContent = '🚨 الفرصة الأخيرة! من يضغط أولاً؟';
    systemMessageDisplay.style.color = '#f44336';
    answerSection.style.display      = 'none';
    buzzerBtn.style.display          = 'block';
    buzzerBtn.disabled               = false;
    buzzerBtn.style.opacity          = '1';
    if (voteSkipBtn) {
        voteSkipBtn.style.display    = 'inline-block';
        voteSkipBtn.disabled         = false;
        setButtonWithIcon(voteSkipBtn, 'fa-solid fa-forward-step', 'اقتراح تغيير السؤال');
        voteSkipBtn.style.background = '#607d8b';
    }
    startGlobalTimer(data.timer);
});

socket.on('huroof_answer_result', (data) => {
    clearInterval(playerTimerInterval);
    const cell = cells[data.hexIndex];
    if (data.correct) {
        if (cell) { cell.classList.remove('active'); cell.classList.add(data.color); }
        systemMessageDisplay.textContent = `✅ إجابة صحيحة! (${sanitizeText(data.answer)})`;
        systemMessageDisplay.style.color = '#4CAF50';
        buzzerBtn.style.display          = 'none';
        answerSection.style.display      = 'none';
        if (voteSkipBtn) voteSkipBtn.style.display = 'none';
    } else {
        systemMessageDisplay.textContent = `❌ إجابة خاطئة: ${sanitizeText(data.answer)}`;
        systemMessageDisplay.style.color = '#f44336';
    }
});

socket.on('huroof_timeout_info', (data) => {
    clearInterval(globalTimerInterval);
    clearInterval(playerTimerInterval);
    systemMessageDisplay.textContent = sanitizeHTML(data.msg);
    systemMessageDisplay.style.color = '#ff9800';
    buzzerBtn.style.display          = 'none';
    answerSection.style.display      = 'none';
    if (voteSkipBtn) voteSkipBtn.style.display = 'none';
});

socket.on('huroof_skip_voted', (data) => {
    if (data.sid === socket.id && voteSkipBtn) {
        setButtonWithIcon(voteSkipBtn, 'fa-solid fa-check', 'بانتظار الخصم...');
        voteSkipBtn.style.background = '#4CAF50';
        voteSkipBtn.disabled         = true;
    }
});

socket.on('error_message', (msg) => {
    systemMessageDisplay.textContent = `⚠️ ${sanitizeHTML(msg)}`;
    systemMessageDisplay.style.color = '#f44336';
    if (currentTurnSid === socket.id && activeHexIndex !== null) {
        cells[activeHexIndex].classList.remove('active');
        activeHexIndex = null;
    }
});


// ============================================================
// 🎯 نظام الجولات (Best of 3)
// ============================================================

socket.on('huroof_round_over', (data) => {
    updateRoundsUI(data.points, data.next_round);
    resetUIForNewTurn();

    const teamName       = data.winner === 'green' ? 'الأخضر 🟢' : 'البرتقالي 🟠';
    const winnerColor    = data.winner === 'green' ? '#2ecc71' : '#ff9800';
    const waitingOverlay = document.getElementById('waiting-overlay');
    if (waitingOverlay) {
        waitingOverlay.style.display = 'flex';
        const overlayMsg = document.getElementById('overlay-message');
        overlayMsg.innerHTML = '';
        const h2 = document.createElement('h2');
        h2.style.color        = sanitizeText(winnerColor);
        h2.style.marginBottom = '10px';
        h2.style.fontFamily   = "'Tajawal',sans-serif";
        h2.textContent        = `فاز اللاعب ${sanitizeText(teamName)} بالجولة!`;
        const p = document.createElement('p');
        p.textContent = 'استعد للجولة القادمة...';
        overlayMsg.appendChild(h2);
        overlayMsg.appendChild(p);
        document.querySelector('.spinner').style.display = 'block';
    }
});

socket.on('huroof_new_round_started', (data) => {
    // ✅ إذا لم يصل room_joined بعد (myColor لا يزال null)، احفظ الدور وانتظر
    if (!_roomJoinedReceived) {
        _pendingTurnSid = data.turn;
        return;
    }
    document.getElementById('waiting-overlay').style.display = 'none';
    currentTurnSid = data.turn;
    resetUIForNewTurn();
    applyTurnUI();
});

socket.on('huroof_match_over', (data) => {
    updateRoundsUI(data.points);
    const isIWinner  = data.winner === myColor;
    const winnerName = isIWinner ? playersStatsData.me.name : playersStatsData.opponent.name;

    document.getElementById('winner-color').textContent  = winnerName;
    document.getElementById('winner-color').style.color  = data.winner === 'green' ? '#4CAF50' : '#FF9800';
    document.getElementById('winner-reason').textContent =
        data.reason === 'surrender' ? 'بسبب انسحاب الخصم 🏳️' : 'بتحقيق نقطتي الفوز 🏆';
    document.getElementById('winner-overlay').style.display = 'flex';
});

socket.on('show_winner', (data) => {
    const winnerName = data.color === myColor ? playersStatsData.me.name : playersStatsData.opponent.name;
    document.getElementById('winner-color').textContent  = winnerName;
    document.getElementById('winner-color').style.color  = data.color === 'green' ? '#4CAF50' : '#FF9800';
    document.getElementById('winner-reason').textContent = 'بسبب انسحاب الخصم 🏳️';
    document.getElementById('winner-overlay').style.display = 'flex';
});

socket.on('opponent_disconnected', (data) => {
    Swal.fire({
        title: 'انقطع الاتصال!',
        html:  `<b>${data.msg}</b><br><small>أمام الخصم 30 ثانية للعودة قبل إعلان انسحابه.</small>`,
        icon:  'warning',
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => Swal.showLoading(),
    });
});

socket.on('opponent_reconnected', () => {
    Swal.close();
    Swal.fire({ title: 'عاد الخصم!', text: 'تمت استعادة الاتصال، استعد للمتابعة...', icon: 'success', timer: 2000, showConfirmButton: false });
});

// ✅ إضافة handler جديد للانتظار
socket.on('huroof_waiting_opponent', (data) => {
    const overlay = document.getElementById('waiting-overlay');
    if (overlay) {
        overlay.style.display = 'flex';
        const overlayMsg = document.getElementById('overlay-message');
        if (overlayMsg) {
            overlayMsg.innerHTML = '';
            const h2 = document.createElement('h2');
            h2.style.color = '#FF9800';
            h2.style.fontFamily = "'Tajawal',sans-serif";
            h2.textContent = '⏳ في انتظار دخول الخصم...';
            overlayMsg.appendChild(h2);
        }
        const spinner = document.querySelector('.spinner');
        if (spinner) spinner.style.display = 'block';
    }
    // إخفاء أي نص دور حتى يدخل الخصم
    if (currentLetterDisplay) {
        currentLetterDisplay.textContent = 'في انتظار الخصم...';
        currentLetterDisplay.style.color = '#FF9800';
    }
});


// ============================================================
// 🖱️ تفاعلات اللاعب
// ============================================================

// ✅ إصلاح: تعيين data-index لكل خلية عند التحميل (للخلايا المبنية في HTML)
document.querySelectorAll('.hex').forEach((cell, index) => {
    if (!cell.dataset.index) cell.dataset.index = index;
});

cells.forEach((cell, index) => {
    cell.addEventListener('click', () => {
        const hexIndex = parseInt(cell.dataset.index ?? index);
        if (
            currentTurnSid === socket.id &&
            !cell.classList.contains('green') &&
            !cell.classList.contains('orange') &&
            !cell.classList.contains('active')
        ) {
            socket.emit('huroof_select_hex', { roomCode, hexIndex: hexIndex });
        }
    });
});

buzzerBtn.addEventListener('click', () => {
    if (!buzzerBtn.disabled) {
        buzzerBtn.disabled      = true;
        buzzerBtn.style.opacity = '0.5';
        socket.emit('huroof_buzz', { roomCode });
    }
});

function submitAnswer() {
    console.log('📤 submitAnswer called | isMyTurnToAnswer:', isMyTurnToAnswer, '| ans:', playerAnswerInput.value.trim());
    if (!isMyTurnToAnswer) {
        console.warn('⚠️ ليس دورك للإجابة — isMyTurnToAnswer = false');
        return;
    }
    const ans = playerAnswerInput.value.trim();
    if (!ans) {
        console.warn('⚠️ الإجابة فارغة');
        return;
    }
    isMyTurnToAnswer         = false;
    submitAnswerBtn.disabled = true;
    console.log('✅ إرسال الإجابة:', ans, '| roomCode:', roomCode);
    socket.emit('huroof_submit_answer', { roomCode, answer: ans });
}

submitAnswerBtn.addEventListener('click', submitAnswer);
playerAnswerInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') submitAnswer(); });
voteSkipBtn?.addEventListener('click', () => { if (!voteSkipBtn.disabled) socket.emit('huroof_vote_skip', { roomCode }); });


// ============================================================
// 🚪 الانسحاب
// ============================================================
const surrenderModal = document.getElementById('surrenderModal');
const leaveBtn       = document.querySelector('.surrender-btn') || document.querySelector('a[href*="lobby"]');

leaveBtn?.addEventListener('click', (e) => { e.preventDefault(); surrenderModal.style.display = 'flex'; });

document.getElementById('cancelSurrenderBtn').onclick = () => { surrenderModal.style.display = 'none'; };

document.getElementById('confirmSurrenderBtn').onclick = () => {
    surrenderModal.style.display = 'none';
    socket.emit('huroof_surrender', { roomCode });
    sessionStorage.removeItem('gameRoomCode');

    const opponentColor = myColor === 'green' ? 'orange' : 'green';
    document.getElementById('winner-color').textContent  = playersStatsData.opponent.name || (opponentColor === 'green' ? 'الأخضر' : 'البرتقالي');
    document.getElementById('winner-color').style.color  = opponentColor === 'green' ? '#4CAF50' : '#FF9800';
    document.getElementById('winner-reason').textContent = 'انسحبت من المباراة';
    document.getElementById('winner-overlay').style.display = 'flex';
};


// ============================================================
// 👤 الشريط العلوي والملف الشخصي
// ============================================================

function updateTopBarUI() {
    document.getElementById('myPlayerName').textContent  = playersStatsData.me.name;
    document.getElementById('myAvatarImg').src           = playersStatsData.me.avatar;
    document.getElementById('myFlagImg').src             = playersStatsData.me.flag;
    document.querySelector('#myColorIndicator .color-circle').className = `color-circle ${playersStatsData.me.color}-team`;

    document.getElementById('opponentName').textContent     = playersStatsData.opponent.name;
    document.getElementById('opponentAvatarImg').src        = playersStatsData.opponent.avatar;
    document.getElementById('opponentAvatarImg').style.opacity = '1'; // <--- أضف هذا السطر
    document.getElementById('opponentFlagImg').src          = playersStatsData.opponent.flag;
    document.querySelector('#opponentColorIndicator .color-circle').className = `color-circle ${playersStatsData.opponent.color}-team`;
}

function openProfileModal(isMe) {
    const data  = isMe ? playersStatsData.me : playersStatsData.opponent;
    const modal = document.getElementById('playerProfileModal');
    document.getElementById('modalAvatar').src            = data.avatar;
    document.getElementById('modalPlayerName').textContent = data.name;
    document.getElementById('modalFlag').src              = data.flag;
    document.getElementById('rankValue').textContent      = data.rank;
    document.getElementById('huroofWins').textContent     = data.huroof.wins;
    document.getElementById('huroofLosses').textContent   = data.huroof.losses;
    document.getElementById('huroofTotal').textContent    = data.huroof.total;
    document.getElementById('globalWins').textContent     = data.global.wins;
    document.getElementById('globalLosses').textContent   = data.global.losses;
    document.getElementById('globalTotal').textContent    = data.global.total;
    document.getElementById('modalActionButtons').style.display = isMe ? 'none' : 'flex';
    modal.style.display = 'flex';
}

document.getElementById('myProfileBtn')?.addEventListener('click', () => openProfileModal(true));
document.getElementById('opponentProfileBtn')?.addEventListener('click', () => openProfileModal(false));
document.getElementById('closeProfileBtn')?.addEventListener('click', () => {
    document.getElementById('playerProfileModal').style.display = 'none';
});
document.getElementById('playerProfileModal')?.addEventListener('click', (e) => {
    if (e.target === document.getElementById('playerProfileModal')) {
        document.getElementById('playerProfileModal').style.display = 'none';
    }
});


// ============================================================
// ⏱️ المؤقتات والواجهة
// ============================================================

function startGlobalTimer(seconds) {
    clearInterval(globalTimerInterval);
    globalTimerDisplay.style.display = 'block';
    globalTimerDisplay.textContent   = `⏳ ${seconds}`;
    let left = seconds;
    globalTimerInterval = setInterval(() => {
        left--;
        globalTimerDisplay.textContent = `⏳ ${left}`;
        if (left <= 0) clearInterval(globalTimerInterval);
    }, 1000);
}

function startPlayerTimer(seconds) {
    clearInterval(playerTimerInterval);
    playerTimerDisplay.textContent = `⏱️ ${seconds}`;
    let left = seconds;
    playerTimerInterval = setInterval(() => {
        left--;
        playerTimerDisplay.textContent = `⏱️ ${left}`;
        if (left <= 0) clearInterval(playerTimerInterval);
    }, 1000);
}

/** يُطبّق شكل الواجهة بناءً على من يملك الدور الحالي */
function applyTurnUI() {
    const turnBadge = document.getElementById('turn-status-badge');
    if (currentTurnSid === socket.id) {
        currentLetterDisplay.textContent = 'دورك! اختر حرفاً من اللوحة';
        currentLetterDisplay.style.color = '#4CAF50';
        if (turnBadge) turnBadge.textContent = 'دورك الآن';
        cells.forEach(cell => {
            cell.style.cursor = (!cell.classList.contains('green') && !cell.classList.contains('orange'))
                ? 'pointer' : 'not-allowed';
        });
    } else {
        currentLetterDisplay.textContent = 'دور الخصم لاختيار حرف...';
        currentLetterDisplay.style.color = '#FF9800';
        if (turnBadge) turnBadge.textContent = 'دور الخصم';
        cells.forEach(cell => cell.style.cursor = 'not-allowed');
    }
}

/** يُعيد الواجهة لحالة الحياد بين الأدوار */
function resetUIForNewTurn() {
    activeHexIndex   = null;
    isMyTurnToAnswer = false;
    clearInterval(globalTimerInterval);
    clearInterval(playerTimerInterval);
    cells.forEach(c => c.classList.remove('active'));

    const sidebar = document.getElementById('questionSidebar');
    if (sidebar) {
        Object.assign(sidebar.style, { display: 'flex', visibility: 'visible', opacity: '1', pointerEvents: 'auto' });
        sidebar.classList.add('active');
    }

    const qText = document.getElementById('questionText');
    if (qText) {
        qText.innerHTML = '';
        const qStrong = document.createElement('strong');
        qStrong.textContent = currentTurnSid === socket.id
            ? 'دورك! اختر حرفاً من اللوحة للبدء.'
            : 'دور الخصم لاختيار حرف...';
        const qEmoji = document.createTextNode(currentTurnSid === socket.id ? '🎯 ' : '⏳ ');
        qText.appendChild(qEmoji);
        qText.appendChild(qStrong);
        qText.style.display = 'block';
    }

    globalTimerDisplay.style.display = 'none';
    buzzerBtn.style.display          = 'none';
    buzzerBtn.disabled               = false;
    buzzerBtn.style.opacity          = '1';
    answerSection.style.display      = 'none';
    if (voteSkipBtn) voteSkipBtn.style.display = 'none';
    document.getElementById('answer-container').style.display = 'none';
    systemMessageDisplay.textContent = '';
    submitAnswerBtn.disabled         = false;
}

function updateRoundsUI(points, currentRound) {
    // ✅ إعادة ضبط جميع النقاط أولاً قبل الرسم لمنع تراكم الألوان
    document.querySelectorAll('#team-green-score .score-dot').forEach(dot => dot.classList.remove('won'));
    document.querySelectorAll('#team-orange-score .score-dot').forEach(dot => dot.classList.remove('won'));

    document.querySelectorAll('#team-green-score .score-dot').forEach((dot, i) => {
        if (i < points.green) dot.classList.add('won');
    });
    document.querySelectorAll('#team-orange-score .score-dot').forEach((dot, i) => {
        if (i < points.orange) dot.classList.add('won');
    });
    if (currentRound) {
        const indicator = document.getElementById('round-indicator');
        indicator.textContent = `الجولة ${currentRound}`;
        indicator.classList.remove('round-animate');
        void indicator.offsetWidth; // إعادة تشغيل الأنيميشن
        indicator.classList.add('round-animate');
    }
}


// ============================================================
// ✨ تأثيرات بصرية
// ============================================================
function createStars() {
    const container = document.getElementById('stars');
    if (!container) return;
    for (let i = 0; i < 150; i++) {
        const star = document.createElement('div');
        star.className = 'star' + (Math.random() > 0.3 ? ' purple' : '');
        star.style.cssText = `left:${Math.random()*100}%;top:${Math.random()*100}%;animation-delay:${Math.random()*2}s;`;
        container.appendChild(star);
    }
}

createStars();