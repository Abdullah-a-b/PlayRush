/*  من أنا — منطق العميل */
(function () {
  'use strict';
  window.CURRENT_GAME = 'whoami';

  const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });
  window.socket = socket;  // لنظام الإيموجيات (game_emojis.js)
  const roomCode     = sessionStorage.getItem('gameRoomCode');
  const token        = localStorage.getItem('token') || sessionStorage.getItem('token');
  const playerName   = sessionStorage.getItem('playerName')   || sessionStorage.getItem('username') || 'لاعب';
  const playerAvatar = sessionStorage.getItem('playerAvatar') || sessionStorage.getItem('avatar')   || '';
  let mySid = null;

  if (!token || !roomCode) { window.location.href = '../lobby.html'; return; }

  const $ = (id) => document.getElementById(id);
  const hintsStage      = $('hintsStage');
  const buzzBtn         = $('buzzBtn');
  const answerBox       = $('answerBox');
  const answerInput     = $('answerInput');
  const answerTimerEl   = $('answerTimer');
  const statusMsg       = $('statusMsg');
  const revealTimerWrap = $('revealTimerWrap');
  const revealTimerBar  = $('revealTimerBar');
  let answerCountdown = null;

  // ===== المساعدات =====
  let helpsCatalog = {};
  let myLoadout = [];
  let myInventory = {};
  let devModeHelps = false;
  const helpsUsedLocal = new Set();
  let myShieldActive = false;
  let myPointsLocked = false;
  let phase = 'revealing';   // revealing | buzzed — لتحديد المتاح
  let iBuzzed = false;

  function pickMine(map) {
    if (!map) return undefined;
    if (mySid && (mySid in map)) return map[mySid];
    return undefined;
  }
  function syncHelpsState(d) {
    if (!d) return;
    const used = pickMine(d.helps_used);
    if (Array.isArray(used)) used.forEach((h) => helpsUsedLocal.add(h));
    const sh = pickMine(d.shield_active);
    if (sh !== undefined) myShieldActive = !!sh;
    const lp = pickMine(d.locked_points);
    if (lp !== undefined && lp !== null) myPointsLocked = true;
  }
  function renderHelpsBar() {
    const bar = $('whoamiHelpsBar');
    if (!bar) return;
    bar.innerHTML = '';
    myLoadout.forEach((hid) => {
      const h = helpsCatalog[hid];
      if (!h) return;
      const qty = devModeHelps ? '∞' : String(myInventory[hid] || 0);
      const depleted = (!devModeHelps && (myInventory[hid] || 0) <= 0);
      const timing = h.timing || 'revealing';
      // «تمديد الجرس» يظهر متاحاً فقط بعد جرسك؛ البقية أثناء الكشف
      const wrongPhase = (timing === 'buzzed') ? !iBuzzed : (phase !== 'revealing');
      const usedUp = helpsUsedLocal.has(hid);
      const btn = document.createElement('button');
      btn.className = 'bank-help-btn'
        + (usedUp ? ' used' : '')
        + ((depleted || wrongPhase) ? ' depleted' : '');
      btn.title = `${h.name}: ${h.desc}`;
      btn.innerHTML = `<span class="hicon">${h.icon}</span>`
        + `<span class="hqty">${qty}</span>`;
      btn.addEventListener('click', () => {
        if (usedUp || depleted) return;
        if (wrongPhase) {
          showToast(timing === 'buzzed'
            ? '⏱️ تُستخدم بعد ضغطك الجرس'
            : '🎯 تُستخدم أثناء عرض المعلومات');
          return;
        }
        socket.emit('whoami_use_help', { roomCode, helpId: hid, token });
      });
      bar.appendChild(btn);
    });
  }

  // ===== أدوات =====
  function getValidAvatar(src) {
    if (!src || String(src).trim() === '') return '../assets/avatars/avatar_1.svg';
    let v = String(src).trim();
    const staleMatch = v.match(/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/.*)$/i);
    if (staleMatch) {
      const path = staleMatch[3];
      if (path.startsWith('/uploads')) return (typeof API_URL !== 'undefined' ? API_URL : '') + path;
      const fn = path.split('/').pop();
      return '../assets/avatars/' + fn;
    }
    if (v.startsWith('/uploads')) return (typeof API_URL !== 'undefined' ? API_URL : '') + v;
    if (v.startsWith('http') || v.startsWith('data:')) return v;
    if (v.startsWith('../') || v.startsWith('/')) { const n = v.split('/').pop(); return '../assets/avatars/' + (n.includes('.') ? n : n + '.svg'); }
    const name = v.split('/').pop();
    return '../assets/avatars/' + (name.includes('.') ? name : name + '.svg');
  }

  // ===== أنيميشن استعد 3-2-1 (موحّد) =====
  function playReadyAnimation(cb) {
    const overlay = document.getElementById('readyOverlay');
    const countEl = document.getElementById('readyCount');
    const titleEl = document.getElementById('readyTitle');
    if (!overlay) { if (cb) cb(); return; }
    overlay.style.display = 'flex';
    if (titleEl) titleEl.textContent = 'استعد!';
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
  let _readyShown = false;


  function renderHints(hints, animateLast) {
    hintsStage.innerHTML = '';
    if (!hints || !hints.length) {
      hintsStage.innerHTML = '<div class="clubs-placeholder">جارٍ التحميل…</div>';
      return;
    }
    hints.forEach((hint, i) => {
      const card = document.createElement('div');
      card.className = 'hint-card';
      if (animateLast && i === hints.length - 1) card.classList.add('hint-reveal-anim');
      const num = document.createElement('div');
      num.className = 'hint-num'; num.textContent = i + 1;
      const txt = document.createElement('div');
      txt.textContent = hint;
      card.appendChild(num); card.appendChild(txt);
      hintsStage.appendChild(card);
    });
    hintsStage.scrollTop = hintsStage.scrollHeight;
  }

  function setStatus(text, type) {
    statusMsg.textContent = text || '';
    statusMsg.className = 'career-status-msg' + (type ? ' ' + type : '');
  }

  function updateScores(scores) {
    if (!scores) return;
    const oppSid = Object.keys(scores).find((s) => s !== mySid);
    $('myScore').textContent = scores[mySid] ?? 0;
    $('opponentScore').textContent = scores[oppSid] ?? 0;
  }

  function updateProgress(index, total, tiebreaker) {
    document.querySelectorAll('.progress-dot').forEach((d, i) => {
      d.classList.toggle('done', i < index - 1);
      d.classList.toggle('active', i === index - 1);
    });
    const tb = $('tiebreakerBadge');
    if (tb) tb.style.display = tiebreaker ? 'block' : 'none';
  }

  function renderStrikeRow(el, count) {
    if (!el) return;
    el.innerHTML = '';
    for (let i = 0; i < 2; i++) {
      const x = document.createElement('span');
      x.className = 'strike-x' + (i < count ? ' filled' : '');
      x.textContent = '✗'; el.appendChild(x);
    }
  }

  function updateStrikes(strikes) {
    //  سترايكاتك + سترايكات خصمك (2 لكل لاعب) — مرئية للطرفين
    // حتى تعرف متى تغامر بالجرس ومتى خصمك على الحافة.
    strikes = strikes || {};
    const myStrk = strikes[mySid] || 0;
    let oppStrk = 0;
    for (const k in strikes) { if (k !== mySid) oppStrk = strikes[k] || 0; }
    renderStrikeRow($('myStrikes'), myStrk);
    renderStrikeRow($('oppStrikes'), oppStrk);
  }

  function startRevealBar(seconds) {
    revealTimerWrap.style.display = 'block';
    revealTimerBar.style.transition = 'none';
    revealTimerBar.style.width = '100%';
    void revealTimerBar.offsetWidth;
    revealTimerBar.style.transition = `width ${seconds}s linear`;
    revealTimerBar.style.width = '0%';
  }
  function stopRevealBar() { revealTimerWrap.style.display = 'none'; }

  // ===== الاتصال والانضمام =====
  socket.on('connect', () => {
    mySid = socket.id;
    socket.emit('join_room', { room_code: roomCode, token, player_name: playerName, avatar: playerAvatar });
    socket.emit('get_help_loadout', { token, game: 'whoami', roomCode });
  });

  // ===== مساعدات: التشكيلة والمخزون =====
  socket.on('help_loadout_data', (d) => {
    if (!d || d.game !== 'whoami') return;
    helpsCatalog = {};
    (d.catalog || []).forEach((h) => { helpsCatalog[h.id] = h; });
    myLoadout = d.loadout || d.defaultLoadout || [];
    myInventory = d.inventory || {};
    devModeHelps = !!d.devMode;
    renderHelpsBar();
  });

  socket.on('whoami_help_result', (d) => {
    if (!d) return;
    if (!d.ok) { showToast('⚠️ ' + (d.msg || '')); return; }
    helpsUsedLocal.add(d.helpId);
    if (!devModeHelps && myInventory[d.helpId]) {
      myInventory[d.helpId] = Math.max(0, myInventory[d.helpId] - 1);
    }
    if (d.helpId === 'w_strike_shield') myShieldActive = true;
    if (d.helpId === 'w_lock_points') myPointsLocked = true;
    renderHelpsBar();
    if (d.info) setStatus(d.info, 'reveal');
  });

  // تمديد الجرس: مؤقّت نافذة جديد
  socket.on('whoami_buzz_extended', (d) => {
    if (!d) return;
    if (d.sid === mySid) {
      setStatus(`⏱️ +${d.added} ثوانٍ لنافذتك!`, 'my-turn');
      openAnswerBox(d.newWindow);
    } else {
      showToast('⏱️ الخصم مدّد نافذته');
      startRevealBar(d.newWindow || 15);
    }
  });

  // درع مُفعّل (إشعار للطرفين)
  socket.on('whoami_shield_on', (d) => {
    if (d && d.sid !== mySid) showToast('🛡️ الخصم فعّل درع السترايك');
  });

  // درع امتص السترايك
  socket.on('whoami_shield_absorbed', (d) => {
    if (!d) return;
    const mine = (d.sid === mySid);
    if (mine) myShieldActive = false;
    setStatus(mine ? '🛡️ درعك امتص الخطأ — لا سترايك!'
                   : `🛡️ درع ${d.name || 'الخصم'} امتص خطأه`, 'reveal');
    if (d.shield_active) { const sh = d.shield_active[mySid]; if (sh !== undefined) myShieldActive = !!sh; }
    answerBox.style.display = 'none';
    renderHelpsBar();
  });

  // بيانات اللاعبين (نفس بنية حروف بالضبط)
  let playersStatsData = {
    me:       { name: playerName, avatar: '../assets/avatars/avatar_1.svg', flag: '../assets/flags/SA.svg', rank: '-', whoami: {wins:0,losses:0,total:0}, global: {wins:0,losses:0,total:0} },
    opponent: { name: 'الخصم',    avatar: '../assets/avatars/avatar_2.svg', flag: '../assets/flags/SA.svg', rank: '-', whoami: {wins:0,losses:0,total:0}, global: {wins:0,losses:0,total:0} },
  };
  let _opponentUserId = null;

  
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
    const players = data.players || [];
    const me       = players.find(p => p.sid === socket.id || p.name === playerName);
    const opponent = players.find(p => p.sid !== socket.id && p.name !== playerName);

    if (me?.stats)       playersStatsData.me       = { ...me.stats,       avatar: getValidAvatar(me.stats.avatar) };
    if (opponent?.stats) playersStatsData.opponent = { ...opponent.stats, avatar: getValidAvatar(opponent.stats.avatar) };

    $('myName').textContent       = playersStatsData.me.name;
    $('myAvatarImg').src          = playersStatsData.me.avatar;
    $('opponentName').textContent = playersStatsData.opponent.name;
    $('opponentAvatarImg').src    = playersStatsData.opponent.avatar;
    // 🎮 كشف التطابق بين اللاعبين
    if (playersStatsData.opponent && playersStatsData.opponent.name) {
      showMatchReveal(
        playersStatsData.me.name, playersStatsData.me.avatar,
        playersStatsData.opponent.name, playersStatsData.opponent.avatar
      );
    }
    // 🎮 كشف التطابق بين اللاعبين
    if (playersStatsData.opponent && playersStatsData.opponent.name) {
      showMatchReveal(
        playersStatsData.me.name, playersStatsData.me.avatar,
        playersStatsData.opponent.name, playersStatsData.opponent.avatar
      );
    }

    //  حالة الصداقة/الحظر من الخادم (نفس حروف)
    if (typeof data.opponent_user_id !== 'undefined') _opponentUserId = data.opponent_user_id;
    if (typeof data.opponent_relation === 'string' && typeof applyOpponentRelation === 'function') {
      applyOpponentRelation(data.opponent_relation);
    }
  });

  socket.on('whoami_ready', () => {
    setStatus('بدأت المباراة!', '');
    if (!_readyShown) { _readyShown = true; playReadyAnimation(); }
  });

  // ===== أحداث اللعبة =====
  socket.on('whoami_new_character', (d) => {
    updateScores(d.scores);
    updateProgress(d.charIndex, d.totalCharacters, d.tiebreaker);
    $('statusText').textContent = '🎭 ' + (d.category || 'شخصية غامضة — من أنا؟');
    $('statusBanner').className = 'player-status-banner current';
    setStatus('شخصية جديدة — المعلومات تبدأ غامضة ثم تتضح…', '');
    buzzBtn.disabled = false;
    answerBox.style.display = 'none';
    updateStrikes({});
    $('pointsValue').textContent = '4';
    $('pointsIndicator').className = 'points-indicator';
    // الدرع والقفل يُصفَّران كل شخصية (لكن helps_used يبقى للمباراة)
    myShieldActive = false; myPointsLocked = false;
    phase = 'revealing'; iBuzzed = false;
    renderHelpsBar();
  });

  socket.on('whoami_reveal_state', (d) => {
    renderHints(d.hints, true);
    updateScores(d.scores);
    updateStrikes(d.strikes);
    if (d.category) {
      $('statusText').textContent = '🎭 ' + d.category;
      $('statusBanner').className = 'player-status-banner current';
    }
    $('pointsValue').textContent = d.pointsIfAnswer;
    $('pointsIndicator').className = 'points-indicator' + (d.pointsIfAnswer <= 1 ? ' one-point' : '');
    updateProgress(d.charIndex, d.totalCharacters, d.tiebreaker);
    if (d.hintsJustCompleted) setStatus('آخر معلومة! نافذة أخيرة قبل كشف الإجابة…', 'reveal');
    // مدة الشريط: استئناف بعد خطأ / نافذة معلنة من الخادم / افتراضي 10
    let secs = 10;
    if (d.resumed && d.resumeSeconds) secs = d.resumeSeconds;
    else if (d.windowSeconds) secs = d.windowSeconds;
    startRevealBar(secs);
    const myStrk = (d.strikes && d.strikes[mySid]) || 0;
    buzzBtn.disabled = (myStrk >= 2) || (d.buzzedPlayer != null && d.buzzedPlayer !== undefined);
    answerBox.style.display = 'none';
    phase = 'revealing'; iBuzzed = false;
    syncHelpsState(d);
    renderHelpsBar();
  });

  socket.on('whoami_buzzed', (d) => {
    buzzBtn.disabled = true;
    phase = 'buzzed';
    if (d.sid === mySid) {
      iBuzzed = true;
      stopRevealBar();
      setStatus('🔔 دورك! اكتب إجابتك', 'my-turn');
      openAnswerBox(d.answerWindow);
    } else {
      iBuzzed = false;
      // الخصم يكتب — نعرض عدّاده حتى لا تبدو الشاشة مجمّدة
      setStatus('⏳ الخصم يكتب…', 'opp-turn');
      startRevealBar(d.answerWindow || 10);
    }
    renderHelpsBar();
  });

  function openAnswerBox(seconds) {
    answerBox.style.display = 'flex';
    answerInput.value = ''; answerInput.focus();
    let t = Math.round(seconds); answerTimerEl.textContent = t;
    clearInterval(answerCountdown);
    answerCountdown = setInterval(() => {
      t--; answerTimerEl.textContent = Math.max(0, t);
      if (t <= 0) { clearInterval(answerCountdown); answerBox.style.display = 'none'; }
    }, 1000);
  }

  socket.on('whoami_answer_result', (d) => {
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
    updateScores(d.scores);
    const who = d.sid === mySid ? 'أنت' : 'الخصم';
    if (d.correct) {
      setStatus(`✅ ${who} أجاب صح: ${d.name} (+${d.points})`, 'correct');
    } else {
      setStatus(`❌ ${who}: إجابة خاطئة`, 'wrong');
    }
  });

  //  الحكم الذكي يراجع إجابة حدّية — المؤقّت متوقف حتى الحسم
  socket.on('whoami_judging', (d) => {
    const mine = d && d.sid === mySid;
    setStatus(mine ? '⚖️ الحكم الذكي يراجع إجابتك…'
                   : '⚖️ الحكم الذكي يراجع إجابة الخصم…', 'reveal');
  });

  socket.on('whoami_strike', (d) => {
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
    updateStrikes(d.strikes);
    const who = d.sid === mySid ? 'أنت' : 'الخصم';
    setStatus(`✗ ${who}: ${d.timedOut ? 'انتهى الوقت' : 'إجابة خاطئة'} (${d.count}/${d.maxStrikes})`, 'wrong');
  });

  socket.on('whoami_reveal_answer', (d) => {
    setStatus(`🎭 الشخصية كانت: ${d.name}`, 'reveal');
    stopRevealBar();
    buzzBtn.disabled = true;
  });
  socket.on('whoami_tiebreaker', (d) => {
    updateScores(d.scores);
    const tb = $('tiebreakerBadge');
    if (tb) tb.style.display = 'block';
    setStatus('⚡ تعادل! شخصية كسر التعادل', 'tiebreak');
  });

  socket.on('whoami_match_over', (d) => {
    stopRevealBar();
    clearInterval(answerCountdown);
    buzzBtn.disabled = true;
    answerBox.style.display = 'none';
    const iWon = d.winner === mySid;
    const isDraw = !d.winner;
    $('winIcon').textContent  = isDraw ? '🤝' : (iWon ? '🏆' : '😔');
    $('winTitle').textContent = isDraw ? 'تعادل' : (iWon ? 'فزت!' : 'خسرت');
    const sc = d.scores || {};
    const oppSid = Object.keys(sc).find((s) => s !== mySid);
    $('winSubtitle').textContent = `النتيجة: ${sc[mySid] ?? 0} - ${sc[oppSid] ?? 0}`;
    $('winMessageOverlay').style.display = 'flex';
  });

  // ===== الرسائل الجاهزة — نفس نمط حروف بالضبط =====
  (function initIngameQuickChat() {
    const btn = $('gameQuickChatBtn');
    if (btn && window.QuickChat) {
      QuickChat.init({
        socket,
        triggerBtn: btn,
        event: 'send_room_chat_message',
        extra: () => ({ roomCode }),
        context: 'game',
        game: 'whoami',
      });
    }
  
  })();

  // فقاعة عائمة فوق أفاتار المُرسِل (نفس حروف)
  socket.on('new_room_chat_message', (msg) => {
    if (!msg || !msg.text) return;
    const mine = msg.senderSid === socket.id;
    showChatBubble(msg.text, mine);
  });

  function showChatBubble(text, mine) {
    const anchor = mine ? $('myProfileBtn') : $('opponentProfileBtn');
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

  // ===== تفاعلات =====
  buzzBtn.addEventListener('click', () => {
    if (buzzBtn.disabled) return;
    buzzBtn.disabled = true;
    socket.emit('whoami_buzz', { roomCode });
  });

  function submitAnswer() {
    const ans = answerInput.value.trim();
    if (!ans) return;
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
    setStatus('⏳ جارٍ التحقق…', 'reveal');
    socket.emit('whoami_submit_answer', { roomCode, answer: ans });
  }
  $('submitAnswerBtn').addEventListener('click', submitAnswer);
  answerInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitAnswer(); });

  $('surrenderBtn').addEventListener('click', () => { $('surrenderModal').style.display = 'flex'; });
  $('cancelSurrenderBtn').addEventListener('click', () => { $('surrenderModal').style.display = 'none'; });
  $('confirmSurrenderBtn').addEventListener('click', () => {
    socket.emit('whoami_surrender', { roomCode });
    $('surrenderModal').style.display = 'none';
  });
  $('backToLobbyBtn').addEventListener('click', () => window.location.assign('../lobby.html?game=whoami'));

  // ============================================================
  //  بروفايل اللاعب — نسخة حروف بالضبط (بطاقة مسيرة لاعب بدل حروف)
  // ============================================================
  function openProfileModal(isMe) {
    const data  = isMe ? playersStatsData.me : playersStatsData.opponent;
    const modal = document.getElementById('playerProfileModal');
    document.getElementById('modalAvatar').src              = data.avatar;
    document.getElementById('modalPlayerName').textContent  = data.name;
    document.getElementById('modalFlag').src                = data.flag || '../assets/flags/SA.svg';
    document.getElementById('rankValue').textContent        = data.rank ?? '-';
    const cs = data.whoami || { wins: 0, losses: 0, total: 0 };
    const gl = data.global || { wins: 0, losses: 0, total: 0 };
    document.getElementById('careerWins').textContent    = cs.wins;
    document.getElementById('careerLosses').textContent  = cs.losses;
    document.getElementById('careerTotal').textContent   = cs.total;
    document.getElementById('globalWins').textContent    = gl.wins;
    document.getElementById('globalLosses').textContent  = gl.losses;
    document.getElementById('globalTotal').textContent   = gl.total;
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
  //  الإبلاغ عن الخصم (نسخة حروف)
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
    document.getElementById('playerProfileModal').style.display = 'none';
    reportModal.style.display = 'flex';
  });
  cancelReportBtn?.addEventListener('click', () => { reportModal.style.display = 'none'; });
  document.querySelectorAll('.report-reason').forEach(btn => {
    btn.addEventListener('click', () => {
      socket.emit('report_opponent', { roomCode, token, reason: btn.dataset.reason, target_id: _opponentUserId, game_mode: window.CURRENT_GAME });
      reportModal.style.display = 'none';
    });
  });
  socket.on('report_result', (data) => {
    showToast(data.ok ? '✅ ' + data.msg : '⚠️ ' + data.msg);
    if (data.ok) reportSentThisMatch = true;
  });
  socket.on('chat_error', (data) => {
    showToast('🔇 ' + (data.msg || 'لا يمكنك إرسال رسائل'));
  });

  // ============================================================
  //  الصداقة والحظر (نسخة حروف — ديناميكية حسب الحالة)
  // ============================================================
  const addFriendBtn = document.querySelector('#modalActionButtons .add-friend');
  const blockUserBtn = document.querySelector('#modalActionButtons .block-user');

  let friendState = (sessionStorage.getItem('isFriendly') === '1') ? 'friends' : 'none';
  let blockState  = false;

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
    if (blockState) { addFriendBtn.style.display = 'none'; return; }
    addFriendBtn.style.display = '';
    if (friendState === 'friends') {
      addFriendBtn.innerHTML = '<i class="fa-solid fa-user-minus"></i> حذف صديق';
      addFriendBtn.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
      addFriendBtn.style.boxShadow  = '0 4px 10px rgba(231, 76, 60, 0.4)';
      addFriendBtn.disabled = false; addFriendBtn.style.opacity = '1'; addFriendBtn.style.cursor = 'pointer';
    } else if (friendState === 'pending') {
      addFriendBtn.innerHTML = '<i class="fa-solid fa-clock"></i> في انتظار الرد';
      addFriendBtn.style.background = 'rgba(255,255,255,0.12)';
      addFriendBtn.style.boxShadow  = 'none';
      addFriendBtn.disabled = true; addFriendBtn.style.opacity = '0.7'; addFriendBtn.style.cursor = 'default';
    } else if (friendState === 'incoming') {
      addFriendBtn.innerHTML = '<i class="fa-solid fa-user-check"></i> قبول الطلب';
      addFriendBtn.style.background = 'linear-gradient(135deg, #2ecc71, #27ae60)';
      addFriendBtn.style.boxShadow  = '0 4px 10px rgba(46, 204, 113, 0.4)';
      addFriendBtn.disabled = false; addFriendBtn.style.opacity = '1'; addFriendBtn.style.cursor = 'pointer';
    } else {
      addFriendBtn.innerHTML = '<i class="fa-solid fa-user-plus"></i> إضافة صديق';
      addFriendBtn.style.background = 'linear-gradient(135deg, #3498db, #2980b9)';
      addFriendBtn.style.boxShadow  = '0 4px 10px rgba(52, 152, 219, 0.4)';
      addFriendBtn.disabled = false; addFriendBtn.style.opacity = '1'; addFriendBtn.style.cursor = 'pointer';
    }
  }

  function renderBlockButton() {
    if (!blockUserBtn) return;
    if (blockState) {
      blockUserBtn.innerHTML = '<i class="fa-solid fa-unlock"></i> رفع الحظر';
      blockUserBtn.style.background = 'linear-gradient(135deg, #e67e22, #d35400)';
    } else {
      blockUserBtn.innerHTML = '<i class="fa-solid fa-ban"></i> حظر';
      blockUserBtn.style.background = '';
    }
  }

  renderFriendButton();
  renderBlockButton();

  let _pendingFriendAction = null;

  addFriendBtn?.addEventListener('click', () => {
    if (blockState || friendState === 'pending') return;
    if (friendState === 'friends') {
      _pendingFriendAction = 'remove';
      socket.emit('remove_friend_opponent', { roomCode, token, target_id: _opponentUserId });
    } else if (friendState === 'incoming') {
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
    if (blockState) socket.emit('unblock_opponent', { roomCode, token, target_id: _opponentUserId });
    else socket.emit('block_opponent', { roomCode, token, target_id: _opponentUserId });
    document.getElementById('playerProfileModal').style.display = 'none';
  });

  socket.on('friend_result', (data) => {
    showToast((data.ok ? '✅ ' : '⚠️ ') + (data.msg || ''));
    if (data.ok && _pendingFriendAction) {
      friendState = (_pendingFriendAction === 'remove') ? 'none' : 'pending';
      renderFriendButton();
    }
    _pendingFriendAction = null;
  });
  socket.on('block_result', (data) => {
    showToast((data.ok ? '🚫 ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) {
      blockState = true; friendState = 'none';
      renderBlockButton(); renderFriendButton();
    }
  });
  socket.on('unblock_result', (data) => {
    showToast((data.ok ? '🔓 ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) { blockState = false; renderBlockButton(); renderFriendButton(); }
  });
  socket.on('opponent_unfriended', () => { friendState = 'none'; renderFriendButton(); });
  socket.on('opponent_accepted_friend', () => {
    friendState = 'friends'; renderFriendButton();
    showToast('✅ قبل طلب صداقتك!');
  });
  socket.on('friend_request_received', (data) => {
    showToast('👋 ' + (data.from || 'لاعب') + ' أرسل لك طلب صداقة');
    friendState = 'incoming';
    renderFriendButton();
  });
  // ============================================================
  //  أنيميشن انقطاع/عودة الخصم (موحّد — نسخة حروف)
  // ============================================================
  socket.on('opponent_disconnected', (data) => {
    if (typeof Swal === 'undefined') return;
    Swal.fire({
      title: 'انقطع الاتصال!',
      html: `<b>${(data && data.msg) || 'انقطع اتصال الخصم'}</b><br><small>أمام الخصم 30 ثانية للعودة قبل إعلان انسحابه.</small>`,
      icon: 'warning',
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });
  });
  socket.on('opponent_reconnected', () => {
    if (typeof Swal === 'undefined') return;
    Swal.close();
    Swal.fire({ title: 'عاد الخصم!', text: 'تمت استعادة الاتصال، استعد للمتابعة...', icon: 'success', timer: 2000, showConfirmButton: false });
  });
})();