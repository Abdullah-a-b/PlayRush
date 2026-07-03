// ============================================================
// 👥 قسم الأصدقاء (مشترك بين اللوبي و categories)
// يتطلب: socket عام + token + دالة showToast + sanitizeHTML (اختياري)
// ============================================================
(function() {
  const token = (typeof getToken === 'function')
    ? getToken()
    : (localStorage.getItem('token') || sessionStorage.getItem('token'));

  let _lastSearchedId = null;  // آخر لاعب ظهر في البحث (لتحديثه لحظياً)

  function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }
  function avatarSrc(a) {
    if (!a) return 'assets/avatars/avatar_1.svg';
    return a.startsWith('assets/') || a.startsWith('http') ? a : 'assets/avatars/' + a;
  }

  // يربط النقر على [data-profile] لفتح بروفايل اللاعب (نفس مودال الإشعارات)
  function _bindProfileClicks(container) {
    if (!container) return;
    container.querySelectorAll('[data-profile]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(el.dataset.profile);
        if (id && typeof openPlayerProfileById === 'function') {
          openPlayerProfileById(id);
        }
      });
    });
  }

  // تأثير hover للعناصر القابلة للنقر (يوضّح أنها تفاعلية)
  function _bindProfileHover(container) {
    if (!container) return;
    container.querySelectorAll('.profile-clickable').forEach(el => {
      el.addEventListener('mouseenter', () => { el.style.background = 'rgba(74,144,226,0.15)'; });
      el.addEventListener('mouseleave', () => { el.style.background = 'transparent'; });
    });
  }

  // يحدّث زر نتيجة البحث إلى "صديق بالفعل" لحظياً (عند قبول الطرف الآخر)
  function _updateSearchBtnToFriend() {
    const btn = document.getElementById('searchAddBtn');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'صديق بالفعل';
    btn.style.background = 'rgba(46,204,113,0.25)';
    btn.style.color = '#2ecc71';
    btn.style.cursor = 'default';
  }

  // يعيد تشغيل البحث الحالي (لتحديث حالة الزر بعد تغيّر العلاقة)
  function _refreshCurrentSearch() {
    const input = document.getElementById('friendSearchInput');
    const btn = document.getElementById('friendSearchBtn');
    if (input && input.value && btn) {
      setTimeout(() => btn.click(), 300);
    }
  }

  const friendsModal = document.getElementById('friendsModal');
  const friendsNavBtn = document.getElementById('friendsNavBtn');
  const closeFriends = document.getElementById('closeFriends');

  // الصفحة لازم يكون فيها لوحات الأصدقاء (سواء modal أو inline section)
  const hasPanels = document.getElementById('friendsListPanel') && document.getElementById('friendsRequestsPanel');
  if (!hasPanels) return;

  // فتح/إغلاق (للوبي — modal)
  if (friendsModal && friendsNavBtn) {
    friendsNavBtn.addEventListener('click', () => {
      friendsModal.style.display = 'flex';
      requestFriendsData();
    });
    closeFriends?.addEventListener('click', () => { friendsModal.style.display = 'none'; });
    friendsModal.addEventListener('click', (e) => {
      if (e.target === friendsModal) friendsModal.style.display = 'none';
    });
  }

  // categories — زر القسم (data-section="friends")
  const sectionBtn = document.querySelector('[data-section="friends"]');
  if (sectionBtn) {
    sectionBtn.addEventListener('click', () => { setTimeout(requestFriendsData, 100); });
  }

  // التبويبات
  document.querySelectorAll('.friends-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.friends-tab').forEach(b => {
        b.classList.remove('active');
        b.style.background = 'rgba(255,255,255,0.05)';
        b.style.color = '#ccc';
        b.style.border = '1px solid rgba(255,255,255,0.15)';
      });
      btn.classList.add('active');
      btn.style.background = 'linear-gradient(135deg,#667eea,#764ba2)';
      btn.style.color = '#fff';
      btn.style.border = 'none';
      const tab = btn.dataset.ftab;
      document.getElementById('friendsListPanel').style.display = tab === 'list' ? 'block' : 'none';
      document.getElementById('friendsRequestsPanel').style.display = tab === 'requests' ? 'block' : 'none';
      const searchPanel = document.getElementById('friendsSearchPanel');
      if (searchPanel) searchPanel.style.display = tab === 'search' ? 'block' : 'none';
    });
  });

  // ----- بحث عن لاعب بالمعرّف (ID) -----
  const searchBtn = document.getElementById('friendSearchBtn');
  const searchInput = document.getElementById('friendSearchInput');
  if (searchBtn && searchInput) {
    const doSearch = () => {
      let q = (searchInput.value || '').trim().toUpperCase();
      if (!q) return;
      // نقبل الإدخال مع أو بدون البادئة PR-
      if (!q.startsWith('PR-') && /^\d+$/.test(q)) q = 'PR-' + q;
      const resultBox = document.getElementById('friendSearchResult');
      resultBox.innerHTML = '<p style="color:#aaa;">جارٍ البحث…</p>';
      socket.emit('search_player_by_id', { token, player_id: q });
    };
    searchBtn.addEventListener('click', doSearch);
    searchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
  }

  socket.on('search_player_result', (res) => {
    const box = document.getElementById('friendSearchResult');
    if (!box) return;
    if (!res || !res.ok) {
      box.innerHTML = `<p style="color:#e57373;">${escHtml((res && res.msg) || 'لم يُعثر على اللاعب')}</p>`;
      return;
    }
    const p = res.player;
    const statusLabel = {
      none: 'إضافة صديق', pending: 'طلب معلّق', friends: 'صديق بالفعل',
      self: 'هذا أنت', i_blocked: 'رفع الحظر', they_blocked: 'حظرك هذا اللاعب'
    }[p.relation] || 'إضافة صديق';
    // الزر قابل للضغط في حالتين: إضافة صديق (none) أو رفع الحظر (i_blocked)
    const isAdd = p.relation === 'none';
    const isUnblock = p.relation === 'i_blocked';
    const clickable = isAdd || isUnblock;
    const btnColor = isUnblock
      ? 'linear-gradient(135deg,#e67e22,#d35400)'   // برتقالي لرفع الحظر
      : (isAdd ? 'linear-gradient(135deg,#4a90e2,#357abd)' : 'rgba(255,255,255,0.1)');
    box.innerHTML = `
      <div style="display:flex; align-items:center; gap:12px; padding:12px; background:rgba(255,255,255,0.05); border-radius:10px;">
        <div class="profile-clickable" data-profile="${p.id}" title="اعرض البروفايل" style="display:flex;align-items:center;gap:12px;flex:1;cursor:pointer;padding:4px 8px;border-radius:8px;transition:background 0.15s;">
          <img src="${escHtml(avatarSrc(p.avatar))}" style="width:46px;height:46px;border-radius:50%;background:#222;pointer-events:none;">
          <div style="flex:1;pointer-events:none;">
            <div style="color:#fff;font-weight:bold;">${escHtml(p.name)} <i class="fa-solid fa-circle-info" style="color:#4a90e2;font-size:12px;opacity:0.7;"></i></div>
            <div style="color:#888;font-size:12px;">${escHtml(p.player_id)}</div>
          </div>
        </div>
        <button id="searchAddBtn" ${clickable ? '' : 'disabled'}
          style="padding:8px 14px;border-radius:7px;border:none;font-family:inherit;font-size:13px;
          background:${btnColor};
          color:${clickable ? '#fff' : '#888'};cursor:${clickable ? 'pointer' : 'default'};">${escHtml(statusLabel)}</button>
      </div>`;
    _bindProfileClicks(box);
    _bindProfileHover(box);
    // نحفظ آخر نتيجة بحث لتحديثها لحظياً عند القبول
    _lastSearchedId = p.id;
    if (clickable) {
      document.getElementById('searchAddBtn').addEventListener('click', () => {
        const btn = document.getElementById('searchAddBtn');
        if (isUnblock) {
          socket.emit('unblock_player_by_id', { token, target_id: p.id });
          if (typeof showToast === 'function') showToast('🔓 تم رفع الحظر');
          btn.disabled = true;
          btn.textContent = 'إضافة صديق';
          btn.style.background = 'rgba(255,255,255,0.1)';
          btn.style.color = '#888';
          // إعادة بحث تلقائية لتحديث الحالة
          setTimeout(() => { const q = document.getElementById('friendSearchInput'); if (q && q.value) document.getElementById('friendSearchBtn').click(); }, 400);
        } else {
          socket.emit('send_friend_request_by_id', { token, friend_id: p.id });
          if (typeof showToast === 'function') showToast('✅ أُرسل طلب الصداقة');
          btn.disabled = true;
          btn.textContent = 'طلب معلّق';
        }
      });
    }
  });

  function requestFriendsData() {
    if (typeof socket !== 'undefined' && socket && token) {
      socket.emit('fetch_friends_data', { token });
    }
  }

  // استقبال البيانات
  if (typeof socket !== 'undefined' && socket) {
    socket.on('friends_data', (data) => {
      renderFriendsList(data.friends || []);
      renderRequests(data.pending || []);
      updateFriendsBadge(data.pending_count || 0);
    });

    socket.on('friend_response_result', (res) => {
      if (typeof showToast === 'function') showToast((res.ok ? '✅ ' : '⚠️ ') + res.msg);
      requestFriendsData(); // إعادة تحميل
    });

    socket.on('friend_removed', (data) => {
      if (typeof showToast === 'function') showToast('تم حذف الصديق');
      requestFriendsData();
      // لو المحذوف هو نفسه الظاهر في البحث → نعيد البحث ليتغيّر الزر إلى "إضافة صديق"
      const removedId = data && (data.friend_id || data.target_id);
      if (removedId && removedId === _lastSearchedId) {
        _refreshCurrentSearch();
      }
    });

    // طلب جديد أو قبول وصل حيّاً → نحدّث القوائم والشارة
    socket.on('new_notification', (n) => {
      if (!n) return;
      if (n.type === 'friend_request') {
        requestFriendsData();
      } else if (n.type === 'friend_accepted') {
        // شخص قبِل طلبي → نحدّث قائمة الأصدقاء + زر البحث لو كان هو نفسه
        requestFriendsData();
        if (n.sender_id && n.sender_id === _lastSearchedId) {
          _updateSearchBtnToFriend();
        }
      }
    });

    // ----- دعوات اللعب (بلا دردشة) -----
    // نتيجة إرسال دعوتي
    socket.on('play_invite_result', (res) => {
      if (typeof showToast === 'function') showToast((res.ok ? '✅ ' : '⚠️ ') + res.msg);
    });

    // وصلتني دعوة من صديق → نعرض تأكيداً
    socket.on('play_invite_received', (inv) => {
      if (!inv) return;
      const name = escHtml(inv.inviterName || 'صديق');
      const ask = () => {
        socket.emit('respond_play_invite', {
          token, inviterId: inv.inviterId, gameMode: inv.gameMode, accept: true
        });
      };
      const decline = () => {
        socket.emit('respond_play_invite', {
          token, inviterId: inv.inviterId, gameMode: inv.gameMode, accept: false
        });
      };
      if (typeof showConfirm === 'function') {
        showConfirm('دعوة لعب', `دعاك ${name} للعب. تقبل؟`, ask, decline);
      } else if (confirm(`دعاك ${inv.inviterName} للعب. تقبل؟`)) {
        ask();
      } else {
        decline();
      }
    });

    // صديقي رفض الدعوة
    socket.on('play_invite_declined', (d) => {
      if (typeof showToast === 'function') showToast(`اعتذر ${escHtml(d?.byName || 'صديقك')} عن الدعوة`);
    });

    // الغرفة جاهزة → ندخلها ونتوجّه للعبة
    // ملاحظة: قبول دعوة الصديق الآن يستخدم نفس تدفّق match_found (شاشة العد)
    // الذي يعالجه lobby.js — فلا حاجة لمعالج منفصل هنا.
  }

  function renderFriendsList(friends) {
    const panel = document.getElementById('friendsListPanel');
    if (!friends.length) {
      panel.innerHTML = '<div style="text-align:center;color:#888;padding:30px;">لا يوجد أصدقاء بعد</div>';
      return;
    }
    panel.innerHTML = friends.map(f => `
      <div style="display:flex;align-items:center;gap:12px;padding:10px;border-bottom:1px solid rgba(255,255,255,0.07);">
        <div class="profile-clickable" data-profile="${f.id}" title="اعرض البروفايل" style="display:flex;align-items:center;gap:10px;flex:1;cursor:pointer;padding:4px 8px;border-radius:8px;transition:background 0.15s;">
          <img src="${escHtml(avatarSrc(f.avatar))}" style="width:42px;height:42px;border-radius:50%;background:#222;pointer-events:none;">
          <span style="color:#fff;pointer-events:none;">${escHtml(f.name)}</span>
          <i class="fa-solid fa-circle-info" style="color:#4a90e2;font-size:12px;opacity:0.7;pointer-events:none;"></i>
        </div>
        <button data-invite="${f.id}" title="ادعُ للعب" style="background:rgba(74,144,226,0.2);color:#7fb3ec;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;"><i class="fa-solid fa-gamepad"></i> العب</button>
        <button data-remove="${f.id}" style="background:rgba(244,67,54,0.15);color:#e57373;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;">حذف</button>
      </div>`).join('');
    _bindProfileClicks(panel);
    _bindProfileHover(panel);
    panel.querySelectorAll('[data-invite]').forEach(btn => {
      btn.addEventListener('click', () => {
        const gm = (typeof selectedGameMode !== 'undefined' && selectedGameMode)
          ? selectedGameMode
          : (sessionStorage.getItem('selectedGameMode') || 'huroof');
        socket.emit('invite_friend_to_play', { token, friend_id: parseInt(btn.dataset.invite), gameMode: gm });
        if (typeof showToast === 'function') showToast('⏳ جارٍ إرسال الدعوة…');
      });
    });
    panel.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', () => {
        socket.emit('remove_friend', { token, friend_id: parseInt(btn.dataset.remove) });
      });
    });
  }

  function renderRequests(pending) {
    const panel = document.getElementById('friendsRequestsPanel');
    if (!pending.length) {
      panel.innerHTML = '<div style="text-align:center;color:#888;padding:30px;">لا توجد طلبات معلّقة</div>';
      return;
    }
    panel.innerHTML = pending.map(p => `
      <div style="display:flex;align-items:center;gap:12px;padding:10px;border-bottom:1px solid rgba(255,255,255,0.07);">
        <div class="profile-clickable" data-profile="${p.id}" title="اعرض البروفايل" style="display:flex;align-items:center;gap:10px;flex:1;cursor:pointer;padding:4px 8px;border-radius:8px;transition:background 0.15s;">
          <img src="${escHtml(avatarSrc(p.avatar))}" style="width:42px;height:42px;border-radius:50%;background:#222;pointer-events:none;">
          <span style="color:#fff;pointer-events:none;">${escHtml(p.name)}</span>
          <i class="fa-solid fa-circle-info" style="color:#4a90e2;font-size:12px;opacity:0.7;pointer-events:none;"></i>
        </div>
        <button data-accept="${p.id}" style="background:rgba(76,175,80,0.2);color:#81c784;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;">قبول</button>
        <button data-reject="${p.id}" style="background:rgba(244,67,54,0.15);color:#e57373;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;">رفض</button>
      </div>`).join('');
    _bindProfileClicks(panel);
    _bindProfileHover(panel);
    panel.querySelectorAll('[data-accept]').forEach(btn => {
      btn.addEventListener('click', () => {
        socket.emit('respond_friend_request', { token, requester_id: parseInt(btn.dataset.accept), accept: true });
      });
    });
    panel.querySelectorAll('[data-reject]').forEach(btn => {
      btn.addEventListener('click', () => {
        socket.emit('respond_friend_request', { token, requester_id: parseInt(btn.dataset.reject), accept: false });
      });
    });
  }

  function updateFriendsBadge(count) {
    const badge = document.getElementById('friendsBadge');
    const reqBadge = document.getElementById('reqCountBadge');
    if (badge) {
      badge.style.display = count > 0 ? 'flex' : 'none';
      badge.textContent = count > 9 ? '9+' : count;
    }
    if (reqBadge) {
      reqBadge.style.display = count > 0 ? 'inline' : 'none';
      reqBadge.textContent = count;
    }
  }

  // نجلب عدد الطلبات عند تحميل الصفحة (لإظهار الشارة فوراً)
  if (token) {
    setTimeout(requestFriendsData, 1500);
  }
})();
