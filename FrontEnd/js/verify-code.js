// ملف config.js
const isLocal = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
const API_URL = isLocal ? CONFIG.API_URL : "https://api.your-real-domain.com";
let lastSubmitTime = 0;
const COOLDOWN_MS = 3000; // 3 ثوانٍ انتظار بين كل محاولة

window.addEventListener('load', () => {
    if (typeof createStars === "function") createStars();

    const storedEmail = sessionStorage.getItem("verifyEmail");
    const flowType = sessionStorage.getItem("verifyFlow") || "register";
    
    const form = document.getElementById("verifyCodeForm");
    const inputs = document.querySelectorAll(".field-box");
    const msgBox = document.getElementById("verifyMessage");

    // حماية بدون Alert
    if (!storedEmail) {
        if(msgBox) {
            msgBox.textContent = "لا يوجد حساب قيد التحقق. يرجى التسجيل أولاً.";
            msgBox.style.color = "#f43f5e";
        }
        return;
    }

    // 1. إعداد مربعات الإدخال (Inputs)
    inputs.forEach((input, index) => {
        input.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
            const val = e.target.value;
            if (val.length === 1 && index < inputs.length - 1) { inputs[index + 1].focus(); }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === "Backspace" && input.value === "" && index > 0) { inputs[index - 1].focus(); }
        });

        input.addEventListener('paste', (e) => {
            e.preventDefault();
            const pasteData = (e.clipboardData || window.clipboardData).getData('text');
            const numbers = pasteData.replace(/[^0-9]/g, '').split('');
            if (numbers.length > 0) {
                inputs.forEach((inp, i) => { if (i < numbers.length) inp.value = numbers[i]; });
                const targetIndex = Math.min(numbers.length, inputs.length) - 1;
                if (targetIndex >= 0) inputs[targetIndex].focus();
            }
        });
    });

    // ==========================================
    // ⏳ نظام إعادة الإرسال والكول داون (60 ثانية)
    // ==========================================
    const resendBtn = document.getElementById('resendBtn');
    const resendTimerText = document.getElementById('resendTimerText');
    const countdownEl = document.getElementById('countdown');
    let cooldownTimerId;

    function startVerificationCooldown() {
        let timeLeft = 60;
        if(resendBtn) resendBtn.style.display = 'none';
        if(resendTimerText) resendTimerText.style.display = 'block';
        if(countdownEl) countdownEl.textContent = timeLeft;

        cooldownTimerId = setInterval(() => {
            timeLeft--;
            if(countdownEl) countdownEl.textContent = timeLeft;
            if (timeLeft <= 0) {
                clearInterval(cooldownTimerId);
                if(resendTimerText) resendTimerText.style.display = 'none';
                if(resendBtn) resendBtn.style.display = 'block';
            }
        }, 1000);
    }

    // تشغيل العداد تلقائياً عند فتح الصفحة
    startVerificationCooldown();

    if(resendBtn) {
        resendBtn.addEventListener('click', async () => {
            resendBtn.disabled = true;
            resendBtn.textContent = 'جاري الإرسال...';
            if(msgBox) msgBox.textContent = "";

            const formData = new FormData();
            formData.append('email', storedEmail); // استخدام الإيميل المحفوظ

            // التوجيه الذكي: هل هو تسجيل جديد أم نسيان كلمة مرور؟
            let endpoint = flowType === 'reset' ? '/auth/forgot-password' : '/auth/resend-otp';

            try {
                const response = await fetch(`${API_URL}${endpoint}`, { method: 'POST', body: formData });
                const data = await response.json();

                if (response.ok) {
                    if(msgBox) { msgBox.textContent = "تم إرسال رمز جديد إلى بريدك!"; msgBox.style.color = "#00ff88"; }
                    resendBtn.textContent = 'إعادة إرسال الرمز';
                    resendBtn.disabled = false;
                    startVerificationCooldown(); // إعادة تشغيل العداد
                } else {
                    if(msgBox) { msgBox.textContent = data.detail || "حدث خطأ أثناء إرسال الرمز"; msgBox.style.color = "#f43f5e"; }
                    resendBtn.textContent = 'إعادة إرسال الرمز';
                    resendBtn.disabled = false;
                }
            } catch (error) {
                if(msgBox) { msgBox.textContent = "فشل الاتصال بالسيرفر"; msgBox.style.color = "#f43f5e"; }
                resendBtn.textContent = 'إعادة إرسال الرمز';
                resendBtn.disabled = false;
            }
        });
    }

    // ==========================================
    // 🔐 التحقق من الرمز (Submit)
    // ==========================================
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            const now = Date.now();
            if (now - lastSubmitTime < COOLDOWN_MS) {
                showError("يرجى الانتظار قليلاً قبل المحاولة مرة أخرى.");
                return;
            }
            lastSubmitTime = now;
            
            let code = "";
            inputs.forEach(inp => { code += inp.value; });
            
            if (code.length < 6) {
                msgBox.textContent = "يرجى إدخال الرمز كاملاً (6 أرقام)";
                msgBox.style.color = "#f43f5e";
                return;
            }

            const btn = form.querySelector("button[type='submit']");
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = "جاري التحقق...";
            msgBox.textContent = "";

            const formData = new FormData();
            formData.append("email", storedEmail);
            formData.append("code", code);
            formData.append("flow", flowType);

            try {
                const response = await fetch(`${API_URL}/auth/verify-code`, { method: "POST", body: formData });
                const data = await response.json();

                if (response.ok) {
                    msgBox.textContent = "تم التحقق بنجاح!";
                    msgBox.style.color = "#00ff88";
                    
                    if (flowType === "reset") {
                        sessionStorage.setItem("resetCode", code);
                        window.location.replace("reset-password.html");
                    } else {
                        sessionStorage.removeItem("verifyEmail");
                        sessionStorage.removeItem("verifyFlow");
                        window.location.replace("login.html");
                    }
                } else {
                    msgBox.textContent = data.detail || "الرمز غير صحيح";
                    msgBox.style.color = "#f43f5e";
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            } catch (err) {
                msgBox.textContent = "فشل الاتصال بالسيرفر";
                msgBox.style.color = "#f43f5e";
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });
    }
});

// دالة إنشاء النجوم للخلفية
function createStars() { 
    const c = document.getElementById("stars"); if(!c) return; c.innerHTML='';
    for(let i=0;i<100;i++){const s=document.createElement("div");s.className="star";
    s.style.left=Math.random()*100+"%";s.style.top=Math.random()*100+"%";
    c.appendChild(s);}
}