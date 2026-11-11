"""تكييف سرعة البوت داخل المباراة بناءً على نتائج اللاعب الأخيرة."""


def record_human_answer(room, sid, bot_sid, correct, quick=False):
    if not room.get("is_solo") or sid is None or sid == bot_sid:
        return
    recent = room.setdefault("solo_human_answers", [])
    recent.append(1.0 if correct and quick else 0.5 if correct else 0.0)
    del recent[:-6]


def adapt_reaction_delay(room, delay, minimum, maximum):
    recent = room.get("solo_human_answers", [])
    if len(recent) < 2:
        return delay
    pace = (sum(recent) + 1.0) / (len(recent) + 2)
    shift = (0.5 - pace) * (maximum - minimum) * 0.55
    return max(minimum, min(maximum, delay + shift))
