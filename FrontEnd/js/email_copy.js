// ============================================================
// email_copy.js — يضيف زر "نسخ" بجانب إيميل المنصة في كل صفحة.
// يعمل على أي رابط mailto: أو أي عنصر يحمل data-email.
// النسخ موثوق (clipboard API + fallback)، ويعطي تأكيداً بصرياً.
// ============================================================

(function () {
    var PLATFORM_EMAIL = 'playrush.online@gmail.com';

    function copyText(text) {
        // الطريقة الحديثة
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        // fallback قديم
        return new Promise(function (resolve, reject) {
            try {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                resolve();
            } catch (e) { reject(e); }
        });
    }

    function flash(btn, ok) {
        var original = btn.getAttribute('data-label') || btn.innerHTML;
        if (!btn.getAttribute('data-label')) btn.setAttribute('data-label', original);
        btn.innerHTML = ok
            ? '<i class="fa-solid fa-check"></i> تم النسخ!'
            : '<i class="fa-solid fa-xmark"></i> تعذّر';
        btn.classList.add(ok ? 'copied' : 'copy-fail');
        setTimeout(function () {
            btn.innerHTML = btn.getAttribute('data-label');
            btn.classList.remove('copied', 'copy-fail');
        }, 1600);
    }

    function makeCopyBtn(email) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'email-copy-btn';
        b.innerHTML = '<i class="fa-solid fa-copy"></i> نسخ';
        b.title = 'نسخ الإيميل';
        b.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            copyText(email).then(function () { flash(b, true); })
                           .catch(function () { flash(b, false); });
        });
        return b;
    }

    function enhance() {
        // كل روابط mailto + أي عنصر بـ data-email
        var mailtoLinks = Array.prototype.slice.call(
            document.querySelectorAll('a[href^="mailto:"], [data-email]')
        );
        mailtoLinks.forEach(function (el) {
            if (el.getAttribute('data-copy-enhanced')) return;
            el.setAttribute('data-copy-enhanced', '1');

            // نستخرج الإيميل
            var email = el.getAttribute('data-email');
            if (!email) {
                var href = el.getAttribute('href') || '';
                email = href.replace(/^mailto:/, '').split('?')[0] || PLATFORM_EMAIL;
            }

            // نضيف زر النسخ بعد العنصر مباشرة
            var btn = makeCopyBtn(email);
            if (el.parentNode) {
                // لو العنصر داخل رابط، نضع الزر بعده كشقيق
                if (el.nextSibling) {
                    el.parentNode.insertBefore(btn, el.nextSibling);
                } else {
                    el.parentNode.appendChild(btn);
                }
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', enhance);
    } else {
        enhance();
    }

    // نتيح استدعاءها يدوياً لو أُضيف إيميل ديناميكياً
    window.enhanceEmailCopy = enhance;
})();
