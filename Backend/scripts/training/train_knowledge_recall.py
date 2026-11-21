from pathlib import Path
import json, math, random
ROOT = Path(__file__).resolve().parents[2]
questions = json.loads((ROOT / 'data/knowledge_questions.json').read_text('utf8'))['questions']
sizes = [len(q['answers']) for q in questions if q.get('active', True) and len(q.get('answers', [])) >= 15 and q['id'] != 'kq_world_currencies']
rng = random.Random(20261121)
rng.shuffle(sizes)
cut = max(1, int(.8 * len(sizes)))
model = {}
for level, recall in [('beginner', .54), ('medium', .72), ('hard', .85), ('expert', .94)]:
    weights = [0., 0., 0.]
    def sample(bank):
        size = rng.choice(bank)
        used = rng.randrange(size)
        # محاكاة استرجاع عدد محدود من الأسماء تحت الضغط، مع تداخل الإجابات المستعملة.
        pressure = used / size
        remembered = rng.random() < recall and any(rng.randrange(size) >= used for _ in range(1 + int(4 * recall)))
        return (1., pressure, pressure ** 2), int(remembered)
    def predict(x):
        return 1 / (1 + math.exp(-sum(a*b for a,b in zip(weights,x))))
    for step in range(100000):
        x,y = sample(sizes[:cut])
        error = y - predict(x)
        for i in range(3):
            weights[i] += .05 / (1 + step / 10000) * error * x[i]
    model[level] = weights
    cases = [sample(sizes[cut:]) for _ in range(20000)]
    print(level, 'predicted/target recall', round(sum(predict(x) for x,y in cases)/len(cases),3), round(sum(y for x,y in cases)/len(cases),3))
(ROOT / 'app/domains/games/knowledge/recall_weights.json').write_text(json.dumps(model, indent=2)+'\n', encoding='utf8')
