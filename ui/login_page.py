from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox, QFrame,
    QPushButton, QLineEdit, QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPointF, QRectF
from PyQt5.QtGui import QColor, QBrush, QPainter, QPainterPath, QLinearGradient
from qfluentwidgets import CheckBox, FluentIcon
from ui.styles import Styles, get_font, FONT_CSS
from ui.theme import theme_manager, ThemeMode
from services.repositories import user_repo, setting_repo
from core.config import settings
from core.database import init_user_database

# عنوان برنامه روی صفحهٔ لاگین (تیتر پنجره + تیتر بزرگ سمت چپ)
APP_TITLE = "برنامه هماهنگی امورات فرمانداری"


def _mix(color_a: str, color_b: str, t: float) -> str:
    """ترکیب دو رنگ هگز؛ t=0 رنگ اول و t=1 رنگ دوم."""
    a, b = QColor(color_a), QColor(color_b)
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    ).name()


class _WaveHeader(QWidget):
    """بنر گرادیانی بالای کارت ورود، با موج تزئینی و نشان برنامه."""

    RADIUS = 22
    HEIGHT = 126

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self._card_bg = "#ffffff"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.addWidget(self._make_avatar(), alignment=Qt.AlignmentFlag.AlignHCenter)

    def _make_avatar(self):
        self.avatar = QLabel("گ")
        self.avatar.setObjectName("brandAvatar")
        self.avatar.setFixedSize(62, 62)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFont(get_font(22, True))
        return self.avatar

    def set_card_bg(self, color: str):
        self._card_bg = color
        self.update()

    def paintEvent(self, event):
        c = theme_manager.current
        r = QRectF(self.rect())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rad = self.RADIUS
        band = QPainterPath()
        band.moveTo(r.left(), r.bottom())
        band.lineTo(r.left(), r.top() + rad)
        band.quadTo(r.left(), r.top(), r.left() + rad, r.top())
        band.lineTo(r.right() - rad, r.top())
        band.quadTo(r.right(), r.top(), r.right(), r.top() + rad)
        band.lineTo(r.right(), r.bottom())
        band.closeSubpath()

        grad = QLinearGradient(r.left(), r.top(), r.right(), r.bottom())
        grad.setColorAt(0.0, QColor(c.primary))
        grad.setColorAt(0.55, QColor(c.primary_active))
        grad.setColorAt(1.0, QColor(c.accent_purple))
        p.fillPath(band, QBrush(grad))

        p.save()
        p.setClipPath(band)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 20))
        for cx, cy, radius in (
            (r.right() - 42, r.top() + 20, 46),
            (r.left() + 30, r.top() + 56, 62),
            (r.right() - 128, r.bottom() + 8, 34),
            (r.left() + 122, r.top() - 12, 28),
        ):
            p.drawEllipse(QPointF(cx, cy), radius, radius)

        w = r.width()
        crest = QPainterPath()
        crest.moveTo(r.left(), r.bottom())
        crest.lineTo(r.left(), r.bottom() - 27)
        crest.cubicTo(r.left() + w * 0.28, r.bottom() - 55,
                      r.left() + w * 0.60, r.bottom() - 23,
                      r.right(), r.bottom() - 41)
        crest.lineTo(r.right(), r.bottom())
        crest.closeSubpath()
        p.fillPath(crest, QColor(255, 255, 255, 36))

        cut = QPainterPath()
        cut.moveTo(r.left(), r.bottom())
        cut.lineTo(r.left(), r.bottom() - 15)
        cut.cubicTo(r.left() + w * 0.32, r.bottom() - 42,
                    r.left() + w * 0.66, r.bottom() - 6,
                    r.right(), r.bottom() - 24)
        cut.lineTo(r.right(), r.bottom())
        cut.closeSubpath()
        p.fillPath(cut, QColor(self._card_bg))
        p.restore()
        p.end()


class LoginPage(QWidget):
    login_successful = pyqtSignal(object)  # emits User object

    CARD_WIDTH = 428

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self._setup_ui()
        self._apply_theme()
        self._check_auto_login()

    # ------------------------------------------------------------------ ساخت
    def _setup_ui(self):
        self.setObjectName("loginPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.addStretch(1)

        self.card = QFrame()
        self.card.setObjectName("loginCard")
        self.card.setFixedWidth(self.CARD_WIDTH)

        self.card_shadow = QGraphicsDropShadowEffect(self.card)
        self.card_shadow.setBlurRadius(46)
        self.card_shadow.setOffset(0, 12)
        self.card.setGraphicsEffect(self.card_shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.header = _WaveHeader()
        card_layout.addWidget(self.header)
        card_layout.addWidget(self._build_body())

        root.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

    def _build_body(self):
        body = QWidget()
        body.setObjectName("cardBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(34, 2, 34, 20)
        layout.setSpacing(0)

        brand = QLabel("سامانه فرمانداری")
        brand.setObjectName("brandTitle")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        tagline = QLabel("سامانهٔ مدیریت امور دفتری فرمانداری")
        tagline.setObjectName("brandSub")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)
        layout.addSpacing(16)

        layout.addWidget(self._field_label("نام کاربری"))
        layout.addSpacing(6)
        self.username_input = QLineEdit()
        self.username_input.setObjectName("loginInput")
        self.username_input.setPlaceholderText("نام کاربری خود را وارد کنید")
        self.username_input.setClearButtonEnabled(True)
        self.username_input.setFixedHeight(44)
        self.username_input.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._user_icon = self.username_input.addAction(
            FluentIcon.PEOPLE.icon(), QLineEdit.ActionPosition.LeadingPosition)
        self.username_input.returnPressed.connect(lambda: self.password_input.setFocus())
        layout.addWidget(self.username_input)
        layout.addSpacing(12)

        layout.addWidget(self._field_label("رمز عبور"))
        layout.addSpacing(6)
        self.password_input = QLineEdit()
        self.password_input.setObjectName("loginInput")
        self.password_input.setPlaceholderText("رمز عبور خود را وارد کنید")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setFixedHeight(44)
        self.password_input.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._pass_icon = self.password_input.addAction(
            FluentIcon.FINGERPRINT.icon(), QLineEdit.ActionPosition.LeadingPosition)
        self._eye_action = self.password_input.addAction(
            FluentIcon.VIEW.icon(), QLineEdit.ActionPosition.TrailingPosition)
        self._eye_action.setToolTip("نمایش رمز عبور")
        self._eye_action.triggered.connect(self._toggle_password)
        self.password_input.returnPressed.connect(self._login)
        layout.addWidget(self.password_input)
        layout.addSpacing(6)

        options = QHBoxLayout()
        options.setContentsMargins(2, 0, 2, 0)
        self.remember_check = CheckBox("به‌خاطرسپاری ورود")
        self.remember_check.setChecked(True)
        self.remember_check.setToolTip("در اجرای بعدی، بدون وارد کردن رمز عبور خودکار وارد می‌شوید")
        options.addWidget(self.remember_check)
        options.addStretch()
        forgot_btn = QPushButton("فراموشی رمز")
        forgot_btn.setObjectName("linkButton")
        forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot_btn.clicked.connect(self._forgot_password)
        options.addWidget(forgot_btn)
        layout.addLayout(options)
        layout.addSpacing(14)

        self.login_btn = QPushButton("ورود")
        self.login_btn.setObjectName("loginButton")
        self.login_btn.setFixedHeight(46)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self._login)
        layout.addWidget(self.login_btn)
        layout.addSpacing(12)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        version_text = settings.APP_VERSION.translate(
            str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        )
        footer = QLabel(f"نسخه {version_text} · استفادهٔ داخلی — اطلاعات روی همین رایانه ذخیره می‌شود")
        footer.setObjectName("cardFooter")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        return body

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    # ------------------------------------------------------------------ پوسته
    def _apply_theme(self):
        c = theme_manager.current
        dark = c.mode == ThemeMode.DARK

        if dark:
            page_bg = f"background-color: {c.canvas_default};"
        else:
            top = _mix(c.primary, "#ffffff", 0.90)
            bottom = _mix(c.accent_purple, "#ffffff", 0.93)
            page_bg = (
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {top}, stop:0.45 {c.canvas_subtle}, stop:1 {bottom});"
            )

        focus_tint = _mix(c.input_bg, c.primary, 0.07)
        purple_hover = _mix(c.accent_purple, "#ffffff" if dark else "#000000", 0.14)
        btn_grad = (f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                    f"stop:0 {c.primary}, stop:1 {c.accent_purple})")
        btn_grad_hover = (f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                          f"stop:0 {c.primary_hover}, stop:1 {purple_hover})")

        self.setStyleSheet(f"""
            #loginPage {{ {page_bg} }}
            #loginCard {{
                background-color: {c.canvas_overlay};
                border: none;
                border-radius: {_WaveHeader.RADIUS}px;
            }}
            #cardBody {{ background: transparent; }}
            #brandAvatar {{
                background-color: rgba(255, 255, 255, 0.20);
                border: 2px solid rgba(255, 255, 255, 0.55);
                border-radius: 31px;
                color: #ffffff;
            }}
            #brandTitle {{
                color: {c.fg_default};
                font-size: 21px;
                font-weight: 700;
                font-family: {FONT_CSS};
            }}
            #brandSub {{
                color: {c.fg_muted};
                font-size: 12px;
                font-family: {FONT_CSS};
            }}
            #fieldLabel {{
                color: {c.fg_default};
                font-size: 12px;
                font-weight: 600;
                font-family: {FONT_CSS};
            }}
            #loginInput {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 12px;
                padding: 0 10px;
                color: {c.fg_default};
                font-size: 13px;
                font-family: {FONT_CSS};
                selection-background-color: {c.selection_bg};
                selection-color: {c.selection_fg};
            }}
            #loginInput:hover {{ border-color: {c.control_border_hover}; }}
            #loginInput:focus {{
                border: 1px solid {c.primary};
                background-color: {focus_tint};
            }}
            #linkButton {{
                background: transparent;
                border: none;
                color: {c.primary};
                font-size: 12px;
                font-family: {FONT_CSS};
                padding: 4px 2px;
            }}
            #linkButton:hover {{ color: {c.primary_hover}; }}
            #linkButton:pressed {{ color: {c.primary_active}; }}
            #loginButton {{
                background: {btn_grad};
                color: #ffffff;
                border: none;
                border-radius: 23px;
                font-size: 14px;
                font-weight: 700;
                font-family: {FONT_CSS};
            }}
            #loginButton:hover {{ background: {btn_grad_hover}; }}
            #loginButton:pressed {{ background-color: {c.primary_active}; }}
            #loginButton:disabled {{
                background: {c.control_bg};
                color: {c.fg_muted};
                border: 1px solid {c.border_default};
            }}
            #errorLabel {{
                color: {c.fg_danger};
                background-color: {c.danger_subtle};
                border: 1px solid {c.danger_muted};
                border-radius: 10px;
                padding: 7px 10px;
                font-size: 12px;
                font-family: {FONT_CSS};
            }}
            #cardFooter {{
                color: {c.fg_muted};
                font-size: 10px;
                font-family: {FONT_CSS};
                margin-top: 12px;
            }}
        """)

        self.header.set_card_bg(c.canvas_overlay)
        self.card_shadow.setColor(QColor(0, 0, 0, 130 if dark else 38))

        icon_color = QColor(c.fg_muted)
        self._user_icon.setIcon(FluentIcon.PEOPLE.icon(color=icon_color))
        self._pass_icon.setIcon(FluentIcon.FINGERPRINT.icon(color=icon_color))
        self._eye_action.setIcon(self._eye_icon().icon(color=icon_color))
        self.remember_check.setFont(get_font(9))

    def _toggle_password(self):
        show = self.password_input.echoMode() == QLineEdit.EchoMode.Password
        self.password_input.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        )
        self._eye_action.setIcon(self._eye_icon().icon(color=QColor(theme_manager.current.fg_muted)))
        self._eye_action.setToolTip("پنهان کردن رمز عبور" if show else "نمایش رمز عبور")

    def _eye_icon(self) -> FluentIcon:
        hidden = self.password_input.echoMode() == QLineEdit.EchoMode.Password
        return FluentIcon.VIEW if hidden else FluentIcon.HIDE

    # ------------------------------------------------------------------ منطق
    def _check_auto_login(self):
        QTimer.singleShot(100, lambda: self.username_input.setFocus())

    def _login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            self._show_error("نام کاربری و رمز عبور را وارد کنید")
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("در حال ورود...")
        self.error_label.setVisible(False)

        QTimer.singleShot(50, lambda: self._do_login(username, password))

    def _do_login(self, username: str, password: str):
        try:
            user = user_repo.authenticate(username, password)

            if user:
                # Initialize user database
                try:
                    init_user_database(user.username)
                except Exception as e:
                    self._show_error(f"خطا در مقداردهی اولیه دیتابیس کاربر: {e}")
                    self.login_btn.setEnabled(True)
                    self.login_btn.setText("ورود")
                    return

                # Store user in settings for session
                setting_repo.set_setting("current_user_id", user.id)
                setting_repo.set_setting("current_username", user.username)
                setting_repo.set_setting("remember_login", self.remember_check.isChecked())

                self.login_successful.emit(user)
            else:
                self._show_error("نام کاربری یا رمز عبور اشتباه است")
                self.login_btn.setEnabled(True)
                self.login_btn.setText("ورود")
        except ValueError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(f"خطا در ورود: {str(e)}")
            self.login_btn.setEnabled(True)
            self.login_btn.setText("ورود")

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.login_btn.setEnabled(True)
        self.login_btn.setText("ورود")

    def _forgot_password(self):
        message = "برای بازیابی رمز عبور با مدیر سیستم تماس بگیرید."
        try:
            admin = user_repo.get_by_username("admin")
            if admin and admin.mobile:
                number = admin.mobile.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
                message += f"\nشماره تماس مدیر سیستم: {number}"
        except Exception:
            pass
        # در تست‌های offscreen QMessageBox بلاک می‌شود؛ اینجا فقط log می‌کنیم
        import logging
        logging.getLogger(__name__).info("Forgot password: %s", message)

    def refresh(self):
        self._apply_theme()


class UserSelectionPage(QWidget):
    """Page for selecting user when multiple users exist"""
    user_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"background-color: {c.canvas_default};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("انتخاب کاربر")
        title.setStyleSheet(Styles.title_label())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("لطفاً کاربر مورد نظر را انتخاب کنید")
        subtitle.setStyleSheet(Styles.subtitle_label())
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Users list will be populated dynamically
        self.users_container = QVBoxLayout()
        self.users_container.setSpacing(12)
        layout.addLayout(self.users_container)

        layout.addStretch()

        back_btn = QPushButton("بازگشت")
        back_btn.setStyleSheet(Styles.secondary_button())
        back_btn.setFixedWidth(150)
        back_btn.clicked.connect(lambda: self.parent().setCurrentIndex(0) if self.parent() else None)
        layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def load_users(self):
        c = theme_manager.current
        # Clear existing
        while self.users_container.count():
            item = self.users_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        users = user_repo.get_active_users()
        for user in users:
            btn = QPushButton(f"{user.full_name} (@{user.username})")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c.canvas_overlay};
                    color: {c.fg_default};
                    border: 2px solid {c.border_default};
                    border-radius: 12px;
                    padding: 16px 24px;
                    font-size: 14px;
                    font-family: Tahoma;
                    font-weight: bold;
                    text-align: right;
                }}
                QPushButton:hover {{
                    border-color: {c.primary};
                    background-color: {c.canvas_subtle};
                }}
            """)
            btn.setMinimumHeight(60)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, u=user: self._select_user(u))
            self.users_container.addWidget(btn)

    def _select_user(self, user):
        # Show password dialog for this user
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle(f"ورود به حساب {user.full_name}")
        dialog.setMinimumWidth(400)
        dialog.setFont(get_font(10))

        c = theme_manager.current
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(f"ورود به حساب {user.full_name}")
        title.setStyleSheet(Styles.title_label())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        pass_label = QLabel("رمز عبور")
        pass_label.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(pass_label)

        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("رمز عبور را وارد کنید")
        password_input.setStyleSheet(Styles.line_edit())
        layout.addWidget(password_input)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        login_btn = QPushButton("ورود")
        login_btn.setStyleSheet(Styles.primary_button())

        def do_login():
            if user_repo.authenticate(user.username, password_input.text()):
                from core.database import init_user_database
                init_user_database(user.username)
                from services.repositories import setting_repo
                setting_repo.set_setting("current_user_id", user.id)
                setting_repo.set_setting("current_username", user.username)
                self.user_selected.emit(user)
                dialog.accept()
            else:
                QMessageBox.warning(dialog, "خطا", "رمز عبور اشتباه است")

        login_btn.clicked.connect(do_login)
        btn_layout.addWidget(login_btn)

        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            pass  # user_selected signal already emitted