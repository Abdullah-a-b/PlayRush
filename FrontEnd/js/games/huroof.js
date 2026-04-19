// ============================================================
// games/huroof.js — لعبة حروف (المباراة المباشرة)
// المتطلبات: config.js → utils.js (يوفر API_URL, sanitizeHTML, getToken)
// ============================================================


// ============================================================
// 🚀 الاتصال والجلسة
// ============================================================
const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });

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

let playersStatsData = {
    me: {
        name: 'أنت', avatar: '../../assets/avatars/avatar_1.svg',
        flag: '../../assets/flags/SA.svg', rank: '--',
        huroof: { wins: 0, losses: 0, total: 0 },
        global:  { wins: 0, losses: 0, total: 0 },
        color: 'green',
    },
    opponent: {
        name: 'الخصم', avatar: '../../assets/avatars/avatar_2.svg',
        flag: '../../assets/flags/AE.svg', rank: '--',
        huroof: { wins: 0, losses: 0, total: 0 },
        global:  { wins: 0, losses: 0, total: 0 },
        color: 'orange',
    },
};


// ============================================================
// 🛠️ مسار الأفاتار (خاص بمجلد games/ حيث المسار ../../)
// ============================================================
function getValidAvatarSrc(avatarValue) {
    if (!avatarValue || avatarValue.trim() === '') return '../../assets/avatars/avatar_1.svg';
    if (avatarValue.startsWith('http') || avatarValue.startsWith('data:')) return avatarValue;
    if (avatarValue.startsWith('/uploads')) return `${API_URL}${avatarValue}`;
    const name = avatarValue.split('/').pop();
    return `../../assets/avatars/${name.includes('.') ? name : name + '.svg'}`;
}


// ============================================================
// 🔌 الاتصال والانضمام للغرفة
// ============================================================
socket.on('connect', () => {
    socket.emit('join_room', { room_code: roomCode, token, player_name: playerName, avatar: playerAvatar });
});

socket.on('room_joined', (data) => {
    const me       = data.players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = data.players.find(p => p.sid !== socket.id && p.name !== playerName);

    if (me) {
        myColor = me.color;
        const gameTitle = document.querySelector('.game-title');
        if (gameTitle) {
            gameTitle.textContent = `حروف - أنت اللاعب ${myColor === 'green' ? 'الأخضر 🟢' : 'البرتقالي 🟠'}`;
            gameTitle.style.color = myColor === 'green' ? '#4CAF50' : '#FF9800';
        }
        if (me.stats) {
            playersStatsData.me = { ...me.stats, color: me.color, avatar: getValidAvatarSrc(me.stats.avatar) };
        }
    }
    if (opponent?.stats) {
        playersStatsData.opponent = { ...opponent.stats, color: opponent.color, avatar: getValidAvatarSrc(opponent.stats.avatar) };
    }

    updateTopBarUI();
});

socket.on('update_players_stats', (players) => {
    const me       = players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = players.find(p => p.sid !== socket.id && p.name !== playerName);
    if (me?.stats)       playersStatsData.me       = { ...me.stats,       color: me.color,       avatar: getValidAvatarSrc(me.stats.avatar) };
    if (opponent?.stats) playersStatsData.opponent = { ...opponent.stats, color: opponent.color, avatar: getValidAvatarSrc(opponent.stats.avatar) };
    updateTopBarUI();
});


// ============================================================
// 🎮 أحداث السيرفر — سير اللعبة
// ============================================================

socket.on('huroof_board_init', (data) => {
    const roundsDisplay = document.getElementById('rounds-display');
    if (roundsDisplay) roundsDisplay.style.display = 'flex';

    systemMessageDisplay.textContent = 'اكتمل الاتصال! المعركة تبدأ الآن ⚔️';
    systemMessageDisplay.style.color = '#00ff88';

    data.board.forEach((hexData, index) => {
        cells[index].textContent   = hexData.letter;
        cells[index].dataset.index = index;
        cells[index].classList.remove('active', 'green', 'orange');
        if (hexData.color) cells[index].classList.add(hexData.color);
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
    const sidebar = document.getElementById('questionSidebar');
    if (sidebar) {
        Object.assign(sidebar.style, { display: 'flex', visibility: 'visible', opacity: '1', pointerEvents: 'auto' });
        sidebar.classList.add('active');
    }

    const qText = document.getElementById('questionText');
    if (qText) qText.innerHTML = sanitizeHTML(data.questionData.question);

    buzzerBtn.style.display  = 'block';
    buzzerBtn.disabled       = false;
    buzzerBtn.style.opacity  = '1';
    systemMessageDisplay.textContent = '';

    if (voteSkipBtn) {
        voteSkipBtn.style.display    = 'inline-block';
        voteSkipBtn.disabled         = false;
        voteSkipBtn.innerHTML        = '<i class="fa-solid fa-forward-step"></i> اقتراح تغيير السؤال';
        voteSkipBtn.style.background = '#607d8b';
    }

    document.getElementById('answer-container').style.display = 'none';
    answerSection.style.display      = 'none';
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
        systemMessageDisplay.textContent = 'أسرع! اكتب إجابتك...';
        systemMessageDisplay.style.color = '#4CAF50';
        answerSection.style.display      = 'block';
        playerAnswerInput.value          = '';
        playerAnswerInput.focus();
    } else {
        isMyTurnToAnswer = false;
        systemMessageDisplay.textContent = 'الخصم يجيب الآن... استعد في حال أخطأ!';
        systemMessageDisplay.style.color = '#FF9800';
        answerSection.style.display      = 'none';
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
    systemMessageDisplay.innerHTML   = '🚨 الفرصة الأخيرة! من يضغط أولاً؟';
    systemMessageDisplay.style.color = '#f44336';
    answerSection.style.display      = 'none';
    buzzerBtn.style.display          = 'block';
    buzzerBtn.disabled               = false;
    buzzerBtn.style.opacity          = '1';
    if (voteSkipBtn) {
        voteSkipBtn.style.display    = 'inline-block';
        voteSkipBtn.disabled         = false;
        voteSkipBtn.innerHTML        = '<i class="fa-solid fa-forward-step"></i> اقتراح تغيير السؤال';
        voteSkipBtn.style.background = '#607d8b';
    }
    startGlobalTimer(data.timer);
});

socket.on('huroof_answer_result', (data) => {
    clearInterval(playerTimerInterval);
    const cell = cells[data.hexIndex];
    if (data.correct) {
        if (cell) { cell.classList.remove('active'); cell.classList.add(data.color); }
        systemMessageDisplay.innerHTML   = `✅ إجابة صحيحة! (${sanitizeHTML(data.answer)})`;
        systemMessageDisplay.style.color = '#4CAF50';
        buzzerBtn.style.display          = 'none';
        answerSection.style.display      = 'none';
        if (voteSkipBtn) voteSkipBtn.style.display = 'none';
    } else {
        systemMessageDisplay.innerHTML   = `❌ إجابة خاطئة: ${sanitizeHTML(data.answer)}`;
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
        voteSkipBtn.innerHTML        = '<i class="fa-solid fa-check"></i> بانتظار الخصم...';
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
        document.getElementById('overlay-message').innerHTML = `
            <h2 style="color:${winnerColor};margin-bottom:10px;font-family:'Tajawal',sans-serif;">
                فاز اللاعب ${teamName} بالجولة!
            </h2>
            <p>استعد للجولة القادمة...</p>
        `;
        document.querySelector('.spinner').style.display = 'block';
    }
});

socket.on('huroof_new_round_started', (data) => {
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


// ============================================================
// 🖱️ تفاعلات اللاعب
// ============================================================

cells.forEach((cell, index) => {
    cell.addEventListener('click', () => {
        if (
            currentTurnSid === socket.id &&
            !cell.classList.contains('green') &&
            !cell.classList.contains('orange') &&
            !cell.classList.contains('active')
        ) {
            socket.emit('huroof_select_hex', { roomCode, hexIndex: index });
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
    if (!isMyTurnToAnswer) return;
    const ans = playerAnswerInput.value.trim();
    if (!ans) return;
    isMyTurnToAnswer         = false;
    submitAnswerBtn.disabled = true;
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
        qText.innerHTML = currentTurnSid === socket.id
            ? '🎯 <strong>دورك! اختر حرفاً من اللوحة للبدء.</strong>'
            : '⏳ <strong>دور الخصم لاختيار حرف...</strong>';
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
