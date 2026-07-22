/*  ماذا تعرف — منطق العميل (الأقسام المشتركة منقولة من البنك حرفياً — ثبات التصميم) */
(function () {
  'use strict';
  window.CURRENT_GAME = 'knowledge';

  const socket = io(API_URL, { transports: ['websocket', 'polling'], upgrade: true });
  window.socket = socket;
  const roomCode     = sessionStorage.getItem('gameRoomCode');
  const token        = localStorage.getItem('token') || sessionStorage.getItem('token');
  const playerName   = sessionStorage.getItem('playerName')   || sessionStorage.getItem('username') || 'لاعب';
  const playerAvatar = sessionStorage.getItem('playerAvatar') || sessionStorage.getItem('avatar')   || '';
  let mySid = null;

  if (!token || !roomCode) { window.location.href = '../lobby.html'; return; }

  const $ = (id) => document.getElementById(id);
  const answerBox   = $('answerBox');
  const answerInput = $('answerInput');
  const answerTimerEl = $('answerTimer');
  let answerCountdown = null;
  let timerRAF = null;
  let iAmActive = false;
  
  // 🐛 [تم التعديل هنا]: تعريف المتغير لحل مشكلة sentThisTurn is not defined
  let sentThisTurn = false; 

  // ===== المساعدات (نمط بقية الألعاب) =====
  // الكتالوج والتشكيلة والمخزون تصل عبر help_loadout_data.
  // «مراوغة» تُفعَّل فقط في دورك وعندك سترايكان (وغير مُقفلة بقاعدة 2-2).
  let helpsCatalog = {};
  let myLoadout = [];
  let myInventory = {};
  let devModeHelps = false;
  const helpsUsedLocal = new Set();
  let myDodgeBlocked = false;
  let myStrikesNow = 0;

  function pickMine(map) {
    if (!map) return undefined;
    if (mySid && (mySid in map)) return map[mySid];
    return undefined;
  }

  function syncHelpsState(d) {
    if (!d) return;
    const used = pickMine(d.helps_used);
    if (Array.isArray(used)) used.forEach((h) => helpsUsedLocal.add(h));
    const pb = pickMine(d.dodge_blocked);
    if (pb !== undefined) myDodgeBlocked = !!pb;
    if (d.strikes) myStrikesNow = d.strikes[mySid] || 0;
  }

  function renderHelpsBar() {
    const bar = $('knHelpsBar');
    if (!bar) return;
    bar.innerHTML = '';
    myLoadout.forEach((hid) => {
      const h = helpsCatalog[hid];
      if (!h) return;
      const qty = devModeHelps ? '∞' : String(myInventory[hid] || 0);
      const depleted = (!devModeHelps && (myInventory[hid] || 0) <= 0);
      // «مراوغة» لها شروط عرض إضافية: دورك + سترايكان + غير مُقفلة
      const dodgeLocked = (hid === 'k_dodge') &&
        (!iAmActive || myStrikesNow !== 2 || myDodgeBlocked);
      // ⏱️ كل مساعدات اللعبة توقيتها 'turn': خارج دورك = مقفلة بصرياً
      const wrongPhase = !iAmActive;
      const btn = document.createElement('button');
      btn.className = 'bank-help-btn'
        + (helpsUsedLocal.has(hid) ? ' used' : '')
        + ((depleted || dodgeLocked || wrongPhase) ? ' depleted' : '');
      btn.title = `${h.name}: ${h.desc}`;
      btn.innerHTML = `<span class="hicon">${h.icon}</span>`
        + `<span class="hqty">${qty}</span>`;
      btn.addEventListener('click', () => {
        if (helpsUsedLocal.has(hid) || depleted) return;
        if (hid === 'k_dodge' && dodgeLocked) {
          showToast(myDodgeBlocked
            ? '🔒 مراوغتك مُقفلة: خصمك سبقك في حالة 2-2'
            : '🌀 المراوغة تتاح في دورك وعندك سترايكان');
          return;
        }
        if (wrongPhase) { showToast('⏳ المساعدات تُستخدم في دورك فقط'); return; }
        socket.emit('knowledge_use_help', { roomCode, helpId: hid, token });
      });
      bar.appendChild(btn);
    });
  }

  function getValidAvatar(src) {
    if (!src || String(src).trim() === '') return '../assets/avatars/avatar_1.svg';
    let v = String(src).trim();
    // نعالج الروابط القديمة الثابتة (127.0.0.1/localhost) المحفوظة قبل التحديث
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
  function setStatus(t, type) {
    const el = $('statusMsg');
    el.textContent = t || '';
    el.className = 'bank-status-msg' + (type ? ' ' + type : '');
  }
  function updateRound(round) {
    document.querySelectorAll('.round-dot').forEach((d, i) => {
      d.classList.toggle('active', (i + 1) === round);
      d.classList.toggle('done', (i + 1) < round);
    });
  }
  function updatePoints(points) {
    if (!points) return;
    const opp = Object.keys(points).find(s => s !== mySid);
    $('myPoints').textContent = points[mySid] ?? 0;
    $('opponentPoints').textContent = points[opp] ?? 0;
  }
  //  سترايكات عند الأسماء (نمط مسيرة لاعب المعتمد) — 3 خانات هنا
  function renderStrikeRow(el, count) {
    if (!el) return;
    el.innerHTML = '';
    for (let i = 0; i < 3; i++) {
      const x = document.createElement('span');
      x.className = 'strike-x' + (i < count ? ' filled' : '');
      x.textContent = '✗'; el.appendChild(x);
    }
  }
  function updateStrikes(strikes) {
    strikes = strikes || {};
    const myStrk = strikes[mySid] || 0;
    let oppStrk = 0;
    for (const k in strikes) { if (k !== mySid) oppStrk = strikes[k] || 0; }
    renderStrikeRow($('myStrikes'), myStrk);
    renderStrikeRow($('oppStrikes'), oppStrk);
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

  // ===== شريط وقت الدور (10ث) =====
  function startTimerBar(seconds) {
    cancelAnimationFrame(timerRAF);
    const bar = $('knTimerBar');
    const endsAt = Date.now() + seconds * 1000;
    (function tick() {
      const left = Math.max(0, endsAt - Date.now());
      const pct = (left / (seconds * 1000)) * 100;
      bar.style.width = pct + '%';
      bar.classList.toggle('danger', pct < 30);
      if (left > 0) timerRAF = requestAnimationFrame(tick);
    })();
  }
  function stopTimerBar() {
    cancelAnimationFrame(timerRAF);
    $('knTimerBar').style.width = '0%';
  }

  // ⏱ يحسب الوقت المتبقي من timestamp الـ server (turn_ends_at) بدلاً من
  // عداد محلي يتراكم فيه خطأ الشبكة (50-300ms) — يمنع السترايك الظالم
  function openAnswerBox(seconds, endsAtServerTs) {
    sentThisTurn = false;
    answerBox.style.display = 'flex';
    answerInput.value = '';
    answerInput.disabled = false;
    $('submitAnswerBtn').disabled = false;
    answerInput.focus();
    clearInterval(answerCountdown);
    // endsAtServerTs = Unix timestamp (ثوانٍ) من الـ server
    // بدونه → نستخدم seconds كـ fallback (reconnect أو حالات خاصة)
    const endsAt = endsAtServerTs
      ? (endsAtServerTs * 1000)
      : (Date.now() + seconds * 1000);
    // نعرض الوقت الأولي فوراً قبل أول interval
    answerTimerEl.textContent = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
    answerCountdown = setInterval(() => {
      const left = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
      answerTimerEl.textContent = left;
      //  نوقف الإدخال بصرياً فقط — الـ backend هو المرجع الفعلي
      if (left <= 0) { clearInterval(answerCountdown); answerInput.disabled = true; }
    }, 200);
  }
  function closeAnswerBox() {
    clearInterval(answerCountdown);
    answerBox.style.display = 'none';
  }

  // ===== الاتصال =====
  socket.on('connect', () => {
    // ملاحظة: لا نعتمد socket.id هنا (قد يختلف عن sid الخادم في
    // multiport/polling). mySid يُضبط من your_sid في room_joined.
    if (!mySid) mySid = socket.id;   // قيمة مبدئية فقط لحين وصول your_sid
    socket.emit('join_room', { room_code: roomCode, token, player_name: playerName, avatar: playerAvatar });
  });

  // بيانات اللاعبين (نفس بنية حروف/مسيرة/البنك)
  let playersStatsData = {
    me:       { name: playerName, avatar: '../assets/avatars/avatar_1.svg', flag: '../assets/flags/SA.svg', rank: '-', knowledge: {wins:0,losses:0,total:0}, global: {wins:0,losses:0,total:0} },
    opponent: { name: 'الخصم',    avatar: '../assets/avatars/avatar_2.svg', flag: '../assets/flags/SA.svg', rank: '-', knowledge: {wins:0,losses:0,total:0}, global: {wins:0,losses:0,total:0} },
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
    //  الجذر الأمتن: الخادم يرسل your_sid صراحةً (يعرف sid المستقبِل
    // يقيناً). نعتمده أولاً — لا تخمين من socket.id ولا مطابقة اسم قد تفشل.
    if (data.your_sid) {
      mySid = data.your_sid;
    } else {
      const meByName = players.find(p => p.name === playerName);
      const meFallback = meByName || players.find(p => p.sid === socket.id);
      if (meFallback && meFallback.sid) mySid = meFallback.sid;
    }
    const me = players.find(p => p.sid === mySid) || players.find(p => p.name === playerName);
    const opp = players.find(p => p.sid !== mySid);
    if (me?.stats)  playersStatsData.me       = { ...me.stats,  avatar: getValidAvatar(me.stats.avatar) };
    if (opp?.stats) playersStatsData.opponent = { ...opp.stats, avatar: getValidAvatar(opp.stats.avatar) };
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
    if (typeof data.opponent_user_id !== 'undefined') _opponentUserId = data.opponent_user_id;
    if (typeof data.opponent_relation === 'string') applyOpponentRelation(data.opponent_relation);
    socket.emit('knowledge_state', { roomCode });
    renderStrikeRow($('myStrikes'), 0);
    renderStrikeRow($('oppStrikes'), 0);
  });

  // ===== تدفق اللعبة =====
  socket.on('knowledge_ready', () => {
    playReadyAnimation(() => setStatus('بدأت المباراة!', ''));
  });

  socket.on('knowledge_round_start', (d) => {
    $('roundOverBox').style.display = 'none';
    $('knSaid').innerHTML = '';
    stopTimerBar();
    closeAnswerBox();
    updateRound(d.index);
    $('turnText').textContent = d.tiebreak ? '🔥 جولة حسم!' : `الجولة ${d.index} / ${d.total}`;
    $('qMeta').textContent = d.category || '';
    $('qText').textContent = d.q;
    setStatus('');
    updateStrikes({});
  });

  // 🎯 حدث موجّه من الخادم لصاحب الدور حصرياً — فتح مضمون 100%
  socket.on('knowledge_your_turn', (d) => {
    iAmActive = true;
    $('turnText').textContent = '🫵 دورك — اكتب إجابة!';
    openAnswerBox(d.seconds || 10, d.turn_ends_at);
    renderHelpsBar();
  });

  socket.on('knowledge_turn', (d) => {
    updateStrikes(d.strikes);
    updatePoints(d.points);
    //  صاحب الدور: نطابق بالsid أولاً، وكحماية إضافية بالاسم (لو
    // اختلف الsid لأي سبب بيئي، الاسم يبقى ثابتاً). هذا يضمن أن
    // iAmActive صحيح دائماً → الإجابة تُرسل → لا سترايك زائف.
    iAmActive = (d.sid === mySid) || (d.name && d.name === playerName);
    console.log('[knowledge_turn] d.sid=' + d.sid + ' mySid=' + mySid +
                ' d.name=' + d.name + ' me=' + playerName + ' → iAmActive=' + iAmActive);
    startTimerBar(d.seconds || 10);
    if (iAmActive) {
      $('turnText').textContent = '🫵 دورك — اكتب إجابة!';
      openAnswerBox(d.seconds || 10, d.turn_ends_at);   //  يظهر فوراً بوقت دقيق من الـ server
    } else {
      closeAnswerBox();
      $('turnText').textContent = `⏳ دور ${d.name}…`;
    }
    syncHelpsState(d);
    renderHelpsBar();
    // تحصين: مع تعدد الـ workers قد يصل حدث متأخر (round_start) بعد
    // knowledge_turn فيغلق الصندوق المفتوح للتو — نعيد التأكيد بعد لحظة
    if (iAmActive) {
      const endsAt = d.turn_ends_at;
      const secs = d.seconds || 10;
      setTimeout(() => {
        if (iAmActive && answerBox.style.display === 'none') {
          openAnswerBox(secs, endsAt);
        }
      }, 450);
    }
  });

  function submit() {
    if (!iAmActive || sentThisTurn) return;
    const ans = answerInput.value.trim();
    if (!ans) return;
    sentThisTurn = true;
    answerInput.disabled = true;
    $('submitAnswerBtn').disabled = true;
    clearInterval(answerCountdown);
    stopTimerBar();   //  نوقف شريط الوقت: الحسم الآن للخادم/الـAI بلا ضغط وقت
    socket.emit('knowledge_submit_answer', { roomCode, answer: ans });
    setStatus('⏳ جارٍ التحقق…');
  }
  $('submitAnswerBtn').addEventListener('click', submit);
  answerInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });

  socket.on('knowledge_judging', () => setStatus('⚖️ الحكم الذكي يراجع الإجابة…'));

  // ===== أحداث المساعدات =====
  socket.emit('get_help_loadout', { token, game: 'knowledge' });

  socket.on('help_loadout_data', (d) => {
    if (!d || d.game !== 'knowledge') return;
    helpsCatalog = {};
    (d.catalog || []).forEach((h) => { helpsCatalog[h.id] = h; });
    myLoadout = d.loadout || d.defaultLoadout || [];
    myInventory = d.inventory || {};
    devModeHelps = !!d.devMode;
    renderHelpsBar();
  });

  socket.on('knowledge_help_result', (d) => {
    if (!d) return;
    if (!d.ok) { showToast('⚠️ ' + (d.msg || '')); return; }
    helpsUsedLocal.add(d.helpId);
    if (!devModeHelps && myInventory[d.helpId]) {
      myInventory[d.helpId] = Math.max(0, myInventory[d.helpId] - 1);
    }
    renderHelpsBar();
    if (d.info) setStatus(d.info, 'ok');
  });

  socket.on('knowledge_opponent_used_help', (d) => {
    if (d && d.name) showToast(`${d.icon || '🎯'} الخصم استخدم: ${d.name}`);
  });

  // «مراوغة»: انتقال الدور بلا سترايك (+ قاعدة القفل 2-2)
  socket.on('knowledge_dodge', (d) => {
    stopTimerBar();
    closeAnswerBox();
    syncHelpsState(d);
    renderHelpsBar();
    const mine = (d.sid === mySid);
    setStatus(mine ? '🌀 راوغت — انتقل الدور بلا سترايك'
                   : `🌀 ${d.name} راوغ — جاء دورك`, 'ok');
    if (d.blocked_sid && d.blocked_sid === mySid) {
      showToast('🔒 خصمك سبقك في حالة 2-2 — أُقفلت مراوغتك لبقية المباراة');
    }
  });

  // «محاولة ثانية»: الخطأ المكتوب لم يُحسب — 5 ثوانٍ لمحاولة أخرى
  socket.on('knowledge_retry', (d) => {
    if (!d) return;
    const mine = (d.sid === mySid);
    if (mine) {
      sentThisTurn = false;
      answerInput.disabled = false;
      $('submitAnswerBtn').disabled = false;
      setStatus('🔄 محاولتك الثانية — الخطأ لم يُحسب، عندك 5 ثوانٍ!', 'ok');
      startTimerBar(d.seconds || 5);
      openAnswerBox(d.seconds || 5, d.turn_ends_at);
      answerInput.value = '';
      answerInput.focus();
    } else {
      showToast(`🔄 محاولة ثانية لـ ${d.name} — خطؤه لم يُحسب`);
      startTimerBar(d.seconds || 5);
    }
    syncHelpsState(d);
    renderHelpsBar();
  });

  // «وقت إضافي»: مؤقّت جديد من الخادم للطرفين
  socket.on('knowledge_time_plus', (d) => {
    if (!d) return;
    const mine = (d.sid === mySid);
    if (!mine) showToast(`⏱️ ${d.name} أضاف وقتاً لدوره`);
    if (mine && d.turn_ends_at) {
      const left = Math.max(1, Math.ceil(d.turn_ends_at - (Date.now() / 1000)));
      startTimerBar(left);
      openAnswerBox(left, d.turn_ends_at);
    }
  });


  socket.on('knowledge_correct', (d) => {
    stopTimerBar();
    closeAnswerBox();
    setStatus(`✅ ${d.sid === mySid ? 'أنت' : d.name}: ${d.answer}`, 'ok');
    const chip = document.createElement('span');
    chip.className = 'kn-chip' + (d.sid === mySid ? ' mine' : '');
    chip.textContent = d.answer;
    $('knSaid').appendChild(chip);
  });

  socket.on('knowledge_strike', (d) => {
    stopTimerBar();
    closeAnswerBox();
    updateStrikes(d.strikes);
    const who = d.sid === mySid ? 'أنت' : d.name;
    const why = { wrong: 'إجابة خاطئة', timeout: 'انتهى الوقت', repeat: 'إجابة مكررة!' }[d.reason] || 'خطأ';
    setStatus(`✗ ${who}: ${why}${d.answer ? ` («${d.answer}»)` : ''} — ${d.count}/${d.max}`, 'wrong');
  });

  socket.on('knowledge_round_over', (d) => {
    stopTimerBar();
    closeAnswerBox();
    updatePoints(d.points);
    updateStrikes(d.strikes);
    const box = $('roundOverBox');
    let txt;
    if (d.exhausted) {
      txt = '🕳️ نفدت إجابات القائمة! كلاكما ينقّط حسب سترايكاته.';
    } else {
      const loserMe = d.loser_sid === mySid;
      txt = loserMe ? `💥 وصلت 3 سترايكات — خسرت هذا السؤال`
                    : `🎯 ${d.loser_name} وصل 3 سترايكات — السؤال لك!`;
    }
    const gainsTxt = Object.keys(d.gains || {})
      .map(s => `${s === mySid ? 'أنت' : 'الخصم'} +${d.gains[s]}`)
      .filter(x => !x.endsWith('+0')).join(' • ');
    $('roundOverText').textContent = txt + (gainsTxt ? ` (${gainsTxt})` : '');
    box.style.display = 'block';
  });

  socket.on('knowledge_tiebreak', () => setStatus('🔥 تعادل! جولة حسم إضافية', 'wrong'));

  // ===== إعادة المزامنة =====
  socket.on('knowledge_state', (d) => {
    if (!d) return;
    updatePoints(d.points);
    updateStrikes(d.strikes);
    syncHelpsState(d);
    if (d.index) updateRound(d.index);
    if (d.stage === 'turn' && d.q) {
      $('qText').textContent = d.q;
      $('qMeta').textContent = d.category || '';
      iAmActive = d.turn === mySid;
      startTimerBar(d.seconds_left || 3);
      if (iAmActive) openAnswerBox(d.seconds_left || 3, d.turn_ends_at);
      $('turnText').textContent = iAmActive ? '🫵 دورك — اكتب إجابة!' : '⏳ دور الخصم…';
      renderHelpsBar();
    }
  });

  // ===== نهاية المباراة =====
  socket.on('knowledge_match_over', (d) => {
    stopTimerBar();
    closeAnswerBox();
    if (typeof Swal !== 'undefined') Swal.close();
    const won = d.winner_sid === mySid;
    $('winIcon').textContent = won ? '🏆' : '😔';
    $('winTitle').textContent = won ? 'فزت!' : 'خسرت';
    const my = (d.points && d.points[mySid]) || 0;
    let opp = 0;
    for (const s in (d.points || {})) if (s !== mySid) opp = d.points[s];
    $('winSubtitle').textContent = d.reason === 'surrender'
      ? (won ? 'انسحب خصمك — مكافأة الفوز كاملة لك.' : 'انسحبت — لا مكافآت.')
      : `النقاط: ${my} — ${opp}`;
    $('winMessageOverlay').style.display = 'flex';
  });
  $('backToLobbyBtn').addEventListener('click', () => window.location.assign('../lobby.html?game=knowledge'));

  // ===== الانسحاب (نفس مواضع الأخوات) =====
  $('surrenderBtn').addEventListener('click', () => $('surrenderModal').style.display = 'flex');
  $('cancelSurrenderBtn').addEventListener('click', () => $('surrenderModal').style.display = 'none');
  $('confirmSurrenderBtn').addEventListener('click', () => {
    $('surrenderModal').style.display = 'none';
    socket.emit('knowledge_surrender', { roomCode });
  });

  // رسائل جاهزة (نفس نظام الأخوات)
  (function initQuickChat() {
    const btn = $('gameQuickChatBtn');
    if (btn && window.QuickChat) {
      QuickChat.init({ socket, triggerBtn: btn, event: 'send_room_chat_message',
        extra: () => ({ roomCode }), context: 'game', game: 'knowledge' });
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

  // انقطاع الخصم — عدّاد حي 30ث (تجربة أوضح من الأخوات)
  let dcCountdownTimer = null;
  function startDcCountdown(seconds) {
    clearInterval(dcCountdownTimer);
    let left = seconds;
    const render = () => {
      const txt = `أمامه ${left} ثانية للعودة…`;
      if (typeof Swal !== 'undefined' && Swal.isVisible()) {
        const el = document.getElementById('dcCountText');
        if (el) el.textContent = txt;
      }
      const el2 = document.getElementById('dcText');
      if (el2) el2.textContent = txt;
    };
    render();
    dcCountdownTimer = setInterval(() => {
      left--;
      if (left < 0) { clearInterval(dcCountdownTimer); return; }
      render();
    }, 1000);
  }
  socket.on('opponent_disconnected', (data) => {
    if (typeof Swal !== 'undefined') {
      Swal.fire({
        title: 'انقطع الاتصال!',
        html: `<b>${(data && data.msg) || 'انقطع اتصال الخصم'}</b><br><small id="dcCountText">أمامه 30 ثانية للعودة…</small>`,
        icon: 'warning', allowOutsideClick: false, showConfirmButton: false,
        didOpen: () => Swal.showLoading()
      });
    } else {
      $('dcOverlay').style.display = 'flex';
    }
    startDcCountdown(30);
  });
  socket.on('opponent_reconnected', () => {
    clearInterval(dcCountdownTimer);
    $('dcOverlay').style.display = 'none';
    if (typeof Swal === 'undefined') return;
    Swal.close();
    Swal.fire({ title: 'عاد الخصم!', icon: 'success', timer: 2000, showConfirmButton: false });
  });
  //  مهلة الخادم (30ث) تُطلق show_winner — نعامله كنهاية مباراة بانسحاب
  socket.on('show_winner', (d) => {
    clearInterval(dcCountdownTimer);
    if (typeof Swal !== 'undefined') Swal.close();
    stopTimerBar(); closeAnswerBox();
    // نحدد إن كنا الفائز: اللون الأخضر = المضيف عادةً؛ نعتمد أننا لم ننقطع
    const won = d && d.reason === 'surrender';
    $('winIcon').textContent = '🏆';
    $('winTitle').textContent = 'فزت!';
    $('winSubtitle').textContent = 'انسحب خصمك (انقطع اتصاله) — مكافأة الفوز كاملة لك.';
    $('winMessageOverlay').style.display = 'flex';
  });

  // ============================================================
  //  بروفايل اللاعب — نسخة حروف بالضبط (بطاقة ماذا تعرف)
  // ============================================================
  function openProfileModal(isMe) {
    const data  = isMe ? playersStatsData.me : playersStatsData.opponent;
    const modal = document.getElementById('playerProfileModal');
    document.getElementById('modalAvatar').src              = data.avatar;
    document.getElementById('modalPlayerName').textContent  = data.name;
    document.getElementById('modalFlag').src                = data.flag || '../assets/flags/SA.svg';
    document.getElementById('rankValue').textContent        = data.rank ?? '-';
    const cs = data.knowledge || { wins: 0, losses: 0, total: 0 };
    const gl = data.global || { wins: 0, losses: 0, total: 0 };
    document.getElementById('knWins').textContent    = cs.wins;
    document.getElementById('knLosses').textContent  = cs.losses;
    document.getElementById('knTotal').textContent   = cs.total;
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
    if (e.target === document.getElementById('playerProfileModal'))
      document.getElementById('playerProfileModal').style.display = 'none';
  });

  // ============================================================
  //  الإبلاغ عن الخصم (نسخة حروف)
  // ============================================================
  const reportModal     = document.getElementById('reportModal');
  const cancelReportBtn = document.getElementById('cancelReportBtn');
  const reportUserBtn   = document.querySelector('#modalActionButtons .report-user');
  let reportSentThisMatch = false;

  reportUserBtn?.addEventListener('click', () => {
    if (reportSentThisMatch) { showToast('⚠️ سبق وأبلغت عن الخصم في هذه المباراة'); return; }
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
  socket.on('chat_error', (data) => showToast('🔇 ' + (data.msg || 'لا يمكنك إرسال رسائل')));

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
      if (_opponentUserId) socket.emit('respond_friend_request', { token, requester_id: _opponentUserId, accept: true });
      friendState = 'friends'; renderFriendButton();
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
    if (data.ok) { blockState = true; friendState = 'none'; renderBlockButton(); renderFriendButton(); }
  });
  socket.on('unblock_result', (data) => {
    showToast((data.ok ? '🔓 ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) { blockState = false; renderBlockButton(); renderFriendButton(); }
  });
  socket.on('opponent_unfriended', () => { friendState = 'none'; renderFriendButton(); });
  socket.on('opponent_accepted_friend', () => { friendState = 'friends'; renderFriendButton(); showToast('✅ قبل طلب صداقتك!'); });
  socket.on('friend_request_received', (data) => {
    showToast('👋 ' + (data.from || 'لاعب') + ' أرسل لك طلب صداقة');
    friendState = 'incoming'; renderFriendButton();
  });

})();