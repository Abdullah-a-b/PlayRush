/*  تجهيز المساعدات */
(function () {
  if (typeof window === 'undefined') return;
  function _token() { return (typeof getToken === 'function') ? getToken() : (localStorage.getItem('token') || sessionStorage.getItem('token')); }
  function _esc(s) { return (typeof sanitizeHTML === 'function') ? sanitizeHTML(String(s ?? '')) : String(s ?? ''); }
  function _toast(m) { if (typeof showToast === 'function') showToast(m); }
  let _data = { loadout: [], inventory: {}, catalog: [], slots: 3, defaultLoadout: [] };
  let _selected = [];
  function _helpById(id) { return (_data.catalog || []).find(h => h.id === id); }
  function _availableHelps() {
    const DEF = _data.defaultLoadout || ['extend_time', 'change_question', 'count_letters'];
    const owned = Object.keys(_data.inventory || {});
    const all = new Set([...DEF, ...owned]);
    return (_data.catalog || []).filter(h => all.has(h.id));
  }
  window.openLoadout = function () {
    socket.emit('get_help_loadout', { token: _token(), game: (window.CURRENT_GAME || 'huroof') });
    let modal = document.getElementById('loadoutModal');
    if (!modal) {
      modal = document.createElement('div'); modal.id = 'loadoutModal'; modal.className = 'loadout-modal';
      modal.innerHTML = `<div class="loadout-box"><span class="loadout-close" onclick="document.getElementById('loadoutModal').style.display='none'">✕</span><h2>🎯 تجهيز المساعدات</h2><p class="loadout-hint">اختر المساعدات التي تريد وضعها في خاناتك قبل اللعب.</p><div class="loadout-slots" id="loadoutSlots"></div><h3 class="loadout-subtitle">المساعدات المتاحة</h3><div class="loadout-available" id="loadoutAvailable"></div><button class="loadout-save" id="loadoutSaveBtn">حفظ التشكيل</button></div>`;
      document.body.appendChild(modal);
      modal.querySelector('#loadoutSaveBtn').addEventListener('click', saveLoadout);
    }
    modal.style.display = 'flex';
  };
  socket.on('help_loadout_data', (data) => {
    if (!data) return;
    _data = data; _selected = (data.loadout || []).slice(0, data.slots); renderLoadout();
  });
  function renderLoadout() {
    const slotsEl = document.getElementById('loadoutSlots'); const availEl = document.getElementById('loadoutAvailable');
    if (!slotsEl || !availEl) return;
    slotsEl.innerHTML = '';
    for (let i = 0; i < _data.slots; i++) {
      const id = _selected[i]; const h = id ? _helpById(id) : null;
      const slot = document.createElement('div'); slot.className = 'loadout-slot' + (h ? ' filled' : ' empty');
      if (h) {
        slot.innerHTML = `<span class="ls-icon">${h.icon}</span><span class="ls-name">${_esc(h.name)}</span><span class="ls-remove">✕</span>`;
        slot.querySelector('.ls-remove').addEventListener('click', () => { _selected.splice(i, 1); renderLoadout(); });
      } else { slot.innerHTML = `<span class="ls-empty">+</span>`; }
      slotsEl.appendChild(slot);
    }
    availEl.innerHTML = '';
    const DEF = _data.defaultLoadout || ['extend_time', 'change_question', 'count_letters'];
    _availableHelps().forEach(h => {
      const inSlot = _selected.includes(h.id); const qty = _data.inventory[h.id]; const isDefault = DEF.includes(h.id);
      const card = document.createElement('button'); card.className = 'loadout-help' + (inSlot ? ' selected' : '');
      card.disabled = inSlot || _selected.length >= _data.slots;
      card.innerHTML = `<span class="lh-icon">${h.icon}</span><span class="lh-name">${_esc(h.name)}</span><span class="lh-qty">${isDefault ? 'أساسية' : 'تملك: ' + (qty || 0)}</span>`;
      card.addEventListener('click', () => {
        if (_selected.length >= _data.slots || _selected.includes(h.id)) return;
        //  تعارض التجهيز (مثل: درع الرصيد × فرصة ثانية بالبنك)
        const confs = _data.conflicts || [];
        for (const pair of confs) {
          const other = pair[0] === h.id ? pair[1] : (pair[1] === h.id ? pair[0] : null);
          if (other && _selected.includes(other)) {
            const oh = _helpById(other);
            if (typeof showToast === 'function') showToast(`⚠️ لا يمكن تجهيز "${h.name}" مع "${(oh && oh.name) || ''}" معاً`);
            else alert(`لا يمكن تجهيز "${h.name}" مع "${(oh && oh.name) || ''}" معاً`);
            return;
          }
        }
        _selected.push(h.id); renderLoadout();
      });
      availEl.appendChild(card);
    });
  }
  function saveLoadout() { socket.emit('set_help_loadout', { token: _token(), slots: _selected }); }
  socket.on('help_loadout_result', (data) => {
    if (!data) return;
    _toast((data.ok ? '✅ ' : '⚠️ ') + (data.msg || ''));
    if (data.ok) { const modal = document.getElementById('loadoutModal'); if (modal) setTimeout(() => { modal.style.display = 'none'; }, 600); }
  });
})();
