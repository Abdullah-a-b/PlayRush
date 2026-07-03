/* ============================================================
   🛒 المتجر (مشترك بين اللوبيات و categories)
   يتطلب: socket عام + token + showToast + sanitizeHTML
   السياق: window.STORE_CONTEXT = 'huroof' (لوبي) أو 'categories'
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

  let _store = { helps: [], cosmetics: [], wallet: { coins: 0, gems: 0 },
                 level: 0, help_inventory: {}, owned_cosmetics: [] };
  let _activeTab = 'help';
  let _loaded = false;

  function _context() {
    return window.STORE_CONTEXT || 'categories';
  }

  window.openStore = function () {
    // نجلب البيانات أول مرة (أو نحدّثها)
    socket.emit('fetch_store', { token: _token(), context: _context() });
  };

  socket.on('store_data', (data) => {
    if (!data) return;
    _store = data;
    _loaded = true;
    renderStore();
  });

  function _rarityColor(r) {
    return { common: '#9e9e9e', rare: '#2196F3', epic: '#9c27b0', legendary: '#ff9800' }[r] || '#9e9e9e';
  }

  function _itemsForTab(tab) {
    if (tab === 'help') return [...(_store.upgrades || []), ...(_store.helps || [])];
    return (_store.cosmetics || []).filter(c => c.category === tab);
  }

  function _isOwned(item) {
    if (item.category === 'help') return false; // المساعدات تُشترى متكررة
    return (_store.owned_cosmetics || []).includes(item.id);
  }

  function _canAfford(item) {
    const bal = item.currency === 'coins' ? _store.wallet.coins : _store.wallet.gems;
    return bal >= item.price;
  }

  function _levelOk(item) {
    return (_store.level || 0) >= item.unlock_level;
  }

  function renderStore() {
    const grid = document.getElementById('storeGrid');
    if (!grid) return;
    const items = _itemsForTab(_activeTab);
    if (!items.length) {
      grid.innerHTML = '<div style="color:#888;text-align:center;padding:40px;grid-column:1/-1;">لا عناصر في هذا القسم بعد.</div>';
      return;
    }
    grid.innerHTML = items.map(item => {
      const owned = _isOwned(item);
      const locked = !_levelOk(item);
      const afford = _canAfford(item);
      const curIcon = item.currency === 'coins' ? '🪙' : '💎';
      const ownedHelpQty = item.category === 'help' ? (_store.help_inventory[item.ref_id] || 0) : null;

      let btnHtml;
      if (owned) {
        btnHtml = `<button class="store-buy owned" disabled>تملكه ✓</button>`;
      } else if (locked) {
        btnHtml = `<button class="store-buy locked" disabled>🔒 مستوى ${item.unlock_level}</button>`;
      } else if (item.price === 0) {
        btnHtml = `<button class="store-buy free" data-buy="${item.id}">مجاني — احصل عليه</button>`;
      } else {
        btnHtml = `<button class="store-buy ${afford ? '' : 'cant'}" data-buy="${item.id}" ${afford ? '' : 'disabled'}>${item.price} ${curIcon}</button>`;
      }

      // للأفاتار: نعرض الصورة الفعلية بدل الإيموجي
      let iconHtml;
      if (item.category === 'avatar' && item.asset) {
        const inGames = window.location.pathname.includes('/games/');
        const url = `${inGames ? '../' : ''}${item.asset}`;
        iconHtml = `<img src="${url}" alt="${_esc(item.name)}" style="width:60px;height:60px;border-radius:50%;object-fit:cover;">`;
      } else {
        iconHtml = item.icon || '🎁';
      }

      // وسم نطاق العبارة (عامة أو خاصة باللعبة)
      let scopeLabel = '';
      if (item.category === 'chat_phrase') {
        if (item.scope === 'game') {
          scopeLabel = `<div class="store-scope game">🎮 خاصة باللعبة</div>`;
        } else {
          scopeLabel = `<div class="store-scope general">💬 عامة (كل الدردشات)</div>`;
        }
      }

      return `
        <div class="store-card" style="border-color:${_rarityColor(item.rarity)};">
          <div class="store-rarity" style="background:${_rarityColor(item.rarity)};">${_rarityLabel(item.rarity)}</div>
          <div class="store-icon">${iconHtml}</div>
          <div class="store-name">${_esc(item.name)}</div>
          ${scopeLabel}
          ${item.desc ? `<div class="store-desc">${_esc(item.desc)}</div>` : ''}
          ${ownedHelpQty !== null ? `<div class="store-owned-qty">تملك: ${ownedHelpQty}</div>` : ''}
          ${btnHtml}
        </div>`;
    }).join('');

    grid.querySelectorAll('[data-buy]').forEach(btn => {
      btn.addEventListener('click', () => {
        const itemId = btn.dataset.buy;
        btn.disabled = true;
        btn.textContent = '...';
        socket.emit('purchase_item', { token: _token(), itemId });
      });
    });
  }

  function _rarityLabel(r) {
    return { common: 'عادي', rare: 'نادر', epic: 'ملحمي', legendary: 'أسطوري' }[r] || 'عادي';
  }

  socket.on('purchase_result', (data) => {
    if (!data) { renderStore(); return; }
    _toast((data.ok ? '✅ ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) {
      // نحدّث المحفظة محلياً
      if (data.wallet) {
        _store.wallet = data.wallet;
        _updateWalletDisplay(data.wallet);
      }
      // نحدّث الملكية
      if (data.category === 'help') {
        // نزيد المخزون محلياً (نعيد الجلب للدقة)
        socket.emit('fetch_store', { token: _token(), context: _context() });
        return;
      } else if (data.itemId) {
        _store.owned_cosmetics = _store.owned_cosmetics || [];
        _store.owned_cosmetics.push(data.itemId);
      }
    }
    renderStore();
  });

  function _updateWalletDisplay(wallet) {
    const c = document.getElementById('coins');
    const g = document.getElementById('gems');
    if (c && typeof wallet.coins === 'number') c.textContent = wallet.coins;
    if (g && typeof wallet.gems === 'number') g.textContent = wallet.gems;
  }

  // تبديل التبويبات
  document.addEventListener('click', (e) => {
    const tab = e.target.closest('.store-tab');
    if (tab) {
      document.querySelectorAll('.store-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      _activeTab = tab.dataset.stab;
      renderStore();
    }
  });

  // نفتح المتجر تلقائياً عند الضغط على قسم المتجر (categories)
  document.addEventListener('click', (e) => {
    const navBtn = e.target.closest('[data-section="store"]');
    if (navBtn) {
      setTimeout(() => window.openStore(), 100);
    }
  });
})();
