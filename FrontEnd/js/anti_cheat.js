// =========================================================
// 🛡️ درع الحماية المتقدم (Client-Side Spy) - النسخة النهائية
// =========================================================

(function() {
    const MAX_CHEAT_ATTEMPTS = 3; 
    
    // سحب المحاولات السابقة، وإذا لم تكن موجودة نعتبرها 0
    let cheatViolations = parseInt(localStorage.getItem('cheatViolations')) || 0;

    // استخدام true في النهاية (Capture Phase) لضمان أن درع الحماية هو أول من يقرأ الكيبورد
    window.addEventListener('keydown', function(e) {
        
        // 🔴 الحل السحري لمشكلة الحظر السريع: منع احتساب الضغطة المطولة كعدة محاولات
        if (e.repeat) return; 

        // استخدام keyCode (الأرقام) لأنها أقوى في التقاط الاختصارات من الأسماء
        const isF12 = (e.keyCode === 123 || e.key === 'F12');
        const isI = (e.keyCode === 73 || (e.key && e.key.toLowerCase() === 'i'));
        const isJ = (e.keyCode === 74 || (e.key && e.key.toLowerCase() === 'j'));
        const isC = (e.keyCode === 67 || (e.key && e.key.toLowerCase() === 'c'));
        const isU = (e.keyCode === 85 || (e.key && e.key.toLowerCase() === 'u'));
        const isO = (e.keyCode === 79 || (e.key && e.key.toLowerCase() === 'o'));

        const isCtrlShiftI = (e.ctrlKey && e.shiftKey && isI);
        const isCtrlShiftJ = (e.ctrlKey && e.shiftKey && isJ);
        const isCtrlShiftC = (e.ctrlKey && e.shiftKey && isC);
        const isCtrlU = (e.ctrlKey && isU);
        const isCtrlO = (e.ctrlKey && isO);

        if (isF12 || isCtrlShiftI || isCtrlShiftJ || isCtrlShiftC || isCtrlU || isCtrlO) {
            
            // إيقاف فتح النافذة
            e.preventDefault();
            e.stopPropagation();

            // زيادة عدد المخالفات
            cheatViolations++;
            localStorage.setItem('cheatViolations', cheatViolations);

            if (cheatViolations >= MAX_CHEAT_ATTEMPTS) {
                executeBan();
            } else {
                const remaining = MAX_CHEAT_ATTEMPTS - cheatViolations;
                showWarningMessage(`⚠️ تحذير أمني: محاولة فتح أدوات المطور ممنوعة! تتبقى لك ${remaining} محاولة قبل الحظر.`);
            }
            
            return false;
        }
    }, true); // <-- true هنا مهمة جداً (Capture Phase)

    // 🚫 حظر الكليك يمين
    window.addEventListener('contextmenu', function(e) {
        e.preventDefault();
    }, true);

    // ---------------------------------------------------------
    // دوال المساعدة
    // ---------------------------------------------------------
    function showWarningMessage(message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: 'warning',
                title: 'تحذير!',
                text: message,
                confirmButtonColor: '#d33'
            });
        } else {
            alert(message);
        }
    }

    function executeBan() {
        console.warn("🚫 تم حظر اللاعب لتجاوز الحد الأقصى من محاولات الغش.");
        
        if (typeof socket !== 'undefined' && socket.connected) {
            socket.emit('player_cheated', { reason: 'Tried to open DevTools multiple times' });
        }

        // تدمير الجلسة
        localStorage.removeItem('token');
        localStorage.removeItem('userData');
        
        // طمس الشاشة
        document.body.innerHTML = `
            <div style="height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: #0d0d1a; color: red; text-align: center; direction: rtl;">
                <h1 style="font-size: 3rem;">تم حظرك!</h1>
                <p style="font-size: 1.5rem; color: white;">لقد تجاوزت الحد الأقصى لمحاولات العبث بالنظام.</p>
            </div>
        `;
        
        setTimeout(() => {
            window.location.href = '../login.html'; 
        }, 3000);
    }

})();