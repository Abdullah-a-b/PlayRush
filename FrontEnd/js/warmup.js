(() => {
  const stage = document.getElementById('rushWarmup');
  if (!stage || !window.PR_IS_APP) return;
  const rounds = [
    ['حرف «ن» · أيّهما آلة موسيقية؟','ناي','نرد'],
    ['من أنا؟ · لي مفاتيح وأوتار ومطارق صغيرة','بيانو','عود'],
    ['مسيرة لاعب · سانتوس ثم نيويورك كوسموس','بيليه','كاكا'],
    ['ماذا تعرف · أيّهما من الثدييات؟','دلفين','قرش'],
    ['البنك · كم ضلعًا للمسدّس؟','ستة','ثمانية'],
    ['حرف «ب» · ما الذي يشير إلى الشمال المغناطيسي؟','بوصلة','بارومتر'],
    ['مسيرة لاعب · أيّهما لعب لبرشلونة وريال مدريد؟','لويس فيغو','تشافي'],
    ['من أنا؟ · أدور حول الأرض مرة كل شهر تقريبًا','القمر','المريخ'],
    ['ماذا تعرف · أيّهما رياضة أولمبية مائية؟','الغطس','التزلج الفني'],
    ['البنك · ما نصف ثلاثة أرباع؟','ثلاثة أثمان','ثلث'],
  ];
  const choices = document.getElementById('warmChoices');
  const result = document.getElementById('warmResult');
  let last = -1;
  try { last = Number(localStorage.getItem('pr_warmup_last') ?? -1); } catch {}
  function deal() {
    const pick = (last + 1 + Math.floor(Math.random() * (rounds.length - 1))) % rounds.length;
    last = pick;
    try { localStorage.setItem('pr_warmup_last', String(pick)); } catch {}
    const [prompt, correct, other] = rounds[pick];
    document.getElementById('warmPrompt').textContent = prompt;
    result.textContent = '';
    choices.replaceChildren();
    const answers = Math.random() < .5 ? [correct, other] : [other, correct];
    for (const answer of answers) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = answer;
      button.onclick = () => {
        for (const choice of choices.children) {
          choice.disabled = true;
          choice.classList.toggle('warm-correct', choice.textContent === correct);
        }
        result.textContent = answer === correct ? 'إجابة صحيحة!' : 'الإجابة الصحيحة: ' + correct;
      };
      choices.append(button);
    }
  }
  stage.hidden = false;
  deal();
})();
