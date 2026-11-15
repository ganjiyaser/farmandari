from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QDialog, QFormLayout, QComboBox,
    QTextEdit, QCheckBox, QScrollArea, QTabWidget, QGroupBox,
    QAbstractItemView, QMenu, QFileDialog
)
import os
import jdatetime
from typing import Optional
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import user_repo, role_repo, permission_repo, setting_repo
from models.models import User, Role, Permission, UserRole, PermissionName
from core.database import get_user_db_path, get_user_files_dir

MIN_PASSWORD_LEN = 8


def _current_user() -> Optional[User]:
    try:
        uid = setting_repo.get_setting("current_user_id")
        return user_repo.get_by_id(int(uid)) if uid else None
    except Exception:
        return None


class UserDialog(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("ویرایش کاربر" if user else "کاربر جدید")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)
        self.setFont(get_font(10))
        self._setup_ui()
        if user:
            self._load_data()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("ویرایش کاربر" if self.user else "کاربر جدید")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(16, True))
        layout.addWidget(title)

        # Tabs
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
                font-family: Tahoma;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {c.canvas_overlay};
                color: {c.fg_default};
                font-weight: bold;
                border-bottom: 2px solid {c.primary};
            }}
        """)

        tabs.addTab(self._create_basic_tab(), "اطلاعات پایه")
        tabs.addTab(self._create_access_tab(), "دسترسی‌ها")
        tabs.addTab(self._create_settings_tab(), "تنظیمات")

        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("ذخیره")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _create_basic_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        self.username_input = QLineEdit()
        self.username_input.setStyleSheet(Styles.line_edit())
        self.username_input.setPlaceholderText("نام کاربری منحصر به فرد")
        layout.addRow(self._make_label("نام کاربری:"), self.username_input)

        self.email_input = QLineEdit()
        self.email_input.setStyleSheet(Styles.line_edit())
        self.email_input.setPlaceholderText("email@example.com")
        layout.addRow(self._make_label("ایمیل:"), self.email_input)

        self.first_name_input = QLineEdit()
        self.first_name_input.setStyleSheet(Styles.line_edit())
        self.first_name_input.setPlaceholderText("نام")
        layout.addRow(self._make_label("نام:"), self.first_name_input)

        self.last_name_input = QLineEdit()
        self.last_name_input.setStyleSheet(Styles.line_edit())
        self.last_name_input.setPlaceholderText("نام خانوادگی")
        layout.addRow(self._make_label("نام خانوادگی:"), self.last_name_input)

        self.mobile_input = QLineEdit()
        self.mobile_input.setStyleSheet(Styles.line_edit())
        self.mobile_input.setPlaceholderText("09xxxxxxxxx")
        layout.addRow(self._make_label("موبایل:"), self.mobile_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet(Styles.line_edit())
        self.password_input.setPlaceholderText(
            "تغییر رمز عبور (اختیاری)" if self.user else f"رمز عبور (حداقل {MIN_PASSWORD_LEN} کاراکتر)"
        )
        layout.addRow(self._make_label("رمز عبور:"), self.password_input)

        # Status
        self.active_check = QCheckBox("کاربر فعال است")
        self.active_check.setStyleSheet(f"color: {c.fg_default}; font-family: Tahoma; spacing: 8px;")
        self.active_check.setChecked(True)
        layout.addRow("", self.active_check)

        self.superuser_check = QCheckBox("مدیر کل (Superuser)")
        self.superuser_check.setStyleSheet(f"color: {c.fg_default}; font-family: Tahoma; spacing: 8px;")
        # Granting superuser must not be available to a non-superuser who only
        # holds the user_management permission (privilege escalation).
        if not (current := _current_user()) or not current.is_superuser:
            self.superuser_check.setEnabled(False)
            self.superuser_check.setToolTip(
                "فقط مدیر کل می‌تواند سطح «مدیر کل» را تغییر دهد."
            )
        layout.addRow("", self.superuser_check)

        return widget

    def _create_access_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Role selection
        role_group = QGroupBox("نقش اصلی")
        role_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: Tahoma; font-weight: bold; color: {c.fg_default};
                border: 1px solid {c.border_default}; border-radius: 6px;
                padding: 12px; margin-top: 8px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; background: {c.canvas_overlay}; }}
        """)
        role_layout = QVBoxLayout(role_group)

        self.role_combo = QComboBox()
        self.role_combo.setStyleSheet(Styles.combo_box())
        for label, role in [
            ("مدیر", UserRole.ADMIN),
            ("بخشدار", UserRole.DISTRICT_GOVERNOR),
            ("مسئول دفتر", UserRole.OFFICE_MANAGER),
            ("کاربر عادی", UserRole.REGULAR_USER),
        ]:
            self.role_combo.addItem(label, role)
        role_layout.addWidget(self.role_combo)

        layout.addWidget(role_group)

        # Direct permissions
        perm_group = QGroupBox("دسترسی‌های مستقیم (Override)")
        perm_group.setStyleSheet(role_group.styleSheet())
        perm_layout = QVBoxLayout(perm_group)

        self.perm_scroll = QScrollArea()
        self.perm_scroll.setWidgetResizable(True)
        self.perm_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.perm_container = QWidget()
        self.perm_container.setStyleSheet("background: transparent;")
        self.perm_layout = QVBoxLayout(self.perm_container)
        self.perm_layout.setSpacing(4)
        self.perm_scroll.setWidget(self.perm_container)
        perm_layout.addWidget(self.perm_scroll)

        layout.addWidget(perm_group, 1)

        return widget

    def _create_settings_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 8, 8, 8)

        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(100)
        self.notes_input.setStyleSheet(Styles.text_edit())
        self.notes_input.setPlaceholderText("یادداشت‌های داخلی درباره کاربر...")
        layout.addRow(self._make_label("یادداشت‌ها:"), self.notes_input)

        return widget

    def _make_label(self, text):
        c = theme_manager.current
        lbl = QLabel(text)
        lbl.setFont(get_font(10, True))
        lbl.setStyleSheet(f"color: {c.fg_default}; font-family: Tahoma; min-width: 100px;")
        return lbl

    def _load_data(self):
        self.username_input.setText(self.user.username or "")
        self.email_input.setText(self.user.email or "")
        self.first_name_input.setText(self.user.first_name or "")
        self.last_name_input.setText(self.user.last_name or "")
        self.mobile_input.setText(self.user.mobile or "")
        self.password_input.setPlaceholderText("رمز عبور فعلی حفظ می‌شود")
        self.active_check.setChecked(self.user.is_active)
        self.superuser_check.setChecked(self.user.is_superuser)
        self.notes_input.setPlainText(self.user.settings.get("notes", "") if self.user.settings else "")

        # Set role
        for i in range(self.role_combo.count()):
            if self.role_combo.itemData(i) == self.user.default_role:
                self.role_combo.setCurrentIndex(i)
                break

        # Load direct permissions
        self._load_permissions()

    def _load_permissions(self):
        c = theme_manager.current
        # Clear
        while self.perm_layout.count():
            item = self.perm_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get user's direct permissions
        user_perms = user_repo.get_user_permissions(self.user.id)
        
        # Group permissions by category
        perms = permission_repo.get_all()
        categories = {}
        for perm in perms:
            cat = perm.category or "other"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(perm)

        for cat, perms_list in sorted(categories.items()):
            cat_label = QLabel(cat)
            cat_label.setStyleSheet(f"color: {c.fg_muted}; font-weight: bold; font-size: 11px; padding-top: 8px;")
            self.perm_layout.addWidget(cat_label)

            for perm in perms_list:
                check = QCheckBox(f"{perm.label} ({perm.name.value})")
                check.setProperty("perm_name", perm.name)
                check.setChecked(perm.name in user_perms)
                check.setStyleSheet(f"color: {c.fg_default}; font-size: 11px; font-family: Tahoma; spacing: 6px;")
                self.perm_layout.addWidget(check)

        self.perm_layout.addStretch()

    def _save(self):
        username = self.username_input.text().strip()
        if not username:
            QMessageBox.warning(self, "خطا", "نام کاربری الزامی است")
            return

        # Check uniqueness
        existing = user_repo.get_by_username(username)
        if existing and (not self.user or existing.id != self.user.id):
            QMessageBox.warning(self, "خطا", "این نام کاربری قبلاً ثبت شده است")
            return

        data = {
            "username": username,
            "email": self.email_input.text().strip() or None,
            "first_name": self.first_name_input.text().strip(),
            "last_name": self.last_name_input.text().strip(),
            "mobile": self.mobile_input.text().strip() or None,
            "is_active": self.active_check.isChecked(),
            "is_superuser": self.superuser_check.isChecked(),
        }

        # Get role
        role = self.role_combo.currentData()
        if role:
            data["default_role"] = role

        # Handle password
        new_password = self.password_input.text()
        if new_password and len(new_password) < MIN_PASSWORD_LEN:
            QMessageBox.warning(
                self, "خطا", f"رمز عبور باید حداقل {MIN_PASSWORD_LEN} کاراکتر باشد"
            )
            return
        if new_password:
            data["password"] = new_password

        # Only a superuser may change these flags; the checkbox is disabled for
        # everyone else but keep the guard server-side too.
        current = _current_user()
        if not current or not current.is_superuser:
            data.pop("is_superuser", None)
            if self.user:
                data["is_superuser"] = self.user.is_superuser

        try:
            if self.user:
                user = user_repo.update_user(self.user.id, **data)
                # Update permissions
                self._save_permissions(user.id)
            else:
                if not new_password:
                    QMessageBox.warning(
                        self, "خطا",
                        f"برای کاربر جدید رمز عبور الزامی است (حداقل {MIN_PASSWORD_LEN} کاراکتر).",
                    )
                    return
                user = user_repo.create_user(
                    username=username,
                    password=new_password,
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    email=data.get("email"),
                    mobile=data.get("mobile"),
                    role=role or UserRole.REGULAR_USER,
                    # Previously present in `data` but never passed through, so
                    # both checkboxes silently had no effect on creation.
                    is_active=bool(data.get("is_active", True)),
                    is_superuser=bool(data.get("is_superuser", False)),
                )
                # Update permissions
                self._save_permissions(user.id)

            # Update notes
            settings_dict = self.user.settings if self.user else {}
            settings_dict["notes"] = self.notes_input.toPlainText().strip()
            user_repo.update_user(user.id, settings=settings_dict)

            QMessageBox.information(self, "موفق", "کاربر ذخیره شد")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _save_permissions(self, user_id):
        # The checkboxes show *effective* permissions (direct + role). Writing
        # `remove_permission()` for an unchecked role permission was a no-op, so
        # the "Override" column could never actually take anything away. An
        # unchecked role permission now becomes an explicit deny row, which
        # User.has_permission honours.
        role_perms = set()
        try:
            target = user_repo.get_by_id(user_id)
            for role in (target.roles if target else []):
                for p in role.permissions:
                    role_perms.add(p.name)
        except Exception:
            target = None

        for i in range(self.perm_layout.count()):
            item = self.perm_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, QCheckBox):
                perm_name = widget.property("perm_name")
                if perm_name:
                    if widget.isChecked():
                        user_repo.add_permission(user_id, perm_name, True)
                    elif perm_name in role_perms:
                        user_repo.add_permission(user_id, perm_name, False)
                    else:
                        user_repo.remove_permission(user_id, perm_name)


class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None, user_id=None):
        super().__init__(parent)
        self.user_id = user_id
        current = _current_user()
        self.current_user_id = current.id if current else None
        # Re-authentication only makes sense for your own account; an admin
        # resetting somebody else's password cannot know their old one.
        self.is_self = bool(user_id) and user_id == self.current_user_id
        self.current_is_superuser = bool(current and current.is_superuser)
        self.setWindowTitle("تغییر رمز عبور")
        self.setMinimumWidth(400)
        self.setFont(get_font(10))
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("تغییر رمز عبور")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(16, True))
        layout.addWidget(title)

        old_label = QLabel("رمز عبور فعلی:")
        self.old_pass = QLineEdit()
        self.old_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pass.setPlaceholderText("رمز عبور فعلی")
        self.old_pass.setStyleSheet(Styles.line_edit())
        layout.addWidget(old_label)
        layout.addWidget(self.old_pass)
        if not self.is_self:
            # Somebody else's account: the old password is not ours to know.
            old_label.setVisible(False)
            self.old_pass.setVisible(False)

        self.new_pass = QLineEdit()
        self.new_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pass.setPlaceholderText("رمز عبور جدید")
        self.new_pass.setStyleSheet(Styles.line_edit())
        layout.addWidget(QLabel("رمز عبور جدید:"))
        layout.addWidget(self.new_pass)

        self.confirm_pass = QLineEdit()
        self.confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pass.setPlaceholderText("تکرار رمز عبور جدید")
        self.confirm_pass.setStyleSheet(Styles.line_edit())
        layout.addWidget(QLabel("تکرار رمز عبور:"))
        layout.addWidget(self.confirm_pass)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("ذخیره")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _save(self):
        if self.new_pass.text() != self.confirm_pass.text():
            QMessageBox.warning(self, "خطا", "رمز عبور جدید و تکرار آن یکسان نیستند")
            return

        if len(self.new_pass.text()) < MIN_PASSWORD_LEN:
            QMessageBox.warning(
                self, "خطا", f"رمز عبور باید حداقل {MIN_PASSWORD_LEN} کاراکتر باشد"
            )
            return

        if self.is_self:
            # Re-authenticate before allowing a password change.
            old = self.old_pass.text()
            if not old:
                QMessageBox.warning(self, "خطا", "رمز عبور فعلی را وارد کنید")
                return
            user = user_repo.get_by_id(self.user_id) if self.user_id else None
            if not user or not user.check_password(old):
                QMessageBox.warning(self, "خطا", "رمز عبور فعلی اشتباه است")
                return
        elif not self.current_is_superuser:
            QMessageBox.warning(
                self, "خطا", "فقط مدیر کل می‌تواند رمز عبور دیگران را تغییر دهد"
            )
            return

        if user_repo.change_password(self.user_id, self.new_pass.text()):
            QMessageBox.information(self, "موفق", "رمز عبور تغییر کرد")
            self.accept()
        else:
            QMessageBox.critical(self, "خطا", "خطا در تغییر رمز عبور")


class UsersPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self._setup_ui()
        self._load_users()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("مدیریت کاربران")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(18, True))
        header.addWidget(title)
        header.addStretch()

        add_btn = QPushButton("+ کاربر جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_user)
        header.addWidget(add_btn)

        layout.addLayout(header)

        # Search/Filter
        filter_frame = QFrame()
        filter_frame.setStyleSheet(Styles.card())
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(16, 12, 16, 12)
        filter_layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجو بر اساس نام، نام کاربری، ایمیل...")
        self.search_input.setStyleSheet(Styles.line_edit())
        # Debounce: every keystroke refetched all users from the DB, ran a
        # permission query per row and rebuilt the table.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._on_filter)
        self.search_input.textChanged.connect(lambda *_: self._search_timer.start())
        filter_layout.addWidget(self.search_input)

        self.role_filter = QComboBox()
        self.role_filter.setStyleSheet(Styles.combo_box())
        self.role_filter.addItems(["همه نقش‌ها", "مدیر", "بخشدار", "مسئول دفتر", "کاربر عادی"])
        self.role_filter.currentTextChanged.connect(self._on_filter)
        self.role_filter.setFixedWidth(180)
        filter_layout.addWidget(self.role_filter)

        self.status_filter = QComboBox()
        self.status_filter.setStyleSheet(Styles.combo_box())
        self.status_filter.addItems(["همه", "فعال", "غیرفعال"])
        self.status_filter.currentTextChanged.connect(self._on_filter)
        self.status_filter.setFixedWidth(130)
        filter_layout.addWidget(self.status_filter)

        layout.addWidget(filter_frame)

        # Table
        table_frame = QFrame()
        table_frame.setStyleSheet(Styles.card())
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setStyleSheet(Styles.table_widget())
        self.table.setFont(get_font(10))
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ردیف", "نام کامل", "نام کاربری", "ایمیل", "نقش",
            "وضعیت", "آخرین ورود", "دسترسی‌ها", "عملیات"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # ستون ردیف و عملیات ثابت بمانند تا دکمه‌ها با Stretch له/بریده نشوند
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 56)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(8, 320)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._edit_user)
        table_layout.addWidget(self.table)

        layout.addWidget(table_frame)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(Styles.subtitle_label())
        layout.addWidget(self.count_label)

    def _load_users(self, users=None):
        c = theme_manager.current
        if users is None:
            # All accounts, so deactivated ones are visible and the
            # "غیرفعال" filter can actually match something.
            users = user_repo.get_all_users()

        self.table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(user.full_name))
            self.table.setItem(row, 2, QTableWidgetItem(user.username))
            self.table.setItem(row, 3, QTableWidgetItem(user.email or "-"))
            
            role_labels = {
                UserRole.ADMIN: "مدیر",
                UserRole.DISTRICT_GOVERNOR: "بخشدار",
                UserRole.OFFICE_MANAGER: "مسئول دفتر",
                UserRole.REGULAR_USER: "کاربر عادی"
            }
            self.table.setItem(row, 4, QTableWidgetItem(role_labels.get(user.default_role, "-")))
            
            status_text = "فعال" if user.is_active else "غیرفعال"
            if not user.is_active:
                status_text = "قفل شده" if user.locked_until else "غیرفعال"
            status_item = QTableWidgetItem(status_text)
            if user.is_active:
                status_item.setForeground(QColor(c.success))
            else:
                status_item.setForeground(QColor(c.danger))
            self.table.setItem(row, 5, status_item)

            last_login = "هرگز"
            if user.last_login_at:
                # Jalali, like the rest of the UI -- previously a Gregorian
                # strftime() sat next to jdatetime-formatted dates.
                last_login = jdatetime.datetime.strftime(
                    jdatetime.datetime.fromgregorian(datetime=user.last_login_at),
                    "%Y/%m/%d %H:%M",
                )
            self.table.setItem(row, 6, QTableWidgetItem(last_login))

            # Permissions count
            perms = user_repo.get_user_permissions(user.id)
            self.table.setItem(row, 7, QTableWidgetItem(f"{len(perms)} دسترسی"))

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(4)

            for text, color, callback in [
                ("ویرایش", c.accent_blue, lambda checked=False, uid=user.id: self._edit_user_by_id(uid)),
                ("دسترسی", c.success, lambda checked=False, uid=user.id: self._manage_permissions(uid)),
                ("رمز عبور", c.warning,
                 lambda checked=False, uid=user.id: self._change_password(uid)),
                ("حذف", c.danger, lambda checked=False, uid=user.id: self._delete_user(uid)),
            ]:
                btn = QPushButton(text)
                btn.setFixedHeight(28)
                if text == "حذف":
                    btn.setStyleSheet(Styles.table_action_button("danger"))
                elif text == "ویرایش":
                    btn.setStyleSheet(Styles.table_action_button("neutral"))
                elif text == "دسترسی":
                    btn.setStyleSheet(Styles.table_action_button("primary"))
                else:
                    btn.setStyleSheet(Styles.table_action_button("warning"))
                btn.clicked.connect(callback)
                actions_layout.addWidget(btn)

            self.table.setCellWidget(row, 8, actions_widget)
            self.table.setRowHeight(row, 42)

        self.count_label.setText(f"تعداد: {len(users)} کاربر")

    def _on_filter(self, _text=None):
        search = self.search_input.text().strip().lower()
        role_text = self.role_filter.currentText()
        status_text = self.status_filter.currentText()

        role_map = {
            "مدیر": UserRole.ADMIN,
            "بخشدار": UserRole.DISTRICT_GOVERNOR,
            "مسئول دفتر": UserRole.OFFICE_MANAGER,
            "کاربر عادی": UserRole.REGULAR_USER,
        }

        users = user_repo.get_all_users()
        filtered = []
        for u in users:
            if search:
                hay = f"{u.username} {u.full_name} {u.email or ''}".lower()
                if search not in hay:
                    continue
            if role_text != "همه نقش‌ها":
                if u.default_role != role_map.get(role_text):
                    continue
            if status_text == "فعال" and not u.is_active:
                continue
            if status_text == "غیرفعال" and u.is_active:
                continue
            filtered.append(u)
        self._load_users(filtered)

    def _add_user(self):
        dlg = UserDialog(self)
        if dlg.exec():
            self._load_users()

    def _edit_user(self, index):
        item = self.table.item(index.row(), 2)
        if item:
            user = user_repo.get_by_username(item.text())
            if user:
                self._edit_user_by_id(user.id)

    def _edit_user_by_id(self, uid):
        user = user_repo.get_by_id(uid)
        if user:
            dlg = UserDialog(self, user=user)
            if dlg.exec():
                self._load_users()

    def _manage_permissions(self, uid):
        user = user_repo.get_by_id(uid)
        if user:
            dlg = UserDialog(self, user=user)
            dlg.exec()

    def _change_password(self, uid):
        dlg = ChangePasswordDialog(self, user_id=uid)
        dlg.exec()

    def _delete_user(self, uid):
        user = user_repo.get_by_id(uid)
        if not user:
            return

        if user.is_superuser:
            QMessageBox.warning(self, "خطا", "نمی‌توان کاربر superuser را حذف کرد")
            return

        c = user_repo.get_by_id(uid)
        if c and confirm_delete(
            self, noun="کاربر", name=f"{c.full_name} (@{c.username})",
            extra="داده‌های شخصی این کاربر (یادداشت‌ها، وظایف، جلسات) نیز حذف خواهند شد.",
        ):
            try:
                user_repo.delete(uid)
                # دیتابیس و پوشهٔ فایل‌ها بین همهٔ کاربران مشترک است؛ حذف کاربر
                # فقط ردیف‌های متعلق به او (روابط cascade) را پاک می‌کند.
                self._load_users()
                QMessageBox.information(self, "موفق", "کاربر و داده‌های او حذف شدند")
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        username_item = self.table.item(row, 2)
        if not username_item:
            return
        user = user_repo.get_by_username(username_item.text())
        if not user:
            return

        menu = QMenu(self)
        menu.setFont(get_font(10))

        actions = [
            ("ویرایش", lambda: self._edit_user_by_id(user.id)),
            ("مدیریت دسترسی", lambda: self._manage_permissions(user.id)),
            ("تغییر رمز عبور", lambda: self._change_password(user.id)),
            ("پشتیبان‌گیری داده‌ها", lambda: self._backup_user_data(user)),
            ("حذف", lambda: self._delete_user(user.id)),
        ]
        for text, cb in actions:
            action = menu.addAction(text)
            action.triggered.connect(cb)

        menu.exec(self.table.mapToGlobal(pos))

    def _backup_user_data(self, user):
        from core.config import settings
        import shutil
        import zipfile
        from datetime import datetime

        dest, _ = QFileDialog.getSaveFileName(
            self, "ذخیره پشتیبان داده‌های کاربر",
            f"backup_{user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            "فایل‌های ZIP (*.zip)"
        )
        if not dest:
            return

        try:
            with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
                # User database
                user_db_path = get_user_db_path(user.username)
                if user_db_path.exists():
                    zf.write(user_db_path, f"{user.username}/user.db")
                
                # User files
                user_files_dir = get_user_files_dir(user.username)
                if user_files_dir.exists():
                    for root, dirs, files in os.walk(user_files_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, user_files_dir.parent)
                            zf.write(file_path, arcname)

            QMessageBox.information(self, "موفق", f"پشتیبان ذخیره شد:\n{dest}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در پشتیبان‌گیری:\n{str(e)}")

    def refresh(self):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")
        self._load_users()

