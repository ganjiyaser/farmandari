"""برنامهٔ روزانه/هفتگی مدیر و ارسال پیامک یک روز قبل.

هر «برنامه» یک جلسه است که کاربر یا خودش آن را ساخته (📤 ارسالی) یا نامش در
«دعوت‌شدگان» جلسه ثبت شده (📥 دریافتی). یک روز قبل، در ساعت تنظیم‌شده در
تنظیمات، هر برنامه با **یک پیامک جداگانه** برای مدیر ارسال می‌شود تا حجم
هر پیامک بالا نرود؛ گیرنده شمارهٔ موبایل خود کاربر (`users.mobile`) است.

انتخاب اینکه کدام برنامه پیامک داشته باشد با چک‌باکس کنار هر ردیف در پنل
«برنامه‌های مدیر» انجام می‌شود (`program_opt_in` در custom_fields).
"""

import logging
import time

import jdatetime
from PyQt6.QtCore import QThread, pyqtSignal

from services.repositories import calendar_repo, setting_repo, user_repo
from services.sms_service import normalize_mobile, sms_service

logger = logging.getLogger(__name__)

# ---- کلیدهای custom_fields -------------------------------------------
KEY_INVITED_USER_IDS = "invited_user_ids"
KEY_PROGRAM_OPT_IN = "program_opt_in"
KEY_DIGEST_SENT_FOR = "program_digest_sent_for"

# ---- کلیدهای app_settings (سراسری) ------------------------------------
SETTING_DIGEST_ENABLED = "program_digest_enabled"
SETTING_DIGEST_TIME = "program_digest_time"
DEFAULT_DIGEST_TIME = "18:00"

# تأخیر بین دو پیامک تا صف اپراتور اشباع نشود
SMS_GAP_SECONDS = 1.5

# سقف طول دستور کار در پیامک (باقی‌مانده بخش دیگر متن را می‌برد)
MAX_DESCRIPTION_LEN = 250

DIRECTION_SENT = "sent"
DIRECTION_RECEIVED = "received"

DIRECTION_LABELS = {
    DIRECTION_SENT: "ارسالی",
    DIRECTION_RECEIVED: "دریافتی",
}


# ---- عضویت و برچسب ----------------------------------------------------
def invited_user_ids(event) -> list:
    """شناسهٔ کاربرانی که به این جلسه دعوت شده‌اند."""
    raw = ((event.custom_fields or {}).get(KEY_INVITED_USER_IDS)) or []
    out = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def is_in_program(event, user_id) -> bool:
    """جلسه در برنامهٔ این کاربر هست؟ (سازنده بودن یا عضویت در دعوت‌شدگان)"""
    if event is None or user_id is None:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    try:
        creator = int(getattr(event, "user_id", 0) or 0)
    except (TypeError, ValueError):
        creator = 0
    if creator == uid:
        return True
    return uid in invited_user_ids(event)


def direction(event, user_id) -> str:
    """سازندهٔ جلسه = ارسالی، غیر او = دریافتی."""
    try:
        creator = int(getattr(event, "user_id", 0) or 0)
        uid = int(user_id)
    except (TypeError, ValueError):
        return DIRECTION_RECEIVED
    return DIRECTION_SENT if creator == uid else DIRECTION_RECEIVED


def direction_label(event, user_id) -> str:
    return DIRECTION_LABELS.get(direction(event, user_id), "دریافتی")


def issuer_name(event) -> str:
    """صادرکنندهٔ دعوتنامه = سازندهٔ جلسه."""
    user_id = getattr(event, "user_id", None)
    if not user_id:
        return "-"
    try:
        user = user_repo.get_by_id(int(user_id))
    except Exception:
        logger.debug("Could not load event owner %s", user_id, exc_info=True)
        user = None
    if user is None:
        return f"کاربر {user_id}"
    name = ((getattr(user, "full_name", None) or "")
            or (getattr(user, "username", None) or "")).strip()
    return name or f"کاربر {user_id}"


# ---- استخراج جزئیات ---------------------------------------------------
def _clip(text, limit=MAX_DESCRIPTION_LEN):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def program_details(event, user_id) -> list:
    """فهرست (برچسب، مقدار)؛ هم برای کارت پنل و هم برای متن پیامک استفاده می‌شود.

    عناصر خواسته‌شده: عنوان، زمان و تاریخ، مکان، دستور کار، صادرکنندهٔ دعوتنامه.
    """
    start = (event.event_time or "").strip()
    end = (event.end_time or "").strip()
    hours = f"{start} تا {end}" if start and end else (start or end or "-")
    location = (event.location or "").strip()
    description = (event.description or "").strip()
    return [
        ("عنوان", (event.title or "-").strip() or "-"),
        ("تاریخ", (event.event_date or "-").strip() or "-"),
        ("ساعت", hours),
        ("مکان", location or "-"),
        ("دستور کار", _clip(description) or "-"),
        ("صادرکنندهٔ دعوتنامه", issuer_name(event)),
        ("نوع", direction_label(event, user_id)),
    ]


def build_program_sms(event, user_id, target_date=None) -> str:
    """متن پیامک تک‌برنامه؛ هر برنامه جداگانه ارسال می‌شود."""
    header = f"برنامهٔ {target_date}" if target_date else "برنامهٔ مدیر"
    lines = [header]
    for label, value in program_details(event, user_id):
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


# ---- واکشی برنامه -----------------------------------------------------
def get_program(user_id, date_from: str, date_to: str) -> list:
    """جلسات بازهٔ [date_from, date_to] که برنامهٔ این کاربر هستند."""
    if not user_id or not date_from or not date_to:
        return []
    try:
        events = calendar_repo.get_range(date_from, date_to)
    except Exception:
        logger.exception("Could not load program range %s..%s", date_from, date_to)
        return []
    return [e for e in events if is_in_program(e, user_id)]


def get_day_program(user_id, date_str: str) -> list:
    return get_program(user_id, date_str, date_str)


def is_opt_in(event) -> bool:
    return bool((event.custom_fields or {}).get(KEY_PROGRAM_OPT_IN))


def set_opt_in(event_id: int, value: bool) -> bool:
    """چک‌باکس «ارسال در برنامهٔ فردا» کنار هر ردیف پنل."""
    event = calendar_repo.get_by_id(event_id)
    if not event:
        return False
    custom = dict(event.custom_fields or {})
    if value:
        custom[KEY_PROGRAM_OPT_IN] = True
    else:
        custom.pop(KEY_PROGRAM_OPT_IN, None)
    calendar_repo.update(event_id, custom_fields=custom)
    return True


def already_sent(event, target_date: str) -> bool:
    return str((event.custom_fields or {}).get(KEY_DIGEST_SENT_FOR) or "") == target_date


# ---- تنظیمات ارسال -----------------------------------------------------
def digest_enabled() -> bool:
    raw = setting_repo.get_setting(SETTING_DIGEST_ENABLED, True)
    if isinstance(raw, str):
        return raw.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(raw)


def digest_time() -> str:
    raw = setting_repo.get_setting(SETTING_DIGEST_TIME, None)
    text = str(raw or "").strip()
    return text or DEFAULT_DIGEST_TIME


def _to_minutes(hhmm) -> int:
    try:
        parts = str(hhmm).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (IndexError, ValueError, TypeError):
        return -1


def tomorrow(now=None) -> str:
    now = now or jdatetime.datetime.now()
    return (now.date() + jdatetime.timedelta(days=1)).strftime("%Y/%m/%d")


def digest_due(now=None, target_date=None) -> str:
    """تاریخ برنامه‌ای که الان باید ارسال شود؛ اگر وقت نرسیده "".

    از ساعت تنظیم‌شده تا پایان همان روز هر بازه‌ای برنامه ارسال نشده باشد،
    ارسال می‌شود؛ بنابراین اگر برنامه در لحظهٔ تنظیم‌شده باز نبود، پس از باز
    شدن هم ارسال انجام می‌گیرد و هرگز دوبار برای یک روز تکرار نمی‌شود.
    """
    if not digest_enabled():
        return ""
    now = now or jdatetime.datetime.now()
    scheduled = _to_minutes(digest_time())
    if scheduled < 0:
        logger.warning("Invalid program digest time %r", digest_time())
        return ""
    if now.hour * 60 + now.minute < scheduled:
        return ""
    return target_date or tomorrow(now)


# ---- ارسال -------------------------------------------------------------
def pending_events(user_id, target_date: str, ignore_time: bool = False) -> list:
    """برنامه‌هایی از target_date که باید ارسال شوند."""
    if not target_date:
        return []
    events = get_day_program(user_id, target_date)
    return [
        e for e in events
        if is_opt_in(e) and (ignore_time or not already_sent(e, target_date))
    ]


class ProgramDigestWorker(QThread):
    """ارسال یکی‌یکی برنامه‌ها؛ هر ردیف یک پیامک جدا تا حجم پیامک بالا نرود."""

    done = pyqtSignal(dict)

    def __init__(self, user_id, target_date, mobile, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.target_date = target_date
        self.mobile = normalize_mobile(str(mobile or ""))

    def run(self):
        result = {
            "success": 0, "failed": 0, "total": 0, "results": [],
            "target_date": self.target_date, "error": None,
        }
        if not self.mobile:
            result["error"] = "شمارهٔ موبایل کاربر ثبت نشده است"
            self.done.emit(result)
            return

        events = pending_events(self.user_id, self.target_date)
        result["total"] = len(events)
        if not events:
            self.done.emit(result)
            return

        for index, event in enumerate(events):
            text = build_program_sms(event, self.user_id, self.target_date)
            try:
                sms = sms_service.send_number(self.mobile, text)
                ok = bool(getattr(sms, "success", False))
                error = getattr(sms, "error", None)
            except Exception as exc:
                logger.exception("Program digest SMS failed for event %s", event.id)
                ok, error = False, str(exc)

            result["results"].append({
                "event_id": event.id,
                "title": event.title,
                "success": 1 if ok else 0,
                "error": error,
            })
            if ok:
                result["success"] += 1
                try:
                    custom = dict(event.custom_fields or {})
                    custom[KEY_DIGEST_SENT_FOR] = self.target_date
                    calendar_repo.update(event.id, custom_fields=custom)
                except Exception:
                    logger.exception(
                        "Could not mark digest sent for event %s", event.id
                    )
            else:
                result["failed"] += 1

            if index < len(events) - 1 and SMS_GAP_SECONDS:
                time.sleep(SMS_GAP_SECONDS)

        self.done.emit(result)


def send_program_digest(user_id, target_date, mobile, parent=None) -> ProgramDigestWorker:
    """ارسال برنامه در thread جدا؛ caller باید worker را نگه دارد."""
    return ProgramDigestWorker(user_id, target_date, mobile, parent)
