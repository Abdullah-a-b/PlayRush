"""
period_keys.py — توليد مفاتيح الفترات الزمنية الموحّدة.

يومي: 2026-07-15
أسبوعي: 2026-W29 (ISO week)
موسمي: يبدأ الخميس الثالث من كل شهر (قرار الوثيقة).
       مفتاح الموسم = سنة + رقم تسلسلي شهري: 2026-S07
"""
import datetime


def daily_key(now: datetime.datetime = None) -> str:
    now = now or datetime.datetime.utcnow()
    return now.strftime("%Y-%m-%d")


def weekly_key(now: datetime.datetime = None) -> str:
    now = now or datetime.datetime.utcnow()
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _third_thursday(year: int, month: int) -> datetime.date:
    """تاريخ الخميس الثالث من شهر معيّن."""
    d = datetime.date(year, month, 1)
    # weekday(): الاثنين=0 ... الخميس=3
    first_thursday_offset = (3 - d.weekday()) % 7
    first_thursday = 1 + first_thursday_offset
    return datetime.date(year, month, first_thursday + 14)


def current_season(now: datetime.datetime = None) -> dict:
    """الموسم الحالي: يبدأ الخميس الثالث من الشهر وينتهي قبل التالي.

    يرجع: { key, start, end, index } — index رقم الموسم في السنة (1..12).
    """
    now = now or datetime.datetime.utcnow()
    today = now.date()
    this_month_start = _third_thursday(today.year, today.month)

    if today >= this_month_start:
        start = this_month_start
        idx = today.month
        year = today.year
    else:
        # ما زلنا في موسم الشهر السابق
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        start = _third_thursday(prev_year, prev_month)
        idx = prev_month
        year = prev_year

    # نهاية الموسم = بداية الموسم التالي
    if start.month == 12:
        nxt = _third_thursday(start.year + 1, 1)
    else:
        nxt = _third_thursday(start.year, start.month + 1)

    return {
        "key": f"{year}-S{idx:02d}",
        "start": start.isoformat(),
        "end": nxt.isoformat(),
        "index": idx,
    }


def season_key(now: datetime.datetime = None) -> str:
    return current_season(now)["key"]
