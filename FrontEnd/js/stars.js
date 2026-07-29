/* ══════════════════════════════════════════════════════════════════════
   PRStars — توليد النجوم بتوزيع شبكي مُذبذَب
   ----------------------------------------------------------------------
   لماذا وُجد هذا الملف: كل صفحة كانت تُنشئ 150 نجمة بمواضع عشوائية بحتة،
   وكل نجمة تحمل هالتين ضبابيتين (20px و 40px) وتومض بلا توقف. النتيجة
   قياساً على DevTools: ذاكرة GPU ممتلئة (130/131 MB) و 9 إطارات/ثانية،
   وعلى الجوال تنفد الذاكرة فتظهر مناطق فارغة وممزّقة.

   العدد وحده ليس الحل: العشوائية البحتة تُكدّس النجوم في مواضع وتترك
   فجوات، فيبدو التقليل أفحش مما هو. لذلك نوزّعها على شبكة ونُزيح كل نجمة
   داخل خليتها عشوائياً — تغطية منتظمة بإحساس طبيعي، فيكفي عدد أقل بكثير.
   ══════════════════════════════════════════════════════════════════════ */
(function () {
    function isApp() {
        return window.PR_IS_APP === true
            || (typeof window.Capacitor !== 'undefined')
            || /^(capacitor|file|ionic):$/.test(window.location.protocol);
    }

    window.PRStars = {
        render: function (container, opts) {
            if (typeof container === 'string') container = document.getElementById(container);
            if (!container) return;
            opts = opts || {};

            // الجوال/التطبيق أثقل حملاً ومساحته أصغر، فيكفيه عدد أقل
            var light = isApp() || window.innerWidth <= 900;
            var count = opts.count || (light ? 70 : 110);

            // شبكة أقرب ما تكون للمربّعة تُغطّي الشاشة بالتساوي
            var cols = Math.max(4, Math.round(Math.sqrt(count * (window.innerWidth / Math.max(window.innerHeight, 1)))));
            var rows = Math.max(4, Math.ceil(count / cols));

            var frag = document.createDocumentFragment();
            var purple = opts.purple !== false;

            for (var r = 0; r < rows; r++) {
                for (var c = 0; c < cols; c++) {
                    var star = document.createElement('div');
                    star.className = 'star' + (purple && Math.random() > 0.3 ? ' purple' : '');

                    // موضع الخلية + إزاحة عشوائية داخلها (jitter)
                    var x = ((c + 0.15 + Math.random() * 0.7) / cols) * 100;
                    var y = ((r + 0.15 + Math.random() * 0.7) / rows) * 100;

                    // مدد ومهل متفاوتة كي لا تومض كلها معاً
                    var dur   = (2.6 + Math.random() * 2.2).toFixed(2);
                    var delay = (Math.random() * 3).toFixed(2);

                    star.style.cssText = 'left:' + x.toFixed(2) + '%;top:' + y.toFixed(2)
                        + '%;animation-duration:' + dur + 's;animation-delay:' + delay + 's;';
                    frag.appendChild(star);
                }
            }
            container.innerHTML = '';
            container.appendChild(frag);
        }
    };
})();
