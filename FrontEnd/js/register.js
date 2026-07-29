// نضع هذا السطر في بداية الملف
// ربط زر جوجل انتقل إلى js/google_auth.js (يدعم الويب والتطبيق)


let lastSubmitTime = 0;
const COOLDOWN_MS = 3000; // 3 ثوانٍ انتظار بين كل محاولة

function createStars() {
    const starsContainer = document.getElementById('stars');
    if (!starsContainer) return;
    starsContainer.innerHTML = ''; // تنظيف النجوم القديمة
    // 🌟 التوليد انتقل إلى js/stars.js: توزيع شبكي + عدد أقل
    //    (كان 150 نجمة عشوائية بهالات ضبابية تستنزف ذاكرة الرسم)
    if (window.PRStars) { window.PRStars.render(starsContainer); return; }
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
    setupPasswordToggle('toggleConfirmPassword', 'confirmPassword');

    const registerForm = document.getElementById("registerForm");
    
    if (registerForm) {
        registerForm.addEventListener("submit", async function (e) {
        const _consent = document.getElementById('ageTermsConsent');
        if (_consent && !_consent.checked) {
            e.preventDefault();
            prAlert('يجب الإقرار بأن عمرك 13+ والموافقة على الشروط للمتابعة');
            return;
        }
            e.preventDefault();

            // Check cooldown
            const now = Date.now();
            if (now - lastSubmitTime < COOLDOWN_MS) {
                prAlert("يرجى الانتظار قبل محاولة التسجيل مرة أخرى.");
                return;
            }
            lastSubmitTime = now;

            const password = document.getElementById("password").value;
            const confirmPassword = document.getElementById("confirmPassword").value;
            
            let msgDiv = document.getElementById("messageBox");
            if (!msgDiv) {
                msgDiv = document.createElement("div");
                msgDiv.id = "messageBox";
                msgDiv.style.marginTop = "15px"; 
                msgDiv.style.padding = "10px";
                msgDiv.style.borderRadius = "5px";
                msgDiv.style.textAlign = "center";
                registerForm.appendChild(msgDiv);
            }

            if (password !== confirmPassword) {
                msgDiv.textContent = "كلمتا المرور غير متطابقتين!";
                msgDiv.style.backgroundColor = "rgba(244, 63, 94, 0.1)";
                msgDiv.style.color = "#ff4d4d";
                msgDiv.style.border = "1px solid #ff4d4d";
                return; 
            }
            
            if (password.length < 6) {
                msgDiv.textContent = "كلمة المرور يجب أن تكون 6 أحرف على الأقل";
                msgDiv.style.backgroundColor = "rgba(244, 63, 94, 0.1)";
                msgDiv.style.color = "#ff4d4d";
                msgDiv.style.border = "1px solid #ff4d4d";
                return;
            }

            const submitBtn = this.querySelector('button[type="submit"]');
            const originalText = submitBtn ? submitBtn.textContent : "تسجيل";
            
            if(submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "جاري الاتصال...";
            }

            const formData = new FormData();
            formData.append("email", document.getElementById("email").value);
            formData.append("password", document.getElementById("password").value);
            
            //  الكود النظيف: إرسال القيم الافتراضية للحساب الجديد فوراً (تم حذف نظام الضيف)
            formData.append("coins", 0);
            formData.append("gems", 0);
            formData.append("level", 1);

            try {
                const response = await fetch(`${API_URL}/auth/register`, {
                    method: "POST",
                    body: formData
                });
                
                let data = {};
                try { data = await response.json(); } catch (e) { data = {}; }

                // 429 = تجاوز حدّ المحاولات — نوضّح السبب بدل رسالة عامة
                if (response.status === 429) {
                    throw new Error("__RATE_LIMIT__");
                }

                if (response.ok) {
                    const userEmail = document.getElementById("email").value;
                    sessionStorage.setItem("verifyEmail", userEmail);
                    sessionStorage.setItem("verifyFlow", "register");
                    
                    msgDiv.textContent = "تم إرسال رمز التحقق! جاري التحويل...";
                    msgDiv.style.backgroundColor = "#d4edda";
                    msgDiv.style.color = "#155724";
                    
                    window.location.replace("verify-code.html");
                }
                else {
                    let errorMsg = "فشل التسجيل";
                    if (data.detail) {
                        if (Array.isArray(data.detail)) {
                            errorMsg = "يوجد خطأ في البيانات المدخلة"; 
                        } else {
                            errorMsg = data.detail;
                        }
                    }
                    throw new Error(errorMsg);
                }
            } catch (err) {
                console.error("Error:", err);
                msgDiv.textContent = (err && err.message === "__RATE_LIMIT__")
                    ? "محاولات كثيرة خلال وقت قصير. انتظر قليلاً ثم أعد المحاولة."
                    : (err.message || "تعذّر الوصول للسيرفر");
                msgDiv.style.backgroundColor = "#f8d7da";
                msgDiv.style.color = "#721c24";
                
                if(submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
        });
    }
});