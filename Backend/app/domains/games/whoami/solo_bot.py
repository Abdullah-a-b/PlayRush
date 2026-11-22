"""مصنف شخصيات خفيف يتعلم أوزان المفردات من ملفات تعريف مستقلة عن تلميحات المباراة."""
import math
import random
from app.domains.games.recall_calibration import calibrated
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

# المعرفة التدريبية: شخصية ومفاهيم مرتبطة بها. نصوص الأسئلة ليست مدخل تدريب.
PROFILES = """
einstein|النسبية العامة النسبية الخاصة تكافؤ الطاقة والكتلة الضوء الفيزياء الكهروضوئية براءات الاختراع سويسرا نوبل عالم ألماني
newton|الجاذبية التفاحة قوانين الحركة القوة تسارع منشور ضوئي لون الطيف تحليل الضوء التفاضل إنجلترا سك العملة
curie|البولونيوم الراديوم النشاط الإشعاعي إشعاع مختبر بيير نوبل الفيزياء الكيمياء وارسو باريس
tesla|التيار المتناوب التيارات الكهرباء المحرك الكهربائي ملف تسلا إديسون نياجرا
edison|المصباح الكهربائي الفونوغراف تسجيل الصوت مينلو بارك الاختراع الصحف قطارات التيار المستمر
davinci|الموناليزا العشاء الأخير الرسم الفنان الإيطالي فلورنسا تشريح آلات طائرة الكتابة المعكوسة
khwarizmi|الجبر المقابلة الأرقام الخوارزميات بيت الحكمة بغداد حساب رياضيات
ibnsina|القانون في الطب الفلسفة الشفاء الطبيب الشيخ الرئيس بخارى
jabir|الكيمياء التقطير مختبر الكوفة معادن تجارب
ibnkhaldun|المقدمة العصبية العمران الاجتماع تونس الدول تيمورلنك
ibnbattuta|طنجة الرحلة رحالة الحج الهند قاضي المالديف تحفة النظار
zewail|الفيمتوثانية الليزر تفاعل كيميائي نوبل كيمياء مصر كاليفورنيا دمنهور
yacoub|جراح القلب زراعة القلوب أسوان بريطانيا مصر صمامات الطب
mahfouz|الثلاثية بين القصرين القاهرة الحارة المصرية روايات نوبل الأدب السكرية
mutanabbi|الشعر قصائد سيف الدولة حلب الحمداني مدح كافور الكوفة الخيل الليل البيداء
jobs|أبل آيفون ماكنتوش بيكسار تصميم الحاسوب ووزنياك أجهزة شخصية
gates|مايكروسوفت ويندوز البرمجيات الحاسوب بيل بول ألين هارفارد سياتل
bell|الهاتف الصوت الكلام تعليم الصم الاتصالات براءة اختراع
messi|برشلونة الأرجنتين روساريو لاماسيا كأس العالم قطر إنتر ميامي الكرة الذهبية
ronaldo|البرتغال ماديرا سبورتينغ لشبونة مانشستر يونايتد ريال مدريد النصر هداف
pele|البرازيل سانتوس ثلاثة كؤوس العالم سبعة عشر عاما الجوهرة السوداء
maradona|الأرجنتين نابولي المكسيك إنجلترا يد الله بوينس آيرس مونديال
zidane|فرنسا مرسيليا الجزائر يوفنتوس ريال مدريد نهائي 1998 رأسية
salah|ليفربول روما تشيلسي بازل مصر المقاولون العرب الدوري الإنجليزي الفرعون
fairuz|لبنان بيروت بعلبك الرحابنة الأخوان رحباني نهاد حداد نسم علينا الهوى زهرة المدائن القدس
umm_kulthum|مصر كوكب الشرق الأطلال السنباطي عبد الوهاب أنت عمري حفل الخميس الراديو
amr_diab|الهضبة بورسعيد تملي معاك نور العين البوب الغناء المصري
kadhim|قيصر الأغنية العراقية العراق نزار قباني زيديني عشقا بغداد ألحان
adel_imam|الزعيم بهجت الأباصيري مدرسة المشاغبين الإرهاب والكباب مسرح كوميديا مصر
ahmed_helmy|عسل أسود كده رضا مطب صناعي زكي شان لعب عيال كوميديا أطفال مصري
jackie|هونغ كونغ كونغ فو فنون قتالية مشاهد خطرة كريس تاكر Rush Hour المعلم السكران
chaplin|الصعلوك السينما الصامتة العصا القبعة الشارب الكوميديا الأزمنة الحديثة
waltdisney|الرسوم المتحركة ميكي ماوس روي ديزني لاند سنو وايت الأقزام أنهايم
stanlee|مارفل قصص مصورة الرجل العنكبوت أبطال خارقون إكسلسيور سبايدر مان
rowan|مستر بين جوني إنجلش ميني دب دمية كوميديا بريطانية هندسة كهربائية
zuckerberg|فيسبوك ميتا إنستغرام واتساب هارفارد التواصل الاجتماعي شبكة اجتماعية
"""

LEVELS = {
    'beginner': (.34, .40, 4.4),
    'medium': (.50, .32, 3.5),
    'hard': (.65, .25, 2.8),
    'expert': (.79, .20, 2.2),
}


def features(text):
    text = re.sub(r'[\u064b-\u065fـ]', '', text.lower()).translate(str.maketrans('أإآىة', 'ااايه'))
    terms = Counter()
    for word in re.findall(r'[\w]+', text):
        word = re.sub(r'^(?:وال|بال|لل|ال)', '', word)
        if len(word) < 3:
            continue
        terms[word] += 2
        for i in range(len(word)-2):
            terms['#'+word[i:i+3]] += .35
    return terms


@lru_cache(maxsize=1)
def fit():
    profiles = dict(line.split('|', 1) for line in PROFILES.strip().splitlines())
    docs = {key: features(text) for key, text in profiles.items()}
    freq = Counter(term for doc in docs.values() for term in doc)
    idf = {term: 1 + math.log((1+len(docs))/(1+count)) for term,count in freq.items()}
    vectors = {}
    for key, doc in docs.items():
        vec = {t: n*idf[t] for t,n in doc.items()}
        norm = math.sqrt(sum(v*v for v in vec.values()))
        vectors[key] = {t:v/norm for t,v in vec.items()}
    return vectors,idf


def rank(hints, candidates):
    vectors,idf = fit()
    scores = Counter()
    for hint in hints:
        vec = {t:n*idf[t] for t,n in features(hint).items() if t in idf}
        norm = math.sqrt(sum(v*v for v in vec.values()))
        if norm:
            for key in candidates:
                if key in vectors:
                    scores[key] += sum(v*vectors[key].get(t,0) for t,v in vec.items())/norm
    return scores.most_common()


def decide(hints, candidates, level, attempted, rng=random):
    ranked = [(k,s) for k,s in rank(hints,candidates) if k not in attempted]
    if not ranked:
        return None
    recall, threshold, delay = LEVELS[level]
    best,score = ranked[0]
    runner = ranked[1][1] if len(ranked)>1 else 0
    evidence = score - .65*runner
    if evidence < threshold or rng.random() > calibrated("whoami", level, recall * min(1, evidence/(threshold*2))):
        return None
    return best, rng.uniform(delay, delay+1.8)
