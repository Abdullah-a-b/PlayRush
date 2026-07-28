/* ============================================================
   PlayRush — معالجة الكيبورد في خلية الحروف (الجوال)
   ------------------------------------------------------------
   المشكلة: الصندوق السفلي position:fixed bottom:0. حين يظهر
   كيبورد الجوال يطغى عليه أو ينضغط النصّ.

   الحل: نستخدم visualViewport لرفع الصندوق فوق الكيبورد بسلاسة
   حين يُركَّز حقل الإجابة، ونعيده لمكانه عند إغلاق الكيبورد.
   ============================================================ */
(function () {
    var sidebar = null;
    var input = null;
    var vv = window.visualViewport;
    if (!vv) return;   // متصفح قديم — نتركه للسلوك الافتراضي

    function el(id) { return document.getElementById(id); }

    function lift() {
        sidebar = sidebar || el('questionSidebar');
        if (!sidebar) return;
        // مقدار ما يغطّيه الكيبورد من أسفل الشاشة
        var covered = window.innerHeight - (vv.height + vv.offsetTop);
        if (covered > 80) {
            // نرفع الصندوق فوق الكيبورد مع هامش صغير
            sidebar.style.transition = 'transform .2s ease';
            sidebar.style.transform = 'translateY(-' + (covered - 4) + 'px)';
            sidebar.classList.add('kb-lifted');
        } else {
            reset();
        }
    }

    function reset() {
        sidebar = sidebar || el('questionSidebar');
        if (!sidebar) return;
        sidebar.style.transform = '';
        sidebar.classList.remove('kb-lifted');
    }

    function bind() {
        input = el('playerAnswerInput');
        if (!input) return;
        input.addEventListener('focus', function () {
            setTimeout(lift, 100);   // ننتظر ظهور الكيبورد
        });
        input.addEventListener('blur', function () {
            setTimeout(reset, 100);
        });
        // نتابع تغيّر حجم الـviewport (فتح/إغلاق الكيبورد)
        vv.addEventListener('resize', function () {
            if (document.activeElement === input) lift();
            else reset();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind);
    } else {
        bind();
    }
})();
