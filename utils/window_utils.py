# -*- coding: utf-8 -*-
"""ابزارهای چیدمان پنجره‌ها روی مانیتور"""
import weakref

from PyQt5.QtCore import QEvent, QObject, QSize, QTimer
from PyQt5.QtWidgets import QApplication, QDialog, QMainWindow


# حاشیهٔ تقریبی قاب پنجره پیش از نمایش (نوار عنوان + لبه‌ها)
_FRAME_W = 16
_FRAME_H = 48
_MARGIN = 8


def available_geometry(widget=None):
    """فضای قابل استفادهٔ مانیتورِ مربوط به پنجره (بدون نوار وظیفه)."""
    screen = None
    if widget is not None:
        try:
            parent = widget.parentWidget()
            if parent is not None:
                screen = parent.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = widget.screen()
            except Exception:
                screen = None
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def fit_window_to_screen(widget, preferred=None, center=True, margin=_MARGIN):
    """جمع کردن پنجره تا کاملاً داخل مانیتور جا شود.

    اگر حداقل اندازهٔ پنجره بزرگ‌تر از صفحه باشد، حداقل اندازه هم کم می‌شود؛
    وگرنه resize توسط setMinimumSize نادیده گرفته می‌شد و بخشی از پنجره
    بیرون از صفحه می‌ماند (مثلاً مانیتور HD با مقیاس ۱۲۵٪/۱۵۰٪).

    preferred: اندازهٔ دلخواه؛ None یعنی اندازهٔ فعلی پنجره حفظ شود.
    center: پنجره در مرکز صفحه قرار بگیرد (برای دیالوگ‌ها معمولاً False تا
    جای طبیعیِ کنار پنجرهٔ والد حفظ شود).
    """
    if widget.isMaximized() or widget.isFullScreen():
        return
    avail = available_geometry(widget)
    if avail is None or avail.isEmpty():
        return

    if widget.isVisible():
        frame = widget.frameGeometry()
        border_w = max(0, frame.width() - widget.width())
        border_h = max(0, frame.height() - widget.height())
    else:
        border_w, border_h = _FRAME_W, _FRAME_H

    max_w = avail.width() - 2 * margin - border_w
    max_h = avail.height() - 2 * margin - border_h
    if max_w < 320 or max_h < 240:
        return

    if preferred is not None:
        pref_w, pref_h = preferred.width(), preferred.height()
    else:
        pref_w, pref_h = widget.width(), widget.height()
        if pref_w <= 0 or pref_h <= 0:
            hint = widget.sizeHint()
            pref_w, pref_h = hint.width(), hint.height()

    # حداقل اندازهٔ بزرگ‌تر از صفحه، اول کم می‌شود؛ وگرنه resize بی‌اثر است.
    min_w = min(widget.minimumWidth(), max_w)
    min_h = min(widget.minimumHeight(), max_h)
    if (min_w, min_h) != (widget.minimumWidth(), widget.minimumHeight()):
        widget.setMinimumSize(min_w, min_h)

    target_w = max(min_w, min(pref_w, max_w))
    target_h = max(min_h, min(pref_h, max_h))
    if (target_w, target_h) != (widget.width(), widget.height()):
        widget.resize(target_w, target_h)

    frame = widget.frameGeometry()
    if center:
        frame.moveCenter(avail.center())
    x = min(max(frame.x(), avail.left()), avail.right() - frame.width() + 1)
    y = min(max(frame.y(), avail.top()), avail.bottom() - frame.height() + 1)
    if x != widget.x() or y != widget.y():
        widget.move(x, y)


def center_on_screen(widget, available=None):
    """باز کردن پنجره در مرکز مانیتور.

    باید بعد از show() صدا زده شود تا هندسهٔ قاب (نوار عنوان و حاشیه‌ها)
    واقعی باشد؛ اگر پنجره از فضای قابل استفادهٔ صفحه بزرگ‌تر باشد ابتدا
    اندازه‌اش را جمع می‌کند (و در صورت نیاز حداقل اندازه را کم می‌کند).

    available: مستطیل مقصد؛ پیش‌فرض فضای قابل استفادهٔ صفحهٔ همان پنجره است
    (برای تست و صفحه‌های چندگانه قابل پوشش).
    """
    if available is None:
        fit_window_to_screen(widget, center=True)
        return

    if available.isEmpty():
        return
    frame = widget.frameGeometry()
    border_w = max(0, frame.width() - widget.width())
    border_h = max(0, frame.height() - widget.height())
    max_w = available.width() - border_w
    max_h = available.height() - border_h
    if max_w <= 0 or max_h <= 0:
        return
    widget.setMinimumSize(
        min(widget.minimumWidth(), max_w), min(widget.minimumHeight(), max_h)
    )
    widget.resize(min(widget.width(), max_w), min(widget.height(), max_h))
    frame = widget.frameGeometry()
    frame.moveCenter(available.center())
    x = min(max(frame.x(), available.left()), available.right() - frame.width() + 1)
    y = min(max(frame.y(), available.top()), available.bottom() - frame.height() + 1)
    widget.move(x, y)


class ScreenFitFilter(QObject):
    """هر دیالوگ/پنجرهٔ جدید را در اولین نمایش داخل مانیتور نگه می‌دارد."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seen = weakref.WeakSet()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, (QDialog, QMainWindow)) and obj.isWindow():
            if obj not in self._seen:
                self._seen.add(obj)
                QTimer.singleShot(0, lambda w=obj: self._fit_later(w))
        return False

    @staticmethod
    def _fit_later(widget):
        try:
            if widget.isVisible():
                fit_window_to_screen(widget, center=False)
        except RuntimeError:
            pass  # پنجره پیش از اجرای تایمر بسته شده است


def watch_window_screen(widget):
    """هنگام انتقال پنجره به مانیتور دیگر، اگر بزرگ‌تر از آن بود جمعش کن."""
    handle = widget.windowHandle()
    if handle is None:
        return

    def _on_screen_changed(_screen):
        if widget.isMaximized() or widget.isFullScreen():
            return
        QTimer.singleShot(
            0,
            lambda: fit_window_to_screen(
                widget, preferred=QSize(widget.width(), widget.height()), center=False
            ),
        )

    handle.screenChanged.connect(_on_screen_changed)
