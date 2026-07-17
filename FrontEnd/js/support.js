// ============================================================
//  صفحة الدعم — FAQ + تذاكر + تواصل
// ============================================================
const API = (typeof CONFIG !== 'undefined' && CONFIG.API_URL) ? CONFIG.API_URL : 'http://127.0.0.1:8000';
const token = (typeof getToken === 'function') ? getToken() : (localStorage.getItem('token') || sessionStorage.getItem('token'));

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

// ---------- التبويبات ----------
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'mine') loadMyTickets();
  });
});

// ---------- FAQ ----------
const FAQ = [
  {
    q: 'لماذا تم حظر حسابي وكيف أستعيده؟',
    a: 'يُحظر الحساب عند مخالفة سياسات اللعب العادل (الغش، محاولات الوصول لأدوات المطور، أو الإساءة). إذا كنت تعتقد أن الحظر بالخطأ، أرسل تذكرة من نوع "مراجعة حظر" وسنراجع حالتك.'
  },
  {
    q: 'كيف أغيّر اسم اللاعب أو الصورة الرمزية؟',
    a: 'من صفحة اللوبي، افتح الإعدادات (أيقونة الترس)، ثم بطاقة "الملف الشخصي"، وعدّل اسمك أو صورتك الرمزية من هناك.'
  },
  {
    q: 'لماذا لا يجد البحث عن مباراة خصماً؟',
    a: 'يحتاج البحث وجود لاعب آخر يبحث في نفس اللعبة. كما أن النظام يمنع مطابقتك مع نفس الخصم بشكل متكرر خلال فترة قصيرة لضمان التنوع.'
  },
  {
    q: 'لماذا حصلت على حظر مؤقت من البحث؟',
    a: 'الانسحاب المتكرر من المباريات يؤدي لحظر مؤقت متصاعد يبدأ بتحذير. أكمل مبارياتك دون انسحاب لاستعادة وضعك الطبيعي.'
  },
  {
    q: 'كيف أبلّغ عن لاعب مسيء؟',
    a: 'أثناء المباراة، اضغط على بطاقة الخصم في الأعلى ثم زر "إبلاغ"، واختر السبب المناسب. البلاغات تُراجَع والمخالفون يُعاقَبون تلقائياً.'
  },
  {
    q: 'كيف يعمل نظام النقاط والجوائز؟',
    a: 'تكسب XP وعملات عند الفوز. الفوز الأول يومياً يمنح مكافأة إضافية. اللعب المتكرر مع نفس الخصم يقلّل الجوائز لمنع التلاعب.'
  },
];

function renderFAQ() {
  const list = document.getElementById('faqList');
  list.innerHTML = FAQ.map((f, i) => `
    <div class="faq-item" data-i="${i}">
      <div class="faq-q">${esc(f.q)} <i class="fa-solid fa-chevron-down"></i></div>
      <div class="faq-a">${esc(f.a)}</div>
    </div>`).join('');
  list.querySelectorAll('.faq-q').forEach(q => {
    q.addEventListener('click', () => q.parentElement.classList.toggle('open'));
  });
}
renderFAQ();

// ---------- روابط التواصل (تُقرأ من SOCIAL_LINKS في config.js) ----------
(function setupSocial() {
  var grid = document.getElementById('socialGrid');
  if (!grid) return;
  var links = (typeof SOCIAL_LINKS !== 'undefined') ? SOCIAL_LINKS : {};
  var PLATFORMS = [
    { key: 'twitter',   icon: 'fa-x-twitter',  label: 'X',        color: '#ffffff' },
    { key: 'instagram', icon: 'fa-instagram',  label: 'إنستغرام', color: '#e1306c' },
    { key: 'tiktok',    icon: 'fa-tiktok',     label: 'تيك توك',  color: '#00f2ea' },
    { key: 'snapchat',  icon: 'fa-snapchat',   label: 'سناب شات', color: '#f5d90a' },
    { key: 'threads',   icon: 'fa-threads',    label: 'ثريدز',    color: '#ffffff' },
    { key: 'facebook',  icon: 'fa-facebook-f', label: 'فيسبوك',   color: '#1877f2' },
  ];
  var any = false;
  PLATFORMS.forEach(function (p) {
    var url = links[p.key];
    if (!url || String(url).trim() === '') return;
    any = true;
    var a = document.createElement('a');
    a.className = 'social-tile';
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.style.setProperty('--sc', p.color);
    a.innerHTML = '<i class="fa-brands ' + p.icon + '"></i><span>' + p.label + '</span>';
    grid.appendChild(a);
  });
  if (!any) {
    grid.innerHTML = '<p style="color:#888;font-size:13px;">حساباتنا قريباً…</p>';
  }
})();

// ---------- إرسال تذكرة ----------
const submitBtn = document.getElementById('submitTicket');
const formMsg = document.getElementById('formMsg');

submitBtn.addEventListener('click', async () => {
  const category = document.getElementById('ticketCategory').value;
  const subject = document.getElementById('ticketSubject').value.trim();
  const message = document.getElementById('ticketMessage').value.trim();

  formMsg.className = 'form-msg';
  if (message.length < 5) {
    formMsg.className = 'form-msg err';
    formMsg.textContent = 'الرجاء كتابة وصف أوضح للمشكلة';
    return;
  }
  if (!token) {
    formMsg.className = 'form-msg err';
    formMsg.textContent = 'يجب تسجيل الدخول لإرسال تذكرة';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'جارٍ الإرسال...';
  try {
    const res = await fetch(API + '/support/ticket', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ category, subject, message }),
    });
    const data = await res.json();
    if (data.ok) {
      formMsg.className = 'form-msg ok';
      formMsg.textContent = '✅ ' + data.msg;
      document.getElementById('ticketSubject').value = '';
      document.getElementById('ticketMessage').value = '';
    } else {
      formMsg.className = 'form-msg err';
      formMsg.textContent = '⚠️ ' + (data.msg || 'تعذّر الإرسال');
    }
  } catch (e) {
    formMsg.className = 'form-msg err';
    formMsg.textContent = 'تعذّر الاتصال بالخادم';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'إرسال التذكرة';
  }
});

// ---------- تذاكري ----------
const STATUS_LABEL = { open: 'مفتوحة', in_progress: 'قيد المعالجة', closed: 'مغلقة' };

async function loadMyTickets() {
  const list = document.getElementById('ticketsList');
  if (!token) { list.innerHTML = '<div class="empty">سجّل الدخول لعرض تذاكرك</div>'; return; }
  list.innerHTML = '<div class="empty">جارٍ التحميل...</div>';
  try {
    const res = await fetch(API + '/support/my-tickets', {
      headers: { 'Authorization': 'Bearer ' + token },
    });
    const data = await res.json();
    const tickets = data.tickets || [];
    if (tickets.length === 0) {
      list.innerHTML = '<div class="empty">لا توجد تذاكر بعد</div>';
      return;
    }
    list.innerHTML = tickets.map(t => `
      <div class="ticket">
        <div class="ticket-head">
          <span class="ticket-cat">#${t.id} · ${esc(t.category_label)}</span>
          <span class="status-badge status-${t.status}">${STATUS_LABEL[t.status] || t.status}</span>
        </div>
        ${t.subject ? `<div class="ticket-subject">${esc(t.subject)}</div>` : ''}
        <div class="ticket-msg">${esc(t.message)}</div>
        ${t.admin_reply ? `<div class="ticket-reply"><strong>رد الدعم:</strong> ${esc(t.admin_reply)}</div>` : ''}
      </div>`).join('');
  } catch (e) {
    list.innerHTML = '<div class="empty">تعذّر تحميل التذاكر</div>';
  }
}
