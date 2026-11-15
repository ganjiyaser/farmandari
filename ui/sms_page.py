import re
import time

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QTextEdit, QComboBox, QProgressBar,
    QTabWidget, QFormLayout, QAbstractItemView, QCheckBox, QApplication,
    QSizePolicy, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm
from core.config import settings
from services.repositories import contact_repo, group_repo, message_repo, setting_repo
from services.sms_service import sms_service, normalize_mobile, is_valid_mobile

# ارتفاع یکسان کنترل‌ها در تب «ارسال پیامک». QSS سراسری ورودی‌ها را ۵۲
# (min-height 36 + padding 7*2 + border) و دکمه‌ها را ۴۸ (34 + 6*2 + 2)
# می‌سازد؛ اینجا همه به ۴۰ می‌رسند تا با هم تناسب داشته باشند.
CTRL_H = 40


def fix_ctrl_height(widget, height=CTRL_H, border=1):
    """قفل کردن ارتفاع ورودی/دکمه در این صفحه

    Qt مقدار min-height را با padding و border جمع می‌زند و بر setFixedHeight
    مقدم می‌داند؛ پس باید min-height و padding همان ویجت هم بازنویسی شود.
    border: عرض حاشیهٔ همان ویجت (دکمه‌های حالت ارسال حاشیهٔ ۲ پیکسلی دارند).
    """
    widget.setFixedHeight(height)
    if isinstance(widget, QPushButton):
        pad = 6
        rule = (
            f"QPushButton {{ min-height: {height - 2 * (pad + border)}px; "
            f"padding: {pad}px 16px; }}"
        )
    else:
        pad = 7
        rule = (
            "QLineEdit, LineEdit, SearchLineEdit, PasswordLineEdit, "
            f"QComboBox, ComboBox {{ min-height: {height - 2 * (pad + border)}px; "
            f"padding: {pad}px 12px; }}"
        )
    widget.setStyleSheet((widget.styleSheet() or "") + rule)


class SendWorker(QThread):
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int, int)

    def __init__(self, contact_ids, message, numbers=None, overrides=None):
        super().__init__()
        self.contact_ids = contact_ids
        self.message = message
        self.numbers = numbers or []
        self.overrides = overrides or {}

    def run(self):
        total = len(self.contact_ids) + len(self.numbers)
        success = 0
        failed = 0
        done = 0
        errors = []

        def _record(ok, err):
            nonlocal success, failed, done
            done += 1
            if ok:
                success += 1
            else:
                failed += 1
                errors.append(err or "خطای نامشخص")
            self.progress.emit(done, total)

        # استثنای یک مقصد نباید کل نخ را بکشد (وگرنه دکمه ارسال تا ابد
        # غیرفعال می‌ماند)؛ پس هر ارسال جداگانه مهار می‌شود.
        for cid in self.contact_ids:
            try:
                result = sms_service.send_sms(
                    cid, self.message, mobile=self.overrides.get(cid)
                )
                _record(result.success, result.error)
            except Exception as e:
                _record(False, str(e))
        for number in self.numbers:
            try:
                result = sms_service.send_number(number, self.message)
                _record(result.success, result.error)
            except Exception as e:
                _record(False, str(e))
        self.finished.emit(
            {"success": success, "failed": failed, "total": total, "errors": errors}
        )


class BalanceWorker(QThread):
    """گرفتن مانده (HTTP برای API و USSD برای سیمکارت) در پس‌زمینه"""
    done = pyqtSignal(dict)  # balances dict or {} on failure

    def run(self):
        try:
            balances = sms_service.get_balance()
        except Exception:
            balances = {}
        self.done.emit(balances or {})


class ModemScanWorker(QThread):
    """جستجوی روترهای شبکه (Wi-Fi) و مودم‌های USB در پس‌زمینه"""
    scan_done = pyqtSignal(list)

    def run(self):
        try:
            results = sms_service.scan_modems()
        except Exception:
            results = []
        self.scan_done.emit(results)


class ModemConnectWorker(QThread):
    """اتصال به مودم انتخاب‌شده در پس‌زمینه"""
    done = pyqtSignal(bool, str, str)  # ok, modem_id, error

    def __init__(self, modem_id, baud, pin=None):
        super().__init__()
        self.modem_id = modem_id
        self.baud = baud
        self.pin = pin

    def run(self):
        ok = False
        error = ""
        try:
            ok = sms_service.connect_modem(self.modem_id, baud=self.baud, pin=self.pin)
        except Exception as e:
            ok = False
            error = str(e) or ""
        self.done.emit(bool(ok), self.modem_id, error)


class SMSPage(QWidget):
    # از نخ شنوندهٔ مودم می‌آید و در نخ UI پردازش می‌شود (QueuedConnection)
    delivery_updated = pyqtSignal(int, int)
    incoming_received = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self.selected_contacts = []
        self._custom_numbers = []
        # تیک مخاطب‌ها باید بین بارگذاری‌های جدول (جستجو/پاسخ) حفظ شود؛
        # قبلاً هر جستجو همهٔ تیک‌ها را پاک می‌کرد
        self._checked_ids = set()
        # شماره‌ای که کاربر برای یک مخاطب در همین صفحه تغییر داده
        self._mobile_overrides = {}
        # اعضای حذف‌شده از لیست (گروهی/تکی) تا با بار بعدی دوباره برنگردند
        self._excluded_ids = set()
        self._recipients = []
        self._filling_contacts = False
        self._scan_worker = None
        self._connect_worker = None
        self._balance_worker = None
        self._detected_bauds = {}
        self._connect_silent = False
        self._last_port_sig = None
        self._last_scan_time = 0.0
        # مودم متصل از نوع "router:<ip>" یا "usb:<COMx>" — خالی یعنی قطع است
        self._connected_modem = None
        self._setup_ui()
        self._load_data()

        self.delivery_updated.connect(self._on_delivery_updated)
        sms_service.on_delivery_update = self._emit_delivery_update

        self.incoming_received.connect(self._on_incoming)
        sms_service.on_incoming_update = self._emit_incoming_update

        # پایش هات‌پلاگ: هر ۵ ثانیه لیست پورت‌ها (سریع) مقایسه می‌شود و فقط در
        # صورت تغییر، اسکن/پروب سنگین در پس‌زمینه اجرا می‌شود.
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setInterval(5000)
        self._hotplug_timer.timeout.connect(self._hotplug_tick)
        self._hotplug_timer.start()

        # QThread اگر هنگام تخریب والد هنوز در حال اجرا باشد، پروسه هنگام خروج
        # با STATUS_STACK_BUFFER_OVERRUN می‌شکند. closeEvent به صفحه‌ای که داخل
        # QStackedWidget است نمی‌رسد، پس هر دو مسیر (بستن پنجره و خروج برنامه)
        # باید منتظر اتمام نخ‌ها بمانند.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_workers)

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)

    def _stop_workers(self):
        """صبر کردن برای پایان نخ‌های پس‌زمینه پیش از تخریب ویجت"""
        for name in ("_scan_worker", "_connect_worker", "_bulk_worker", "_balance_worker"):
            worker = getattr(self, name, None)
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    worker.wait(5000)
            except RuntimeError:
                # آبجکت C++ قبلاً حذف شده است
                pass

    def _emit_delivery_update(self, message_id, st):
        try:
            self.delivery_updated.emit(int(message_id), int(st))
        except RuntimeError:
            pass

    def _on_delivery_updated(self, message_id, st):
        self._load_history()
        self._load_delivery()

    def _emit_incoming_update(self, message_id):
        try:
            self.incoming_received.emit(int(message_id))
        except RuntimeError:
            # ویجت در این فاصله حذف شده است
            pass

    def _on_incoming(self, message_id):
        self._load_incoming()
        self._load_history()

    def _port_signature(self):
        try:
            import serial.tools.list_ports
            return tuple(sorted((p.device, p.description) for p in serial.tools.list_ports.comports()))
        except Exception:
            return ()

    def _hotplug_tick(self):
        sig = self._port_signature()
        if sig == self._last_port_sig:
            return
        self._last_port_sig = sig
        # پورت جدید/جدا‌شده: اگر اتصال قطع شده، وضعیت را هم اصلاح کن
        if self._connected_modem and not sms_service.is_modem_connected():
            self._connected_modem = None
            self._set_connection_ui(False)
        self._scan_ports(force=True)

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(12)

        # هدر
        header = QHBoxLayout()
        title = QLabel("ارسال پیامک")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(18, True))
        header.addWidget(title)
        header.addStretch()

        self.balance_label = QLabel("مانده: در حال بررسی...")
        self.balance_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        header.addWidget(self.balance_label)

        refresh_btn = QPushButton("بروزرسانی مانده")
        refresh_btn.setStyleSheet(Styles.primary_button())
        refresh_btn.clicked.connect(self._refresh_balance)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # تب‌ها
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {c.border_default};
                background: {c.canvas_overlay};
                border-radius: 8px;
            }}
            QTabBar::tab {{
                padding: 10px 20px;
                margin-left: 4px;
                border: 1px solid {c.border_default};
                border-bottom: none;
                border-radius: 8px 8px 0 0;
                background: {c.canvas_subtle};
                color: {c.fg_default};
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
            }}
            QTabBar::tab:selected {{
                background: {c.canvas_overlay};
                color: {c.primary};
                font-weight: bold;
                border-bottom: 2px solid {c.primary};
            }}
        """)

        tabs.addTab(self._send_tab(), "ارسال پیامک")
        tabs.addTab(self._incoming_tab(), "پیام‌های دریافتی")
        tabs.addTab(self._sim_tab(), "تنظیمات سیمکارت")
        tabs.addTab(self._api_tab(), "تنظیمات API")
        tabs.addTab(self._history_tab(), "سابقه")
        tabs.addTab(self._delivery_tab(), "گزارش تحویل")

        self.tabs = tabs
        layout.addWidget(tabs)

    def _send_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # حالت ارسال
        mode_frame = QFrame()
        mode_frame.setStyleSheet(Styles.card())
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(12, 4, 12, 4)
        mode_layout.setSpacing(8)

        mode_label = QLabel("حالت ارسال:")
        mode_label.setFont(get_font(10, True))
        mode_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.setStyleSheet(Styles.combo_box())
        self.mode_combo.setFont(get_font(10))
        self.mode_combo.addItems(["سیمکارت", "سرویس API"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setFixedWidth(160)
        fix_ctrl_height(self.mode_combo)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()

        self.sim_status_label = QLabel("SIM: قطع اتصال")
        self.sim_status_label.setStyleSheet(f"color: {c.danger}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        mode_layout.addWidget(self.sim_status_label)
        layout.addWidget(mode_frame)

        # انتخاب گیرندگان
        target_frame = QFrame()
        target_frame.setStyleSheet(Styles.card())
        target_layout = QVBoxLayout(target_frame)
        target_layout.setContentsMargins(12, 10, 12, 10)
        target_layout.setSpacing(6)

        target_title = QLabel("انتخاب گیرندگان:")
        target_title.setFont(get_font(12, True))

        # عنوان و دکمه‌های تک/گروهی در یک ردیف؛ دو ردیف جدا ارتفاع کارت را
        # بی‌جهت ۵۰ پیکسل بیشتر می‌کرد
        mode_select = QHBoxLayout()
        mode_select.setSpacing(8)
        mode_select.addWidget(target_title)
        mode_select.addStretch()
        self.single_mode = QPushButton("تکی / چندتایی")
        self.single_mode.setCheckable(True)
        self.single_mode.setChecked(True)
        self.single_mode.setStyleSheet(f"""
            QPushButton {{
                padding: 8px 16px; border-radius: 6px; border: 2px solid {c.primary};
                color: {c.primary}; font-weight: bold; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
            }}
            QPushButton:checked {{
                background-color: {c.primary}; color: white;
            }}
        """)
        self.single_mode.clicked.connect(lambda: self._set_send_mode("single"))

        self.group_mode = QPushButton("گروهی")
        self.group_mode.setCheckable(True)
        self.group_mode.setStyleSheet(f"""
            QPushButton {{
                padding: 8px 16px; border-radius: 6px; border: 2px solid {c.primary};
                color: {c.primary}; font-weight: bold; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
            }}
            QPushButton:checked {{
                background-color: {c.primary}; color: white;
            }}
        """)
        self.group_mode.clicked.connect(lambda: self._set_send_mode("group"))

        mode_select.addWidget(self.single_mode)
        mode_select.addWidget(self.group_mode)
        fix_ctrl_height(self.single_mode, border=2)
        fix_ctrl_height(self.group_mode, border=2)
        target_layout.addLayout(mode_select)

        # بخش تکی / چندتایی
        # QWidget (و نه QFrame) تا استایل کارتِ والد روی آن آب نشود؛
        # selector سراسری Styles.card() هر QFrame داخلی را هم کارت می‌کرد.
        self.single_frame = QWidget()
        single_layout = QVBoxLayout(self.single_frame)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.setSpacing(6)

        self.contact_search = QLineEdit()
        self.contact_search.setPlaceholderText("جستجو در نام، موبایل، سازمان، سمت، آدرس، برچسب‌ها و ...")
        self.contact_search.setStyleSheet(Styles.line_edit())
        self.contact_search.setFont(get_font(10))
        self.contact_search.textChanged.connect(self._search_contacts)
        fix_ctrl_height(self.contact_search)
        single_layout.addWidget(self.contact_search)

        self.contact_table = QTableWidget()
        self.contact_table.setStyleSheet(Styles.table_widget())
        self.contact_table.setFont(get_font(9))
        self.contact_table.setColumnCount(4)
        self.contact_table.setHorizontalHeaderLabels(["انتخاب", "نام", "موبایل", "سمت"])
        self.contact_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # حداقل ارتفاع برای نمایش ۳ مخاطب (هر ردیف ~۲۸ پیکسل)؛ فضای آزادِ
        # پنجره‌های بزرگ‌تر به همین جدول می‌رسد (تا سقف ۳۲۰)
        self.contact_table.setMinimumHeight(116)
        self.contact_table.setMaximumHeight(320)
        self.contact_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.contact_table.itemChanged.connect(self._on_contact_item_changed)
        single_layout.addWidget(self.contact_table, 1)

        self.selected_label = QLabel("هیچ مخاطبی انتخاب نشده")
        self.selected_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        single_layout.addWidget(self.selected_label)

        target_layout.addWidget(self.single_frame, 1)

        # بخش گروهی
        self.group_frame = QWidget()
        self.group_frame.hide()
        group_layout = QVBoxLayout(self.group_frame)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(8)

        self.group_combo = QComboBox()
        self.group_combo.setStyleSheet(Styles.combo_box())
        self.group_combo.setFont(get_font(10))
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        group_layout.addWidget(self.group_combo)

        self.group_count_label = QLabel("")
        self.group_count_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        group_layout.addWidget(self.group_count_label)

        target_layout.addWidget(self.group_frame)

        # ---- لیست گیرندگان: همهٔ مقصد‌های ارسال در یک جدول قابل ویرایش/حذف ----
        # عمداً بیرون از single_frame است تا در حالت «گروهی» هم دیده شود
        numbers_frame = QFrame()
        numbers_frame.setStyleSheet(Styles.card())
        numbers_layout = QVBoxLayout(numbers_frame)
        numbers_layout.setContentsMargins(10, 8, 10, 8)
        numbers_layout.setSpacing(6)

        rec_head = QHBoxLayout()
        rec_head.setSpacing(8)
        numbers_title = QLabel("لیست گیرندگان")
        numbers_title.setFont(get_font(11, True))
        rec_head.addWidget(numbers_title)
        rec_head.addStretch()
        self.recipients_count_label = QLabel("هیچ گیرنده‌ای انتخاب نشده")
        self.recipients_count_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        rec_head.addWidget(self.recipients_count_label)
        numbers_layout.addLayout(rec_head)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.custom_number_input = QLineEdit()
        self.custom_number_input.setPlaceholderText("شماره موبایل؛ چند شماره را با کاما یا فاصله جدا کنید")
        self.custom_number_input.setStyleSheet(Styles.line_edit())
        self.custom_number_input.setFont(get_font(10))
        self.custom_number_input.returnPressed.connect(self._add_custom_numbers)
        fix_ctrl_height(self.custom_number_input)
        add_row.addWidget(self.custom_number_input, 1)

        add_number_btn = QPushButton("افزودن شماره")
        add_number_btn.setStyleSheet(Styles.primary_button())
        fix_ctrl_height(add_number_btn)
        add_number_btn.clicked.connect(self._add_custom_numbers)
        add_row.addWidget(add_number_btn)
        numbers_layout.addLayout(add_row)

        self.recipients_table = QTableWidget()
        # padding عمودی صفر: QSS آیتم، مستطیل سلول را هم می‌کاهد و ویجت
        # «عملیات» به‌جای تمام سلول فقط داخل آن ناحیه جا می‌گرفت (۸px بالا/پایین)
        self.recipients_table.setStyleSheet(Styles.table_widget(item_padding="0px 12px"))
        self.recipients_table.setFont(get_font(9))
        self.recipients_table.setColumnCount(4)
        self.recipients_table.setHorizontalHeaderLabels(["شماره", "نام", "نوع", "عملیات"])
        r_hdr = self.recipients_table.horizontalHeader()
        r_hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        r_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        r_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.recipients_table.verticalHeader().setVisible(False)
        self.recipients_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.recipients_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # سرصفحه ۳۸ + دو ردیف ۳۰ = ۱۰۰؛ کمتر از این دومین ردیف نصفه می‌ماند
        self.recipients_table.setMinimumHeight(100)
        self.recipients_table.setMaximumHeight(240)
        numbers_layout.addWidget(self.recipients_table)

        # چک‌باکس و دکمه‌ها در یک ردیف؛ ردیف جدا ارتفاع کارت را می‌افزود
        numbers_bottom = QHBoxLayout()
        numbers_bottom.setSpacing(8)

        self.save_numbers_check = QCheckBox(
            "شماره‌های جدید به فهرست مخاطبین اضافه شوند (ثبت در سابقه و گزارش تحویل)"
        )
        self.save_numbers_check.setFont(get_font(10))
        numbers_bottom.addWidget(self.save_numbers_check)
        numbers_bottom.addStretch()

        remove_number_btn = QPushButton("حذف انتخاب‌شده")
        remove_number_btn.setStyleSheet(Styles.danger_button())
        fix_ctrl_height(remove_number_btn)
        remove_number_btn.clicked.connect(self._remove_selected_numbers)
        numbers_bottom.addWidget(remove_number_btn)

        clear_numbers_btn = QPushButton("پاک کردن همه")
        clear_numbers_btn.setStyleSheet(Styles.danger_button())
        fix_ctrl_height(clear_numbers_btn)
        clear_numbers_btn.clicked.connect(self._clear_custom_numbers)
        numbers_bottom.addWidget(clear_numbers_btn)
        numbers_layout.addLayout(numbers_bottom)

        target_layout.addWidget(numbers_frame, 1)
        layout.addWidget(target_frame, 3)

        # متن پیام
        msg_frame = QFrame()
        msg_frame.setStyleSheet(Styles.card())
        msg_layout = QVBoxLayout(msg_frame)
        msg_layout.setContentsMargins(12, 6, 12, 6)
        msg_layout.setSpacing(8)

        msg_label = QLabel("متن پیام:")
        msg_label.setFont(get_font(12, True))
        msg_layout.addWidget(msg_label)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("پیام خود را اینجا بنویسید...")
        self.message_input.setStyleSheet(Styles.text_edit())
        self.message_input.setFont(get_font(10))
        # به‌جای سقف ۱۱۰ ثابت، فضای آزاد کارت را می‌گیرد تا همیشه بزرگ‌ترین
        # ورودی صفحه باشد و صفحه هم حداقل ارتفاع زیادی پیدا نکند
        self.message_input.setMinimumHeight(70)
        self.message_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.message_input.textChanged.connect(self._update_char_count)
        msg_layout.addWidget(self.message_input, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {c.border_default};
                border-radius: 6px;
                text-align: center;
                height: 22px;
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
            }}
            QProgressBar::chunk {{
                background-color: {c.primary};
                border-radius: 5px;
            }}
        """)
        msg_layout.addWidget(self.progress)

        # شمارنده‌ها و دکمه‌ها در یک ردیف؛ دو ردیف جدا ارتفاع کارت را ۶۷
        # پیکسل بیشتر می‌کرد (فضایی که به ورودی متن می‌رسید)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        self.send_btn = QPushButton("ارسال پیامک")
        self.send_btn.setStyleSheet(Styles.success_button())
        fix_ctrl_height(self.send_btn)
        self.send_btn.clicked.connect(self._send_sms)

        clear_btn = QPushButton("پاک کردن")
        clear_btn.setStyleSheet(Styles.danger_button())
        fix_ctrl_height(clear_btn)
        clear_btn.clicked.connect(self._clear_form)

        action_layout.addWidget(self.send_btn)
        action_layout.addWidget(clear_btn)
        action_layout.addStretch()

        self.char_count = QLabel("تعداد کاراکتر: 0")
        self.char_count.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        action_layout.addWidget(self.char_count)

        self.sms_parts = QLabel("تعداد پیامک: 0")
        self.sms_parts.setStyleSheet(f"color: {c.primary}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        action_layout.addWidget(self.sms_parts)
        msg_layout.addLayout(action_layout)

        layout.addWidget(msg_frame, 2)
        return widget

    def _sim_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("تنظیمات مودم پیامک (روتر Wi-Fi / سیمکارت USB)")
        title.setFont(get_font(13, True))
        title.setStyleSheet(f"color: {c.primary};")
        layout.addWidget(title)

        info_frame = QFrame()
        info_frame.setStyleSheet(Styles.card())
        info_layout = QFormLayout(info_frame)

        # هر دو مودم (روترهای شبکه و مودم‌های USB) در این فهرست می‌آیند؛
        # کاربر با «اتصال»، همان مودم را برای ارسال/دریافت پیامک فعال می‌کند
        self.modem_combo = QComboBox()
        self.modem_combo.setStyleSheet(Styles.combo_box())
        self.modem_combo.setFont(get_font(10))
        self.modem_combo.currentIndexChanged.connect(self._on_modem_combo_changed)
        info_layout.addRow("مودم:", self.modem_combo)

        self.baud_combo = QComboBox()
        self.baud_combo.setStyleSheet(Styles.combo_box())
        self.baud_combo.setFont(get_font(10))
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud_combo.setCurrentText("115200")
        self.baud_label = QLabel("سرعت انتقال:")
        info_layout.addRow(self.baud_label, self.baud_combo)

        self.auto_connect_check = QCheckBox("اتصال خودکار به مودم به‌محض شناسایی")
        self.auto_connect_check.setFont(get_font(10))
        self.auto_connect_check.setChecked(
            str(setting_repo.get_setting("sms_auto_connect", "1")) not in ("0", "False", "false")
        )
        self.auto_connect_check.toggled.connect(
            lambda v: setting_repo.set_setting("sms_auto_connect", "1" if v else "0")
        )
        info_layout.addRow("", self.auto_connect_check)

        layout.addWidget(info_frame)

        self.detect_label = QLabel("در حال شناسایی مودم‌های متصل...")
        self.detect_label.setWordWrap(True)
        self.detect_label.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        layout.addWidget(self.detect_label)

        btn_layout = QHBoxLayout()
        scan_btn = QPushButton("جستجوی مودم")
        scan_btn.setStyleSheet(Styles.primary_button())
        scan_btn.clicked.connect(lambda: self._scan_ports(force=True))

        connect_btn = QPushButton("اتصال")
        connect_btn.setStyleSheet(Styles.success_button())
        connect_btn.clicked.connect(self._connect_sim)

        disconnect_btn = QPushButton("قطع اتصال")
        disconnect_btn.setStyleSheet(Styles.danger_button())
        disconnect_btn.clicked.connect(self._disconnect_sim)

        btn_layout.addWidget(scan_btn)
        btn_layout.addWidget(connect_btn)
        btn_layout.addWidget(disconnect_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        status_frame = QFrame()
        status_frame.setStyleSheet(Styles.card())
        status_layout = QVBoxLayout(status_frame)

        status_title = QLabel("وضعیت مودم:")
        status_title.setFont(get_font(11, True))
        status_layout.addWidget(status_title)

        self.modem_status = QLabel("قطع اتصال")
        self.modem_status.setStyleSheet(f"color: {c.danger}; font-size: 13px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;")
        status_layout.addWidget(self.modem_status)

        self.modem_info_label = QLabel("")
        self.modem_info_label.setStyleSheet(f"color: {c.fg_muted}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        self.modem_info_label.setWordWrap(True)
        status_layout.addWidget(self.modem_info_label)

        self.delivery_status_label = QLabel("")
        self.delivery_status_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        status_layout.addWidget(self.delivery_status_label)

        layout.addWidget(status_frame)
        layout.addStretch()
        return widget

    def _api_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("تنظیمات سرویس API")
        title.setFont(get_font(13, True))
        title.setStyleSheet(f"color: {c.primary};")
        layout.addWidget(title)

        frame = QFrame()
        frame.setStyleSheet(Styles.card())
        form = QFormLayout(frame)

        self.api_provider = QComboBox()
        self.api_provider.setStyleSheet(Styles.combo_box())
        self.api_provider.setFont(get_font(10))
        self.api_provider.addItems(["کافه نگار", "ملی پیامک", "سفارشی"])
        form.addRow("سرویس‌دهنده:", self.api_provider)

        self.api_url = QLineEdit()
        self.api_url.setStyleSheet(Styles.line_edit())
        self.api_url.setFont(get_font(10))
        self.api_url.setPlaceholderText("https://api.example.com/v1/sms/send")
        form.addRow("آدرس API:", self.api_url)

        self.api_key = QLineEdit()
        self.api_key.setStyleSheet(Styles.line_edit())
        self.api_key.setFont(get_font(10))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("کلید API:", self.api_key)

        self.api_sender = QLineEdit()
        self.api_sender.setStyleSheet(Styles.line_edit())
        self.api_sender.setFont(get_font(10))
        form.addRow("شماره فرستنده:", self.api_sender)

        self.api_username = QLineEdit()
        self.api_username.setStyleSheet(Styles.line_edit())
        self.api_username.setFont(get_font(10))
        form.addRow("نام کاربری:", self.api_username)

        self.api_password = QLineEdit()
        self.api_password.setStyleSheet(Styles.line_edit())
        self.api_password.setFont(get_font(10))
        self.api_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("رمز عبور:", self.api_password)

        layout.addWidget(frame)

        save_btn = QPushButton("ذخیره تنظیمات API")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save_api_settings)
        layout.addWidget(save_btn)
        layout.addStretch()
        return widget

    def _history_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("سابقه پیامک‌ها")
        title.setFont(get_font(13, True))
        title.setStyleSheet(f"color: {c.primary};")
        layout.addWidget(title)

        self.history_table = QTableWidget()
        self.history_table.setStyleSheet(Styles.table_widget())
        self.history_table.setFont(get_font(9))
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["گیرنده", "متن", "وضعیت", "تاریخ", "حالت"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.history_table)

        refresh_btn = QPushButton("بروزرسانی")
        refresh_btn.setStyleSheet(Styles.primary_button())
        refresh_btn.clicked.connect(self._load_history)
        layout.addWidget(refresh_btn)

        return widget

    def _incoming_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("پیام‌های دریافتی")
        title.setFont(get_font(13, True))
        title.setStyleSheet(f"color: {c.primary};")
        top.addWidget(title)
        top.addStretch()

        self.incoming_count_label = QLabel("دریافت‌شده: ۰")
        self.incoming_count_label.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        top.addWidget(self.incoming_count_label)

        refresh_btn = QPushButton("بروزرسانی")
        refresh_btn.setStyleSheet(Styles.primary_button())
        refresh_btn.clicked.connect(self._load_incoming)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.incoming_table = QTableWidget()
        # دکمهٔ «پاسخ» با انتخاب‌گر variant از همین استایل آب می‌شود
        self.incoming_table.setStyleSheet(
            Styles.table_widget() + Styles.table_action_buttons()
        )
        self.incoming_table.setFont(get_font(9))
        self.incoming_table.setColumnCount(5)
        self.incoming_table.setHorizontalHeaderLabels(
            ["فرستنده", "مخاطب", "متن", "تاریخ دریافت", "عملیات"]
        )
        self.incoming_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.incoming_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.incoming_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.incoming_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.incoming_table)

        hint = QLabel(
            "پیام‌های دریافتی فقط زمانی ثبت می‌شوند که مودم سیم‌کارت متصل باشد. "
            "برای شماره‌های ناشناس به‌صورت خودکار مخاطب ساخته می‌شود."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        layout.addWidget(hint)

        return widget

    def _load_incoming(self):
        try:
            messages = sms_service.get_incoming(limit=200)
        except Exception:
            messages = []
        self.incoming_table.setRowCount(len(messages) if messages else 1)
        self.incoming_count_label.setText("دریافت‌شده: %s" % len(messages))
        if not messages:
            self.incoming_table.setItem(0, 0, QTableWidgetItem("پیامک دریافتی‌ای وجود ندارد"))
            return
        contacts = {}
        for row, m in enumerate(messages):
            contact = contacts.get(m.contact_id)
            if m.contact_id not in contacts:
                contact = contact_repo.get_by_id(m.contact_id)
                contacts[m.contact_id] = contact
            name = f"{contact.first_name} {contact.last_name}".strip() if contact else "نامشخص"
            stamp = m.received_at or m.created_at
            sender = m.sender_number or ""
            sender_item = QTableWidgetItem(sender or "-")
            sender_item.setData(Qt.ItemDataRole.UserRole, sender)
            self.incoming_table.setItem(row, 0, sender_item)
            self.incoming_table.setItem(row, 1, QTableWidgetItem(name or "نامشخص"))
            text_item = QTableWidgetItem(m.content or "-")
            text_item.setToolTip(m.content or "")
            self.incoming_table.setItem(row, 2, text_item)
            self.incoming_table.setItem(
                row, 3, QTableWidgetItem(stamp.strftime("%Y/%m/%d %H:%M") if stamp else "-")
            )

            reply_btn = QPushButton("پاسخ")
            reply_btn.setProperty("variant", "primary")
            can_reply = bool(sender) and is_valid_mobile(sender)
            reply_btn.setEnabled(can_reply)
            reply_btn.setToolTip(
                "ارسال پاسخ به این شماره در تب «ارسال پیامک»"
                if can_reply
                else "این شماره برای ارسال پاسخ معتبر نیست"
            )
            reply_btn.clicked.connect(
                lambda checked=False, r=row: self._reply_to_message(r)
            )
            self.incoming_table.setCellWidget(row, 4, reply_btn)

    def _find_contact_row(self, contact_id):
        """ردیف مخاطب در جدول گیرندگان تب ارسال (یا None)"""
        if not contact_id:
            return None
        for r in range(self.contact_table.rowCount()):
            name_item = self.contact_table.item(r, 1)
            if name_item and name_item.data(Qt.ItemDataRole.UserRole) == contact_id:
                return r
        return None

    def _reply_to_message(self, row):
        """رفتن به تب ارسال با گیرندهٔ همان فرستندهٔ پیام انتخاب‌شده"""
        item = self.incoming_table.item(row, 0)
        raw = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not raw:
            return
        sender = normalize_mobile(str(raw)) or str(raw)
        if not is_valid_mobile(sender):
            QMessageBox.warning(
                self, "هشدار",
                f"برای پاسخ به این شماره قابل ارسال نیست: {raw}",
            )
            return

        self.tabs.setCurrentIndex(0)
        self._set_send_mode("single")

        # گیرنده باید فقط همان فرستنده باشد
        self._checked_ids.clear()
        self._excluded_ids.clear()
        self._mobile_overrides.clear()
        if self.contact_search.text():
            self.contact_search.clear()
        for r in range(self.contact_table.rowCount()):
            self._set_contact_checked_from_row(r, False)
        self._custom_numbers = []
        self._refresh_recipients()

        contact = contact_repo.get_by_mobile(sender)
        matched_row = None
        if contact:
            matched_row = self._find_contact_row(contact.id)
            if matched_row is None:
                # فهرست قدیمی است؛ ممکن است مخاطب بعد از آخرین بارگذاری ساخته شده باشد
                self._load_contacts()
                matched_row = self._find_contact_row(contact.id)

        if matched_row is not None:
            self.contact_table.item(matched_row, 0).setCheckState(
                Qt.CheckState.Checked
            )
            self.contact_table.scrollToItem(
                self.contact_table.item(matched_row, 1)
            )
            name = f"{contact.first_name} {contact.last_name}".strip()
            self.selected_label.setText(f"گیرندهٔ پاسخ: {name}")
        else:
            # مخاطب در فهرست جاری نیست (یا ثبت نشده) → همان شماره ارسال شود
            self._custom_numbers = [sender]
            self._refresh_recipients()
            self.selected_label.setText(f"گیرندهٔ پاسخ: شمارهٔ {sender}")

        self.message_input.setFocus()

    def _set_send_mode(self, mode):
        self.single_mode.setChecked(mode == "single")
        self.group_mode.setChecked(mode == "group")
        self.single_frame.setVisible(mode == "single")
        self.group_frame.setVisible(mode == "group")
        self._refresh_recipients()

    def _load_data(self):
        self._load_contacts()
        self._load_groups()
        self._load_history()
        self._load_delivery()
        self._load_incoming()
        self._refresh_balance()
        self._scan_ports()

    def _load_contacts(self):
        self._fill_contacts(contact_repo.get_active(limit=300))

    def _fill_contacts(self, contacts):
        """پر کردن جدول مخاطبین بدون از دست رفتن تیک‌های قبلی"""
        self._filling_contacts = True
        try:
            self.contact_table.setRowCount(len(contacts))
            for row, c in enumerate(contacts):
                check_item = QTableWidgetItem()
                check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                check_item.setCheckState(
                    Qt.CheckState.Checked
                    if c.id in self._checked_ids
                    else Qt.CheckState.Unchecked
                )
                self.contact_table.setItem(row, 0, check_item)
                self.contact_table.setItem(row, 1, QTableWidgetItem(f"{c.first_name} {c.last_name}"))
                self.contact_table.setItem(row, 2, QTableWidgetItem(c.mobile or "-"))
                self.contact_table.setItem(row, 3, QTableWidgetItem(c.position or "-"))
                self.contact_table.item(row, 1).setData(Qt.ItemDataRole.UserRole, c.id)
        finally:
            self._filling_contacts = False
        self._refresh_recipients()

    def _on_contact_item_changed(self, item):
        if self._filling_contacts or item.column() != 0:
            return
        name_item = self.contact_table.item(item.row(), 1)
        cid = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        if not cid:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_ids.add(cid)
            self._excluded_ids.discard(cid)
        else:
            self._checked_ids.discard(cid)
        self._refresh_recipients()

    def _load_groups(self):
        groups = group_repo.get_with_counts()
        self.group_combo.clear()
        self.group_combo.addItem("انتخاب گروه...", None)
        for g_data in groups:
            g = g_data["group"]
            self.group_combo.addItem(f"{g.name} ({g_data['contact_count']})", g.id)

    def _search_contacts(self, text):
        if len(text) >= 2:
            contacts = contact_repo.search(text)
        else:
            contacts = contact_repo.get_active(limit=100)
        self._fill_contacts(contacts)

    def _on_group_changed(self, text):
        group_id = self.group_combo.currentData()
        if group_id:
            contacts = contact_repo.get_by_group(group_id)
            self.group_count_label.setText(f"تعداد اعضا: {len(contacts)}")
        self._excluded_ids.clear()
        self._refresh_recipients()

    def _on_mode_changed(self, text):
        mode = "sim_card" if text == "سیمکارت" else "api"
        sms_service.set_mode(mode)

    def _update_char_count(self):
        text = self.message_input.toPlainText()
        count = len(text)
        # متن فارسی با UCS2 کد می‌شود: تک‌بخشی تا ۷۰ و چندبخشی ۶۷ کاراکتر.
        # متن ASCII (GSM-7): تک‌بخشی تا ۱۶۰ و چندبخشی ۱۵۳ کاراکتر.
        is_ucs2 = any(ord(ch) > 127 for ch in text)
        single, multi = (70, 67) if is_ucs2 else (160, 153)
        if count == 0:
            parts = 0
        elif count <= single:
            parts = 1
        else:
            parts = -(-count // multi)  # گرد کردن به بالا
        self.char_count.setText(f"تعداد کاراکتر: {count}")
        self.sms_parts.setText(f"تعداد پیامک: {parts}")

    def _get_selected_contact_ids(self):
        return sorted(self._checked_ids)

    # ------------------------------------------------------------------ #
    #  لیست گیرندگان
    # ------------------------------------------------------------------ #
    def _recipient_rows(self):
        """همهٔ مقصد‌های ارسال: اعضای گروه / مخاطب‌های تیک‌خورده + شماره‌های جدید"""
        rows = []
        if self.group_mode.isChecked():
            group_id = self.group_combo.currentData()
            contacts = contact_repo.get_by_group(group_id) if group_id else []
            kind = "گروه"
        else:
            contacts = [
                c for c in (contact_repo.get_by_id(cid)
                            for cid in self._get_selected_contact_ids()) if c
            ]
            kind = "مخاطب"

        for contact in contacts:
            if contact.id in self._excluded_ids:
                continue
            rows.append({
                "contact_id": contact.id,
                "mobile": self._mobile_overrides.get(contact.id)
                or (contact.mobile or ""),
                "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "-",
                "kind": kind,
            })

        for number in self._custom_numbers:
            name = "-"
            try:
                existing = contact_repo.get_by_mobile(number)
            except Exception:
                existing = None
            if existing:
                name = f"{existing.first_name or ''} {existing.last_name or ''}".strip() or "-"
            rows.append({"contact_id": None, "mobile": number, "name": name, "kind": "شماره جدید"})
        return rows

    def _clear_recipient_widgets(self):
        """جداسازی ویجت‌های عملیات قبل از پر کردن مجدد جدول.

        setCellWidget/setRowCount فقط deleteLater صدا می‌زند و ویجت قدیمی تا
        پردازش رویداد به‌عنوان فرزند viewport باقی می‌ماند؛ نتیجه‌اش دکمه‌های
        دوبر روی سطر اول بود. اینجا صریحاً از والد جدا می‌شوند.
        """
        viewport = self.recipients_table.viewport()
        for child in list(viewport.children()):
            if isinstance(child, QWidget):
                child.setParent(None)
                child.deleteLater()

    def _refresh_recipients(self):
        rows = self._recipient_rows()
        self._recipients = rows

        self._clear_recipient_widgets()
        self.recipients_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            number_item = QTableWidgetItem(row["mobile"] or "-")
            self.recipients_table.setItem(index, 0, number_item)
            self.recipients_table.setItem(index, 1, QTableWidgetItem(row["name"]))
            self.recipients_table.setItem(index, 2, QTableWidgetItem(row["kind"]))
            self.recipients_table.setCellWidget(index, 3, self._recipient_actions(index))
            self.recipients_table.setRowHeight(index, 30)

        total = len(rows)
        custom = len(self._custom_numbers)
        if total == 0:
            self.recipients_count_label.setText("هیچ گیرنده‌ای انتخاب نشده")
        elif custom and custom != total:
            self.recipients_count_label.setText(
                f"{total} گیرنده آماده ارسال ({custom} شماره جدید)"
            )
        else:
            self.recipients_count_label.setText(f"{total} گیرنده آماده ارسال")

    def _recipient_actions(self, index):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(4)

        edit_btn = QPushButton("ویرایش")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda _=False, i=index: self._edit_recipient(i))

        del_btn = QPushButton("حذف")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda _=False, i=index: self._remove_recipient(i))

        for btn in (edit_btn, del_btn):
            btn.setFont(get_font(8))
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 0 8px; border-radius: 4px; "
                f"border: 1px solid {theme_manager.current.border_default}; "
                f"background-color: transparent; "
                f"color: {theme_manager.current.primary}; }}"
                f" QPushButton:hover {{ background-color: {theme_manager.current.primary_subtle}; }}"
            )
        del_btn.setStyleSheet(
            f"QPushButton {{ padding: 0 8px; border-radius: 4px; "
            f"border: 1px solid {theme_manager.current.border_default}; "
            f"background-color: transparent; "
            f"color: {theme_manager.current.danger}; }}"
            f" QPushButton:hover {{ background-color: {theme_manager.current.primary_subtle}; }}"
        )
        lay.addWidget(edit_btn)
        lay.addWidget(del_btn)
        lay.addStretch()
        return box

    def _edit_recipient(self, index):
        if not (0 <= index < len(self._recipients)):
            return
        current = self._recipients[index]
        text, ok = QInputDialog.getText(
            self, "ویرایش شماره گیرنده", "شماره موبایل:",
            QLineEdit.EchoMode.Normal, current["mobile"] or "",
        )
        if not ok:
            return
        number = normalize_mobile(text.strip())
        if not is_valid_mobile(number):
            QMessageBox.warning(
                self, "شماره نامعتبر",
                f"شماره موبایل معتبر وارد کنید: {text.strip() or '-'}",
            )
            return
        taken = [r["mobile"] for j, r in enumerate(self._recipients) if j != index]
        if number in taken:
            QMessageBox.information(self, "تکراری", "این شماره قبلاً در لیست گیرندگان هست")
            return

        if current["contact_id"]:
            self._mobile_overrides[current["contact_id"]] = number
        else:
            try:
                self._custom_numbers[self._custom_numbers.index(current["mobile"])] = number
            except ValueError:
                return
        self._refresh_recipients()

    def _drop_recipient(self, index):
        if not (0 <= index < len(self._recipients)):
            return
        row = self._recipients[index]
        contact_id = row["contact_id"]
        if contact_id:
            self._excluded_ids.add(contact_id)
            self._checked_ids.discard(contact_id)
            self._mobile_overrides.pop(contact_id, None)
            self._set_contact_checked(contact_id, False)
        else:
            try:
                self._custom_numbers.remove(row["mobile"])
            except ValueError:
                pass

    def _remove_recipient(self, index):
        self._drop_recipient(index)
        self._refresh_recipients()

    def _set_contact_checked(self, contact_id, checked):
        """تیک یک مخاطب در جدول سمت چپ (بدون اثر جانبی روی لیست)"""
        row = self._find_contact_row(contact_id)
        if row is None:
            return
        box = self.contact_table.item(row, 0)
        if not box:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        if box.checkState() == state:
            return
        self._filling_contacts = True
        try:
            box.setCheckState(state)
        finally:
            self._filling_contacts = False

    def _add_custom_numbers(self):
        raw = self.custom_number_input.text().strip()
        if not raw:
            return

        parts = [p for p in re.split(r"[,;\s]+", raw) if p.strip()]
        known = {r["mobile"] for r in self._recipients}
        added = []
        invalid = []
        duplicate = []

        for part in parts:
            number = normalize_mobile(part)
            if not is_valid_mobile(number):
                invalid.append(part.strip())
                continue
            if number in self._custom_numbers or number in known:
                duplicate.append(number)
                continue
            self._custom_numbers.append(number)
            known.add(number)
            added.append(number)

        self.custom_number_input.clear()
        self._refresh_custom_numbers()

        messages = []
        if added:
            messages.append(f"{len(added)} شماره افزوده شد")
        if duplicate:
            messages.append("تکراری (نادیده گرفته شد): " + "، ".join(duplicate))
        if invalid:
            messages.append("نامعتبر (نادیده گرفته شد): " + "، ".join(invalid))

        if messages:
            QMessageBox.information(self, "افزودن شماره", "\n".join(messages))

    def _refresh_custom_numbers(self):
        """نگه‌داشتن نام قدیمی برای فراخوانی‌های موجود"""
        self._refresh_recipients()

    def _remove_selected_numbers(self):
        rows = sorted(
            {index.row() for index in self.recipients_table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            QMessageBox.information(
                self, "حذف گیرنده", "ابتدا یک ردیف را از لیست گیرندگان انتخاب کنید"
            )
            return
        for row in rows:
            self._drop_recipient(row)
        self._refresh_recipients()

    def _clear_custom_numbers(self):
        if not self._recipients:
            return
        if not confirm(
            self, title="پاک کردن لیست گیرندگان",
            message="همه گیرندگان از لیست حذف شوند؟", yes_text="پاک کن",
        ):
            return
        self._checked_ids.clear()
        self._excluded_ids.clear()
        self._mobile_overrides.clear()
        self._custom_numbers = []
        for row in range(self.contact_table.rowCount()):
            self._set_contact_checked_from_row(row, False)
        self._refresh_recipients()

    def _set_contact_checked_from_row(self, row, checked):
        box = self.contact_table.item(row, 0)
        if not box:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        if box.checkState() == state:
            return
        self._filling_contacts = True
        try:
            box.setCheckState(state)
        finally:
            self._filling_contacts = False

    def _send_sms(self):
        message = self.message_input.toPlainText().strip()
        if not message:
            QMessageBox.warning(self, "هشدار", "لطفاً یک پیام وارد کنید")
            return

        is_group = self.group_mode.isChecked()

        if is_group:
            group_id = self.group_combo.currentData()
            if not group_id:
                QMessageBox.warning(self, "هشدار", "لطفاً یک گروه انتخاب کنید")
                return
            contact_ids = [
                c.id for c in contact_repo.get_by_group(group_id)
                if c.id not in self._excluded_ids
            ]
        else:
            contact_ids = self._get_selected_contact_ids()

        numbers = list(self._custom_numbers)

        if not contact_ids and not numbers:
            QMessageBox.warning(
                self, "هشدار",
                "لطفاً حداقل یک مخاطب انتخاب کنید یا در «لیست گیرندگان» شماره وارد نمایید"
            )
            return

        # اگر کاربر خواسته شماره‌ها در فهرست مخاطبین ثبت شوند، همین‌جا به
        # مخاطب تبدیل می‌شوند تا سابقه و گزارش تحویل هم برایشان ثبت شود
        if numbers and not is_group and self.save_numbers_check.isChecked():
            for number in numbers:
                contact = sms_service.ensure_contact(number)
                if contact and contact.id not in contact_ids:
                    contact_ids.append(contact.id)
                if contact and number != (contact.mobile or ""):
                    self._mobile_overrides[contact.id] = number
            numbers = []

        overrides = {
            cid: self._mobile_overrides[cid]
            for cid in contact_ids if cid in self._mobile_overrides
        }

        mode = "سیمکارت" if self.mode_combo.currentIndex() == 0 else "API"
        count = len(contact_ids) + len(numbers)

        preview = message[:120] + ("..." if len(message) > 120 else "")
        if not confirm(
            self, title="تأیید ارسال پیامک",
            message=f"ارسال از طریق {mode} به {count} مخاطب؟\n\nمتن پیام:\n{preview}",
            yes_text="ارسال کن",
        ):
            return

        self.send_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setMaximum(count)
        self.progress.setValue(0)

        # همهٔ ارسال‌ها (تکی و گروهی) از نخ پس‌زمینه عبور می‌کنند تا حتی
        # ارسال یک پیامک هم رابط کاربری را بلاک نکند. دکمه در
        # _on_send_complete فعال می‌شود؛ فعال‌سازی زودهنگام = ارسال تکراری.
        self._bulk_worker = SendWorker(contact_ids, message, numbers, overrides)
        self._bulk_worker.progress.connect(self._on_progress)
        self._bulk_worker.finished.connect(self._on_send_complete)
        self._bulk_worker.start()

    def _on_progress(self, current, total):
        self.progress.setValue(current)

    def _on_send_complete(self, result):
        self.send_btn.setEnabled(True)
        self.progress.setVisible(False)
        failed = result.get("failed", 0)
        summary = (
            f"ارسال شده: {result['success']}\n"
            f"ناموفق: {failed}\n"
            f"تعداد کل: {result['total']}"
        )
        if failed:
            # نمایش تا ۵ خطای اول تا کاربر بداند چرا ارسال ناموفق بود
            errors = result.get("errors") or []
            if errors:
                preview = "\n".join(f"• {e}" for e in errors[:5])
                if len(errors) > 5:
                    preview += f"\n… و {len(errors) - 5} خطای دیگر"
                summary += f"\n\nخطاها:\n{preview}"
            QMessageBox.warning(self, "نتیجه ارسال", summary)
        else:
            QMessageBox.information(self, "نتیجه ارسال", summary)
        self._clear_form()
        self._load_history()

    def _clear_form(self):
        self.message_input.clear()
        self.selected_label.setText("هیچ مخاطبی انتخاب نشده")
        self._checked_ids.clear()
        self._excluded_ids.clear()
        self._mobile_overrides.clear()
        for row in range(self.contact_table.rowCount()):
            self._set_contact_checked_from_row(row, False)
        self._custom_numbers = []
        self.custom_number_input.clear()
        self._refresh_recipients()

    def _delivery_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("گزارش تحویل پیامک‌ها")
        title.setFont(get_font(13, True))
        title.setStyleSheet(f"color: {c.primary};")
        layout.addWidget(title)

        summary_frame = QFrame()
        summary_frame.setStyleSheet(Styles.card())
        summary_layout = QHBoxLayout(summary_frame)

        self.delivered_label = QLabel("تحویل گرفته: ۰")
        self.delivered_label.setStyleSheet(
            f"color: {c.success}; font-size: 13px; font-weight: bold; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        self.undelivered_label = QLabel("تحویل نگرفته: ۰")
        self.undelivered_label.setStyleSheet(
            f"color: {c.danger}; font-size: 13px; font-weight: bold; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        self.waiting_label = QLabel("در انتظار تایید: ۰")
        self.waiting_label.setStyleSheet(
            f"color: {c.warning}; font-size: 13px; font-weight: bold; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )

        summary_layout.addWidget(self.delivered_label)
        summary_layout.addSpacing(20)
        summary_layout.addWidget(self.undelivered_label)
        summary_layout.addSpacing(20)
        summary_layout.addWidget(self.waiting_label)
        summary_layout.addStretch()

        period_label = QLabel("بازه:")
        period_label.setFont(get_font(10, True))
        summary_layout.addWidget(period_label)

        self.delivery_period = QComboBox()
        self.delivery_period.setStyleSheet(Styles.combo_box())
        self.delivery_period.setFont(get_font(10))
        self.delivery_period.addItem("امروز", 1)
        self.delivery_period.addItem("۷ روز اخیر", 7)
        self.delivery_period.addItem("۳۰ روز اخیر", 30)
        self.delivery_period.setCurrentIndex(1)
        self.delivery_period.currentIndexChanged.connect(self._load_delivery)
        summary_layout.addWidget(self.delivery_period)

        refresh_btn = QPushButton("بروزرسانی")
        refresh_btn.setStyleSheet(Styles.primary_button())
        refresh_btn.clicked.connect(self._load_delivery)
        summary_layout.addWidget(refresh_btn)

        layout.addWidget(summary_frame)

        self.delivery_table = QTableWidget()
        self.delivery_table.setStyleSheet(Styles.table_widget())
        self.delivery_table.setFont(get_font(9))
        self.delivery_table.setColumnCount(5)
        self.delivery_table.setHorizontalHeaderLabels(
            ["وضعیت", "نام گیرنده", "موبایل", "زمان ارسال", "زمان تحویل / علت"]
        )
        self.delivery_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.delivery_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.delivery_table)

        hint = QLabel(
            "تاییدیهٔ تحویل فقط برای پیامک‌های ارسالی با سیم‌کارت و در صورتی که اپراتور "
            "گزارش تحویل را ارائه کند ثبت می‌شود."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        layout.addWidget(hint)

        return widget

    def _load_delivery(self):
        c = theme_manager.current
        days = self.delivery_period.currentData() or 7
        try:
            summary = sms_service.get_delivery_summary(days)
            report = sms_service.get_delivery_report(days)
        except Exception:
            return

        self.delivered_label.setText(f"تحویل گرفته: {summary['delivered']}")
        self.undelivered_label.setText(f"تحویل نگرفته: {summary['undelivered']}")
        self.waiting_label.setText(f"در انتظار تایید: {summary['waiting']}")

        rows = []
        for r in report['delivered']:
            rows.append(("تحویل شد", c.success, r))
        for r in report['undelivered']:
            rows.append(("تحویل نشد", c.danger, r))
        for r in report['waiting']:
            rows.append(("در انتظار تایید", c.warning, r))

        self.delivery_table.setRowCount(len(rows))
        for i, (status_text, color, r) in enumerate(rows):
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(color))
            self.delivery_table.setItem(i, 0, status_item)
            self.delivery_table.setItem(i, 1, QTableWidgetItem(r['name']))
            self.delivery_table.setItem(i, 2, QTableWidgetItem(r['mobile']))
            self.delivery_table.setItem(i, 3, QTableWidgetItem(r['date']))
            self.delivery_table.setItem(
                i, 4, QTableWidgetItem(r['delivered_at'] or r['reason'] or "-")
            )

    def _load_history(self):
        messages = message_repo.get_all(limit=100)
        self.history_table.setRowCount(len(messages))
        status_map = {
            "pending": "در انتظار",
            "sent": "ارسال شده",
            "delivered": "تحویل داده شده",
            "failed": "ناموفق",
            "received": "دریافت شده"
        }
        contacts = {}
        for row, m in enumerate(messages):
            if m.contact_id not in contacts:
                contacts[m.contact_id] = contact_repo.get_by_id(m.contact_id)
            contact = contacts[m.contact_id]
            name = f"{contact.first_name} {contact.last_name}" if contact else "نامشخص"
            is_incoming = (m.direction.value if m.direction else "") == "incoming"
            phone = contact.mobile if contact else (
                (m.sender_number if is_incoming else m.recipient_number) or "-"
            )
            self.history_table.setItem(row, 0, QTableWidgetItem(f"{name}\n{phone}"))
            text_item = QTableWidgetItem(m.content or "-")
            text_item.setToolTip(m.content or "")
            self.history_table.setItem(row, 1, text_item)
            self.history_table.setItem(row, 2, QTableWidgetItem(status_map.get(m.status.value if m.status else "", "-")))
            # created_at به UTC نوشته می‌شود (func.now) ولی sent_at/received_at
            # محلی‌اند؛ برای نمایش به کاربر اول مهر محلی و در نبود آن created_at.
            if is_incoming:
                stamp = m.received_at or m.created_at
            else:
                stamp = m.sent_at or m.created_at
            self.history_table.setItem(row, 3, QTableWidgetItem(stamp.strftime("%Y/%m/%d %H:%M") if stamp else "-"))
            self.history_table.setItem(row, 4, QTableWidgetItem("دریافت" if is_incoming else "ارسال"))

    def _on_modem_combo_changed(self, index):
        """سرعت انتقال فقط برای مودم USB معنی دارد؛ برای روتر پنهان می‌شود"""
        modem_id = self.modem_combo.itemData(index) if index >= 0 else None
        is_usb = bool(modem_id) and str(modem_id).startswith("usb:")
        self.baud_combo.setVisible(is_usb)
        self.baud_label.setVisible(is_usb)

    def _scan_ports(self, force=False):
        """جستجوی مودم در پس‌زمینه؛ روترهای شبکه و مودم‌های USB پیدا می‌شوند"""
        if self._scan_worker and self._scan_worker.isRunning():
            return
        if not force:
            if self.modem_combo.count() > 0:
                return
            if (time.time() - self._last_scan_time) < 10:
                return

        self._last_scan_time = time.time()
        self.detect_label.setText("در حال جستجوی مودم‌های متصل...")
        self._scan_worker = ModemScanWorker(self)
        self._scan_worker.scan_done.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_done(self, results):
        c = theme_manager.current
        previous = self.modem_combo.currentData()
        self.modem_combo.clear()
        self._detected_bauds = {}

        routers = [r for r in results if r.get("kind") == "router"]
        modems = [r for r in results if r.get("kind") == "usb"]

        for r in routers:
            self.modem_combo.addItem(r["label"], r["id"])
        if routers and modems:
            self.modem_combo.insertSeparator(self.modem_combo.count())
        for m in modems:
            label = m["label"]
            if m.get("in_use"):
                label += " (در حال استفاده)"
            self.modem_combo.addItem(label, m["id"])
            self._detected_bauds[m["id"]] = m.get("baud")

        if self.modem_combo.count() == 0:
            self.modem_combo.addItem("مودمی یافت نشد", "")

        found = len(routers) + len(modems)
        if found:
            names = "، ".join((r["label"] for r in routers + modems))
            self.detect_label.setText(f"{found} مودم شناسایی شد: {names}")
            self.detect_label.setStyleSheet(
                f"color: {c.success}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
            )
        else:
            self.detect_label.setText(
                "مودمی شناسایی نشد. برای روتر: به همان Wi-Fi روتر وصل باشید؛ "
                "برای مودم USB: کابل و درایور را بررسی کنید."
            )
            self.detect_label.setStyleSheet(
                f"color: {c.warning}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
            )

        # انتخاب مودم: مودمی که قبلاً انتخاب/اتصال داشته در اولویت است تا بین
        # اسکن‌ها حفظ شود
        keep = False
        selected = sms_service.get_selected_modem()
        for candidate in (previous, selected):
            if not candidate:
                continue
            idx = self.modem_combo.findData(candidate)
            if idx >= 0:
                self.modem_combo.setCurrentIndex(idx)
                keep = True
                break
        if not keep:
            first_id = self.modem_combo.itemData(0)
            if first_id:
                baud = self._detected_bauds.get(first_id)
                if baud:
                    self.baud_combo.setCurrentText(str(baud))

        if found and self.auto_connect_check.isChecked() and not self._is_modem_connected():
            self._connect_sim(silent=True)

    def _is_modem_connected(self):
        try:
            return bool(sms_service.is_modem_connected())
        except Exception:
            return False

    def _set_connection_ui(self, connected):
        c = theme_manager.current
        font = "'Vazirmatn', 'Segoe UI', Tahoma"
        label = "روتر" if (self._connected_modem or "").startswith("router:") else "SIM"
        if connected:
            self.modem_status.setText("متصل شده")
            self.modem_status.setStyleSheet(f"color: {c.success}; font-size: 13px; font-family: {font}; font-weight: bold;")
            self.sim_status_label.setText(f"{label}: متصل شده")
            self.sim_status_label.setStyleSheet(f"color: {c.success}; font-family: {font};")
        else:
            self.modem_status.setText("قطع اتصال")
            self.modem_status.setStyleSheet(f"color: {c.danger}; font-size: 13px; font-family: {font}; font-weight: bold;")
            self.modem_info_label.setText("")
            self.sim_status_label.setText(f"{label}: قطع اتصال")
            self.sim_status_label.setStyleSheet(f"color: {c.danger}; font-family: {font};")
            self.delivery_status_label.setText("")

    def _connect_sim(self, silent=False):
        if self._connect_worker and self._connect_worker.isRunning():
            return
        modem_id = self.modem_combo.currentData()
        baud = int(self.baud_combo.currentText() or 115200)
        if not modem_id:
            if not silent:
                QMessageBox.warning(self, "هشدار", "لطفاً یک مودم انتخاب کنید")
            return

        pin = None
        if str(modem_id).startswith("router:"):
            host = str(modem_id).split(":", 1)[1]
            if sms_service.router_needs_password(host):
                # رمز فقط در حافظه برای همین اجرا نگه داشته می‌شود و هرگز در
                # فایل/دیتابیس ذخیره نمی‌شود
                pwd, ok = QInputDialog.getText(
                    self, "رمز روتر",
                    f"رمز پنل مدیریت روتر ({host}) را وارد کنید:",
                    QLineEdit.EchoMode.Password,
                )
                if not ok or not pwd:
                    if not silent:
                        QMessageBox.warning(self, "هشدار", "برای اتصال به روتر، رمز پنل مدیریت لازم است")
                    return
                sms_service.set_router_credentials(
                    host, settings.DLINK_ROUTER_USER or "admin", pwd
                )
        else:
            # مودم USB - اگر سیمکارت PIN دارد، از کاربر بپرس
            pin, ok = QInputDialog.getText(
                self, "کد PIN سیمکارت",
                "اگر سیمکارت کد PIN دارد، وارد کنید (در صورت عدم داشتن خالی بگذارید):",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            # pin می‌تواند خالی باشد

        self._connect_silent = silent
        if not silent:
            self.detect_label.setText("در حال اتصال...")
        self._connect_worker = ModemConnectWorker(modem_id, baud, pin)
        self._connect_worker.done.connect(self._on_connect_done)
        self._connect_worker.start()

    def _on_connect_done(self, ok, modem_id, error):
        c = theme_manager.current
        if ok:
            self._connected_modem = modem_id
            self._set_connection_ui(True)
            if str(modem_id).startswith("router:"):
                host = str(modem_id).split(":", 1)[1]
                self.modem_info_label.setText(
                    f"نوع: روتر Wi-Fi (D-Link)\nآدرس: {host}\nوضعیت: آماده ارسال و دریافت پیامک"
                )
            else:
                info = sms_service.get_modem_status()
                self.modem_info_label.setText(
                    f"تولیدکننده: {info.manufacturer}\nمدل: {info.model}\nIMEI: {info.imei}\nSIM: {info.sim_number or 'N/A'}"
                )
            self._update_delivery_status_label()
            if not self._connect_silent:
                QMessageBox.information(self, "موفق", "به مودم متصل شد")
        else:
            self._connected_modem = None
            self._set_connection_ui(False)
            self.modem_status.setText("اتصال ناموفق")
            self.modem_status.setStyleSheet(
                f"color: {c.danger}; font-size: 13px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;"
            )
            if not self._connect_silent:
                QMessageBox.critical(self, "خطا", error or "اتصال ناموفق بود. مودم را بررسی کنید.")

    def _update_delivery_status_label(self):
        c = theme_manager.current
        font = "'Vazirmatn', 'Segoe UI', Tahoma"
        if (self._connected_modem or "").startswith("router:"):
            # روتر گزارش لحظه‌ای (+CDS) ندارد؛ دریافت از صندوق روتر خوانده می‌شود
            self.delivery_status_label.setText(
                "تاییدیه تحویل: روتر گزارش لحظه‌ای نمی‌فرستد؛ پیامک‌های دریافتی هر چند ثانیه از صندوق روتر خوانده می‌شوند"
            )
            self.delivery_status_label.setStyleSheet(
                f"color: {c.fg_muted}; font-size: 11px; font-family: {font};"
            )
            return
        try:
            from services.sim_sms import sim_modem
            enabled = bool(sim_modem.delivery_reports_enabled)
        except Exception:
            enabled = False
        if enabled:
            self.delivery_status_label.setText("تاییدیه تحویل: فعال (گزارش تحویل از مودم دریافت می‌شود)")
            self.delivery_status_label.setStyleSheet(
                f"color: {c.success}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
            )
        else:
            self.delivery_status_label.setText("تاییدیه تحویل: غیرفعال (مودم از گزارش تحویل پشتیبانی نمی‌کند)")
            self.delivery_status_label.setStyleSheet(
                f"color: {c.warning}; font-size: 11px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
            )

    def _disconnect_sim(self):
        sms_service.disconnect_modem()
        self._connected_modem = None
        self._set_connection_ui(False)
        QMessageBox.information(self, "اطلاعات", "از مودم قطع اتصال شد")

    def _refresh_balance(self):
        # get_balance ترکیبی از HTTP (برای API) و USSD (برای سیمکارت) است و
        # چند ثانیه طول می‌کشد؛ اگر روی نخ GUI اجرا شود هر بار ورود به تب
        # «ارسال پیامک» رابط کاربری را فریز می‌کرد.
        worker = self._balance_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    return
            except RuntimeError:
                pass
        self.balance_label.setText("مانده: در حال بررسی...")
        self._balance_worker = BalanceWorker(self)
        self._balance_worker.done.connect(self._on_balance_ready)
        self._balance_worker.start()

    def _on_balance_ready(self, balances):
        parts = []
        if "sim_card" in balances:
            parts.append(f"SIM: {balances['sim_card']}")
        if "api" in balances:
            parts.append(f"API: {balances['api']}")
        self.balance_label.setText(f"مانده: {' | '.join(parts) if parts else 'N/A'}")

    def _save_api_settings(self):
        from services.repositories import setting_repo
        setting_repo.set_setting("sms_api_provider", self.api_provider.currentText())
        setting_repo.set_setting("sms_api_url", self.api_url.text().strip())
        setting_repo.set_setting("sms_api_key", self.api_key.text().strip())
        setting_repo.set_setting("sms_sender", self.api_sender.text().strip())
        setting_repo.set_setting("sms_username", self.api_username.text().strip())
        setting_repo.set_setting("sms_password", self.api_password.text().strip())
        QMessageBox.information(self, "موفق", "تنظیمات API ذخیره شد")

    def refresh(self):
        self._load_data()