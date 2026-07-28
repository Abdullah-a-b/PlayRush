// ============================================================
// games/huroof.js — لعبة حروف (المباراة المباشرة)
// المتطلبات: config.js → utils.js (يوفر API_URL, sanitizeHTML, getToken)
// ============================================================


// ============================================================
//  الاتصال والجلسة
// ============================================================
const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });

const token        = getToken();
const playerName   = sessionStorage.getItem('playerName')   || sessionStorage.getItem('username')   || 'لاعب';
const playerAvatar = sessionStorage.getItem('playerAvatar') || sessionStorage.getItem('avatar')     || '';
const roomCode     = sessionStorage.getItem('gameRoomCode');

// 🤖 الوضع الفردي: نكتشفه من رابط الصفحة (?solo=1&difficulty=...)
const _soloParams  = new URLSearchParams(window.location.search);
const IS_SOLO      = _soloParams.get('solo') === '1';
const SOLO_DIFF    = _soloParams.get('difficulty') || 'medium';
let   soloRoomCode = null;   // يُملأ من solo_started

// الغرفة الفعّالة: الفردية بعد بدئها، وإلا غرفة الأونلاين
function activeRoom() { return soloRoomCode || roomCode; }


// في الأونلاين نحتاج roomCode؛ في الفردي لا (الخادم ينشئ الغرفة)
if (!token || (!roomCode && !IS_SOLO)) window.location.href = '../lobby.html';


// ============================================================
//  بناء لوحة السداسيات
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
//  مراجع عناصر الواجهة
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

function showBuzzer(show) {
    if (buzzerBtn) buzzerBtn.classList.toggle('visible', show);
}
function showSkipBtn(show) {
    if (voteSkipBtn) voteSkipBtn.classList.toggle('visible', show);
}
function resetSkipBtn() {
    if (!voteSkipBtn) return;
    voteSkipBtn.classList.remove('state-waiting', 'state-approve');
    voteSkipBtn.style.animation = 'none';
    voteSkipBtn.innerHTML = '<i class="fa-solid fa-rotate"></i><span class="skip-label">تغيير السؤال</span>';
    voteSkipBtn.disabled = false;
}
function showGlobalTimer(show) {
    if (globalTimerDisplay) globalTimerDisplay.classList.toggle('visible', show);
}
function showAnswerSection(show) {
    if (answerSection) answerSection.classList.toggle('visible', show);
}
function showAnswerContainer(show) {
    const el = document.getElementById('answer-container');
    if (el) el.classList.toggle('visible', show);
}


// ============================================================
//  حالة اللعبة
// ============================================================
let myColor             = null;
let currentTurnSid      = null;
let currentTurnColor    = null;
let _opponentUserId     = null;
let activeHexIndex      = null;
let isMyTurnToAnswer    = false;
let globalTimerInterval = null;
let playerTimerInterval = null;

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


// ============================================================
//  مسار الأفاتار (خاص بمجلد games/ حيث المسار ../../)
// ============================================================
function getValidAvatarSrc(avatarValue) {
    if (!avatarValue || avatarValue.trim() === '') return '../assets/avatars/avatar_1.svg';
    //  نعالج روابط قديمة ثابتة (127.0.0.1/localhost) محفوظة من قبل التحديث:
    // نحوّلها لمسار يعمل على العنوان الحالي (لابتوب/جوال).
    let v = avatarValue.trim();
    const staleMatch = v.match(/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/.*)$/i);
    if (staleMatch) {
        const path = staleMatch[3];  // الجزء بعد الدومين
        if (path.startsWith('/uploads')) return `${API_URL}${path}`;
        // كان أصلاً assets — نحوّله لمسار نسبي
        const fname = path.split('/').pop();
        return `../assets/avatars/${fname}`;
    }
    if (v.startsWith('http') || v.startsWith('data:')) return v;
    if (v.startsWith('/uploads')) return `${API_URL}${v}`;
    //  مسارات نسبية أو مطلقة محلية → نأخذ اسم الملف فقط
    const name = v.split('/').pop();
    if (!name) return '../assets/avatars/avatar_1.svg';
    return `../assets/avatars/${name.includes('.') ? name : name + '.svg'}`;
}

//  رسم أفاتار اللاعب مبكراً من الجلسة (قبل وصول بيانات الخادم) حتى لا تظهر صورة فارغة
document.addEventListener('DOMContentLoaded', () => {
    try {
        const myImg = document.getElementById('myAvatarImg');
        if (myImg && playerAvatar) myImg.src = getValidAvatarSrc(playerAvatar);
        // احتياطي: أي أفاتار يفشل تحميله يرجع للصورة الافتراضية
        ['myAvatarImg', 'opponentAvatarImg', 'mrMyAvatar', 'mrOppAvatar', 'modalAvatar'].forEach((id, i) => {
            const el = document.getElementById(id);
            if (el) el.onerror = function () {
                this.onerror = null;
                this.src = `../assets/avatars/avatar_${(i % 2) + 1}.svg`;
            };
        });
    } catch (e) {}
});


// ============================================================
//  معالج الكيبورد على الجوال (visualViewport) — نسخة محسّنة
//
//  المشكلة: لما يفتح الكيبورد في Chrome Android:
//    1. الـ viewport يصغر → الصندوق يخرج من الشاشة
//    2. الـ vh يتغير في بعض المتصفحات → max-height يتكسر
//    3. المحتوى يتراكم لأن الـ overflow لا يعمل مع max-height ثابت
//
//  الحل:
//    - نحسب ارتفاع الكيبورد بدقة من visualViewport
//    - نضبط bottom + max-height ديناميكياً بـ px (لا vh)
//    - نضيف كلاس keyboard-open يُخفي العناصر غير الضرورية (CSS)
//    - نُخفي أزرار المساعدات وزر الاستسلام أثناء الكتابة
// ============================================================
(function setupMobileKeyboardHandler() {
    if (!window.visualViewport) return;

    const sidebar    = document.getElementById('questionSidebar');
    const helpSlots  = document.querySelector('.help-slots');
    const surrendBtn = document.getElementById('surrenderBtn');
    const soundBtn   = document.querySelector('.pr-sound-float');
    const ansInput   = document.getElementById('playerAnswerInput');
    if (!sidebar) return;

    const BASE_BOTTOM  = 68;
    const BASE_MAX_VH  = 0.38;
    const KB_THRESHOLD = 100;

    let kbOpen = false;
    let rafId  = 0;

    function applyLayout() {
        rafId = 0;
        const vv       = window.visualViewport;
        const winH     = window.innerHeight;
        const vvBottom = vv.offsetTop + vv.height;
        const kbHeight = Math.max(0, winH - vvBottom);

        if (kbHeight > KB_THRESHOLD) {
            if (!kbOpen) {
                kbOpen = true;
                sidebar.classList.add('keyboard-open');
                document.documentElement.classList.add('kb-open');
                if (helpSlots)  helpSlots.style.setProperty('display', 'none', 'important');
                if (surrendBtn) surrendBtn.style.setProperty('display', 'none', 'important');
                if (soundBtn)   soundBtn.style.setProperty('display', 'none', 'important');
            }

            // نُثبّت الصندوق بـ top بالنسبة لأعلى الصفحة (layout viewport)
            // top = أعلى المنطقة المرئية + المسافة المتاحة - ارتفاع الصندوق - هامش
            const topBar     = 62;
            const margin     = 8;
            const available  = vv.height - topBar - margin * 2;
            const sidebarH   = Math.max(140, Math.min(available, Math.round(vv.height * 0.55)));
            // vv.offsetTop = إزاحة المنطقة المرئية عن أعلى layout viewport (يتغيّر مع scroll)
            const topPx      = vv.offsetTop + vv.height - sidebarH - margin;

            sidebar.style.setProperty('top',        topPx + 'px',    'important');
            sidebar.style.setProperty('bottom',     'auto',           'important');
            sidebar.style.setProperty('max-height', sidebarH + 'px',  'important');
            sidebar.style.setProperty('height',     sidebarH + 'px',  'important');
        } else {
            _resetSidebar();
        }
    }

    function onViewportChange() {
        if (rafId) return;
        rafId = requestAnimationFrame(applyLayout);
    }

    function _resetSidebar() {
        if (!kbOpen) return;
        kbOpen = false;
        sidebar.classList.remove('keyboard-open');
        document.documentElement.classList.remove('kb-open');
        sidebar.style.removeProperty('top');
        sidebar.style.removeProperty('height');
        sidebar.style.setProperty('bottom',     BASE_BOTTOM + 'px', 'important');
        sidebar.style.setProperty('max-height', (window.innerHeight * BASE_MAX_VH) + 'px', 'important');
        if (helpSlots)  helpSlots.style.removeProperty('display');
        if (surrendBtn) surrendBtn.style.removeProperty('display');
        if (soundBtn)   soundBtn.style.removeProperty('display');
    }

    window.visualViewport.addEventListener('resize', onViewportChange);
    window.visualViewport.addEventListener('scroll', onViewportChange);
    // بعض متصفحات iOS تُحرّك الصفحة عند focus — نعيد الحساب فوراً
    if (ansInput) {
        ansInput.addEventListener('focus', () => setTimeout(onViewportChange, 50));
        ansInput.addEventListener('blur',  () => setTimeout(_resetSidebar,  200));
    }
})();

// ============================================================
//  الاتصال والانضمام للغرفة
// ============================================================
socket.on('connect', () => {
    if (IS_SOLO) {
        // الوضع الفردي: نطلب من الخادم إنشاء مباراة ضد البوت
        // نرسل التوكن والبيانات لأن الصفحة قد تُفتح مباشرة دون لوبي
        socket.emit('huroof_start_solo', {
            difficulty: SOLO_DIFF, token: token,
            name: playerName, avatar: playerAvatar
        });
    } else {
        socket.emit('join_room', { room_code: roomCode, token, player_name: playerName, avatar: playerAvatar });
    }
});

// 🤖 بدء المباراة الفردية: نخزّن رمز الغرفة ونعرض الخصم "الكمبيوتر"
socket.on('solo_started', (data) => {
    soloRoomCode = data.room_code;
    // نضبط لوني مباشرة من الخادم (مصدر موثوق) قبل أي حدث آخر
    if (data.your_color) {
        myColor = data.your_color;
        var gt = document.querySelector('.game-title');
        if (gt) {
            gt.textContent = 'خلية الحروف - أنت اللاعب ' + (myColor === 'green' ? 'الأخضر 🟢' : 'البرتقالي 🟠');
            gt.style.color = myColor === 'green' ? '#4CAF50' : '#FF9800';
        }
    }
    try {
        showMatchReveal(playerName, getCorrectAvatarUrl(playerAvatar),
                        'الكمبيوتر (' + (data.difficulty_label || '') + ')',
                        '../assets/avatars/avatar_1.svg');
    } catch (e) {}
    // نطلب كتالوج المساعدات الآن بعد أن صار لدينا رمز الغرفة
    setTimeout(() => socket.emit('huroof_get_helps_catalog', { roomCode: activeRoom() }), 300);

    // تحسينات الوضع الفردي في الواجهة:
    // 1) نخفي الدردشة (لا فائدة منها ضد بوت) — عبر صنف على body
    //    ليصمد أمام إعادة بناء quick_chat.js للأزرار.
    document.body.classList.add('solo-mode');
    // 2) علم الكمبيوتر = كوكب الأرض
    setTimeout(function () {
        var f = document.getElementById('opponentFlagImg');
        if (f) f.src = '../assets/flags/EARTH.svg';
    }, 400);
});

socket.on('solo_error', (data) => {
    if (typeof showToast === 'function') showToast((data && data.msg) || 'تعذّر بدء اللعب', 'error');
    setTimeout(() => window.location.href = '../lobby.html', 1500);
});


/* ================================================================
   🎮 showMatchReveal — كشف التطابق عند بدء المباراة
   ================================================================ */
function showMatchReveal(myName, myAvatarSrc, oppName, oppAvatarSrc) {
  var overlay = document.getElementById('matchRevealOverlay');
  if (!overlay) return;
  var ge = function(id){ return document.getElementById(id); };
  if (myName)       ge('mrMyName').textContent   = myName;
  if (myAvatarSrc)  ge('mrMyAvatar').src         = myAvatarSrc;
  if (oppName)      ge('mrOppName').textContent   = oppName;
  if (oppAvatarSrc) ge('mrOppAvatar').src         = oppAvatarSrc;
  overlay.classList.add('show');
  var bar = ge('mrReadyFill');
  if (bar) { bar.style.width = '0%'; void bar.offsetWidth; bar.style.width = '100%'; }
  setTimeout(function(){ overlay.classList.remove('show'); }, 3200);
}

socket.on('room_joined', (data) => {
    const me       = data.players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = data.players.find(p => p.sid !== socket.id && p.name !== playerName);

    if (me) {
        myColor = me.color;
        const gameTitle = document.querySelector('.game-title');
        if (gameTitle) {
            gameTitle.textContent = `خلية الحروف - أنت اللاعب ${myColor === 'green' ? 'الأخضر 🟢' : 'البرتقالي 🟠'}`;
            gameTitle.style.color = myColor === 'green' ? '#4CAF50' : '#FF9800';
        }
        if (me.stats) {
            playersStatsData.me = { ...me.stats, color: me.color, avatar: getValidAvatarSrc(me.stats.avatar) };
        }
    }
    if (opponent?.stats) {
        playersStatsData.opponent = { ...opponent.stats, color: opponent.color, avatar: getValidAvatarSrc(opponent.stats.avatar) };
    }

    //  نضبط حالة أزرار الصداقة/الحظر حسب العلاقة الحقيقية من الخادم
    if (typeof data.opponent_user_id !== 'undefined') {
        _opponentUserId = data.opponent_user_id;
    }
    if (typeof data.opponent_relation === 'string' && typeof applyOpponentRelation === 'function') {
        applyOpponentRelation(data.opponent_relation);
    }

    updateTopBarUI();
    // 🎮 كشف التطابق بين اللاعبين
    if (playersStatsData.opponent && playersStatsData.opponent.name) {
      showMatchReveal(
        playersStatsData.me.name, playersStatsData.me.avatar,
        playersStatsData.opponent.name, playersStatsData.opponent.avatar
      );
    }
});

socket.on('update_players_stats', (players) => {
    const me       = players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = players.find(p => p.sid !== socket.id && p.name !== playerName);
    if (me?.stats)       playersStatsData.me       = { ...me.stats,       color: me.color,       avatar: getValidAvatarSrc(me.stats.avatar) };
    if (opponent?.stats) playersStatsData.opponent = { ...opponent.stats, color: opponent.color, avatar: getValidAvatarSrc(opponent.stats.avatar) };
    updateTopBarUI();
});


// ============================================================
//  أحداث السيرفر — سير اللعبة
// ============================================================


// ===== أنيميشن استعد 3-2-1 (موحّد مع بقية الألعاب) =====
let _readyShown = false;
function playReadyAnimation(cb) {
    const overlay = document.getElementById('readyOverlay');
    const countEl = document.getElementById('readyCount');
    if (!overlay || !countEl) { if (cb) cb(); return; }
    overlay.style.display = 'flex';
    let n = 3;
    countEl.textContent = n;
    countEl.className = 'ready-count pop';
    const tick = () => {
        n--;
        if (n > 0) {
            countEl.textContent = n;
            countEl.className = 'ready-count';
            void countEl.offsetWidth;
            countEl.className = 'ready-count pop';
            setTimeout(tick, 1000);
        } else {
            overlay.style.display = 'none';
            if (cb) cb();
        }
    };
    setTimeout(tick, 1000);
}

socket.on('huroof_board_init', (data) => {
    if (!_readyShown) { _readyShown = true; playReadyAnimation(); }
    const roundsDisplay = document.getElementById('rounds-display');
    if (roundsDisplay) roundsDisplay.style.display = 'flex';

    systemMessageDisplay.textContent = 'اكتمل الاتصال! المعركة تبدأ الآن ⚔️';
    systemMessageDisplay.style.color = '#00ff88';

    //  نبضة تعريفية على بروفايل الخصم (مرة واحدة) — تلمّح أنه قابل للضغط
    const oppBtn = document.getElementById('opponentProfileBtn');
    if (oppBtn && !oppBtn.dataset.hinted) {
        oppBtn.dataset.hinted = '1';
        oppBtn.classList.add('hint-pulse');
        setTimeout(() => oppBtn.classList.remove('hint-pulse'), 2600);
    }

    data.board.forEach((hexData, index) => {
        cells[index].textContent   = hexData.letter;
        cells[index].dataset.index = index;
        cells[index].classList.remove('active', 'green', 'orange');
        if (hexData.color) cells[index].classList.add(hexData.color);
    });
});

socket.on('huroof_turn_changed', (data) => {
    currentTurnSid = data.turn_sid;
    // اللون أكثر استقراراً من sid عبر إعادة الاتصال/الانتقال
    currentTurnColor = data.turn_color || null;
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
    if (qText) {
        qText.innerHTML = sanitizeHTML(data.questionData.question);
        // 🆕 منع نسخ السؤال (يقلل الغش بالبحث عنه)
        qText.style.userSelect = 'none';
        qText.style.webkitUserSelect = 'none';
        qText.style.MozUserSelect = 'none';
        qText.oncopy = (e) => { e.preventDefault(); return false; };
        qText.oncontextmenu = (e) => { e.preventDefault(); return false; };
    }

    // 🆕 توست عند تغيير السؤال
    if (data.changed) {
        showToast('🔄 تم تغيير السؤال');
    }

    showBuzzer(true);
    buzzerBtn.disabled       = false;
    buzzerBtn.style.opacity  = '1';
    systemMessageDisplay.textContent = '';

    resetSkipBtn();
    showSkipBtn(true);

    showAnswerContainer(false);
    showAnswerSection(false);
    showGlobalTimer(true);
    startGlobalTimer(data.timer);
});

// 🆕 دالة توست بسيطة (لو ما كانت موجودة)
function showToast(message) {
    let toast = document.getElementById('huroof-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'huroof-toast';
        Object.assign(toast.style, {
            position: 'fixed', bottom: '30px', left: '50%',
            transform: 'translateX(-50%)', background: 'rgba(33,33,55,0.95)',
            color: '#fff', padding: '12px 24px', borderRadius: '10px',
            fontSize: '1rem', zIndex: '9999', opacity: '0',
            transition: 'opacity 0.3s', pointerEvents: 'none',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)'
        });
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.style.opacity = '1';
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(() => { toast.style.opacity = '0'; }, 2500);
}

socket.on('huroof_buzzed', (data) => {
    clearInterval(globalTimerInterval);
    showGlobalTimer(false);
    showBuzzer(false);
    showSkipBtn(false);

    const timeValue = parseInt(data.time || data.timer);
    if (isNaN(timeValue)) return;

    if (data.sid === socket.id) {
        isMyTurnToAnswer = true;
        systemMessageDisplay.textContent = 'أسرع! اكتب إجابتك...';
        systemMessageDisplay.style.color = '#4CAF50';
        showAnswerSection(true);
        submitAnswerBtn.disabled         = false;  // 🆕 نعيد تفعيل الزر للمحاولة الجديدة
        playerAnswerInput.value          = '';
        playerAnswerInput.focus();
    } else {
        isMyTurnToAnswer = false;
        systemMessageDisplay.textContent = 'الخصم يجيب الآن... استعد في حال أخطأ!';
        systemMessageDisplay.style.color = '#FF9800';
        showAnswerSection(false);
    }
    startPlayerTimer(timeValue);
});

socket.on('huroof_chance_transfer', (data) => {
    clearInterval(playerTimerInterval);
    if (data.to_sid === socket.id) {
        isMyTurnToAnswer = true;
        systemMessageDisplay.textContent = 'أخطأ الخصم! فرصتك الآن...';
        systemMessageDisplay.style.color = '#4CAF50';
        showAnswerSection(true);
        submitAnswerBtn.disabled         = false;  // 🆕 نعيد تفعيل الزر للمحاولة الجديدة
        playerAnswerInput.value          = '';
        playerAnswerInput.focus();
    } else {
        isMyTurnToAnswer = false;
        systemMessageDisplay.textContent = 'أخطأت! فرصة الخصم الآن...';
        systemMessageDisplay.style.color = '#FF9800';
        showAnswerSection(false);
    }
    startPlayerTimer(data.timer);
});

socket.on('huroof_last_chance', (data) => {
    clearInterval(playerTimerInterval);
    systemMessageDisplay.innerHTML   = '🚨 الفرصة الأخيرة! من يضغط أولاً؟';
    systemMessageDisplay.style.color = '#f44336';
    showAnswerSection(false);
    showBuzzer(true);
    buzzerBtn.disabled               = false;
    buzzerBtn.style.opacity          = '1';
    resetSkipBtn();
    showSkipBtn(true);
    startGlobalTimer(data.timer);
});

socket.on('huroof_answer_result', (data) => {
    clearInterval(playerTimerInterval);
    const cell = cells[data.hexIndex];
    if (data.correct) {
        if (cell) { cell.classList.remove('active'); cell.classList.add(data.color); }
        systemMessageDisplay.innerHTML   = `✅ إجابة صحيحة! (${sanitizeHTML(data.answer)})`;
        systemMessageDisplay.style.color = '#4CAF50';
        showBuzzer(false);
        showAnswerSection(false);
        showSkipBtn(false);
    } else {
        // 🆕 رسالة ذكية + إظهار الإجابة الصحيحة
        const feedback = data.feedback || 'إجابة خاطئة';
        let msg = `❌ ${sanitizeHTML(feedback)}: ${sanitizeHTML(data.answer)}`;
        if (data.correct_answer) {
            msg += `<br><span style="font-size:0.9em;color:#aaa;">الإجابة الصحيحة: <b style="color:#4CAF50;">${sanitizeHTML(data.correct_answer)}</b></span>`;
        }
        systemMessageDisplay.innerHTML   = msg;
        systemMessageDisplay.style.color = '#f44336';
    }
});

socket.on('huroof_timeout_info', (data) => {
    clearInterval(globalTimerInterval);
    clearInterval(playerTimerInterval);
    systemMessageDisplay.textContent = sanitizeHTML(data.msg);
    systemMessageDisplay.style.color = '#ff9800';
    showBuzzer(false);
    showAnswerSection(false);
    showSkipBtn(false);
});

// 🆕 كشف الإجابة الصحيحة للطرفين (عند فشل الاثنين أو الاتفاق على التغيير)
socket.on('huroof_reveal_answer', (data) => {
    clearInterval(globalTimerInterval);
    clearInterval(playerTimerInterval);
    if (data && data.correct_answer) {
        systemMessageDisplay.innerHTML = `الإجابة الصحيحة: <b style="color:#4CAF50;">${sanitizeHTML(data.correct_answer)}</b>`;
        systemMessageDisplay.style.color = '#4CAF50';
    }
    showBuzzer(false);
    showAnswerSection(false);
    showSkipBtn(false);
});

socket.on('huroof_skip_voted', (data) => {
    if (data.sid === socket.id) {
        // أنا اللي طلبت التغيير → بانتظار موافقة الخصم
        if (voteSkipBtn) {
            voteSkipBtn.classList.add('state-waiting');
            voteSkipBtn.classList.remove('state-approve');
            voteSkipBtn.innerHTML = '<i class="fa-solid fa-check"></i><span class="skip-label">انتظر...</span>';
            voteSkipBtn.disabled = true;
        }
    } else {
        // 🆕 الخصم طلب التغيير → يطلع لي طلب الموافقة
        showToast('🔄 الخصم يطلب تغيير السؤال — اضغط "تغيير السؤال" للموافقة');
        if (voteSkipBtn && !voteSkipBtn.disabled) {
            voteSkipBtn.classList.add('state-approve');
            voteSkipBtn.classList.remove('state-waiting');
            voteSkipBtn.innerHTML = '<i class="fa-solid fa-handshake"></i><span class="skip-label">وافق؟</span>';
            ensurePulseKeyframe();
        }
    }
});

// 🆕 يضمن وجود keyframe النبضة (مرة واحدة)
function ensurePulseKeyframe() {
    if (document.getElementById('huroof-pulse-style')) return;
    const style = document.createElement('style');
    style.id = 'huroof-pulse-style';
    style.textContent = '@keyframes huroofPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}';
    document.head.appendChild(style);
}

socket.on('error_message', (msg) => {
    systemMessageDisplay.textContent = `⚠️ ${sanitizeHTML(msg)}`;
    systemMessageDisplay.style.color = '#f44336';
    if (currentTurnSid === socket.id && activeHexIndex !== null) {
        cells[activeHexIndex].classList.remove('active');
        activeHexIndex = null;
    }
});


// ============================================================
//  نظام الجولات (Best of 3)
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
//  تفاعلات اللاعب
// ============================================================

cells.forEach((cell, index) => {
    cell.addEventListener('click', () => {
        const myTurn = currentTurnColor
            ? (currentTurnColor === myColor)
            : (currentTurnSid === socket.id);
        if (
            myTurn &&
            !cell.classList.contains('green') &&
            !cell.classList.contains('orange') &&
            !cell.classList.contains('active')
        ) {
            socket.emit('huroof_select_hex', { roomCode: activeRoom(), hexIndex: index });
        }
    });
});

buzzerBtn.addEventListener('click', () => {
    if (!buzzerBtn.disabled) {
        buzzerBtn.disabled      = true;
        buzzerBtn.style.opacity = '0.5';
        socket.emit('huroof_buzz', { roomCode: activeRoom() });
    }
});

function submitAnswer() {
    if (!isMyTurnToAnswer) return;
    const ans = playerAnswerInput.value.trim();
    if (!ans) return;
    isMyTurnToAnswer         = false;
    submitAnswerBtn.disabled = true;
    socket.emit('huroof_submit_answer', { roomCode: activeRoom(), answer: ans });
}

submitAnswerBtn.addEventListener('click', submitAnswer);
playerAnswerInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') submitAnswer(); });
voteSkipBtn?.addEventListener('click', () => { if (!voteSkipBtn.disabled) socket.emit('huroof_vote_skip', { roomCode: activeRoom() }); });


// ============================================================
//  الانسحاب
// ============================================================
const surrenderModal = document.getElementById('surrenderModal');
const leaveBtn       = document.querySelector('.surrender-btn') || document.querySelector('a[href*="lobby"]');

leaveBtn?.addEventListener('click', (e) => { e.preventDefault(); surrenderModal.style.display = 'flex'; });

document.getElementById('cancelSurrenderBtn').onclick = () => { surrenderModal.style.display = 'none'; };

document.getElementById('confirmSurrenderBtn').onclick = () => {
    surrenderModal.style.display = 'none';
    socket.emit('huroof_surrender', { roomCode: activeRoom() });
    sessionStorage.removeItem('gameRoomCode');

    const opponentColor = myColor === 'green' ? 'orange' : 'green';
    document.getElementById('winner-color').textContent  = playersStatsData.opponent.name || (opponentColor === 'green' ? 'الأخضر' : 'البرتقالي');
    document.getElementById('winner-color').style.color  = opponentColor === 'green' ? '#4CAF50' : '#FF9800';
    document.getElementById('winner-reason').textContent = 'انسحبت من المباراة';
    document.getElementById('winner-overlay').style.display = 'flex';
};


// ============================================================
//  الشريط العلوي والملف الشخصي
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
// ⏱ المؤقتات والواجهة
// ============================================================

let _globalTimerLeft = 0;
let _playerTimerLeft = 0;

function startGlobalTimer(seconds) {
    clearInterval(globalTimerInterval);
    showGlobalTimer(true);
    globalTimerDisplay.textContent   = `⏳ ${seconds}`;
    _globalTimerLeft = seconds;
    globalTimerInterval = setInterval(() => {
        _globalTimerLeft--;
        globalTimerDisplay.textContent = `⏳ ${_globalTimerLeft}`;
        if (_globalTimerLeft <= 0) clearInterval(globalTimerInterval);
    }, 1000);
}

function startPlayerTimer(seconds) {
    clearInterval(playerTimerInterval);
    playerTimerDisplay.textContent = `⏱️ ${seconds}`;
    _playerTimerLeft = seconds;
    playerTimerInterval = setInterval(() => {
        _playerTimerLeft--;
        playerTimerDisplay.textContent = `⏱️ ${_playerTimerLeft}`;
        if (_playerTimerLeft <= 0) clearInterval(playerTimerInterval);
    }, 1000);
}

/** يُطبّق شكل الواجهة بناءً على من يملك الدور الحالي */
function applyTurnUI() {
    const turnBadge = document.getElementById('turn-status-badge');
    // نحدّد "دوري" باللون أولاً (مستقر)، ثم sid كاحتياط
    const isMyTurn = currentTurnColor
        ? (currentTurnColor === myColor)
        : (currentTurnSid === socket.id);
    if (isMyTurn) {
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

    showGlobalTimer(false);
    showBuzzer(false);
    buzzerBtn.disabled               = false;
    buzzerBtn.style.opacity          = '1';
    showAnswerSection(false);
    showSkipBtn(false);
    showAnswerContainer(false);
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
//  تأثيرات بصرية
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

// ============================================================
//  نظام الإبلاغ عن الخصم (زر "إبلاغ" في بروفايل الخصم)
// ============================================================
const reportModal     = document.getElementById('reportModal');
const cancelReportBtn = document.getElementById('cancelReportBtn');
const reportUserBtn   = document.querySelector('#modalActionButtons .report-user');
let reportSentThisMatch = false;

reportUserBtn?.addEventListener('click', () => {
    if (reportSentThisMatch) {
        showToast('⚠️ سبق وأبلغت عن الخصم في هذه المباراة');
        return;
    }
    // نغلق البروفايل ونفتح نافذة اختيار السبب
    document.getElementById('playerProfileModal').style.display = 'none';
    reportModal.style.display = 'flex';
});

cancelReportBtn?.addEventListener('click', () => {
    reportModal.style.display = 'none';
});

document.querySelectorAll('.report-reason').forEach(btn => {
    btn.addEventListener('click', () => {
        const reason = btn.dataset.reason;
        socket.emit('report_opponent', { roomCode, token, reason, target_id: _opponentUserId, game_mode: window.CURRENT_GAME });
        reportModal.style.display = 'none';
    });
});

socket.on('report_result', (data) => {
    showToast(data.ok ? '✅ ' + data.msg : '⚠️ ' + data.msg);
    if (data.ok) {
        reportSentThisMatch = true;  // بلاغ واحد لكل مباراة
    }
});

socket.on('chat_error', (data) => {
    showToast('🔇 ' + (data.msg || 'لا يمكنك إرسال رسائل'));
});

// ============================================================
//  الصداقة والحظر (أزرار بروفايل الخصم) — ديناميكية حسب الحالة
// ============================================================
const addFriendBtn = document.querySelector('#modalActionButtons .add-friend');
const blockUserBtn  = document.querySelector('#modalActionButtons .block-user');

// حالة العلاقة الحالية مع الخصم (تتغيّر مع الأفعال + من الخادم)
// 'friends' = صديق (زر: حذف صديق) | 'none' = غير صديق (زر: إضافة صديق)
// 'pending' = طلب مُرسَل (زر: في انتظار الرد) | blockState منفصل
let friendState = (sessionStorage.getItem('isFriendly') === '1') ? 'friends' : 'none';
let blockState  = false;

// تُستدعى من معالج room_joined لضبط الحالة حسب العلاقة الحقيقية من الخادم
function applyOpponentRelation(relation) {
    if (relation === 'friends') { friendState = 'friends'; blockState = false; }
    else if (relation === 'i_blocked') { blockState = true; friendState = 'none'; }
    else if (relation === 'they_blocked') { blockState = false; friendState = 'none'; }
    else if (relation === 'pending_outgoing') { friendState = 'pending'; blockState = false; }
    else if (relation === 'pending_incoming') { friendState = 'incoming'; blockState = false; }
    else { friendState = 'none'; blockState = false; }
    renderFriendButton();
    renderBlockButton();
}

function renderFriendButton() {
    if (!addFriendBtn) return;
    if (blockState) {
        // محظور → نخفي زر الصداقة (لا معنى لها أثناء الحظر)
        addFriendBtn.style.display = 'none';
        return;
    }
    addFriendBtn.style.display = '';
    if (friendState === 'friends') {
        addFriendBtn.innerHTML = '<i class="fa-solid fa-user-minus"></i> حذف صديق';
        addFriendBtn.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';  // أحمر
        addFriendBtn.style.boxShadow  = '0 4px 10px rgba(231, 76, 60, 0.4)';
        addFriendBtn.disabled = false;
        addFriendBtn.style.opacity = '1';
        addFriendBtn.style.cursor = 'pointer';
    } else if (friendState === 'pending') {
        addFriendBtn.innerHTML = '<i class="fa-solid fa-clock"></i> في انتظار الرد';
        addFriendBtn.style.background = 'rgba(255,255,255,0.12)';  // رمادي معطّل
        addFriendBtn.style.boxShadow  = 'none';
        addFriendBtn.disabled = true;
        addFriendBtn.style.opacity = '0.7';
        addFriendBtn.style.cursor = 'default';
    } else if (friendState === 'incoming') {
        addFriendBtn.innerHTML = '<i class="fa-solid fa-user-check"></i> قبول الطلب';
        addFriendBtn.style.background = 'linear-gradient(135deg, #2ecc71, #27ae60)';  // أخضر
        addFriendBtn.style.boxShadow  = '0 4px 10px rgba(46, 204, 113, 0.4)';
        addFriendBtn.disabled = false;
        addFriendBtn.style.opacity = '1';
        addFriendBtn.style.cursor = 'pointer';
    } else {
        addFriendBtn.innerHTML = '<i class="fa-solid fa-user-plus"></i> إضافة صديق';
        addFriendBtn.style.background = 'linear-gradient(135deg, #3498db, #2980b9)';  // أزرق
        addFriendBtn.style.boxShadow  = '0 4px 10px rgba(52, 152, 219, 0.4)';
        addFriendBtn.disabled = false;
        addFriendBtn.style.opacity = '1';
        addFriendBtn.style.cursor = 'pointer';
    }
}

function renderBlockButton() {
    if (!blockUserBtn) return;
    if (blockState) {
        blockUserBtn.innerHTML = '<i class="fa-solid fa-unlock"></i> رفع الحظر';
        blockUserBtn.style.background = 'linear-gradient(135deg, #e67e22, #d35400)';  // برتقالي
    } else {
        blockUserBtn.innerHTML = '<i class="fa-solid fa-ban"></i> حظر';
        blockUserBtn.style.background = '';  // اللون الافتراضي
    }
}

renderFriendButton();
renderBlockButton();

let _pendingFriendAction = null;  // 'add' أو 'remove' — لتحديث الحالة بدقة

addFriendBtn?.addEventListener('click', () => {
    if (blockState || friendState === 'pending') return;  // معطّل أثناء الحظر أو انتظار الرد
    if (friendState === 'friends') {
        _pendingFriendAction = 'remove';
        socket.emit('remove_friend_opponent', { roomCode, token, target_id: _opponentUserId });
    } else if (friendState === 'incoming') {
        // الخصم أرسل لي طلباً → أقبله
        if (_opponentUserId) {
            socket.emit('respond_friend_request', { token, requester_id: _opponentUserId, accept: true });
        }
        friendState = 'friends';
        renderFriendButton();
        showToast('✅ تمت إضافة الصديق');
    } else {
        _pendingFriendAction = 'add';
        socket.emit('friend_request_opponent', { roomCode, token, target_id: _opponentUserId });
    }
    document.getElementById('playerProfileModal').style.display = 'none';
});
blockUserBtn?.addEventListener('click', () => {
    if (blockState) {
        socket.emit('unblock_opponent', { roomCode, token, target_id: _opponentUserId });
    } else {
        socket.emit('block_opponent', { roomCode, token, target_id: _opponentUserId });
    }
    document.getElementById('playerProfileModal').style.display = 'none';
});

socket.on('friend_result', (data) => {
    showToast((data.ok ? '✅ ' : '⚠️ ') + (data.msg || ''));
    if (data.ok && _pendingFriendAction) {
        // نحدّث الحالة حسب الفعل الذي أرسلناه (دقيق، لا يعتمد على نص الرسالة)
        friendState = (_pendingFriendAction === 'remove') ? 'none' : 'pending';
        renderFriendButton();
    }
    _pendingFriendAction = null;
});
socket.on('block_result', (data) => {
    showToast((data.ok ? '🚫 ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) {
        blockState = true;
        friendState = 'none';  // الحظر يلغي الصداقة
        renderBlockButton();
        renderFriendButton();
    }
});
socket.on('unblock_result', (data) => {
    showToast((data.ok ? '🔓 ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) {
        blockState = false;
        renderBlockButton();
        renderFriendButton();
    }
});

// 🆕 الخصم حذفني من أصدقائه → أُحدّث زري إلى "إضافة صديق"
socket.on('opponent_unfriended', () => {
    friendState = 'none';
    renderFriendButton();
});

// 🆕 الخصم قبِل طلب صداقتي → أُحدّث زري إلى "حذف صديق"
socket.on('opponent_accepted_friend', () => {
    friendState = 'friends';
    renderFriendButton();
    showToast('✅ قبل طلب صداقتك!');
});
socket.on('friend_request_received', (data) => {
    showToast('👋 ' + sanitizeHTML(data.from || 'لاعب') + ' أرسل لك طلب صداقة');
});

// 🆕 toast تفاعلي لحظي لطلب الصداقة داخل المباراة (غير معطّل، لا يوقف اللعب)
socket.on('ingame_friend_request', (data) => {
    if (!data || !data.requesterId) return;
    showFriendRequestToast(data.requesterId, sanitizeHTML(data.requesterName || 'لاعب'));
    // نحدّث زر بروفايل الخصم إلى "قبول الطلب" (طلب وارد منه)
    _opponentUserId = data.requesterId;
    if (friendState !== 'friends' && !blockState) {
        friendState = 'incoming';
        renderFriendButton();
    }
});

function showFriendRequestToast(requesterId, requesterName) {
    // نزيل أي toast صداقة سابق (نعرض واحداً فقط)
    const old = document.getElementById('ingameFriendToast');
    if (old) old.remove();

    const toast = document.createElement('div');
    toast.id = 'ingameFriendToast';
    toast.style.cssText = `
        position: fixed; top: 90px; right: 20px; transform: translateY(-20px);
        background: linear-gradient(135deg, #2c3e50, #1a252f);
        border: 1px solid rgba(74,144,226,0.5); border-radius: 14px;
        padding: 12px 16px; z-index: 2000; box-shadow: 0 8px 28px rgba(0,0,0,0.5);
        display: flex; align-items: center; gap: 10px; max-width: 320px;
        opacity: 0; transition: opacity .3s ease, transform .3s ease; font-family: inherit;`;
    toast.innerHTML = `
        <i class="fa-solid fa-user-plus" style="color:#4a90e2; font-size:18px;"></i>
        <span style="color:#fff; font-size:13px;">${requesterName} يريد إضافتك صديقاً</span>
        <button id="frToastAccept" style="background:linear-gradient(135deg,#2ecc71,#27ae60); color:#fff; border:none; border-radius:8px; padding:6px 12px; cursor:pointer; font-family:inherit; font-size:12px;">قبول</button>
        <button id="frToastReject" style="background:rgba(255,255,255,0.12); color:#ccc; border:none; border-radius:8px; padding:6px 10px; cursor:pointer; font-family:inherit; font-size:12px;">لاحقاً</button>`;
    document.body.appendChild(toast);
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });

    let dismissed = false;
    const dismiss = () => {
        if (dismissed) return;
        dismissed = true;
        clearTimeout(autoTimer);
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-20px)';
        setTimeout(() => toast.remove(), 300);
    };

    document.getElementById('frToastAccept').addEventListener('click', () => {
        socket.emit('respond_friend_request', { token, requester_id: requesterId, accept: true });
        showToast('✅ تمت إضافة الصديق');
        // 🆕 نحدّث زر بروفايل الخصم إلى "حذف صديق" (صرنا أصدقاء)
        friendState = 'friends';
        blockState = false;
        if (typeof renderFriendButton === 'function') renderFriendButton();
        dismiss();
    });
    document.getElementById('frToastReject').addEventListener('click', () => {
        // "لاحقاً" لا يرفض الطلب — يبقى في تبويب الطلبات (النظام الحالي محفوظ)
        dismiss();
    });

    // يختفي تلقائياً بعد 8 ثوانٍ (الطلب يبقى في تبويب الطلبات)
    const autoTimer = setTimeout(dismiss, 8000);
}
socket.on('leaver_penalty', (data) => {
    showToast(data.msg);
});

// ----------------------------------------
//  الرسائل الجاهزة داخل اللعبة (Quick Chat)
// زر عائم يفتح لوحة العبارات المعتمدة. يرسل phraseId فقط (لا نص حر).
// ----------------------------------------
(function initIngameQuickChat() {
    const btn = document.getElementById('gameQuickChatBtn');
    if (btn && window.QuickChat) {
        QuickChat.init({
            socket,
            triggerBtn: btn,
            event: 'send_room_chat_message',
            extra: () => ({ roomCode }),  // رسالة داخل غرفة المباراة الحالية
            context: 'game',              // 🆕 عبارات المباراة (تنافسية) لا اللوبي
            game: 'huroof',               // لجلب عبارات حروف المشتراة
        });
    }

    // عرض الرسائل الواردة كفقاعة عائمة فوق أفاتار المُرسِل
    socket.on('new_room_chat_message', (msg) => {
        if (!msg || !msg.text) return;
        const mine = msg.senderSid === socket.id;
        showChatBubble(msg.text, mine);
    });

    function showChatBubble(text, mine) {
        // نعرضها قرب أفاتار اللاعب (يمين=أنا، يسار=الخصم في الواجهة RTL)
        const anchor = mine
            ? document.getElementById('myProfileBtn')
            : document.getElementById('opponentProfileBtn');
        if (!anchor) return;
        const bubble = document.createElement('div');
        bubble.className = 'qc-bubble' + (mine ? ' mine' : '');
        bubble.textContent = text;
        anchor.style.position = 'relative';
        anchor.appendChild(bubble);
        setTimeout(() => bubble.classList.add('show'), 10);
        setTimeout(() => {
            bubble.classList.remove('show');
            setTimeout(() => bubble.remove(), 250);
        }, 3500);
    }
})();


// ============================================================
//  نظام المساعدات (3 خانات)
// ============================================================
(function initHelps() {
    let _helpsLoadout = [];
    let _helpsCatalog = [];
    let _helpsUsed = new Set();
    let _questionActive = false;  // هل يوجد سؤال نشط (حرف مختار)؟
    let _inventory = {};          // {help_id: quantity}
    let _devMode = false;
    let _slots = 3;
    let _fourthSlotLevel = 10;

    function _helpById(id) {
        return _helpsCatalog.find(h => h.id === id);
    }

    function _owns(id) {
        return _devMode || (_inventory[id] || 0) > 0;
    }

    function renderHelpSlots() {
        const container = document.getElementById('helpSlots');
        if (!container) return;
        container.innerHTML = '';
        _helpsLoadout.forEach(id => {
            const h = _helpById(id);
            if (!h) return;
            const used = _helpsUsed.has(id);
            const owned = _owns(id);
            // ⏱️ القفل حسب توقيت المساعدة: post = يلزم سؤال معروض،
            // pre = قبل اختيار الحرف فقط (كانت مقفولة بوقتها الصحيح — bug عكسي)
            const timing = h.timing || 'post';
            const locked = (timing === 'pre') ? _questionActive : !_questionActive;
            const qty = _devMode ? '∞' : (_inventory[id] || 0);
            const btn = document.createElement('button');
            let cls = 'help-slot';
            if (used) cls += ' used';
            else if (!owned) cls += ' unowned';
            else if (locked) cls += ' locked';
            btn.className = cls;
            btn.disabled = used || locked || !owned;
            btn.title = !owned ? `${h.name} — لا تملكها (اشترها من المتجر)`
                       : (locked ? `${h.name} — ${timing === 'pre' ? 'تُستخدم قبل اختيار الحرف' : 'اختر حرفاً أولاً'}`
                                 : h.name + ' — ' + h.desc);
            btn.innerHTML = `
                <span class="rarity-dot rarity-${h.rarity}"></span>
                <span class="help-icon">${h.icon}</span>
                <span class="help-name">${sanitizeHTML(h.name)}</span>
                <span class="help-qty">${qty}</span>`;
            btn.addEventListener('click', () => useHelp(id));
            container.appendChild(btn);
        });
    }

    function useHelp(id) {
        if (_helpsUsed.has(id)) return;
        socket.emit('huroof_use_help', { roomCode: activeRoom(), helpId: id });
    }

    function showHelpToast(msg) {
        const old = document.getElementById('activeHelpToast');
        if (old) old.remove();
        const t = document.createElement('div');
        t.id = 'activeHelpToast';
        t.className = 'help-toast';
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(() => { t.remove(); }, 3500);
    }

    // طلب الكتالوج عند بدء المباراة
    socket.on('connect', () => {
        setTimeout(() => socket.emit('huroof_get_helps_catalog', { roomCode: activeRoom() }), 800);
    });

    socket.on('huroof_helps_catalog', (data) => {
        if (!data) return;
        _helpsLoadout = data.loadout || [];
        _helpsCatalog = data.catalog || [];
        _helpsUsed = new Set(data.used || []);
        _inventory = data.inventory || {};
        _devMode = !!data.devMode;
        _slots = data.slots || 3;
        _fourthSlotLevel = data.fourthSlotLevel || 10;
        // الخانة الرابعة: لو مفتوحة، نضيف مساعدة يملكها اللاعب وليست في التحميل الأساسي
        if (_slots >= 4) {
            const owned = Object.keys(_inventory);
            const extra = owned.find(id => !_helpsLoadout.includes(id));
            if (extra && _helpsLoadout.length < 4) _helpsLoadout = [..._helpsLoadout, extra];
        }
        renderHelpSlots();
    });

    // تفعيل الخانات عند بدء سؤال (حرف مختار)، وتعطيلها عند انتهائه
    socket.on('huroof_new_question', () => { _questionActive = true; renderHelpSlots(); });
    socket.on('huroof_hex_locked', () => { _questionActive = true; renderHelpSlots(); });
    socket.on('huroof_round_over', () => { _questionActive = false; renderHelpSlots(); });
    socket.on('huroof_match_over', () => { _questionActive = false; renderHelpSlots(); });
    // عند العودة لاختيار حرف جديد (انتهى السؤال السابق)
    socket.on('huroof_turn_changed', () => { _questionActive = false; renderHelpSlots(); });

    // نتيجة استخدام مساعدتي
    //  اختيار التصنيف: الخادم يرسل قائمة التصنيفات لنعرضها
    socket.on('huroof_choose_category_options', (data) => {
        if (!data || !Array.isArray(data.categories) || !data.categories.length) {
            showHelpToast('⚠️ لا توجد تصنيفات متاحة');
            return;
        }
        const old = document.getElementById('catPickerModal');
        if (old) old.remove();
        const modal = document.createElement('div');
        modal.id = 'catPickerModal';
        modal.style.cssText = 'position:fixed;inset:0;z-index:6000;background:rgba(0,0,0,0.75);display:flex;align-items:center;justify-content:center;';
        const box = document.createElement('div');
        box.style.cssText = 'background:#1a1a2e;border:1px solid #4a90e2;border-radius:16px;padding:24px;max-width:420px;width:92%;text-align:center;';
        box.innerHTML = '<h3 style="color:#fff;margin-bottom:6px;">📚 اختر تصنيف سؤالك القادم</h3><p style="color:#aaa;font-size:13px;margin-bottom:16px;">سيكون سؤالك التالي من هذا المجال.</p>';
        const grid = document.createElement('div');
        grid.style.cssText = 'display:grid;grid-template-columns:repeat(2,1fr);gap:10px;';
        data.categories.forEach(cat => {
            const btn = document.createElement('button');
            btn.textContent = cat;
            btn.style.cssText = 'background:rgba(74,144,226,0.15);border:1px solid rgba(74,144,226,0.4);color:#fff;border-radius:10px;padding:12px;cursor:pointer;font-family:inherit;font-size:14px;';
            btn.addEventListener('click', () => {
                socket.emit('huroof_use_help', { roomCode: activeRoom(), helpId: 'choose_category', category: cat });
                modal.remove();
            });
            grid.appendChild(btn);
        });
        box.appendChild(grid);
        const cancel = document.createElement('button');
        cancel.textContent = 'إلغاء';
        cancel.style.cssText = 'margin-top:16px;background:transparent;border:1px solid #555;color:#aaa;border-radius:10px;padding:8px 20px;cursor:pointer;font-family:inherit;';
        cancel.addEventListener('click', () => modal.remove());
        box.appendChild(cancel);
        modal.appendChild(box);
        document.body.appendChild(modal);
    });

    socket.on('huroof_help_result', (data) => {
        if (!data) return;
        if (!data.ok) {
            showHelpToast('⚠️ ' + (data.msg || 'تعذّر استخدام المساعدة'));
            return;
        }
        // المساعدة نجحت → نعلّمها مستخدمة + ننقص المخزون محلياً
        if (data.helpId) {
            _helpsUsed.add(data.helpId);
            if (!_devMode && _inventory[data.helpId]) {
                _inventory[data.helpId] = Math.max(0, _inventory[data.helpId] - 1);
            }
        }
        renderHelpSlots();

        // ===== تطبيق التأثير =====
        if (data.effect === 'extend_time') {
            // نزامن العدّاد مع القيمة الجديدة من الخادم (فعّالة حقاً)
            const newTotal = data.new_total;
            if (typeof newTotal === 'number') {
                if (typeof _globalTimerLeft !== 'undefined' && _globalTimerLeft > 0) {
                    _globalTimerLeft = newTotal;
                    if (globalTimerDisplay) globalTimerDisplay.textContent = `⏳ ${newTotal}`;
                }
                if (typeof _playerTimerLeft !== 'undefined' && _playerTimerLeft > 0) {
                    _playerTimerLeft = newTotal;
                    if (playerTimerDisplay) playerTimerDisplay.textContent = `⏱️ ${newTotal}`;
                }
            }
            showHelpToast(`⏱️ +${data.seconds || 10} ثانية لوقتك`);
        }
        else if (data.effect === 'count_letters') {
            showHelpToast(`🔢 عدد حروف الإجابة: ${data.count}`);
        }
        else if (data.effect === 'reveal') {
            // كشف معلومة (حرف/تصنيف/نصف) — نعرضها في toast أطول قليلاً
            showHelpToast('💡 ' + (data.msg || ''));
        }
        else if (data.effect === 'skip_letter') {
            showHelpToast('⏭️ ' + (data.msg || 'تم التخطّي'));
        }
        else if (data.effect === 'change_question') {
            showHelpToast('🔄 ' + (data.msg || 'سؤال جديد...'));
        }
        else {
            showHelpToast(data.msg || 'تم');
        }
    });

    // الخصم استخدم مساعدة (شفافية)
    socket.on('huroof_opponent_used_help', (data) => {
        if (!data) return;
        showHelpToast(`🔔 الخصم استخدم: ${sanitizeHTML(data.name || 'مساعدة')}`);
    });
})();
