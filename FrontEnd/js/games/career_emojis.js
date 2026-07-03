/* ============================================================
   😄 إيموجيات متحركة (Lottie) — مدمجة مع لوحة الرسائل (QuickChat)
   تُحمّل بعد career.js (socket + roomCode متاحان)
   ============================================================ */
(function () {
  if (typeof window === 'undefined') return;

  const RC = () => (typeof roomCode !== 'undefined' ? roomCode : sessionStorage.getItem('gameRoomCode'));
  const SOCK = () => (typeof socket !== 'undefined' ? socket : null);

  const EMOJI_LIST = [
    { id: 'emoji_laugh', fallback: '😂', name: 'ضحكة' },
    { id: 'emoji_cry',   fallback: '😭', name: 'بكاء' },
    { id: 'emoji_angry', fallback: '😡', name: 'غضب' },
    { id: 'emoji_think', fallback: '🤔', name: 'تفكير' },
    { id: 'emoji_cool',  fallback: '😎', name: 'متباهٍ' },
    { id: 'emoji_fire',  fallback: '🔥', name: 'نار' },
    { id: 'emoji_clap',  fallback: '👏', name: 'تصفيق' },
    { id: 'emoji_crown', fallback: '👑', name: 'ملك' },
    { id: 'emoji_goat',  fallback: '🐐', name: 'الأعظم' },
    { id: 'emoji_shock',     fallback: '😱', name: 'صدمة' },
    { id: 'emoji_mindblown', fallback: '🤯', name: 'انفجار العقل' },
    { id: 'emoji_target',    fallback: '🎯', name: 'إصابة دقيقة' },
    { id: 'emoji_heart',     fallback: '❤️', name: 'حب' },
    { id: 'emoji_devil',     fallback: '😈', name: 'شيطنة' },
    { id: 'emoji_bolt',      fallback: '⚡', name: 'سرعة' },
    { id: 'emoji_trophy',    fallback: '🏆', name: 'بطل' },
  ];
  const EMOJI_MAP = {};
  EMOJI_LIST.forEach(e => { EMOJI_MAP[e.id] = e; });

  let _owned = ['emoji_laugh', 'emoji_cry', 'emoji_angry', 'emoji_think'];

  function _hasLottie() {
    return (typeof window.lottie !== 'undefined' && window.lottie && typeof window.lottie.loadAnimation === 'function');
  }
  function _path(id) { return `../assets/emojis/${id}.json`; }

  function injectEmojiRow() {
    const panel = document.querySelector('.ingame-quick-chat .quick-chat-panel');
    if (!panel) return;
    if (panel.querySelector('.qc-emoji-row')) return;

    const title = document.createElement('div');
    title.className = 'qc-category qc-emoji-title';
    title.textContent = 'الإيموجيات';
    panel.appendChild(title);

    const row = document.createElement('div');
    row.className = 'qc-emoji-row';
    _owned.forEach(id => {
      const e = EMOJI_MAP[id];
      if (!e) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'qc-emoji-btn';
      btn.title = e.name;
      // نعرض Lottie متحرك في الزر (مع نص احتياطي)
      const holder = document.createElement('div');
      holder.style.width = '34px';
      holder.style.height = '34px';
      holder.style.fontSize = '24px';
      holder.textContent = e.fallback;
      btn.appendChild(holder);
      (function tryLoad(tries) {
        if (_hasLottie()) {
          try {
            holder.textContent = '';
            window.lottie.loadAnimation({
              container: holder, renderer: 'svg', loop: true, autoplay: true,
              path: _path(id),
            });
          } catch (_) { holder.textContent = e.fallback; }
        } else if (tries < 20) {
          setTimeout(() => tryLoad(tries + 1), 250);
        }
      })(0);
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        sendEmoji(id);
        panel.style.display = 'none';
      });
      row.appendChild(btn);
    });
    panel.appendChild(row);
  }

  function refreshEmojiRow() {
    const panel = document.querySelector('.ingame-quick-chat .quick-chat-panel');
    if (!panel) return;
    panel.querySelectorAll('.qc-emoji-row, .qc-emoji-title').forEach(el => el.remove());
    injectEmojiRow();
  }

  function sendEmoji(emojiId) {
    const s = SOCK();
    if (!s) return;
    s.emit('career_send_emoji', { roomCode: RC(), emojiId });
  }

  function playEmoji(emojiId, isMine) {
    const e = EMOJI_MAP[emojiId];
    if (!e) return;
    const anchor = isMine
      ? document.getElementById('myProfileBtn')
      : document.getElementById('opponentProfileBtn');

    const bubble = document.createElement('div');
    bubble.className = 'emoji-bubble';

    if (_hasLottie()) {
      const holder = document.createElement('div');
      holder.style.width = '90px';
      holder.style.height = '90px';
      bubble.appendChild(holder);
      try {
        const anim = window.lottie.loadAnimation({
          container: holder, renderer: 'svg', loop: false, autoplay: true,
          path: _path(emojiId),
        });
        anim.addEventListener('data_failed', () => {
          holder.innerHTML = `<span class="emoji-fallback">${e.fallback}</span>`;
        });
        anim.addEventListener('complete', () => {
          setTimeout(() => { try { anim.destroy(); } catch(_){} }, 100);
        });
      } catch (_) {
        holder.innerHTML = `<span class="emoji-fallback">${e.fallback}</span>`;
      }
    } else {
      bubble.innerHTML = `<span class="emoji-fallback">${e.fallback}</span>`;
    }

    bubble.style.position = 'fixed';
    if (anchor) {
      const r = anchor.getBoundingClientRect();
      bubble.style.left = `${r.left + r.width / 2 - 45}px`;
      bubble.style.top = `${r.bottom + 8}px`;
    } else {
      bubble.style.top = '110px';
      bubble.style[isMine ? 'right' : 'left'] = '24px';
    }
    document.body.appendChild(bubble);

    requestAnimationFrame(() => bubble.classList.add('show'));
    setTimeout(() => {
      bubble.classList.remove('show');
      setTimeout(() => bubble.remove(), 300);
    }, 2600);
  }

  function bindSocket() {
    const s = SOCK();
    if (!s) { setTimeout(bindSocket, 300); return; }
    s.on('career_my_emojis', (data) => {
      if (data && Array.isArray(data.owned) && data.owned.length) {
        _owned = data.owned;
        refreshEmojiRow();
      }
    });
    s.on('career_emoji', (data) => {
      if (data && data.emojiId) playEmoji(data.emojiId, !!data.isMine);
    });
    const ask = () => s.emit('career_get_my_emojis', { roomCode: RC() });
    s.on('connect', () => setTimeout(ask, 900));
    setTimeout(ask, 1000);
  }

  bindSocket();
  setInterval(injectEmojiRow, 800);
})();
