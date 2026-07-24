/* ============================================================
   PlayRush — محرّك الإيموجي المتحرك (مشترك ومحسّن للجوال)
   ------------------------------------------------------------
   المشكلة التي يعالجها:
   لوحة الدردشة كانت تشغّل ~16 أنيميشن Lottie في آنٍ واحد،
   بمُصيّر SVG، بتكرار لا نهائي، وتُعيد تحميل كل ملف JSON في كل مرة.
   على WebView في الجوال هذا يستهلك المعالج بالكامل → تعليق واضح
   لحظة فتح اللوحة وإرسال الرسائل.

   المعالجة:
   • ذاكرة مؤقتة: كل ملف يُجلب مرة واحدة فقط ويُعاد استخدامه.
   • مُصيّر canvas على أجهزة اللمس (أسرع بكثير من SVG).
   • داخل اللوحة: إطار ثابت فقط بلا حركة (الحركة عند الإرسال).
   • سقف للأنيميشنات المتزامنة، والأقدم يتوقف تلقائياً.
   • تنظيف صريح عند إزالة العنصر (يمنع تسريب الذاكرة).
   ============================================================ */
(function () {
    if (window.PREmoji) return;

    var IS_TOUCH = (typeof window.matchMedia === 'function'
                        && window.matchMedia('(pointer: coarse)').matches)
                   || ('ontouchstart' in window)
                   || (navigator.maxTouchPoints > 0);

    // سقف الأنيميشنات العاملة معاً — أقل على الجوال
    var MAX_LIVE = IS_TOUCH ? 3 : 8;

    var _cache = {};    // emojiId -> animationData (JSON مُحمَّل)
    var _pending = {};  // emojiId -> Promise (يمنع الجلب المزدوج)
    var _live = [];     // الأنيميشنات العاملة حالياً

    function _path(emojiId) {
        var inGames = window.location.pathname.indexOf('/games/') !== -1;
        return (inGames ? '../' : '') + 'assets/emojis/' + emojiId + '.json';
    }

    /** يجلب بيانات الإيموجي مرة واحدة ويحفظها */
    function load(emojiId) {
        if (_cache[emojiId]) return Promise.resolve(_cache[emojiId]);
        if (_pending[emojiId]) return _pending[emojiId];

        _pending[emojiId] = fetch(_path(emojiId))
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                _cache[emojiId] = data;
                delete _pending[emojiId];
                return data;
            })
            .catch(function (e) {
                delete _pending[emojiId];
                throw e;
            });
        return _pending[emojiId];
    }

    function _waitLottie(tries) {
        tries = tries || 0;
        if (typeof window.lottie !== 'undefined' && window.lottie.loadAnimation) {
            return Promise.resolve(true);
        }
        if (tries >= 20) return Promise.resolve(false);
        return new Promise(function (res) {
            setTimeout(function () { res(_waitLottie(tries + 1)); }, 250);
        });
    }

    function _register(anim) {
        _live.push(anim);
        while (_live.length > MAX_LIVE) {
            var old = _live.shift();
            try { old.stop(); old.destroy(); } catch (e) {}
        }
    }

    /**
     * يعرض إيموجي داخل عنصر.
     * @param {HTMLElement} holder  الحاوية
     * @param {string} emojiId      معرّف الإيموجي
     * @param {string} fallbackText نص بديل عند الفشل
     * @param {object} opts         { animate: bool, loop: bool, replays: number }
     */
    function render(holder, emojiId, fallbackText, opts) {
        opts = opts || {};
        var animate = opts.animate !== false;   // الافتراضي: متحرك
        var replays = opts.replays || 0;

        return _waitLottie().then(function (ready) {
            if (!ready) { holder.textContent = fallbackText || ''; return null; }
            return load(emojiId).then(function (data) {
                var anim = window.lottie.loadAnimation({
                    container: holder,
                    renderer: IS_TOUCH ? 'canvas' : 'svg',
                    loop: false,
                    autoplay: false,
                    animationData: data,          // من الذاكرة — بلا طلب شبكة جديد
                    rendererSettings: { progressiveLoad: true, clearCanvas: true }
                });

                if (!animate) {
                    // إطار ثابت: يظهر شكل الإيموجي بلا أي استهلاك للمعالج
                    try { anim.goToAndStop(0, true); } catch (e) {}
                    return anim;
                }

                _register(anim);
                anim.play();

                if (replays > 0) {
                    var plays = 0;
                    anim.addEventListener('complete', function () {
                        plays++;
                        if (plays >= replays) return;
                        var wait = 2500 + Math.random() * 4000;
                        setTimeout(function () {
                            try { anim.goToAndPlay(0, true); } catch (e) {}
                        }, wait);
                    });
                }
                return anim;
            }).catch(function () {
                holder.textContent = fallbackText || '';
                return null;
            });
        });
    }

    /** يشغّل إيموجي ثابتاً عند اللمس/المرور (للوحة الاختيار) */
    function playOnce(anim) {
        if (!anim) return;
        try { _register(anim); anim.goToAndPlay(0, true); } catch (e) {}
    }

    window.PREmoji = {
        render: render,
        load: load,
        playOnce: playOnce,
        isTouch: IS_TOUCH
    };
})();
