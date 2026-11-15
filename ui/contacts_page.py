from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QComboBox, QAbstractItemView, QCheckBox, QMenu, QListWidget,
    QListWidgetItem, QSizePolicy, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt5.QtGui import QColor, QFontMetrics
import uuid
from qfluentwidgets import (
    TitleLabel, PrimaryPushButton, PushButton, SearchLineEdit,
    ElevatedCardWidget, FluentIcon as FIF
)
from ui.styles import Styles, get_font, FONT_CSS, FS_BODY, FS_SMALL
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from models.models import ContactStatus
from services.repositories import contact_repo, group_repo, contact_group_repo, setting_repo


# مقدار ویژه برای گزینهٔ «بدون دسته» در نوار کناری (با شناسهٔ واقعی گروه تداخل ندارد)
NO_CATEGORY = -1

STATUS_TEXT = {"active": "فعال", "inactive": "غیرفعال", "blocked": "مسدود"}
STATUS_COLOR_ATTR = {"active": "success", "inactive": "fg_default", "blocked": "danger"}

# بزرگ‌نمایی جدول مخاطبین (مثل اکسل)
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 60, 200, 10
ZOOM_SETTING_KEY = "contacts_zoom"
BASE_ROW_HEIGHT = 46
BASE_ACTION_HEIGHT = 28
BASE_INDEX_WIDTH = 56
BASE_ACTIONS_WIDTH = 240


def list_qss(item_padding: str = "8px 10px") -> str:
    """QSS فهرست‌های انتخاب دسته (نوار کناری و چک‌لیست دیالوگ)"""
    c = theme_manager.current
    return f"""
        QListWidget {{
            background-color: {c.canvas_default};
            border: 1px solid {c.border_default};
            border-radius: 6px;
            outline: none;
            padding: 4px;
            font-family: {FONT_CSS};
            font-size: 12px;
            color: {c.fg_default};
        }}
        QListWidget::item {{
            padding: {item_padding};
            border-radius: 4px;
            color: {c.fg_default};
        }}
        QListWidget::item:hover {{
            background-color: {c.canvas_subtle};
        }}
        QListWidget::item:selected {{
            background-color: {c.selection_bg};
            color: {c.selection_fg};
        }}
    """


class CategoryDialog(QDialog):
    """ساخت/ویرایش دسته‌بندی دفترچه تلفن"""

    def __init__(self, parent=None, group_id=None):
        super().__init__(parent)
        self.group_id = group_id
        self.created_id = None
        self.group = group_repo.get_by_id(group_id) if group_id else None
        self.setWindowTitle("ویرایش دسته" if group_id else "دسته جدید")
        self.setMinimumWidth(460)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.group:
            self.name_input.setText(self.group.name or "")
            self.desc_input.setText(self.group.description or "")

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("ویرایش دسته" if self.group_id else "دسته جدید")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(15, True))
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("مثلاً: ادارات بخش، اداره برق، مخابرات...")
        self.name_input.setStyleSheet(Styles.line_edit())
        self.name_input.setFont(get_font(10))
        form.addRow(self._label("نام دسته:"), self.name_input)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("اختیاری")
        self.desc_input.setStyleSheet(Styles.line_edit())
        self.desc_input.setFont(get_font(10))
        form.addRow(self._label("توضیحات:"), self.desc_input)
        layout.addLayout(form)

        hint = QLabel("پس از ساخت دسته، می‌توانید مخاطبین و ادارات را به آن اضافه کنید.")
        hint.setStyleSheet(Styles.muted_label())
        hint.setFont(get_font(9))
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        save_btn = QPushButton("ذخیره")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _label(self, text):
        c = theme_manager.current
        lbl = QLabel(text)
        lbl.setFont(get_font(10, True))
        lbl.setStyleSheet(
            f"color: {c.fg_default}; font-family: {FONT_CSS}; min-width: 90px;"
        )
        return lbl

    def _save(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "نام الزامی", "نام دسته را وارد کنید")
            return
        # UNIQUE(name, parent_id) در SQLite برای ریشه‌ها کار نمی‌کند (NULL != NULL)
        try:
            duplicate = any(
                g.name.strip() == name and g.id != self.group_id
                for g in group_repo.get_tree()
            )
        except Exception:
            duplicate = False
        if duplicate:
            QMessageBox.warning(self, "تکراری", "دسته‌ای با همین نام از قبل وجود دارد")
            return
        description = self.desc_input.text().strip() or None
        try:
            if self.group_id:
                group_repo.update(self.group_id, name=name, description=description)
                self.created_id = self.group_id
            else:
                obj = group_repo.create(
                    uuid=str(uuid.uuid4()),
                    name=name,
                    description=description,
                    is_system=False,
                    sort_order=50,
                )
                self.created_id = obj.id if obj else None
            self.accept()
        except Exception as e:
            msg = str(e)
            if "UNIQUE" in msg.upper():
                msg = "دسته‌ای با همین نام از قبل وجود دارد"
            QMessageBox.critical(self, "خطا", msg)


class ContactDialog(QDialog):
    def __init__(self, parent=None, contact_id=None):
        super().__init__(parent)
        self.contact_id = contact_id
        self.contact = None
        if contact_id:
            self.contact = contact_repo.get_by_id(contact_id)
        self.setWindowTitle("ویرایش مخاطب" if contact_id else "مخاطب جدید")
        self.setMinimumSize(1040, 680)
        self.resize(1180, 740)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.contact:
            self._load_data()

    # ------------------------------------------------------------------ #
    #  سازنده‌های مشترک ویجت (هم‌سبک با صفحه جلسه)
    # ------------------------------------------------------------------ #
    def _dialog_stylesheet(self, c):
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
                font-family: {FONT_CSS};
            }}
            QLabel#fieldLabel {{
                color: {c.fg_muted};
                font-size: 11px;
                font-family: {FONT_CSS};
            }}
            QLabel#hint {{
                color: {c.fg_muted};
                font-size: 10px;
                font-family: {FONT_CSS};
            }}
        """

    def _field_label(self, text, required=False):
        lbl = QLabel(f"{text} *" if required else text)
        lbl.setObjectName("fieldLabel")
        lbl.setFont(get_font(10, True))
        return lbl

    def _hint(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        lbl.setFont(get_font(9))
        lbl.setWordWrap(True)
        return lbl

    def _line_edit(self, placeholder=""):
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFont(get_font(10))
        inp.setMinimumHeight(34)
        inp.setStyleSheet(Styles.line_edit())
        return inp

    def _combo(self, items=None):
        combo = QComboBox()
        combo.setFont(get_font(10))
        combo.setMinimumHeight(34)
        combo.setStyleSheet(Styles.combo_box())
        if items:
            combo.addItems(items)
        return combo

    def _text_edit(self, placeholder="", height=54):
        edit = QTextEdit()
        edit.setFont(get_font(10))
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(height)
        edit.setMaximumHeight(height + 14)
        edit.setStyleSheet(Styles.text_edit())
        return edit

    def _card(self, title_text):
        frame = QFrame()
        frame.setObjectName("card")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        title.setFont(get_font(11, True))
        outer.addWidget(title)
        return frame, outer

    @staticmethod
    def _grid(column_stretch=(1,)):
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for index, stretch in enumerate(column_stretch):
            grid.setColumnStretch(index, stretch)
        return grid

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(self._dialog_stylesheet(c))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("ویرایش مخاطب" if self.contact_id else "مخاطب جدید")
        heading.setStyleSheet(Styles.title_label())
        heading.setFont(get_font(16, True))
        layout.addWidget(heading)

        self.inputs = {}

        body = QGridLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(14)
        body.setVerticalSpacing(12)
        body.setColumnStretch(0, 30)
        body.setColumnStretch(1, 32)
        body.setColumnStretch(2, 38)
        body.setRowStretch(0, 1)
        layout.addLayout(body, 1)

        # ==================== کارت ۱: مشخصات فرد ====================
        card_person, box_person = self._card("مشخصات فرد")
        person = self._grid((1, 1))
        box_person.addLayout(person)

        person.addWidget(self._field_label("نام", required=True), 0, 0)
        person.addWidget(self._field_label("نام خانوادگی"), 0, 1)
        for col, (field, placeholder) in enumerate((
            ("first_name", "مثال: علی"),
            ("last_name", "مثال: محمدی"),
        )):
            inp = self._line_edit(placeholder)
            person.addWidget(inp, 1, col)
            self.inputs[field] = inp

        person.addWidget(self._field_label("کد ملی"), 2, 0, 1, 2)
        self.inputs["national_code"] = self._line_edit("کد ۱۰ رقمی")
        person.addWidget(self.inputs["national_code"], 3, 0, 1, 2)

        person.addWidget(self._field_label("سمت"), 4, 0, 1, 2)
        self.position = self._combo([
            "بخشدار", "دهیار", "دبیر", "کارمند", "مشاور",
            "عضو شورا", "کارشناس", "مدیر", "رئیس", "سایر"
        ])
        self.position.setEditable(True)
        person.addWidget(self.position, 5, 0, 1, 2)
        box_person.addStretch()
        body.addWidget(card_person, 0, 0)

        # ==================== کارت ۲: راه‌های تماس ====================
        card_contact, box_contact = self._card("راه‌های تماس")
        contact = self._grid((1, 1))
        box_contact.addLayout(contact)

        contact.addWidget(self._field_label("موبایل"), 0, 0)
        contact.addWidget(self._field_label("تلفن ثابت"), 0, 1)
        for col, (field, placeholder) in enumerate((
            ("mobile", "09xxxxxxxxx"),
            ("phone", "0xx-xxxxxxxx"),
        )):
            inp = self._line_edit(placeholder)
            contact.addWidget(inp, 1, col)
            self.inputs[field] = inp

        contact.addWidget(self._field_label("تلفن داخلی"), 2, 0)
        contact.addWidget(self._field_label("فکس"), 2, 1)
        for col, (field, placeholder) in enumerate((
            ("extension", "مثلاً ۱۲۳"),
            ("fax", "0xx-xxxxxxxx"),
        )):
            inp = self._line_edit(placeholder)
            contact.addWidget(inp, 3, col)
            self.inputs[field] = inp

        box_contact.addWidget(self._hint(
            "برای ذخیره، وارد کردن حداقل یکی از موارد موبایل، تلفن ثابت یا فکس الزامی است."
        ))
        box_contact.addStretch()
        body.addWidget(card_contact, 0, 1)

        # ==================== کارت ۳: دسته‌بندی ====================
        card_cat, box_cat = self._card("دسته‌بندی")
        self.groups_list = QListWidget()
        self.groups_list.setStyleSheet(list_qss("4px 8px"))
        self.groups_list.setFont(get_font(10))
        self.groups_list.setMinimumHeight(132)
        self.groups_list.setMaximumHeight(165)
        self.groups_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        box_cat.addWidget(self.groups_list, 1)

        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)
        new_cat_btn = QPushButton("دسته جدید…")
        new_cat_btn.setStyleSheet(Styles.table_action_button("primary"))
        new_cat_btn.setFixedHeight(30)
        new_cat_btn.clicked.connect(self._add_category)
        cat_row.addWidget(new_cat_btn)
        cat_row.addStretch()
        box_cat.addLayout(cat_row)
        box_cat.addWidget(self._hint("هر مخاطب می‌تواند در چند دسته باشد."))
        body.addWidget(card_cat, 0, 2)

        # ==================== کارت ۴: نشانی و توضیحات ====================
        card_addr, box_addr = self._card("نشانی، سازمان و توضیحات")
        addr = self._grid((1, 1, 1, 1))
        box_addr.addLayout(addr)

        top_fields = [
            ("سازمان", "organization", "نام سازمان / اداره"),
            ("استان", "province", ""),
            ("شهرستان", "county", ""),
            ("بخش", "district", ""),
        ]
        for col, (label_text, field, placeholder) in enumerate(top_fields):
            addr.addWidget(self._field_label(label_text), 0, col)
            inp = self._line_edit(placeholder)
            addr.addWidget(inp, 1, col)
            self.inputs[field] = inp

        second_fields = [
            ("دهستان", "rural_district", ""),
            ("روستا", "village", ""),
            ("کد پستی", "postal_code", ""),
        ]
        for col, (label_text, field, placeholder) in enumerate(second_fields):
            addr.addWidget(self._field_label(label_text), 2, col)
            inp = self._line_edit(placeholder)
            addr.addWidget(inp, 3, col)
            self.inputs[field] = inp

        addr.addWidget(self._field_label("وضعیت"), 2, 3)
        self.status = self._combo(["فعال", "غیرفعال", "مسدود"])
        addr.addWidget(self.status, 3, 3)

        addr.addWidget(self._field_label("آدرس"), 4, 0, 1, 2)
        addr.addWidget(self._field_label("یادداشت"), 4, 2, 1, 2)
        self.address = self._text_edit("نشانی کامل پستی")
        addr.addWidget(self.address, 5, 0, 1, 2)
        self.notes = self._text_edit("توضیحات دلخواه")
        addr.addWidget(self.notes, 5, 2, 1, 2)

        body.addWidget(card_addr, 1, 0, 1, 3)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        save_btn = QPushButton("ذخیره")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.setMinimumHeight(38)
        save_btn.setMinimumWidth(130)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setMinimumWidth(110)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._reload_groups()

    # ------------------------------------------------------------------ #
    #  دسته‌بندی‌ها
    # ------------------------------------------------------------------ #
    def _checked_group_ids(self):
        ids = []
        for i in range(self.groups_list.count()):
            item = self.groups_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                gid = item.data(Qt.ItemDataRole.UserRole)
                if gid:
                    ids.append(int(gid))
        return ids

    def _reload_groups(self, keep_checked=True, check_new=None):
        checked = set(self._checked_group_ids()) if keep_checked else set()
        if check_new:
            checked.add(int(check_new))
        self.groups_list.blockSignals(True)
        self.groups_list.clear()
        try:
            rows = group_repo.get_with_counts()
        except Exception:
            rows = []
        for row in rows:
            g = row["group"]
            item = QListWidgetItem(f"{g.name}  ({row['contact_count']})")
            item.setData(Qt.ItemDataRole.UserRole, g.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if g.id in checked else Qt.CheckState.Unchecked
            )
            self.groups_list.addItem(item)
        self.groups_list.blockSignals(False)

    def _add_category(self):
        dlg = CategoryDialog(self)
        if dlg.exec() and dlg.created_id:
            self._reload_groups(check_new=dlg.created_id)

    def _sync_groups(self, contact_id):
        try:
            current = {g.id for g in contact_group_repo.get_contact_groups(contact_id)}
        except Exception:
            current = set()
        wanted = set(self._checked_group_ids())
        for gid in wanted - current:
            try:
                contact_group_repo.add_contact_to_group(contact_id, gid)
            except Exception:
                pass
        for gid in current - wanted:
            try:
                contact_group_repo.remove_contact_from_group(contact_id, gid)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  داده
    # ------------------------------------------------------------------ #
    def _load_data(self):
        c = self.contact
        self.inputs["first_name"].setText(c.first_name or "")
        self.inputs["last_name"].setText(c.last_name or "")
        self.inputs["mobile"].setText(c.mobile or "")
        self.inputs["phone"].setText(c.phone or "")
        self.inputs["extension"].setText(getattr(c, "extension", None) or "")
        self.inputs["fax"].setText(getattr(c, "fax", None) or "")
        self.inputs["national_code"].setText(c.national_code or "")
        self.position.setCurrentText(c.position or "")
        self.inputs["organization"].setText(c.organization or "")
        self.inputs["province"].setText(c.province or "")
        self.inputs["county"].setText(c.county or "")
        self.inputs["district"].setText(c.district or "")
        self.inputs["rural_district"].setText(c.rural_district or "")
        self.inputs["village"].setText(c.village or "")
        self.inputs["postal_code"].setText(c.postal_code or "")
        self.address.setText(c.address or "")
        status_map = {"active": "فعال", "inactive": "غیرفعال", "blocked": "مسدود"}
        self.status.setCurrentText(status_map.get(c.status.value, "فعال"))
        self.notes.setText(c.notes or "")
        try:
            mine = {g.id for g in contact_group_repo.get_contact_groups(c.id)}
        except Exception:
            mine = set()
        for i in range(self.groups_list.count()):
            item = self.groups_list.item(i)
            gid = item.data(Qt.ItemDataRole.UserRole)
            item.setCheckState(
                Qt.CheckState.Checked if gid in mine else Qt.CheckState.Unchecked
            )

    def _save(self):
        first_name = self.inputs["first_name"].text().strip()
        last_name = self.inputs["last_name"].text().strip()
        mobile = self.inputs["mobile"].text().strip() or None
        phone = self.inputs["phone"].text().strip() or None
        extension = self.inputs["extension"].text().strip() or None
        fax = self.inputs["fax"].text().strip() or None
        national_code = self.inputs["national_code"].text().strip() or None

        if not first_name and not last_name:
            QMessageBox.warning(self, "نام الزامی", "نام یا نام خانوادگی را وارد کنید")
            return
        if not any([mobile, phone, fax]):
            QMessageBox.warning(
                self, "شماره الزامی",
                "حداقل یکی از موارد موبایل، تلفن ثابت یا فکس را وارد کنید"
            )
            return
        if mobile:
            try:
                dup = contact_repo.get_by_mobile(mobile)
                if dup and dup.id != self.contact_id:
                    QMessageBox.warning(
                        self, "تکراری",
                        f"این شماره موبایل برای «{dup.full_name}» ثبت شده است"
                    )
                    return
            except Exception:
                pass

        data = {
            "first_name": first_name,
            "last_name": last_name,
            "mobile": mobile,
            "phone": phone,
            "extension": extension,
            "fax": fax,
            "national_code": national_code,
            "position": self.position.currentText().strip() or None,
            "organization": self.inputs["organization"].text().strip() or None,
            "province": self.inputs["province"].text().strip() or None,
            "county": self.inputs["county"].text().strip() or None,
            "district": self.inputs["district"].text().strip() or None,
            "rural_district": self.inputs["rural_district"].text().strip() or None,
            "village": self.inputs["village"].text().strip() or None,
            "postal_code": self.inputs["postal_code"].text().strip() or None,
            "address": self.address.toPlainText().strip() or None,
            "status": {
                "فعال": ContactStatus.ACTIVE,
                "غیرفعال": ContactStatus.INACTIVE,
                "مسدود": ContactStatus.BLOCKED
            }.get(self.status.currentText(), ContactStatus.ACTIVE),
            "notes": self.notes.toPlainText().strip() or None,
        }
        try:
            if self.contact_id:
                contact_repo.update(self.contact_id, **data)
                contact_id = self.contact_id
            else:
                data["uuid"] = str(uuid.uuid4())
                obj = contact_repo.create(**data)
                contact_id = obj.id if obj else None
            if contact_id:
                self._sync_groups(contact_id)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))


class ContactsPage(QWidget):
    """دفترچه تلفن: مخاطبین و ادارات، دسته‌بندی‌شده"""

    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self._zoom = self._read_zoom()
        try:
            group_repo.ensure_default_categories()
        except Exception:
            pass
        self._setup_ui()
        self._apply_zoom()
        self._load_groups()
        self._apply_filters()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = TitleLabel("دفترچه تلفن")
        title_box.addWidget(title)
        subtitle = QLabel("مخاطبین، ادارات و سازمان‌ها — دسته‌بندی‌شده")
        subtitle.setStyleSheet(Styles.subtitle_label())
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        # ---- بزرگ‌نمایی جدول (مثل اکسل: + / − و Ctrl+اسکرول) ----
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(4)
        zoom_caption = QLabel("بزرگ‌نمایی:")
        zoom_caption.setStyleSheet(Styles.subtitle_label())
        zoom_row.addWidget(zoom_caption)

        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setToolTip("کوچک‌نمایی (Ctrl + اسکرول ماوس به پایین)")
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setToolTip("بزرگ‌نمایی (Ctrl + اسکرول ماوس به بالا)")
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setToolTip("اندازهٔ عادی — برای بازنشانی کلیک کنید")
        for btn in (self.zoom_out_btn, self.zoom_in_btn, self.zoom_label):
            btn.setFixedHeight(32)
            btn.setStyleSheet(Styles.table_action_button("neutral"))
        self.zoom_out_btn.setFixedWidth(32)
        self.zoom_in_btn.setFixedWidth(32)
        self.zoom_label.setFixedWidth(64)
        self.zoom_out_btn.clicked.connect(lambda: self._set_zoom(self._zoom - ZOOM_STEP))
        self.zoom_in_btn.clicked.connect(lambda: self._set_zoom(self._zoom + ZOOM_STEP))
        self.zoom_label.clicked.connect(lambda: self._set_zoom(100))
        zoom_row.addWidget(self.zoom_out_btn)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(self.zoom_in_btn)
        header.addLayout(zoom_row)

        import_btn = PushButton("ورودی اکسل")
        try:
            import_btn.setIcon(FIF.DOWNLOAD.icon())
        except Exception:
            pass
        import_btn.clicked.connect(self._import_excel)
        header.addWidget(import_btn)

        add_btn = PrimaryPushButton("مخاطب جدید")
        try:
            add_btn.setIcon(FIF.ADD.icon())
        except Exception:
            pass
        add_btn.clicked.connect(self._add_contact)
        header.addWidget(add_btn)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        # ---- کارت دسته‌بندی‌ها (در چیدمان راست‌به‌چپ اولین ستون سمت راست است)
        cat_card = QFrame()
        cat_card.setStyleSheet(Styles.card())
        cat_card.setFixedWidth(250)
        cat_layout = QVBoxLayout(cat_card)
        cat_layout.setContentsMargins(12, 12, 12, 12)
        cat_layout.setSpacing(10)

        cat_title = QLabel("دسته‌بندی‌ها")
        cat_title.setStyleSheet(Styles.section_title_label())
        cat_title.setFont(get_font(12, True))
        cat_layout.addWidget(cat_title)

        self.category_list = QListWidget()
        self.category_list.setStyleSheet(list_qss())
        self.category_list.setFont(get_font(10))
        self.category_list.currentRowChanged.connect(self._on_category_changed)
        cat_layout.addWidget(self.category_list, 1)

        cat_btns = QHBoxLayout()
        cat_btns.setSpacing(6)
        add_cat_btn = QPushButton("دسته جدید")
        add_cat_btn.setStyleSheet(Styles.table_action_button("primary"))
        add_cat_btn.setFixedHeight(30)
        add_cat_btn.clicked.connect(self._add_category)
        edit_cat_btn = QPushButton("ویرایش")
        edit_cat_btn.setStyleSheet(Styles.table_action_button("neutral"))
        edit_cat_btn.setFixedHeight(30)
        edit_cat_btn.clicked.connect(self._edit_category)
        del_cat_btn = QPushButton("حذف")
        del_cat_btn.setStyleSheet(Styles.table_action_button("danger"))
        del_cat_btn.setFixedHeight(30)
        del_cat_btn.clicked.connect(self._delete_category)
        cat_btns.addWidget(add_cat_btn)
        cat_btns.addWidget(edit_cat_btn)
        cat_btns.addWidget(del_cat_btn)
        cat_layout.addLayout(cat_btns)
        body.addWidget(cat_card)

        # ---- ستون اصلی
        main_col = QVBoxLayout()
        main_col.setSpacing(12)

        search_frame = ElevatedCardWidget()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(16, 12, 16, 12)
        search_layout.setSpacing(12)

        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText(
            "جستجو در همهٔ فیلدها: نام، نام پدر، عنوان، سازمان، موبایل، تلفن، "
            "فکس، داخلی، کد ملی، آدرس، یادداشت، دسته‌بندی، وضعیت..."
        )
        # Debounce: _apply_filters re-queries the DB and rebuilds the whole
        # table (up to 5000 rows) on every single keystroke.
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._schedule_filters)
        search_layout.addWidget(self.search_input)

        self.filter_combo = QComboBox()
        self.filter_combo.setStyleSheet(Styles.combo_box())
        self.filter_combo.setFont(get_font(10))
        self.filter_combo.addItems(["همه", "فعال", "غیرفعال", "مسدود"])
        self.filter_combo.currentTextChanged.connect(self._apply_filters)
        self.filter_combo.setFixedWidth(130)
        search_layout.addWidget(self.filter_combo)
        main_col.addWidget(search_frame)

        table_frame = QFrame()
        table_frame.setStyleSheet(Styles.card())
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setFont(get_font(10))
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "ردیف", "نام و عنوان", "سازمان", "دسته‌بندی",
            "تلفن ثابت", "فکس", "موبایل", "داخلی", "وضعیت", "عملیات"
        ])
        self._configure_columns()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._edit_contact)
        # Ctrl + اسکرول روی جدول (و خود صفحه) بزرگ‌نمایی می‌کند؛ مثل اکسل
        self.table.installEventFilter(self)
        self.installEventFilter(self)
        table_layout.addWidget(self.table)
        main_col.addWidget(table_frame, 1)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(Styles.subtitle_label())
        main_col.addWidget(self.count_label)

        body.addLayout(main_col, 1)
        layout.addLayout(body, 1)

    # ------------------------------------------------------------------ #
    #  بزرگ‌نمایی جدول (مثل اکسل)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clamp_zoom(value):
        try:
            value = int(round(int(value) / ZOOM_STEP) * ZOOM_STEP)
        except (TypeError, ValueError):
            return 100
        return max(ZOOM_MIN, min(ZOOM_MAX, value))

    def _read_zoom(self):
        try:
            return self._clamp_zoom(setting_repo.get_setting(ZOOM_SETTING_KEY, 100))
        except Exception:
            return 100

    @property
    def _scale(self):
        return self._zoom / 100.0

    def _set_zoom(self, value):
        value = self._clamp_zoom(value)
        if value == self._zoom:
            return
        self._zoom = value
        self._apply_zoom()
        try:
            setting_repo.set_setting(ZOOM_SETTING_KEY, value)
        except Exception:
            pass

    def _apply_zoom(self):
        """مقیاس‌بندی فونت، پدینگ، ارتفاع ردیف و عرض ستون‌ها

        font-size و padding داخل QSS هستند، پس بدون بازنویسی استایل، setFont
        هیچ اثری ندارد.
        """
        s = self._scale
        head_fs = max(7, round(FS_SMALL * s))
        pad_v = max(3, round(8 * s))
        pad_h = max(5, round(12 * s))
        padding = f"{pad_v}px {pad_h}px"
        # استایل جدول و دکمه‌های «عملیات» با یک فراخوانی روی جدول ست می‌شود؛
        # setStyleSheet تک‌تک دکمه‌ها برای جدول‌های پرردیف چند ثانیه طول می‌کشد.
        self.table.setStyleSheet(
            Styles.table_widget(
                font_size=max(7, round(FS_BODY * s)),
                header_font_size=head_fs,
                item_padding=padding,
                header_padding=padding,
            )
            + Styles.table_action_buttons(font_size=max(7, round(FS_SMALL * s)))
        )
        table_font = get_font(10)
        table_font.setPointSizeF(max(6.0, round(10 * s, 1)))
        self.table.setFont(table_font)

        row_h = max(24, round(BASE_ROW_HEIGHT * s))
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        btn_h = max(18, round(BASE_ACTION_HEIGHT * s))
        margins = (
            max(1, round(4 * s)), max(1, round(2 * s)),
            max(1, round(4 * s)), max(1, round(2 * s)),
        )
        spacing = max(1, round(4 * s))
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, row_h)
            holder = self.table.cellWidget(row, 9)
            if holder is None:
                continue
            layout = holder.layout()
            if layout is not None:
                layout.setContentsMargins(*margins)
                layout.setSpacing(spacing)
            for btn in holder.findChildren(QPushButton):
                if btn.height() != btn_h:
                    btn.setFixedHeight(btn_h)

        self._configure_columns()
        self.zoom_label.setText(f"{self._zoom}%")
        self.zoom_out_btn.setEnabled(self._zoom > ZOOM_MIN)
        self.zoom_in_btn.setEnabled(self._zoom < ZOOM_MAX)
        self.table.viewport().update()

    def _configure_columns(self):
        """چیدمان ستون‌ها؛ عرض هیچ ستونی از عنوانش کمتر نمی‌شود

        اگر حداقل عرض ستون از متن عنوان کوچک باشد، QHeaderView متن را با «…»
        کوتاه می‌کند و عنوان درست دیده نمی‌شود.
        """
        s = self._scale
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setTextElideMode(Qt.TextElideMode.ElideNone)

        head_fs = max(7, round(FS_SMALL * s))
        measure_font = get_font(FS_SMALL, True)
        measure_font.setPixelSize(head_fs)
        fm = QFontMetrics(measure_font)
        pad_h = max(5, round(12 * s)) * 2 + 8

        needs = []
        for col in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(col)
            label = item.text() if item is not None else ""
            needs.append(fm.horizontalAdvance(label) + pad_h if label else 0)

        header.setMinimumSectionSize(max(48, max(needs)) if needs else 48)
        header.setMinimumHeight(fm.height() + 2 * max(3, round(8 * s)) + 6)

        # فقط «نام و عنوان» کشسان می‌ماند؛ بقیه به اندازهٔ محتوا جا می‌گیرند
        # تا نام سازمان‌ها و دسته‌های بلند بریده نشود.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, max(needs[0], round(BASE_INDEX_WIDTH * s)))
        for col in (2, 3, 4, 5, 6, 7, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(9, max(needs[9], round(BASE_ACTIONS_WIDTH * s)))

        header.resizeSections()

    def eventFilter(self, obj, event):
        # Ctrl + اسکرول ماوس = بزرگ‌نمایی (اسکرول معمولی همچنان اسکرول می‌کند)
        if event.type() == QEvent.Type.Wheel and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            delta = event.angleDelta().y()
            if delta:
                self._set_zoom(self._zoom + (ZOOM_STEP if delta > 0 else -ZOOM_STEP))
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    #  دسته‌بندی‌ها
    # ------------------------------------------------------------------ #
    def selected_group_id(self):
        item = self.category_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _load_groups(self, select_id="__keep__"):
        if select_id == "__keep__":
            select_id = self.selected_group_id()
        total = 0
        try:
            total = contact_repo.count()
        except Exception:
            pass
        no_cat = 0
        try:
            no_cat = len(contact_repo.get_without_group(limit=5000))
        except Exception:
            pass

        self.category_list.blockSignals(True)
        self.category_list.clear()

        all_item = QListWidgetItem(f"همه مخاطبین  ({total})")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.category_list.addItem(all_item)

        try:
            rows = group_repo.get_with_counts()
        except Exception:
            rows = []
        for row in rows:
            g = row["group"]
            item = QListWidgetItem(f"{g.name}  ({row['contact_count']})")
            item.setData(Qt.ItemDataRole.UserRole, g.id)
            item.setToolTip(g.description or "")
            self.category_list.addItem(item)

        if no_cat:
            nc_item = QListWidgetItem(f"بدون دسته  ({no_cat})")
            nc_item.setData(Qt.ItemDataRole.UserRole, NO_CATEGORY)
            self.category_list.addItem(nc_item)

        target = 0
        for i in range(self.category_list.count()):
            if self.category_list.item(i).data(Qt.ItemDataRole.UserRole) == select_id:
                target = i
                break
        self.category_list.setCurrentRow(target)
        self.category_list.blockSignals(False)

    def _on_category_changed(self, row):
        self._apply_filters()

    def _add_category(self):
        dlg = CategoryDialog(self)
        if dlg.exec() and dlg.created_id:
            self._load_groups(select_id=dlg.created_id)
            self._apply_filters()

    def _edit_category(self):
        gid = self.selected_group_id()
        if gid in (None, NO_CATEGORY):
            QMessageBox.information(self, "انتخاب دسته", "یک دسته را انتخاب کنید")
            return
        dlg = CategoryDialog(self, group_id=gid)
        if dlg.exec():
            self._load_groups(select_id=gid)
            self._apply_filters()

    def _delete_category(self):
        gid = self.selected_group_id()
        if gid in (None, NO_CATEGORY):
            QMessageBox.information(self, "انتخاب دسته", "یک دسته را انتخاب کنید")
            return
        g = group_repo.get_by_id(gid)
        if not g:
            return
        c = theme_manager.current
        _ = c
        if not confirm_delete(self, noun="دسته", name=g.name):
            return
        try:
            group_repo.delete(gid)
            self._load_groups(select_id=None)
            self._apply_filters()
        except Exception as e:
            QMessageBox.critical(self, "خطا در حذف", str(e))

    # ------------------------------------------------------------------ #
    #  نمایش
    # ------------------------------------------------------------------ #
    def _schedule_filters(self, *_):
        self._filter_timer.start()

    def _apply_filters(self, *_):
        keyword = self.search_input.text().strip()
        self._load_contacts(self._fetch_contacts(keyword))

    # سازگاری با فراخوانی‌های قبلی
    def _on_search(self, text):
        self._apply_filters()

    def _on_filter(self, text):
        self._apply_filters()

    def _fetch_contacts(self, keyword):
        gid = self.selected_group_id()
        try:
            if keyword:
                results = contact_repo.search(keyword, limit=2000)
                return results or []
            if gid == NO_CATEGORY:
                return contact_repo.get_without_group(limit=5000) or []
            if gid is None:
                return contact_repo.get_all(limit=5000) or []
            return contact_repo.get_by_group(gid, limit=5000) or []
        except Exception:
            return []

    def _clear_table(self):
        """جدا کردن و نابودی ویجت‌های عملیات قبل از پر کردن مجدد جدول.

        setRowCount فقط deleteLater صدا می‌زند و ویجت تا پردازش رویداد حذف
        به‌عنوان فرزند viewport باقی می‌ماند؛ نتیجه‌اش دکمه‌های تکراری شناور
        روی ستون‌های میانی بود. اینجا صریحاً از والد جدا می‌شوند.
        """
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 9)
            if widget is not None:
                self.table.removeCellWidget(row, 9)
                widget.setParent(None)
                widget.deleteLater()
        self.table.clearContents()
        self.table.setRowCount(0)

    def _load_contacts(self, contacts):
        c = theme_manager.current
        contacts = contacts or []
        gid = self.selected_group_id()

        # فیلتر دسته روی نتایج جستجو هم اعمال شود
        if gid is not None and self.search_input.text().strip():
            try:
                gmap = contact_group_repo.get_group_map([co.id for co in contacts])
            except Exception:
                gmap = {}
            if gid == NO_CATEGORY:
                contacts = [co for co in contacts if not gmap.get(co.id)]
            else:
                contacts = [co for co in contacts if gid in [g for g, _ in gmap.get(co.id, [])]]

        # فیلتر وضعیت
        status_label = self.filter_combo.currentText()
        wanted = {v: k for k, v in STATUS_TEXT.items()}.get(status_label)
        if wanted:
            contacts = [
                co for co in contacts
                if (co.status.value if co.status else "") == wanted
            ]

        try:
            gmap = contact_group_repo.get_group_map([co.id for co in contacts])
        except Exception:
            gmap = {}

        self._clear_table()
        self.table.setRowCount(len(contacts))
        s = self._scale
        row_h = max(24, round(BASE_ROW_HEIGHT * s))
        btn_h = max(18, round(BASE_ACTION_HEIGHT * s))
        margins = (
            max(1, round(4 * s)), max(1, round(2 * s)),
            max(1, round(4 * s)), max(1, round(2 * s)),
        )
        spacing = max(1, round(4 * s))
        for row, co in enumerate(contacts):
            id_item = QTableWidgetItem(str(row + 1))
            id_item.setData(Qt.ItemDataRole.UserRole, co.id)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, id_item)

            name = co.full_name or "-"
            name_item = QTableWidgetItem(name)
            tip_parts = [p for p in [co.position, co.organization, co.notes] if p]
            if tip_parts:
                name_item.setToolTip("\n".join(tip_parts))
            self.table.setItem(row, 1, name_item)

            self.table.setItem(row, 2, QTableWidgetItem(co.organization or "-"))

            names = [name for _, name in gmap.get(co.id, [])]
            cat_item = QTableWidgetItem("، ".join(names) if names else "بدون دسته")
            if names:
                cat_item.setToolTip("\n".join(names))
            self.table.setItem(row, 3, cat_item)

            self.table.setItem(row, 4, QTableWidgetItem(co.phone or "-"))
            self.table.setItem(row, 5, QTableWidgetItem(getattr(co, "fax", None) or "-"))
            self.table.setItem(row, 6, QTableWidgetItem(co.mobile or "-"))
            self.table.setItem(row, 7, QTableWidgetItem(getattr(co, "extension", None) or "-"))

            status_value = co.status.value if co.status else ""
            status_item = QTableWidgetItem(STATUS_TEXT.get(status_value, "-"))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(
                QColor(getattr(c, STATUS_COLOR_ATTR.get(status_value, "fg_default")))
            )
            self.table.setItem(row, 8, status_item)

            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(*margins)
            actions_layout.setSpacing(spacing)
            for text, variant, callback in [
                ("ویرایش", "neutral", lambda checked=False, cid=co.id: self._edit_contact_by_id(cid)),
                ("پروفایل", "subtle", lambda checked=False, cid=co.id: self._view_profile(cid)),
                ("حذف", "danger", lambda checked=False, cid=co.id: self._delete_contact(cid)),
            ]:
                btn = QPushButton(text)
                btn.setFixedHeight(btn_h)
                # استایل از QSS جدول (با انتخاب‌گر variant) می‌آید تا هنگام
                # بزرگ‌نمایی فقط یک setStyleSheet روی جدول انجام شود.
                btn.setProperty("variant", variant)
                btn.clicked.connect(callback)
                actions_layout.addWidget(btn)
            self.table.setCellWidget(row, 9, actions_widget)
            self.table.setRowHeight(row, row_h)

        if not contacts:
            self.count_label.setText("موردی یافت نشد — با «مخاطب جدید» یا «ورودی اکسل» اضافه کنید")
        else:
            self.count_label.setText(f"تعداد: {len(contacts)} مورد")
        self._configure_columns()

    def _refresh_preserving_state(self):
        gid = self.selected_group_id()
        self._load_groups(select_id=gid)
        self._apply_filters()

    # ------------------------------------------------------------------ #
    #  عملیات روی مخاطب
    # ------------------------------------------------------------------ #
    def _add_contact(self):
        if ContactDialog(self).exec():
            self._refresh_preserving_state()

    def _edit_contact(self, index):
        self._edit_row(index.row())

    def _edit_row(self, row):
        item = self.table.item(row, 0)
        cid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if cid:
            self._edit_contact_by_id(cid)

    def _edit_contact_by_id(self, cid):
        if ContactDialog(self, contact_id=cid).exec():
            self._refresh_preserving_state()

    def _view_profile(self, cid):
        from ui.profile_dialog import ProfileDialog
        ProfileDialog(self, cid).exec()

    def _delete_contact(self, cid):
        co = contact_repo.get_by_id(cid)
        if not co:
            return
        if not confirm_delete(self, noun="مخاطب", name=co.full_name):
            return
        try:
            contact_repo.delete(cid)
            self._refresh_preserving_state()
        except Exception as e:
            QMessageBox.critical(self, "خطا در حذف", str(e))

    def _remove_from_current_category(self, cid):
        gid = self.selected_group_id()
        if gid in (None, NO_CATEGORY):
            return
        try:
            contact_group_repo.remove_contact_from_group(cid, gid)
            self._refresh_preserving_state()
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    # ------------------------------------------------------------------ #
    #  منوی زمینه
    # ------------------------------------------------------------------ #
    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        id_item = self.table.item(row, 0)
        cid = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if not cid:
            return
        co = contact_repo.get_by_id(cid)
        if not co:
            return

        menu = QMenu(self)
        menu.setFont(get_font(10))
        actions = [
            ("ویرایش", lambda: self._edit_contact_by_id(cid)),
            ("پروفایل", lambda: self._view_profile(cid)),
            ("مدیریت دسته‌ها", lambda: self._manage_groups(cid)),
            ("ارسال پیامک", lambda: self._send_sms_to(cid)),
        ]
        gid = self.selected_group_id()
        if gid not in (None, NO_CATEGORY):
            actions.append(("حذف از این دسته", lambda: self._remove_from_current_category(cid)))
        actions.append(("حذف", lambda: self._delete_contact(cid)))

        for text, cb in actions:
            action = menu.addAction(text)
            action.triggered.connect(cb)
        menu.exec(self.table.mapToGlobal(pos))

    def _manage_groups(self, cid):
        from ui.group_dialog import ManageContactGroupsDialog
        ManageContactGroupsDialog(self, cid).exec()
        self._refresh_preserving_state()

    def _send_sms_to(self, cid):
        main_window = self.window()
        if hasattr(main_window, "navigate_to"):
            main_window.navigate_to("sms")

    def _import_excel(self):
        from ui.excel_import_dialog import ExcelImportDialog
        if ExcelImportDialog(self).exec():
            self._refresh_preserving_state()

    def refresh(self):
        self._load_groups()
        self._apply_filters()
