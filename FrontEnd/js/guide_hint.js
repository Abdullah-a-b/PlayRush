/* ============================================================
   PlayRush — إرشاد المستخدم الجديد إلى «كيف ألعب؟»
   يظهر مرة واحدة فقط لكل جهاز، ويختفي فور فتح الدليل.
   ============================================================ */
(function () {
    var SEEN_KEY = 'pr_guide_seen';

    function seen() {
        try { return localStorage.getItem(SEEN_KEY) === '1'; } catch (e) { return true; }
    }
    function markSeen() {
        try { localStorage.setItem(SEEN_KEY, '1'); } catch (e) {}
        var btn = document.getElementById('guideNavBtn');
        if (btn) btn.classList.remove('pr-hint-pulse');
        var tip = document.getElementById('prGuideTip');
        if (tip && tip.parentNode) tip.parentNode.removeChild(tip);
    }

    function showTip(btn) {
        var tip = document.createElement('div');
        tip.id = 'prGuideTip';
        tip.className = 'pr-guide-tip';
        tip.innerHTML =
            '<div>👋 جديد في PlayRush؟<br>اضغط <b>«كيف ألعب؟»</b> لتعرف شرح كل لعبة وطريقة اللعب مع أصدقائك.</div>' +
            '<button type="button">فهمت</button>';
        document.body.appendChild(tip);

        // نضعها أسفل الزر مباشرة
        var r = btn.getBoundingClientRect();
        var top = r.bottom + 10;
        var right = Math.max(10, window.innerWidth - r.right);
        tip.style.top = top + 'px';
        tip.style.right = right + 'px';

        tip.querySelector('button').addEventListener('click', markSeen);
        setTimeout(function () {
            var t = document.getElementById('prGuideTip');
            if (t && t.parentNode) t.parentNode.removeChild(t);
        }, 12000);
    }

    function init() {
        var btn = document.getElementById('guideNavBtn');
        if (!btn) return;

        // فتح الدليل بأي وسيلة = المستخدم يعرف مكانه
        btn.addEventListener('click', markSeen);

        if (seen()) return;
        btn.classList.add('pr-hint-pulse');
        setTimeout(function () { showTip(btn); }, 1200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
