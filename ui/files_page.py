from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QComboBox, QFileDialog, QDialog,
    QFormLayout, QTextEdit, QDateEdit, QSplitter, QGroupBox
)
from PyQt5.QtCore import Qt, QDate, QTimer
import os
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import file_repo, contact_repo
from services.file_service import file_service


class FileUploadDialog(QDialog):
    def __init__(self, parent=None, contact_id=None):
        super().__init__(parent)
        self.contact_id = contact_id
        self.file_path = None
        self.setWindowTitle("بارگذاری فایل / نامه")
        self.setMinimumWidth(560)
        self.setFont(get_font(10))
        self._setup_ui()
        if contact_id:
            contact = contact_repo.get_by_id(contact_id)
            if contact:
                self.contact_combo.setCurrentText(f"{contact.first_name} {contact.last_name}")

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("بارگذاری فایل یا نامه")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(16, True))
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        contacts = contact_repo.get_active(limit=500)
        self.contact_combo = QComboBox()
        self.contact_combo.setStyleSheet(Styles.combo_box())
        self.contact_combo.setFont(get_font(10))
        self.contact_combo.addItem("انتخاب مخاطب...", None)
        for cont in contacts:
            self.contact_combo.addItem(f"{cont.first_name} {cont.last_name} ({cont.mobile})", cont.id)
        form.addRow("مخاطب:", self.contact_combo)

        self.file_path_label = QLabel("فایلی انتخاب نشده")
        self.file_path_label.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted};")
        select_file_btn = QPushButton("انتخاب فایل")
        select_file_btn.setStyleSheet(Styles.primary_button())
        select_file_btn.clicked.connect(self._select_file)
        form.addRow(self.file_path_label, select_file_btn)

        self.category = QComboBox()
        self.category.setStyleSheet(Styles.combo_box())
        self.category.setFont(get_font(10))
        self.category.addItems(["سند", "نامه", "تصویر", "کارت ملی", "شناسنامه", "سایر"])
        form.addRow("نوع فایل:", self.category)

        self.description = QTextEdit()
        self.description.setMaximumHeight(60)
        self.description.setStyleSheet(Styles.text_edit())
        form.addRow("توضیحات:", self.description)

        # اطلاعات نامه
        letter_group = QGroupBox("اطلاعات نامه (اختیاری)")
        letter_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary};
                border: 1px solid {c.border_default}; border-radius: 8px;
                padding: 12px; margin-top: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; }}
        """)
        letter_layout = QFormLayout(letter_group)

        self.letter_number = QLineEdit()
        self.letter_number.setStyleSheet(Styles.line_edit())
        letter_layout.addRow("شماره نامه:", self.letter_number)

        self.letter_date = QDateEdit()
        self.letter_date.setStyleSheet(Styles.line_edit())
        self.letter_date.setCalendarPopup(True)
        self.letter_date.setDate(QDate.currentDate())
        letter_layout.addRow("تاریخ نامه:", self.letter_date)

        self.letter_subject = QLineEdit()
        self.letter_subject.setStyleSheet(Styles.line_edit())
        letter_layout.addRow("موضوع:", self.letter_subject)

        self.letter_type = QComboBox()
        self.letter_type.setStyleSheet(Styles.combo_box())
        self.letter_type.addItems(["ورودی", "خروجی", "داخلی"])
        letter_layout.addRow("نوع نامه:", self.letter_type)

        self.sender = QLineEdit()
        self.sender.setStyleSheet(Styles.line_edit())
        letter_layout.addRow("فرستنده:", self.sender)

        self.receiver = QLineEdit()
        self.receiver.setStyleSheet(Styles.line_edit())
        letter_layout.addRow("گیرنده:", self.receiver)

        layout.addLayout(form)
        layout.addWidget(letter_group)

        btn_layout = QHBoxLayout()
        upload_btn = QPushButton("بارگذاری")
        upload_btn.setStyleSheet(Styles.success_button())
        upload_btn.clicked.connect(self._upload)
        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(upload_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل", "",
            "فایل‌ها (*.pdf *.doc *.docx *.xls *.xlsx *.jpg *.jpeg *.png *.gif *.bmp *.txt *.rtf *.zip *.rar)"
        )
        if file_path:
            self.file_path = file_path
            name = os.path.basename(file_path)
            size = os.path.getsize(file_path) / 1024
            size_str = f"{size:.1f} KB" if size < 1024 else f"{size/1024:.1f} MB"
            self.file_path_label.setText(f"{name} ({size_str})")
            self.file_path_label.setStyleSheet(
                f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {theme_manager.current.success}; font-weight: bold;"
            )

    def _upload(self):
        contact_id = self.contact_combo.currentData()
        if not contact_id:
            QMessageBox.warning(self, "خطا", "لطفاً یک مخاطب انتخاب کنید")
            return
        if not self.file_path:
            QMessageBox.warning(self, "خطا", "لطفاً یک فایل انتخاب کنید")
            return

        category_map = {
            "سند": "document", "نامه": "letter", "تصویر": "image",
            "کارت ملی": "id_card", "شناسنامه": "birth_cert", "سایر": "other"
        }
        lt_map = {"ورودی": "incoming", "خروجی": "outgoing", "داخلی": "internal"}

        try:
            file_service.upload_file(
                contact_id=contact_id,
                file_path=self.file_path,
                category=category_map.get(self.category.currentText(), "other"),
                description=self.description.toPlainText().strip() or None,
                letter_number=self.letter_number.text().strip() or None,
                letter_date=self.letter_date.date().toPyDate() if self.letter_number.text().strip() else None,
                letter_subject=self.letter_subject.text().strip() or None,
                letter_type=lt_map.get(self.letter_type.currentText()),
                sender=self.sender.text().strip() or None,
                receiver=self.receiver.text().strip() or None,
            )
            QMessageBox.information(self, "موفق", "فایل با موفقیت بارگذاری شد")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در بارگذاری:\n{str(e)}")


class FilesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self.current_files = []
        self.selected_file_id = None
        self._setup_ui()
        self._load_files()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("مدیریت فایل‌ها و نامه‌ها")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(18, True))
        header.addWidget(title)
        header.addStretch()

        upload_btn = QPushButton("+ بارگذاری فایل / نامه")
        upload_btn.setStyleSheet(Styles.primary_button())
        upload_btn.clicked.connect(self._upload_file)
        header.addWidget(upload_btn)
        layout.addLayout(header)

        # جستجو و فیلتر
        search_frame = QFrame()
        search_frame.setStyleSheet(Styles.card())
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(15, 10, 15, 10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجو بر اساس نام فایل، شماره نامه، موضوع...")
        self.search_input.setStyleSheet(Styles.line_edit())
        self.search_input.setFont(get_font(10))
        # Debounce: _search_files runs a DB LIKE query on every keystroke.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._search_files)
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)

        self.filter_combo = QComboBox()
        self.filter_combo.setStyleSheet(Styles.combo_box())
        self.filter_combo.setFont(get_font(10))
        self.filter_combo.addItems(["همه", "نامه", "سند", "تصویر", "کارت ملی", "شناسنامه", "سایر"])
        self.filter_combo.currentTextChanged.connect(self._on_filter)
        self.filter_combo.setFixedWidth(150)
        search_layout.addWidget(self.filter_combo)
        layout.addWidget(search_frame)

        # جدول + جزئیات
        splitter = QSplitter(Qt.Orientation.Horizontal)

        table_frame = QFrame()
        table_frame.setStyleSheet(Styles.card())
        table_layout = QVBoxLayout(table_frame)

        self.files_table = QTableWidget()
        self.files_table.setStyleSheet(Styles.table_widget())
        self.files_table.setFont(get_font(10))
        self.files_table.setColumnCount(8)
        self.files_table.setHorizontalHeaderLabels([
            "ردیف", "نام فایل", "مخاطب", "نوع", "تاریخ", "اندازه", "شماره نامه", "عملیات"
        ])
        self.files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.files_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.files_table.setAlternatingRowColors(True)
        self.files_table.currentCellChanged.connect(self._on_row_changed)
        table_layout.addWidget(self.files_table)
        splitter.addWidget(table_frame)

        # پنل جزئیات
        detail_frame = QFrame()
        detail_frame.setStyleSheet(Styles.card())
        detail_frame.setFixedWidth(320)
        detail_layout = QVBoxLayout(detail_frame)

        detail_title = QLabel("جزئیات فایل")
        detail_title.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; font-size: 14px;")
        detail_layout.addWidget(detail_title)

        self.detail_info = QLabel("یک فایل انتخاب کنید")
        self.detail_info.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px;")
        self.detail_info.setWordWrap(True)
        detail_layout.addWidget(self.detail_info)

        dl_btn = QPushButton("دانلود فایل")
        dl_btn.setStyleSheet(Styles.primary_button())
        dl_btn.clicked.connect(self._download_selected)
        detail_layout.addWidget(dl_btn)

        delete_btn = QPushButton("حذف فایل")
        delete_btn.setStyleSheet(Styles.danger_button())
        delete_btn.clicked.connect(self._delete_selected)
        detail_layout.addWidget(delete_btn)
        detail_layout.addStretch()

        splitter.addWidget(detail_frame)
        splitter.setSizes([750, 320])
        layout.addWidget(splitter)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 12px;")
        layout.addWidget(self.count_label)

    def _load_files(self, files=None):
        c = theme_manager.current
        if files is None:
            files = file_repo.get_all(limit=500)

        self.current_files = files
        self.files_table.setRowCount(len(files))

        category_map = {
            "letter": "نامه", "document": "سند", "image": "تصویر",
            "id_card": "کارت ملی", "birth_cert": "شناسنامه", "other": "سایر"
        }

        for row, f in enumerate(files):
            self.files_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.files_table.setItem(row, 1, QTableWidgetItem(f.original_name))

            contact = contact_repo.get_by_id(f.contact_id) if f.contact_id else None
            contact_name = f"{contact.first_name} {contact.last_name}" if contact else "-"
            self.files_table.setItem(row, 2, QTableWidgetItem(contact_name))
            self.files_table.setItem(row, 3, QTableWidgetItem(category_map.get(f.file_category, f.file_category or "-")))
            self.files_table.setItem(row, 4, QTableWidgetItem(f.created_at.strftime("%Y/%m/%d") if f.created_at else "-"))

            size_kb = f.file_size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            self.files_table.setItem(row, 5, QTableWidgetItem(size_str))
            self.files_table.setItem(row, 6, QTableWidgetItem(f.letter_number or "-"))

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(4)

            dl_btn = QPushButton("دانلود")
            dl_btn.setFixedSize(58, 28)
            dl_btn.setStyleSheet(Styles.table_action_button("primary"))
            dl_btn.clicked.connect(lambda checked=False, fid=f.id: self._download_file(fid))
            actions_layout.addWidget(dl_btn)

            del_btn = QPushButton("حذف")
            del_btn.setFixedSize(48, 28)
            del_btn.setStyleSheet(Styles.table_action_button("danger"))
            del_btn.clicked.connect(lambda checked=False, fid=f.id: self._delete_file(fid))
            actions_layout.addWidget(del_btn)

            self.files_table.setCellWidget(row, 7, actions)
            self.files_table.setRowHeight(row, 42)

        self.count_label.setText(f"مجموع: {len(files)} فایل")

    def _on_row_changed(self, row, col, prev_row, prev_col):
        if 0 <= row < len(self.current_files):
            f = self.current_files[row]
            self.selected_file_id = f.id
            contact = contact_repo.get_by_id(f.contact_id) if f.contact_id else None

            info = [
                f"نام فایل: {f.original_name}",
                f"نوع: {f.file_category or '-'}",
                f"مخاطب: {f'{contact.first_name} {contact.last_name}' if contact else '-'}",
                f"تاریخ: {f.created_at.strftime('%Y/%m/%d %H:%M') if f.created_at else '-'}",
            ]
            if f.letter_number:
                info.append(f"شماره نامه: {f.letter_number}")
            if f.letter_subject:
                info.append(f"موضوع: {f.letter_subject}")
            if f.description:
                info.append(f"توضیحات: {f.description}")

            self.detail_info.setText("\n\n".join(info))

    def _on_search_changed(self, text):
        if not text:
            # Emptying the box must clear immediately, not after the delay.
            self._search_timer.stop()
            self._search_files()
            return
        self._search_timer.start()

    def _search_files(self, text=None):
        if text is None:
            text = self.search_input.text()
        if len(text) >= 2:
            files = file_repo.search_files(text)
            self._load_files(files)
        elif not text:
            self._load_files()

    def _on_filter(self, text):
        category_map = {
            "نامه": "letter", "سند": "document", "تصویر": "image",
            "کارت ملی": "id_card", "شناسنامه": "birth_cert", "سایر": "other"
        }
        if text == "همه":
            self._load_files()
        else:
            cat = category_map.get(text)
            if cat:
                all_files = file_repo.get_all(limit=1000)
                filtered = [f for f in all_files if f.file_category == cat]
                self._load_files(filtered)

    def _upload_file(self):
        if FileUploadDialog(self).exec():
            self._load_files()

    def _download_file(self, file_id):
        try:
            path = file_service.download_file(file_id)
            QMessageBox.information(self, "موفق", f"فایل ذخیره شد:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _download_selected(self):
        if self.selected_file_id:
            self._download_file(self.selected_file_id)
        else:
            QMessageBox.warning(self, "هشدار", "فایلی انتخاب نشده است")

    def _delete_file(self, file_id):
        f = file_repo.get_by_id(file_id)
        if not confirm_delete(self, noun="فایل", name=f.original_name if f else None):
            return
        file_service.delete_file(file_id)
        self._load_files()
        QMessageBox.information(self, "موفق", "فایل حذف شد")

    def _delete_selected(self):
        if self.selected_file_id:
            self._delete_file(self.selected_file_id)
        else:
            QMessageBox.warning(self, "هشدار", "فایلی انتخاب نشده است")

    def refresh(self):
        self._load_files()