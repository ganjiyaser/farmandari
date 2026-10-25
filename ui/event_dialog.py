import logging
import uuid
import jdatetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox,
    QCheckBox, QMessageBox, QTimeEdit, QWidget, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea, QSizePolicy, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTime
from PyQt6.QtGui import QIntValidator
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from models.models import EventType, EventPriority, EventStatus, OfficialPosition
from services.repositories import (
    calendar_repo, contact_repo, user_repo, setting_repo,
    official_repo, participant_repo, holiday_repo
)
from ui.officials_page import position_label
from services import conflict_service
from services.event_sms import (
    DEFAULT_INVITE_TEMPLATE, DEFAULT_REMINDER_TEMPLATE,
    KEY_AUTO_INVITE, KEY_CONTACT_IDS, KEY_INVITE_TEMPLATE,
    KEY_MANAGER_INVITE, KEY_MANAGER_MOBILE, KEY_MANAGER_REMINDER,
    KEY_REMINDER_FIXED_TIME, KEY_REMINDER_MODE, KEY_REMINDER_TEMPLATE,
    REMINDER_MODE_BEFORE, REMINDER_MODE_FIXED, REMINDER_MODE_LABELS,
    REMINDER_MODE_MANUAL, REMINDER_MODE_OFF,
    build_recipients, build_values, render_sms_template,
)
from services.sms_service import is_valid_mobile, normalize_mobile


# کلید setting برای به‌خاطرسپاری آخرین شماره مدیر (جلسهٔ بعدی پیش‌پر می‌شود)
SETTING_MANAGER_MOBILE = "event_sms_manager_mobile"

DEFAULT_SMS_TEMPLATE = DEFAULT_INVITE_TEMPLATE


class EventDialog(QDialog):
    # --- نگاشت‌های ثابت (یک‌بار تعریف می‌شوند و هم در لود و هم در ذخیره استفاده می‌شوند) ---
    EVENT_TYPES = [
        ("جلسه", EventType.MEETING, "meeting"),
        ("همایش", EventType.CONFERENCE, "conference"),
        ("بازدید / دیدار", EventType.VISIT, "visit"),
        ("پیگیری", EventType.FOLLOWUP, "followup"),
        ("یادآوری", EventType.REMINDER, "reminder"),
        ("سایر", EventType.OTHER, "other"),
    ]
    PRIORITIES = [
        ("بالا", EventPriority.HIGH, "high"),
        ("متوسط", EventPriority.MEDIUM, "medium"),
        ("پایین", EventPriority.LOW, "low"),
    ]
    STATUSES = [
        ("در انتظار", EventStatus.PENDING, "pending"),
        ("تایید شده", EventStatus.CONFIRMED, "confirmed"),
        ("لغو شده", EventStatus.CANCELLED, "cancelled"),
        ("انجام شده", EventStatus.COMPLETED, "completed"),
    ]
    REMINDER_OPTIONS = [
        ("۱۵ دقیقه قبل", 15),
        ("۳۰ دقیقه قبل", 30),
        ("۱ ساعت قبل", 60),
        ("۲ ساعت قبل", 120),
    ]

    def __init__(self, parent=None, event_id=None, default_date=None):
        super().__init__(parent)
        self.event_id = event_id
        self.event = None
        self.default_date = default_date
        self.pending_sms = None
        self._selected_sms_ids = set()
        self._contacts_by_id = {}
        if event_id:
            self.event = calendar_repo.get_by_id(event_id)

        self.setWindowTitle("ویرایش جلسه" if event_id else "جلسه جدید")
        # ارتفاع کافی تا هر دو کادر متن پیامک بدون اسکرول دیده شوند؛
        # QScrollArea بدنه فقط برای نمایشگرهای کوتاه ایمنی است
        self.setMinimumSize(1120, 830)
        self.resize(1260, 870)
        self.setFont(get_font(11))

        self._setup_ui()

        if self.event:
            self._load_data()
        else:
            # جلسهٔ جدید: شماره مدیر از آخرین مقدار واردشده پیش‌پر می‌شود ولی
            # انتخاب «کجا ارسال شود» همیشه تصمیم تازهٔ کاربر است
            self.manager_edit.setText(str(setting_repo.get_setting(SETTING_MANAGER_MOBILE, "") or ""))
            self._sync_manager_checks()
            if self.default_date:
                self._set_date_fields(self.default_date)

    # ------------------------------------------------------------------ #
    #  استایل متمرکز و سازنده‌های مشترک ویجت
    # ------------------------------------------------------------------ #
    def _build_stylesheet(self, c):
        return f"""
            QDialog {{ background-color: {c.canvas_default}; }}

            QFrame#card {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 12px;
            }}
            QLabel#sectionTitle {{
                color: {c.primary};
                font-size: 13px;
                font-weight: bold;
            }}
            QLabel#fieldLabel {{
                color: {c.fg_muted};
                font-size: 12px;
            }}
            QLabel#fieldLabelRequired {{
                color: {c.danger};
                font-size: 12px;
                font-weight: bold;
            }}
            QLabel#hint {{
                color: {c.fg_subtle};
                font-size: 11px;
            }}

            QTimeEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 8px;
                padding: 6px 10px;
                font-family: Tahoma;
                font-size: 13px;
                color: {c.fg_default};
            }}
            QTimeEdit:hover {{ border-color: {c.input_border_hover}; }}
            QTimeEdit:focus {{ border-color: {c.input_border_hover}; }}
            QTimeEdit::up-button, QTimeEdit::down-button {{
                subcontrol-origin: border;
                width: 20px;
                border: none;
                background: transparent;
            }}
            QTimeEdit::up-button {{ subcontrol-position: top left; }}
            QTimeEdit::down-button {{ subcontrol-position: bottom left; }}

            QTableWidget {{
                background-color: {c.canvas_overlay};
                alternate-background-color: {c.canvas_subtle};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                border-radius: 8px;
                gridline-color: {c.canvas_subtle};
                font-size: 12px;
                font-family: Tahoma;
            }}
            QTableWidget::item {{ padding: 4px; }}
            QTableWidget::item:selected {{
                background-color: {c.primary};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {c.canvas_subtle};
                color: {c.fg_muted};
                border: none;
                border-bottom: 1px solid {c.border_default};
                padding: 6px;
                font-family: Tahoma;
                font-size: 12px;
                font-weight: bold;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {c.border_default};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """

    def _field_label(self, text, required=False):
        lbl = QLabel(f"{text} *" if required else text)
        lbl.setObjectName("fieldLabelRequired" if required else "fieldLabel")
        lbl.setFont(get_font(11, True))
        return lbl

    def _hint(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        lbl.setFont(get_font(10))
        lbl.setWordWrap(True)
        return lbl

    @staticmethod
    def _flex_height(widget, min_height, grid=None, row=None):
        """sizeHint پیش‌فرض QTextEdit/QTableWidget حدود ۱۹۲px است؛ اگر همان مبنا
        قرار بگیرد ارتفاع طبیعی دیالوگ ~۲۵۰px بیشتر از نیاز می‌شود و اسکرول
        همیشگی ظاهر می‌شود. با Ignored فقط حداقل اعمال و فضای اضافه بعداً پخش
        می‌شود (جداول و کادرهای متن همچنان با بزرگ‌شدن پنجره رشد می‌کنند).

        حداقل ارتفاع باید روی **سطر گرید** گذاشته شود، نه روی خود ویجت:
        setMinimumHeight بر سلول مقدم می‌شود و ویجت از سطر بیرون می‌زند
        (سطرهای بعدی روی آن می‌افتند).
        """
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )
        if grid is not None and row is not None:
            grid.setRowMinimumHeight(row, min_height)

    def _line_edit(self, placeholder=""):
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFont(get_font(11))
        inp.setMinimumHeight(38)
        inp.setStyleSheet(Styles.line_edit())
        return inp

    def _combo(self, items=None):
        combo = QComboBox()
        combo.setFont(get_font(11))
        combo.setMinimumHeight(38)
        combo.setStyleSheet(Styles.combo_box())
        if items:
            combo.addItems(items)
        return combo

    def _check(self, text=""):
        box = QCheckBox(text)
        box.setFont(get_font(11))
        box.setStyleSheet(Styles.checkbox())
        return box

    def _text_edit(self, placeholder=""):
        edit = QTextEdit()
        edit.setFont(get_font(11))
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(Styles.text_edit())
        return edit

    def _time_edit(self, value):
        """ساعت همیشه چپبهراست نمایش داده میشود وگرنه در چیدمان راستبهچپ برعکس دیده میشود"""
        edit = QTimeEdit()
        # باید قبل از setTime اعمال شود؛ وگرنه متن ساعت در چیدمان راست‌به‌چپ برعکس (00:09) می‌شود
        edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        edit.setDisplayFormat("HH:mm")
        edit.setTime(value)
        edit.setFont(get_font(12, True))
        edit.setMinimumHeight(38)
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return edit

    def _card(self, title_text):
        """کارت بخش؛ چیدمان داخلی با QGridLayout در بدنهٔ کارت ساخته می‌شود"""
        frame = QFrame()
        frame.setObjectName("card")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        title.setFont(get_font(12, True))
        outer.addWidget(title)
        return frame, outer

    @staticmethod
    def _grid(column_stretch=(1, 1)):
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for index, stretch in enumerate(column_stretch):
            grid.setColumnStretch(index, stretch)
        return grid

    @staticmethod
    def _add_gap(grid, row):
        """ردیف خالی کشسان تا محتوای کارت در ارتفاع پخش شود"""
        grid.setRowMinimumHeight(row, 6)
        grid.setRowStretch(row, 1)

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(self._build_stylesheet(c))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # ---------------------- سرصفحه ----------------------
        header = QHBoxLayout()
        header.setSpacing(12)

        heading = QLabel("ویرایش جلسه" if self.event_id else "ثبت جلسه جدید")
        heading.setStyleSheet(Styles.title_label())
        heading.setFont(get_font(17, True))
        header.addWidget(heading)
        header.addStretch()

        self.sms_count_label = QLabel("")
        self.sms_count_label.setFont(get_font(11, True))
        self.sms_count_label.setStyleSheet(
            f"color: {c.primary}; background-color: {c.canvas_subtle};"
            f" border: 1px solid {c.border_default}; border-radius: 12px;"
            f" padding: 5px 14px; font-family: Tahoma;"
        )
        header.addWidget(self.sms_count_label)

        # تاریخ آخرین ارسال‌ها در سرصفحه تا کارت پیامک فضای کمتری بگیرد
        self.sms_last_label = QLabel("")
        self.sms_last_label.setFont(get_font(10))
        self.sms_last_label.setStyleSheet(
            f"color: {c.fg_muted}; background: transparent; border: none; font-family: Tahoma;"
        )
        self.sms_last_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter
        )
        header.insertWidget(2, self.sms_last_label)

        main_layout.addLayout(header)

        # ---------------------- بدنه: سه کارت کنار هم ----------------------
        body = QGridLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(14)
        body.setVerticalSpacing(0)
        body.setColumnStretch(0, 28)
        body.setColumnStretch(1, 26)
        body.setColumnStretch(2, 40)
        body.setRowStretch(0, 1)

        self.inputs = {}

        # ==================== کارت ۱: مشخصات جلسه ====================
        card_info, box_info = self._card("مشخصات جلسه")
        info = self._grid()
        box_info.addLayout(info)

        self.inputs["title"] = self._line_edit("مثال: جلسه هماهنگی طرح‌های عمرانی")
        info.addWidget(self._field_label("عنوان جلسه", required=True), 0, 0, 1, 2)
        info.addWidget(self.inputs["title"], 1, 0, 1, 2)
        self._add_gap(info, 2)

        self.date_inputs = {}
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        for field, placeholder, max_len, width, low, high in (
            ("year", "سال", 4, 86, 1300, 1500),
            ("month", "ماه", 2, 60, 1, 12),
            ("day", "روز", 2, 60, 1, 31),
        ):
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setFont(get_font(12, True))
            edit.setMaxLength(max_len)
            edit.setFixedWidth(width)
            edit.setMinimumHeight(38)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.setValidator(QIntValidator(low, high, self))
            edit.setStyleSheet(Styles.line_edit())
            self.date_inputs[field] = edit
            date_row.addWidget(edit)

        today_btn = QPushButton("امروز")
        today_btn.setMinimumHeight(38)
        today_btn.setFont(get_font(10, True))
        today_btn.setStyleSheet(Styles.secondary_button())
        today_btn.clicked.connect(self._use_today)
        date_row.addWidget(today_btn)
        date_row.addStretch()

        self._use_today()

        date_widget = QWidget()
        date_widget.setLayout(date_row)
        info.addWidget(self._field_label("تاریخ شمسی", required=True), 3, 0, 1, 2)
        info.addWidget(date_widget, 4, 0, 1, 2)
        self._add_gap(info, 5)

        self.time_start = self._time_edit(QTime(9, 0))
        self.time_end = self._time_edit(QTime(11, 0))
        # اگر ساعت شروع از پایان جلو زد، پایان یک ساعت بعد تنظیم شود
        self.time_start.timeChanged.connect(self._sync_end_time)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        time_row.addWidget(self._field_label("از"))
        time_row.addWidget(self.time_start, 1)
        time_row.addWidget(self._field_label("تا"))
        time_row.addWidget(self.time_end, 1)

        self.suggest_btn = QPushButton("زمان آزاد؟")
        self.suggest_btn.setMinimumHeight(38)
        self.suggest_btn.setFont(get_font(10, True))
        self.suggest_btn.setStyleSheet(Styles.secondary_button())
        self.suggest_btn.setToolTip(
            "اولین تاریخ و ساعت آزادِ مشترک صاحب برنامه و مسئولین دعوت‌شده")
        self.suggest_btn.clicked.connect(self._suggest_free_slot)
        time_row.addWidget(self.suggest_btn)

        time_widget = QWidget()
        time_widget.setLayout(time_row)
        info.addWidget(self._field_label("ساعت برگزاری"), 6, 0, 1, 2)
        info.addWidget(time_widget, 7, 0, 1, 2)
        self._add_gap(info, 8)

        self.event_type = self._combo([label for label, _, _ in self.EVENT_TYPES])
        self.priority = self._combo([label for label, _, _ in self.PRIORITIES])
        self.priority.setCurrentIndex(1)

        info.addWidget(self._field_label("نوع جلسه"), 9, 0)
        info.addWidget(self._field_label("اولویت"), 9, 1)
        info.addWidget(self.event_type, 10, 0)
        info.addWidget(self.priority, 10, 1)
        self._add_gap(info, 11)

        self.status_combo = self._combo([label for label, _, _ in self.STATUSES])
        self.inputs["location"] = self._line_edit("مثال: سالن اجتماعات فرمانداری")

        info.addWidget(self._field_label("وضعیت"), 12, 0)
        info.addWidget(self._field_label("مکان"), 12, 1)
        info.addWidget(self.status_combo, 13, 0)
        info.addWidget(self.inputs["location"], 13, 1)
        self._add_gap(info, 14)

        # مسئولین دعوت‌شده: تیک‌خورده‌ها به‌عنوان شرکت‌کننده ثبت و برایشان پیامک می‌رود
        self.invited_list = QListWidget()
        self.invited_list.setFont(get_font(10))
        self.invited_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._flex_height(self.invited_list, 96, info, 16)
        self.invited_list.setStyleSheet(
            f"QListWidget {{ background-color: {c.input_bg}; color: {c.fg_default};"
            f" border: 1px solid {c.input_border}; border-radius: 6px; padding: 6px;"
            f" font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px; }}"
            f" QListWidget::item {{ padding: 5px 4px; border: none; }}"
            f" QListWidget::item:hover {{ background-color: {c.primary_subtle}; }}"
        )
        self._fill_invited_officials()

        info.addWidget(
            self._field_label("مسئولین دعوت‌شده (ثبت شرکت‌کننده + ارسال پیامک)"),
            15, 0, 1, 2,
        )
        info.addWidget(self.invited_list, 16, 0, 1, 2)
        info.setRowStretch(16, 1)

        body.addWidget(card_info, 0, 0)

        # ============ کارت ۲: یادآوری و توضیحات ============
        card_extra, box_extra = self._card("یادآوری، ارتباط و توضیحات")
        extra = self._grid((0, 1))
        box_extra.addLayout(extra)

        # حالت ارسال پیامک یادآوری — هر سه قابلیت و به انتخاب کاربر
        self.reminder_mode = self._combo([label for _, label in REMINDER_MODE_LABELS])
        self.reminder_mode.setCurrentIndex(1)  # پیش‌فرض: چند دقیقه قبل از جلسه
        self.reminder_mode.currentIndexChanged.connect(self._sync_reminder_mode)
        extra.addWidget(self._field_label("ارسال پیامک یادآوری"), 0, 0)
        extra.addWidget(self.reminder_mode, 1, 0)

        self.reminder_minutes = self._combo([label for label, _ in self.REMINDER_OPTIONS])
        self.reminder_minutes.setCurrentIndex(1)
        self.reminder_fixed_time = self._time_edit(QTime(8, 0))

        detail_widget = QWidget()
        detail_row = QHBoxLayout(detail_widget)
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_row.setSpacing(8)
        detail_row.addWidget(self._field_label("زمان"))
        detail_row.addWidget(self.reminder_minutes, 1)
        detail_row.addWidget(self.reminder_fixed_time, 1)
        detail_row.addStretch(1)
        self.reminder_detail = detail_widget
        extra.addWidget(detail_widget, 1, 0)
        self._add_gap(extra, 2)
        self._sync_reminder_mode()

        self.official_combo = self._combo()
        self.official_combo.addItem("-- بدون مسئول --", None)
        for official in official_repo.get_active(limit=200):
            self.official_combo.addItem(
                f"{official.display_name} — {position_label(official.position)}",
                official.id,
            )

        self.contact_combo = self._combo()
        self.contact_combo.addItem("-- بدون مخاطب --", None)
        for contact in contact_repo.get_active(limit=500):
            self.contact_combo.addItem(f"{contact.first_name} {contact.last_name}", contact.id)

        extra.addWidget(self._field_label("صاحب برنامه (مسئول جلسه)"), 3, 0)
        extra.addWidget(self.official_combo, 4, 0)
        extra.addWidget(self._field_label("مخاطب مرتبط"), 3, 1)
        extra.addWidget(self.contact_combo, 4, 1)

        self.inputs["host"] = self._line_edit("مثال: فرماندار، رئیس اداره آموزش و پرورش")
        extra.addWidget(self._field_label("میزبان / مقام ملاقات (برای بازدید)"), 5, 0, 1, 2)
        extra.addWidget(self.inputs["host"], 6, 0, 1, 2)
        self._add_gap(extra, 7)

        self.description = self._text_edit("توضیحات، دستور جلسه یا نکات لازم...")
        self._flex_height(self.description, 150, extra, 10)

        extra.addWidget(self._field_label("توضیحات"), 9, 0)
        extra.addWidget(self.description, 10, 0)
        extra.setRowStretch(10, 1)

        body.addWidget(card_extra, 0, 1)

        # ============ کارت ۳: اعضای جلسه و پیامک ============
        card_sms, box_sms = self._card("اعضای جلسه و پیامک")
        sms_grid = self._grid((1, 1))
        box_sms.addLayout(sms_grid)

        self.sms_contact_search = QLineEdit()
        self.sms_contact_search.setPlaceholderText("جستجوی نام یا شماره برای افزودن به اعضای جلسه...")
        self.sms_contact_search.setFont(get_font(11))
        self.sms_contact_search.setMinimumHeight(38)
        self.sms_contact_search.setStyleSheet(Styles.search_input())
        self.sms_contact_search.setClearButtonEnabled(True)
        self.sms_contact_search.textChanged.connect(self._filter_sms_contacts)
        sms_grid.addWidget(self.sms_contact_search, 0, 0, 1, 2)

        self.sms_table = QTableWidget()
        self.sms_table.setColumnCount(3)
        self.sms_table.setHorizontalHeaderLabels(["انتخاب", "نام", "موبایل"])
        table_header = self.sms_table.horizontalHeader()
        table_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.sms_table.setAlternatingRowColors(True)
        self.sms_table.setShowGrid(False)
        self.sms_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sms_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sms_table.verticalHeader().setVisible(False)
        self.sms_table.verticalHeader().setDefaultSectionSize(30)
        self.sms_table.itemChanged.connect(self._on_sms_item_changed)
        self.sms_table.itemClicked.connect(self._toggle_sms_row)
        sms_grid.addWidget(self.sms_table, 1, 0, 1, 2)
        sms_grid.setRowStretch(1, 1)
        self._flex_height(self.sms_table, 150, sms_grid, 1)

        sms_grid.addWidget(self._hint("برای انتخاب سریع، روی ردیف مخاطب کلیک کنید"), 2, 0, 1, 2)

        self.sms_auto_check = self._check("ارسال خودکار دعوت‌نامه پس از ذخیره جلسه")
        self.sms_auto_check.setChecked(True)
        sms_grid.addWidget(self.sms_auto_check, 3, 0, 1, 2)

        # ---- شماره مدیر: کاربر خودش وارد می‌کند (شمارهٔ صاحب نرم‌افزار حذف شد) ----
        sms_grid.addWidget(self._field_label("ارسال پیامک برای مدیر"), 4, 0, 1, 2)

        self.manager_invite_check = self._check("در زمان ثبت (دعوت‌نامه)")
        self.manager_reminder_check = self._check("در زمان یادآوری")
        self.manager_invite_check.stateChanged.connect(lambda _: self._update_sms_count())
        self.manager_reminder_check.stateChanged.connect(lambda _: self._update_sms_count())

        self.manager_edit = self._line_edit("شماره موبایل مدیر — خالی بماند یعنی بدون پیامک به مدیر")
        self.manager_edit.setClearButtonEnabled(True)
        self.manager_edit.textChanged.connect(self._sync_manager_checks)
        sms_grid.addWidget(self.manager_edit, 5, 0, 1, 2)

        sms_grid.addWidget(self.manager_invite_check, 6, 0)
        sms_grid.addWidget(self.manager_reminder_check, 6, 1)

        # ---- دو متن پیامک که هر دو هنگام ثبت جلسه نوشته می‌شوند ----
        sms_grid.addWidget(self._field_label("متن دعوت‌نامه (ارسال هنگام ثبت جلسه)"), 7, 0, 1, 2)

        self.sms_template = self._text_edit()
        self.sms_template.setPlainText(DEFAULT_INVITE_TEMPLATE)
        sms_grid.addWidget(self.sms_template, 8, 0, 1, 2)
        self._flex_height(self.sms_template, 84, sms_grid, 8)

        sms_grid.addWidget(self._field_label("متن یادآوری (ارسال در زمان انتخاب‌شده)"), 9, 0, 1, 2)

        self.reminder_template = self._text_edit()
        self.reminder_template.setPlainText(DEFAULT_REMINDER_TEMPLATE)
        sms_grid.addWidget(self.reminder_template, 10, 0, 1, 2)
        self._flex_height(self.reminder_template, 84, sms_grid, 10)

        sms_grid.addWidget(
            self._hint("متغیرهای قابل استفاده: {عنوان} {تاریخ} {ساعت} {مکان} {نوع}"),
            11, 0, 1, 2
        )

        body.addWidget(card_sms, 0, 2)

        # بدنه در QScrollArea تا روی نمایشگرهای کوتاه متن‌ها بریده نشود
        body_host = QWidget()
        body_host.setLayout(body)
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        body_scroll.setWidget(body_host)
        body_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        main_layout.addWidget(body_scroll, 1)

        # ---------------------- دکمه‌ها ----------------------
        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        self.save_btn = QPushButton("ذخیره جلسه")
        self.save_btn.setMinimumHeight(44)
        self.save_btn.setMinimumWidth(150)
        self.save_btn.setFont(get_font(12, True))
        self.save_btn.setStyleSheet(Styles.primary_button())
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton("انصراف")
        cancel_btn.setMinimumHeight(44)
        cancel_btn.setMinimumWidth(120)
        cancel_btn.setFont(get_font(12, True))
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)

        buttons.addStretch()
        buttons.addWidget(self.save_btn)
        buttons.addWidget(cancel_btn)
        main_layout.addLayout(buttons)

        self._load_sms_contacts()

    def _use_today(self):
        today = jdatetime.date.today()
        self.date_inputs["year"].setText(str(today.year))
        self.date_inputs["month"].setText(f"{today.month:02d}")
        self.date_inputs["day"].setText(f"{today.day:02d}")

    def _toggle_sms_row(self, item):
        """کلیک روی هر جای ردیف، وضعیت تیک انتخاب را برمی‌گرداند"""
        if not item or item.column() == 0:
            return
        check_item = self.sms_table.item(item.row(), 0)
        if not check_item:
            return
        check_item.setCheckState(
            Qt.CheckState.Unchecked
            if check_item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )

    # ------------------------------------------------------------------ #
    #  کمکی‌ها
    # ------------------------------------------------------------------ #
    def _set_date_fields(self, date_str):
        parts = date_str.split("/")
        if len(parts) == 3:
            self.date_inputs["year"].setText(parts[0])
            self.date_inputs["month"].setText(parts[1])
            self.date_inputs["day"].setText(parts[2])

    def _sync_end_time(self, new_start: QTime):
        if self.time_end.time() <= new_start:
            self.time_end.setTime(new_start.addSecs(3600))

    @staticmethod
    def _index_by_value(options, value, key_index=2, default=0):
        for i, opt in enumerate(options):
            if opt[key_index] == value:
                return i
        return default

    def _set_combo_by_data(self, combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _reminder_mode_key(self) -> str:
        index = self.reminder_mode.currentIndex()
        if 0 <= index < len(REMINDER_MODE_LABELS):
            return REMINDER_MODE_LABELS[index][0]
        return REMINDER_MODE_OFF

    def _set_reminder_mode(self, mode: str):
        for i, (key, _) in enumerate(REMINDER_MODE_LABELS):
            if key == mode:
                self.reminder_mode.setCurrentIndex(i)
                return
        self.reminder_mode.setCurrentIndex(1)

    def _sync_reminder_mode(self, *_):
        """نمایش کنترل زمانِ متناسب با حالت انتخابی یادآوری"""
        mode = self._reminder_mode_key()
        show_minutes = mode == REMINDER_MODE_BEFORE
        show_fixed = mode == REMINDER_MODE_FIXED
        self.reminder_minutes.setVisible(show_minutes)
        self.reminder_fixed_time.setVisible(show_fixed)
        self.reminder_detail.setVisible(show_minutes or show_fixed)

    def _sync_manager_checks(self, *_):
        """چک‌باکس‌های «کجا برای مدیر ارسال شود» فقط با شمارهٔ معتبر فعال می‌شوند"""
        valid = is_valid_mobile(self.manager_edit.text())
        self.manager_invite_check.setEnabled(valid)
        self.manager_reminder_check.setEnabled(valid)
        if not valid:
            self.manager_invite_check.setChecked(False)
            self.manager_reminder_check.setChecked(False)
        self._update_sms_count()

    def _manager_included(self, key: str) -> bool:
        box = self.manager_invite_check if key == KEY_MANAGER_INVITE else self.manager_reminder_check
        return bool(box.isChecked() and box.isEnabled() and is_valid_mobile(self.manager_edit.text()))

    # ------------------------------------------------------------------ #
    #  اعضای جلسه و پیامک
    # ------------------------------------------------------------------ #
    def _load_sms_contacts(self, search_text=""):
        self.sms_table.blockSignals(True)
        try:
            if search_text and search_text.strip():
                contacts = contact_repo.search(search_text.strip(), limit=500)
            else:
                contacts = contact_repo.get_active(limit=2000) or contact_repo.get_all(limit=2000)
            contacts = [c for c in contacts if (c.mobile or "").strip()]

            self._contacts_by_id = {c.id: c for c in contacts}
            self.sms_table.setRowCount(len(contacts))
            for row, contact in enumerate(contacts):
                check_item = QTableWidgetItem()
                check_item.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                check_item.setData(Qt.ItemDataRole.UserRole, contact.id)
                check_item.setCheckState(
                    Qt.CheckState.Checked if contact.id in self._selected_sms_ids
                    else Qt.CheckState.Unchecked
                )
                self.sms_table.setItem(row, 0, check_item)
                self.sms_table.setItem(
                    row, 1, QTableWidgetItem(f"{contact.first_name or ''} {contact.last_name or ''}".strip())
                )
                self.sms_table.setItem(row, 2, QTableWidgetItem(contact.mobile or "-"))
                self.sms_table.setRowHeight(row, 30)
        finally:
            self.sms_table.blockSignals(False)
        self._update_sms_count()

    def _filter_sms_contacts(self, text):
        self._load_sms_contacts(text)

    def _on_sms_item_changed(self, item):
        if not item or item.column() != 0:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_sms_ids.add(cid)
        else:
            self._selected_sms_ids.discard(cid)
        self._update_sms_count()

    def _update_sms_count(self):
        base = len(self._selected_sms_ids)
        invite = base + (1 if self._manager_included(KEY_MANAGER_INVITE) else 0)
        remind = base + (1 if self._manager_included(KEY_MANAGER_REMINDER) else 0)
        self.sms_count_label.setText(f"{invite} دعوت • {remind} یادآوری")

    def _fill_invited_officials(self, selected=None):
        """فهرست مسئولین (فرماندار/معاونین/بخشداران) برای انتخاب دعوت‌شدگان"""
        selected = {int(x) for x in (selected or set())}
        try:
            officials = official_repo.get_active(limit=200)
        except Exception:
            officials = []
        self.invited_list.clear()
        for official in officials:
            label = official.display_name or f"مسئول {official.id}"
            mobile = (getattr(official, "mobile", "") or "").strip()
            text = f"{label} — {position_label(official.position)}"
            if mobile:
                text += f" — {mobile}"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if official.id in selected else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, int(official.id))
            if official.color:
                from PyQt6.QtGui import QColor
                item.setForeground(QColor(official.color))
            self.invited_list.addItem(item)

    def _invited_official_ids(self) -> list:
        ids = []
        for index in range(self.invited_list.count()):
            item = self.invited_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                try:
                    ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
                except (TypeError, ValueError):
                    continue
        return sorted(ids)

    def _event_participants_for_conflict(self) -> list:
        """همهٔ مسئولین مرتبط با جلسه: صاحب برنامه + دعوت‌شدگان (بدون تکرار)"""
        ids = list(self._invited_official_ids())
        owner = self.official_combo.currentData()
        if owner and owner not in ids:
            ids.append(owner)
        return ids

    def _suggest_free_slot(self):
        """اولین تاریخ/ساعت آزاد مشترک را در فیلدهای تاریخ و ساعت می‌نشیند"""
        official_ids = self._event_participants_for_conflict()
        if not official_ids:
            QMessageBox.information(
                self, "زمان آزاد",
                "ابتدا «صاحب برنامه» یا «مسئولین دعوت‌شده» را انتخاب کنید.")
            return

        start = self.time_start.time()
        end = self.time_end.time()
        duration = max(15, start.secsTo(end) // 60)
        current = (f"{self.date_inputs['year'].text().strip()}/"
                   f"{self.date_inputs['month'].text().strip().zfill(2)}/"
                   f"{self.date_inputs['day'].text().strip().zfill(2)}")

        result = conflict_service.suggest_next_free(
            official_ids=official_ids, duration_minutes=duration,
            from_date=current, exclude_event_id=self.event_id,
        )
        if not result:
            QMessageBox.information(
                self, "زمان آزاد",
                "در ۳۰ روز آینده بازهٔ آزاد مشترکی پیدا نشد.")
            return

        y, m, d = result["date"].split("/")
        self.date_inputs["year"].setText(y)
        self.date_inputs["month"].setText(m)
        self.date_inputs["day"].setText(d)
        h, mi = result["start"].split(":")
        self.time_start.setTime(QTime(int(h), int(mi)))
        h, mi = result["end"].split(":")
        self.time_end.setTime(QTime(int(h), int(mi)))
        QMessageBox.information(
            self, "زمان آزاد",
            f"اولین بازهٔ آزاد مشترک:\n{result['date']} از {result['start']} تا {result['end']}")

    def _sms_custom(self) -> dict:
        """فیلدهای سفارشی پیامک بر اساس وضعیت فعلی دیالوگ"""
        custom = dict(self.event.custom_fields or {}) if self.event else {}
        custom[KEY_CONTACT_IDS] = sorted(self._selected_sms_ids)
        custom[KEY_OFFICIAL_IDS] = self._invited_official_ids()
        custom[KEY_MANAGER_MOBILE] = normalize_mobile(self.manager_edit.text().strip())
        custom[KEY_MANAGER_INVITE] = self._manager_included(KEY_MANAGER_INVITE)
        custom[KEY_MANAGER_REMINDER] = self._manager_included(KEY_MANAGER_REMINDER)
        custom[KEY_INVITE_TEMPLATE] = self.sms_template.toPlainText().strip()
        custom[KEY_REMINDER_TEMPLATE] = self.reminder_template.toPlainText().strip()
        custom[KEY_AUTO_INVITE] = self.sms_auto_check.isChecked()
        custom[KEY_REMINDER_MODE] = self._reminder_mode_key()
        custom[KEY_REMINDER_FIXED_TIME] = self.reminder_fixed_time.time().toString("HH:mm")
        return custom

    def _build_sms_payload(self, event_id, values, custom):
        """فهرست گیرندگان و متن نهایی دعوت‌نامه؛ اگر ارسال خودکار خاموش باشد None"""
        if not self.sms_auto_check.isChecked():
            return None

        recipients = build_recipients(custom, bool(custom.get(KEY_MANAGER_INVITE)))
        if not recipients:
            return None

        return {
            "event_id": event_id,
            "recipients": recipients,
            "message": render_sms_template(custom.get(KEY_INVITE_TEMPLATE) or "", values),
        }

    # ------------------------------------------------------------------ #
    #  بارگذاری داده
    # ------------------------------------------------------------------ #
    def _load_data(self):
        e = self.event
        self.inputs["title"].setText(e.title or "")

        if e.event_date:
            self._set_date_fields(e.event_date)

        if e.event_time:
            try:
                h, m = e.event_time.split(":")
                self.time_start.setTime(QTime(int(h), int(m)))
            except (ValueError, TypeError):
                pass
        if e.end_time:
            try:
                h, m = e.end_time.split(":")
                self.time_end.setTime(QTime(int(h), int(m)))
            except (ValueError, TypeError):
                pass

        self.inputs["location"].setText(e.location or "")

        self.event_type.setCurrentIndex(self._index_by_value(
            self.EVENT_TYPES, e.event_type.value if e.event_type else "meeting"))
        self.priority.setCurrentIndex(self._index_by_value(
            self.PRIORITIES, e.priority.value if e.priority else "medium", default=1))
        self.status_combo.setCurrentIndex(self._index_by_value(
            self.STATUSES, e.status.value if e.status else "pending"))

        self._set_combo_by_data(self.contact_combo, e.contact_id)

        reminder_idx = next(
            (i for i, (_, mins) in enumerate(self.REMINDER_OPTIONS) if mins == e.reminder_minutes),
            1,
        )
        self.reminder_minutes.setCurrentIndex(reminder_idx)

        self.description.setPlainText(e.description or "")

        custom = e.custom_fields or {}
        # شرکت‌کنندگان از جدول event_participants خوانده می‌شوند
        try:
            parts = participant_repo.get_by_event(e.id)
        except Exception:
            parts = []
        self._fill_invited_officials([p.official_id for p in parts if p.official_id])
        self._selected_sms_ids = {
            int(p.contact_id) for p in parts if p.contact_id
        }

        # شماره مدیر و اینکه کجا ارسال شود
        self.manager_edit.setText(str(custom.get(KEY_MANAGER_MOBILE) or ""))
        self.manager_invite_check.setChecked(bool(custom.get(KEY_MANAGER_INVITE)))
        self.manager_reminder_check.setChecked(bool(custom.get(KEY_MANAGER_REMINDER)))
        self._sync_manager_checks()

        # هر دو متن پیامک هنگام ثبت جلسه نوشته و ذخیره می‌شوند
        self.sms_template.setPlainText(custom.get(KEY_INVITE_TEMPLATE) or DEFAULT_INVITE_TEMPLATE)
        self.reminder_template.setPlainText(
            custom.get(KEY_REMINDER_TEMPLATE) or DEFAULT_REMINDER_TEMPLATE
        )

        mode = custom.get(KEY_REMINDER_MODE)
        if not mode:
            # جلسات قدیمی: حالت از ستون reminder_enabled استخراج می‌شود
            mode = REMINDER_MODE_BEFORE if e.reminder_enabled else REMINDER_MODE_OFF
        self._set_reminder_mode(mode)
        fixed = str(custom.get(KEY_REMINDER_FIXED_TIME) or "08:00")
        try:
            fh, fm = fixed.split(":")
            self.reminder_fixed_time.setTime(QTime(int(fh), int(fm)))
        except (ValueError, TypeError):
            pass
        self._sync_reminder_mode()

        last_parts = []
        if custom.get("sms_sent_at"):
            last_parts.append(
                f"دعوت {custom.get('sms_sent_at')} ({custom.get('sms_last_result', '')})"
            )
        if custom.get("sms_reminder_sent_at"):
            last_parts.append(f"یادآوری {custom.get('sms_reminder_sent_at')}")
        if last_parts:
            self.sms_last_label.setText("آخرین ارسال: " + "، ".join(last_parts))
            # پیامک قبلاً ارسال شده؛ برای ارسال مجدد باید کاربر خودش تیک بزند
            self.sms_auto_check.setChecked(False)

        self._load_sms_contacts(self.sms_contact_search.text())

    # ------------------------------------------------------------------ #
    #  اعتبارسنجی و ذخیره
    # ------------------------------------------------------------------ #
    def _validate(self):
        title = self.inputs["title"].text().strip()
        if not title:
            return "عنوان جلسه الزامی است"

        year = self.date_inputs["year"].text().strip()
        month = self.date_inputs["month"].text().strip()
        day = self.date_inputs["day"].text().strip()
        if not (year and month and day):
            return "تاریخ را کامل وارد کنید"

        try:
            jdatetime.date(int(year), int(month), int(day))
        except ValueError:
            return "تاریخ شمسی وارد شده معتبر نیست"

        if self.time_end.time() <= self.time_start.time():
            return "ساعت پایان باید بعد از ساعت شروع باشد"

        if not self.sms_template.toPlainText().strip():
            return "متن دعوت‌نامه پیامک را وارد کنید"

        if not self.reminder_template.toPlainText().strip():
            return "متن یادآوری پیامک را وارد کنید"

        if (self.manager_invite_check.isChecked() or self.manager_reminder_check.isChecked()):
            if not is_valid_mobile(normalize_mobile(self.manager_edit.text().strip())):
                return "شماره موبایل مدیر معتبر نیست"

        return None

    def _check_conflicts(self, data: dict) -> bool:
        """True یعنی تداخل هست و کاربر با ثبت موافقت نکرد (باید ذخیره متوقف شود)."""
        official_ids = self._event_participants_for_conflict()
        if not official_ids and not self._selected_sms_ids:
            return False

        lines = []
        official_names = {}
        for oid in official_ids:
            conflicts = conflict_service.find_conflicts(
                event_date=data["event_date"], event_time=data["event_time"],
                end_time=data["end_time"], official_id=oid,
                exclude_event_id=self.event_id,
            )
            if not conflicts:
                continue
            official = official_repo.get_by_id(oid)
            name = official.display_name if official else f"مسئول {oid}"
            official_names[oid] = name
            lines.append(f"{name}:")
            lines.append(conflict_service.format_conflict_message(conflicts, official_names))

        for cid in self._selected_sms_ids:
            conflicts = conflict_service.find_conflicts(
                event_date=data["event_date"], event_time=data["event_time"],
                end_time=data["end_time"], contact_id=cid,
                exclude_event_id=self.event_id,
            )
            if not conflicts:
                continue
            contact = contact_repo.get_by_id(cid)
            name = contact.display_name if contact else f"مخاطب {cid}"
            lines.append(f"{name}:")
            lines.append(conflict_service.format_conflict_message(conflicts))

        if not lines:
            return False

        answer = QMessageBox.question(
            self, "تداخل برنامه",
            "زمان این جلسه با برنامهٔ افراد زیر تداخل دارد:\n\n"
            + "\n".join(lines)
            + "\n\nثبت جلسه با وجود تداخل، توصیه نمی‌شود. ادامه می‌دهید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer != QMessageBox.StandardButton.Yes

    def _save(self):
        error = self._validate()
        if error:
            QMessageBox.warning(self, "خطا", error)
            return

        year = self.date_inputs["year"].text().strip()
        month = self.date_inputs["month"].text().strip().zfill(2)
        day = self.date_inputs["day"].text().strip().zfill(2)

        reminder_mode = self._reminder_mode_key()
        data = {
            "title": self.inputs["title"].text().strip(),
            "event_date": f"{year}/{month}/{day}",
            "event_time": self.time_start.time().toString("HH:mm"),
            "end_time": self.time_end.time().toString("HH:mm"),
            "location": self.inputs["location"].text().strip() or None,
            "event_type": self.EVENT_TYPES[self.event_type.currentIndex()][1],
            "priority": self.PRIORITIES[self.priority.currentIndex()][1],
            "status": self.STATUSES[self.status_combo.currentIndex()][1],
            # در حالت «دستی» و «غیرفعال» یادآوری خودکار (اعلان و پیامک) انجام نمی‌شود
            "reminder_enabled": reminder_mode in (REMINDER_MODE_BEFORE, REMINDER_MODE_FIXED),
            "reminder_minutes": self.REMINDER_OPTIONS[self.reminder_minutes.currentIndex()][1],
            "reminder_sent": False,
            "contact_id": self.contact_combo.currentData(),
            "official_id": self.official_combo.currentData(),
            "host": self.inputs["host"].text().strip() or None,
            "description": self.description.toPlainText().strip() or None,
        }

        # ---------- هشدار تعطیل رسمی ----------
        try:
            holiday = holiday_repo.get_by_date(data["event_date"])
        except Exception:
            holiday = None
        if holiday is not None:
            answer = QMessageBox.question(
                self, "روز تعطیل",
                f"تاریخ «{data['event_date']}» تعطیل رسمی است ({holiday.title}).\n"
                "آیا ثبت این جلسه در روز تعطیل عمدی است؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        # ---------- بررسی تداخل برنامهٔ مسئولین ----------
        if self._check_conflicts(data):
            return  # کاربر ثبت در زمان تداخل را رد کرد

        sms_values = build_values(
            title=data["title"],
            event_date=data["event_date"],
            event_time=data["event_time"],
            end_time=data["end_time"],
            location=data["location"],
            event_type=data["event_type"],
        )

        custom = self._sms_custom()
        data["custom_fields"] = custom

        # user_id در مدل Event اجباری است؛ اگر کاربر جاری مشخص نبود از admin استفاده میشود
        user_id = None
        try:
            user_id = setting_repo.get_setting("current_user_id")
        except Exception:
            user_id = None
        if not user_id:
            admin_user = user_repo.get_by_username("admin")
            if admin_user:
                user_id = admin_user.id
        if user_id:
            data["user_id"] = user_id
        else:
            QMessageBox.critical(self, "خطا", "کاربر ثبتکننده مشخص نیست. با حساب مدیر وارد شوید.")
            return

        try:
            if self.event_id:
                calendar_repo.update(self.event_id, **data)
                event_id = self.event_id
                QMessageBox.information(self, "موفق", "جلسه ویرایش شد")
            else:
                data["uuid"] = str(uuid.uuid4())
                created = calendar_repo.create(**data)
                event_id = created.id
                QMessageBox.information(self, "موفق", "جلسه ثبت شد")
            # شرکت‌کنندگان (مسئولین و مخاطبین) ثبت شوند
            try:
                participant_repo.replace_participants(
                    event_id,
                    self._invited_official_ids(),
                    sorted(self._selected_sms_ids),
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Could not save participants for event %s", event_id)
            # شماره مدیر برای جلسات بعدی به‌خاطر سپرده می‌شود
            try:
                setting_repo.set_setting(
                    SETTING_MANAGER_MOBILE,
                    custom.get(KEY_MANAGER_MOBILE) or "",
                    "شماره مدیر برای پیامک جلسات",
                )
            except Exception:
                pass
            self.pending_sms = self._build_sms_payload(event_id, sms_values, custom)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
