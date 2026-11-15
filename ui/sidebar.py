from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from qfluentwidgets import (
    NavigationInterface, NavigationItemPosition, NavigationWidget,
    FluentIcon as FIF
)
from ui.theme import theme_manager
from ui.styles import get_font, FONT_CSS


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._setup_ui()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(132)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {c.primary};
                border: none;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 22, 20, 14)
        header_layout.setSpacing(10)

        icon_label = QLabel("د")
        icon_label.setStyleSheet(f"""
            font-size: 26px; font-family: {FONT_CSS}; font-weight: bold;
            color: white; background-color: {c.primary};
            border-radius: 24px;
        """)
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        app_name = QLabel("سامانه مدیریت فرمانداری")
        app_name.setStyleSheet(f"color: white; font-size: 14px; font-weight: bold; font-family: {FONT_CSS};")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(app_name)

        app_sub = QLabel("بخشداری‌های تابعه")
        app_sub.setStyleSheet(f"color: rgba(255,255,255,0.65); font-size: 11px; font-family: {FONT_CSS};")
        app_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(app_sub)

        layout.addWidget(header)
        layout.addSpacing(8)

        self.nav = NavigationInterface(self, showReturnButton=False)
        self.nav.setStyleSheet(f"""
            NavigationInterface {{
                background-color: {c.canvas_overlay};
                border: none;
            }}
        """)

        self.items = {}
        menu_items = [
            ("dashboard", "داشبورد", FIF.HOME),
            ("contacts", "مخاطبین", FIF.PEOPLE),
            ("officials", "مسئولین", FIF.PEOPLE),
            ("calendar", "تقویم و جلسات", FIF.CALENDAR),
            ("decisions", "صورت‌جلسه و مصوبات", FIF.DOCUMENT),
            ("letters", "دفتر اندیکاتور", FIF.EDIT),
            ("groups", "گروه\u200cها", FIF.LIBRARY),
            ("sms", "پیامک", FIF.MESSAGE),
            ("files", "فایل\u200cها و نامه\u200cها", FIF.FOLDER),
            ("reports", "گزارش\u200cها", FIF.INFO),
            ("settings", "تنظیمات", FIF.SETTING),
        ]

        for key, text, icon in menu_items:
            item = self.nav.addItem(
                routeKey=key,
                icon=icon,
                text=text,
                onClick=lambda checked=False, k=key: self._on_item_clicked(k),
                position=NavigationItemPosition.TOP
            )
            self.items[key] = item

        layout.addWidget(self.nav)

        self._on_item_clicked("dashboard")

    def _on_item_clicked(self, key):
        self.nav.setCurrentItem(key)
        self.page_changed.emit(key)

    def set_active_page(self, key):
        self.nav.setCurrentItem(key)

    def _on_theme_changed(self, theme_name):
        c = theme_manager.current
        self.setStyleSheet(f"QWidget {{ background-color: {c.canvas_overlay}; border: none; }}")
