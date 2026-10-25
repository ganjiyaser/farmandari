"""بررسی تداخل برنامهٔ مسئولین و یافتن زمان آزاد.

جلسات در یک دیتابیس مشترک نگهداری می‌شوند، بنابراین تداخل بین برنامهٔ
فرماندار، معاونین و بخشداران (صاحب جلسه یا دعوت‌شده) قابل تشخیص است.
تاریخ‌ها شمسی (YYYY/MM/DD) و ساعت‌ها HH:mm هستند — همان قالب جدول events.
"""

import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import or_

from core.database import get_db
from models.models import Event, EventParticipant, Official, Contact

logger = logging.getLogger(__name__)

WORK_START = "08:00"
WORK_END = "17:00"


def _to_minutes(hhmm: Optional[str]) -> Optional[int]:
    if not hhmm:
        return None
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    """بازه‌های دقیقه‌ای؛ None یعنی نامشخص (کل روز در نظر گرفته می‌شود)."""
    if a_start is None or b_start is None:
        return True
    a_end = a_end if a_end is not None else a_start + 60
    b_end = b_end if b_end is not None else b_start + 60
    return a_start < b_end and b_start < a_end


def _event_dict(ev: Event, via: str) -> Dict[str, Any]:
    return {
        "event_id": ev.id,
        "title": ev.title,
        "event_date": ev.event_date,
        "event_time": ev.event_time,
        "end_time": ev.end_time,
        "official_id": ev.official_id,
        "via": via,  # صاحب جلسه یا شرکت‌کننده
    }


def _events_for_session(db, *, date: str, official_id: Optional[int] = None,
                        contact_id: Optional[int] = None,
                        exclude_event_id: Optional[int] = None) -> List[Event]:
    q = db.query(Event).filter(Event.event_date == date)
    if official_id is not None:
        q = q.outerjoin(EventParticipant, EventParticipant.event_id == Event.id).filter(
            or_(Event.official_id == official_id,
                EventParticipant.official_id == official_id)
        )
    elif contact_id is not None:
        q = q.outerjoin(EventParticipant, EventParticipant.event_id == Event.id).filter(
            EventParticipant.contact_id == contact_id
        )
    else:
        return []
    if exclude_event_id:
        q = q.filter(Event.id != exclude_event_id)
    return q.distinct().all()


def find_conflicts(*, event_date: str, event_time: Optional[str] = None,
                   end_time: Optional[str] = None,
                   official_id: Optional[int] = None,
                   contact_id: Optional[int] = None,
                   exclude_event_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """جلسات هم‌پوشان برای یک مسئول یا مخاطب در تاریخ مشخص.

    خروجی: فهرست دیکشنری با کلیدهای event_id/title/event_time/end_time/via
    (via = owner اگر جلسهٔ خودِ شخص باشد، participant اگر فقط دعوت‌شده باشد).
    """
    start = _to_minutes(event_time)
    end = _to_minutes(end_time)
    conflicts: List[Dict[str, Any]] = []
    seen = set()
    db = get_db()
    try:
        for ev in _events_for_session(
            db, date=event_date, official_id=official_id,
            contact_id=contact_id, exclude_event_id=exclude_event_id,
        ):
            if ev.id in seen:
                continue
            if _overlaps(start, end,
                         _to_minutes(ev.event_time), _to_minutes(ev.end_time)):
                seen.add(ev.id)
                via = "owner" if (official_id and ev.official_id == official_id) else "participant"
                conflicts.append(_event_dict(ev, via))
        return conflicts
    except Exception:
        logger.exception("find_conflicts failed")
        return []
    finally:
        db.close()


def find_conflicts_for_participants(*, event_date: str, event_time: Optional[str] = None,
                                    end_time: Optional[str] = None,
                                    official_ids: List[int] = None,
                                    contact_ids: List[int] = None,
                                    exclude_event_id: Optional[int] = None) -> Dict[int, List[Dict]]:
    """تداخل هر دعوت‌شده را جداگانه برمی‌گرداند: {official_id/contact_id: conflicts}."""
    result: Dict[int, List[Dict]] = {}
    for oid in official_ids or []:
        c = find_conflicts(event_date=event_date, event_time=event_time,
                           end_time=end_time, official_id=oid,
                           exclude_event_id=exclude_event_id)
        if c:
            result[("official", oid)] = c
    for cid in contact_ids or []:
        c = find_conflicts(event_date=event_date, event_time=event_time,
                           end_time=end_time, contact_id=cid,
                           exclude_event_id=exclude_event_id)
        if c:
            result[("contact", cid)] = c
    return result


def busy_intervals(db, *, date: str, official_ids: List[int],
                   exclude_event_id: Optional[int] = None) -> List[tuple]:
    """بازه‌های اشغالی (شروع، پایان، عنوان، نام مسئول) برای چند مسئول."""
    intervals = []
    seen_events = set()
    officials = {o.id: o for o in db.query(Official).filter(
        Official.id.in_(official_ids or [0])).all()}
    for oid in official_ids or []:
        for ev in _events_for_session(db, date=date, official_id=oid,
                                      exclude_event_id=exclude_event_id):
            if ev.id in seen_events:
                continue
            seen_events.add(ev.id)
            s = _to_minutes(ev.event_time)
            e = _to_minutes(ev.end_time)
            if s is None:
                continue
            intervals.append((s, e if e is not None else s + 60,
                              ev.title, officials.get(ev.official_id)))
    return intervals


def find_free_slots(*, date: str, official_ids: List[int],
                    duration_minutes: int = 60,
                    work_start: str = WORK_START, work_end: str = WORK_END,
                    exclude_event_id: Optional[int] = None) -> List[Dict[str, int]]:
    """بازه‌های آزاد مشترک مسئولین انتخاب‌شده در یک روز (دقیقه از نیمه‌شب)."""
    ws = _to_minutes(work_start) or 480
    we = _to_minutes(work_end) or 1020
    db = get_db()
    try:
        busy = sorted(busy_intervals(db, date=date, official_ids=official_ids,
                                     exclude_event_id=exclude_event_id))
    finally:
        db.close()

    free = []
    cursor = ws
    for s, e, _title, _off in busy:
        if s - cursor >= duration_minutes:
            free.append({"start": cursor, "end": s})
        cursor = max(cursor, e)
    if we - cursor >= duration_minutes:
        free.append({"start": cursor, "end": we})
    return free


def suggest_next_free(*, official_ids: List[int], duration_minutes: int = 60,
                      from_date: str, max_days: int = 30,
                      work_start: str = WORK_START, work_end: str = WORK_END,
                      exclude_event_id: Optional[int] = None) -> Optional[Dict[str, str]]:
    """اولین تاریخ/ساعت آزاد مشترک از تاریخ به بعد (جست‌وجوی روزبه‌روز)."""
    import jdatetime

    try:
        y, m, d = (int(x) for x in from_date.split("/"))
        jd = jdatetime.date(y, m, d)
    except (ValueError, TypeError):
        return None

    for _ in range(max_days):
        date_str = jd.strftime("%Y/%m/%d")
        slots = find_free_slots(date=date_str, official_ids=official_ids,
                                duration_minutes=duration_minutes,
                                work_start=work_start, work_end=work_end,
                                exclude_event_id=exclude_event_id)
        if slots:
            s = slots[0]["start"]
            e = min(slots[0]["end"], s + duration_minutes)
            return {
                "date": date_str,
                "start": f"{s // 60:02d}:{s % 60:02d}",
                "end": f"{e // 60:02d}:{e % 60:02d}",
            }
        jd = jd + jdatetime.timedelta(days=1)
    return None


def format_conflict_message(conflicts: List[Dict[str, Any]],
                            official_names: Optional[Dict[int, str]] = None) -> str:
    """متن فارسی گزارش تداخل برای نمایش به کاربر."""
    official_names = official_names or {}
    lines = []
    for c in conflicts:
        t = c.get("event_time") or "ساعت نامشخص"
        owner = official_names.get(c.get("official_id"), "")
        suffix = f" — {owner}" if owner else ""
        lines.append(f"• {c['title']} ({t}){suffix}")
    return "\n".join(lines)
