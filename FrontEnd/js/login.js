// نضع هذا السطر في بداية الملف
// ربط زر جوجل انتقل إلى js/google_auth.js (يدعم الويب والتطبيق)


let lastSubmitTime = 0;
const COOLDOWN_MS = 3000; // 3 ثوانٍ انتظار بين كل محاولة

function createStars() {
    const starsContainer = document.getElementById('stars');
    if (!starsContainer) return;
    for (let i = 0; i < 50; i++) {
        const star = document.createElement('div');
        star.className = 'star';
        star.style.left = `${Math.random() * 100}%`;
        star.style.top = `${Math.random() * 100}%`;
        star.style.animationDuration = `${Math.random() * 2 + 1}s`;
        starsContainer.appendChild(star);
    }
}

function setupPasswordToggle(toggleId, inputId) {
    const toggle = document.getElementById(toggleId);
    const input = document.getElementById(inputId);
    if (toggle && input) {
        toggle.addEventListener('click', function () {
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);
            this.classList.toggle('fa-eye');
            this.classList.toggle('fa-eye-slash');
        });
    }
}

window.addEventListener('load', () => {
    createStars();

    setupPasswordToggle('togglePassword', 'password');

    const loginForm = document.getElementById('loginForm');
    const messageBox = document.getElementById('loginMessage');

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Check cooldown
            const now = Date.now();
            if (now - lastSubmitTime < COOLDOWN_MS) {
                prAlert("يرجى الانتظار قبل محاولة تسجيل الدخول مرة أخرى.");
                return;
            }
            lastSubmitTime = now;

            const submitBtn = loginForm.querySelector('button[type="submit"]');
            const originalText = submitBtn ? submitBtn.textContent : 'دخول';
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'جاري الاتصال...';
            }

            const formData = new FormData();
            formData.append('username', document.getElementById('email').value);
            formData.append('password', document.getElementById('password').value); //  الحل الصحيح

            try {
                const response = await fetch(`${API_URL}/auth/login`, {
                    method: 'POST',
                    body: formData
                });

                let data = {};
                try { data = await response.json(); } catch (e) { data = {}; }

                // 429 = تجاوز حدّ المحاولات — نوضّح السبب بدل رسالة عامة
                if (response.status === 429) {
                    throw new Error("__RATE_LIMIT__");
                }

                if (response.ok) {
                    messageBox.textContent = 'تم تسجيل الدخول! جاري تحويلك...';
                    messageBox.style.color = '#00ff88';
                    
                    if (data.token) {
                        // توحيد استخدام الذاكرة لتكون sessionStorage
                        sessionStorage.setItem('token', data.token);
                        // 💾 "تذكرني": دخول محفوظ حتى انتهاء صلاحية التوكن (7 أيام)
                        try {
                            const remember = document.getElementById('rememberMe');
                            // 📱 التطبيق: الجلسة محفوظة دائماً (كما اتفقنا)
                            if (window.PR_IS_APP || (remember && remember.checked)) {
                                localStorage.setItem('token', data.token);
                            } else {
                                localStorage.removeItem('token');
                            }
                        } catch (e) {}
                    }

                    // 🎬 دخول جديد = أنيميشن المنصة يُعرض من جديد (حتى لو
                    // كان logout ثم login داخل نفس جلسة المتصفح)
                    try { sessionStorage.removeItem('pr_splash_platform'); } catch (e) {}

                    //  التوجيه الذكي والفوري! (بدون انتظار لتخطي مشكلة التحديث)
                    if (data.has_profile) {
                        window.location.replace('categories.html');
                    } else {
                        window.location.replace('profile-setup.html');
                    }

                } else {
                // استقبال أمر التوجيه
                if (response.status === 403 && data.action === "redirect_to_verify") {
                    loginMessage.textContent = data.detail;
                    loginMessage.style.color = "#facc15"; 
                    sessionStorage.setItem('registeredEmail', data.email); 
                    setTimeout(() => {
                        window.location.href = "verify-code.html";
                    }, 2000);
                    return; 
                }

                //  الحساب محظور → صفحة حظر لائقة بدل عرض JSON خام
                let rawMsg = data.detail || "";
                if (response.status === 403 && typeof rawMsg === 'string' &&
                    (rawMsg.includes('حظر') || rawMsg.includes('محظور'))) {
                    sessionStorage.setItem('banReason', rawMsg);
                    window.location.replace('banned.html');
                    return;
                }

                //  محرك قراءة الأخطاء الذكي بدلاً من [object Object]
                let errorMsg = data.detail || "خطأ في تسجيل الدخول";
                
                if (typeof errorMsg === 'object') {
                    // إذا كان الخطأ مصفوفة من السيرفر (Error 422)، نستخرج اسم الحقل الناقص
                    errorMsg = Array.isArray(errorMsg) 
                        ? "بيانات غير صالحة أو ناقصة في حقل: " + errorMsg.map(e => e.loc[e.loc.length - 1]).join(", ") 
                        : "خطأ غير معروف في البيانات";
                }

                loginMessage.textContent = errorMsg;
                loginMessage.style.color = "#ff4d4d";
                submitBtn.disabled = false;
                submitBtn.textContent = "تسجيل الدخول";
                }
            } catch (error) {
            loginMessage.textContent = (error && error.message === "__RATE_LIMIT__")
                ? "محاولات كثيرة خلال وقت قصير. انتظر قليلاً ثم أعد المحاولة."
                : "تعذّر الوصول للسيرفر. تحقّق من اتصالك بالإنترنت.";
            loginMessage.style.color = "#ff4d4d";
            submitBtn.disabled = false;
            submitBtn.textContent = "تسجيل الدخول";
        }
        });
    }
});