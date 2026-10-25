# -*- coding: utf-8 -*-
"""ابزارهای چیدمان پنجره‌ها روی مانیتور"""
from PyQt6.QtWidgets import QApplication


def center_on_screen(widget, available=None):
    """باز کردن پنجره در مرکز مانیتور

    باید بعد از show() صدا زده شود تا هندسهٔ قاب (نوار عنوان و حاشیه‌ها)
    واقعی باشد؛ وگرنه پنجره چند پیکسل بالاتر/کنارتر می‌نشیند. اگر پنجره از
    فضای قابل استفادهٔ صفحه بزرگ‌تر باشد ابتدا اندازه‌اش را جمع می‌کند.

    available: مستطیل مقصد؛ پیش‌فرض فضای قابل استفادهٔ صفحهٔ همان پنجره است
    (برای تست و صفحه‌های چندگانه قابل پوشش).
    """
    if available is None:
        try:
            screen = widget.screen() or QApplication.primaryScreen()
        except Exception:
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
    if available is None or available.isEmpty():
        return

    # حاشیهٔ قاب (نوار عنوان/لبه‌ها) تا بعد از اولین resize درست گزارش می‌شود،
    # پس چند بار تکرار می‌کنیم تا خودِ قاب هم داخل صفحه جا شود.
    for _ in range(3):
        frame = widget.frameGeometry()
        border_w = frame.width() - widget.width()
        border_h = frame.height() - widget.height()
        max_w = available.width() - border_w
        max_h = available.height() - border_h
        if max_w <= 0 or max_h <= 0:
            break
        new_w = min(widget.width(), max_w)
        new_h = min(widget.height(), max_h)
        if new_w >= widget.width() and new_h >= widget.height():
            break
        widget.resize(new_w, new_h)

    frame = widget.frameGeometry()
    frame.moveCenter(available.center())
    widget.move(frame.topLeft())
