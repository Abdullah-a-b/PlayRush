/* ============================================================
   PlayRush — نوافذ حوار مخصّصة (بديل alert / confirm / prompt)
   ------------------------------------------------------------
   • تبني DOM الخاص بها تلقائياً → تعمل في أي صفحة بلا HTML إضافي.
   • مناسبة للجوال: أزرار كبيرة للمس، عرض مرن، دعم RTL.
   • واجهة Promise: تُستخدم مع await بدل الحظر التزامني.

        await prAlert('نص الرسالة');
        if (await prConfirm('هل أنت متأكد؟')) { ... }
        const v = await prPrompt('الاسم الجديد:', 'القيمة الحالية');

   • showConfirm(title, msg, onConfirm, onCancel) محفوظة للتوافق
     مع الكود القديم، لكنها تعمل الآن عبر هذه النافذة.
   ============================================================ */
(function () {
    if (window.__prDialogReady) return;
    window.__prDialogReady = true;

    var STYLE = `
    .pr-dlg-overlay{position:fixed;inset:0;background:rgba(8,3,15,.72);
        backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;
        z-index:2147483000;padding:18px;opacity:0;transition:opacity .16s ease;}
    .pr-dlg-overlay.show{opacity:1;}
    .pr-dlg{width:100%;max-width:380px;background:linear-gradient(180deg,#3a1257 0%,#2a0d40 100%);
        border:1px solid rgba(255,235,59,.28);border-radius:18px;
        box-shadow:0 18px 50px rgba(0,0,0,.55);padding:20px 18px 16px;
        font-family:inherit;color:#f3e9ff;text-align:center;
        transform:translateY(10px) scale(.98);transition:transform .16s ease;}
    .pr-dlg-overlay.show .pr-dlg{transform:translateY(0) scale(1);}
    .pr-dlg h3{margin:0 0 8px;font-size:1.05rem;font-weight:800;color:#ffe14d;}
    .pr-dlg p{margin:0 0 16px;font-size:.95rem;line-height:1.6;color:#e8dcff;
        white-space:pre-wrap;word-break:break-word;}
    .pr-dlg input{width:100%;box-sizing:border-box;padding:13px 14px;margin:0 0 16px;
        border-radius:12px;border:1px solid rgba(255,255,255,.16);
        background:rgba(0,0,0,.3);color:#fff;font-size:1rem;font-family:inherit;
        text-align:inherit;outline:none;}
    .pr-dlg input:focus{border-color:#ffe14d;}
    .pr-dlg-btns{display:flex;gap:10px;}
    .pr-dlg-btns button{flex:1;min-height:46px;padding:12px 10px;border:none;border-radius:12px;
        font-family:inherit;font-size:.98rem;font-weight:700;cursor:pointer;
        -webkit-tap-highlight-color:transparent;transition:filter .15s ease,transform .1s ease;}
    .pr-dlg-btns button:active{transform:scale(.97);}
    .pr-dlg-ok{background:linear-gradient(180deg,#ffd93d,#f0a500);color:#2a0d40;}
    .pr-dlg-cancel{background:rgba(255,255,255,.12);color:#e8dcff;}
    @media (max-width:380px){ .pr-dlg h3{font-size:1rem;} .pr-dlg p{font-size:.9rem;} }
    `;

    function injectStyle() {
        if (document.getElementById('pr-dlg-style')) return;
        var s = document.createElement('style');
        s.id = 'pr-dlg-style';
        s.textContent = STYLE;
        (document.head || document.documentElement).appendChild(s);
    }

    /* النواة: تبني نافذة وتُرجع Promise بالنتيجة */
    function open(opts) {
        injectStyle();
        return new Promise(function (resolve) {
            var overlay = document.createElement('div');
            overlay.className = 'pr-dlg-overlay';

            var box = document.createElement('div');
            box.className = 'pr-dlg';
            box.setAttribute('role', 'dialog');
            box.setAttribute('aria-modal', 'true');

            if (opts.title) {
                var h = document.createElement('h3');
                h.textContent = opts.title;
                box.appendChild(h);
            }

            var p = document.createElement('p');
            p.textContent = opts.message || '';
            box.appendChild(p);

            var input = null;
            if (opts.type === 'prompt') {
                input = document.createElement('input');
                input.type = 'text';
                input.value = opts.defaultValue || '';
                box.appendChild(input);
            }

            var btns = document.createElement('div');
            btns.className = 'pr-dlg-btns';

            // زر الإلغاء أولاً (يمين في RTL) ثم التأكيد
            var cancelBtn = null;
            if (opts.type !== 'alert') {
                cancelBtn = document.createElement('button');
                cancelBtn.className = 'pr-dlg-cancel';
                cancelBtn.textContent = opts.cancelText || 'إلغاء';
                btns.appendChild(cancelBtn);
            }

            var okBtn = document.createElement('button');
            okBtn.className = 'pr-dlg-ok';
            okBtn.textContent = opts.okText || 'حسناً';
            btns.appendChild(okBtn);

            box.appendChild(btns);
            overlay.appendChild(box);
            document.body.appendChild(overlay);
            requestAnimationFrame(function () { overlay.classList.add('show'); });

            var prevOverflow = document.body.style.overflow;
            document.body.style.overflow = 'hidden';

            function close(result) {
                document.removeEventListener('keydown', onKey);
                document.body.style.overflow = prevOverflow;
                overlay.classList.remove('show');
                setTimeout(function () {
                    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                }, 170);
                resolve(result);
            }

            function onKey(e) {
                if (e.key === 'Escape' && opts.type !== 'alert') close(opts.type === 'prompt' ? null : false);
                else if (e.key === 'Enter') confirmNow();
            }

            function confirmNow() {
                if (opts.type === 'prompt') close(input ? input.value : '');
                else close(true);
            }

            okBtn.addEventListener('click', confirmNow);
            if (cancelBtn) {
                cancelBtn.addEventListener('click', function () {
                    close(opts.type === 'prompt' ? null : false);
                });
            }
            // النقر خارج الصندوق = إلغاء (ما عدا alert)
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay && opts.type !== 'alert') {
                    close(opts.type === 'prompt' ? null : false);
                }
            });

            document.addEventListener('keydown', onKey);
            setTimeout(function () { (input || okBtn).focus(); }, 60);
        });
    }

    window.prAlert = function (message, title) {
        return open({ type: 'alert', message: message, title: title || 'تنبيه' });
    };
    window.prConfirm = function (message, title) {
        return open({ type: 'confirm', message: message, title: title || 'تأكيد' });
    };
    window.prPrompt = function (message, defaultValue, title) {
        return open({ type: 'prompt', message: message, defaultValue: defaultValue, title: title || '' });
    };

    /* توافق مع الاستدعاء القديم showConfirm(title,msg,onConfirm,onCancel) */
    window.showConfirm = function (title, message, onConfirm, onCancel) {
        open({ type: 'confirm', title: title, message: message }).then(function (ok) {
            if (ok) { if (typeof onConfirm === 'function') onConfirm(); }
            else { if (typeof onCancel === 'function') onCancel(); }
        });
    };
})();
