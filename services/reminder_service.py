import logging

import jdatetime
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from services import manager_program as program
from services.event_sms import send_event_reminder
from services.repositories import calendar_repo, setting_repo, user_repo

logger = logging.getLogger(__name__)


class ReminderService(QObject):
    reminder_triggered = pyqtSignal(int, str, str)
    program_digest_done = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_reminders)
        self._interval = 60000
        self._running = False
        # workerهای ارسال پیامک یادآوری باید زنده بمانند تا thread تمام شود
        self._sms_workers = []
        self._digest_worker = None

    def start(self):
        if not self._running:
            self._timer.start(self._interval)
            self._running = True
            logger.info("Reminder service started")

    def stop(self):
        if self._running:
            self._timer.stop()
            self._running = False
            logger.info("Reminder service stopped")

    def set_interval(self, seconds: int):
        self._interval = seconds * 1000
        if self._running:
            self._timer.setInterval(self._interval)

    def _check_reminders(self):
        try:
            events = calendar_repo.get_pending_reminders()
            for event in events:
                if calendar_repo.should_remind(event):
                    calendar_repo.mark_reminder_sent(event.id)
                    self.reminder_triggered.emit(
                        event.id,
                        event.title,
                        f"{event.event_date} - {event.event_time or ''}"
                    )
                    self._start_reminder_sms(event.id)
        except Exception as e:
            logger.error(f"Reminder check error: {e}")
        self._check_program_digest()

    # ------------------------------------------------------------------ #
    #  برنامهٔ فردا — ارسال یکی‌یکی در ساعت تنظیم‌شده
    # ------------------------------------------------------------------ #
    def _check_program_digest(self):
        try:
            target = program.digest_due()
            if not target:
                return
            if self._digest_worker is not None and self._digest_worker.isRunning():
                return
            uid = setting_repo.get_setting("current_user_id")
            if not uid:
                return
            user = user_repo.get_by_id(int(uid))
            mobile = str(getattr(user, "mobile", "") or "") if user else ""
            if not mobile.strip():
                logger.warning(
                    "Program digest for %s skipped: user has no mobile", uid
                )
                return
            if not program.pending_events(int(uid), target):
                return
            worker = program.send_program_digest(int(uid), target, mobile)
            self._digest_worker = worker
            worker.done.connect(self._on_program_digest_done)
            worker.start()
        except Exception as e:
            logger.error(f"Program digest check error: {e}")

    def _on_program_digest_done(self, result: dict):
        if result.get("error"):
            logger.warning("Program digest not sent: %s", result["error"])
        else:
            logger.info(
                "Program digest %s: %s of %s sent",
                result.get("target_date"),
                result.get("success", 0),
                result.get("total", 0),
            )
        self.program_digest_done.emit(result)
        self._digest_worker = None

    # ------------------------------------------------------------------ #
    #  ارسال پیامک یادآوری
    # ------------------------------------------------------------------ #
    def _start_reminder_sms(self, event_id: int):
        try:
            worker = send_event_reminder(event_id)
        except Exception as e:
            logger.error("Could not start reminder SMS for event %s: %s", event_id, e)
            return
        self._sms_workers.append(worker)
        worker.done.connect(self._on_reminder_sms_done)
        worker.finished.connect(
            lambda w=worker: self._sms_workers.remove(w) if w in self._sms_workers else None
        )
        worker.start()

    def _on_reminder_sms_done(self, result: dict):
        event_id = result.get("event_id")
        if not event_id or not result.get("success"):
            if result.get("error"):
                logger.warning("Reminder SMS for event %s: %s", event_id, result["error"])
            return
        try:
            event = calendar_repo.get_by_id(event_id)
            if not event:
                return
            custom = dict(event.custom_fields or {})
            custom["sms_reminder_sent_at"] = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
            custom["sms_reminder_last_result"] = (
                f"{result.get('success', 0)} از {result.get('total', 0)}"
            )
            calendar_repo.update(event_id, custom_fields=custom)
        except Exception:
            logger.exception("Could not record reminder SMS result for event %s", event_id)


reminder_service = ReminderService()
