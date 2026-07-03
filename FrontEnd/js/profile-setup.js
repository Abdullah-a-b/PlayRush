// 1. التقاط التوكن بذكاء وتنظيف الرابط
const urlParams = new URLSearchParams(window.location.search);
const tokenFromUrl = urlParams.get('token');
if (tokenFromUrl) {
    sessionStorage.setItem('token', tokenFromUrl);
    window.history.replaceState({}, document.title, window.location.pathname);
}

let customAvatarFile = null;

function getCorrectAvatarUrl(path) {
    if (!path) return '../assets/avatars/avatar_1.svg';
    if (path.startsWith('http')) return path;
    if (path.startsWith('/uploads')) return `${API_URL}${path}`;
    const cleanPath = path.replace('../', '');
    return `../${cleanPath}`;
}

// 2. النجوم (تأثير بصري)
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

window.addEventListener('load', () => {
    createStars();
    
    // 3. توليد الصور المجانية فقط (1-15). الباقي (16-60) يُشترى من المتجر
    //    لتفادي التضارب مع نظام الأفاتارات المقفلة في الإعدادات.
    const FREE_AVATARS_COUNT = 15;
    const defaultAvatars = [];
    for (let i = 1; i <= FREE_AVATARS_COUNT; i++) {
        defaultAvatars.push(`../assets/avatars/avatar_${i}.svg`);
    }

    let currentAvatarData = defaultAvatars[0];
    const mainProfileImg = document.getElementById('mainProfileImg');
    const avatarModal = document.getElementById('avatarModal');
    const avatarsGrid = document.getElementById('avatarsGrid');
    const customFileInput = document.getElementById('customFileInput');
    const removeCustomBtn = document.getElementById('removeCustomBtn');

    mainProfileImg.src = defaultAvatars[0];

    // تعبئة النافذة بالصور الجاهزة
    defaultAvatars.forEach(src => {
        const img = document.createElement('img');
        img.setAttribute('src', src); // حماية المسار
        img.className = 'avatar-item';
        if (src === currentAvatarData) img.classList.add('selected');
        
        img.addEventListener('click', () => {
            document.querySelectorAll('.avatar-item').forEach(el => el.classList.remove('selected'));
            img.classList.add('selected');
            
            currentAvatarData = src;
            mainProfileImg.setAttribute('src', src);
            if (removeCustomBtn) removeCustomBtn.style.display = 'none'; 
            if (customFileInput) customFileInput.value = ''; 
            closeModal();
        });
        avatarsGrid.appendChild(img);
    });

    function openModal() { avatarModal.classList.add('active'); }
    function closeModal() { avatarModal.classList.remove('active'); }
    
    document.getElementById('openModalBtn').addEventListener('click', openModal);
    document.getElementById('closeModalBtn').addEventListener('click', closeModal);
    avatarModal.addEventListener('click', (e) => { if(e.target === avatarModal) closeModal(); });

    // 4. رفع صورة مخصصة — 🔒 مؤجّل حالياً (العناصر محذوفة من HTML)
    if (customFileInput && removeCustomBtn) {
    customFileInput.addEventListener('click', function() { this.value = ''; });
    customFileInput.addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        if (file.size > 2 * 1024 * 1024) {
            alert("حجم الصورة كبير جداً! الحد الأقصى هو 2 ميجابايت.");
            return;
        }
        customAvatarFile = file; 
        currentAvatarData = 'custom';
        const reader = new FileReader();
        reader.onload = function(event) {
            mainProfileImg.src = event.target.result;
            removeCustomBtn.style.display = 'flex';
            document.querySelectorAll('.avatar-item').forEach(el => el.classList.remove('selected'));
            closeModal();
        };
        reader.readAsDataURL(file);
    }
});

    removeCustomBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        customAvatarFile = null;
        currentAvatarData = defaultAvatars[0];
        mainProfileImg.setAttribute('src', defaultAvatars[0]);
        document.querySelectorAll('.avatar-item')[0].classList.add('selected');
        removeCustomBtn.style.display = 'none';
        customFileInput.value = ''; 
        closeModal();
    });
    }  // نهاية حارس رفع الصور

    // 5. الإرسال للسيرفر (باستخدام API_URL الديناميكي)
    const profileForm = document.getElementById('profileForm');
    const profileMessage = document.getElementById('profileMessage');

    profileForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const playerName = document.getElementById('playerName').value.trim();
        const playerCountry = document.getElementById('playerCountry').value; 
        const token = sessionStorage.getItem('token');

        // 🛡️ موافقة الشروط إجبارية (مهم قانونياً — خاصة لمستخدمي Google)
        const termsBox = document.getElementById('termsAgree');
        if (termsBox && !termsBox.checked) {
            profileMessage.textContent = "يجب الموافقة على الشروط والأحكام للمتابعة";
            return profileMessage.style.color = "#facc15";
        }

        // تحققات الأمان (Validation)
        if (!token) {
            profileMessage.textContent = "حدث خطأ، يرجى تسجيل الدخول مجدداً.";
            return profileMessage.style.color = "#ff4d4d";
        }
        if (playerName.length < 3 || playerName.length > 15) {
            profileMessage.textContent = "الاسم يجب أن يكون بين 3 و 15 حرفاً ✍️";
            return profileMessage.style.color = "#facc15";
        }
        if (!playerCountry) {
            profileMessage.textContent = "يرجى اختيار بلدك 🌍";
            return profileMessage.style.color = "#facc15";
        }

        const submitBtn = profileForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = "جاري الحفظ...";

        try {
            const formData = new FormData();
            formData.append('token', token); // تأكد من استرجاع التوكن الصحيح
            formData.append('player_name', playerName);
            formData.append('country', playerCountry); 

            // 🚀 السحر هنا: نرسل الملف تحت اسم "avatar_file"، أو النص تحت اسم "avatar_url"
            // (اسم الحقل يجب أن يطابق ما ينتظره الباك في setup-profile endpoint)
            if (typeof customAvatarFile !== 'undefined' && customAvatarFile) {
                formData.append('avatar_file', customAvatarFile); // نرسل الملف للباك اند
            } else {
                formData.append('avatar_url', currentAvatarData); // نرسل المسار (مثل ../assets/...)
            }

            const response = await fetch(`${API_URL}/auth/setup-profile`, {
                method: "POST",
                body: formData
            });
            const data = await response.json();

            if (response.ok) {
                profileMessage.textContent = "تم الحفظ! جاري توجيهك للوبي...";
                profileMessage.style.color = "#00ff88";
                
                const finalAvatar = data.new_avatar || currentAvatarData;

                sessionStorage.setItem('playerName', playerName);
                sessionStorage.setItem('playerAvatar', finalAvatar);
                sessionStorage.setItem('country', playerCountry);

                setTimeout(() => window.location.replace("categories.html"), 800);
            } else {
                profileMessage.textContent = data.detail || "حدث خطأ أثناء الحفظ";
                profileMessage.style.color = "#ff4d4d";
                submitBtn.disabled = false;
                submitBtn.textContent = "دخول للوبي 🚀";
            }
        } catch (error) {
            profileMessage.textContent = "خطأ في الاتصال بالسيرفر";
            profileMessage.style.color = "#ff4d4d";
            submitBtn.disabled = false;
            submitBtn.textContent = "دخول للوبي 🚀";
        }
    });
});

// ==========================================
// 🌍 محرك الدول (النسخة الجميلة - الجميلة والوفلاين!)
// ==========================================

// 1. القائمة المدمجة (سريعة جداً) مع رموز المسارات المحلية
// تأكد من تحميل الصور (SVG) ووضعها في assets/flags/ باسم الرمز (مثال: SA.svg)
const allCountriesData = [
    { name: "السعودية", code: "SA" }, { name: "مصر", code: "EG" },
    { name: "العراق", code: "IQ" }, { name: "اليمن", code: "YE" },
    { name: "سوريا", code: "SY" }, { name: "المغرب", code: "MA" },
    { name: "الجزائر", code: "DZ" }, { name: "السودان", code: "SD" },
    { name: "الأردن", code: "JO" }, { name: "الإمارات", code: "AE" },
    { name: "لبنان", code: "LB" }, { name: "ليبيا", code: "LY" },
    { name: "فلسطين", code: "PS" }, { name: "عمان", code: "OM" },
    { name: "الكويت", code: "KW" }, { name: "تونس", code: "TN" },
    { name: "قطر", code: "QA" }, { name: "البحرين", code: "BH" },
    { name: "موريتانيا", code: "MR" }, { name: "الصومال", code: "SO" },
    { name: "جيبوتي", code: "DJ" }, { name: "تركيا", code: "TR" },
    { name: "عالمي", code: "GL" } // علم عالمي احتياطي
];

const searchInput = document.getElementById('countrySearchInput');
const hiddenCountryInput = document.getElementById('playerCountry');
const dropdown = document.getElementById('countryDropdown');
const countryWrapper = document.getElementById('countryWrapper');

// دالة رسم خيارات الدول
function renderCountryOptions(countries) {
    dropdown.innerHTML = '';
    if(countries.length === 0) {
        dropdown.innerHTML = '<div style="padding:10px;color:#bbb;text-align:center;">لا توجد نتائج 🧐</div>';
        return;
    }

    countries.forEach(c => {
        const item = document.createElement('div');
        item.className = 'dropdown-item';
        
        // 🚀 السحر هنا: قمنا بتضمين علامة <img> تشير للمجلد المحلي
        item.innerHTML = `
            <img src="../assets/flags/${c.code}.svg" 
                 alt="${c.name} flag" 
                 style="width: 28px; height: auto; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.2); margin-left: 10px;"
                 onerror="this.style.display='none';"> <span>${c.name}</span>
        `;
        
        item.onclick = () => {
            searchInput.value = `${c.name}`; 
            hiddenCountryInput.value = `${c.code}`; // نرسل الرمز فقط للباك اند (SA) لسهولة جلب الصورة هناك
            dropdown.style.display = 'none'; 
            searchInput.style.borderColor = "rgba(255,255,255,0.2)"; 
        };
        dropdown.appendChild(item);
    });
}

// إظهار القائمة عند النقر
searchInput.addEventListener('focus', () => {
    dropdown.style.display = 'block';
    renderCountryOptions(allCountriesData); // عرض الكل في البداية
});

// فلترة البحث
searchInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    // فلترة بناءً على الاسم (يمن، سعودية...)
    const filtered = allCountriesData.filter(c => c.name.includes(val));
    renderCountryOptions(filtered);
    hiddenCountryInput.value = ""; 
});

// إخفاء القائمة عند الضغط خارجها
document.addEventListener('click', (e) => {
    if (!countryWrapper.contains(e.target)) {
        dropdown.style.display = 'none';
    }
});

// افترض أن لديك زر في الـ HTML يحمل الآي دي cancelRegistrationBtn
const cancelBtn = document.getElementById('cancelRegistrationBtn');
if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
        if (!confirm('هل أنت متأكد أنك تريد إلغاء التسجيل وحذف الحساب؟')) return;

        try {
            const response = await fetch(`${API_URL}/auth/cancel-registration`, {
                method: "DELETE",
                headers: {
                    'Authorization': `Bearer ${sessionStorage.getItem('token')}`
                }
            });

            if (response.ok) {
                // مسح البيانات من المتصفح والعودة لتسجيل الدخول
                sessionStorage.clear();
                localStorage.clear();
                window.location.replace("login.html");
            }
        } catch (error) {
            console.error("خطأ في الاتصال");
        }
    });
}