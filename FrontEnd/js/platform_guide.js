/* ============================================================
   platform_guide.js — دليل المنصة الشامل (نافذة كاملة)
   الهوية · الاقتصاد (عملتان) · الرتب والمواسم · المهام · البطاقة.
   ============================================================ */
(function () {
  'use strict';

  var GUIDE = [
    {
      id: 'identity', icon: '🎮', title: 'ما هي المنصة؟',
      blocks: [
        ['PlayRush', 'منصة ألعاب عربية تنافسية معرفية — تُقاس فيها المهارة والمعرفة الحقيقية، لا الحظ ولا المال. خمس ألعاب متنوعة، مباريات مباشرة بين لاعبين، ونظام تقدّم موسمي يكافئ المثابرة والذكاء.'],
        ['الألعاب الخمس', 'خلية الحروف (شبكة سداسية وأسئلة سريعة)، البنك (مراكمة رصيد ومخاطرة)، مسيرة لاعب (تخمين كرة القدم من الأندية)، ماذا تعرف (سرد إجابات بالتناوب)، ومن أنا (كشف شخصية من التلميحات).'],
        ['مبدأنا: Win to Play', 'الفوز بالمهارة والمثابرة — لا بالدفع. كل ما يؤثر في المباراة يُكتسب باللعب. لا شيء تشتريه بالمال يمنحك أفضلية تنافسية. اللعب العادل ضمانة، لا شعار.'],
      ],
    },
    {
      id: 'economy', icon: '💰', title: 'الاقتصاد: عملتان منفصلتان',
      blocks: [
        ['🪙 الكوينز', 'عملة اللعب اليومية — تكسبها من كل مباراة (فوزاً أو خسارة) ومن المهام. تنفقها على المساعدات والعبارات والأفاتارات. وفيرة نسبياً، وهي وقود تطوّرك التكتيكي.'],
        ['💎 الجواهر', 'عملة نادرة ومحمية — لا تأتي من المباريات أبداً. مصادرها: ترقية مستواك (جوهرة لكل مستوى)، عبور حواجز الرتب (برونزي ← فضي ← ذهبي…)، المهام الأسبوعية والموسمية، والبطاقة الموسمية. تُنفَق على التجميل النادر والبطاقة الموسمية فقط.'],
        ['فصل تام', 'لا تحويل بين العملتين بأي اتجاه. الجواهر لا تُشترى بكوينز، والكوينز لا تُشترى بجواهر. هذا الفصل يحمي ندرة الجواهر ونزاهة التنافس.'],
        ['المستوى منفصل عن الرتبة', 'مستواك (XP) يقيس مثابرتك ويفتح المساعدات في المتجر. رتبتك (Elo) تقيس مهارتك الخالصة. الاثنان لا يُشتريان ولا يتحوّل أحدهما للآخر.'],
      ],
    },
    {
      id: 'rank', icon: '🏅', title: 'نظام الرتب والمواسم',
      blocks: [
        ['رتبة لكل لعبة', 'لكل لعبة رتبتها المستقلة المبنية على نظام Elo العالمي. الفوز على أقوى منك يرفعك أكثر، والخسارة أمام أضعف تكلّفك أكثر — مهارتك الحقيقية تظهر بوضوح.'],
        ['المجموعات والدرجات', 'خمس مجموعات: برونزي ← فضي ← ذهبي ← بلاتيني ← نخبة. كل مجموعة ثلاث درجات (III ← II ← I). تبدأ من برونزي وتصعد بالفوز. عبور كل مجموعة جديدة يمنحك جواهر.'],
        ['هامش الفوز في حروف', 'في خلية الحروف الفوز الكاسح (2-0) يرفع تصنيفك أكثر من الفوز القريب (2-1) — والخسارة القريبة أرحم من الكاسحة. كل جولة تُحسب.'],
        ['المواسم الشهرية', 'يبدأ كل موسم الخميس الثالث من الشهر. مع نهايته تُعاد الرتبة ضبطاً ناعماً (تنحدر نحو المنتصف مع حفظ نصف فارقك) — فالنخبة يبدأ أعلى ويستعيد رتبته بسرعة، والجميع يخوض تسلّقاً جديداً. البطاقة الموسمية تُعاد أيضاً مع كل موسم.'],
        ['الصدارة', 'لكل لعبة صدارتان في لوبيها: التصنيف (بالـElo) والانتصارات (وعند التعادل صاحب المباريات الأقل يتقدّم — كفاءة أعلى). وفي هذه الصفحة صدارة عامة بمتوسط تصنيفك عبر الألعاب لمن لعب ثلاث ألعاب فأكثر.'],
      ],
    },
    {
      id: 'quests', icon: '📋', title: 'المهام',
      blocks: [
        ['يومية', 'ثلاث مهام تتجدّد كل يوم. تمنح كوينز وخبرة ونقاط بطاقة — دفعة تقدّم سريعة لكل جلسة لعب.'],
        ['أسبوعية', 'ثلاث مهام أكبر تتجدّد كل أسبوع، تضيف الجواهر إلى مكافآتها — تكافئ الالتزام المنتظم.'],
        ['موسمية', 'أربع مهام كبرى تدوم الموسم كامل بأضخم الجوائز (جواهر عالية ونقاط بطاقة كبيرة) — أهداف طويلة المدى للمثابرين.'],
      ],
    },
    {
      id: 'pass', icon: '🎟️', title: 'البطاقة الموسمية',
      blocks: [
        ['كيف تعمل', 'ثلاثون محطة تُفتح بجمع «نقاط البطاقة» من اللعب والمهام. نقاط البطاقة منفصلة تماماً عن مستواك ورتبتك — مسار تقدّم ثالث خاص بالموسم.'],
        ['مساران', 'المسار المجاني للجميع بجوائز كوينز وجواهر. ومسار Premium يُفتح بالجواهر مرة واحدة في الموسم، بجوائز أغنى وتجميل حصري.'],
        ['يموّل نفسه', 'مسار Premium يعيد إليك جواهر أكثر مما دفعت عبر محطاته — فمن يشتريه ويكمله يخرج رابحاً. نموذج مبني على المكافأة لا على الاستنزاف.'],
      ],
    },
    {
      id: 'fair', icon: '⚖️', title: 'اللعب النظيف',
      blocks: [
        ['تحكيم ذكي للإجابات', 'نظام من أربع طبقات يفهم إجاباتك: تطبيع النص، التشابه الذكي، تحليل الكلمات، ثم حكم ذكي للحالات الحدّية — وعند أي شك تُحسب الإجابة لصالحك.'],
        ['حماية التنافس', 'أنظمة تكافح الغش والتواطؤ، وعقوبات تصاعدية للانسحاب المتكرر. المباراة العادلة حق لكل لاعب.'],
        ['العبارات الجاهزة', 'التفاعل داخل المباراة عبر عبارات وإيموجي معتمدة — تواصل حيّ وخالٍ من الإساءة. (الدردشة الحرة قادمة قريباً مع الإشراف المناسب.)'],
      ],
    },
  ];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function close() {
    var o = document.getElementById('pgOverlay');
    if (o) { o.classList.remove('open'); setTimeout(function () { o.remove(); }, 220); }
  }

  window.openPlatformGuide = function () {
    close();
    var overlay = document.createElement('div');
    overlay.className = 'pg-overlay'; overlay.id = 'pgOverlay';

    var nav = GUIDE.map(function (s, i) {
      return '<button class="pg-nav-btn' + (i === 0 ? ' active' : '') +
        '" data-target="pg-sec-' + s.id + '">' + s.icon + ' ' + esc(s.title) + '</button>';
    }).join('');

    var sections = GUIDE.map(function (s) {
      var body = s.blocks.map(function (b) {
        return '<div class="pg-block"><h4>' + esc(b[0]) + '</h4><p>' + esc(b[1]) + '</p></div>';
      }).join('');
      return '<div class="pg-section" id="pg-sec-' + s.id + '">' +
        '<h3><span class="pg-sec-icon">' + s.icon + '</span> ' + esc(s.title) + '</h3>' +
        body + '</div>';
    }).join('');

    overlay.innerHTML =
      '<div class="pg-modal">' +
        '<div class="pg-head">' +
          '<h2><i class="fa-solid fa-book-open"></i> دليل المنصة</h2>' +
          '<button class="pg-close" id="pgClose"><i class="fa-solid fa-xmark"></i></button>' +
        '</div>' +
        '<div class="pg-body">' +
          '<div class="pg-nav">' + nav + '</div>' +
          '<div class="pg-content">' + sections + '</div>' +
        '</div>' +
      '</div>';

    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.body.appendChild(overlay);
    requestAnimationFrame(function () { overlay.classList.add('open'); });

    document.getElementById('pgClose').addEventListener('click', close);

    var content = overlay.querySelector('.pg-content');
    overlay.querySelectorAll('.pg-nav-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        overlay.querySelectorAll('.pg-nav-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var tgt = document.getElementById(btn.dataset.target);
        if (tgt) content.scrollTo({ top: tgt.offsetTop - 10, behavior: 'smooth' });
      });
    });
    // تمييز القسم المرئي أثناء التمرير
    content.addEventListener('scroll', function () {
      var secs = overlay.querySelectorAll('.pg-section');
      var active = null;
      secs.forEach(function (sec) {
        if (sec.offsetTop - 60 <= content.scrollTop) active = sec.id;
      });
      if (active) {
        overlay.querySelectorAll('.pg-nav-btn').forEach(function (b) {
          b.classList.toggle('active', b.dataset.target === active);
        });
      }
    });
  };
})();
