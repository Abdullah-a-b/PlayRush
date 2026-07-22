/* ============================================================
 نظام الثيمات — تطبيق + اختيار من الإعدادات
 ============================================================ */
(function () {
  if (typeof window === 'undefined') return;

  const THEMES = {
    theme_ocean:   { name: 'المحيط', icon: '🌊', vars: { '--theme-primary': '#1565c0', '--theme-accent': '#00bcd4', '--theme-bg1': '#041627', '--theme-bg2': '#0a2942', '--theme-bg3': '#06384f' } },
    theme_forest:  { name: 'الغابة', icon: '🌲', vars: { '--theme-primary': '#2e7d32', '--theme-accent': '#66bb6a', '--theme-bg1': '#05130a', '--theme-bg2': '#0d2818', '--theme-bg3': '#103820' } },
    theme_cherry:  { name: 'الكرز', icon: '🌸', vars: { '--theme-primary': '#c2185b', '--theme-accent': '#ff80ab', '--theme-bg1': '#1a070f', '--theme-bg2': '#2e0f1c', '--theme-bg3': '#3d1526' } },
    theme_sunset:  { name: 'الغروب', icon: '🌅', vars: { '--theme-primary': '#e65100', '--theme-accent': '#ff9800', '--theme-bg1': '#1a0d05', '--theme-bg2': '#2e1810', '--theme-bg3': '#3d2410' } },
    theme_cyber:   { name: 'سايبر', icon: '🤖', vars: { '--theme-primary': '#00e5ff', '--theme-accent': '#ff00aa', '--theme-bg1': '#05070f', '--theme-bg2': '#0a1226', '--theme-bg3': '#0d1a3d' } },
    theme_lava:    { name: 'الحمم', icon: '🌋', vars: { '--theme-primary': '#d84315', '--theme-accent': '#ff5722', '--theme-bg1': '#160605', '--theme-bg2': '#2a0d08', '--theme-bg3': '#3d130a' } },
    theme_galaxy:  { name: 'المجرّة', icon: '🌌', vars: { '--theme-primary': '#6a1b9a', '--theme-accent': '#ab47bc', '--theme-bg1': '#0d0518', '--theme-bg2': '#1a0a2e', '--theme-bg3': '#24103d' } },
    theme_aurora:  { name: 'الشفق', icon: '❄️', vars: { '--theme-primary': '#00bfa5', '--theme-accent': '#64ffda', '--theme-bg1': '#03120f', '--theme-bg2': '#08231f', '--theme-bg3': '#0a332d' } },
    theme_gold:    { name: 'ذهبي', icon: '✨', vars: { '--theme-primary': '#c9a227', '--theme-accent': '#ffd700', '--theme-bg1': '#151103', '--theme-bg2': '#1f1805', '--theme-bg3': '#2a2008' } },
    theme_diamond: { name: 'الماس', icon: '💎', vars: { '--theme-primary': '#0288d1', '--theme-accent': '#b3e5fc', '--theme-bg1': '#070f14', '--theme-bg2': '#0d1f28', '--theme-bg3': '#10303d' } },
  };

  function _themeKey() {
    const tok = (typeof getToken === 'function') ? getToken()
      : (localStorage.getItem('token') || sessionStorage.getItem('token') || '');
    const suffix = tok ? tok.slice(-14) : '';
    return suffix ? ('equipped_theme_' + suffix) : 'equipped_theme';
  }

  function _token() {
    return (typeof getToken === 'function') ? getToken()
      : (localStorage.getItem('token') || sessionStorage.getItem('token'));
  }

  // إعدادات الجسيمات المتحرّكة لكل ثيم (شكل + سلوك يشبه ألعاب الشركات الكبيرة)
  const THEME_FX = {
    theme_ocean:   { emoji: ['🫧', '🐟', '🌊'], count: 16, dir: 'up',   speed: [10, 20], size: [14, 30] },
    theme_forest:  { emoji: ['🍃', '🌿', '🍂'], count: 14, dir: 'fall', speed: [8, 16],  size: [16, 28], sway: true },
    theme_cherry:  { emoji: ['🌸', '🌸', '💮'], count: 18, dir: 'fall', speed: [9, 18],  size: [14, 26], sway: true },
    theme_sunset:  { emoji: ['✨', '🌅', '🔆'], count: 12, dir: 'up',   speed: [12, 22], size: [12, 22] },
    theme_cyber:   { emoji: ['⬡', '◈', '▱', '01'], count: 18, dir: 'fall', speed: [6, 12], size: [14, 24], glow: '#00e5ff' },
    theme_lava:    { emoji: ['🔥', '✦', '🌋'], count: 16, dir: 'up',   speed: [7, 15],  size: [14, 28], glow: '#ff5722' },
    theme_galaxy:  { emoji: ['⭐', '✦', '🌟', '✧'], count: 22, dir: 'drift', speed: [14, 26], size: [10, 22], glow: '#ab47bc' },
    theme_aurora:  { emoji: ['❄️', '✦', '❅'], count: 20, dir: 'fall', speed: [10, 20], size: [12, 24], sway: true, glow: '#64ffda' },
    theme_gold:    { emoji: ['✨', '⭐', '💫'], count: 16, dir: 'drift', speed: [12, 22], size: [12, 24], glow: '#ffd700' },
    theme_diamond: { emoji: ['💎', '✦', '✧', '◇'], count: 20, dir: 'drift', speed: [13, 24], size: [12, 26], glow: '#b3e5fc' },
  };

  let _fxContainer = null;

  function _clearFx() {
    if (_fxContainer) { _fxContainer.remove(); _fxContainer = null; }
  }

  function _spawnFx(themeId) {
    _clearFx();
    const fx = THEME_FX[themeId];
    if (!fx) return;

    _fxContainer = document.createElement('div');
    _fxContainer.id = 'themeFxLayer';
    Object.assign(_fxContainer.style, {
      position: 'fixed', inset: '0', pointerEvents: 'none',
      zIndex: '0', overflow: 'hidden',
    });
    document.body.appendChild(_fxContainer);

    const rand = (min, max) => Math.random() * (max - min) + min;

    for (let i = 0; i < fx.count; i++) {
      const el = document.createElement('span');
      el.textContent = fx.emoji[Math.floor(Math.random() * fx.emoji.length)];
      const size = rand(fx.size[0], fx.size[1]);
      const dur = rand(fx.speed[0], fx.speed[1]);
      const delay = rand(0, dur);
      const left = rand(0, 100);

      Object.assign(el.style, {
        position: 'absolute',
        left: `${left}%`,
        fontSize: `${size}px`,
        opacity: String(rand(0.25, 0.7)),
        userSelect: 'none',
        willChange: 'transform',
        animationDuration: `${dur}s`,
        animationDelay: `-${delay}s`,
        animationIterationCount: 'infinite',
        animationTimingFunction: 'linear',
      });
      if (fx.glow) el.style.filter = `drop-shadow(0 0 6px ${fx.glow})`;

      // اتجاه الحركة
      if (fx.dir === 'fall') {
        el.style.top = '-40px';
        el.style.animationName = fx.sway ? 'fxFallSway' : 'fxFall';
      } else if (fx.dir === 'up') {
        el.style.bottom = '-40px';
        el.style.animationName = 'fxRise';
      } else { // drift
        el.style.top = `${rand(0, 100)}%`;
        el.style.animationName = 'fxDrift';
      }
      _fxContainer.appendChild(el);
    }
  }

  // نحقن الأنميشنات (keyframes) مرّة واحدة
  function _injectFxKeyframes() {
    if (document.getElementById('themeFxKeyframes')) return;
    const style = document.createElement('style');
    style.id = 'themeFxKeyframes';
    style.textContent = `
      @keyframes fxFall { 0% { transform: translateY(0) rotate(0); } 100% { transform: translateY(105vh) rotate(360deg); } }
      @keyframes fxFallSway { 0% { transform: translateY(0) translateX(0) rotate(0); } 25% { transform: translateY(26vh) translateX(40px) rotate(90deg); } 50% { transform: translateY(52vh) translateX(-30px) rotate(180deg); } 75% { transform: translateY(78vh) translateX(35px) rotate(270deg); } 100% { transform: translateY(105vh) translateX(0) rotate(360deg); } }
      @keyframes fxRise { 0% { transform: translateY(0) scale(1); opacity: 0.6; } 100% { transform: translateY(-105vh) scale(1.3); opacity: 0; } }
      @keyframes fxDrift { 0% { transform: translate(0,0) scale(0.8); } 25% { transform: translate(40px,-30px) scale(1.1); } 50% { transform: translate(-20px,-50px) scale(0.9); } 75% { transform: translate(30px,-20px) scale(1.05); } 100% { transform: translate(0,0) scale(0.8); } }
    `;
    document.head.appendChild(style);
  }

  window.applyTheme = function (themeId) {
    const root = document.documentElement;
    Object.values(THEMES).forEach(t => Object.keys(t.vars).forEach(k => root.style.removeProperty(k)));
    const theme = THEMES[themeId];
    if (theme) {
      Object.entries(theme.vars).forEach(([k, v]) => root.style.setProperty(k, v));
      root.setAttribute('data-theme', themeId);
      try { localStorage.setItem(_themeKey(), themeId); } catch (_) {}
      _injectFxKeyframes();
      _spawnFx(themeId);
    } else {
      root.removeAttribute('data-theme');
      try { localStorage.removeItem(_themeKey()); } catch (_) {}
      _clearFx();
    }
  };

  // تطبيق الثيم المحفوظ فوراً
  try { const s = localStorage.getItem(_themeKey()); if (s) window.applyTheme(s); } catch (_) {}

  // ===== شبكة اختيار الثيم في الإعدادات =====
  let _ownedThemes = [];
  let _equippedTheme = null;

  function renderThemeGrid() {
    const grid = document.getElementById('themeGrid');
    if (!grid) return;
    if (!_ownedThemes.length) {
      grid.innerHTML = '<div style="color:#888;grid-column:1/-1;text-align:center;padding:20px;">لا تملك ثيمات بعد. اشترِ من المتجر.</div>';
      return;
    }
    grid.innerHTML = '';
    // خيار "الافتراضي" (إلغاء الثيم)
    const def = document.createElement('button');
    def.className = 'theme-option' + (!_equippedTheme ? ' active' : '');
    def.innerHTML = `<span style="font-size:28px;">⚪</span><span style="font-size:12px;color:#fff;">الافتراضي</span>`;
    def.addEventListener('click', () => equipTheme(null));
    grid.appendChild(def);

    _ownedThemes.forEach(t => {
      const btn = document.createElement('button');
      btn.className = 'theme-option' + (_equippedTheme === t.id ? ' active' : '');
      const vars = (THEMES[t.id] && THEMES[t.id].vars) || {};
      const c1 = vars['--theme-primary'] || '#555';
      const c2 = vars['--theme-accent'] || '#888';
      btn.innerHTML = `
        <span style="display:block;width:100%;height:36px;border-radius:8px;background:linear-gradient(135deg,${c1},${c2});margin-bottom:6px;"></span>
        <span style="font-size:20px;">${t.icon}</span>
        <span style="font-size:12px;color:#fff;">${t.name}</span>`;
      btn.addEventListener('click', () => equipTheme(t.id));
      grid.appendChild(btn);
    });
  }

  function equipTheme(themeId) {
    if (themeId === null) {
      // إلغاء الثيم (الافتراضي)
      window.applyTheme(null);
      _equippedTheme = null;
      renderThemeGrid();
      if (typeof socket !== 'undefined' && socket) {
        socket.emit('clear_equipped', { token: _token(), slotType: 'theme' });
      }
      return;
    }
    if (typeof socket !== 'undefined' && socket) {
      socket.emit('equip_cosmetic', { token: _token(), itemId: themeId });
    }
    window.applyTheme(themeId);
    _equippedTheme = themeId;
    renderThemeGrid();
  }

  // نجلب الثيمات المملوكة عند فتح تبويب المظهر
  function _requestThemes() {
    if (typeof socket === 'undefined' || !socket) { setTimeout(_requestThemes, 400); return; }
    socket.emit('get_owned_themes', { token: _token() });
  }

  if (typeof socket !== 'undefined' || true) {
    document.addEventListener('click', (e) => {
      const tab = e.target.closest('[data-tab="themeTab"]');
      if (tab) setTimeout(_requestThemes, 100);
    });
  }

  // مستمعو الخادم
  function _bind() {
    if (typeof socket === 'undefined' || !socket) { setTimeout(_bind, 300); return; }
    socket.on('owned_themes_data', (data) => {
      if (!data) return;
      _ownedThemes = (data.themes || []).map(t => ({
        id: t.id, name: (THEMES[t.id] && THEMES[t.id].name) || t.name, icon: (THEMES[t.id] && THEMES[t.id].icon) || t.icon,
      }));
      _equippedTheme = data.equipped || null;
      if (_equippedTheme) window.applyTheme(_equippedTheme);
      renderThemeGrid();
    });
    socket.on('equipped_data', (data) => {
      if (data && data.equipped && data.equipped.theme) {
        _equippedTheme = data.equipped.theme;
        window.applyTheme(_equippedTheme);
      }
    });
    // عند شراء ثيم → نحدّث القائمة فوراً (بلا تحديث صفحة)
    socket.on('purchase_result', (data) => {
      if (data && data.ok && data.category === 'theme') {
        setTimeout(_requestThemes, 200);
      }
    });
    socket.on('connect', () => {
      setTimeout(() => socket.emit('get_equipped', { token: _token() }), 600);
    });
  }
  _bind();
})();
