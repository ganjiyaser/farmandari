import os
import re
import uuid
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QMessageBox, QComboBox, QFileDialog, QProgressBar,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import openpyxl
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm
from models.models import ContactStatus
from services.repositories import contact_repo


COLUMN_MAPPING = {
    "نام": "first_name",
    "نام اول": "first_name",
    "first_name": "first_name",
    "firstname": "first_name",
    "name": "first_name",
    "نام خانوادگی": "last_name",
    "نام خانوادگي": "last_name",
    "فامیلی": "last_name",
    "فاميلي": "last_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "surname": "last_name",
    "family": "last_name",
    "موبایل": "mobile",
    "موبايل": "mobile",
    "شماره موبایل": "mobile",
    "شماره‌ی موبایل": "mobile",
    "تلفن همراه": "mobile",
    "همراه": "mobile",
    "mobile": "mobile",
    "cell": "mobile",
    "cellphone": "mobile",
    "تلفن": "phone",
    "تلفن ثابت": "phone",
    "شماره تلفن": "phone",
    "phone": "phone",
    "landline": "phone",
    "tel": "phone",
    "تلفن داخلی": "extension",
    "تلفن داخلي": "extension",
    "داخلی": "extension",
    "internal": "extension",
    "extension": "extension",
    "سمت": "position",
    "شغل": "position",
    "عنوان شغلی": "position",
    "عنوان شغلي": "position",
    "position": "position",
    "title": "position",
    "job": "position",
    "سازمان": "organization",
    "اداره": "organization",
    "سازمان مربوطه": "organization",
    "organization": "organization",
    "org": "organization",
    "department": "organization",
    "استان": "province",
    "province": "province",
    "شهرستان": "county",
    "county": "county",
    "بخش": "district",
    "district": "district",
    "دهستان": "rural_district",
    "rural_district": "rural_district",
    "روستا": "village",
    "village": "village",
    "کد ملی": "national_code",
    "کد ملّی": "national_code",
    "کدملی": "national_code",
    "کدملّی": "national_code",
    "شماره ملی": "national_code",
    "national_code": "national_code",
    "national_id": "national_code",
    "کد پستی": "postal_code",
    "کدپستی": "postal_code",
    "کد پستي": "postal_code",
    "postal_code": "postal_code",
    "zip": "postal_code",
    "zipcode": "postal_code",
    "آدرس": "address",
    "address": "address",
    "یادداشت": "notes",
    "توضیحات": "notes",
    "توضيحات": "notes",
    "notes": "notes",
    "comment": "notes",
}

DB_FIELD_LABELS = {
    "": "-- بدون نقش --",
    "first_name": "نام",
    "last_name": "نام خانوادگی",
    "mobile": "موبایل",
    "phone": "تلفن ثابت",
    "extension": "تلفن داخلی",
    "position": "سمت",
    "organization": "سازمان",
    "province": "استان",
    "county": "شهرستان",
    "district": "بخش",
    "rural_district": "دهستان",
    "village": "روستا",
    "national_code": "کد ملی",
    "postal_code": "کد پستی",
    "address": "آدرس",
    "notes": "یادداشت",
}

DB_FIELD_OPTIONS = [
    "", "first_name", "last_name", "mobile", "phone", "extension",
    "position", "organization", "province", "county", "district",
    "rural_district", "village", "national_code", "postal_code",
    "address", "notes",
]

# فیلدهای عددی که فقط باید رقم نگه دارند
_DIGIT_FIELDS = {"mobile", "phone", "extension", "national_code", "postal_code"}
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def _to_english_digits(s: str) -> str:
    for i, d in enumerate("0123456789"):
        s = s.replace(_PERSIAN_DIGITS[i], d).replace(_ARABIC_DIGITS[i], d)
    return s


def _normalize_arabic(s: str) -> str:
    return s.replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u0629", "\u0647")


def _cell_to_text(value, db_field: str = None) -> str:
    """تبدیل مقدار خام اکسل به متن تمیز:
    - 9123456787.0 (اعشاری اکسل) → 09123456787
    - ۰۹۱۲... (ارقام فارسی/عربی) → 0912...
    - کدملی کوتاه با صفر ابتدا تکمیل می‌شود
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y/%m/%d")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = _to_english_digits(_normalize_arabic(str(value))).strip()
    if s.startswith("'"):  # اکسل گاهی برای حفظ صفر ابتدا ' می‌گذارد
        s = s[1:]
    if db_field in _DIGIT_FIELDS:
        digits = re.sub(r"[^0-9]", "", s)
        if db_field == "mobile":
            # 9123456787 → 09123456787 ، 989123456787 → 09123456787
            if len(digits) == 10 and digits.startswith("9"):
                digits = "0" + digits
            elif len(digits) == 12 and digits.startswith("98"):
                digits = "0" + digits[2:]
            elif len(digits) == 11 and not digits.startswith("0"):
                digits = "0" + digits
            return digits
        if db_field == "national_code":
            return digits.zfill(10) if 0 < len(digits) <= 10 else digits
        if db_field == "postal_code":
            return digits.zfill(10) if 0 < len(digits) <= 10 else digits
        if db_field == "phone":
            if len(digits) == 10 and not digits.startswith("0"):
                digits = "0" + digits
            return digits
        return digits
    return s


def _norm_header(h) -> str:
    s = _to_english_digits(_normalize_arabic(str(h))).strip().lower()
    return re.sub(r"[\s_\-.:]+", " ", s).strip()


# lookup عادی + نسخه با آندرلاین/بدون فاصله تا «First_Name» و «National Code»
# و «کدملی» هم تشخیص داده شوند
_HEADER_LOOKUP = {}
for _k, _v in COLUMN_MAPPING.items():
    _nk = _norm_header(_k)
    _HEADER_LOOKUP[_nk] = _v
    _HEADER_LOOKUP[_nk.replace(" ", "_")] = _v
    _HEADER_LOOKUP[_nk.replace(" ", "")] = _v


class ImportWorker(QThread):
    # NOT named `finished`: that shadows QThread.finished, so anything waiting
    # on the thread's own completion signal would never fire.
    import_done = pyqtSignal(int, int, int, int)  # imported, duplicates, no_mobile, errors
    progress = pyqtSignal(int)

    def __init__(self, rows):
        super().__init__()
        self.rows = rows  # list of dicts already mapped to db field names

    def run(self):
        imported = 0
        duplicates = 0
        no_mobile = 0
        errors = 0
        total = len(self.rows)
        seen_mobiles = set()
        for i, data in enumerate(self.rows):
            try:
                first_name = (data.get("first_name") or "").strip()
                last_name = (data.get("last_name") or "").strip()
                mobile = (data.get("mobile") or "").strip()

                if not mobile:
                    # ستون mobile در مدل NOT NULL و UNIQUE است؛ ردیف بدون
                    # موبایل قابل درج نیست وگرنه همه ردیف‌های بعدی خطا می‌خورند
                    no_mobile += 1
                    self.progress.emit(int((i + 1) / total * 100) if total else 100)
                    continue
                if mobile in seen_mobiles:
                    duplicates += 1
                    self.progress.emit(int((i + 1) / total * 100) if total else 100)
                    continue

                record = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "mobile": mobile,
                    "uuid": str(uuid.uuid4()),
                    "status": ContactStatus.ACTIVE,
                }
                for field in (
                    "phone", "extension", "position", "organization",
                    "province", "county", "district", "rural_district",
                    "village", "national_code", "postal_code", "address", "notes",
                ):
                    val = (data.get(field) or "").strip()
                    if val and val != "None":
                        record[field] = val

                if contact_repo.get_by_mobile(mobile):
                    duplicates += 1
                    seen_mobiles.add(mobile)
                    self.progress.emit(int((i + 1) / total * 100) if total else 100)
                    continue

                contact_repo.create(**record)
                seen_mobiles.add(mobile)
                imported += 1
            except Exception:
                errors += 1
            self.progress.emit(int((i + 1) / total * 100) if total else 100)
        self.import_done.emit(imported, duplicates, no_mobile, errors)


class ExcelImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ورودی اکسل - دفترچه تلفن")
        self.setMinimumSize(1000, 700)
        self.setFont(get_font(10))
        self.column_map = {}   # excel_header -> db_field
        self.rows_data = []
        self.headers = []
        self._importing = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        c = theme_manager.current
        title = QLabel("ورودی اکسل - دفترچه تلفن")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(16, True))
        layout.addWidget(title)

        # Step 1 – file selection
        step1 = QFrame()
        step1.setStyleSheet(Styles.card())
        s1_layout = QHBoxLayout(step1)
        s1_layout.setContentsMargins(15, 10, 15, 10)

        file_btn = QPushButton("انتخاب فایل اکسل")
        file_btn.setStyleSheet(Styles.primary_button())
        file_btn.clicked.connect(self._select_file)
        s1_layout.addWidget(file_btn)

        self.file_label = QLabel("فایلی انتخاب نشده")
        self.file_label.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px;"
        )
        s1_layout.addWidget(self.file_label)
        s1_layout.addStretch()
        layout.addWidget(step1)

        # Step 2 – column mapping
        step2 = QFrame()
        step2.setStyleSheet(Styles.card())
        s2_layout = QVBoxLayout(step2)
        s2_layout.setContentsMargins(12, 8, 12, 8)
        s2_layout.setSpacing(6)
        s2_title = QLabel("تشخیص خودکار ستون‌ها (هر ستون را می‌توانید تغییر دهید)")
        s2_title.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; font-size: 12px;"
        )
        s2_layout.addWidget(s2_title)

        self.map_table = QTableWidget()
        self.map_table.setStyleSheet(Styles.table_widget())
        self.map_table.setFont(get_font(10))
        self.map_table.setColumnCount(3)
        self.map_table.setHorizontalHeaderLabels(["ستون اکسل", "فیلد سیستم", "نمونه مقدار"])
        map_header = self.map_table.horizontalHeader()
        # کامبو از sizeHint ردیف تأثیر نمی‌گذارد؛ ResizeToContents فقط آیتم‌ها را می‌سنجد
        map_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        map_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.map_table.setColumnWidth(1, 210)
        map_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.map_table.verticalHeader().setVisible(False)
        # ارتفاع ردیف باید کامبو (حداقل ۳۸px) را کامل جا دهد؛ وگرنه بریده می‌شود
        self.map_table.verticalHeader().setDefaultSectionSize(44)
        self.map_table.setMinimumHeight(120)
        self.map_table.setMaximumHeight(190)
        self.map_table.setAlternatingRowColors(True)
        self.map_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        s2_layout.addWidget(self.map_table)
        layout.addWidget(step2)

        # Step 3 – preview
        step3 = QFrame()
        step3.setStyleSheet(Styles.card())
        s3_layout = QVBoxLayout(step3)
        s3_layout.setContentsMargins(12, 8, 12, 8)
        s3_layout.setSpacing(6)
        s3_title = QLabel("پیش‌نمایش اطلاعات")
        s3_title.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; font-size: 12px;"
        )
        s3_layout.addWidget(s3_title)

        self.preview_table = QTableWidget()
        self.preview_table.setStyleSheet(Styles.table_widget())
        self.preview_table.setFont(get_font(10))
        # حالت اندازه ستون‌ها هنگام پر شدن در _update_preview اعمال می‌شود
        self.preview_table.verticalHeader().setDefaultSectionSize(40)
        self.preview_table.setMinimumHeight(180)
        self.preview_table.setMaximumHeight(240)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        s3_layout.addWidget(self.preview_table)
        layout.addWidget(step3)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {c.border_default}; border-radius: 8px;
                text-align: center; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; height: 25px;
            }}
            QProgressBar::chunk {{ background-color: {c.success}; border-radius: 8px; }}
        """)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px;"
        )
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        import_btn = QPushButton("ورود اطلاعات")
        import_btn.setStyleSheet(Styles.success_button())
        import_btn.clicked.connect(self._import_data)
        btn_layout.addWidget(import_btn)
        close_btn = QPushButton("بستن")
        close_btn.setStyleSheet(Styles.danger_button())
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.import_btn = import_btn
        self.close_btn = close_btn

    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل اکسل", "",
            "فایل اکسل (*.xlsx);;همه فایل‌ها (*)"
        )
        if not file_path:
            return

        try:
            # try/finally around the workbook: the old code only called
            # wb.close() on the success path, leaking the file handle on the
            # early "empty file" return and on every parse error.
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            try:
                ws = wb.active

                all_rows = list(ws.iter_rows(values_only=True))
                if len(all_rows) < 1:
                    QMessageBox.warning(self, "خطا", "فایل خالی است")
                    return

                self.headers = [
                    str(h).strip() if h is not None else f"ستون_{i + 1}"
                    for i, h in enumerate(all_rows[0])
                ]
                self.rows_data = []
                for row in all_rows[1:]:
                    if all(v is None or str(v).strip() == "" for v in row):
                        continue  # ردیف کاملاً خالی
                    row_dict = {}
                    for i, val in enumerate(row):
                        if i < len(self.headers):
                            row_dict[self.headers[i]] = val
                    self.rows_data.append(row_dict)
            finally:
                wb.close()

            self.file_label.setText(f"{os.path.basename(file_path)} | {len(self.rows_data)} ردیف")
            self._detect_columns()
            self._update_preview()
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در خواندن فایل:\n{str(e)}")

    def _detect_columns(self):
        self.column_map = {}
        self.map_table.setRowCount(len(self.headers))

        for row, header in enumerate(self.headers):
            detected = _HEADER_LOOKUP.get(_norm_header(header), "")

            excel_item = QTableWidgetItem(header)
            excel_item.setFlags(excel_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.map_table.setItem(row, 0, excel_item)

            combo = QComboBox()
            combo.setStyleSheet(Styles.combo_box())
            combo.setFont(get_font(10))
            for opt in DB_FIELD_OPTIONS:
                combo.addItem(DB_FIELD_LABELS.get(opt, opt), opt)

            if detected and detected in DB_FIELD_OPTIONS:
                combo.setCurrentIndex(DB_FIELD_OPTIONS.index(detected))
                self.column_map[header] = detected

            self.map_table.setCellWidget(row, 1, combo)

            sample_val = ""
            for rd in self.rows_data[:10]:
                v = rd.get(header)
                txt = _cell_to_text(v)
                if txt:
                    sample_val = txt[:40]
                    break
            sample_item = QTableWidgetItem(sample_val)
            sample_item.setFlags(sample_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.map_table.setItem(row, 2, sample_item)

            combo.currentIndexChanged.connect(
                lambda _idx, r=row, h=header: self._on_map_change(r, h)
            )

    def _on_map_change(self, row, header):
        combo = self.map_table.cellWidget(row, 1)
        if not combo:
            return
        val = combo.currentData()
        if val:
            self.column_map[header] = val
        elif header in self.column_map:
            del self.column_map[header]
        self._update_preview()

    def _update_preview(self):
        display_fields = [
            ("first_name", "نام"),
            ("last_name", "نام خانوادگی"),
            ("mobile", "موبایل"),
            ("position", "سمت"),
            ("organization", "سازمان"),
            ("county", "شهرستان"),
        ]

        # Reverse map: db_field -> excel_header
        field_to_header = {v: k for k, v in self.column_map.items()}

        self.preview_table.setColumnCount(len(display_fields))
        self.preview_table.setHorizontalHeaderLabels([label for _, label in display_fields])
        # حتماً بعد از setColumnCount؛ وگرنه سکشن‌های تازه‌ساخته حالت پیش‌فرض می‌گیرند
        preview_header = self.preview_table.horizontalHeader()
        preview_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(display_fields)):
            preview_header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        preview_count = min(10, len(self.rows_data))
        self.preview_table.setRowCount(preview_count)

        for row_idx in range(preview_count):
            row_data = self.rows_data[row_idx]
            for col_idx, (db_field, _) in enumerate(display_fields):
                excel_header = field_to_header.get(db_field)
                val = ""
                if excel_header is not None:
                    raw = row_data.get(excel_header)
                    val = _cell_to_text(raw, db_field)
                self.preview_table.setItem(row_idx, col_idx, QTableWidgetItem(val))

    def _import_data(self):
        if self._importing:
            return
        if not self.rows_data:
            QMessageBox.warning(self, "خطا", "فایلی انتخاب نشده است")
            return

        if not self.column_map or "mobile" not in self.column_map.values():
            QMessageBox.warning(
                self, "خطا",
                "ستون «موبایل» باید نقش‌بندی شود؛ بدون موبایل مخاطب قابل ذخیره نیست."
            )
            return

        mapped_mobile_header = next(
            (h for h, f in self.column_map.items() if f == "mobile"), None
        )
        no_mobile_count = sum(
            1 for row in self.rows_data
            if not _cell_to_text(row.get(mapped_mobile_header), "mobile")
        ) if mapped_mobile_header else len(self.rows_data)

        message = f"{len(self.rows_data)} ردیف اطلاعات وارد شود؟"
        if no_mobile_count:
            message += f"\n({no_mobile_count} ردیف بدون موبایل رد می‌شوند)"
        if not confirm(self, title="تأیید ورود اطلاعات", message=message, yes_text="وارد کن"):
            return

        # Build mapped rows (db_field -> normalized value)
        rows_to_import = []
        for row in self.rows_data:
            mapped = {}
            for excel_header, db_field in self.column_map.items():
                mapped[db_field] = _cell_to_text(row.get(excel_header), db_field)
            rows_to_import.append(mapped)

        self._importing = True
        self.import_btn.setEnabled(False)
        self.close_btn.setEnabled(False)  # بستن دیالوگ حین اجرای thread = کرش
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("در حال ورود اطلاعات... لطفاً صبر کنید")

        self.worker = ImportWorker(rows_to_import)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.import_done.connect(self._on_import_done)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_import_done(self, imported, duplicates, no_mobile, errors):
        self._importing = False
        self.progress_bar.setVisible(False)
        self.import_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        msg = (
            f"ورود اطلاعات انجام شد.\n"
            f"موفق: {imported}\n"
            f"تکراری (رد شد): {duplicates}\n"
            f"بدون موبایل (رد شد): {no_mobile}\n"
            f"خطا: {errors}"
        )
        if errors or no_mobile or duplicates:
            QMessageBox.warning(self, "نتیجه ورود", msg)
        else:
            QMessageBox.information(self, "نتیجه ورود", msg)
        self.accept()

    def reject(self):
        # جلوگیری از بسته‌شدن دیالوگ در حین اجرای worker
        if self._importing:
            QMessageBox.warning(
                self, "در حال انجام",
                "ورود اطلاعات در جریان است. تا پایان عملیات صبر کنید."
            )
            return
        super().reject()

    def closeEvent(self, event):
        if self._importing:
            QMessageBox.warning(
                self, "در حال انجام",
                "ورود اطلاعات در جریان است. تا پایان عملیات صبر کنید."
            )
            event.ignore()
            return
        super().closeEvent(event)
