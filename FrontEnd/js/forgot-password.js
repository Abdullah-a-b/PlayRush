// ملف config.js
const isLocal = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
const API_URL = isLocal ? CONFIG.API_URL : "https://api.your-real-domain.com";
let lastSubmitTime = 0;
const COOLDOWN_MS = 3000; // 3 ثوانٍ انتظار بين كل محاولة

// دالة النجوم
function createStars() {
    const starsContainer = document.getElementById('stars');
    if (!starsContainer) return;
    starsContainer.innerHTML = '';
    for (let i = 0; i < 150; i++) {
        const star = document.createElement('div');
        star.className = 'star' + (Math.random() > 0.3 ? ' purple' : '');
        star.style.left = `${Math.random() * 100}%`;
        star.style.top = `${Math.random() * 100}%`;
        star.style.animationDelay = `${Math.random() * 2}s`;
        starsContainer.appendChild(star);
    }
}

window.addEventListener('load', () => {
    if (typeof createStars === 'function') createStars();
    const form = document.querySelector('form');
    const emailInput = document.querySelector('input[type="email"]');
    
    // إنشاء مربع للرسائل
    const msgBox = document.createElement('div');
    msgBox.style.marginTop = "15px";
    msgBox.style.textAlign = "center";
    form.appendChild(msgBox);

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const now = Date.now();
            if (now - lastSubmitTime < COOLDOWN_MS) {
                showError("يرجى الانتظار قليلاً قبل المحاولة مرة أخرى.");
                return;
            }
            lastSubmitTime = now;
            
            const btn = form.querySelector('button[type="submit"]');
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = "جاري الإرسال...";
            msgBox.textContent = "";

            const formData = new FormData();
            formData.append("email", emailInput.value);

            try {
                const response = await fetch(`${API_URL}/auth/forgot-password`, {
                    method: "POST",
                    body: formData
                });
                
                const data = await response.json();

                if (response.ok) {
                    // حفظ الإيميل والمسار لصفحة التحقق
                    sessionStorage.setItem("verifyEmail", emailInput.value);
                    sessionStorage.setItem("verifyFlow", "reset");
                    
                    msgBox.textContent = "تم إرسال الرمز! جاري التحويل...";
                    msgBox.style.color = "#00ff88";
                    
                    // تحويل مباشر 
                    window.location.replace("verify-code.html");
                } else {
                    msgBox.textContent = data.detail || "حدث خطأ";
                    msgBox.style.color = "#ff4d4d";
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            } catch (err) {
                msgBox.textContent = "فشل الاتصال بالسيرفر";
                msgBox.style.color = "#ff4d4d";
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });
    }
});