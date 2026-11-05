"""تحويل حقائق الدول إلى أسئلة أحادية الإجابة بهوية مستقرة."""
from collections import defaultdict
from app.core.import_support import canonical, stable_id


def value(binding, key):
    return (binding.get(key) or {}).get("value", "").strip()


def arabic(text):
    return bool(text) and any("\u0600" <= c <= "\u06ff" and c.isalpha() for c in text)


def countries(rows):
    grouped = {}
    for row in rows:
        label = value(row, "cLabelAr")
        if not arabic(label):
            continue
        identity = value(row, "c") or canonical(label)
        country = grouped.setdefault(identity, {"id": identity, "name": label, "en": value(row, "cLabelEn"), "cap": {}, "cur": {}, "cont": {}})
        for kind in ("cap", "cur", "cont"):
            name = value(row, kind + "Ar")
            if arabic(name):
                entity = value(row, kind) or canonical(name)
                country[kind][entity] = (name, value(row, kind + "En"))
    return sorted(grouped.values(), key=lambda c: c["id"])


def country_facts(rows):
    """نستبعد العلاقة المتعددة بدلاً من اختيار أول صف اعتباطياً."""
    facts = []
    cs = countries(rows)
    owners = defaultdict(set)
    for c in cs:
        for cap in c["cap"]:
            owners[cap].add(c["id"])
    for c in cs:
        for kind in ("cap", "cur", "cont"):
            if len(c[kind]) != 1:
                continue
            entity, (answer, english) = next(iter(c[kind].items()))
            facts.append({"id": stable_id(kind, c["id"]), "kind": kind, "country": c["name"], "country_en": c["en"], "country_id": c["id"], "answer_id": entity, "answer": answer, "english": english, "inverse_unique": kind == "cap" and len(owners[entity]) == 1})
    return facts
