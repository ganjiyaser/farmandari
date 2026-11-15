"""دیالوگ تأیید همسان و خوانا برای عملیات‌های حساس (حذف، بازیابی، ارسال انبوه)."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.styles import FONT_CSS, FS_BODY, FS_SECTION, SPACE_LG, Styles, get_font
from ui.theme import theme_manager


class ConfirmDialog(QDialog):
    """دیالوگ تأیید فارسی با دکمه‌های واضح؛ بر خلاف QMessageBox دکمه‌ها انگلیسی نیستند."""

    def __init__(self, parent=None, title: str = "", message: str = "",
                 yes_text: str = "تأیید", cancel_text: str = "انصراف",
                 danger: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFont(get_font(10))
        self.setMinimumWidth(440)

        c = theme_manager.current
        self.setStyleSheet(f"QDialog {{ background-color: {c.canvas_overlay}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, 20)
        root.setSpacing(12)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                font-size: {FS_SECTION}px;
                font-family: {FONT_CSS};
                font-weight: 700;
                color: {c.danger if danger else c.fg_default};
            }}
        """)
        root.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message_label.setStyleSheet(f"""
            QLabel {{
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
            }}
        """)
        root.addWidget(message_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        self.yes_button = QPushButton(yes_text)
        self.yes_button.setStyleSheet(Styles.danger_button() if danger else Styles.primary_button())
        self.yes_button.setMinimumWidth(120)
        self.yes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.yes_button.clicked.connect(self.accept)

        self.cancel_button = QPushButton(cancel_text)
        self.cancel_button.setStyleSheet(Styles.secondary_button())
        self.cancel_button.setMinimumWidth(120)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)

        buttons.addWidget(self.yes_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        # در عملیات خطرناک، Enter تصادفی نباید موجب حذف شود
        if danger:
            self.yes_button.setAutoDefault(False)
            self.cancel_button.setDefault(True)
            self.cancel_button.setFocus()
        else:
            self.cancel_button.setAutoDefault(False)
            self.yes_button.setDefault(True)
            self.yes_button.setFocus()


def confirm(parent=None, title: str = "", message: str = "",
            yes_text: str = "تأیید", cancel_text: str = "انصراف",
            danger: bool = False) -> bool:
    """نمایش دیالوگ تأیید و بازگرداندن True در صورت تأیید کاربر."""
    dialog = ConfirmDialog(parent, title, message, yes_text, cancel_text, danger)
    return dialog.exec() == QDialog.DialogCode.Accepted


def confirm_delete(parent=None, noun: str = "مورد", name: str = None,
                   extra: str = None, yes_text: str = "حذف کن") -> bool:
    """تأیید حذف با ذکر دقیق آنچه حذف می‌شود."""
    subject = f"{noun} «{name}»" if name else noun
    lines = [f"{subject} حذف شود؟", "این عملیات قابل بازگشت نیست."]
    if extra:
        lines.append(extra)
    return confirm(parent, title=f"حذف {noun}", message="\n".join(lines),
                   yes_text=yes_text, danger=True)
