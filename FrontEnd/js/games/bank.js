/* 🏦 البنك — منطق العميل */
(function () {
  'use strict';
  window.CURRENT_GAME = 'bank';

  const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });
  window.socket = socket;
  const roomCode     = sessionStorage.getItem('gameRoomCode');
  const token        = localStorage.getItem('token') || sessionStorage.getItem('token');
  const playerName   = sessionStorage.getItem('playerName')   || sessionStorage.getItem('username') || 'لاعب';
  const playerAvatar = sessionStorage.getItem('playerAvatar') || sessionStorage.getItem('avatar')   || '';
  let mySid = null;

  if (!token || !roomCode) { window.location.href = '../lobby.html'; return; }

  const $ = (id) => document.getElementById(id);
  const answerBox     = $('answerBox');
  const answerInput   = $('answerInput');
  const answerTimerEl = $('answerTimer');
  const turnTimerEl   = $('turnTimer');
  let answerCountdown = null;
  let turnCountdown   = null;
  let iAmActive       = false;

  function getValidAvatar(src) {
    if (!src) return '../assets/avatars/avatar_1.svg';
    if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('../') || src.startsWith('/')) return src;
    return `../assets/avatars/${src}`;
  }
  function setStatus(t, type) {
    const el = $('statusMsg');
    el.textContent = t || '';
    el.className = 'bank-status-msg' + (type ? ' ' + type : '');
  }
  function updateSafe(safe, safeByName) {
    // 🛡️ الأسماء ثابتة مهما تقلّبت هوية الاتصال — نفضّلها دائماً
    if (safeByName && Object.keys(safeByName).length) {
      const oppName = oppRoomName || Object.keys(safeByName).find(n => n !== myRoomName);
      $('mySafe').textContent = safeByName[myRoomName] ?? 0;
      $('opponentSafe').textContent = safeByName[oppName] ?? 0;
      return;
    }
    if (!safe) return;
    const opp = Object.keys(safe).find(s => s !== mySid);
    $('mySafe').textContent = safe[mySid] ?? 0;
    $('opponentSafe').textContent = safe[opp] ?? 0;
  }
  function updateTemp(temp) {
    if (!temp) return;
    $('tempValue').textContent = temp[mySid] ?? 0;
  }
  function updateRound(round) {
    document.querySelectorAll('.round-dot').forEach((d, i) => {
      d.classList.toggle('active', (i + 1) === round);
      d.classList.toggle('done', (i + 1) < round);
    });
  }

  // ===== أنيميشن استعد 3-2-1 (موحّد) =====
  function playReadyAnimation(cb) {
    const overlay = $('readyOverlay');
    const countEl = $('readyCount');
    const titleEl = $('readyTitle');
    overlay.style.display = 'flex';
    titleEl.textContent = 'استعد!';
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

  // ===== المؤقّت المرئي =====
  function startTurnTimer(seconds) {
    clearInterval(turnCountdown);
    let t = Math.round(seconds);
    turnTimerEl.textContent = t;
    turnTimerEl.classList.remove('low');
    turnCountdown = setInterval(() => {
      t--;
      turnTimerEl.textContent = Math.max(0, t);
      if (t <= 10) turnTimerEl.classList.add('low');
      if (t <= 0) clearInterval(turnCountdown);
    }, 1000);
  }
  function pauseTurnTimer() { clearInterval(turnCountdown); }

  // ===== الاتصال =====
  socket.on('connect', () => {
    mySid = socket.id;
    socket.emit('join_room', { room_code: roomCode, token, player_name: playerName, avatar: playerAvatar });
  });

  // بيانات اللاعبين (نفس بنية حروف/مسيرة لاعب)
  let playersStatsData = {
    me:       { name: playerName, avatar: '../assets/avatars/avatar_1.svg', flag: '../assets/flags/SA.svg', rank: '-', bank: {wins:0,losses:0,total:0}, global: {wins:0,losses:0,total:0} },
    opponent: { name: 'الخصم',    avatar: '../assets/avatars/avatar_2.svg', flag: '../assets/flags/SA.svg', rank: '-', bank: {wins:0,losses:0,total:0}, global: {wins:0,losses:0,total:0} },
  };
  let _opponentUserId = null;

  function showToast(msg) {
    if (typeof window.showToast === 'function' && window.showToast !== showToast) { window.showToast(msg); return; }
    let t = document.getElementById('bankToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'bankToast';
      t.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#161b22;color:#fff;padding:10px 20px;border-radius:12px;z-index:7000;font-weight:700;border:1px solid rgba(255,255,255,.15);transition:opacity .3s;max-width:80%;text-align:center;';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._to);
    t._to = setTimeout(() => { t.style.opacity = '0'; }, 3000);
  }
  function _esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }

  let myRoomName = playerName;   // اسمي في الغرفة (نفس مصدر safeByName بالخادم)
  let oppRoomName = null;
  socket.on('room_joined', (data) => {
    const players = data.players || [];
    const me = players.find(p => p.sid === socket.id || p.name === playerName);
    const opp = players.find(p => p.sid !== socket.id && p.name !== playerName);
    if (me?.name) myRoomName = me.name;
    if (opp?.name) oppRoomName = opp.name;
    if (me?.stats)  playersStatsData.me       = { ...me.stats,  avatar: getValidAvatar(me.stats.avatar) };
    if (opp?.stats) playersStatsData.opponent = { ...opp.stats, avatar: getValidAvatar(opp.stats.avatar) };
    $('myName').textContent       = playersStatsData.me.name;
    $('myAvatarImg').src          = playersStatsData.me.avatar;
    $('opponentName').textContent = playersStatsData.opponent.name;
    $('opponentAvatarImg').src    = playersStatsData.opponent.avatar;
    if (typeof data.opponent_user_id !== 'undefined') _opponentUserId = data.opponent_user_id;
    if (typeof data.opponent_relation === 'string' && typeof applyOpponentRelation === 'function') {
      applyOpponentRelation(data.opponent_relation);
    }
  });

  socket.on('bank_ready', () => setStatus('بدأت المباراة!', ''));

  // ===== بدء دور =====
  socket.on('bank_round_start', (d) => {
    updateSafe(d.safe, d.safeByName);
    updateRound(d.round);
    updateTemp({ [mySid]: 0 });
    iAmActive = true;  // 🔥 متزامن: الجميع يلعب معاً
    answerBox.style.display = 'none';
    $('actionButtons').style.display = 'none';
    $('qText').textContent = 'استعد…';
    $('qMeta').textContent = '';
    const banner = $('turnBanner');
    banner.className = 'turn-banner mine';
    $('turnText').textContent = `🔥 الجولة ${d.round}/${d.totalRounds} — كلاكما يلعب الآن!`;
    playReadyAnimation(() => {
      startTurnTimer(d.turnSeconds);
      $('actionButtons').style.display = 'flex';
    });
  });

  // ===== سؤال جديد =====
  socket.on('bank_question', (d) => {
    // 🙈 لا صعوبة ولا نقاط — الفئة فقط (مثل الأصل)
    $('qMeta').innerHTML = `<span class="q-cat">${d.category}</span>`;
    $('qText').textContent = d.text;
    answerBox.style.display = 'none';
    if (typeof d.remaining === 'number') startTurnTimer(d.remaining);
    $('actionButtons').style.display = 'flex';
    $('answerActionBtn').disabled = false;
    $('answerActionBtn').style.display = '';
    $('bankBtn').style.display = 'none';  // 🏦 البنك بين الأسئلة فقط
  });

  // 🏦 نافذة القرار: "تبنّك أم تغامر؟" (ثانيتان بين الأسئلة)
  socket.on('bank_decision', (d) => {
    $('qMeta').textContent = '';
    $('qText').textContent = `🏦 معك ${d.temp} — تبنّك أم تغامر؟`;
    $('actionButtons').style.display = 'flex';
    $('answerActionBtn').style.display = 'none';
    $('bankBtn').style.display = '';
    $('bankBtn').classList.add('pulse');
    if (typeof d.remaining === 'number') startTurnTimer(d.remaining);
    setTimeout(() => $('bankBtn').classList.remove('pulse'), 2000);
  });
  socket.on('bank_denied', (d) => showToast('⚠️ ' + (d.msg || '')));

  // ===== ضغط إجابة → نافذة كتابة =====
  socket.on('bank_answering', (d) => {
    pauseTurnTimer();  // ⏸️ الوقت مجمّد أثناء الكتابة (يستأنف بنتيجة الإجابة)
    $('actionButtons').style.display = 'none';
    openAnswerBox(d.answerWindow);
  });

  // ⚖️ الحكم الذكي يراجع إجابة حدّية — الوقت ما زال مجمّداً حتى الحسم
  socket.on('bank_judging', () => {
    setStatus('⚖️ الحكم الذكي يراجع إجابتك… (وقتك مجمّد)', 'bank');
  });

  // نشاط الخصم (متزامن — نعرضه بشكل خفيف)
  socket.on('bank_opp_activity', (d) => {
    const map = {
      answering: '✍️ الخصم يكتب…',
      correct: '✅ الخصم أجاب صح',
      wrong: '❌ الخصم أخطأ',
      banked: `🏦 الخصم بنّك ${d.amount ?? ''}`,
      done: '⏱️ الخصم أنهى جولته',
    };
    const el = $('oppActivity');
    if (el && map[d.type]) {
      el.textContent = map[d.type];
      el.classList.add('show');
      clearTimeout(el._to);
      el._to = setTimeout(() => el.classList.remove('show'), 2500);
    }
  });

  function openAnswerBox(seconds) {
    answerBox.style.display = 'flex';
    answerInput.value = '';
    answerInput.focus();
    let t = Math.round(seconds);
    answerTimerEl.textContent = t;
    clearInterval(answerCountdown);
    answerCountdown = setInterval(() => {
      t--;
      answerTimerEl.textContent = Math.max(0, t);
      if (t <= 0) { clearInterval(answerCountdown); answerBox.style.display = 'none'; }
    }, 1000);
  }

  // ===== نتيجة الإجابة =====
  socket.on('bank_answer_result', (d) => {
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
    $('tempValue').textContent = d.temp ?? 0;
    updateSafe(d.safe);
    if (typeof d.remaining === 'number') startTurnTimer(d.remaining);
    if (d.correct) {
      setStatus(`✅ صحيح! +${d.points}`, 'correct');
    } else if (d.shielded) {
      setStatus(`🛡️ الدرع امتص الخطأ — رصيدك سليم! (الإجابة: ${d.correctAnswer})`, 'bank');
    } else {
      const lostMsg = d.lost ? ` — خسرت ${d.lost} وعاد السلّم سهلاً` : '';
      setStatus(`❌ ${d.timedOut ? 'انتهى الوقت' : 'خطأ'}: ${d.correctAnswer}${lostMsg}`, 'wrong');
    }
  });

  // ===== بنك =====
  socket.on('bank_banked', (d) => {
    updateSafe(d.safe);
    $('tempValue').textContent = 0;
    if (typeof d.remaining === 'number') startTurnTimer(d.remaining);
    setStatus(`🏦 بنّكت ${d.amount} بأمان — السلّم عاد سهلاً!`, 'bank');
    $('bankBtn').style.display = 'none';
  });
  socket.on('bank_safe_update', (d) => updateSafe(d.safe, d.safeByName));

  // ===== نهاية دور =====
  socket.on('bank_player_done', (d) => {
    pauseTurnTimer();
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
    $('actionButtons').style.display = 'none';
    updateSafe(d.safe);
    $('qText').textContent = 'انتهى وقتك — بانتظار الخصم…';
    $('qMeta').textContent = '';
    setStatus(`⏱️ بُنّك ${d.autoBanked} تلقائياً`, 'reveal');
  });

  // ===== نهاية المباراة =====
  socket.on('bank_match_over', (d) => {
    pauseTurnTimer();
    clearInterval(answerCountdown);
    clearInterval(turnCountdown);
    const myName = myRoomName;
    // 🛡️ الحكم باسم الغرفة الثابت (نفس مصدر الخادم بالضبط)
    const iWon = d.winnerName ? (d.winnerName === myName) : (d.winner === mySid);
    const isDraw = !d.winner && !d.winnerName;
    $('winIcon').textContent = isDraw ? '🤝' : (iWon ? '🏆' : '😔');
    $('winTitle').textContent = isDraw ? 'تعادل' : (iWon ? 'فزت!' : 'خسرت');
    let mine = 0, theirs = 0;
    if (d.safeByName && Object.keys(d.safeByName).length) {
      const oppName = oppRoomName || Object.keys(d.safeByName).find(n => n !== myName);
      mine = d.safeByName[myName] ?? 0; theirs = d.safeByName[oppName] ?? 0;
    } else {
      const safe = d.safe || {};
      const opp = Object.keys(safe).find(s => s !== mySid);
      mine = safe[mySid] ?? 0; theirs = safe[opp] ?? 0;
    }
    $('winSubtitle').textContent = `الرصيد النهائي: ${mine} - ${theirs}`;
    $('winMessageOverlay').style.display = 'flex';
  });

  socket.on('bank_state', (d) => {
    updateSafe(d.safe);
    updateTemp(d.temp);
    updateRound(d.round);
    // متزامن: الأزرار تظهر أثناء اللعب (ما لم يكن انتهى وقتي)
    const overlay = $('readyOverlay');
    const animActive = overlay && overlay.style.display === 'flex';
    if (d.stage === 'playing' && !animActive && answerBox.style.display === 'none') {
      $('actionButtons').style.display = 'flex';
    }
  });

  // ===== تفاعلات =====
  $('answerActionBtn').addEventListener('click', () => {
    $('answerActionBtn').disabled = true;
    socket.emit('bank_answer_start', { roomCode });
  });
  $('bankBtn').addEventListener('click', () => {
    socket.emit('bank_bank', { roomCode });
  });
  function submitAnswer() {
    const ans = answerInput.value.trim();
    if (!ans) return;
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
    setStatus('⏳ جارٍ التحقق…', 'reveal');
    socket.emit('bank_submit_answer', { roomCode, answer: ans });
  }
  $('submitAnswerBtn').addEventListener('click', submitAnswer);
  answerInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitAnswer(); });

  $('surrenderBtn').addEventListener('click', () => { $('surrenderModal').style.display = 'flex'; });
  $('cancelSurrenderBtn').addEventListener('click', () => { $('surrenderModal').style.display = 'none'; });
  $('confirmSurrenderBtn').addEventListener('click', () => {
    socket.emit('bank_surrender', { roomCode });
    $('surrenderModal').style.display = 'none';
  });
  $('backToLobbyBtn').addEventListener('click', () => window.location.assign('../lobby.html?game=bank'));

  // رسائل جاهزة
  (function initQuickChat() {
    const btn = $('gameQuickChatBtn');
    if (btn && window.QuickChat) {
      QuickChat.init({ socket, triggerBtn: btn, event: 'send_room_chat_message',
        extra: () => ({ roomCode }), context: 'game', game: 'bank' });
    }
  })();
  socket.on('new_room_chat_message', (msg) => {
    if (!msg || !msg.text) return;
    const mine = msg.senderSid === socket.id;
    const anchor = mine ? $('myProfileBtn') : $('opponentProfileBtn');
    if (!anchor) return;
    const b = document.createElement('div');
    b.className = 'qc-bubble' + (mine ? ' mine' : '');
    b.textContent = msg.text;
    anchor.style.position = 'relative';
    anchor.appendChild(b);
    setTimeout(() => b.classList.add('show'), 10);
    setTimeout(() => { b.classList.remove('show'); setTimeout(() => b.remove(), 250); }, 3500);
  });

  // أنيميشن انقطاع الخصم (موحّد)
  socket.on('opponent_disconnected', (data) => {
    if (typeof Swal === 'undefined') return;
    Swal.fire({ title: 'انقطع الاتصال!', html: `<b>${(data && data.msg) || 'انقطع اتصال الخصم'}</b><br><small>أمامه 30 ثانية للعودة.</small>`,
      icon: 'warning', allowOutsideClick: false, showConfirmButton: false, didOpen: () => Swal.showLoading() });
  });
  socket.on('opponent_reconnected', () => {
    if (typeof Swal === 'undefined') return;
    Swal.close();
    Swal.fire({ title: 'عاد الخصم!', icon: 'success', timer: 2000, showConfirmButton: false });
  });

  // ============================================================
  // 👤 بروفايل اللاعب — نسخة حروف بالضبط (بطاقة البنك)
  // ============================================================
  function openProfileModal(isMe) {
    const data  = isMe ? playersStatsData.me : playersStatsData.opponent;
    const modal = document.getElementById('playerProfileModal');
    document.getElementById('modalAvatar').src              = data.avatar;
    document.getElementById('modalPlayerName').textContent  = data.name;
    document.getElementById('modalFlag').src                = data.flag || '../assets/flags/SA.svg';
    document.getElementById('rankValue').textContent        = data.rank ?? '-';
    const cs = data.bank || { wins: 0, losses: 0, total: 0 };
    const gl = data.global || { wins: 0, losses: 0, total: 0 };
    document.getElementById('bankWins').textContent    = cs.wins;
    document.getElementById('bankLosses').textContent  = cs.losses;
    document.getElementById('bankTotal').textContent   = cs.total;
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
  // 🛡️ الإبلاغ عن الخصم (نسخة حروف)
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
      socket.emit('report_opponent', { roomCode, token, reason: btn.dataset.reason });
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
  // 👥 الصداقة والحظر (نسخة حروف — ديناميكية حسب الحالة)
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
      socket.emit('remove_friend_opponent', { roomCode, token });
    } else if (friendState === 'incoming') {
      if (_opponentUserId) {
        socket.emit('respond_friend_request', { token, requester_id: _opponentUserId, accept: true });
      }
      friendState = 'friends';
      renderFriendButton();
      showToast('✅ تمت إضافة الصديق');
    } else {
      _pendingFriendAction = 'add';
      socket.emit('friend_request_opponent', { roomCode, token });
    }
    document.getElementById('playerProfileModal').style.display = 'none';
  });
  blockUserBtn?.addEventListener('click', () => {
    if (blockState) socket.emit('unblock_opponent', { roomCode, token });
    else socket.emit('block_opponent', { roomCode, token });
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


  // ربط أزرار فتح البروفايل
  document.getElementById('myProfileBtn')?.addEventListener('click', () => openProfileModal(true));
  document.getElementById('opponentProfileBtn')?.addEventListener('click', () => openProfileModal(false));
  document.getElementById('closeProfileBtn')?.addEventListener('click', () => {
    document.getElementById('playerProfileModal').style.display = 'none';
  });
  document.getElementById('playerProfileModal')?.addEventListener('click', (e) => {
    if (e.target === document.getElementById('playerProfileModal'))
      document.getElementById('playerProfileModal').style.display = 'none';
  });


  // ============================================================
  // 🎯 مساعدات البنك (Play to Win) — شريط تحت يسار
  // ============================================================
  let helpsCatalog = {};
  let myLoadout = [];
  let myInventory = {};
  let devModeHelps = false;
  const helpsUsedLocal = new Set();

  socket.emit('get_help_loadout', { token, game: 'bank' });

  socket.on('help_loadout_data', (d) => {
    if (!d || d.game !== 'bank') return;
    helpsCatalog = {};
    (d.catalog || []).forEach((h) => { helpsCatalog[h.id] = h; });
    myLoadout = d.loadout || d.defaultLoadout || [];
    myInventory = d.inventory || {};
    devModeHelps = !!d.devMode;
    renderHelpsBar();
  });

  function renderHelpsBar() {
    const bar = $('bankHelpsBar');
    if (!bar) return;
    bar.innerHTML = '';
    myLoadout.forEach((hid) => {
      const h = helpsCatalog[hid];
      if (!h) return;
      const qty = devModeHelps ? '∞' : String(myInventory[hid] || 0);
      const depleted = (!devModeHelps && (myInventory[hid] || 0) <= 0);
      const btn = document.createElement('button');
      btn.className = 'bank-help-btn'
        + (helpsUsedLocal.has(hid) ? ' used' : '')
        + (depleted ? ' depleted' : '');
      btn.title = `${h.name}: ${h.desc}`;
      btn.innerHTML = `<span class="hicon">${h.icon}</span>`
        + `<span class="hqty">${qty}</span>`;
      btn.addEventListener('click', () => {
        if (helpsUsedLocal.has(hid) || depleted) return;
        socket.emit('bank_use_help', { roomCode, helpId: hid, token });
      });
      bar.appendChild(btn);
    });
  }

  socket.on('bank_help_result', (d) => {
    if (!d) return;
    if (!d.ok) { showToast('⚠️ ' + (d.msg || '')); return; }
    helpsUsedLocal.add(d.helpId);
    if (!devModeHelps && myInventory[d.helpId]) {
      myInventory[d.helpId] = Math.max(0, myInventory[d.helpId] - 1);
    }
    renderHelpsBar();
    if (d.info) setStatus(d.info, 'bank');
    if (typeof d.remaining === 'number') startTurnTimer(d.remaining);
  });

  socket.on('bank_opponent_used_help', (d) => {
    if (d && d.name) showToast(`${d.icon || '🎯'} الخصم استخدم: ${d.name}`);
  });

  // 🔄 فرصة ثانية: نفس السؤال يُفتح مجدداً (+5ث)
  socket.on('bank_second_chance', (d) => {
    setStatus('🔄 فرصة ثانية! جاوب مرة أخرى', 'bank');
    openAnswerBox(d.answerWindow || 13);
  });
})();