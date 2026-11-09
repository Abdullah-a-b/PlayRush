"""الأندية المتشابهة بالاسم تُعرّف بمعرّف الكيان قبل جلب الشعار."""

_AL_AHLY = {
    "Q223566": ("الأهلي المصري", "https://www.alahlyegypt.com/logo.png"),
    "Q44441": ("الأهلي السعودي", "https://images.alahlifc.sa/image/private/t_q-good/v1751481087/prd/assets/brand/al-ahli-logo.svg"),
}
_LEGACY_NAMES = {
    "الأهلي المصري": "Q223566",
    "النادي الأهلي (مصر)": "Q223566",
    "الأهلي السعودي": "Q44441",
    "النادي الأهلي (السعودية)": "Q44441",
}


def resolve_club(club):
    # السجلات القديمة لم تحفظ المعرّف. نستخدم التسمية الصريحة فقط.
    qid = club.get("club_qid") or _LEGACY_NAMES.get(club["name"])
    if qid not in _AL_AHLY:
        return club
    name, logo = _AL_AHLY[qid]
    return {**club, "club_qid": qid, "name": name, "logo": logo}
