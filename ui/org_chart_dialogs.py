"""دیالوگ‌های ویرایش پست سازمانی و اطلاعات کامل پرسنل."""

import jdatetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QCheckBox, QMessageBox,
    QScrollArea, QWidget, QFrame,
)

from services.repositories import org_post_repo, employee_repo
from services.sms_service import normalize_mobile, is_valid_mobile
from ui.styles import Styles, get_font
from ui.theme import theme_manager

DEFAULT_CATEGORIES = [
    "فرمانداری", "حوزهٔ فرماندار", "معاونت سیاسی،امنیتی و اجتماعی",
    "معاون هماهنگی و امور عمرانی", "معاون برنامه ریزی و توسعه",
    "حراست", "بخشداری", "ستاد",
]
GENDER_OPTIONS = ["", "مرد", "زن"]
MARITAL_OPTIONS = ["", "مجرد", "متأهل"]
STATUS_OPTIONS = ["شاغل", "مرخصی", "انتقالی", "بازنشسته", "پایان خدمت"]
TYPE_OPTIONS = ["رسمی", "پیمانی", "قراردادی", "شرکتی", "سایر"]
EDUCATION_OPTIONS = ["زیر دیپلم", "دیپلم", "فوق دیپلم", "کارشناسی", "کارشناسی ارشد", "دکتری"]


def normalize_jalali(text: str):
    """(تاریخ نرمال‌شده، پیام خطا)؛ تاریخ خالی مجاز است."""
    text = (text or "").strip()
    if not text:
        return None, None
    parts = text.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None, "قالب تاریخ صحیح نیست. مثال: 1404/07/29"
    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    try:
        jdatetime.date(y, m, d)
    except (ValueError, TypeError):
        return None, "تاریخ نامعتبر است."
    return f"{y:04d}/{m:02d}/{d:02d}", None


def ordered_post_choices(posts):
    """[(post, label)] به ترتیب درخت چارت."""
    by_parent = {}
    for p in posts:
        by_parent.setdefault(p.parent_id, []).append(p)
    for lst in by_parent.values():
        lst.sort(key=lambda p: (p.sort_order, p.id))

    out = []
    seen = set()

    def walk(parent_id, depth):
        for p in by_parent.get(parent_id, []):
            if p.id in seen:
                continue
            seen.add(p.id)
            out.append((p, ("— " * depth) + p.title))
            walk(p.id, depth + 1)

    walk(None, 0)
    for p in posts:
        if p.id not in seen:
            out.append((p, p.title))
    return out


def descendant_ids(posts, root_id):
    by_parent = {}
    for p in posts:
        by_parent.setdefault(p.parent_id, []).append(p)
    out = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child in by_parent.get(current, []):
            if child.id not in out:
                out.add(child.id)
                stack.append(child.id)
    return out


def _dialog_qss():
    c = theme_manager.current
    return f"""
        QDialog {{ background-color: {c.canvas_overlay}; }}
        QLineEdit, QComboBox, QTextEdit, QSpinBox {{
            background-color: {c.input_bg};
            border: 1px solid {c.input_border};
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 12px;
            color: {c.fg_default};
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {{
            border: 2px solid {c.input_border_hover};
        }}
        QComboBox QAbstractItemView {{
            background-color: {c.canvas_overlay};
            color: {c.fg_default};
            border: 1px solid {c.border_default};
            selection-background-color: {c.accent_blue};
            selection-color: white;
        }}
    """


def _field_label(text):
    c = theme_manager.current
    label = QLabel(text)
    label.setStyleSheet(f"color: {c.fg_default}; font-weight: bold; font-size: 11px;")
    return label


def _hint(text):
    c = theme_manager.current
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {c.fg_muted}; font-size: 10px;")
    return label


class OrgPostDialog(QDialog):
    def __init__(self, parent=None, post_id=None, posts=None, default_parent_id=None):
        super().__init__(parent)
        self.post_id = post_id
        self.saved_id = None
        self.posts = list(posts or org_post_repo.get_ordered())
        self.post = org_post_repo.get_by_id(post_id) if post_id else None
        if post_id and self.post is None:
            raise ValueError("post not found")
        self.setWindowTitle("ویرایش پست سازمانی" if post_id else "پست سازمانی جدید")
        self.setMinimumWidth(560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFont(get_font(10))
        self.setStyleSheet(_dialog_qss())
        self._setup_ui(default_parent_id)
        if self.post:
            self._load()

    def _setup_ui(self, default_parent_id):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        title = QLabel("ویرایش پست سازمانی" if self.post_id else "پست سازمانی جدید")
        title.setStyleSheet(Styles.title_label())
        layout.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("مثال: کارشناس امور عمرانی")
        form.addWidget(_field_label("عنوان پست"), 0, 0)
        form.addWidget(self.title_input, 1, 0, 1, 2)

        self.parent_combo = QComboBox()
        self.parent_combo.addItem("— سطح اول (بدون والد) —", None)
        excluded = descendant_ids(self.posts, self.post_id) | {self.post_id} if self.post_id else set()
        for post, label in ordered_post_choices(self.posts):
            if post.id in excluded:
                continue
            self.parent_combo.addItem(label, post.id)
        form.addWidget(_field_label("پست بالادستی"), 2, 0)
        form.addWidget(self.parent_combo, 3, 0, 1, 2)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        categories = list(DEFAULT_CATEGORIES)
        for p in self.posts:
            if p.category and p.category not in categories:
                categories.append(p.category)
        self.category_combo.addItems(categories)
        form.addWidget(_field_label("حوزه / دسته"), 4, 0)
        form.addWidget(self.category_combo, 5, 0, 1, 2)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("اختیاری")
        form.addWidget(_field_label("کد پست سازمانی"), 6, 0)
        form.addWidget(self.code_input, 7, 0)

        self.approved_spin = QSpinBox()
        self.approved_spin.setRange(0, 999)
        self.approved_spin.setValue(1)
        form.addWidget(_field_label("تعداد پست مصوب"), 6, 1)
        form.addWidget(self.approved_spin, 7, 1)

        self.sort_spin = QSpinBox()
        self.sort_spin.setRange(0, 100000)
        form.addWidget(_field_label("ترتیب نمایش"), 8, 0)
        form.addWidget(self.sort_spin, 9, 0)

        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)

        layout.addWidget(_field_label("یادداشت"))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)
        self.notes.setPlaceholderText("اختیاری")
        layout.addWidget(self.notes)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("انصراف")
        cancel.setStyleSheet(Styles.secondary_button())
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("ذخیره")
        save.setStyleSheet(Styles.primary_button())
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        if default_parent_id:
            idx = self.parent_combo.findData(default_parent_id)
            if idx >= 0:
                self.parent_combo.setCurrentIndex(idx)
        self._apply_default_sort()

    def _apply_default_sort(self):
        if self.post_id:
            return
        parent_id = self.parent_combo.currentData()
        siblings = [p for p in self.posts if p.parent_id == parent_id]
        self.sort_spin.setValue(max((p.sort_order for p in siblings), default=0) + 10)
        parent = next((p for p in self.posts if p.id == parent_id), None)
        if parent and not self.category_combo.currentText().strip():
            self.category_combo.setCurrentText(parent.category or "")

    def _load(self):
        p = self.post
        self.title_input.setText(p.title or "")
        idx = self.parent_combo.findData(p.parent_id)
        if idx >= 0:
            self.parent_combo.setCurrentIndex(idx)
        self.category_combo.setCurrentText(p.category or "")
        self.code_input.setText(p.code or "")
        self.approved_spin.setValue(p.approved_count or 0)
        self.sort_spin.setValue(p.sort_order or 0)
        self.notes.setPlainText(p.notes or "")

    def _save(self):
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "خطا", "عنوان پست سازمانی الزامی است")
            return
        data = {
            "title": title,
            "parent_id": self.parent_combo.currentData(),
            "category": self.category_combo.currentText().strip() or None,
            "code": self.code_input.text().strip() or None,
            "approved_count": self.approved_spin.value(),
            "sort_order": self.sort_spin.value(),
            "notes": self.notes.toPlainText().strip() or None,
        }
        try:
            if self.post_id:
                org_post_repo.update(self.post_id, **data)
                self.saved_id = self.post_id
            else:
                obj = org_post_repo.create(**data)
                self.saved_id = obj.id
        except Exception as e:
            QMessageBox.critical(self, "خطا در ذخیره", str(e))
            return
        self.accept()


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee_id=None, posts=None, default_post_id=None):
        super().__init__(parent)
        self.employee_id = employee_id
        self.saved_id = None
        self.posts = list(posts or org_post_repo.get_ordered())
        self.employee = employee_repo.get_by_id(employee_id) if employee_id else None
        if employee_id and self.employee is None:
            raise ValueError("employee not found")
        self.setWindowTitle("ویرایش پرسنل" if employee_id else "پرسنل جدید")
        self.resize(820, 780)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFont(get_font(10))
        self.setStyleSheet(_dialog_qss())
        self._setup_ui(default_post_id)
        if self.employee:
            self._load()

    def _setup_ui(self, default_post_id):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 14)
        outer.setSpacing(10)

        title = QLabel("ویرایش اطلاعات پرسنل" if self.employee_id else "ثبت پرسنل جدید")
        title.setStyleSheet(Styles.title_label())
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)

        def add_pair(row, col, label_text, widget):
            base = col * 2
            grid.addWidget(_field_label(label_text), row, base)
            grid.addWidget(widget, row, base + 1)

        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        add_pair(0, 0, "نام *", self.first_name)
        add_pair(0, 1, "نام خانوادگی *", self.last_name)

        self.personnel_code = QLineEdit()
        self.personnel_code.setMaxLength(30)
        self.national_code = QLineEdit()
        self.national_code.setMaxLength(10)
        add_pair(1, 0, "کد پرسنلی", self.personnel_code)
        add_pair(1, 1, "کد ملی", self.national_code)

        self.father_name = QLineEdit()
        self.gender = QComboBox()
        self.gender.addItems(GENDER_OPTIONS)
        add_pair(2, 0, "نام پدر", self.father_name)
        add_pair(2, 1, "جنسیت", self.gender)

        self.birth_date = QLineEdit()
        self.birth_date.setPlaceholderText("1404/07/29")
        self.birth_place = QLineEdit()
        add_pair(3, 0, "تاریخ تولد (شمسی)", self.birth_date)
        add_pair(3, 1, "محل تولد", self.birth_place)

        self.marital_status = QComboBox()
        self.marital_status.addItems(MARITAL_OPTIONS)
        self.employment_status = QComboBox()
        self.employment_status.addItems(STATUS_OPTIONS)
        add_pair(4, 0, "وضعیت تأهل", self.marital_status)
        add_pair(4, 1, "وضعیت خدمت", self.employment_status)

        self.education_level = QComboBox()
        self.education_level.setEditable(True)
        self.education_level.addItems(EDUCATION_OPTIONS)
        self.field_of_study = QLineEdit()
        add_pair(5, 0, "مدرک تحصیلی", self.education_level)
        add_pair(5, 1, "رشتهٔ تحصیلی", self.field_of_study)

        self.hire_date = QLineEdit()
        self.hire_date.setPlaceholderText("1404/07/29")
        self.employment_type = QComboBox()
        self.employment_type.setEditable(True)
        self.employment_type.addItems(TYPE_OPTIONS)
        add_pair(6, 0, "تاریخ استخدام (شمسی)", self.hire_date)
        add_pair(6, 1, "نوع استخدام", self.employment_type)

        self.mobile = QLineEdit()
        self.mobile.setMaxLength(11)
        self.phone = QLineEdit()
        add_pair(7, 0, "موبایل", self.mobile)
        add_pair(7, 1, "تلفن ثابت", self.phone)

        self.email = QLineEdit()
        self.address = QLineEdit()
        add_pair(8, 0, "ایمیل", self.email)
        add_pair(8, 1, "آدرس", self.address)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)

        layout.addWidget(_field_label("پست سازمانی (طبق چارت)"))
        self.post_combo = QComboBox()
        self.post_combo.addItem("— بدون پست سازمانی —", None)
        for post, label in ordered_post_choices(self.posts):
            self.post_combo.addItem(label, post.id)
        layout.addWidget(self.post_combo)

        layout.addWidget(_field_label("محل خدمت فعلی (ممکن است با پست سازمانی متفاوت باشد)"))
        self.workplace = QComboBox()
        self.workplace.setEditable(True)
        suggestions = set()
        for p in self.posts:
            if p.category:
                suggestions.add(p.category)
        try:
            for emp in employee_repo.get_all_with_post():
                if emp.workplace:
                    suggestions.add(emp.workplace)
        except Exception:
            pass
        suggestions.add("فرمانداری")
        self.workplace.addItems(sorted(suggestions))
        self.workplace.setCurrentText("")
        layout.addWidget(self.workplace)
        layout.addWidget(_hint(
            "پست سازمانی جایگاه ثابت فرد در چارت است؛ محل خدمت فعلی جایی است که "
            "اکنون کار می‌کند و می‌تواند متفاوت باشد."))

        bottom_row = QHBoxLayout()
        self.active_check = QCheckBox("شاغل / فعال")
        self.active_check.setChecked(True)
        bottom_row.addWidget(self.active_check)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        layout.addWidget(_field_label("یادداشت"))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(70)
        layout.addWidget(self.notes)
        layout.addStretch()

        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("انصراف")
        cancel.setStyleSheet(Styles.secondary_button())
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("ذخیره")
        save.setStyleSheet(Styles.primary_button())
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        outer.addLayout(buttons)

        if default_post_id:
            idx = self.post_combo.findData(default_post_id)
            if idx >= 0:
                self.post_combo.setCurrentIndex(idx)

    def _load(self):
        e = self.employee
        self.first_name.setText(e.first_name or "")
        self.last_name.setText(e.last_name or "")
        self.personnel_code.setText(e.personnel_code or "")
        self.national_code.setText(e.national_code or "")
        self.father_name.setText(e.father_name or "")
        self.gender.setCurrentText(e.gender or "")
        self.birth_date.setText(e.birth_date or "")
        self.birth_place.setText(e.birth_place or "")
        self.marital_status.setCurrentText(e.marital_status or "")
        self.employment_status.setCurrentText(e.employment_status or "شاغل")
        self.education_level.setCurrentText(e.education_level or "")
        self.field_of_study.setText(e.field_of_study or "")
        self.hire_date.setText(e.hire_date or "")
        self.employment_type.setCurrentText(e.employment_type or "")
        self.mobile.setText(e.mobile or "")
        self.phone.setText(e.phone or "")
        self.email.setText(e.email or "")
        self.address.setText(e.address or "")
        idx = self.post_combo.findData(e.post_id)
        if idx >= 0:
            self.post_combo.setCurrentIndex(idx)
        self.workplace.setCurrentText(e.workplace or "")
        self.active_check.setChecked(bool(e.is_active))
        self.notes.setPlainText(e.notes or "")

    def _save(self):
        first = self.first_name.text().strip()
        last = self.last_name.text().strip()
        if not first or not last:
            QMessageBox.warning(self, "خطا", "نام و نام خانوادگی الزامی است")
            return

        national_code = self.national_code.text().strip() or None
        if national_code and (not national_code.isdigit() or len(national_code) != 10):
            QMessageBox.warning(self, "خطا", "کد ملی باید ۱۰ رقم باشد")
            return

        birth_date, error = normalize_jalali(self.birth_date.text())
        if error:
            QMessageBox.warning(self, "خطا", f"تاریخ تولد: {error}")
            return
        hire_date, error = normalize_jalali(self.hire_date.text())
        if error:
            QMessageBox.warning(self, "خطا", f"تاریخ استخدام: {error}")
            return

        mobile = self.mobile.text().strip() or None
        if mobile:
            mobile = normalize_mobile(mobile)
            if not is_valid_mobile(mobile):
                QMessageBox.warning(self, "خطا", "شماره موبایل معتبر نیست")
                return

        data = {
            "first_name": first,
            "last_name": last,
            "personnel_code": self.personnel_code.text().strip() or None,
            "national_code": national_code,
            "father_name": self.father_name.text().strip() or None,
            "gender": self.gender.currentText().strip() or None,
            "birth_date": birth_date,
            "birth_place": self.birth_place.text().strip() or None,
            "marital_status": self.marital_status.currentText().strip() or None,
            "education_level": self.education_level.currentText().strip() or None,
            "field_of_study": self.field_of_study.text().strip() or None,
            "hire_date": hire_date,
            "employment_type": self.employment_type.currentText().strip() or None,
            "employment_status": self.employment_status.currentText().strip() or None,
            "post_id": self.post_combo.currentData(),
            "workplace": self.workplace.currentText().strip() or None,
            "mobile": mobile,
            "phone": self.phone.text().strip() or None,
            "email": self.email.text().strip() or None,
            "address": self.address.text().strip() or None,
            "notes": self.notes.toPlainText().strip() or None,
            "is_active": self.active_check.isChecked(),
        }
        try:
            if self.employee_id:
                employee_repo.update(self.employee_id, **data)
                self.saved_id = self.employee_id
            else:
                obj = employee_repo.create(**data)
                self.saved_id = obj.id
        except Exception as e:
            message = str(e)
            if "UNIQUE" in message.upper():
                message = "کد پرسنلی یا کد ملی واردشده قبلاً ثبت شده است."
            QMessageBox.critical(self, "خطا در ذخیره", message)
            return
        self.accept()
