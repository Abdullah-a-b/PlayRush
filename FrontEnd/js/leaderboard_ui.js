/* ============================================================
   leaderboard_ui.js — نافذة الصدارة في لوبي كل لعبة (قسمان)
   Ranked (Elo) + Wins (الأقل مباريات يتقدّم عند التعادل).
   يعتمد ProgressionAPI. الوضع من selectedGameMode.
   ============================================================ */
(function () {
  'use strict';

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function avatarUrl(a) {
    if (typeof getValidAvatarUrl === 'function') return getValidAvatarUrl(a);
    return a || 'assets/avatars/avatar_1.svg';
  }

  var currentTab = 'ranked';
  var cachedData = null;

  function rowEl(item, tab) {
    var row = el('div', 'lb-row' + (item.is_me ? ' me' : ''));
    var pos = el('div', 'lb-pos');
    pos.textContent = item.position;
    if (item.position === 1) pos.classList.add('gold');
    else if (item.position === 2) pos.classList.add('silver');
    else if (item.position === 3) pos.classList.add('bronze');
    row.appendChild(pos);

    var img = el('img', 'lb-avatar');
    img.src = avatarUrl(item.avatar); img.alt = '';
    img.onerror = function () { this.src = 'assets/avatars/avatar_1.svg'; };
    row.appendChild(img);

    var info = el('div', 'lb-info');
    info.appendChild(el('div', 'lb-name', esc(item.player_name)));
    if (tab === 'ranked') {
      // 🛡️ شارة رتبة (زي الألعاب العالمية): سداسية بلون الرتبة + الدرجة
      var label = item.rank_label || '';
      var div = (label.match(/(I{1,3})\s*$/) || [,''])[1];
      var badge = el('span', 'lb-rank-hex');
      badge.innerHTML = '<span class="lb-hex" style="--c:' + (item.color || '#cd7f32')
        + '">' + esc(div || '•') + '</span>'
        + '<span class="lb-rank-name">' + esc(label) + '</span>';
      info.appendChild(badge);
    } else {
      info.appendChild(el('div', 'lb-sub',
        esc(item.matches) + ' مباراة · ' + esc(item.win_rate || 0) + '%'));
    }
    row.appendChild(info);

    var val = el('div', 'lb-value');
    if (tab === 'ranked') {
      // 📊 بار التقدم داخل الدرجة (بدل الرقم — زي الألعاب العالمية)
      var pct = Math.max(2, Math.min(100, item.division_progress || 0));
      val.innerHTML = '<div class="lb-progress" title="التقدم داخل ' + esc(item.rank_label || '') + '">'
        + '<div class="lb-progress-fill" style="width:' + pct + '%;background:'
        + (item.color || '#facc15') + '"></div></div>';
    } else {
      val.innerHTML = esc(item.wins) + ' <span class="lb-unit">فوز</span>';
    }
    row.appendChild(val);
    // 👤 نقر الصف = بروفايل اللاعب (باللوبي بإحصائيات لعبته، وبcategories العام)
    row.style.cursor = 'pointer';
    row.title = 'عرض البروفايل';
    row.addEventListener('click', function () {
      if (typeof window.openPlayerProfileById === 'function') {
        window.openPlayerProfileById(item.player_id || item.user_id);
      }
    });
    return row;
  }

  function renderList(container, data, tab) {
    container.innerHTML = '';
    var list = tab === 'ranked' ? data.ranked : data.wins;
    if (!list || !list.length) {
      container.appendChild(el('div', 'lb-empty',
        'لا توجد نتائج بعد هذا الموسم — كن أول المتصدّرين! 🏆'));
      return;
    }
    list.forEach(function (item) { container.appendChild(rowEl(item, tab)); });
  }

  function close() {
    var o = document.getElementById('lbOverlay');
    if (o) { o.classList.remove('open'); setTimeout(function () { o.remove(); }, 200); }
  }

  window.openLeaderboard = async function () {
    var mode = (typeof selectedGameMode === 'string' && selectedGameMode) ||
      sessionStorage.getItem('selectedGameMode') || 'huroof';
    close();

    var overlay = el('div', 'lb-overlay');
    overlay.id = 'lbOverlay';
    var modal = el('div', 'lb-modal');

    var head = el('div', 'lb-head');
    head.appendChild(el('h2', null, '<i class="fa-solid fa-ranking-star"></i> الصدارة'));
    var closeBtn = el('button', 'lb-close', '<i class="fa-solid fa-xmark"></i>');
    closeBtn.addEventListener('click', close);
    head.appendChild(closeBtn);
    modal.appendChild(head);

    var tabs = el('div', 'lb-tabs');
    var tRanked = el('button', 'lb-tab active', '<i class="fa-solid fa-medal"></i> التصنيف');
    var tWins = el('button', 'lb-tab', '<i class="fa-solid fa-trophy"></i> الانتصارات');
    tabs.appendChild(tRanked); tabs.appendChild(tWins);
    modal.appendChild(tabs);

    var body = el('div', 'lb-body');
    body.appendChild(el('div', 'lb-loading', 'جارٍ التحميل…'));
    modal.appendChild(body);

    var foot = el('div', 'lb-foot', '');
    modal.appendChild(foot);

    overlay.appendChild(modal);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.body.appendChild(overlay);
    requestAnimationFrame(function () { overlay.classList.add('open'); });

    function switchTab(tab) {
      currentTab = tab;
      tRanked.classList.toggle('active', tab === 'ranked');
      tWins.classList.toggle('active', tab === 'wins');
      if (cachedData) renderList(body, cachedData, tab);
      updateFoot();
    }
    function updateFoot() {
      if (currentTab === 'ranked' && cachedData && cachedData.me && cachedData.me.ranked) {
        foot.style.display = 'block';
        foot.innerHTML = 'مركزك: <b>#' + esc(cachedData.me.position) + '</b> · ' +
          esc(cachedData.me.rank_label) + ' · ' + esc(cachedData.me.elo) + ' نقطة';
      } else { foot.style.display = 'none'; }
    }
    tRanked.addEventListener('click', function () { switchTab('ranked'); });
    tWins.addEventListener('click', function () { switchTab('wins'); });

    try {
      cachedData = await ProgressionAPI.leaderboard(mode);
      renderList(body, cachedData, currentTab);
      updateFoot();
    } catch (e) {
      body.innerHTML = '<div class="lb-empty">تعذّر تحميل الصدارة، حاول لاحقاً.</div>';
    }
  };
})();
