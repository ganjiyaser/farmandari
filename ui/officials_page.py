from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QDialog, QCheckBox, QFrame, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import official_repo
from models.models import OfficialPosition, OFFICIAL_POSITION_LABELS

POSITION_ORDER = [
    OfficialPosition.GOVERNOR,
    OfficialPosition.DEPUTY_GOVERNOR,
    OfficialPosition.DISTRICT_GOVERNOR,
]

COLOR_PALETTE = [
    ("آبی", "#0969da"),
    ("سبز", "#1a7f37"),
    ("نارنجی", "#bc4c00"),
    ("بنفش", "#8250df"),
    ("قرمز", "#cf222e"),
    ("فیروزه‌ای", "#1b7c83"),
    ("قهوه‌ای", "#9a6700"),
]


def position_label(position) -> str:
    if isinstance(position, OfficialPosition):
        return OFFICIAL_POSITION_LABELS.get(position, "-")
    for p, label in OFFICIAL_POSITION_LABELS.items():
        if p.value == position:
            return label
    return "-"


class OfficialDialog(QDialog):
    official_saved = pyqtSignal()

    def __init__(self, parent=None, official_id=None):
        super().__init__(parent)
        self.official_id = official_id
        self.official = official_repo.get_by_id(official_id) if official_id else None
        self.setWindowTitle("ویرایش مسئول" if official_id else "مسئول جدید")
        self.setMinimumWidth(480)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.official:
            self._load()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 12px;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {c.fg_default};
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border: 2px solid {c.input_border_hover};
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.canvas_overlay};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                selection-background-color: {c.accent_blue};
                selection-color: white;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("ویرایش مسئول" if self.official_id else "مسئول جدید")
        title.setStyleSheet(Styles.title_label())
        layout.addWidget(title)

        def add_field(label_text, widget):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
            layout.addWidget(lbl)
            layout.addWidget(widget)

        self.first_name = QLineEdit()
        self.first_name.setPlaceholderText("نام")
        add_field("نام", self.first_name)

        self.last_name = QLineEdit()
        self.last_name.setPlaceholderText("نام خانوادگی")
        add_field("نام خانوادگی", self.last_name)

        row = QHBoxLayout()
        col1 = QVBoxLayout()
        lbl_pos = QLabel("سمت")
        lbl_pos.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        col1.addWidget(lbl_pos)
        self.position_combo = QComboBox()
        for pos in POSITION_ORDER:
            self.position_combo.addItem(OFFICIAL_POSITION_LABELS[pos], pos.value)
        col1.addWidget(self.position_combo)
        row.addLayout(col1, 1)

        col2 = QVBoxLayout()
        lbl_org = QLabel("سازمان / حوزه (اختیاری)")
        lbl_org.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        col2.addWidget(lbl_org)
        self.organization = QLineEdit()
        self.organization.setPlaceholderText("مثال: بخشداری مرکزی")
        col2.addWidget(self.organization)
        row.addLayout(col2, 1)
        layout.addLayout(row)

        self.mobile = QLineEdit()
        self.mobile.setPlaceholderText("09xxxxxxxxx")
        add_field("موبایل (برای ارسال پیامک)", self.mobile)

        self.phone = QLineEdit()
        self.phone.setPlaceholderText("تلفن ثابت")
        add_field("تلفن (اختیاری)", self.phone)

        row2 = QHBoxLayout()
        col3 = QVBoxLayout()
        lbl_color = QLabel("رنگ برنامه در تقویم")
        lbl_color.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        col3.addWidget(lbl_color)
        self.color_combo = QComboBox()
        for name, hex_code in COLOR_PALETTE:
            self.color_combo.addItem(name, hex_code)
        col3.addWidget(self.color_combo)
        row2.addLayout(col3, 1)

        col4 = QVBoxLayout()
        self.active_check = QCheckBox("فعال")
        self.active_check.setChecked(True)
        col4.addWidget(self.active_check)
        col4.addStretch()
        row2.addLayout(col4, 1)
        layout.addLayout(row2)

        self.notes = QTextEdit()
        self.notes.setPlaceholderText("یادداشت (اختیاری)")
        self.notes.setMaximumHeight(70)
        add_field("یادداشت", self.notes)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("انصراف")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("ذخیره")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _load(self):
        d = self.official
        self.first_name.setText(d.first_name or "")
        self.last_name.setText(d.last_name or "")
        idx = self.position_combo.findData(d.position.value if d.position else None)
        if idx >= 0:
            self.position_combo.setCurrentIndex(idx)
        self.organization.setText(d.organization or "")
        self.mobile.setText(d.mobile or "")
        self.phone.setText(d.phone or "")
        if d.color:
            for i in range(self.color_combo.count()):
                if self.color_combo.itemData(i) == d.color:
                    self.color_combo.setCurrentIndex(i)
                    break
        self.active_check.setChecked(d.is_active)
        self.notes.setPlainText(d.notes or "")

    def _save(self):
        first = self.first_name.text().strip()
        last = self.last_name.text().strip()
        if not first or not last:
            QMessageBox.warning(self, "خطا", "نام و نام خانوادگی الزامی است")
            return
        mobile = self.mobile.text().strip() or None
        if mobile:
            from services.sms_service import normalize_mobile, is_valid_mobile
            mobile = normalize_mobile(mobile)
            if not is_valid_mobile(mobile):
                QMessageBox.warning(self, "خطا", "شماره موبایل معتبر نیست")
                return

        data = {
            "first_name": first,
            "last_name": last,
            "position": self.position_combo.currentData(),
            "organization": self.organization.text().strip() or None,
            "mobile": mobile,
            "phone": self.phone.text().strip() or None,
            "color": self.color_combo.currentData(),
            "is_active": self.active_check.isChecked(),
            "notes": self.notes.toPlainText().strip() or None,
        }
        try:
            if self.official_id:
                official_repo.update(self.official_id, **data)
            else:
                official_repo.create(**data)
        except Exception as e:
            QMessageBox.critical(self, "خطا در ذخیره", str(e))
            return
        self.official_saved.emit()
        self.accept()


class OfficialRow(QFrame):
    edited = pyqtSignal()
    deleted = pyqtSignal()

    def __init__(self, official, parent=None):
        super().__init__(parent)
        self.official = official
        self.setFixedHeight(58)
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        color = self.official.color or "#0969da"
        self.setStyleSheet(f"""
            OfficialRow {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-right: 4px solid {color};
                border-radius: 8px;
            }}
            OfficialRow:hover {{
                background-color: {c.canvas_subtle};
                border: 1px solid {c.primary};
                border-right: 4px solid {color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(self.official.display_name)
        name.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {c.fg_default};")
        info.addWidget(name)
        sub_parts = [position_label(self.official.position)]
        if self.official.mobile:
            sub_parts.append(self.official.mobile)
        sub = QLabel(" — ".join(sub_parts))
        sub.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
        info.addWidget(sub)
        layout.addLayout(info, 1)

        if not self.official.is_active:
            badge = QLabel("غیرفعال")
            badge.setStyleSheet(
                f"color: {c.accent_red}; font-size: 11px; font-weight: bold;")
            layout.addWidget(badge)

        edit_btn = QPushButton("ویرایش")
        edit_btn.setStyleSheet(Styles.secondary_button())
        edit_btn.clicked.connect(self._edit)
        layout.addWidget(edit_btn)

        del_btn = QPushButton("حذف")
        del_btn.setStyleSheet(Styles.secondary_button())
        del_btn.clicked.connect(self._delete)
        layout.addWidget(del_btn)

    def _edit(self):
        dlg = OfficialDialog(self.window(), self.official.id)
        dlg.official_saved.connect(self.edited.emit)
        dlg.exec()

    def _delete(self):
        if confirm_delete(self, noun="مسئول", name=self.official.display_name,
                          extra="جلساتی که این مسئول صاحب آن‌هاست بدون مسئول می‌شوند."):
            try:
                official_repo.delete(self.official.id)
                self.deleted.emit()
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))


class OfficialsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("مسئولین فرمانداری")
        title.setStyleSheet(Styles.title_label())
        header.addWidget(title)
        header.addStretch()
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(Styles.subtitle_label())
        header.addWidget(self.stats_label)
        add_btn = QPushButton("+ مسئول جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_official)
        header.addWidget(add_btn)
        layout.addLayout(header)

        hint = QLabel("فرماندار، معاونین و بخشداران اینجا ثبت می‌شوند تا در جلسات به‌عنوان «صاحب برنامه» یا «دعوت‌شده» انتخاب شوند و تداخل برنامه‌ها کنترل شود.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px;")
        layout.addWidget(hint)

        from PyQt6.QtWidgets import QScrollArea
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.groups_host = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_host)
        self.groups_layout.setSpacing(14)
        self.scroll.setWidget(self.groups_host)
        layout.addWidget(self.scroll, 1)

    def _add_official(self):
        dlg = OfficialDialog(self)
        dlg.official_saved.connect(self.refresh)
        dlg.exec()

    def refresh(self):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")

        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        officials = official_repo.get_all(limit=500)
        active_count = sum(1 for o in officials if o.is_active)
        self.stats_label.setText(f"{active_count} فعال از {len(officials)}")

        if not officials:
            empty = QLabel("هنوز مسئولی ثبت نشده است — با دکمهٔ «مسئول جدید» شروع کنید")
            empty.setStyleSheet(f"color: {c.fg_muted}; font-size: 13px; padding: 24px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.groups_layout.addWidget(empty)
            self.groups_layout.addStretch()
            return

        for pos in POSITION_ORDER:
            group = [o for o in officials if o.position == pos]
            if not group:
                continue
            lbl = QLabel(
                f"{OFFICIAL_POSITION_LABELS[pos]} ({len(group)} نفر)")
            lbl.setStyleSheet(Styles.section_title_label())
            self.groups_layout.addWidget(lbl)
            for official in group:
                row = OfficialRow(official)
                row.edited.connect(self.refresh)
                row.deleted.connect(self.refresh)
                self.groups_layout.addWidget(row)

        self.groups_layout.addStretch()
