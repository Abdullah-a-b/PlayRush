(function() {
    // 1. منع استخدام الزر الأيمن بشكل كامل
    document.addEventListener('contextmenu', e => e.preventDefault());

    // 2. فخ الاختصارات الشامل (مستقل عن لغة الكيبورد)
    document.addEventListener('keydown', e => {
        // استخدام e.code الذي لا يتغير بتغير لغة الإدخال
        // KeyI, KeyJ, KeyC, KeyU, KeyS, F12
        const code = e.code; 
        
        if (
            code === 'F12' || 
            (e.ctrlKey && e.shiftKey && (code === 'KeyI' || code === 'KeyJ' || code === 'KeyC')) || 
            (e.ctrlKey && code === 'KeyU') || // منع View Source
            (e.metaKey && e.altKey && (code === 'KeyI' || code === 'KeyJ' || code === 'KeyU')) || // ماك
            (e.ctrlKey && code === 'KeyS') // منع الحفظ
        ) {
            e.preventDefault();
            e.stopPropagation();
            alert("⚠️ محاولة اختراق أو غش! تم تسجيل النشاط.");
            return false;
        }
    });

    // 3. فخ الـ Debugger السريع جداً (كل 100 ملي ثانية)
    setInterval(() => {
        const start = performance.now();
        debugger; 
        const end = performance.now();
        
        if (end - start > 50) {
            document.body.innerHTML = "<div style='display:flex; justify-content:center; align-items:center; height:100vh; background:red; color:white; font-family:sans-serif; text-align:center; padding:20px;'><h1>⛔ تم اكتشاف محاولة غش.<br>لا يمكنك اللعب وأدوات المطورين مفتوحة.</h1></div>";
            document.body.style.background = "red";
        }
    }, 100);
})();