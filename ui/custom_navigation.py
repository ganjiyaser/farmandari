from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from ui.theme import theme_manager
from ui.styles import get_font, FONT_CSS


NAV_BADGES = {
    "dashboard": "دا",
    "contacts": "مخ",
    "officials": "مس",
    "calendar": "تق",
    "decisions": "صو",
    "letters": "ان",
    "groups": "گر",
    "sms": "پک",
    "files": "فا",
    "reports": "گز",
    "notes": "یا",
    "tasks": "کا",
    "settings": "تن",
    "users": "کر",
}


class NavItem(QFrame):
    clicked_signal = pyqtSignal(str)

    def __init__(self, item_id, icon, text, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(46)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        badge_text = NAV_BADGES.get(item_id, (text or "•")[:2])
        self.badge = QLabel(badge_text)
        self.badge.setFixedSize(30, 30)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFont(get_font(9, True))

        self.text_label = QLabel(text)
        self.text_label.setFont(get_font(11))
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.badge)
        layout.addWidget(self.text_label, 1)
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_signal.emit(self.item_id)
        super().mousePressEvent(event)

    def set_selected(self, selected):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        c = theme_manager.current
        if self._selected:
            self.setStyleSheet(f"""
                NavItem {{
                    background-color: {c.primary};
                    border: none;
                    border-radius: 10px;
                }}
            """)
            self.badge.setStyleSheet(f"""
                background-color: rgba(255, 255, 255, 0.18);
                color: {c.fg_on_emphasis};
                border: none;
                border-radius: 8px;
            """)
            self.text_label.setStyleSheet(f"""
                color: {c.fg_on_emphasis};
                background: transparent;
                border: none;
                font-weight: 600;
                font-family: {FONT_CSS};
            """)
        else:
            self.setStyleSheet(f"""
                NavItem {{
                    background-color: transparent;
                    border: none;
                    border-radius: 10px;
                }}
                NavItem:hover {{
                    background-color: {c.canvas_subtle};
                }}
            """)
            self.badge.setStyleSheet(f"""
                background-color: {c.canvas_subtle};
                color: {c.primary};
                border: none;
                border-radius: 8px;
                font-weight: 600;
            """)
            self.text_label.setStyleSheet(f"""
                color: {c.fg_default};
                background: transparent;
                border: none;
                font-family: {FONT_CSS};
            """)


class CustomNavigation(QWidget):
    item_clicked = pyqtSignal(str)
    logout_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(248)
        self.items = {}
        self.current_item = None
        self._bottom_spacer = None
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            CustomNavigation {{
                background-color: {c.canvas_overlay};
                border-left: 1px solid {c.border_default};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("navHeader")
        header.setStyleSheet(f"""
            QFrame#navHeader {{
                background-color: {c.primary};
                border: none;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 20, 18, 18)
        header_layout.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel("ب")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFont(get_font(16, True))
        mark.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.16);
            color: white;
            border: none;
            border-radius: 12px;
        """)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        app_name = QLabel("سامانه فرمانداری")
        app_name.setFont(get_font(12, True))
        app_name.setStyleSheet("color: white; background: transparent; border: none;")
        app_sub = QLabel("امور دفتری فرمانداری")
        app_sub.setFont(get_font(9))
        app_sub.setStyleSheet("color: rgba(255,255,255,0.75); background: transparent; border: none;")
        titles.addWidget(app_name)
        titles.addWidget(app_sub)
        brand_row.addWidget(mark)
        brand_row.addLayout(titles, 1)
        header_layout.addLayout(brand_row)
        layout.addWidget(header)

        self.items_container = QWidget()
        self.items_container.setStyleSheet("background: transparent; border: none;")
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(10, 12, 10, 8)
        self.items_layout.setSpacing(4)
        layout.addWidget(self.items_container, 1)

        footer = QFrame()
        footer.setObjectName("navFooter")
        footer.setStyleSheet(f"""
            QFrame#navFooter {{
                background-color: {c.canvas_subtle};
                border: none;
                border-top: 1px solid {c.border_default};
            }}
        """)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 12, 12, 12)
        footer_layout.setSpacing(8)

        self.user_name = QLabel("کاربر سیستم")
        self.user_name.setFont(get_font(10, True))
        self.user_role = QLabel("")
        self.user_role.setFont(get_font(9))
        self.user_name.setStyleSheet(f"color: {c.fg_default}; background: transparent; border: none;")
        self.user_role.setStyleSheet(f"color: {c.fg_muted}; background: transparent; border: none;")
        footer_layout.addWidget(self.user_name)
        footer_layout.addWidget(self.user_role)

        logout_btn = QPushButton("خروج از حساب")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setFont(get_font(10))
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c.danger};
                border: 1px solid {c.border_default};
                border-radius: 8px;
                padding: 8px 12px;
                font-family: {FONT_CSS};
            }}
            QPushButton:hover {{
                background-color: {c.danger_subtle};
                border-color: {c.danger};
            }}
        """)
        logout_btn.clicked.connect(self.logout_requested.emit)
        footer_layout.addWidget(logout_btn)
        layout.addWidget(footer)

    def set_user(self, user):
        if not user:
            return
        self.user_name.setText(getattr(user, "full_name", None) or user.username)
        role = getattr(user, "default_role", None)
        role_map = {
            "admin": "مدیر سیستم",
            "district_governor": "بخشدار",
            "office_manager": "مسئول دفتر",
            "regular_user": "کاربر",
        }
        key = role.value if hasattr(role, "value") else str(role or "")
        self.user_role.setText(role_map.get(key, user.username))

    def add_item(self, item_id, icon, text, handler, position="top"):
        item = NavItem(item_id, icon, text, self)
        item.clicked_signal.connect(lambda _id=item_id: handler(_id) if handler else None)
        self.items[item_id] = item
        if position == "bottom":
            if self._bottom_spacer is None:
                self._bottom_spacer = QWidget()
                self._bottom_spacer.setSizePolicy(
                    QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
                )
                self._bottom_spacer.setStyleSheet("background: transparent; border: none;")
                self.items_layout.addWidget(self._bottom_spacer, 1)
            self.items_layout.addWidget(item)
        else:
            self.items_layout.addWidget(item)

    def set_current(self, item_id):
        if self.current_item:
            self.current_item.set_selected(False)
        self.current_item = self.items.get(item_id)
        if self.current_item:
            self.current_item.set_selected(True)

    def refresh_theme(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            CustomNavigation {{
                background-color: {c.canvas_overlay};
                border-left: 1px solid {c.border_default};
            }}
        """)
        for item in self.items.values():
            item._update_style()
        self.user_name.setStyleSheet(f"color: {c.fg_default}; background: transparent; border: none;")
        self.user_role.setStyleSheet(f"color: {c.fg_muted}; background: transparent; border: none;")
