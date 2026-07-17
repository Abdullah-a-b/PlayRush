/* ============================================================
   بروفايل لاعب قابل للفتح من الإشعارات (lobby + categories)
   يعرض: الأفاتار + الاسم + الرتبة + إحصائيات اللعبة (إن وُجدت) + العامة
   + ثلاثة أزرار: إضافة صديق / حظر / إبلاغ — نفس منطق داخل اللعبة.
   - في lobby.html: يمرّر selectedGameMode → يعرض إحصائيات تلك اللعبة + العامة
   - في categories.html: لا يمرّر mode → إحصائيات عامة فقط
   يتطلب: socket عام + token + (اختياري) showToast / sanitizeHTML
   ============================================================ */
(function () {
  if (typeof window === 'undefined') return;

  function _token() {
    return (typeof getToken === 'function')
      ? getToken()
      : (localStorage.getItem('token') || sessionStorage.getItem('token'));
  }
  function _esc(s) {
    return (typeof sanitizeHTML === 'function') ? sanitizeHTML(String(s ?? '')) : String(s ?? '');
  }
  function _toast(m) { if (typeof showToast === 'function') showToast(m); }

  // اللعبة الحالية: من sessionStorage (lobby محدّدة) أو null (categories)
  function _currentGameMode() {
    // categories تحذف selectedGameMode عند دخولها، lobby تضبطها
    const fromSession = sessionStorage.getItem('selectedGameMode');
    // نعتمد على متغيّر صريح إن وُجد (يضبطه كل صفحة)
    if (typeof window.PROFILE_GAME_MODE !== 'undefined') return window.PROFILE_GAME_MODE;
    return fromSession || null;
  }

  let _modal = null;
  let _state = { targetId: null, relation: 'none', pendingAction: null };

  function _ensureModal() {
    if (_modal) return _modal;
    const el = document.createElement('div');
    el.id = 'sharedProfileModal';
    el.style.cssText = `
      display:none; position:fixed; inset:0; z-index:12000;
      background:rgba(0,0,0,0.8); backdrop-filter:blur(5px);
      align-items:center; justify-content:center;`;
    el.innerHTML = `
      <div style="background:#161622; border:1px solid rgba(255,255,255,0.1); border-radius:20px;
                  width:380px; max-width:92vw; max-height:85vh; overflow-y:auto; padding:26px;
                  position:relative; box-shadow:0 0 30px rgba(0,0,0,0.6); text-align:center;">
        <span id="spClose" style="position:absolute; top:14px; left:18px; color:#aaa; font-size:26px; cursor:pointer; line-height:1;">✕</span>
        <img id="spAvatar" src="" style="width:84px; height:84px; border-radius:50%; background:#222; border:3px solid #4a90e2; object-fit:cover;">
        <div style="display:flex; align-items:center; justify-content:center; gap:8px; margin-top:12px;">
          <img id="spFlag" src="" style="width:22px; height:15px; border-radius:2px;" onerror="this.style.display='none'">
          <h3 id="spName" style="color:#fff; margin:0; font-size:18px;">—</h3>
        </div>
        <div style="color:#ffb300; font-size:13px; margin-top:4px;">الترتيب: <span id="spRank">--</span></div>

        <div id="spGameStats" style="display:none; margin-top:18px;">
          <div id="spGameTitle" style="color:#4a90e2; font-size:13px; margin-bottom:8px; font-weight:bold;">إحصائيات اللعبة</div>
          <div id="spRankBadge" style="display:none; font-size:13px; font-weight:800; margin-bottom:10px;"></div>
          <div style="display:flex; justify-content:space-around; background:rgba(255,255,255,0.04); border-radius:12px; padding:12px;">
            <div><div id="spGameWins" style="color:#2ecc71; font-size:20px; font-weight:bold;">0</div><div style="color:#888; font-size:11px;">فوز</div></div>
            <div><div id="spGameLosses" style="color:#e74c3c; font-size:20px; font-weight:bold;">0</div><div style="color:#888; font-size:11px;">خسارة</div></div>
            <div><div id="spGameTotal" style="color:#fff; font-size:20px; font-weight:bold;">0</div><div style="color:#888; font-size:11px;">مجموع</div></div>
          </div>
        </div>

        <div style="margin-top:14px;">
          <div style="color:#9b59b6; font-size:13px; margin-bottom:8px; font-weight:bold;">الإحصائيات العامة</div>
          <div style="display:flex; justify-content:space-around; background:rgba(255,255,255,0.04); border-radius:12px; padding:12px;">
            <div><div id="spGlobalWins" style="color:#2ecc71; font-size:20px; font-weight:bold;">0</div><div style="color:#888; font-size:11px;">فوز</div></div>
            <div><div id="spGlobalLosses" style="color:#e74c3c; font-size:20px; font-weight:bold;">0</div><div style="color:#888; font-size:11px;">خسارة</div></div>
            <div><div id="spGlobalTotal" style="color:#fff; font-size:20px; font-weight:bold;">0</div><div style="color:#888; font-size:11px;">مجموع</div></div>
          </div>
        </div>

        <div id="spActions" style="display:flex; gap:8px; margin-top:20px;">
          <button id="spFriendBtn" style="flex:1; padding:10px; border:none; border-radius:9px; cursor:pointer; font-family:inherit; font-size:13px; color:#fff; background:linear-gradient(135deg,#3498db,#2980b9);"><i class="fa-solid fa-user-plus"></i> إضافة صديق</button>
          <button id="spBlockBtn" style="padding:10px 14px; border:none; border-radius:9px; cursor:pointer; font-family:inherit; font-size:13px; color:#fff; background:#7f3a3a;"><i class="fa-solid fa-ban"></i> حظر</button>
          <button id="spReportBtn" style="padding:10px 14px; border:none; border-radius:9px; cursor:pointer; font-family:inherit; font-size:13px; color:#ccc; background:rgba(255,255,255,0.1);"><i class="fa-solid fa-flag"></i> إبلاغ</button>
        </div>
      </div>`;
    document.body.appendChild(el);
    _modal = el;

    el.querySelector('#spClose').addEventListener('click', _close);
    el.addEventListener('click', (e) => { if (e.target === el) _close(); });
    el.querySelector('#spFriendBtn').addEventListener('click', _onFriendClick);
    el.querySelector('#spBlockBtn').addEventListener('click', _onBlockClick);
    el.querySelector('#spReportBtn').addEventListener('click', _onReportClick);
    return el;
  }

  function _close() { if (_modal) _modal.style.display = 'none'; }

  function _renderFriendBtn() {
    const b = _modal.querySelector('#spFriendBtn');
    const blk = _modal.querySelector('#spBlockBtn');
    const rel = _state.relation;
    // إظهار/إخفاء زر الصداقة حسب الحظر
    if (rel === 'i_blocked' || rel === 'they_blocked') {
      b.style.display = 'none';
    } else {
      b.style.display = '';
    }
    if (rel === 'friends') {
      b.innerHTML = '<i class="fa-solid fa-user-minus"></i> حذف صديق';
      b.style.background = 'linear-gradient(135deg,#e74c3c,#c0392b)';
      b.disabled = false; b.style.opacity = '1'; b.style.cursor = 'pointer';
    } else if (rel === 'pending_outgoing') {
      b.innerHTML = '<i class="fa-solid fa-clock"></i> في انتظار الرد';
      b.style.background = 'rgba(255,255,255,0.12)';
      b.disabled = true; b.style.opacity = '0.7'; b.style.cursor = 'default';
    } else if (rel === 'pending_incoming') {
      b.innerHTML = '<i class="fa-solid fa-user-check"></i> قبول الطلب';
      b.style.background = 'linear-gradient(135deg,#2ecc71,#27ae60)';
      b.disabled = false; b.style.opacity = '1'; b.style.cursor = 'pointer';
    } else if (rel === 'self') {
      _modal.querySelector('#spActions').style.display = 'none';
    } else {
      b.innerHTML = '<i class="fa-solid fa-user-plus"></i> إضافة صديق';
      b.style.background = 'linear-gradient(135deg,#3498db,#2980b9)';
      b.disabled = false; b.style.opacity = '1'; b.style.cursor = 'pointer';
    }
    // زر الحظر
    if (rel === 'i_blocked') {
      blk.innerHTML = '<i class="fa-solid fa-unlock"></i> رفع الحظر';
      blk.style.background = 'linear-gradient(135deg,#e67e22,#d35400)';
    } else {
      blk.innerHTML = '<i class="fa-solid fa-ban"></i> حظر';
      blk.style.background = '#7f3a3a';
    }
  }

  function _onFriendClick() {
    const rel = _state.relation;
    const token = _token();
    if (rel === 'friends') {
      socket.emit('remove_friend_by_id', { token, friend_id: _state.targetId });
      _state.relation = 'none';
    } else if (rel === 'pending_incoming') {
      socket.emit('respond_friend_request', { token, requester_id: _state.targetId, accept: true });
      _state.relation = 'friends';
      _toast('✅ تمت إضافة الصديق');
    } else if (rel === 'pending_outgoing') {
      return;
    } else {
      socket.emit('send_friend_request_by_id', { token, friend_id: _state.targetId });
      _state.relation = 'pending_outgoing';
      _toast('✅ أُرسل طلب الصداقة');
    }
    _renderFriendBtn();
  }

  function _onBlockClick() {
    const token = _token();
    if (_state.relation === 'i_blocked') {
      socket.emit('unblock_player_by_id', { token, target_id: _state.targetId });
      _state.relation = 'none';
      _toast('🔓 تم رفع الحظر');
    } else {
      socket.emit('block_player_by_id', { token, target_id: _state.targetId });
      _state.relation = 'i_blocked';
      _toast('🚫 تم حظر اللاعب');
    }
    _renderFriendBtn();
  }

  function _onReportClick() {
    const token = _token();
    socket.emit('report_player_by_id', { token, target_id: _state.targetId });
    _toast('🚩 تم إرسال البلاغ');
  }

  // الدالة العامة: تفتح البروفايل بجلب البيانات من الخادم
  window.openPlayerProfileById = function (targetId) {
    if (!targetId) return;
    _ensureModal();
    _state.targetId = targetId;
    const gameMode = _currentGameMode();
    socket.emit('get_player_profile', { token: _token(), target_id: targetId, game_mode: gameMode });
  };

  // استقبال البيانات وعرضها
  if (typeof socket !== 'undefined' && socket) {
    socket.on('player_profile_result', (res) => {
      if (!res || !res.ok) { _toast((res && res.msg) || 'تعذّر جلب البروفايل'); return; }
      _ensureModal();
      const s = res.stats || {};
      _state.targetId = res.target_id;
      _state.relation = res.relation || 'none';

      _modal.querySelector('#spAvatar').src = s.avatar || '';
      _modal.querySelector('#spName').textContent = _esc(s.name || 'لاعب');
      const flag = _modal.querySelector('#spFlag');
      if (s.flag) { flag.src = s.flag; flag.style.display = ''; } else { flag.style.display = 'none'; }
      _modal.querySelector('#spRank').textContent = s.rank ?? '--';

      // إحصائيات اللعبة (لو وُجدت)
      const gs = _modal.querySelector('#spGameStats');
      if (s.game && s.game_mode) {
        gs.style.display = '';
        const title = (typeof GAME_THEMES !== 'undefined' && GAME_THEMES[s.game_mode]?.title) || s.game_mode;
        _modal.querySelector('#spGameTitle').textContent = `إحصائيات ${title}`;
        _modal.querySelector('#spGameWins').textContent = s.game.wins ?? 0;
        _modal.querySelector('#spGameLosses').textContent = s.game.losses ?? 0;
        _modal.querySelector('#spGameTotal').textContent = s.game.total ?? 0;
        // شارة الرتبة الموسمية
        const rb = _modal.querySelector('#spRankBadge');
        if (s.game_rank && s.game_rank.label) {
          rb.style.display = '';
          rb.innerHTML = `<i class="fa-solid fa-medal"></i> ${_esc(s.game_rank.label)} · ${_esc(s.game_rank.elo)} نقطة`;
          rb.style.color = s.game_rank.color || '#facc15';
        } else { rb.style.display = 'none'; }
      } else {
        gs.style.display = 'none';
      }

      // العامة
      const g = s.global || { wins: 0, losses: 0, total: 0 };
      _modal.querySelector('#spGlobalWins').textContent = g.wins ?? 0;
      _modal.querySelector('#spGlobalLosses').textContent = g.losses ?? 0;
      _modal.querySelector('#spGlobalTotal').textContent = g.total ?? 0;

      _modal.querySelector('#spActions').style.display = (_state.relation === 'self') ? 'none' : 'flex';
      _renderFriendBtn();
      _modal.style.display = 'flex';
    });
  }
})();
