// ============================================================
// games/huroof_party.js — لعبة حروف (وضع الجمعات / Local Party)
// المتطلبات: config.js → utils.js (يوفر API_URL, sanitizeHTML, getToken)
// ============================================================


// ============================================================
// 🔌 الاتصال بالسوكيت
// ============================================================
const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });

// ============================================================
// 📋 الحروف العربية
// ============================================================
const arabicLetters = [
    'أ', 'ب', 'ت', 'ث', 'ج', 'ح', 'خ', 'د', 'ذ', 'ر',
    'ز', 'س', 'ش', 'ص', 'ض', 'ط', 'ظ', 'ع', 'غ', 'ف',
    'ق', 'ك', 'ل', 'م', 'ن', 'ه', 'و', 'ي',
];

// ============================================================
// 📊 المتغيرات الأساسية
// ============================================================
let selectedHex    = null;
let colorMenu      = null;
let selectedLetter = null;
let previousColor  = '';
let clickCount     = 0;

let greenWins  = parseInt(localStorage.getItem('huroofGreenWins'))  || 0;
let orangeWins = parseInt(localStorage.getItem('huroofOrangeWins')) || 0;

// مراجع عناصر الواجهة
const questionSidebar       = document.getElementById('questionSidebar');
const currentLetterDisplay  = document.getElementById('currentLetterDisplay');
const questionTextElement   = document.getElementById('questionText');
const changeQuestionBtn     = document.getElementById('changeQuestionBtn');
const resetBtn              = document.getElementById('resetBtn');
const categorySelector      = document.getElementById('categorySelector');
const reportQuestionBtn     = document.getElementById('reportQuestionBtn');
const reportModal           = document.getElementById('reportModal');
const submitReportBtn       = document.getElementById('submitReportBtn');
const reportAnswerInput     = document.getElementById('reportAnswerInput');
const reportFeedback        = document.getElementById('reportFeedback');

let currentQuestionData = null;
let reportStrikes = parseInt(localStorage.getItem('huroofReportStrikes')) || 0;
const MAX_STRIKES = 3;

// حالة الاتصال
let isSocketReady  = false;
let pendingQuestion = false;

socket.on('connect', sendJoinPartyMode);


// ============================================================
// 🌟 تهيئة وإعداد اللوحة
// ============================================================
function initGame() {
    updateScoreUI();

    const tutorialModal = document.getElementById('tutorialModal');
    if (tutorialModal && !localStorage.getItem('partyTutorialShown')) {
        tutorialModal.style.display = 'flex';
        localStorage.setItem('partyTutorialShown', 'true');
    }

    shuffleLetters();
    createStars();
}

function updateScoreUI() {
    const sg = document.getElementById('scoreGreen');
    const so = document.getElementById('scoreOrange');
    if (sg) sg.textContent = greenWins;
    if (so) so.textContent = orangeWins;
}

function saveGameState() {
    const boardState = Array.from(document.querySelectorAll('.hex')).map(hex => ({
        text:  hex.textContent,
        color: hex.style.backgroundColor,
    }));
    localStorage.setItem('huroofGameState', JSON.stringify(boardState));
}

function shuffleLetters() {
    const savedState = localStorage.getItem('huroofGameState');
    const hexes      = document.querySelectorAll('.hex');
    const hexRows    = document.querySelectorAll('.hex-row');

    if (savedState) {
        const boardState = JSON.parse(savedState);
        hexes.forEach((hex, i) => {
            hex.textContent            = boardState[i].text;
            hex.style.backgroundColor = boardState[i].color || '';
        });
    } else {
        const letters = [...arabicLetters];
        for (let i = letters.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [letters[i], letters[j]] = [letters[j], letters[i]];
        }
        hexes.forEach((hex, i) => {
            hex.textContent            = letters[i];
            hex.style.backgroundColor = '';
        });
        saveGameState();
    }

    hexRows.forEach((row, rowIndex) => {
        row.querySelectorAll('.hex').forEach((hex, colIndex) => {
            hex.dataset.row = rowIndex;
            hex.dataset.col = colIndex;
        });
    });
}


// ============================================================
// 🖱️ التفاعل مع السداسيات
// ============================================================
function selectLetter(element) {
    if (colorMenu) { colorMenu.remove(); colorMenu = null; }

    if (selectedHex === element) {
        clickCount++;
    } else {
        clickCount = 1;
        if (selectedHex) selectedHex.style.backgroundColor = previousColor;
        selectedHex    = element;
        selectedLetter = sanitizeHTML(element.textContent.trim());
        previousColor  = selectedHex.style.backgroundColor;
        selectedHex.style.backgroundColor = 'yellow';
        if (currentLetterDisplay) currentLetterDisplay.textContent = selectedLetter;
        requestAiQuestion();
    }

    if (clickCount === 2) { showColorOptions(element); clickCount = 0; }
}

function showColorOptions(element) {
    colorMenu           = document.createElement('div');
    colorMenu.className = 'color-menu';

    const greenBtn  = document.createElement('button');
    greenBtn.className   = 'color-btn green';
    greenBtn.textContent = 'الفريق الأخضر 🟢';
    greenBtn.onclick     = (e) => { e.stopPropagation(); changeColor('green'); };

    const orangeBtn  = document.createElement('button');
    orangeBtn.className   = 'color-btn orange';
    orangeBtn.textContent = 'الفريق البرتقالي 🟠';
    orangeBtn.onclick     = (e) => { e.stopPropagation(); changeColor('orange'); };

    const cancelBtn  = document.createElement('button');
    cancelBtn.className   = 'color-btn cancel';
    cancelBtn.textContent = 'إلغاء التحديد ❌';
    cancelBtn.onclick     = (e) => {
        e.stopPropagation();
        colorMenu.remove(); colorMenu = null;
        if (selectedHex) { selectedHex.style.backgroundColor = previousColor; selectedHex = null; }
    };

    colorMenu.append(greenBtn, orangeBtn, cancelBtn);

    const rect = element.getBoundingClientRect();
    colorMenu.style.left = `${rect.left + window.scrollX + (rect.width / 2) - 80}px`;
    colorMenu.style.top  = `${rect.bottom + window.scrollY + 10}px`;
    document.body.appendChild(colorMenu);
}

function changeColor(color) {
    if (selectedHex) {
        selectedHex.style.backgroundColor = color;
        previousColor  = color;
        disableActionButtons();
        selectedHex    = null;
        selectedLetter = null;
        if (questionSidebar) questionSidebar.classList.remove('active');
        saveGameState();
    }
    if (colorMenu) { colorMenu.remove(); colorMenu = null; }
    checkWin('green');
    checkWin('orange');
}


// ============================================================
// 🏆 منطق الفوز والتوصيل
// ============================================================
function getNeighbors(row, col) {
    const neighbors = row % 2 === 0
        ? [[row-1,col],[row-1,col+1],[row,col-1],[row,col+1],[row+1,col],[row+1,col+1]]
        : [[row-1,col-1],[row-1,col],[row,col-1],[row,col+1],[row+1,col-1],[row+1,col]];
    return neighbors.filter(([r, c]) => r >= 0 && r < 5 && c >= 0 && c < 5);
}

function checkWin(color) {
    const isGreen = color === 'green';
    const startSelector  = isGreen ? '.hex[data-row="0"]'  : '.hex[data-col="0"]';
    const targetFn       = isGreen
        ? (hex) => hex.dataset.row === '4' && hex.style.backgroundColor === 'green'
        : (hex) => hex.dataset.col === '4' && hex.style.backgroundColor === 'orange';

    const startHexes = Array.from(document.querySelectorAll(startSelector))
        .filter(h => h.style.backgroundColor === color);

    for (const start of startHexes) {
        const visited = new Set();
        const queue   = [[parseInt(start.dataset.row), parseInt(start.dataset.col)]];

        while (queue.length > 0) {
            const [r, c] = queue.shift();
            const key    = `${r},${c}`;
            if (visited.has(key)) continue;
            visited.add(key);

            const hex = document.querySelector(`.hex[data-row="${r}"][data-col="${c}"]`);
            if (!hex || hex.style.backgroundColor !== color) continue;
            if (targetFn(hex)) { handleRoundWin(color); return true; }
            getNeighbors(r, c).forEach(n => queue.push(n));
        }
    }
    return false;
}

function handleRoundWin(color) {
    if (color === 'green') {
        greenWins++;
        localStorage.setItem('huroofGreenWins', greenWins);
    } else {
        orangeWins++;
        localStorage.setItem('huroofOrangeWins', orangeWins);
    }
    updateScoreUI();
    if (greenWins >= 2 || orangeWins >= 2) showFinalWinModal(color);
    else showRoundWinModal(color);
}

function showRoundWinModal(color) {
    const overlay = document.getElementById('winMessageOverlay');
    const title   = document.getElementById('winMessageTitle');
    const text    = document.getElementById('winMessageText');
    const btn     = document.querySelector('#winMessageOverlay button');

    if (btn)     btn.style.display     = 'none';
    if (overlay) overlay.style.display = 'flex';
    if (title)   title.textContent     = 'نهاية الجولة!';

    const teamName = color === 'green' ? 'الأخضر 🟢' : 'البرتقالي 🟠';
    let countdown  = 3;

    const updateText = () => {
        if (!text) return;
        text.innerHTML = '';
        // teamName مصدره منطق داخلي فقط (ثابت)، لكن نبني بـ DOM API لأفضل ممارسة
        const winLine = document.createTextNode(`فاز الفريق ${sanitizeText(teamName)} بهذه الجولة!`);
        const br1 = document.createElement('br');
        const br2 = document.createElement('br');
        const subSpan = document.createElement('span');
        subSpan.style.cssText = 'color:#00d2ff;font-size:18px;';
        subSpan.textContent   = 'تبدأ الجولة التالية خلال ';
        const boldCount = document.createElement('b');
        boldCount.style.cssText  = 'font-size:24px;color:#fff;';
        boldCount.textContent    = countdown;
        subSpan.appendChild(boldCount);
        subSpan.appendChild(document.createTextNode('...'));
        text.appendChild(winLine);
        text.appendChild(br1);
        text.appendChild(br2);
        text.appendChild(subSpan);
    };
    updateText();

    const interval = setInterval(() => {
        countdown--;
        updateText();
        if (countdown <= 0) {
            clearInterval(interval);
            if (overlay) overlay.style.display = 'none';
            if (btn)     btn.style.display     = 'block';
            startNewRound();
        }
    }, 1000);
}

function startNewRound() {
    localStorage.removeItem('huroofGameState');
    shuffleLetters();
}

function showFinalWinModal(color) {
    const overlay = document.getElementById('winMessageOverlay');
    const title   = document.getElementById('winMessageTitle');
    const text    = document.getElementById('winMessageText');
    if (overlay) overlay.style.display = 'flex';
    if (title)   title.textContent     = '🏆 بطل السهرة! 🏆';
    if (text)    text.textContent      = `اكتسح الفريق ${color === 'green' ? 'الأخضر' : 'البرتقالي'} وفاز بالمباراة!`;
    startConfetti();

    ['huroofGreenWins', 'huroofOrangeWins', 'huroofGameState'].forEach(k => localStorage.removeItem(k));
}


// ============================================================
// 🤖 السوكيت: طلب سؤال والردود
// ============================================================
function requestAiQuestion() {
    if (!selectedLetter) return;
    if (questionTextElement) questionTextElement.textContent = 'جاري صياغة سؤال... ⏳';
    disableActionButtons();
    if (questionSidebar)  questionSidebar.classList.add('active');
    if (reportQuestionBtn) reportQuestionBtn.style.display = 'none';
    currentQuestionData = null;

    if (!isSocketReady) { pendingQuestion = true; return; }

    pendingQuestion = false;
    socket.emit('request_ai_question', {
        letter:   selectedLetter,
        category: categorySelector?.value || 'عام',
    });
}

socket.on('receive_ai_question', (data) => {
    if (questionTextElement) questionTextElement.textContent = data.question;
    currentQuestionData = data;
    enableActionButtons();

    if (reportQuestionBtn && data.answer !== 'لا يوجد') {
        if (reportStrikes >= MAX_STRIKES) {
            reportQuestionBtn.textContent        = '🚫 محظور من الإبلاغ';
            reportQuestionBtn.disabled           = true;
            reportQuestionBtn.style.background   = '#555';
        } else {
            reportQuestionBtn.textContent        = 'الإبلاغ عن خطأ 🚩';
            reportQuestionBtn.disabled           = false;
            reportQuestionBtn.style.background   = '#f44336';
        }
        reportQuestionBtn.style.display = 'block';
    }
});

socket.on('receive_host_code', (data) => {
    const display = document.getElementById('newHostCodeDisplay');
    const btn     = document.getElementById('generateNewCodeBtn');
    if (display) display.textContent    = data.code;
    if (btn)     btn.style.display      = 'none';
});

socket.on('host_linked_success', () => {
    const hostModal = document.getElementById('hostModal');
    if (hostModal) hostModal.style.display = 'none';

    const toast = document.createElement('div');
    toast.innerHTML  = '';
    const toastIcon = document.createElement('i');
    toastIcon.className = 'fa-solid fa-check-circle';
    toast.appendChild(toastIcon);
    toast.appendChild(document.createTextNode(' تم ربط المدير الجديد بنجاح!'));
    toast.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#4CAF50;color:white;padding:15px 30px;border-radius:8px;font-weight:bold;z-index:9999;box-shadow:0 4px 15px rgba(0,0,0,0.5);display:flex;gap:10px;align-items:center;font-size:16px;';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
});


// ============================================================
// 🔗 الانضمام لوضع الجمعات
// ============================================================
async function sendJoinPartyMode() {
    const token    = getToken();
    let   name     = 'ضيف';
    let   avatar   = '../assets/avatars/avatar1.svg';

    if (token) {
        try {
            const res  = await fetch(`${API_URL}/auth/me?token=${token}`);
            const data = await res.json();
            name   = data.player_name || name;
            avatar = data.avatar      || avatar;
        } catch { /* يستمر بالقيم الافتراضية */ }
    }

    socket.emit('join_party_mode', { gameMode: 'huroof', name, avatar });
    isSocketReady = true;

    if (pendingQuestion && selectedLetter) {
        pendingQuestion = false;
        requestAiQuestion();
    }
}


// ============================================================
// 🎨 الواجهة والتأثيرات
// ============================================================
function disableActionButtons() {
    if (changeQuestionBtn) { changeQuestionBtn.classList.remove('enabled'); changeQuestionBtn.disabled = true; }
}

function enableActionButtons() {
    if (changeQuestionBtn) { changeQuestionBtn.classList.add('enabled'); changeQuestionBtn.disabled = false; }
}

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

function startConfetti() {
    const container = document.getElementById('confettiContainer');
    if (!container) return;
    container.innerHTML = '';
    for (let i = 0; i < 200; i++) {
        const c = document.createElement('div');
        c.className    = 'confetti';
        c.style.cssText = `left:${Math.random()*100}%;animation-delay:${Math.random()*5}s;animation-duration:${Math.random()*3+3}s;`;
        container.appendChild(c);
    }
}


// ============================================================
// 🛑 إغلاق الجلسة والعودة للوبي
// ============================================================
window.closeSessionAndLeave = function (targetUrl) {
    ['huroofGameState', 'huroofGreenWins', 'huroofOrangeWins'].forEach(k => localStorage.removeItem(k));
    socket.emit('close_host_session', {});
    setTimeout(() => window.location.href = targetUrl, 500);
};


// ============================================================
// ⚡ تشغيل الصفحة
// ============================================================
window.addEventListener('load', () => {
    document.body.style.visibility = 'visible';
    initGame();

    // ربط السداسيات
    document.querySelectorAll('.hex').forEach(hex => {
        hex.addEventListener('click', function (e) { e.preventDefault(); selectLetter(this); });
    });

    // أزرار العودة
    document.getElementById('backToLobbyBtn')?.addEventListener('click', (e) => {
        e.preventDefault(); closeSessionAndLeave('../lobby.html');
    });

    const topBackBtn = document.querySelector('.back-btn, #backBtn');
    topBackBtn?.addEventListener('click', (e) => {
        e.preventDefault(); closeSessionAndLeave(topBackBtn.href || '../lobby.html');
    });

    // التحكم بالأسئلة
    changeQuestionBtn?.addEventListener('click', requestAiQuestion);

    resetBtn?.addEventListener('click', () => {
        ['huroofGameState', 'huroofGreenWins', 'huroofOrangeWins'].forEach(k => localStorage.removeItem(k));
        window.location.reload();
    });

    // إدارة المضيف
    const changeHostBtn     = document.getElementById('changeHostBtn');
    const hostModal         = document.getElementById('hostModal');
    const generateNewCodeBtn = document.getElementById('generateNewCodeBtn');
    const newHostCodeDisplay = document.getElementById('newHostCodeDisplay');

    changeHostBtn?.addEventListener('click', (e) => {
        e.preventDefault();
        socket.emit('change_host_session', {});
        if (hostModal) {
            hostModal.style.display = 'flex';
            if (newHostCodeDisplay) { newHostCodeDisplay.style.display = 'none'; newHostCodeDisplay.textContent = '----'; }
            if (generateNewCodeBtn) generateNewCodeBtn.style.display = 'block';
        }
    });

    generateNewCodeBtn?.addEventListener('click', () => {
        if (newHostCodeDisplay) { newHostCodeDisplay.style.display = 'block'; newHostCodeDisplay.textContent = '⏳...'; }
        socket.emit('generate_host_code', {});
    });

    // الإبلاغ عن خطأ
    reportQuestionBtn?.addEventListener('click', () => {
        if (reportStrikes >= MAX_STRIKES) return;
        if (reportModal) {
            reportModal.style.display = 'flex';
            if (reportAnswerInput) reportAnswerInput.value = '';
            if (reportFeedback)   reportFeedback.style.display = 'none';
        }
    });

    submitReportBtn?.addEventListener('click', () => {
        if (reportModal) reportModal.style.display = 'none';
    });

    // الاتصال المباشر (reconnect)
    if (socket.connected) sendJoinPartyMode();
});


// إغلاق القوائم عند النقر خارجها
document.addEventListener('click', (e) => {
    const isHex      = e.target.closest('.hex');
    const isMenu     = colorMenu && colorMenu.contains(e.target);
    const isSidebar  = e.target.closest('#questionSidebar');

    if (!isHex && !isMenu && !isSidebar) {
        if (colorMenu)   { colorMenu.remove(); colorMenu = null; }
        if (selectedHex) { selectedHex.style.backgroundColor = previousColor; selectedHex = null; clickCount = 0; }
        disableActionButtons();
        if (questionSidebar) questionSidebar.classList.remove('active');
    }
});
