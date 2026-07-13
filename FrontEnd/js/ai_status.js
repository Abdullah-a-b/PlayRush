// ============================================================
// ai_status.js — مؤشّر جاهزية الـAI (Gemini) في الواجهة.
// يستعلم /ai-status ويعرض شارة صغيرة: جاهز / معطّل / خطأ.
// يظهر فقط لو العنصر #aiStatusBadge موجود في الصفحة.
// ============================================================

(function () {
    async function checkAI() {
        var badge = document.getElementById('aiStatusBadge');
        if (!badge) return;
        var base = (typeof CONFIG !== 'undefined' && CONFIG.API_URL)
            ? CONFIG.API_URL : '';
        badge.className = 'ai-badge checking';
        badge.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> فحص الذكاء الاصطناعي…';
        try {
            var res = await fetch(base + '/ai-status');
            var d = await res.json();
            if (d.status === 'ready') {
                badge.className = 'ai-badge ready';
                badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> الذكاء الاصطناعي جاهز'
                    + (d.model ? ' <span class="ai-model">(' + d.model + ')</span>' : '');
            } else if (d.status === 'disabled') {
                badge.className = 'ai-badge disabled';
                badge.innerHTML = '<i class="fa-solid fa-circle-minus"></i> الذكاء الاصطناعي معطّل '
                    + '<span class="ai-hint">(التحكيم متساهل)</span>';
            } else {
                badge.className = 'ai-badge error';
                badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> مشكلة في الذكاء الاصطناعي';
            }
            badge.title = d.detail || '';
        } catch (e) {
            badge.className = 'ai-badge error';
            badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> تعذّر فحص الذكاء الاصطناعي';
            badge.title = String(e);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkAI);
    } else {
        checkAI();
    }
    window.recheckAIStatus = checkAI;
})();
