from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QFormLayout, QTextEdit, QComboBox,
    QCheckBox, QMessageBox, QGroupBox, QTabWidget, QSpinBox,
    QRadioButton, QButtonGroup, QFileDialog, QApplication, QTimeEdit
)
from PyQt5.QtCore import Qt, QTime
import logging
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm
from ui.color_settings_widget import ColorSettingsWidget
from services.repositories import setting_repo, holiday_repo
from services.storage_sync import (
    StorageSyncError,
    pull_from_shared,
    push_to_shared,
    shared_files_dir_for,
    validate_shared_path,
)
from services.sim_sms import sim_modem
from services import manager_program as program
from core.config import settings
from core.database import (
    get_current_db_path,
    get_current_files_dir,
    _dispose_engine,
    init_database,
)
from core.storage_config import save_storage_config
import zipfile
import os
import sys
import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("تنظیمات")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(18, True))
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {c.border_default};
                background: {c.canvas_overlay};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                padding: 8px 16px;
                margin-left: -1px;
                border: 1px solid {c.border_default};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                background: {c.canvas_subtle};
                color: {c.fg_muted};
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {c.canvas_overlay};
                color: {c.fg_default};
                font-weight: bold;
                border-bottom: 2px solid {c.primary};
            }}
            QTabBar::tab:hover {{
                background: {c.canvas_subtle};
                color: {c.fg_default};
            }}
        """)

        tabs.addTab(self._theme_tab(), "ظاهر برنامه")
        tabs.addTab(ColorSettingsWidget(), "تنظیم رنگ")
        tabs.addTab(self._sms_tab(), "تنظیمات پیامک")
        tabs.addTab(self._modem_tab(), "مودم سیمکارت")
        tabs.addTab(self._storage_tab(), "حالت ذخیره‌سازی")
        tabs.addTab(self._general_tab(), "تنظیمات عمومی")
        tabs.addTab(self._holidays_tab(), "تعطیلات رسمی")
        tabs.addTab(self._backup_tab(), "پشتیبان\u200cگیری و همگام‌سازی")
        tabs.addTab(self._about_tab(), "درباره برنامه")

        layout.addWidget(tabs)

        save_layout = QHBoxLayout()
        save_layout.addStretch()
        # Kept on self: _restyle() used to hunt it with
        # findChild(QPushButton, ""), which matches by object name (all empty
        # here) and returned whatever button came first.
        self.save_btn = QPushButton("ذخیره تمام تنظیمات")
        self.save_btn.setStyleSheet(Styles.primary_button())
        self.save_btn.clicked.connect(self._save_all)
        save_layout.addWidget(self.save_btn)
        layout.addLayout(save_layout)

    def _theme_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        theme_group = QGroupBox("انتخاب تم ظاهری")
        theme_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        theme_layout = QVBoxLayout(theme_group)

        self.theme_group = QButtonGroup(self)
        for key, label in theme_manager.get_theme_list():
            rb = QRadioButton(label)
            rb.setFont(get_font(13))
            rb.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default}; spacing: 8px;")
            if key == theme_manager.current_name:
                rb.setChecked(True)
            self.theme_group.addButton(rb)
            theme_layout.addWidget(rb)
            rb.toggled.connect(lambda checked, k=key: self._on_theme_change(k) if checked else None)

        layout.addWidget(theme_group)

        info = QLabel("تغییر تم بلافاصله اعمال می\u200cشود. تنظیمات انتخابی شما هنگام ذخیره ذخیره خواهد شد.")
        info.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px; padding: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()
        return widget

    def _on_theme_change(self, theme_name):
        theme_manager.set_mode(theme_name)
        main_window = self.window()
        if hasattr(main_window, "_apply_theme_style"):
            main_window._apply_theme_style()

    def _sms_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        provider_group = QGroupBox("سرویس پیامک")
        provider_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        form = QFormLayout(provider_group)
        form.setSpacing(12)

        self.sms_provider = QComboBox()
        self.sms_provider.setStyleSheet(Styles.combo_box())
        self.sms_provider.setFont(get_font(10))
        self.sms_provider.addItems(["کافه نگار", "ملی پیامک", "سفارشی"])
        form.addRow("سرویس\u200cدهنده:", self.sms_provider)

        self.sms_api_url = QLineEdit()
        self.sms_api_url.setStyleSheet(Styles.line_edit())
        self.sms_api_url.setPlaceholderText("https://api.example.com/v1/sms/send")
        form.addRow("آدرس API:", self.sms_api_url)

        self.sms_api_key = QLineEdit()
        self.sms_api_key.setStyleSheet(Styles.line_edit())
        self.sms_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.sms_api_key.setPlaceholderText("کلید API")
        form.addRow("کلید API:", self.sms_api_key)

        self.sms_sender = QLineEdit()
        self.sms_sender.setStyleSheet(Styles.line_edit())
        self.sms_sender.setPlaceholderText("1000xxxxx")
        form.addRow("شماره فرستنده:", self.sms_sender)

        self.sms_username = QLineEdit()
        self.sms_username.setStyleSheet(Styles.line_edit())
        form.addRow("نام کاربری:", self.sms_username)

        self.sms_password = QLineEdit()
        self.sms_password.setStyleSheet(Styles.line_edit())
        self.sms_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("رمز عبور:", self.sms_password)

        layout.addWidget(provider_group)

        template_group = QGroupBox("قالب پیامک")
        template_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        tpl_layout = QVBoxLayout(template_group)

        tpl_label = QLabel(
            "متغیرهای موجود:\n"
            "{name} = نام مخاطب\n"
            "{mobile} = شماره موبایل\n"
            "{position} = سمت مخاطب\n"
            "{date} = تاریخ امروز"
        )
        tpl_label.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px; padding: 5px;")
        tpl_layout.addWidget(tpl_label)

        self.sms_template = QTextEdit()
        self.sms_template.setMaximumHeight(100)
        self.sms_template.setStyleSheet(Styles.text_edit())
        self.sms_template.setPlaceholderText("قالب پیامک پیش\u200cفرض...")
        tpl_layout.addWidget(self.sms_template)

        layout.addWidget(template_group)
        layout.addStretch()
        return widget

    def _modem_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        conn_group = QGroupBox("اتصال مودم")
        conn_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        conn_form = QFormLayout(conn_group)
        conn_form.setSpacing(12)

        self.port_combo = QComboBox()
        self.port_combo.setStyleSheet(Styles.combo_box())
        self.port_combo.setFont(get_font(10))
        conn_form.addRow("پورت COM:", self.port_combo)

        self.baud_combo = QComboBox()
        self.baud_combo.setStyleSheet(Styles.combo_box())
        self.baud_combo.setFont(get_font(10))
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud_combo.setCurrentText("115200")
        conn_form.addRow("سرعت انتقال:", self.baud_combo)

        layout.addWidget(conn_group)

        btn_layout = QHBoxLayout()
        scan_btn = QPushButton("اسکن پورت\u200cها")
        scan_btn.setStyleSheet(Styles.secondary_button())
        scan_btn.clicked.connect(self._scan_ports)
        btn_layout.addWidget(scan_btn)

        connect_btn = QPushButton("اتصال مودم")
        connect_btn.setStyleSheet(Styles.primary_button())
        connect_btn.clicked.connect(self._connect_modem)
        btn_layout.addWidget(connect_btn)

        disconnect_btn = QPushButton("قطع اتصال")
        disconnect_btn.setStyleSheet(Styles.danger_button())
        disconnect_btn.clicked.connect(self._disconnect_modem)
        btn_layout.addWidget(disconnect_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        status_group = QGroupBox("وضعیت مودم")
        status_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        status_layout = QVBoxLayout(status_group)

        self.modem_status = QLabel("قطع اتصال")
        self.modem_status.setStyleSheet(f"color: {c.danger}; font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;")
        status_layout.addWidget(self.modem_status)

        self.modem_info_label = QLabel("")
        self.modem_info_label.setStyleSheet(f"color: {c.fg_muted}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px;")
        self.modem_info_label.setWordWrap(True)
        status_layout.addWidget(self.modem_info_label)

        layout.addWidget(status_group)

        internet_group = QGroupBox("تنظیمات اینترنت مودم")
        internet_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        internet_form = QFormLayout(internet_group)
        internet_form.setSpacing(12)

        self.apn_input = QLineEdit()
        self.apn_input.setStyleSheet(Styles.line_edit())
        self.apn_input.setPlaceholderText("مثال: mtnirancell")
        internet_form.addRow("APN:", self.apn_input)

        self.apn_user = QLineEdit()
        self.apn_user.setStyleSheet(Styles.line_edit())
        self.apn_user.setPlaceholderText("اختیاری")
        internet_form.addRow("نام کاربری:", self.apn_user)

        self.apn_pass = QLineEdit()
        self.apn_pass.setStyleSheet(Styles.line_edit())
        self.apn_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.apn_pass.setPlaceholderText("اختیاری")
        internet_form.addRow("رمز عبور:", self.apn_pass)

        layout.addWidget(internet_group)

        inet_btn_layout = QHBoxLayout()
        connect_inet_btn = QPushButton("اتصال اینترنت")
        connect_inet_btn.setStyleSheet(Styles.primary_button())
        connect_inet_btn.clicked.connect(self._connect_internet)
        inet_btn_layout.addWidget(connect_inet_btn)

        disconnect_inet_btn = QPushButton("قطع اینترنت")
        disconnect_inet_btn.setStyleSheet(Styles.danger_button())
        disconnect_inet_btn.clicked.connect(self._disconnect_internet)
        inet_btn_layout.addWidget(disconnect_inet_btn)
        inet_btn_layout.addStretch()
        layout.addLayout(inet_btn_layout)

        self.internet_status = QLabel("وضعیت اینترنت: قطع")
        self.internet_status.setStyleSheet(f"color: {c.fg_muted}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px;")
        layout.addWidget(self.internet_status)

        layout.addStretch()
        return widget

    def _storage_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Storage mode selection
        mode_group = QGroupBox("حالت ذخیره‌سازی داده‌ها")
        mode_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        mode_layout = QVBoxLayout(mode_group)

        # Radio buttons for storage mode
        self.storage_mode_group = QButtonGroup(self)
        
        self.local_mode_radio = QRadioButton("حالت محلی (Local)")
        self.local_mode_radio.setFont(get_font(11))
        self.local_mode_radio.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default}; spacing: 8px;")
        self.local_mode_radio.setToolTip("دیتابیس روی همین کامپیوتر ذخیره می‌شود. سریع و بدون نیاز به شبکه.")
        self.storage_mode_group.addButton(self.local_mode_radio)
        mode_layout.addWidget(self.local_mode_radio)

        local_desc = QLabel("  داده‌ها در پوشه data/users/USERNAME/ ذخیره می‌شوند. مناسب برای استفاده تک‌کاربره یا آفلاین.")
        local_desc.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: Tahoma; padding-right: 20px;")
        local_desc.setWordWrap(True)
        mode_layout.addWidget(local_desc)

        self.shared_mode_radio = QRadioButton("حالت اشتراکی / شبکه (Shared)")
        self.shared_mode_radio.setFont(get_font(11))
        self.shared_mode_radio.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default}; spacing: 8px;")
        self.shared_mode_radio.setToolTip("دیتابیس در یک پوشه مشترک شبکه‌ای ذخیره می‌شود. برای چند کاربره در شبکه محلی.")
        self.storage_mode_group.addButton(self.shared_mode_radio)
        mode_layout.addWidget(self.shared_mode_radio)

        shared_desc = QLabel("  تمام کاربران از یک دیتابیس مشترک استفاده می‌کنند. نیاز به مسیر شبکه (مثال: \\\\SERVER\\SharedData).")
        shared_desc.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: Tahoma; padding-right: 20px;")
        shared_desc.setWordWrap(True)
        mode_layout.addWidget(shared_desc)

        # Shared path input
        self.shared_path_frame = QFrame()
        self.shared_path_frame.setStyleSheet(f"background: {c.canvas_subtle}; border: 1px solid {c.border_default}; border-radius: 6px; padding: 8px;")
        shared_path_layout = QHBoxLayout(self.shared_path_frame)
        
        self.shared_path_input = QLineEdit()
        self.shared_path_input.setStyleSheet(Styles.line_edit())
        self.shared_path_input.setPlaceholderText(r"مسیر پوشه مشترک شبکه (مثال: \\SERVER\SharedData یا Z:\SharedData)")
        shared_path_layout.addWidget(self.shared_path_input)

        self.browse_shared_btn = QPushButton("انتخاب پوشه")
        self.browse_shared_btn.setStyleSheet(Styles.secondary_button())
        self.browse_shared_btn.clicked.connect(self._browse_shared_path)
        self.browse_shared_btn.setFixedWidth(120)
        shared_path_layout.addWidget(self.browse_shared_btn)

        mode_layout.addWidget(self.shared_path_frame)
        self.shared_path_frame.setVisible(False)

        # Connect signals
        self.local_mode_radio.toggled.connect(self._on_storage_mode_changed)
        self.shared_mode_radio.toggled.connect(self._on_storage_mode_changed)

        layout.addWidget(mode_group)

        # Sync actions
        sync_group = QGroupBox("همگام‌سازی و انتقال داده")
        sync_group.setStyleSheet(mode_group.styleSheet())
        sync_layout = QVBoxLayout(sync_group)

        sync_info = QLabel("انتقال دیتابیس بین این سیستم و پوشه مشترک شبکه. «ارسال» دیتابیس این سیستم را به پوشه مشترک می‌فرستد و «دریافت» دیتابیس مشترک را روی این سیستم می‌آورد (با پشتیبان‌گیری خودکار از داده‌های فعلی).")
        sync_info.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px; font-family: Tahoma;")
        sync_info.setWordWrap(True)
        sync_layout.addWidget(sync_info)

        btn_layout = QHBoxLayout()
        
        self.push_to_shared_btn = QPushButton("📤 ارسال داده به اشتراکی")
        self.push_to_shared_btn.setStyleSheet(Styles.primary_button())
        self.push_to_shared_btn.setToolTip("دیتابیس فعلی این سیستم در پوشه مشترک کپی می‌شود. اگر دیتابیسی در آن پوشه باشد، بازنویسی می‌شود.")
        self.push_to_shared_btn.clicked.connect(self._push_to_shared)
        btn_layout.addWidget(self.push_to_shared_btn)

        self.pull_from_shared_btn = QPushButton("📥 دریافت داده از اشتراکی")
        self.pull_from_shared_btn.setStyleSheet(Styles.secondary_button())
        self.pull_from_shared_btn.setToolTip("یک کپی از دیتابیس پوشه مشترک روی این سیستم قرار می‌گیرد. قبل از جایگزینی، از دیتابیس فعلی پشتیبان گرفته می‌شود.")
        self.pull_from_shared_btn.clicked.connect(self._pull_from_shared)
        btn_layout.addWidget(self.pull_from_shared_btn)

        btn_layout.addStretch()
        sync_layout.addLayout(btn_layout)

        layout.addWidget(sync_group)

        # Auto backup settings
        backup_settings_group = QGroupBox("تنظیمات پشتیبان‌گیری خودکار")
        backup_settings_group.setStyleSheet(mode_group.styleSheet())
        backup_form = QFormLayout(backup_settings_group)

        self.auto_backup_enabled = QCheckBox("پشتیبان‌گیری خودکار فعال باشد")
        self.auto_backup_enabled.setStyleSheet(f"color: {c.fg_default}; font-family: Tahoma; spacing: 8px;")
        backup_form.addRow(self.auto_backup_enabled)

        self.backup_interval = QSpinBox()
        self.backup_interval.setStyleSheet(Styles.line_edit())
        self.backup_interval.setRange(1, 168)
        self.backup_interval.setSuffix(" ساعت")
        self.backup_interval.setValue(6)
        backup_form.addRow("فاصله زمانی پشتیبان‌گیری:", self.backup_interval)

        self.max_backup_count = QSpinBox()
        self.max_backup_count.setStyleSheet(Styles.line_edit())
        self.max_backup_count.setRange(1, 50)
        self.max_backup_count.setSuffix(" نسخه")
        self.max_backup_count.setValue(10)
        backup_form.addRow("حداکثر تعداد پشتیبان‌ها:", self.max_backup_count)

        layout.addWidget(backup_settings_group)
        layout.addStretch()
        return widget

    def _on_storage_mode_changed(self):
        is_shared = self.shared_mode_radio.isChecked()
        self.shared_path_frame.setVisible(is_shared)
        self.push_to_shared_btn.setVisible(is_shared)
        self.pull_from_shared_btn.setVisible(is_shared)

    def _browse_shared_path(self):
        path = QFileDialog.getExistingDirectory(self, "انتخاب پوشه مشترک شبکه")
        if path:
            self.shared_path_input.setText(path)

    def _push_to_shared(self):
        """ارسال دیتابیس این سیستم به پوشه اشتراکی"""
        raw = self.shared_path_input.text().strip()
        ok, msg, resolved = validate_shared_path(raw)
        if not ok:
            QMessageBox.critical(self, "مسیر نامعتبر", msg)
            return

        db_path = get_current_db_path()
        if not confirm(
            self,
            title="ارسال داده به اشتراکی",
            message=(
                "دیتابیس فعلی این سیستم در پوشه مشترک کپی می‌شود:\n\n"
                f"از: {db_path}\nبه: {resolved}\n\n"
                "اگر دیتابیسی در آن پوشه وجود داشته باشد، بازنویسی می‌شود."
            ),
            yes_text="ارسال کن",
            danger=True,
        ):
            return

        try:
            result = push_to_shared(raw)
        except StorageSyncError as e:
            QMessageBox.critical(self, "خطا", str(e))
            return

        QMessageBox.information(
            self, "موفق",
            f"دیتابیس این سیستم در پوشه اشتراکی کپی شد:\n{result['target']}\n\n"
            "برای استفاده از حالت اشتراکی، گزینه «حالت اشتراکی / شبکه» را انتخاب و تنظیمات را ذخیره کنید.",
        )

    def _pull_from_shared(self):
        """دریافت دیتابیس اشتراکی روی این سیستم"""
        raw = self.shared_path_input.text().strip()
        ok, msg, resolved = validate_shared_path(raw, create=False)
        if not ok:
            QMessageBox.critical(self, "مسیر نامعتبر", msg)
            return

        if not resolved.exists():
            QMessageBox.warning(
                self, "پیدا نشد",
                f"دیتابیس اشتراکی در این مسیر وجود ندارد:\n{resolved}\n\n"
                "ابتدا از سیستم دارای داده، «ارسال داده به اشتراکی» را بزنید.",
            )
            return

        db_path = get_current_db_path()
        if not confirm(
            self,
            title="دریافت داده از اشتراکی",
            message=(
                "دیتابیس این سیستم با نسخه اشتراکی جایگزین می‌شود:\n\n"
                f"از: {resolved}\nبه: {db_path}\n\n"
                "قبل از جایگزینی، از دیتابیس فعلی این سیستم به‌صورت خودکار پشتیبان گرفته می‌شود."
            ),
            yes_text="دریافت کن",
            danger=True,
        ):
            return

        try:
            result = pull_from_shared(raw)
        except StorageSyncError as e:
            QMessageBox.critical(self, "خطا", str(e))
            return

        backup_note = (
            f"\n\nپشتیبان دیتابیس قبلی:\n{result['backup']}"
            if result.get("backup") else ""
        )
        if confirm(
            self,
            title="نیاز به راه‌اندازی مجدد",
            message=(
                "دریافت انجام شد. برای اعمال، برنامه باید یک بار بسته و دوباره باز شود."
                f"{backup_note}\n\nالان برنامه دوباره باز شود؟"
            ),
            yes_text="بله، باز شود",
            cancel_text="بعداً",
        ):
            self._restart_app()

    def _general_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        app_group = QGroupBox("تنظیمات برنامه")
        app_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        form = QFormLayout(app_group)
        form.setSpacing(12)

        self.page_size = QSpinBox()
        self.page_size.setStyleSheet(Styles.line_edit())
        self.page_size.setRange(10, 500)
        self.page_size.setValue(50)
        form.addRow("تعداد ردیف در هر صفحه:", self.page_size)

        self.max_file_size = QSpinBox()
        self.max_file_size.setStyleSheet(Styles.line_edit())
        self.max_file_size.setRange(1, 500)
        self.max_file_size.setValue(50)
        form.addRow("حداکثر اندازه فایل (مگابایت):", self.max_file_size)

        self.auto_backup = QCheckBox("پشتیبان\u200cگیری خودکار")
        self.auto_backup.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 13px; color: {c.fg_default};")
        form.addRow(self.auto_backup)

        layout.addWidget(app_group)

        program_group = QGroupBox("برنامهٔ مدیر — ارسال پیامک یک روز قبل")
        program_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        program_form = QFormLayout(program_group)
        program_form.setSpacing(12)

        self.program_digest_enabled = QCheckBox(
            "ارسال خودکار برنامهٔ فردا (یک روز قبل، هر برنامه در یک پیامک جدا)"
        )
        self.program_digest_enabled.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 13px; color: {c.fg_default};"
        )
        program_form.addRow(self.program_digest_enabled)

        self.program_digest_time = QTimeEdit()
        # ساعت همیشه چپ‌به‌راست تا در چیدمان RTL برعکس دیده نشود
        self.program_digest_time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.program_digest_time.setDisplayFormat("HH:mm")
        self.program_digest_time.setTime(QTime(18, 0))
        self.program_digest_time.setMinimumHeight(36)
        self.program_digest_time.setStyleSheet(Styles.line_edit())
        program_form.addRow("ساعت ارسال برنامهٔ فردا:", self.program_digest_time)

        program_hint = QLabel(
            "فقط برنامه‌هایی که چک‌باکس «ارسال در برنامهٔ فردا» کنارشان فعال باشد ارسال می‌شود؛ "
            "شمارهٔ گیرنده موبایل ثبت‌شده در پروفایل کاربر است."
        )
        program_hint.setWordWrap(True)
        program_hint.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 11px; color: {c.fg_muted};"
        )
        program_form.addRow(program_hint)

        layout.addWidget(program_group)

        org_group = QGroupBox("اطلاعات سازمان")
        org_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        org_form = QFormLayout(org_group)

        self.org_name = QLineEdit()
        self.org_name.setStyleSheet(Styles.line_edit())
        org_form.addRow("نام سازمان:", self.org_name)

        self.org_address = QTextEdit()
        self.org_address.setMaximumHeight(60)
        self.org_address.setStyleSheet(Styles.text_edit())
        org_form.addRow("آدرس:", self.org_address)

        self.org_phone = QLineEdit()
        self.org_phone.setStyleSheet(Styles.line_edit())
        org_form.addRow("تلفن:", self.org_phone)

        layout.addWidget(org_group)
        layout.addStretch()
        return widget

    def _holidays_tab(self):
        import jdatetime

        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        hint = QLabel(
            "در روزهای تعطیلِ ثبت‌شده، هنگام ثبت جلسهٔ جدید هشدار داده می‌شود. "
            "تعطیلات هر سال شمسی را جداگانه وارد کنید."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 11px; color: {c.fg_muted};"
        )
        layout.addWidget(hint)

        group = QGroupBox("تعطیلات رسمی سال")
        group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        g_layout = QVBoxLayout(group)
        g_layout.setSpacing(12)

        year_row = QHBoxLayout()
        year_lbl = QLabel("سال:")
        year_lbl.setStyleSheet(f"color: {c.fg_default};")
        year_row.addWidget(year_lbl)
        self.holiday_year_combo = QComboBox()
        today_year = jdatetime.date.today().year
        for y in range(today_year - 1, today_year + 2):
            self.holiday_year_combo.addItem(str(y), y)
        self.holiday_year_combo.setCurrentIndex(1)
        self.holiday_year_combo.currentIndexChanged.connect(self._load_holidays)
        year_row.addWidget(self.holiday_year_combo)
        year_row.addStretch()
        g_layout.addLayout(year_row)

        add_row = QHBoxLayout()
        self.holiday_date_input = QLineEdit()
        self.holiday_date_input.setPlaceholderText("1405/01/01")
        self.holiday_date_input.setFixedWidth(130)
        self.holiday_date_input.setStyleSheet(Styles.line_edit())
        add_row.addWidget(self.holiday_date_input)
        self.holiday_title_input = QLineEdit()
        self.holiday_title_input.setPlaceholderText("عنوان تعطیلی؛ مثال: عید نوروز")
        self.holiday_title_input.setStyleSheet(Styles.line_edit())
        add_row.addWidget(self.holiday_title_input, 1)
        add_btn = QPushButton("افزودن")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_holiday)
        add_row.addWidget(add_btn)
        g_layout.addLayout(add_row)

        self.holiday_list_layout = QVBoxLayout()
        self.holiday_list_layout.setSpacing(6)
        g_layout.addLayout(self.holiday_list_layout)
        g_layout.addStretch()

        layout.addWidget(group)
        layout.addStretch()

        self._load_holidays()
        return widget

    def _load_holidays(self, *_):
        c = theme_manager.current
        while self.holiday_list_layout.count():
            item = self.holiday_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        year = self.holiday_year_combo.currentData()
        try:
            rows = holiday_repo.get_by_year(year)
        except Exception:
            rows = []

        if not rows:
            empty = QLabel("تعطیلی ثبت نشده است")
            empty.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px; padding: 8px;")
            self.holiday_list_layout.addWidget(empty)
            return

        for h in rows:
            row = QFrame()
            row.setObjectName("holidayRow")
            row.setStyleSheet(f"""
                QFrame#holidayRow {{
                    background-color: {c.canvas_subtle};
                    border: 1px solid {c.border_default};
                    border-radius: 6px;
                }}
                QFrame#holidayRow QLabel {{
                    background: transparent;
                    border: none;
                }}
            """)
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(10, 5, 10, 5)
            date_lbl = QLabel(h.holiday_date)
            date_lbl.setFixedWidth(100)
            date_lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
            r_layout.addWidget(date_lbl)
            title_lbl = QLabel(h.title or "")
            title_lbl.setStyleSheet(f"color: {c.fg_default};")
            r_layout.addWidget(title_lbl, 1)
            del_btn = QPushButton("حذف")
            del_btn.setStyleSheet(Styles.table_action_button("danger"))
            del_btn.clicked.connect(
                lambda checked=False, hid=h.id: self._delete_holiday(hid))
            r_layout.addWidget(del_btn)
            self.holiday_list_layout.addWidget(row)

    def _add_holiday(self):
        import jdatetime

        date_text = self.holiday_date_input.text().strip()
        title = self.holiday_title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "خطا", "عنوان تعطیلی را وارد کنید")
            return
        parts = date_text.split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            try:
                jdatetime.date(y, m, d)
                date_text = f"{y:04d}/{m:02d}/{d:02d}"
            except (ValueError, TypeError):
                QMessageBox.warning(self, "خطا", "تاریخ نامعتبر است. قالب: 1405/01/01")
                return
        else:
            QMessageBox.warning(self, "خطا", "قالب تاریخ صحیح نیست. مثال: 1405/01/01")
            return
        try:
            holiday_repo.upsert(date_text, title)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self.holiday_date_input.clear()
        self.holiday_title_input.clear()
        self._load_holidays()

    def _delete_holiday(self, holiday_id):
        if not confirm(self, title="حذف تعطیلی", message="این روز تعطیل حذف شود؟"):
            return
        try:
            holiday_repo.delete(holiday_id)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self._load_holidays()

    def _backup_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        backup_group = QGroupBox("پشتیبان\u200cگیری")
        backup_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        backup_layout = QVBoxLayout(backup_group)

        backup_info = QLabel("ایجاد نسخه پشتیبان از داده\u200cهای برنامه (دیتابیس + فایل\u200cها).")
        backup_info.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px;")
        backup_layout.addWidget(backup_info)

        btn_layout = QHBoxLayout()
        create_backup_btn = QPushButton("ایجاد پشتیبان کامل")
        create_backup_btn.setStyleSheet(Styles.primary_button())
        create_backup_btn.clicked.connect(self._create_backup)
        btn_layout.addWidget(create_backup_btn)

        restore_btn = QPushButton("بازیابی پشتیبان")
        restore_btn.setStyleSheet(Styles.secondary_button())
        restore_btn.clicked.connect(self._restore_backup)
        btn_layout.addWidget(restore_btn)

        btn_layout.addStretch()
        backup_layout.addLayout(btn_layout)

        # Auto backup info
        auto_info = QLabel("پشتیبان‌گیری خودکار هر ۶ ساعت یک‌بار انجام می‌شود (در صورت فعال بودن).")
        auto_info.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; font-family: Tahoma; padding-top: 8px;")
        backup_layout.addWidget(auto_info)

        layout.addWidget(backup_group)

        # Sync section
        sync_group = QGroupBox("همگام‌سازی با اشتراکی")
        sync_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 16px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        sync_layout = QVBoxLayout(sync_group)

        sync_info = QLabel("در حالت اشتراکی، داده‌ها به‌صورت خودکار همگام‌سازی می‌شوند.")
        sync_info.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px; font-family: Tahoma;")
        sync_info.setWordWrap(True)
        sync_layout.addWidget(sync_info)

        sync_btn_layout = QHBoxLayout()
        
        push_btn = QPushButton("📤 ارسال تغییرات به اشتراکی")
        push_btn.setStyleSheet(Styles.primary_button())
        push_btn.clicked.connect(lambda: self._sync_push())
        sync_btn_layout.addWidget(push_btn)

        pull_btn = QPushButton("📥 دریافت تغییرات از اشتراکی")
        pull_btn.setStyleSheet(Styles.secondary_button())
        pull_btn.clicked.connect(lambda: self._sync_pull())
        sync_btn_layout.addWidget(pull_btn)

        sync_btn_layout.addStretch()
        sync_layout.addLayout(sync_btn_layout)

        layout.addWidget(sync_group)
        layout.addStretch()
        return widget

    def _sync_push(self):
        QMessageBox.information(self, "قرباً", "قابلیت ارسال تغییرات به اشتراکی در نسخه‌های آینده پیاده‌سازی خواهد شد")

    def _sync_pull(self):
        QMessageBox.information(self, "قرباً", "قابلیت دریافت تغییرات از اشتراکی در نسخه‌های آینده پیاده‌سازی خواهد شد")

    def _about_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        icon_label = QLabel("B")
        icon_label.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 48px; font-weight: bold; "
            f"color: {c.primary}; background-color: {c.canvas_overlay}; "
            f"border: 2px solid {c.border_default}; border-radius: 12px; padding: 10px;"
        )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(80, 80)
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        name = QLabel(settings.APP_NAME)
        name.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 20px; font-weight: bold; color: {c.fg_default};")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        version = QLabel(f"نسخه {settings.APP_VERSION}")
        version.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 14px; color: {c.fg_muted};")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        org = QLabel(settings.ORGANIZATION)
        org.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 13px; color: {c.fg_muted};")
        org.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(org)

        desc = QLabel(
            "این نرم\u200cافزار برای مدیریت مخاطبین، ارسال پیامک گروهی و تکی،\n"
            "مدیریت فایل\u200cها و نامه\u200cها، و گزارش\u200cگیری طراحی شده است.\n"
            "طراحی شده برای فرمانداری."
        )
        desc.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px; padding: 20px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()
        return widget

    def _scan_ports(self):
        self.port_combo.clear()
        try:
            ports = sim_modem.scan_ports()
            for p in ports:
                self.port_combo.addItem(f"{p['port']} - {p['description']}", p["port"])
        except Exception:
            pass
        if self.port_combo.count() == 0:
            self.port_combo.addItem("پورتی یافت نشد", "")

    def _connect_modem(self):
        c = theme_manager.current
        port = self.port_combo.currentData()
        baud = int(self.baud_combo.currentText())
        if not port:
            QMessageBox.warning(self, "هشدار", "لطفاً یک پورت COM انتخاب کنید")
            return

        success = sim_modem.connect(port, baud)
        if success:
            info = sim_modem.get_modem_info()
            self.modem_status.setText("متصل شده")
            self.modem_status.setStyleSheet(f"color: {c.success}; font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;")
            self.modem_info_label.setText(
                f"تولیدکننده: {info.manufacturer}\nمدل: {info.model}\nIMEI: {info.imei}\n"
                f"SIM: {info.sim_number or 'N/A'}\nاپراتور: {info.operator or 'N/A'}"
            )
            QMessageBox.information(self, "موفق", "به مودم متصل شد")
        else:
            self.modem_status.setText("اتصال ناموفق")
            self.modem_status.setStyleSheet(f"color: {c.danger}; font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;")
            QMessageBox.critical(self, "خطا", "اتصال ناموفق بود. پورت را بررسی کنید.")

    def _disconnect_modem(self):
        c = theme_manager.current
        sim_modem.disconnect()
        self.modem_status.setText("قطع اتصال")
        self.modem_status.setStyleSheet(f"color: {c.danger}; font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;")
        self.modem_info_label.setText("")
        QMessageBox.information(self, "اطلاعات", "از مودم قطع اتصال شد")

    def _connect_internet(self):
        c = theme_manager.current
        apn = self.apn_input.text().strip()
        if not apn:
            QMessageBox.warning(self, "هشدار", "لطفاً APN را وارد کنید")
            return

        success = sim_modem.connect_internet(
            apn=apn,
            username=self.apn_user.text().strip(),
            password=self.apn_pass.text().strip()
        )
        if success:
            info = sim_modem.get_internet_info()
            self.internet_status.setText(f"وضعیت اینترنت: متصل | IP: {info.ip_address}")
            self.internet_status.setStyleSheet(f"color: {c.success}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px;")
            QMessageBox.information(self, "موفق", f"اینترنت متصل شد\nIP: {info.ip_address}")
        else:
            self.internet_status.setText("وضعیت اینترنت: خطا")
            self.internet_status.setStyleSheet(f"color: {c.danger}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px;")
            QMessageBox.critical(self, "خطا", "اتصال اینترنت ناموفق بود")

    def _disconnect_internet(self):
        c = theme_manager.current
        sim_modem.disconnect_internet()
        self.internet_status.setText("وضعیت اینترنت: قطع")
        self.internet_status.setStyleSheet(f"color: {c.fg_muted}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px;")
        QMessageBox.information(self, "اطلاعات", "اینترنت قطع شد")

    def _load_settings(self):
        try:
            self.sms_api_url.setText(setting_repo.get_setting("sms_api_url", settings.SMS_API_URL or ""))
            self.sms_api_key.setText(setting_repo.get_setting("sms_api_key", settings.SMS_API_KEY or ""))
            self.sms_sender.setText(setting_repo.get_setting("sms_sender", settings.SMS_SENDER_NUMBER or ""))
            self.sms_username.setText(setting_repo.get_setting("sms_username", ""))
            # رمز باید موقع بارگذاری پر شود؛ وگرنه _save_all با فیلد خالی
            # رمز ذخیره‌شده را پاک می‌کرد (کاربر بدون دست‌زدن به آن ذخیره می‌زند).
            self.sms_password.setText(setting_repo.get_setting("sms_password", ""))
            self.sms_template.setPlainText(setting_repo.get_setting("sms_template", ""))
            self.page_size.setValue(setting_repo.get_setting("page_size", 50))
            self.max_file_size.setValue(setting_repo.get_setting("max_file_size_mb", 50))
            self.auto_backup.setChecked(bool(setting_repo.get_setting("auto_backup", False)))
            self.org_name.setText(setting_repo.get_setting("org_name", ""))
            self.org_address.setPlainText(setting_repo.get_setting("org_address", ""))
            self.org_phone.setText(setting_repo.get_setting("org_phone", ""))
            self.apn_input.setText(setting_repo.get_setting("modem_apn", ""))
            self.apn_user.setText(setting_repo.get_setting("modem_apn_user", ""))
            self.apn_pass.setText(setting_repo.get_setting("modem_apn_pass", ""))

            # برنامهٔ مدیر — ارسال پیامک یک روز قبل
            self.program_digest_enabled.setChecked(program.digest_enabled())
            try:
                hh, mm = program.digest_time().split(":")[:2]
                self.program_digest_time.setTime(QTime(int(hh), int(mm)))
            except (ValueError, IndexError):
                self.program_digest_time.setTime(QTime(18, 0))

            # Storage settings — حالت مؤثر همین سیستم (فایل پیکربندی محلی) اولویت دارد
            storage_mode = settings.STORAGE_MODE
            self.local_mode_radio.setChecked(storage_mode != "shared")
            self.shared_mode_radio.setChecked(storage_mode == "shared")
            shared_path = settings.SHARED_DB_PATH or setting_repo.get_setting("shared_db_path", "")
            self.shared_path_input.setText(shared_path or "")
            self._on_storage_mode_changed()

            # Backup settings
            self.auto_backup_enabled.setChecked(setting_repo.get_setting("auto_backup_enabled", True))
            self.backup_interval.setValue(setting_repo.get_setting("backup_interval_hours", 6))
            self.max_backup_count.setValue(setting_repo.get_setting("max_backup_count", 10))

            saved_colors = setting_repo.get_setting("custom_colors", {})
            if saved_colors:
                from ui.theme import CustomColors
                theme_manager.set_custom_colors(CustomColors.from_dict(saved_colors))
        except Exception:
            # A silent pass here meant a failed settings load looked like an
            # untouched form; the user would then save empty values over
            # their real settings.
            logging.exception("Could not load settings")

    def _save_all(self):
        try:
            # Storage settings — اعتبارسنجی پیش از هر ذخیره‌ای تا تنظیمات نیمه‌کاره نماند
            storage_mode = "shared" if self.shared_mode_radio.isChecked() else "local"
            shared_path = self.shared_path_input.text().strip()
            shared_files_dir = None
            if storage_mode == "shared":
                ok, msg, _resolved = validate_shared_path(shared_path)
                if not ok:
                    QMessageBox.critical(self, "مسیر نامعتبر", msg)
                    return
                shared_files_dir = shared_files_dir_for(shared_path)

            old_mode = settings.STORAGE_MODE
            old_path = (settings.SHARED_DB_PATH or "").strip()
            storage_changed = (old_mode != storage_mode) or (
                storage_mode == "shared" and old_path != shared_path
            )

            setting_repo.set_setting("theme", theme_manager.current_name)
            setting_repo.set_setting("sms_api_url", self.sms_api_url.text().strip())
            setting_repo.set_setting("sms_api_key", self.sms_api_key.text().strip())
            setting_repo.set_setting("sms_sender", self.sms_sender.text().strip())
            setting_repo.set_setting("sms_username", self.sms_username.text().strip())
            setting_repo.set_setting("sms_password", self.sms_password.text().strip())
            setting_repo.set_setting("sms_template", self.sms_template.toPlainText().strip())
            setting_repo.set_setting("page_size", self.page_size.value())
            setting_repo.set_setting("max_file_size_mb", self.max_file_size.value())
            setting_repo.set_setting("auto_backup", self.auto_backup.isChecked())
            setting_repo.set_setting("org_name", self.org_name.text().strip())
            setting_repo.set_setting("org_address", self.org_address.toPlainText().strip())
            setting_repo.set_setting("org_phone", self.org_phone.text().strip())
            setting_repo.set_setting("modem_apn", self.apn_input.text().strip())
            setting_repo.set_setting("modem_apn_user", self.apn_user.text().strip())
            setting_repo.set_setting("modem_apn_pass", self.apn_pass.text().strip())
            setting_repo.set_setting(
                program.SETTING_DIGEST_ENABLED, self.program_digest_enabled.isChecked()
            )
            setting_repo.set_setting(
                program.SETTING_DIGEST_TIME,
                self.program_digest_time.time().toString("HH:mm"),
            )

            # Storage settings
            stored_path = shared_path if storage_mode == "shared" else ""
            save_storage_config(storage_mode, stored_path, shared_files_dir)
            setting_repo.set_setting("storage_mode", storage_mode)
            setting_repo.set_setting("shared_db_path", stored_path)
            setting_repo.set_setting("shared_files_dir", shared_files_dir or "")

            # تنظیمات ذخیره‌سازی روی دیسک نوشته شد (save_storage_config) و هنگام
            # راه‌اندازی مجدد از همان‌جا خوانده می‌شود. settings درون‌حافظه را اینجا
            # تغییر نمی‌دهیم: موتور دیتابیس فعال هنوز به مسیر قبلی وصل است، پس اگر
            # کاربر restart را رد کند، تغییر STORAGE_MODE درون‌حافظه باعث می‌شد
            # کد حالت «اشتراکی» ببیند در حالی که اتصال واقعی هنوز «محلی» است.

            # Backup settings
            setting_repo.set_setting("auto_backup_enabled", self.auto_backup_enabled.isChecked())
            setting_repo.set_setting("backup_interval_hours", self.backup_interval.value())
            setting_repo.set_setting("max_backup_count", self.max_backup_count.value())
            settings.AUTO_BACKUP_ENABLED = self.auto_backup_enabled.isChecked()
            settings.AUTO_BACKUP_INTERVAL_HOURS = self.backup_interval.value()
            settings.MAX_BACKUP_COUNT = self.max_backup_count.value()

            if storage_changed:
                if confirm(
                    self,
                    title="نیاز به راه‌اندازی مجدد",
                    message=(
                        "تغییرات ذخیره شد. برای اعمال حالت ذخیره‌سازی جدید، "
                        "برنامه باید یک بار بسته و دوباره باز شود.\n\n"
                        "الان برنامه دوباره باز شود؟"
                    ),
                    yes_text="بله، باز شود",
                    cancel_text="بعداً",
                ):
                    self._restart_app()
                return

            QMessageBox.information(self, "موفق", "تنظیمات با موفقیت ذخیره شد")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره:\n{str(e)}")

    def _restart_app(self):
        """اجرای مجدد برنامه (برای اعمال تغییر حالت ذخیره‌سازی)."""
        try:
            from PyQt5.QtCore import QProcess

            frozen = getattr(sys, "frozen", False)
            if frozen:
                # بسته‌بندی‌شده: sys.executable همان exe است و argv[0] مسیر exe؛
                # بقیهٔ آرگومان‌ها را بدون argv[0] به نمونهٔ جدید می‌دهیم.
                executable = sys.executable
                arguments = sys.argv[1:]
                working_dir = os.path.dirname(sys.executable)
            else:
                # اجرای از سورس: sys.executable = python.exe و argv[0] نام
                # اسکریپت است. باید کل argv (شامل اسکریپت) پاس شود وگرنه
                # python بدون اسکریپت بالا می‌آید و restart ناموفق می‌شود.
                executable = sys.executable
                arguments = sys.argv
                working_dir = os.getcwd()
            if not QProcess.startDetached(executable, arguments, working_dir):
                raise RuntimeError("اجرای فرآیند جدید ناموفق بود")
        except Exception as e:
            QMessageBox.warning(
                self, "خطا",
                f"اجرای مجدد خودکار ممکن نشد:\n{e}\n\nلطفاً برنامه را دستی ببندید و دوباره باز کنید.",
            )
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _create_backup(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "ذخیره پشتیبان",
            f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            "فایل\u200cهای ZIP (*.zip)"
        )
        if not dest:
            return
        tmp_db = None
        try:
            # مسیر واقعی دیتابیس فعال (شامل حالت shared و کاربر جاری)
            db_path = get_current_db_path()
            # اسنپ‌شات سازگار از دیتابیس WAL: با API پشتیبان sqlite یک
            # کپی منفرد و یکپارچه (شامل تراکنش‌های داخل WAL) می‌سازیم.
            if db_path.exists():
                fd, tmp_db = tempfile.mkstemp(suffix=".db")
                os.close(fd)
                src = sqlite3.connect(str(db_path))
                try:
                    dst = sqlite3.connect(tmp_db)
                    try:
                        with dst:
                            src.backup(dst)
                    finally:
                        dst.close()
                finally:
                    src.close()

            with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
                if tmp_db:
                    zf.write(tmp_db, "app.db")
                files_dir = get_current_files_dir()
                if files_dir.exists():
                    for root, dirs, files in os.walk(files_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, str(settings.DATA_DIR))
                            zf.write(file_path, arcname)
            QMessageBox.information(self, "موفق", f"پشتیبان ذخیره شد:\n{dest}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در پشتیبان\u200cگیری:\n{str(e)}")
        finally:
            if tmp_db and os.path.exists(tmp_db):
                try:
                    os.unlink(tmp_db)
                except OSError:
                    pass

    def _restore_backup(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل پشتیبان", "", "فایل\u200cهای ZIP (*.zip)"
        )
        if not file_path:
            return
        if not confirm(
            self, title="بازیابی پشتیبان",
            message="داده‌های فعلی با محتوای فایل پشتیبان جایگزین خواهند شد.\nاین عملیات قابل بازگشت نیست.",
            yes_text="بازیابی کن", danger=True,
        ):
            return
        db_path = get_current_db_path()
        try:
            # آزادسازی قفل فایل دیتابیس قبل از نوشتن روی آن
            _dispose_engine(db_path)

            data_root = settings.DATA_DIR.resolve()
            with zipfile.ZipFile(file_path, 'r') as zf:
                names = zf.namelist()

                # ۱) دیتابیس: مستقیماً روی مسیر واقعی فعال نوشته می‌شود
                if "app.db" in names:
                    with zf.open("app.db") as srcf, open(db_path, "wb") as dstf:
                        shutil.copyfileobj(srcf, dstf)
                    # حذف فایل‌های WAL/SHM کهنه تا روی دیتابیس بازیابی‌شده
                    # replay نشوند (وگرنه داده قدیمی برمی‌گردد/دیتابیس خراب می‌شود)
                    for ext in ("-wal", "-shm"):
                        stale = Path(str(db_path) + ext)
                        if stale.exists():
                            stale.unlink()

                # ۲) سایر فایل‌ها با محافظت در برابر zip-slip
                members = [n for n in names if n != "app.db"]
                for member in members:
                    target = (data_root / member).resolve()
                    if data_root not in target.parents and target != data_root:
                        continue
                    zf.extract(member, str(data_root))

            # بازکردن مجدد موتور روی دیتابیس بازیابی‌شده
            init_database(db_path)
            QMessageBox.information(
                self, "موفق",
                "پشتیبان با موفقیت بازیابی شد.\nلطفاً برنامه را مجدداً راه\u200cاندازی کنید."
            )
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا:\n{str(e)}")

    def refresh(self):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")
        
        # Refresh header
        header = self.layout().itemAt(0).layout()
        if header:
            title = header.itemAt(0).widget()
            if title:
                title.setStyleSheet(Styles.title_label())
        
        # Refresh tabs widget
        tabs = self.findChild(QTabWidget)
        if tabs:
            tabs.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: 1px solid {c.border_default};
                    background: {c.canvas_overlay};
                    border-radius: 6px;
                }}
                QTabBar::tab {{
                    padding: 8px 16px;
                    margin-left: -1px;
                    border: 1px solid {c.border_default};
                    border-bottom: none;
                    border-radius: 6px 6px 0 0;
                    background: {c.canvas_subtle};
                    color: {c.fg_muted};
                    font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
                    font-size: 12px;
                }}
                QTabBar::tab:selected {{
                    background: {c.canvas_overlay};
                    color: {c.fg_default};
                    font-weight: bold;
                    border-bottom: 2px solid {c.primary};
                }}
                QTabBar::tab:hover {{
                    background: {c.canvas_inset};
                    color: {c.fg_default};
                }}
            """)
            
            # Refresh each tab
            for i in range(tabs.count()):
                tab_widget = tabs.widget(i)
                if tab_widget:
                    self._refresh_tab_widget(tab_widget, c)
        
        # Refresh save button
        save_btn = getattr(self, "save_btn", None)
        if save_btn is not None:
            save_btn.setStyleSheet(Styles.primary_button())

    def _refresh_tab_widget(self, widget, c):
        # Update group boxes
        for group in widget.findChildren(QGroupBox):
            group.setStyleSheet(f"""
                QGroupBox {{
                    font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                    border: 1px solid {c.border_default}; border-radius: 6px;
                    padding: 16px; margin-top: 10px;
                }}
                QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
            """)
            
            # Update labels in group
            for label in group.findChildren(QLabel):
                if label.property("isInfo"):
                    label.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px; padding: 10px;")
        
        # Update line edits, combo boxes
        for line_edit in widget.findChildren(QLineEdit):
            line_edit.setStyleSheet(Styles.line_edit())
        
        for combo in widget.findChildren(QComboBox):
            combo.setStyleSheet(Styles.combo_box())
        
        for text_edit in widget.findChildren(QTextEdit):
            text_edit.setStyleSheet(Styles.text_edit())
        
        for spin in widget.findChildren(QSpinBox):
            spin.setStyleSheet(f"""
                QSpinBox {{
                    background-color: {c.input_bg};
                    border: 1px solid {c.input_border};
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                    color: {c.fg_default};
                }}
                QSpinBox:focus {{
                    border: 2px solid {c.input_border_hover};
                }}
            """)
        
        for check in widget.findChildren(QCheckBox):
            check.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default}; spacing: 8px;")
        
        # Update radio buttons (theme selection)
        for rb in widget.findChildren(QRadioButton):
            rb.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default}; spacing: 8px;")
        
        # Update buttons
        for btn in widget.findChildren(QPushButton):
            if btn.text() in ["ذخیره رنگ‌ها", "بازنشانی پیش‌فرض", "خروجی JSON", "ورودی JSON"]:
                continue  # Skip ColorSettingsWidget buttons
            if "ذخیره" in btn.text() or "ایجاد" in btn.text() or "بازیابی" in btn.text() or "اتصال" in btn.text():
                btn.setStyleSheet(Styles.primary_button())
            elif "پیش‌فرض" in btn.text() or "انصراف" in btn.text():
                btn.setStyleSheet(Styles.secondary_button())
