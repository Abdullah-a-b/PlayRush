"""تطبيق مراجعة محتوى الألعاب فقط بعد فحص القيم القديمة؛ المعاينة هي الافتراضي.
python scripts/apply_game_content_review.py plan.json [--apply]
لا يقرأ حسابات المستخدمين أو المباريات، ولا يحذف سجلات.
"""
import argparse
from contextlib import ExitStack
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from app.core.paths import DATA_DIR
from app.core.import_support import atomic_json, import_lock

FILES = {'bank': ('bank_questions.json', None), 'bank_auto': ('bank_questions_auto.json', None), 'whoami': ('whoami_characters.json', 'characters'), 'knowledge': ('knowledge_questions.json', 'questions')}
TABLES = {'career': ('career_players', {'name','status','clubs','accepted_answers','difficulty','nationality','era','position','active','wikidata_id'}), 'huroof': ('questions', {'question_text','correct_answer','category','extra_data'})}
LOCKS = ['bank_import_state.json','career_import_state.json','huroof_import_state.json','knowledge_import_state.json','whoami_import_state.json']


def expected_interim(change):
    """الشكل الوحيد المقبول للعزل الإسعافي الموثق قبل المراجعة الكاملة."""
    old = copy.deepcopy(change['before'])
    if change['game'] == 'knowledge' and old['id'] in {'kq_epl_clubs','kq_laliga_clubs','kq_chemical_metals'}:
        old.update(answers=[], manual_answers=[], auto_answers=[], active=False, quarantine_reason='Source type contamination; under factual review')
    return old


def prepare_files(plan, documents):
    staged = copy.deepcopy(documents)
    seen = set()
    for change in plan['changes']:
        game, ident = change['game'], change['id']
        if (game, ident) in seen:
            raise ValueError('تغيير مكرر في خطة المراجعة')
        seen.add((game, ident))
        if game not in FILES and game not in TABLES:
            raise ValueError('اللعبة خارج نطاق مراجعة المحتوى')
        if change['before']['id'] != ident or change['after']['id'] != ident:
            raise ValueError('تغيير معرف السجل ممنوع')
        if game not in FILES:
            continue
        filename, key = FILES[game]
        rows = staged[filename][key] if key else staged[filename]
        matches = [i for i, row in enumerate(rows) if row.get('id') == ident]
        if len(matches) != 1:
            raise ValueError('معرف المحتوى مفقود أو مكرر: ' + game + ':' + str(ident))
        at = matches[0]
        if rows[at] not in (change['before'], expected_interim(change), change['after']):
            raise RuntimeError('تغيّر المحتوى بعد أخذ اللقطة؛ أُلغيت المراجعة: ' + game + ':' + str(ident))
        rows[at] = change['after']
    validate_documents(staged)
    return staged


def validate_documents(documents):
    from app.core.text_processor import normalize_arabic
    bank_texts = set()
    for game, (filename, key) in FILES.items():
        rows = documents[filename][key] if key else documents[filename]
        ids = [row['id'] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError('معرفات محتوى مكررة: ' + game)
        for row in rows:
            if not row.get('active', True):
                continue
            if game in ('bank', 'bank_auto'):
                if not row.get('q') or not row.get('a'):
                    raise ValueError('سؤال أو إجابة فارغة في البنك')
                text_key = normalize_arabic(row['q'])
                if text_key in bank_texts:
                    raise ValueError('سؤال بنك مكرر بين الملفات: ' + row['id'])
                bank_texts.add(text_key)
            elif game == 'whoami':
                if not row.get('name') or len(row.get('hints', [])) != 5:
                    raise ValueError('شخصية بلا خمسة تلميحات: ' + row['id'])
            elif game == 'knowledge':
                if len(row.get('answers', [])) < 15:
                    raise ValueError('قائمة منشورة دون حد الإجابات')
                seen = set()
                for answer in row['answers']:
                    keys = {normalize_arabic(v) for v in answer.split('|') if v.strip()}
                    if not keys or keys & seen:
                        raise ValueError('إجابات قائمة متكررة: ' + row['id'])
                    seen.update(keys)


def apply_review(plan, execute=False):
    with ExitStack() as stack:
        for name in LOCKS:
            if not stack.enter_context(import_lock(DATA_DIR / name)):
                raise RuntimeError('المستورد مشغول؛ لم تتغير البيانات')
        originals = {name: (DATA_DIR / name).read_bytes() for name, _ in FILES.values()}
        documents = {name: json.loads(raw) for name, raw in originals.items()}
        staged = prepare_files(plan, documents)
        engine = create_engine(os.environ['DATABASE_URL'])
        changed_files = [name for name in staged if staged[name] != documents[name]]
        dest = DATA_DIR.parent / 'backups' / ('review_apply_' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
        written = []; committed = False
        try:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text("SET LOCAL statement_timeout = '30s'"))
                sql_changes = []
                for change in plan['changes']:
                    if change['game'] not in TABLES:
                        continue
                    table, allowed = TABLES[change['game']]
                    condition = " AND game_mode='huroof'" if change['game'] == 'huroof' else ''
                    current = conn.execute(text('SELECT * FROM ' + table + ' WHERE id=:id' + condition + ' FOR UPDATE'), {'id': change['id']}).mappings().one()
                    current = dict(current)
                    if current not in (change['before'], change['after']):
                        raise RuntimeError('تغيّر سجل المحتوى بعد اللقطة: ' + change['game'] + ':' + str(change['id']))
                    fields = {key: value for key, value in change['after'].items() if current.get(key) != value}
                    if set(fields) - allowed:
                        raise ValueError('حقول خارج نطاق المحتوى')
                    if fields:
                        sql_changes.append((table, change['id'], fields, condition))
                if execute:
                    dest.mkdir(parents=True, exist_ok=False)
                    for name, raw in originals.items():
                        (dest / name).write_bytes(raw)
                    atomic_json(dest / 'review_plan.json', plan)
                    atomic_json(dest / 'manifest.json', {'reviewed_at': plan['reviewed_at'], 'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()}})
                    for table, ident, fields, condition in sql_changes:
                        assignment = ', '.join(key + '=:' + key for key in fields)
                        conn.execute(text('UPDATE ' + table + ' SET ' + assignment + ' WHERE id=:id' + condition), dict(fields, id=ident))
                    for name in changed_files:
                        atomic_json(DATA_DIR / name, staged[name]); written.append(name)
            committed = True
            result = {'status': 'applied' if execute else 'preview', 'sql_rows': len(sql_changes), 'files': changed_files, 'backup': str(dest) if execute else None, 'deleted_rows': 0}
            if execute:
                atomic_json(dest / 'result.json', result)
            return result
        except Exception:
            for name in ([] if committed else written):
                # استرجاع القيمة الأصلية إذا فشل اعتماد معاملة SQL.
                atomic_json(DATA_DIR / name, documents[name])
            raise
        finally:
            engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply_review(json.loads(args.plan.read_text(encoding='utf-8')), args.apply), ensure_ascii=False))
