// FrontEnd/js/config.js

const CONFIG = {
    // الدومين الخاص بالباك إند (API)
    API_URL: "http://127.0.0.1:8000", 
    
    // الدومين الخاص بالاتصال المباشر (Socket.io)
    WS_URL: "http://127.0.0.1:8000"
};

// دالة مساعدة لتسهيل جلب التوكن من أي مكان
const getToken = () => localStorage.getItem('token') || sessionStorage.getItem('token');

document.addEventListener('click', function(e) {
    // نراقب أي نقرة في الموقع، وإذا كانت النقرة على "زر رفع ملف/صورة"
    if (e.target && e.target.type === 'file') {
        // نقوم بتفريغ ذاكرة الزر في نفس اللحظة (قبل أن تفتح نافذة اختيار الصور)
        // هذا يخدع المتصفح ويجعله يعتقد أن الصورة التي ستختارها هي "تغيير جديد" دائماً!
        e.target.value = '';
    }
});