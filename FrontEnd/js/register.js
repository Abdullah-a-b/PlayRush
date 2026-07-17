// نضع هذا السطر في بداية الملف
document.getElementById('google-login-btn').href = `${CONFIG.API_URL}/auth/google/login`;


let lastSubmitTime = 0;
const COOLDOWN_MS = 3000; // 3 ثوانٍ انتظار بين كل محاولة

function createStars() {
    const starsContainer = document.getElementById('stars');
    if (!starsContainer) return;
    starsContainer.innerHTML = ''; // تنظيف النجوم القديمة
    for (let i = 0; i < 150; i++) {
        const star = document.createElement('div');
        star.className = 'star';
        star.style.left = `${Math.random() * 100}%`;
        star.style.top = `${Math.random() * 100}%`;
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
    setupPasswordToggle('toggleConfirmPassword', 'confirmPassword');

    const registerForm = document.getElementById("registerForm");
    
    if (registerForm) {
        registerForm.addEventListener("submit", async function (e) {
        const _consent = document.getElementById('ageTermsConsent');
        if (_consent && !_consent.checked) {
            e.preventDefault();
            alert('يجب الإقرار بأن عمرك 13+ والموافقة على الشروط للمتابعة');
            return;
        }
            e.preventDefault();

            // Check cooldown
            const now = Date.now();
            if (now - lastSubmitTime < COOLDOWN_MS) {
                alert("يرجى الانتظار قبل محاولة التسجيل مرة أخرى.");
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
                
                const data = await response.json();

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
                msgDiv.textContent = err.message;
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