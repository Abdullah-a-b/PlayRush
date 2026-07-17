/* ============================================================
   categories_hub.js — لوحات المهام + البطاقة الموسمية + الصدارة
   يعتمد ProgressionAPI. يُحمّل اللوحة عند فتح تبويبها أول مرة.
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
  function toast(m) { if (typeof showToast === 'function') showToast(m); }
  function avatarUrl(a) {
    if (typeof getValidAvatarUrl === 'function') return getValidAvatarUrl(a);
    return a || 'assets/avatars/avatar_1.svg';
  }

  var loaded = { quests: false, pass: false, leaderboard: false };

  // ============ مكوّن المكافآت ============
  function rewardChips(reward) {
    var chips = [];
    if (reward.coins) chips.push('🪙 ' + reward.coins);
    if (reward.xp) chips.push('⭐ ' + reward.xp + ' خبرة');
    if (reward.gems) chips.push('💎 ' + reward.gems);
    if (reward.pass_xp) chips.push('🎟️ ' + reward.pass_xp);
    return chips.map(function (c) {
      return '<span class="rw-chip">' + esc(c) + '</span>';
    }).join('');
  }

  // ============ لوحة المهام ============
  function questCard(q) {
    var card = el('div', 'quest-card' + (q.done ? ' done' : ''));
    var pct = Math.min(100, Math.round(q.progress / q.target * 100));
    card.innerHTML =
      '<div class="quest-icon">' + esc(q.icon) + '</div>' +
      '<div class="quest-body">' +
        '<div class="quest-title">' + esc(q.title) + '</div>' +
        '<div class="quest-bar"><div class="quest-bar-fill" style="width:' + pct + '%"></div></div>' +
        '<div class="quest-meta">' +
          '<span>' + esc(q.progress) + '/' + esc(q.target) + '</span>' +
          '<span class="quest-rewards">' + rewardChips(q.reward) + '</span>' +
        '</div>' +
      '</div>';
    var action = el('div', 'quest-action');
    if (q.claimed) {
      action.innerHTML = '<span class="quest-claimed"><i class="fa-solid fa-check"></i></span>';
    } else if (q.done) {
      var btn = el('button', 'quest-claim-btn', 'استلم');
      btn.addEventListener('click', async function () {
        btn.disabled = true;
        var r = await ProgressionAPI.claimQuest(q.key);
        if (r && r.ok) { toast('🎉 استلمت مكافأة: ' + q.title); renderQuests(); refreshWallet(); }
        else { toast('⚠️ ' + ((r && r.msg) || 'تعذّر الاستلام')); btn.disabled = false; }
      });
      action.appendChild(btn);
    } else {
      action.innerHTML = '<span class="quest-locked"><i class="fa-solid fa-hourglass-half"></i></span>';
    }
    card.appendChild(action);
    return card;
  }

  async function renderQuests() {
    var hub = document.getElementById('questsHub');
    if (!hub) return;
    try {
      var data = await ProgressionAPI.quests();
      var q = data.quests || {};
      hub.innerHTML = '';
      var groups = [
        { key: 'daily', title: '☀️ مهام يومية', note: 'تتجدّد كل يوم' },
        { key: 'weekly', title: '📅 مهام أسبوعية', note: 'جواهر أكبر — تتجدّد كل أسبوع' },
        { key: 'seasonal', title: '🏆 مهام الموسم', note: 'أكبر الجوائز — تدوم الموسم كامل' },
      ];
      groups.forEach(function (g) {
        var items = q[g.key] || [];
        var sec = el('div', 'hub-block');
        sec.appendChild(el('div', 'hub-block-head',
          '<h3>' + g.title + '</h3><span class="hub-note">' + esc(g.note) + '</span>'));
        var grid = el('div', 'quest-grid');
        if (!items.length) grid.appendChild(el('div', 'hub-empty', 'لا مهام حالياً'));
        items.forEach(function (it) { grid.appendChild(questCard(it)); });
        sec.appendChild(grid);
        hub.appendChild(sec);
      });
    } catch (e) {
      hub.innerHTML = '<div class="hub-empty">تعذّر تحميل المهام، حاول لاحقاً.</div>';
    }
  }

  // ============ لوحة البطاقة الموسمية (Pass) ============
  function passRewardBox(reward, claimed, unlocked, onClaim) {
    var box = el('div', 'pass-reward' +
      (claimed ? ' claimed' : '') + (unlocked ? ' unlocked' : ' locked'));
    var label = reward.type === 'coins' ? ('🪙 ' + reward.amount)
      : reward.type === 'gems' ? ('💎 ' + reward.amount)
      : reward.type === 'cosmetic' ? ('🎨 ' + (reward.note || 'تجميل'))
      : '—';
    box.innerHTML = '<div class="pass-reward-icon">' + esc(reward.icon || '🎁') + '</div>' +
      '<div class="pass-reward-label">' + esc(label) + '</div>';
    if (claimed) {
      box.innerHTML += '<div class="pass-reward-check"><i class="fa-solid fa-check"></i></div>';
    } else if (unlocked && onClaim) {
      box.classList.add('claimable');
      box.addEventListener('click', onClaim);
    }
    return box;
  }

  async function renderPass() {
    var hub = document.getElementById('passHub');
    if (!hub) return;
    try {
      var data = await ProgressionAPI.pass();
      var p = data.pass || {};
      hub.innerHTML = '';

      // رأس: التقدّم + شراء Premium
      var head = el('div', 'pass-head');
      var pct = Math.round((p.xp_in_tier || 0) / (p.xp_per_tier || 100) * 100);
      head.innerHTML =
        '<div class="pass-head-info">' +
          '<div class="pass-season">🎟️ البطاقة الموسمية · ' + esc((data.season && data.season.key) || '') + '</div>' +
          '<div class="pass-tier-now">المحطة ' + esc(p.current_tier) + ' / ' + esc(p.total_tiers) + '</div>' +
          '<div class="pass-xp-bar"><div class="pass-xp-fill" style="width:' + pct + '%"></div></div>' +
          '<div class="pass-xp-text">' + esc(p.xp_in_tier) + '/' + esc(p.xp_per_tier) + ' نقطة للمحطة التالية</div>' +
        '</div>';
      var buyWrap = el('div', 'pass-buy-wrap');
      if (p.is_premium) {
        buyWrap.innerHTML = '<div class="pass-premium-active"><i class="fa-solid fa-crown"></i> Premium مُفعّل</div>';
      } else {
        var buyBtn = el('button', 'pass-buy-btn',
          '<i class="fa-solid fa-crown"></i> ترقية Premium · 💎 ' + esc(p.premium_price));
        buyBtn.addEventListener('click', async function () {
          buyBtn.disabled = true;
          var r = await ProgressionAPI.buyPremium();
          if (r && r.ok) { toast('👑 تم تفعيل Premium Pass!'); renderPass(); refreshWallet(); }
          else { toast('⚠️ ' + ((r && r.msg) || 'تعذّر الشراء')); buyBtn.disabled = false; }
        });
        buyWrap.appendChild(buyBtn);
        buyWrap.appendChild(el('div', 'pass-buy-note',
          'يموّل نفسه: تسترد جواهرك وأكثر عبر المحطات'));
      }
      head.appendChild(buyWrap);
      hub.appendChild(head);

      // مسار المحطات
      var track = el('div', 'pass-track');
      var labels = el('div', 'pass-track-labels');
      labels.innerHTML = '<div class="pass-track-label free">مجاني</div>' +
        '<div class="pass-track-label premium">Premium 👑</div>';
      track.appendChild(labels);

      (p.tiers || []).forEach(function (t) {
        var col = el('div', 'pass-col' + (t.unlocked ? ' unlocked' : ''));
        col.appendChild(el('div', 'pass-col-num', String(t.tier)));
        col.appendChild(passRewardBox(t.free, t.free_claimed, t.unlocked, async function () {
          var r = await ProgressionAPI.claimPassTier(t.tier, 'free');
          if (r && r.ok) { toast('🎁 استلمت مكافأة المحطة ' + t.tier); renderPass(); refreshWallet(); }
          else toast('⚠️ ' + ((r && r.msg) || 'تعذّر الاستلام'));
        }));
        var premClaim = p.is_premium ? async function () {
          var r = await ProgressionAPI.claimPassTier(t.tier, 'premium');
          if (r && r.ok) { toast('👑 استلمت مكافأة Premium للمحطة ' + t.tier); renderPass(); refreshWallet(); }
          else toast('⚠️ ' + ((r && r.msg) || 'تعذّر الاستلام'));
        } : null;
        col.appendChild(passRewardBox(t.premium, t.premium_claimed, t.unlocked && p.is_premium, premClaim));
        track.appendChild(col);
      });
      hub.appendChild(track);
    } catch (e) {
      hub.innerHTML = '<div class="hub-empty">تعذّر تحميل البطاقة، حاول لاحقاً.</div>';
    }
  }

  // ============ لوحة الصدارة العامة ============
  async function renderLeaderboard() {
    var hub = document.getElementById('leaderboardHub');
    if (!hub) return;
    try {
      var data = await ProgressionAPI.globalLeaderboard();
      var list = data.global || [];
      hub.innerHTML = '';
      var head = el('div', 'hub-block-head',
        '<h3>🌍 الصدارة العامة</h3><span class="hub-note">متوسط التصنيف عبر الألعاب · من لعب 3 ألعاب فأكثر</span>');
      hub.appendChild(head);
      if (!list.length) {
        hub.appendChild(el('div', 'hub-empty',
          'لا متصدّرين بعد — العب 3 ألعاب مختلفة لتدخل الصدارة العامة! 🌟'));
        return;
      }
      var box = el('div', 'glb-list');
      list.forEach(function (item) {
        var row = el('div', 'glb-row');
        var pos = el('div', 'glb-pos', String(item.position));
        if (item.position <= 3) pos.classList.add('top');
        row.appendChild(pos);
        var img = el('img', 'glb-avatar'); img.src = avatarUrl(item.avatar);
        img.onerror = function () { this.src = 'assets/avatars/avatar_1.svg'; };
        row.appendChild(img);
        var info = el('div', 'glb-info');
        info.innerHTML = '<div class="glb-name">' + esc(item.player_name) + '</div>' +
          '<div class="glb-sub" style="color:' + esc(item.color || '#facc15') + '">' +
          esc(item.rank_label) + ' · ' + esc(item.games) + ' ألعاب</div>';
        row.appendChild(info);
        row.appendChild(el('div', 'glb-elo', esc(item.avg_elo) + '<span> نقطة</span>'));
        box.appendChild(row);
      });
      hub.appendChild(box);
    } catch (e) {
      hub.innerHTML = '<div class="hub-empty">تعذّر تحميل الصدارة، حاول لاحقاً.</div>';
    }
  }

  function refreshWallet() {
    // تحديث عرض العملات في الشريط العلوي إن توفّرت الدالة
    if (typeof window.refreshUserWallet === 'function') window.refreshUserWallet();
    else if (typeof loadUserData === 'function') loadUserData();
  }

  // ============ ربط التبويبات (تحميل كسول) ============
  function hookTabs() {
    document.querySelectorAll('.nav-btn[data-section]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sec = btn.dataset.section;
        if (sec === 'quests' && !loaded.quests) { loaded.quests = true; renderQuests(); }
        if (sec === 'pass' && !loaded.pass) { loaded.pass = true; renderPass(); }
        if (sec === 'leaderboard' && !loaded.leaderboard) { loaded.leaderboard = true; renderLeaderboard(); }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hookTabs);
  } else { hookTabs(); }

  // كشف لإعادة التحميل اليدوي إن لزم
  window.CategoriesHub = { renderQuests: renderQuests, renderPass: renderPass, renderLeaderboard: renderLeaderboard };
})();
