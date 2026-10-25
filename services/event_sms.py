"""منطق مشترک ارسال پیامک جلسه.

دو ارسال برای هر جلسه وجود دارد:
  ۱. دعوت‌نامه — هنگام ثبت جلسه (توسط EventDialog ساخته و CalendarPage ارسال می‌کند)
  ۲. یادآوری — در زمان انتخاب‌شده توسط کاربر (رویکرد «چند دقیقه قبل»، «ساعت ثابت» یا «دستی»)

هر دو متن هنگام ثبت جلسه نوشته و در custom_fields ذخیره می‌شوند.
"""

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from models.models import EventType
from services.repositories import calendar_repo, contact_repo, official_repo
from services.sms_service import normalize_mobile, sms_service

logger = logging.getLogger(__name__)


DEFAULT_INVITE_TEMPLATE = (
    "با سلام و احترام\n"
    "جلسه «{عنوان}» روز {تاریخ} ساعت {ساعت} در {مکان} برگزار می‌شود.\n"
    "حضور شما مورد انتظار است."
)

DEFAULT_REMINDER_TEMPLATE = (
    "یادآوری: جلسه «{عنوان}» امروز {تاریخ} ساعت {ساعت} در {مکان} برگزار می‌شود.\n"
    "خواهشمند است در جلسه حاضر شوید."
)

EVENT_TYPE_LABELS = {
    EventType.MEETING: "جلسه",
    EventType.CONFERENCE: "همایش",
    EventType.VISIT: "بازدید / دیدار",
    EventType.FOLLOWUP: "پیگیری",
    EventType.REMINDER: "یادآوری",
    EventType.OTHER: "سایر",
}

# حالت‌های ارسال پیامک یادآوری — هر سه قابلیت در دیالوگ و به انتخاب کاربر
REMINDER_MODE_OFF = "off"
REMINDER_MODE_BEFORE = "before"
REMINDER_MODE_FIXED = "fixed"
REMINDER_MODE_MANUAL = "manual"

REMINDER_MODE_LABELS = (
    (REMINDER_MODE_OFF, "غیرفعال"),
    (REMINDER_MODE_BEFORE, "چند دقیقه قبل از جلسه"),
    (REMINDER_MODE_FIXED, "ساعت ثابت در روز جلسه"),
    (REMINDER_MODE_MANUAL, "ارسال دستی (با دکمه)"),
)

# کلیدهای custom_fields مربوط به پیامک جلسه
KEY_CONTACT_IDS = "sms_contact_ids"
KEY_OFFICIAL_IDS = "invited_official_ids"
KEY_MANAGER_MOBILE = "sms_manager_mobile"
KEY_MANAGER_INVITE = "sms_send_invite_manager"
KEY_MANAGER_REMINDER = "sms_send_reminder_manager"
KEY_INVITE_TEMPLATE = "sms_template"
KEY_REMINDER_TEMPLATE = "sms_reminder_template"
KEY_AUTO_INVITE = "sms_auto"
KEY_REMINDER_MODE = "reminder_mode"
KEY_REMINDER_FIXED_TIME = "reminder_fixed_time"


def render_sms_template(template: str, values: dict) -> str:
    text = template or ""
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value or "-"))
    return text


def _event_type_label(event_type) -> str:
    if isinstance(event_type, EventType):
        return EVENT_TYPE_LABELS.get(event_type, "سایر")
    for et, label in EVENT_TYPE_LABELS.items():
        if et.value == event_type:
            return label
    return "سایر"


def build_values(*, title, event_date, event_time, end_time,
                 location=None, event_type=None) -> dict:
    """متغیرهای قابل استفاده در متن پیامک ({عنوان} {تاریخ} {ساعت} ...)."""
    start = (event_time or "").strip()
    end = (end_time or "").strip()
    if start and end:
        hours = f"{start} تا {end}"
    else:
        hours = start or end or ""
    return {
        "عنوان": title,
        "تاریخ": event_date,
        "ساعت": hours,
        "مکان": location,
        "نوع": _event_type_label(event_type),
    }


def values_for_event(event) -> dict:
    """متغیرهای پیامک یک جلسهٔ ذخیره‌شده."""
    return build_values(
        title=event.title,
        event_date=event.event_date,
        event_time=event.event_time,
        end_time=event.end_time,
        location=event.location,
        event_type=event.event_type,
    )


def manager_mobile(custom: dict) -> str:
    """شماره مدیر که کاربر در دیالوگ جلسه وارد کرده است (خالی اگر وارد نشده باشد)."""
    return normalize_mobile(str((custom or {}).get(KEY_MANAGER_MOBILE) or ""))


def build_recipients(custom: dict, include_manager: bool) -> list:
    """فهرست گیرندگان پیامک جلسه از custom_fields ذخیره‌شده.

    گیرنده بدون contact_id (شماره مدیر) یا با official_id ارسال می‌شود ولی
    مسئولین در سابقهٔ پیامک مخاطب ثبت نمی‌شوند.
    """
    custom = custom or {}
    recipients = []
    for cid in custom.get(KEY_CONTACT_IDS) or []:
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        contact = contact_repo.get_by_id(cid)
        if not contact or not (contact.mobile or "").strip():
            continue
        recipients.append({
            "contact_id": contact.id,
            "mobile": contact.mobile,
            "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip(),
        })

    for oid in custom.get(KEY_OFFICIAL_IDS) or []:
        try:
            oid = int(oid)
        except (TypeError, ValueError):
            continue
        official = official_repo.get_by_id(oid)
        if not official or not (official.mobile or "").strip():
            continue
        recipients.append({
            "contact_id": None,
            "official_id": official.id,
            "mobile": official.mobile,
            "name": official.display_name,
        })

    if include_manager:
        number = manager_mobile(custom)
        if number:
            recipients.append({"contact_id": None, "mobile": number, "name": "مدیر"})

    return recipients


def prepare_reminder(event):
    """(گیرندگان، متن) پیامک یادآوری جلسه؛ اگر پیکربندی نشده باشد (None, None).

    داخل thread فراخوانی می‌شود چون دسترسی به دیتابیس دارد.
    """
    if event is None:
        return None, None
    custom = event.custom_fields or {}
    template = str(custom.get(KEY_REMINDER_TEMPLATE) or "").strip()
    if not template:
        return None, None
    recipients = build_recipients(custom, bool(custom.get(KEY_MANAGER_REMINDER)))
    if not recipients:
        return None, None
    return recipients, render_sms_template(template, values_for_event(event))


class EventSMSWorker(QThread):
    """ارسال پیامک جلسه با فهرست گیرندگان آماده (دعوت‌نامه)."""

    done = pyqtSignal(dict)

    def __init__(self, recipients, message, event_id=None, parent=None):
        super().__init__(parent)
        self.recipients = recipients or []
        self.message = message
        self.event_id = event_id

    def run(self):
        try:
            result = sms_service.send_to_recipients(self.recipients, self.message)
        except Exception as e:
            logger.exception("Event SMS send failed")
            result = {
                "success": 0, "failed": len(self.recipients), "total": len(self.recipients),
                "results": [], "error": str(e),
            }
        result["event_id"] = self.event_id
        self.done.emit(result)


class ReminderSMSWorker(QThread):
    """ساخت گیرندگان/متن یادآوری و ارسال آن در پس‌زمینه."""

    done = pyqtSignal(dict)

    def __init__(self, event_id, parent=None):
        super().__init__(parent)
        self.event_id = event_id

    def run(self):
        result = {"success": 0, "failed": 0, "total": 0, "results": [], "event_id": self.event_id}
        try:
            event = calendar_repo.get_by_id(self.event_id)
            recipients, message = prepare_reminder(event)
            if not recipients:
                result["error"] = "پیکربندی پیامک یادآوری انجام نشده است"
            else:
                result.update(sms_service.send_to_recipients(recipients, message))
                result["event_id"] = self.event_id
        except Exception as e:
            logger.exception("Reminder SMS failed for event %s", self.event_id)
            result["error"] = str(e)
        self.done.emit(result)


def send_event_reminder(event_id, parent=None) -> ReminderSMSWorker:
    """ارسال پیامک یادآوری جلسه در thread جدا؛ caller باید worker را نگه دارد."""
    return ReminderSMSWorker(event_id, parent)
