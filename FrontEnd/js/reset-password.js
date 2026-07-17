let lastSubmitTime = 0;
const COOLDOWN_MS = 3000; // 3 ثوانٍ انتظار بين كل محاولة

function createStars() {
    const c = document.getElementById("stars"); if(!c) return; c.innerHTML='';
    for(let i=0;i<100;i++){const s=document.createElement("div");s.className="star";
    s.style.left=Math.random()*100+"%";s.style.top=Math.random()*100+"%";
    c.appendChild(s);}
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
    if (typeof createStars === 'function') createStars();

    setupPasswordToggle('togglePassword', 'password');
    setupPasswordToggle('toggleConfirmPassword', 'confirmPassword');
    // جلب الإيميل والرمز من الذاكرة
    const storedEmail = sessionStorage.getItem("verifyEmail");
    const resetCode = sessionStorage.getItem("resetCode");

    const form = document.querySelector('form');
    // جلب مربعات الباسوورد (الأول للجديد، والثاني للتأكيد)
    const passInputs = document.querySelectorAll('input[type="password"]');
    const passInput = passInputs[0];
    const confirmPassInput = passInputs[1];
    
    const msgBox = document.createElement('div');
    msgBox.style.marginTop = "15px";
    msgBox.style.textAlign = "center";
    form.appendChild(msgBox);

    // حماية: إذا دخل الصفحة بدون ما يمر بالتحقق
    if (!storedEmail || !resetCode) {
        msgBox.textContent = "جلسة غير صالحة. يرجى البدء من صفحة نسيت كلمة المرور.";
        msgBox.style.color = "#ff4d4d";
        const btn = form.querySelector('button');
        if(btn) btn.disabled = true;
        return;
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const now = Date.now();
            if (now - lastSubmitTime < COOLDOWN_MS) {
                showError("يرجى الانتظار قليلاً قبل المحاولة مرة أخرى.");
                return;
            }
            lastSubmitTime = now;
            
            if (passInput.value !== confirmPassInput.value) {
                msgBox.textContent = "كلمات المرور غير متطابقة!";
                msgBox.style.color = "#ff4d4d";
                return;
            }

            if (passInput.value.length < 6) {
                msgBox.textContent = "كلمة المرور يجب أن تكون 6 أحرف على الأقل";
                msgBox.style.color = "#ff4d4d";
                return;
            }

            const btn = form.querySelector('button[type="submit"]');
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = "جاري الحفظ...";
            msgBox.textContent = "";

            const formData = new FormData();
            formData.append("email", storedEmail);
            formData.append("code", resetCode);
            formData.append("new_password", passInput.value);

            try {
                const response = await fetch(`${API_URL}/auth/reset-password`, {
                    method: "POST",
                    body: formData
                });
                
                const data = await response.json();

                if (response.ok) {
                    msgBox.textContent = "تم تغيير كلمة المرور بنجاح!";
                    msgBox.style.color = "#00ff88";
                    
                    sessionStorage.removeItem("verifyEmail");
                    sessionStorage.removeItem("verifyFlow");
                    sessionStorage.removeItem("resetCode");
                    
                    window.location.replace("login.html");
                } else {
                    //  التعديل الجديد: التقاط حالة تطابق كلمة المرور
                    if (data.detail === "كلمة المرور الجديدة مطابقة للقديمة") {
                        msgBox.textContent = "كلمة المرور لم تتغير (مطابقة للقديمة)! جاري التحويل...";
                        msgBox.style.color = "#facc15"; // لون أصفر تحذيري
                        
                        // تنظيف الذاكرة
                        sessionStorage.removeItem("verifyEmail");
                        sessionStorage.removeItem("verifyFlow");
                        sessionStorage.removeItem("resetCode");
                        
                        // تحويل بعد ثانيتين ليتمكن اللاعب من قراءة التنبيه
                        setTimeout(() => {
                            window.location.replace("login.html");
                        }, 2000);
                        
                    } else {
                        // الأخطاء الأخرى العادية
                        msgBox.textContent = data.detail || "حدث خطأ";
                        msgBox.style.color = "#ff4d4d";
                        btn.disabled = false;
                        btn.textContent = originalText;
                    }
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