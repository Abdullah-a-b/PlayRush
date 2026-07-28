/**
 *  نظام الرسائل الجاهزة (Quick Chat) — واجهة مشتركة.
 *
 * بديل آمن للدردشة الحرة: المستخدم يختار عبارة معتمدة من قائمة أزرار،
 * فيُرسَل معرّفها (id) فقط للخادم — لا يُكتب نص حر أبداً.
 *
 * الاستخدام:
 * QuickChat.init({
 * socket, // اتصال socket.io
 * triggerBtn: domElement, // الزر الذي يفتح لوحة العبارات
 * event: 'send_chat_message', // أو 'send_game_chat_message'
 * extra: () => ({ gameMode }) // (اختياري) بيانات إضافية لكل رسالة
 * });
 *
 * الخادم يرسل القائمة عبر 'quick_chat_catalog' بعد طلبها بـ 'get_quick_chat_catalog'.
 */
const QuickChat = (function () {
  let _catalog = null;
  let _socket = null;
  const _instances = [];

  // مسار ملف Lottie للإيموجي (يكتشف عمق الصفحة)
  function _emojiPath(emojiId) {
    const inGames = window.location.pathname.includes('/games/');
    return `${inGames ? '../' : ''}assets/emojis/${emojiId}.json`;
  }

  // تحميل Lottie في حاوية — يعيد المحاولة لو المكتبة لم تجهز بعد
  function _loadEmojiInto(holder, emojiId, fallbackText, tries) {
    tries = tries || 0;
    if (typeof window.lottie !== 'undefined' && window.lottie.loadAnimation) {
      try {
        window.lottie.loadAnimation({
          container: holder, renderer: 'svg', loop: true, autoplay: true,
          path: _emojiPath(emojiId),
        });
        return;
      } catch (_) { holder.textContent = fallbackText; return; }
    }
    if (tries < 20) {
      setTimeout(() => _loadEmojiInto(holder, emojiId, fallbackText, tries + 1), 250);
    } else {
      holder.textContent = fallbackText;  // تعذّر تحميل Lottie → نص احتياطي
    }
  }

  function _buildPanel(instance) {
    const panel = document.createElement('div');
    panel.className = 'quick-chat-panel';
    panel.style.display = 'none';

    if (!_catalog) {
      panel.innerHTML = '<div class="qc-loading">جارٍ التحميل…</div>';
      return panel;
    }

    Object.entries(_catalog).forEach(([category, phrases]) => {
      const catTitle = document.createElement('div');
      catTitle.className = 'qc-category';
      catTitle.textContent = category;
      panel.appendChild(catTitle);

      const grid = document.createElement('div');
      grid.className = 'qc-grid';
      phrases.forEach((ph) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'qc-phrase';
        // عبارة إيموجي (لها emojiId) → نعرض Lottie متحرك (مع إعادة محاولة لو المكتبة لم تجهز)
        if (ph.emojiId) {
          btn.classList.add('qc-emoji-phrase');
          const holder = document.createElement('div');
          holder.style.width = '40px';
          holder.style.height = '40px';
          holder.style.margin = '0 auto';
          holder.style.fontSize = '28px';
          btn.appendChild(holder);
          _loadEmojiInto(holder, ph.emojiId, ph.text);
        } else {
          btn.textContent = ph.text;
        }
        btn.addEventListener('click', () => {
          const payload = Object.assign({ phraseId: ph.id }, instance.extra ? instance.extra() : {});
          _socket.emit(instance.event, payload);
          panel.style.display = 'none';  // نغلق بعد الإرسال
        });
        grid.appendChild(btn);
      });
      panel.appendChild(grid);
    });
    return panel;
  }

  function _refreshPanels() {
    // نُعيد بناء كل اللوحات بعد وصول القائمة من الخادم
    _instances.forEach((inst) => {
      if (inst.panel && inst.panel.parentNode) {
        const wasOpen = inst.panel.style.display === 'block';
        const fresh = _buildPanel(inst);
        fresh.style.display = wasOpen ? 'block' : 'none';
        inst.panel.parentNode.replaceChild(fresh, inst.panel);
        inst.panel = fresh;
      }
    });
  }

  function init(opts) {
    const { socket, triggerBtn, event, extra, context, game } = opts;
    if (!socket || !triggerBtn || !event) return;
    _socket = socket;
    const ctx = context || 'lobby';

    // نسجّل مستمع القائمة مرة واحدة فقط على مستوى الـ socket
    if (!socket._qcListenerAttached) {
      socket._qcListenerAttached = true;
      socket.on('quick_chat_catalog', (catalog) => {
        _catalog = catalog;
        _refreshPanels();
      });
      // نطلب القائمة الآن، ومجدداً عند كل إعادة اتصال (احتياطاً للتوقيت)
      const requestCatalog = () => socket.emit('get_quick_chat_catalog', { context: ctx, game: game });
      requestCatalog();
      socket.on('connect', requestCatalog);
      // عند شراء عبارة → نحدّث القائمة فوراً
      socket.on('purchase_result', (d) => {
        if (d && d.ok && (d.category === 'chat_phrase' || d.category === 'emoji')) setTimeout(requestCatalog, 200);
      });
    } else if (!_catalog) {
      // init ثانٍ قبل وصول القائمة → اطلبها ثانية
      socket.emit('get_quick_chat_catalog', { context: ctx, game: game });
    }

    const instance = { triggerBtn, event, extra, panel: null };
    const panel = _buildPanel(instance);
    instance.panel = panel;

    // نضع اللوحة بجانب الزر — لكن لا نكسر موضع الحاوية لو كانت مثبّتة مسبقاً (fixed)
    const parentPos = window.getComputedStyle(triggerBtn.parentNode).position;
    if (parentPos === 'static') {
      triggerBtn.parentNode.style.position = 'relative';
    }
    triggerBtn.parentNode.appendChild(panel);

    triggerBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      const cur = instance.panel;  // نقرأ اللوحة الحالية (قد تكون أُعيد بناؤها)
      const showing = cur.style.display !== 'none';
      // نغلق كل اللوحات الأخرى
      _instances.forEach((i) => { if (i.panel) i.panel.style.display = 'none'; });
      // لو القائمة لم تصل بعد، نطلبها الآن قبل الفتح
      if (!_catalog && _socket) _socket.emit('get_quick_chat_catalog', { context: ctx, game: game });
      cur.style.display = showing ? 'none' : 'block';
    });

    // إغلاق عند النقر خارج اللوحة
    document.addEventListener('click', (e) => {
      const cur = instance.panel;
      if (!cur.contains(e.target) && e.target !== triggerBtn && !triggerBtn.contains(e.target)) {
        cur.style.display = 'none';
      }
    });

    _instances.push(instance);
    return instance;
  }

  return { init };
})();

if (typeof window !== 'undefined') window.QuickChat = QuickChat;
