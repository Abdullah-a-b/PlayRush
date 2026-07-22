/**
 * 🔊 PlayRush Sound — نظام الصوت المركزي للمنصة
 *
 * - مؤثرات مولّدة برمجياً بـWebAudio (صفر ملفات خارجية = صفر حقوق ملكية).
 * - يستمع تلقائياً لأحداث الألعاب الخمس عبر window.socket (لا تعديل بألعاب).
 * - زر كتم عائم 🔊/🔇 + حفظ التفضيل في localStorage.
 * - يبدأ بعد أول تفاعل مستخدم (سياسة المتصفحات autoplay).
 */
(function () {
    const PREF_KEY = 'pr_sound_muted';
    let muted = false;
    try { muted = localStorage.getItem(PREF_KEY) === '1'; } catch (e) {}
    let ctx = null;

    function ac() {
        if (!ctx) {
            try { ctx = new (window.AudioContext || window.webkitAudioContext)(); }
            catch (e) { return null; }
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }

    function _sfxVol() {
        // 🎚️ سلايدر المؤثرات بالإعدادات (0-100) — حي
        try { const v = localStorage.getItem('sfxSlider'); return v === null ? 1 : (parseInt(v, 10) / 100); }
        catch (e) { return 1; }
    }

    function _notifVol() {
        // 🔔 سلايدر صوت الإشعارات (0-100) — مستقل عن المؤثرات
        try { const v = localStorage.getItem('notifSlider'); return v === null ? 0.8 : (parseInt(v, 10) / 100); }
        catch (e) { return 0.8; }
    }

    /** نغمة واحدة: تردد/مدة/نوع موجة/حجم مع غلاف هبوط ناعم */
    function tone(freq, dur, type, vol, when) {
        const a = ac(); if (!a || muted) return;
        vol = (vol || 0.18) * _sfxVol();
        if (vol <= 0.0005) return;
        const t0 = a.currentTime + (when || 0);
        const osc = a.createOscillator();
        const g = a.createGain();
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, t0);
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.exponentialRampToValueAtTime(vol || 0.18, t0 + 0.015);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(g); g.connect(a.destination);
        osc.start(t0); osc.stop(t0 + dur + 0.05);
    }

    /** ضجيج قصير (خطأ/تصفيق خشن) */
    function noise(dur, vol, when) {
        const a = ac(); if (!a || muted) return;
        vol = (vol || 0.12) * _sfxVol();
        if (vol <= 0.0005) return;
        const t0 = a.currentTime + (when || 0);
        const len = Math.floor(a.sampleRate * dur);
        const buf = a.createBuffer(1, len, a.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
        const src = a.createBufferSource(); src.buffer = buf;
        const g = a.createGain(); g.gain.value = vol || 0.12;
        src.connect(g); g.connect(a.destination); src.start(t0);
    }

    /* ===== المؤثرات المسماة ===== */
    const FX = {
        click:    () => tone(660, 0.06, 'sine', 0.10),
        correct:  () => { tone(523, 0.10, 'sine', 0.16); tone(784, 0.16, 'sine', 0.16, 0.09); },
        wrong:    () => { tone(196, 0.22, 'sawtooth', 0.10); noise(0.12, 0.05); },
        buzz:     () => { tone(880, 0.09, 'square', 0.12); tone(880, 0.09, 'square', 0.12, 0.12); },
        bank:     () => { tone(587, 0.09, 'triangle', 0.15); tone(880, 0.09, 'triangle', 0.15, 0.08); tone(1175, 0.18, 'triangle', 0.15, 0.16); },
        tick:     () => tone(1000, 0.045, 'sine', 0.07),
        countGo:  () => tone(1320, 0.25, 'sine', 0.18),
        win:      () => { [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.22, 'triangle', 0.16, i * 0.13)); },
        lose:     () => { [392, 330, 262].forEach((f, i) => tone(f, 0.26, 'sine', 0.13, i * 0.16)); },
        msg:      () => tone(1175, 0.07, 'sine', 0.09),
        emoji:    () => { tone(988, 0.06, 'sine', 0.10); tone(1319, 0.09, 'sine', 0.10, 0.06); },
        turn:     () => { tone(740, 0.08, 'sine', 0.12); tone(988, 0.12, 'sine', 0.12, 0.09); },
        helpUse:  () => { tone(880, 0.07, 'triangle', 0.12); tone(1109, 0.10, 'triangle', 0.12, 0.07); },
        coin:     () => { tone(1568, 0.06, 'square', 0.08); tone(2093, 0.10, 'square', 0.08, 0.05); },
        disconnect: () => tone(311, 0.30, 'sine', 0.10),
        reconnect:  () => { tone(494, 0.10, 'sine', 0.12); tone(740, 0.14, 'sine', 0.12, 0.09); },
        // 🔔 أصوات الإشعارات — تستخدم _notifVol() وتنتظر Context جاهز
        notif:     () => { _playNotifNotes([[880, 0.10, 'sine', 0.13], [1175, 0.16, 'sine', 0.11, 0.08]]); },
        friendReq: () => { _playNotifNotes([[659, 0.09, 'triangle', 0.14], [880, 0.09, 'triangle', 0.12, 0.09], [1109, 0.18, 'triangle', 0.10, 0.18]]); },
    };

    /**
     * يُشغّل نغمات الإشعار بعد التأكد من أن AudioContext في حالة running.
     * يحل مشكلة autoplay policy: لو كان suspended يستعد قبل الجدولة.
     */
    function _playNotifNotes(notes) {
        if (muted) return;
        const v = _notifVol(); if (v <= 0.0005) return;
        const a = ac(); if (!a) return;
        const _schedule = () => {
            const t0 = a.currentTime;
            notes.forEach(([f, d, tp, vol, w]) => {
                const osc = a.createOscillator(), g = a.createGain();
                osc.type = tp; osc.frequency.setValueAtTime(f, t0 + (w || 0));
                g.gain.setValueAtTime(0.0001, t0 + (w || 0));
                g.gain.exponentialRampToValueAtTime(vol * v, t0 + (w || 0) + 0.015);
                g.gain.exponentialRampToValueAtTime(0.0001, t0 + (w || 0) + d);
                osc.connect(g); g.connect(a.destination);
                osc.start(t0 + (w || 0)); osc.stop(t0 + (w || 0) + d + 0.05);
            });
        };
        if (a.state === 'running') {
            _schedule();
        } else {
            // suspended → ننتظر resume (يحدث تلقائياً بعد أول تفاعل مستخدم)
            a.resume().then(_schedule).catch(() => {});
        }
    }

    /* استئناف مبكر: أي تفاعل بالصفحة يُجهّز الـ Context مسبقاً قبل وصول الإشعار */
    function _earlyResume() { if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {}); }
    document.addEventListener('pointerdown', _earlyResume, { passive: true });
    document.addEventListener('keydown',     _earlyResume, { passive: true });
    /* ===== مزامنة سلايدرات الصوت مع زر الكتم ===== */
    let _syncingSliders = false;   // منع الحلقة اللانهائية عند تحديث DOM

    function _applySlidersToDOM(sfxVal, musicVal, notifVal) {
        if (_syncingSliders) return;
        _syncingSliders = true;
        const sfxEl   = document.getElementById('sfxSlider');
        const musicEl = document.getElementById('musicSlider');
        const notifEl = document.getElementById('notifSlider');
        if (sfxEl)   { sfxEl.value   = sfxVal;              sfxEl.dispatchEvent(new Event('input'));   }
        if (musicEl) { musicEl.value = musicVal;             musicEl.dispatchEvent(new Event('input')); }
        if (notifEl && notifVal !== undefined) {
            notifEl.value = notifVal;
            notifEl.dispatchEvent(new Event('input'));
        }
        _syncingSliders = false;
    }

    window.PRSound = {
        play: (name) => { try { (FX[name] || (() => {}))(); } catch (e) {} },
        playNotif:     () => { try { FX.notif(); }     catch(e) {} },
        playFriendReq: () => { try { FX.friendReq(); } catch(e) {} },
        setMuted: (m, fromSlider) => {
            const wasMuted = muted;
            muted = !!m;
            try { localStorage.setItem(PREF_KEY, m ? '1' : '0'); } catch (e) {}

            if (m && !wasMuted) {
                // كتم ← احفظ القيم الثلاثة ثم اجعل كل السلايدرات 0
                try {
                    const sfx   = parseInt(localStorage.getItem('sfxSlider')    || '100');
                    const music = parseInt(localStorage.getItem('musicSlider')   || '100');
                    const notif = parseInt(localStorage.getItem('notifSlider')   || '80');
                    if (sfx   > 0) localStorage.setItem('_prev_sfxSlider',   String(sfx));
                    if (music > 0) localStorage.setItem('_prev_musicSlider',  String(music));
                    if (notif > 0) localStorage.setItem('_prev_notifSlider',  String(notif));
                    localStorage.setItem('sfxSlider',   '0');
                    localStorage.setItem('musicSlider', '0');
                    localStorage.setItem('notifSlider', '0');
                } catch (e) {}
                _applySlidersToDOM(0, 0, 0);
            } else if (!m && wasMuted && !fromSlider) {
                // رفع الكتم بالزر العائم ← استعد القيم الثلاثة السابقة
                try {
                    const sfx   = parseInt(localStorage.getItem('_prev_sfxSlider')   || '100');
                    const music = parseInt(localStorage.getItem('_prev_musicSlider')  || '100');
                    const notif = parseInt(localStorage.getItem('_prev_notifSlider')  || '80');
                    localStorage.setItem('sfxSlider',   String(sfx));
                    localStorage.setItem('musicSlider', String(music));
                    localStorage.setItem('notifSlider', String(notif));
                    _applySlidersToDOM(sfx, music, notif);
                } catch (e) {}
            }
            _updBtn();
        },
        isMuted:       () => muted,
        isSyncingSliders: () => _syncingSliders,
    };

    /* ===== خريطة أحداث السوكيت → مؤثرات (الألعاب الخمس) ===== */
    const RESULT_KEYS = ['correct', 'accepted', 'ok', 'isCorrect'];
    function resultSound(d) {
        const v = RESULT_KEYS.map(k => d && d[k]).find(x => typeof x === 'boolean');
        FX[v === false ? 'wrong' : v === true ? 'correct' : 'click']();
    }
    const MAP = {
        // نتائج الإجابات
        huroof_answer_result: resultSound,
        career_answer_result: resultSound,
        bank_answer_result: resultSound,
        knowledge_answer_result: resultSound,
        whoami_answer_result: resultSound,
        // الجرس
        huroof_buzzed: () => FX.buzz(), career_buzzed: () => FX.buzz(),
        whoami_buzzed: () => FX.buzz(),
        // البنك
        bank_banked: () => FX.bank(), bank_decision: () => FX.turn(),
        // الأدوار والبدء
        huroof_turn_changed: () => FX.turn(),
        knowledge_turn: () => FX.turn(),
        career_new_player: () => FX.turn(),
        whoami_new_character: () => FX.turn(),
        bank_round_start: () => FX.turn(),
        // النهايات (فوز/خسارة تُحدد بالواجهة — نلتقطها عموميّاً بالفوز)
        game_over: (d) => FX[(d && d.winner_sid && window.socket && d.winner_sid === window.socket.id) ? 'win' : 'lose'](),
        bank_match_over: () => {},   // تفاصيلها بالاسم — يلتقطها win/lose أدناه
        // الرسائل والإيموجي
        quick_chat_message: () => FX.msg(),
        huroof_emoji: () => FX.emoji(), career_emoji: () => FX.emoji(),
        bank_emoji: () => FX.emoji(), whoami_emoji: () => FX.emoji(),
        // المساعدات
        huroof_help_result: () => FX.helpUse(), career_help_result: () => FX.helpUse(),
        bank_help_result: () => FX.helpUse(), knowledge_help_result: () => FX.helpUse(),
        whoami_help_result: () => FX.helpUse(),
        // الاتصال
        opponent_disconnected: () => FX.disconnect(),
        opponent_reconnected: () => FX.reconnect(),
    };

    function hook() {
        const s = window.socket;
        if (!s || s.__prSoundHooked) return;
        s.__prSoundHooked = true;
        Object.keys(MAP).forEach((ev) => {
            s.on(ev, (d) => { try { MAP[ev](d); } catch (e) {} });
        });
        // فوز/خسارة عام: أي حدث ينتهي بـ_match_over أو _game_over
        s.onAny && s.onAny((ev, d) => {
            try {
                if (/(_match_over|_game_over)$/.test(ev)) {
                    const meName = (d && d.winnerName && window.playersStatsData)
                        ? window.playersStatsData.me?.name : null;
                    const iWon = d && ((d.winnerName && meName && d.winnerName === meName)
                        || (d.winner && d.winner === s.id));
                    FX[iWon ? 'win' : 'lose']();
                }
            } catch (e) {}
        });
    }
    // نحاول الربط فوراً وبعد التحميل (window.socket قد يتأخر)
    const tryHook = () => { hook(); if (!window.socket) setTimeout(tryHook, 800); };
    document.addEventListener('DOMContentLoaded', tryHook);
    setTimeout(tryHook, 1500);

    /* ===== أصوات النقر العامة + عدّاد الاستعداد ===== */
    document.addEventListener('click', (e) => {
        // أول تفاعل يوقظ الـAudioContext
        ac();
        const t = e.target.closest('button, .game-card, .hex, .qc-emoji-btn');
        if (t) FX.click();
    }, true);
    // عدّاد استعد 3-2-1 (يلتقط تغيّر readyCount)
    const watchReady = () => {
        const el = document.getElementById('readyCount');
        if (!el) return;
        new MutationObserver(() => {
            const v = el.textContent.trim();
            if (v === '1') { FX.tick(); setTimeout(() => FX.countGo(), 950); }
            else FX.tick();
        }).observe(el, { childList: true, characterData: true, subtree: true });
    };
    document.addEventListener('DOMContentLoaded', watchReady);

    /* ===== إخفاء زر الكتم العائم عند ظهور الشاشات الكاملة ===== */
    //  الشاشات التي يجب أن يختفي عندها الزر (استسلام/فوز/خسارة/انتظار/بروفايل/تحذير/عدّاد البدء)
    function _setupFloatAutoHide(button) {
        const SELECTORS = [
            '.win-message-overlay',    // فوز/خسارة/استسلام/إبلاغ (كل الألعاب)
            '#winner-overlay',
            '#waiting-overlay',
            '.cheat-modal',
            '.profile-modal-overlay',
            '#sharedProfileModal',
            '.ready-overlay'           // عدّاد 3-2-1
        ];
        function _visible(el) {
            if (!el) return false;
            const cs = getComputedStyle(el);
            return cs.display !== 'none'
                && cs.visibility !== 'hidden'
                && parseFloat(cs.opacity || '1') > 0.05;
        }
        function _anyOverlay() {
            for (const sel of SELECTORS) {
                const list = document.querySelectorAll(sel);
                for (let i = 0; i < list.length; i++) {
                    if (_visible(list[i])) return true;
                }
            }
            // شاشة كشف التطابق (تُفعَّل عبر كلاس show مع بقاء display)
            const mr = document.getElementById('matchRevealOverlay');
            if (mr && mr.classList.contains('show')) return true;
            return false;
        }
        function _sync() {
            button.style.visibility = _anyOverlay() ? 'hidden' : 'visible';
        }
        _sync();
        try {
            const mo = new MutationObserver(_sync);
            mo.observe(document.body, {
                attributes: true,
                attributeFilter: ['style', 'class'],
                subtree: true,
                childList: true
            });
        } catch (e) {}
        //  احتياط إضافي: أعد الفحص بعد أي نقرة (فتح/غلق المودالات)
        document.addEventListener('click', () => setTimeout(_sync, 60), true);
    }

    /* ===== زر الكتم العائم ===== */
    let btn = null;
    function _updBtn() { if (btn) btn.textContent = muted ? '🔇' : '🔊'; }
    function mountBtn() {
        if (document.getElementById('prSoundBtn')) return;
        btn = document.createElement('button');
        btn.id = 'prSoundBtn';
        btn.title = 'الصوت';

        const IS_MOBILE = window.innerWidth <= 640;
        const IS_GAME   = /\/games\//.test(window.location.pathname);

        const clickHandler = (e) => {
            e.stopPropagation();
            window.PRSound.setMuted(!muted);
            if (!muted) FX.click();
        };

        //  داخل الألعاب: زر عائم دائماً (جوال + ديسكتوب) بطبقة عالية جداً
        //  حتى يبقى ظاهراً فوق شاشات الفوز/الخسارة/الاستسلام.
        //  الأنماط المضمّنة تضمن ظهوره في كل الألعاب؛ وحروف تعدّل موضعه عبر CSS.
        if (IS_GAME) {
            btn.className = 'pr-sound-float';
            btn.style.cssText = 'position:fixed;bottom:20px;left:18px;z-index:99999;'
                + 'width:44px;height:44px;border-radius:50%;border:1px solid rgba(255,255,255,.18);'
                + 'background:rgba(22,27,34,.92);color:#fff;font-size:1.15rem;line-height:1;'
                + 'display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:.85;'
                + 'box-shadow:0 4px 14px rgba(0,0,0,.4);-webkit-tap-highlight-color:transparent;';
            btn.addEventListener('click', clickHandler);
            _updBtn();
            document.body.appendChild(btn);
            //  نخفي الزر تلقائياً عند ظهور شاشات كاملة (استسلام/فوز/خسارة/انتظار/بروفايل…)
            _setupFloatAutoHide(btn);
            return;
        }

        if (IS_MOBILE) {
            // جوال (خارج الألعاب): يدخل داخل الشريط الموحّد (slot من brand.js)
            btn.style.cssText = 'background:none;border:none;font-size:1.1rem;'
                + 'cursor:pointer;opacity:0.85;padding:0;line-height:1;color:#fff;';
            btn.addEventListener('click', clickHandler);
            _updBtn();
            // انتظر الـ slot من brand.js
            function trySlot(n) {
                const slot = document.getElementById('prSoundSlot');
                if (slot) { slot.appendChild(btn); }
                else if (n > 0) { setTimeout(() => trySlot(n - 1), 80); }
            }
            trySlot(15);
        } else {
            // ديسكتوب (خارج الألعاب): الزر العائم المستقل
            btn.style.cssText = 'position:fixed;bottom:20px;left:18px;z-index:5000;'
                + 'width:42px;height:42px;border-radius:50%;border:1px solid rgba(255,255,255,.18);'
                + 'background:rgba(22,27,34,.9);font-size:1.15rem;cursor:pointer;opacity:.75;';
            btn.addEventListener('click', clickHandler);
            _updBtn();
            document.body.appendChild(btn);
        }
    }
    document.addEventListener('DOMContentLoaded', mountBtn);
})();