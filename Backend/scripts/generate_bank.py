import asyncio
import json
import os
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from Backend.app.core.database import engine, Question, Base

load_dotenv()

GAMES_TARGETS = {
    "huroof": 5,  
    "bank": 50,   
    "career": 30, 
    "whoami": 30, 
    "whatdo": 20
}

ARABIC_LETTERS = list('أبتثجحخدذرزسشصضطظعغفقكلمنهوي')
TOPICS = ['إسلاميات وسيرة نبوية', 'ألغاز وفوازير ذكية', 'تاريخ', 'جغرافيا', 'علوم', 'ثقافة عامة', 'رياضة']

db_lock = asyncio.Lock()

def save_question_to_db(game_mode, q_text, answer, category, extra_data_dict):
    db = Session(bind=engine)
    try:
        exists = db.query(Question).filter(
            Question.game_mode == game_mode,
            Question.correct_answer == answer
        ).first()
        
        if not exists:
            new_q = Question(
                game_mode=game_mode,
                question_text=q_text,
                correct_answer=answer,
                category=category,
                extra_data=json.dumps(extra_data_dict, ensure_ascii=False)
            )
            db.add(new_q)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        return False
    finally:
        db.close()

async def generate_question(client, game_mode, extra_param, topic, retry_count=0):
    if game_mode == "huroof":
        prompt = (
            f"قم بتوليد سؤال مسابقات إجابته عبارة عن (كلمة واحدة فقط) تبدأ بحرف '{extra_param}' في مجال ({topic}).\n"
            f"🚨 شرط حاسم جداً: الإجابة (answer) يجب أن تبدأ بحرف '{extra_param}' حصراً.\n"
            f"🎯 هام جداً: قم بتوليد مصفوفة 'accepted_answers' تحتوي على مرادفات للإجابة تبدأ بحرف '{extra_param}'.\n"
            "الرد بصيغة JSON:\n"
            "{\"verification\": \"شرح\", \"question\": \"السؤال\", \"answer\": \"الإجابة\", \"accepted_answers\": [\"مرادف1\"], \"category\": \"التصنيف\"}"
        )
    elif game_mode == "bank":
        prompt = f"قم بتوليد سؤال مسابقات (خيارات متعددة) في مجال ({topic}). الرد JSON: {{\"verification\": \"شرح\", \"question\": \"السؤال\", \"answer\": \"الصحيحة\", \"wrong_options\": [\"خطأ1\", \"خطأ2\", \"خطأ3\"], \"category\": \"التصنيف\"}}"
    elif game_mode == "career":
        prompt = "قم باختيار شخصية مشهورة (لاعب، عالم، قائد)، واكتب مسيرته بالترتيب. الرد JSON: {{\"verification\": \"شرح\", \"question\": \"من هو؟\", \"answer\": \"الاسم\", \"clubs\": [\"المحطة الأولى\", \"الثانية\"], \"category\": \"شخصيات\"}}"
    elif game_mode == "whoami":
        prompt = f"اختر شخصية أو شيئاً في مجال ({topic}) واكتب 4 تلميحات متدرجة. الرد JSON: {{\"verification\": \"شرح\", \"question\": \"من أنا؟\", \"answer\": \"الاسم\", \"hints\": [\"صعب\", \"متوسط\", \"أسهل\", \"واضح\"], \"category\": \"التصنيف\"}}"
    elif game_mode == "whatdo":
        prompt = f"اختر فئة في مجال ({topic}) واذكر 10 إجابات تنتمي لها. الرد JSON: {{\"verification\": \"شرح\", \"question\": \"اذكر أشياء تنتمي إلى: [الفئة]\", \"answer\": \"[الفئة]\", \"valid_answers\": [\"1\", \"2\"...], \"category\": \"التصنيف\"}}"

    hard_letters = ['ظ', 'ض', 'ذ', 'ث', 'غ', 'خ', 'ز']
    if game_mode == "huroof" and extra_param in hard_letters:
        prompt += f"\n💡 ملاحظة: حرف '{extra_param}' نادر. يُسمح بمصطلحات صعبة."

    prompt += "\n--- تحذير ---\nيُمنع التأليف في الدين، إذا شككت بنسبة 1%، اختر سؤالاً ثقافياً."

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3)
        )
        
        text = response.text.strip()
        start_idx, end_idx = text.find('{'), text.rfind('}')
        if start_idx != -1 and end_idx != -1: text = text[start_idx:end_idx+1]
            
        data = json.loads(text)
        q_text, answer, category = data.get('question', '').strip(), data.get('answer', '').strip(), data.get('category', topic).strip()
        
        if game_mode == "huroof" and answer and not answer.startswith(extra_param):
            return f"❌ مرفوض (هلوسة حرف): طلبنا '{extra_param}' وأعطانا '{answer}'"

        extra_data = {}
        if game_mode == "huroof": extra_data.update({"letter": extra_param, "accepted_answers": data.get('accepted_answers', [])})
        elif game_mode == "bank": extra_data["wrong_options"] = data.get('wrong_options', [])
        elif game_mode == "career": extra_data["clubs"] = data.get('clubs', [])
        elif game_mode == "whoami": extra_data["hints"] = data.get('hints', [])
        elif game_mode == "whatdo": extra_data["valid_answers"] = data.get('valid_answers', [])

        if q_text and answer:
            async with db_lock:
                saved = await asyncio.to_thread(save_question_to_db, game_mode, q_text, answer, category, extra_data)
            return f"✅ [{game_mode} | {topic}] أضيف: {answer}" if saved else f"⚠️ مكرر أو خطأ حفظ: {answer}"
            
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            if retry_count < 3:
                wait_time = 20 * (retry_count + 1)
                print(f"    ⏸️ تم حظرنا مؤقتاً. سننتظر {wait_time} ثانية ثم نحاول مجدداً...")
                await asyncio.sleep(wait_time)
                return await generate_question(client, game_mode, extra_param, topic, retry_count + 1)
            else:
                return "🛑 خطأ 429: تم الاستسلام بعد 3 محاولات."
        return f"❌ خطأ غير متوقع: {e}"
    
    return None

async def fill_game_mode(client, game_mode, target):
    print(f"\n🚀 جاري توليد أسئلة للعبة: {game_mode.upper()}...")
    
    if game_mode == "huroof":
        for letter in ARABIC_LETTERS:
            print(f"  ⏳ جاري توليد {target} أسئلة لحرف: {letter}")
            # التعديل الجذري: توليد الأسئلة واحد تلو الآخر (نظام الطابور)
            for _ in range(target):
                res = await generate_question(client, game_mode, letter, random.choice(TOPICS))
                if res: print("    " + res)
                await asyncio.sleep(5) # راحة 5 ثوانٍ بعد كل سؤال لضمان عدم تخطي 12 طلب في الدقيقة!
    else:
        for _ in range(target):
            res = await generate_question(client, game_mode, None, random.choice(TOPICS))
            if res: print("  " + res)
            await asyncio.sleep(5) # راحة 5 ثوانٍ

async def main():
    print("=" * 60)
    print("🤖 مولّد بنك الأسئلة (نظام الطابور الآمن - 100% بدون حظر)")
    print("=" * 60)
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    for game, target in GAMES_TARGETS.items():
        await fill_game_mode(client, game, target)
        
    print("\n" + "=" * 60)
    print("🎉 اكتمل بناء البنك بنجاح!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())