// ============================================================
// brand.js — حقن شريط هوية الشركة في كل صفحة تلقائياً
// يجب إضافة <link rel="stylesheet" href="css/brand.css"> و <script src="js/brand.js" defer> في كل صفحة
// (في صفحات داخل /games/ المسارات تكون "../css/brand.css" و "../js/brand.js")
// ============================================================

(function() {
    // نتأكد إن الـ footer ما اتضاف مرتين
    if (document.querySelector('.brand-footer')) return;

    function injectBrandFooter() {
        const footer = document.createElement('div');
        footer.className = 'brand-footer';

        const bySpan = document.createElement('span');
        bySpan.className = 'brand-by';
        bySpan.textContent = 'Powered by';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'brand-name';
        nameSpan.textContent = 'Isolated Person';

        footer.appendChild(bySpan);
        footer.appendChild(document.createTextNode(' '));
        footer.appendChild(nameSpan);

        document.body.appendChild(footer);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectBrandFooter);
    } else {
        injectBrandFooter();
    }
})();
