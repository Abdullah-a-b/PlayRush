// 🛡️ درع الحماية المتقدم (Client-Side Spy)
document.addEventListener('keydown', function(e) {
    // التقاط F12 أو Ctrl+Shift+I أو Ctrl+U
    if (e.key === 'F12' || 
       (e.ctrlKey && e.shiftKey && e.key === 'I') || 
       (e.ctrlKey && e.key === 'U')) {
        
        e.preventDefault(); // منع المتصفح من فتح النافذة
        
        // إبلاغ الباك إند بوجود اختراق أمني خطير!
        if (typeof socket !== 'undefined' && socket.connected) {
            socket.emit('severe_security_breach', { reason: 'محاولة فتح أو فحص مصدر الكود' });
        }
        
        // طرد المستخدم فوراً من الشاشة كإجراء أولي
        document.body.innerHTML = "<h1 style='color:red; text-align:center; margin-top:20%;'>تم اكتشاف نشاط مشبوه. جاري حظر الحساب...</h1>";
        setTimeout(() => { window.location.href = '../login.html'; }, 2000);
    }
});

// منع الكليك يمين (Right Click)
document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
});