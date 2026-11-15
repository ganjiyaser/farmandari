import jdatetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QGridLayout, QScrollArea, QSizePolicy, QGraphicsOpacityEffect,
    QMessageBox, QCheckBox, QTabWidget
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm, confirm_delete
from services import manager_program as program
from services.repositories import calendar_repo, setting_repo, user_repo, official_repo
from services.event_sms import (
    KEY_CONTACT_IDS, KEY_MANAGER_INVITE, KEY_MANAGER_REMINDER,
    KEY_REMINDER_TEMPLATE, EventSMSWorker, send_event_reminder,
)


PERSIAN_MONTHS = {
    1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
    5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
    9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
}

PERSIAN_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

PRIORITY_COLORS = {
    "high": "#C62828",
    "medium": "#EF6C00",
    "low": "#2E7D32",
}

STATUS_COLORS = {
    "pending": "#F57F17",
    "confirmed": "#2E7D32",
    "cancelled": "#9E9E9E",
    "completed": "#1565C0",
}

STATUS_LABELS = {
    "pending": "در انتظار",
    "confirmed": "تایید شده",
    "cancelled": "لغو شده",
    "completed": "انجام شده",
}


def _event_official(event):
    """صاحب برنامهٔ جلسه؛ چون repoها session را می‌بندند رابطه lazy باز نمی‌شود."""
    try:
        oid = event.official_id
        return official_repo.get_by_id(oid) if oid else None
    except Exception:
        return None


class DayCell(QFrame):
    def __init__(self, day_num, is_today=False, event_count=0, parent=None):
        super().__init__(parent)
        self.day_num = day_num
        self.is_today = is_today
        c = theme_manager.current

        bg = c.primary if is_today else c.canvas_overlay
        border = f"2px solid {c.primary}" if is_today else f"1px solid {c.border_default}"
        text_color = c.fg_on_emphasis if is_today else c.fg_default

        self.setStyleSheet(
            f"DayCell {{ background-color: {bg}; border: {border}; border-radius: 12px; padding: 8px; }}"
        )
        self.setFixedSize(100, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        day_label = QLabel(str(day_num))
        day_label.setStyleSheet(
            f"font-size: 20px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; "
            f"color: {text_color}; background: transparent; border: none;"
        )
        day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(day_label)

        if event_count > 0:
            event_label = QLabel(f"{event_count} جلسه")
            event_label.setStyleSheet(
                f"font-size: 10px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.accent_blue}; "
                f"background: transparent; border: none;"
            )
            event_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(event_label)

        layout.addStretch()
        
        # Store original style for hover effects
        self.original_style = self.styleSheet()
        self.c = c

    def enterEvent(self, event):
        c = theme_manager.current
        self.setStyleSheet(
            f"DayCell {{ background-color: {c.canvas_subtle}; border: 2px solid {c.primary}; "
            f"border-radius: 10px; padding: 6px; }}"
        )
        super().enterEvent(event)

    def leaveEvent(self, event):
        c = theme_manager.current
        bg = c.primary if self.is_today else c.canvas_overlay
        border = f"2px solid {c.primary}" if self.is_today else f"1px solid {c.border_default}"
        self.setStyleSheet(
            f"DayCell {{ background-color: {bg}; border: {border}; border-radius: 10px; padding: 6px; }}"
        )
        super().leaveEvent(event)


class EventCard(QFrame):
    def __init__(self, event, parent=None, on_delete=None, on_reminder=None,
                 on_participants=None, on_invitation=None):
        super().__init__(parent)
        c = theme_manager.current
        priority_color = PRIORITY_COLORS.get(event.priority.value if event.priority else "medium", "#EF6C00")
        official = _event_official(event)
        owner_color = (official.color or priority_color) if official else priority_color

        self.setStyleSheet(
            f"EventCard {{ background-color: {c.canvas_overlay}; border: 1px solid {c.border_default}; "
            f"border-right: 4px solid {owner_color}; border-radius: 12px; padding: 16px; margin: 8px 0; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        # Time section
        time_container = QFrame()
        time_container.setStyleSheet(f"background-color: {c.canvas_subtle}; border-radius: 8px;")
        time_container.setFixedWidth(70)
        time_layout = QVBoxLayout(time_container)
        time_layout.setContentsMargins(8, 8, 8, 8)
        time_layout.setSpacing(2)
        
        time_label = QLabel(event.event_time or "--:--")
        time_label.setStyleSheet(
            f"font-size: 16px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; "
            f"background: transparent; border: none;"
        )
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_layout.addWidget(time_label)
        
        if event.end_time:
            end_label = QLabel(event.end_time)
            end_label.setStyleSheet(
                f"font-size: 10px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
                f"background: transparent; border: none;"
            )
            end_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            time_layout.addWidget(end_label)
        
        time_layout.addStretch()
        layout.addWidget(time_container)

        # Info section
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title_label = QLabel(event.title)
        title_label.setStyleSheet(
            f"font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default}; "
            f"background: transparent; border: none;"
        )
        info_layout.addWidget(title_label)

        if official is not None:
            owner_label = QLabel(f"● {official.display_name}")
            owner_label.setStyleSheet(
                f"font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {owner_color}; "
                f"background: transparent; border: none;"
            )
            info_layout.addWidget(owner_label)

        details = []
        if event.location:
            details.append(f"📍 {event.location}")
        if details:
            det_label = " | ".join(details)
            det_label_widget = QLabel(det_label)
            det_label_widget.setStyleSheet(
                f"font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
                f"background: transparent; border: none;"
            )
            info_layout.addWidget(det_label_widget)

        custom = event.custom_fields or {}
        base = len(custom.get(KEY_CONTACT_IDS) or [])
        invite_count = base + (1 if custom.get(KEY_MANAGER_INVITE) else 0)
        remind_count = base + (1 if custom.get(KEY_MANAGER_REMINDER) else 0)
        if invite_count or remind_count:
            sms_label = QLabel(f"📨 دعوت {invite_count} • یادآوری {remind_count}")
            sms_label.setStyleSheet(
                f"font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.success}; "
                f"background: transparent; border: none;"
            )
            info_layout.addWidget(sms_label)

        layout.addLayout(info_layout, 1)

        # ارسال دستی پیامک یادآوری (حالت «ارسال دستی» یا هر زمان که کاربر بخواهد)
        if on_reminder and str(custom.get(KEY_REMINDER_TEMPLATE) or "").strip():
            reminder_btn = QPushButton("ارسال یادآوری")
            reminder_btn.setFixedHeight(28)
            reminder_btn.setStyleSheet(Styles.table_action_button("primary"))
            reminder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            reminder_btn.clicked.connect(
                lambda checked=False, eid=event.id: on_reminder(eid)
            )
            layout.addWidget(reminder_btn)

        # دعوت‌شدگان و چاپ دعوتنامه (فقط وقتی جلسه دعوت‌شده دارد)
        try:
            from services.repositories import participant_repo as _pref
            has_participants = bool(_pref.get_by_event(event.id))
        except Exception:
            has_participants = False
        if has_participants and on_participants:
            rsvp_btn = QPushButton("دعوت‌شدگان")
            rsvp_btn.setFixedHeight(28)
            rsvp_btn.setStyleSheet(Styles.table_action_button("primary"))
            rsvp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rsvp_btn.clicked.connect(
                lambda checked=False, eid=event.id: on_participants(eid)
            )
            layout.addWidget(rsvp_btn)
        if has_participants and on_invitation:
            invite_btn = QPushButton("دعوتنامه")
            invite_btn.setFixedHeight(28)
            invite_btn.setStyleSheet(Styles.table_action_button("primary"))
            invite_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            invite_btn.clicked.connect(
                lambda checked=False, eid=event.id: on_invitation(eid)
            )
            layout.addWidget(invite_btn)

        # Status section
        status = event.status.value if event.status else "pending"
        status_label = QLabel(STATUS_LABELS.get(status, status))
        status_bg = STATUS_COLORS.get(status, "#F57F17")
        status_label.setStyleSheet(
            f"font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: white; "
            f"background-color: {status_bg}; border-radius: 16px; padding: 6px 14px; border: none;"
        )
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status_label)

        # دکمه حذف — کلیک روی کارت برای ویرایش است، پس حذف دکمه جدا لازم دارد
        if on_delete:
            delete_btn = QPushButton("حذف")
            delete_btn.setFixedHeight(28)
            delete_btn.setStyleSheet(Styles.table_action_button("danger"))
            delete_btn.clicked.connect(lambda checked=False, eid=event.id: on_delete(eid))
            layout.addWidget(delete_btn)

        # Hover effect
        self.original_style = self.styleSheet()
        
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1.0)
        self.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()
    
    def enterEvent(self, event):
        c = theme_manager.current
        self.setStyleSheet(
            f"EventCard {{ background-color: {c.canvas_subtle}; border: 1px solid {c.primary}; "
            f"border-left: 4px solid {c.primary}; border-radius: 12px; padding: 16px; margin: 8px 0; }}"
        )
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.setStyleSheet(self.original_style)
        super().leaveEvent(event)


class ProgramRow(QFrame):
    """یک ردیف از برنامهٔ روزانه/هفتگی مدیر با جزئیات کامل و انتخاب یادآوری."""

    def __init__(self, event, user_id, on_toggle=None, on_open=None, parent=None):
        super().__init__(parent)
        c = theme_manager.current
        self.event = event
        self.user_id = user_id
        self.setStyleSheet(
            f"ProgramRow {{ background-color: {c.canvas_overlay}; border: 1px solid {c.border_default}; "
            f"border-radius: 10px; padding: 10px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # سمت راست (RTL): انتخاب اینکه برنامه پیامک یادآوری داشته باشد یا نه
        self.opt_in = QCheckBox("ارسال در برنامهٔ فردا")
        self.opt_in.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px; "
            f"color: {c.fg_default}; background: transparent; border: none;"
        )
        self.opt_in.setChecked(program.is_opt_in(event))
        self.opt_in.setToolTip(
            "با فعال بودن این گزینه، یک روز قبل (در ساعت تنظیم‌شده) برنامهٔ "
            "این جلسه به‌صورت پیامک جداگانه برای شما ارسال می‌شود."
        )
        self.opt_in.toggled.connect(
            lambda checked, eid=event.id: self._toggle(eid, checked, on_toggle)
        )
        layout.addWidget(self.opt_in, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(event.title or "بدون عنوان")
        title.setStyleSheet(
            f"font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; "
            f"color: {c.fg_default}; background: transparent; border: none;"
        )
        title.setWordWrap(True)
        title_row.addWidget(title, 1)

        badge = QLabel(program.direction_label(event, user_id))
        badge.setStyleSheet(
            f"font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: white; "
            f"background-color: {c.primary if program.direction(event, user_id) == 'sent' else c.success}; "
            f"border-radius: 12px; padding: 5px 12px; border: none;"
        )
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        info.addLayout(title_row)

        start = (event.event_time or "").strip()
        end = (event.end_time or "").strip()
        hours = f"{start} تا {end}" if start and end else (start or "-")
        meta = QLabel(f"🕐 {event.event_date} — {hours}")
        meta.setStyleSheet(
            f"font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.primary}; "
            f"background: transparent; border: none;"
        )
        info.addWidget(meta)

        details = program.program_details(event, user_id)
        body_parts = []
        for label, value in details:
            if label in ("عنوان", "تاریخ", "ساعت", "نوع"):
                continue
            if value and value != "-":
                body_parts.append(f"{label}: {value}")
        if body_parts:
            body = QLabel("\n".join(body_parts))
            body.setStyleSheet(
                f"font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
                f"background: transparent; border: none; line-height: 160%;"
            )
            body.setWordWrap(True)
            info.addWidget(body)

        layout.addLayout(info, 1)

        if on_open:
            open_btn = QPushButton("ویرایش")
            open_btn.setFixedHeight(28)
            open_btn.setStyleSheet(Styles.table_action_button("neutral"))
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.clicked.connect(lambda checked=False, eid=event.id: on_open(eid))
            layout.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignTop)

    @staticmethod
    def _toggle(event_id, checked, on_toggle):
        try:
            program.set_opt_in(event_id, checked)
        except Exception:
            QMessageBox.warning(
                None, "خطا", "ذخیرهٔ انتخاب یادآوری برنامه انجام نشد"
            )
            return
        if on_toggle:
            on_toggle(event_id, checked)


class WeekCell(QFrame):
    """ستون یک روز در نمای هفتگی: سرستون تاریخ + فهرست جمع‌وجور جلسات."""

    def __init__(self, date_str, is_today=False, is_selected=False, parent=None):
        super().__init__(parent)
        c = theme_manager.current
        self.date_str = date_str

        try:
            parts = date_str.split("/")
            day_num, month_num = int(parts[2]), int(parts[1])
            weekday = PERSIAN_WEEKDAYS[jdatetime.date(int(parts[0]), month_num, day_num).weekday()]
        except (IndexError, ValueError):
            day_num, weekday = "", ""

        border = c.primary if is_selected else c.border_default
        bg = c.canvas_subtle if is_today else c.canvas_overlay
        self.setStyleSheet(f"""
            WeekCell {{
                background-color: {bg}; border: 1px solid {border};
                border-top: 3px solid {c.accent_red if weekday == "جمعه" else border};
                border-radius: 8px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        head = QLabel(f"{weekday}\n{day_num}")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {c.primary}; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(head)

        self.events_layout = QVBoxLayout()
        self.events_layout.setSpacing(3)
        lay.addLayout(self.events_layout)
        lay.addStretch()

    def add_event_chip(self, event):
        c = theme_manager.current
        official = _event_official(event)
        color = (official.color or "#EF6C00") if official else "#EF6C00"
        chip = QLabel(f"{(event.event_time or '')[:5]} {event.title[:18]}")
        chip.setToolTip(f"{event.title} — {event.event_time or ''}"
                        + (f" ({official.display_name})" if official else ""))
        chip.setWordWrap(True)
        chip.setStyleSheet(f"""
            QLabel {{
                font-size: 10px; color: {c.fg_default};
                background-color: {c.canvas_subtle};
                border: none; border-right: 3px solid {color};
                border-radius: 4px; padding: 3px 4px;
            }}
        """)
        self.events_layout.addWidget(chip)


class CalendarPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sms_workers = []
        self.view_mode = "month"
        self.setFont(get_font(10))
        today = jdatetime.date.today()
        self.current_year = today.year
        self.current_month = today.month
        self.selected_date = today.strftime("%Y/%m/%d")
        self._setup_ui()
        self._build_calendar()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.prev_btn = QPushButton("ماه قبل")
        self.prev_btn.setFixedHeight(36)
        self.prev_btn.clicked.connect(self._prev_month)
        header.addWidget(self.prev_btn)

        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setStyleSheet(
            f"font-size: 20px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; "
            f"color: {c.fg_default}; background: transparent; border: none;"
        )
        header.addWidget(self.month_label, 1)

        self.next_btn = QPushButton("ماه بعد")
        self.next_btn.setFixedHeight(36)
        self.next_btn.clicked.connect(self._next_month)
        header.addWidget(self.next_btn)

        self.today_btn = QPushButton("امروز")
        self.today_btn.setStyleSheet(Styles.primary_button())
        self.today_btn.clicked.connect(self._go_today)
        header.addWidget(self.today_btn)

        new_event_btn = QPushButton("جلسه جدید")
        new_event_btn.setStyleSheet(Styles.success_button())
        new_event_btn.clicked.connect(self._new_event)
        header.addWidget(new_event_btn)

        self.view_month_btn = QPushButton("ماهانه")
        self.view_month_btn.setCheckable(True)
        self.view_month_btn.setFixedHeight(36)
        self.view_month_btn.clicked.connect(lambda: self._set_view_mode("month"))
        header.addWidget(self.view_month_btn)

        self.view_week_btn = QPushButton("هفتگی")
        self.view_week_btn.setCheckable(True)
        self.view_week_btn.setFixedHeight(36)
        self.view_week_btn.clicked.connect(lambda: self._set_view_mode("week"))
        header.addWidget(self.view_week_btn)

        self.print_program_btn = QPushButton("چاپ برنامه")
        self.print_program_btn.setFixedHeight(36)
        self.print_program_btn.setStyleSheet(Styles.secondary_button())
        self.print_program_btn.clicked.connect(self._print_current_program)
        header.addWidget(self.print_program_btn)

        layout.addLayout(header)

        main_splitter = QHBoxLayout()
        main_splitter.setSpacing(12)

        calendar_frame = QFrame()
        calendar_frame.setStyleSheet(Styles.card())
        frame_layout = QVBoxLayout(calendar_frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(4)

        # --- نمای ماهانه ---
        self.month_box = QWidget()
        cal_layout = QVBoxLayout(self.month_box)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.setSpacing(4)

        weekdays_layout = QHBoxLayout()
        for wd in PERSIAN_WEEKDAYS:
            lbl = QLabel(wd)
            lbl.setStyleSheet(
                f"font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; "
                f"padding: 6px; background: transparent; border: none;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weekdays_layout.addWidget(lbl)
        cal_layout.addLayout(weekdays_layout)

        self.days_grid = QGridLayout()
        self.days_grid.setSpacing(4)
        cal_layout.addLayout(self.days_grid)

        frame_layout.addWidget(self.month_box)

        # --- نمای هفتگی ---
        self.week_box = QWidget()
        week_layout = QVBoxLayout(self.week_box)
        week_layout.setContentsMargins(0, 0, 0, 0)
        week_layout.setSpacing(6)

        self.week_grid = QGridLayout()
        self.week_grid.setSpacing(6)
        week_layout.addLayout(self.week_grid)
        week_layout.addStretch()
        self.week_box.setVisible(False)

        frame_layout.addWidget(self.week_box)

        main_splitter.addWidget(calendar_frame, 60)

        self.events_panel = QFrame()
        self.events_panel.setStyleSheet(Styles.card())
        self.events_panel.setMinimumWidth(380)
        self.events_panel.setMaximumWidth(450)
        events_layout = QVBoxLayout(self.events_panel)
        events_layout.setContentsMargins(16, 16, 16, 16)
        events_layout.setSpacing(12)

        self.events_title = QLabel("جلسات امروز")
        self.events_title.setStyleSheet(
            f"font-size: 16px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; "
            f"padding: 8px 0 12px 0; background: transparent; border: none;"
        )
        events_layout.addWidget(self.events_title)

        self.events_scroll = QScrollArea()
        self.events_scroll.setWidgetResizable(True)
        self.events_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.events_container = QWidget()
        self.events_container.setStyleSheet("background: transparent;")
        self.events_list_layout = QVBoxLayout(self.events_container)
        self.events_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.events_list_layout.setSpacing(10)
        self.events_list_layout.setContentsMargins(0, 0, 0, 0)
        self.events_scroll.setWidget(self.events_container)
        events_layout.addWidget(self.events_scroll)

        main_splitter.addWidget(self.events_panel, 40)
        layout.addLayout(main_splitter)

        layout.addWidget(self._build_program_panel())

        self.stats_layout = QHBoxLayout()
        self.stats_layout.setSpacing(8)
        layout.addLayout(self.stats_layout)

    def _build_program_panel(self):
        c = theme_manager.current
        card = QFrame()
        card.setStyleSheet(Styles.card())
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)

        title = QLabel("برنامه‌های مدیر")
        title.setStyleSheet(
            f"font-size: 16px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; "
            f"color: {c.primary}; background: transparent; border: none;"
        )
        head.addWidget(title)

        self.program_digest_label = QLabel()
        self.program_digest_label.setStyleSheet(
            f"font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
            f"background: transparent; border: none;"
        )
        head.addWidget(self.program_digest_label)
        head.addStretch(1)

        self.program_now_btn = QPushButton("ارسال الان برنامهٔ فردا")
        self.program_now_btn.setFixedHeight(34)
        self.program_now_btn.setStyleSheet(Styles.primary_button())
        self.program_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.program_now_btn.clicked.connect(self._send_program_now)
        head.addWidget(self.program_now_btn)
        lay.addLayout(head)

        self.program_tabs = QTabWidget()
        self.program_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {c.border_default}; border-radius: 8px; "
            f"background: {c.canvas_overlay}; top: -1px; }}"
            f"QTabBar::tab {{ background: {c.canvas_subtle}; color: {c.fg_muted}; "
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 13px; padding: 8px 22px; "
            f"border: 1px solid {c.border_default}; border-bottom: none;"
            f"border-top-left-radius: 8px; border-top-right-radius: 8px; margin-left: 4px; }}"
            f"QTabBar::tab:selected {{ background: {c.canvas_overlay}; color: {c.primary}; font-weight: bold; }}"
        )
        self._program_layouts = {}
        for key, label in (("today", "امروز"), ("week", "این هفته")):
            scroll, row_layout = self._program_tab()
            self._program_layouts[key] = row_layout
            self.program_tabs.addTab(scroll, label)
        self.program_tabs.currentChanged.connect(self._refresh_program)
        # ارتفاع محدود تا صفحهٔ تقویم بیش از حد بلند نشود؛ خود تب اسکرول دارد
        self.program_tabs.setMaximumHeight(380)
        lay.addWidget(self.program_tabs)
        return card

    @staticmethod
    def _program_tab():
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        row_layout = QVBoxLayout(container)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        row_layout.setSpacing(8)
        row_layout.setContentsMargins(4, 4, 4, 8)
        scroll.setWidget(container)
        return scroll, row_layout

    def _update_stats(self):
        c = theme_manager.current
        while self.stats_layout.count():
            item = self.stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = calendar_repo.get_statistics()
        for label_text, value, color in [
            ("امروز", stats.get("today", 0), c.primary),
            ("در انتظار", stats.get("pending", 0), c.warning),
            ("تایید شده", stats.get("confirmed", 0), c.success),
                ("انجام شده", stats.get("completed", 0), c.accent_blue),
        ]:
            card = QFrame()
            card.setStyleSheet(Styles.card_with_padding(8))
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 6, 12, 6)
            val_label = QLabel(str(value))
            val_label.setStyleSheet(
                f"font-size: 20px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {color}; "
                f"background: transparent; border: none;"
            )
            card_layout.addWidget(val_label)
            txt_label = QLabel(label_text)
            txt_label.setStyleSheet(
                f"font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
                f"background: transparent; border: none;"
            )
            card_layout.addWidget(txt_label)
            self.stats_layout.addWidget(card)
        self.stats_layout.addStretch()

    def _set_view_mode(self, mode):
        if mode == self.view_mode:
            return
        self.view_mode = mode
        self._build_calendar()

    def _build_calendar(self):
        c = theme_manager.current
        self.month_box.setVisible(self.view_mode == "month")
        self.week_box.setVisible(self.view_mode == "week")
        self.view_month_btn.setChecked(self.view_mode == "month")
        self.view_week_btn.setChecked(self.view_mode == "week")

        if self.view_mode == "week":
            self._build_week_view()
            self._update_stats()
            self._refresh_program()
            return

        self.month_label.setText(f"{PERSIAN_MONTHS[self.current_month]} {self.current_year}")

        while self.days_grid.count():
            item = self.days_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        first_day = jdatetime.date(self.current_year, self.current_month, 1)
        # در jdatetime شنبه = 0 (ستون اول جدول)؛ +1 همه روزها را یک ستون جابه‌جا می‌کرد
        weekday_offset = first_day.weekday() % 7

        if self.current_month == 12:
            next_month = jdatetime.date(self.current_year + 1, 1, 1)
        else:
            next_month = jdatetime.date(self.current_year, self.current_month + 1, 1)
        days_in_month = (next_month - first_day).days

        events = calendar_repo.get_by_month(self.current_year, self.current_month)
        events_by_day = {}
        for ev in events:
            try:
                day = int(ev.event_date.split("/")[2])
                events_by_day.setdefault(day, []).append(ev)
            except (IndexError, ValueError):
                pass

        today = jdatetime.date.today()
        today_str = today.strftime("%Y/%m/%d")

        row, col = 0, weekday_offset
        for day in range(1, days_in_month + 1):
            date_str = f"{self.current_year:04d}/{self.current_month:02d}/{day:02d}"
            is_today = date_str == today_str
            ev_count = len(events_by_day.get(day, []))
            cell = DayCell(day, is_today, ev_count)
            cell.mousePressEvent = lambda e, d=day, ds=date_str: self._on_day_click(d, ds)
            self.days_grid.addWidget(cell, row, col)
            col += 1
            if col >= 7:
                col = 0
                row += 1

        self._load_events()
        self._update_stats()
        self._refresh_program()

    def _week_start(self, date_str):
        """شنبهٔ هفتهٔ شامل تاریخ داده‌شده."""
        try:
            y, m, d = (int(x) for x in date_str.split("/"))
            base = jdatetime.date(y, m, d)
        except (ValueError, IndexError):
            base = jdatetime.date.today()
        return (base - jdatetime.timedelta(days=base.weekday())).strftime("%Y/%m/%d")

    def _build_week_view(self):
        c = theme_manager.current
        while self.week_grid.count():
            item = self.week_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        start = self._week_start(self.selected_date)
        try:
            sy, sm, sd = (int(x) for x in start.split("/"))
            end_dt = jdatetime.date(sy, sm, sd) + jdatetime.timedelta(days=6)
        except (ValueError, IndexError):
            end_dt = None
        end_str = end_dt.strftime("%Y/%m/%d") if end_dt else ""
        self.month_label.setText(f"هفتهٔ {start} تا {end_str}")

        today_str = jdatetime.date.today().strftime("%Y/%m/%d")

        for i in range(7):
            date_str = self._shift_date(start, i)
            cell = WeekCell(date_str, is_today=(date_str == today_str),
                            is_selected=(date_str == self.selected_date))
            for ev in calendar_repo.get_by_date(date_str):
                if (ev.status.value if ev.status else "") == "cancelled":
                    continue
                cell.add_event_chip(ev)
            cell.mousePressEvent = lambda e, ds=date_str: self._on_week_day_click(ds)
            self.week_grid.addWidget(cell, 0, i)
            self.week_grid.setColumnStretch(i, 1)

        self._load_events()

    def _on_week_day_click(self, date_str):
        self.selected_date = date_str
        self._build_week_view()

    def _current_program_events(self):
        """رویدادهای بازهٔ فعلی (روز انتخابی در نمای ماه، هفته در نمای هفتگی)."""
        if self.view_mode == "week":
            start = self._week_start(self.selected_date)
            end = self._shift_date(start, 6)
            if end < start:
                start, end = end, start
            return calendar_repo.get_range(start, end)
        return calendar_repo.get_by_date(self.selected_date)

    def _print_current_program(self):
        from ui.program_print import print_program
        events = self._current_program_events()
        if self.view_mode == "week":
            start = self._week_start(self.selected_date)
            title, subtitle = "برنامهٔ هفتگی", f"از {start} تا {self._shift_date(start, 6)}"
        else:
            title = "برنامهٔ روزانه"
            try:
                y, m, d = (int(x) for x in self.selected_date.split("/"))
                subtitle = f"{PERSIAN_WEEKDAYS[jdatetime.date(y, m, d).weekday()]} {self.selected_date}"
            except (ValueError, IndexError):
                subtitle = self.selected_date
        print_program(self, title, subtitle, events, owner_of=self._owner_of)

    @staticmethod
    def _owner_of(event):
        official = _event_official(event)
        if official is None:
            return None, None
        return official.color, official.display_name

    def _on_day_click(self, day, date_str):
        self.selected_date = date_str
        self._load_events()

    def _load_events(self):
        c = theme_manager.current
        while self.events_list_layout.count():
            item = self.events_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        events = calendar_repo.get_by_date(self.selected_date)
        try:
            parts = self.selected_date.split("/")
            day_num = int(parts[2])
            month_num = int(parts[1])
            self.events_title.setText(f"جلسات {day_num} {PERSIAN_MONTHS.get(month_num, '')}")
        except (IndexError, ValueError):
            self.events_title.setText("جلسات")

        if not events:
            no_event = QLabel("جلسه‌ای ثبت نشده")
            no_event.setStyleSheet(
                f"font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
                f"padding: 40px; background: transparent; border: 1px dashed {c.border_default}; "
                f"border-radius: 8px;"
            )
            no_event.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.events_list_layout.addWidget(no_event)
            return

        for event in events:
            card = EventCard(event, on_delete=self._delete_event, on_reminder=self._send_reminder_sms,
                             on_participants=self._open_participants,
                             on_invitation=self._print_invitation)
            card.mousePressEvent = lambda e, eid=event.id: self._edit_event(eid)
            self.events_list_layout.addWidget(card)

    def _open_participants(self, event_id):
        from ui.invitation_dialog import ParticipantsDialog
        event = calendar_repo.get_by_id(event_id)
        if not event:
            return
        ParticipantsDialog(event, self).exec()

    def _print_invitation(self, event_id):
        from ui.invitation_dialog import InvitationPreviewDialog
        event = calendar_repo.get_by_id(event_id)
        if not event:
            return
        InvitationPreviewDialog(event, self).exec()

    # ------------------------------------------------------------------ #
    #  برنامهٔ روزانه / هفتگی مدیر
    # ------------------------------------------------------------------ #
    @staticmethod
    def _current_user_id():
        try:
            uid = setting_repo.get_setting("current_user_id")
            return int(uid) if uid else None
        except (TypeError, ValueError):
            return None

    def _refresh_program(self, *_):
        c = theme_manager.current
        if program.digest_enabled():
            self.program_digest_label.setText(
                f"ارسال خودکار برنامهٔ فردا ساعت {program.digest_time()}"
            )
        else:
            self.program_digest_label.setText("ارسال خودکار برنامهٔ فردا غیرفعال است")

        uid = self._current_user_id()
        if uid is None:
            for layout in self._program_layouts.values():
                self._fill_program_layout(layout, [], uid)
            return

        index = 0
        try:
            index = self.program_tabs.currentIndex()
        except Exception:
            pass
        today = jdatetime.date.today()
        if index == 1:
            key = "week"
            # weekday() در jdatetime شنبه=0 است؛ هفته از شنبه شروع می‌شود
            start = today - jdatetime.timedelta(days=today.weekday())
            end = start + jdatetime.timedelta(days=6)
        else:
            key = "today"
            start = end = today

        events = program.get_program(
            uid, start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")
        )
        layout = self._program_layouts.get(key)
        if layout is not None:
            self._fill_program_layout(layout, events, uid)

    def _fill_program_layout(self, layout, events, uid):
        c = theme_manager.current
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not events:
            hint = QLabel("برنامه‌ای برای این بازه ثبت نشده است")
            hint.setStyleSheet(
                f"font-size: 13px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; "
                f"padding: 30px; background: transparent; border: 1px dashed {c.border_default}; "
                f"border-radius: 8px;"
            )
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(hint)
            return

        for event in events:
            layout.addWidget(
                ProgramRow(event, uid, on_open=self._edit_event)
            )

    def _send_program_now(self):
        uid = self._current_user_id()
        if uid is None:
            QMessageBox.warning(self, "برنامهٔ مدیر", "کاربر جاری شناخته نشده است")
            return
        target = program.tomorrow()
        pending = program.pending_events(uid, target, ignore_time=True)
        if not pending:
            QMessageBox.information(
                self,
                "ارسال برنامهٔ فردا",
                "برنامه‌ای برای فردا انتخاب نشده است.\n"
                "«ارسال در برنامهٔ فردا» را کنار ردیف مورد نظر فعال کنید.",
            )
            return
        if not confirm(
            self,
            title="ارسال برنامهٔ فردا",
            message=(
                f"{len(pending)} برنامهٔ {target} هر کدام در یک پیامک جداگانه "
                f"برای شما ارسال شود؟"
            ),
            yes_text="ارسال کن",
        ):
            return

        try:
            user = user_repo.get_by_id(uid)
        except Exception:
            user = None
        mobile = str(getattr(user, "mobile", "") or "") if user else ""
        if not mobile.strip():
            QMessageBox.warning(
                self,
                "ارسال برنامهٔ فردا",
                "شمارهٔ موبایل شما در پروفایل کاربر ثبت نشده است.",
            )
            return

        worker = program.send_program_digest(uid, target, mobile, parent=self)
        worker.done.connect(self._on_program_digest_sent)
        self._sms_workers.append(worker)
        worker.finished.connect(
            lambda w=worker: self._sms_workers.remove(w) if w in self._sms_workers else None
        )
        self.program_now_btn.setEnabled(False)
        worker.start()

    def _on_program_digest_sent(self, result):
        self.program_now_btn.setEnabled(True)
        self._refresh_program()
        if result.get("error"):
            QMessageBox.warning(self, "ارسال برنامهٔ فردا", str(result["error"]))
            return
        lines = [
            f"{result.get('success', 0)} از {result.get('total', 0)} پیامک "
            f"برای برنامهٔ {result.get('target_date')} ارسال شد"
        ]
        failures = [r for r in result.get("results", []) if not r.get("success")]
        if failures:
            lines.append("ارسال ناموفق:")
            for item in failures[:5]:
                lines.append(
                    f"• {item.get('title')}: {item.get('error') or 'خطای نامشخص'}"
                )
        QMessageBox.information(self, "ارسال برنامهٔ فردا", "\n".join(lines))

    def _shift_date(self, date_str, days):
        try:
            y, m, d = (int(x) for x in date_str.split("/"))
            return (jdatetime.date(y, m, d) + jdatetime.timedelta(days=days)).strftime("%Y/%m/%d")
        except (ValueError, IndexError):
            return date_str

    def _prev_month(self):
        if self.view_mode == "week":
            self.selected_date = self._shift_date(self.selected_date, -7)
            self._build_calendar()
            return
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._build_calendar()

    def _next_month(self):
        if self.view_mode == "week":
            self.selected_date = self._shift_date(self.selected_date, 7)
            self._build_calendar()
            return
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._build_calendar()

    def _go_today(self):
        today = jdatetime.date.today()
        self.current_year = today.year
        self.current_month = today.month
        self.selected_date = today.strftime("%Y/%m/%d")
        self._build_calendar()

    def _new_event(self):
        from ui.event_dialog import EventDialog
        dlg = EventDialog(self, default_date=self.selected_date)
        if dlg.exec():
            self._build_calendar()
            self._send_event_sms(dlg.pending_sms)

    def _edit_event(self, event_id):
        from ui.event_dialog import EventDialog
        dlg = EventDialog(self, event_id=event_id)
        if dlg.exec():
            self._build_calendar()
            self._send_event_sms(dlg.pending_sms)

    def _delete_event(self, event_id):
        event = calendar_repo.get_by_id(event_id)
        if not event:
            return
        when = f"{event.event_date} - {event.event_time or ''}".strip(" -")
        if not confirm_delete(self, noun="جلسه", name=f"{event.title} ({when})"):
            return
        try:
            calendar_repo.delete(event_id)
            self._build_calendar()
            QMessageBox.information(self, "موفق", "جلسه حذف شد")
        except Exception as e:
            QMessageBox.critical(self, "خطا در حذف", str(e))

    def _send_event_sms(self, payload):
        if not payload or not payload.get("recipients"):
            return
        worker = EventSMSWorker(payload["recipients"], payload["message"], payload.get("event_id"))
        worker.done.connect(self._on_event_sms_done)
        self._sms_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._sms_workers.remove(w) if w in self._sms_workers else None)
        worker.start()

    def _send_reminder_sms(self, event_id):
        """ارسال دستی پیامک یادآوری از روی کارت جلسه"""
        event = calendar_repo.get_by_id(event_id)
        if not event:
            return
        when = f"{event.event_date} - {event.event_time or ''}".strip(" -")
        if not confirm(
            self,
            title="ارسال پیامک یادآوری",
            message=f"پیامک یادآوری جلسه «{event.title}» ({when}) همین حالا ارسال شود؟",
            yes_text="ارسال کن",
        ):
            return

        worker = send_event_reminder(event_id)
        worker.done.connect(lambda result, eid=event_id: self._on_reminder_sms_done(eid, result))
        self._sms_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._sms_workers.remove(w) if w in self._sms_workers else None)
        worker.start()

    def _on_reminder_sms_done(self, event_id, result):
        if result.get("success"):
            try:
                event = calendar_repo.get_by_id(event_id)
                if event:
                    custom = dict(event.custom_fields or {})
                    custom["sms_reminder_sent_at"] = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
                    custom["sms_reminder_last_result"] = (
                        f"{result.get('success', 0)} از {result.get('total', 0)}"
                    )
                    calendar_repo.update(event_id, custom_fields=custom)
                    self._build_calendar()
            except Exception:
                pass

        if result.get("error"):
            QMessageBox.warning(
                self, "ارسال پیامک", f"ارسال پیامک یادآوری انجام نشد:\n{result['error']}"
            )
            return
        lines = [f"{result.get('success', 0)} پیامک از {result.get('total', 0)} مورد ارسال شد"]
        failures = [r for r in result.get("results", []) if not r.get("success")]
        if failures:
            lines.append("ناموفق:")
            for f in failures[:5]:
                lines.append(f"• {f.get('name') or f.get('mobile')}: {f.get('error') or 'خطای نامشخص'}")
        QMessageBox.information(self, "ارسال پیامک یادآوری", "\n".join(lines))

    def _on_event_sms_done(self, result):
        event_id = result.get("event_id")
        if event_id and result.get("success"):
            event = calendar_repo.get_by_id(event_id)
            if event:
                custom = dict(event.custom_fields or {})
                custom["sms_sent_at"] = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
                custom["sms_last_result"] = f"{result.get('success', 0)} از {result.get('total', 0)}"
                calendar_repo.update(event_id, custom_fields=custom)
                self._build_calendar()

        if result.get("error"):
            QMessageBox.warning(self, "ارسال پیامک", f"ارسال پیامک جلسه انجام نشد:\n{result['error']}")
            return
        lines = [f"{result.get('success', 0)} پیامک از {result.get('total', 0)} مورد ارسال شد"]
        failures = [r for r in result.get("results", []) if not r.get("success")]
        if failures:
            lines.append("ناموفق:")
            for f in failures[:5]:
                lines.append(f"• {f.get('name') or f.get('mobile')}: {f.get('error') or 'خطای نامشخص'}")
        QMessageBox.information(self, "ارسال پیامک", "\n".join(lines))

    def refresh(self):
        self._build_calendar()