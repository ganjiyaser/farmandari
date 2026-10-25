from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QWidget, QFormLayout, QLineEdit,
    QTextEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from services.repositories import contact_repo, profile_repo, file_repo, message_repo
from services.file_service import file_service
from services.export_service import export_service


class ProfileDialog(QDialog):
    def __init__(self, parent=None, contact_id: int = None):
        super().__init__(parent)
        self.contact_id = contact_id
        self.contact = None
        if contact_id:
            self.contact = contact_repo.get_with_profile(contact_id)
        self.setWindowTitle(f"پروفایل - {self.contact.first_name} {self.contact.last_name}" if self.contact else "پروفایل")
        self.setMinimumWidth(750)
        self.setMinimumHeight(600)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.contact:
            self._load_data()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {c.primary};
                padding: 20px;
            }}
        """)
        header_layout = QHBoxLayout(header)

        self.name_label = QLabel("")
        self.name_label.setStyleSheet(f"color: {c.fg_on_emphasis}; font-size: 20px; font-weight: bold; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        header_layout.addWidget(self.name_label)

        self.position_label = QLabel("")
        self.position_label.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 13px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
        header_layout.addWidget(self.position_label)
        header_layout.addStretch()

        close_btn = QPushButton("X")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.2); color: {c.fg_on_emphasis}; border: none; border-radius: 16px; font-size: 14px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.3); }}
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        layout.addWidget(header)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {c.border_default}; background: white; }}
            QTabBar::tab {{ padding: 10px 20px; margin-left: 5px; border: 1px solid {c.border_default};
                border-bottom: none; border-radius: 8px 8px 0 0; background: {c.canvas_subtle}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px; }}
            QTabBar::tab:selected {{ background: white; border-bottom: 2px solid {c.primary}; font-weight: bold; }}
        """)

        tabs.addTab(self._info_tab(), "اطلاعات تماس")
        tabs.addTab(self._profile_tab(), "پروفایل کامل")
        tabs.addTab(self._files_tab(), "فایل‌ها و نامه‌ها")
        tabs.addTab(self._messages_tab(), "پیامک‌ها")

        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(15, 10, 15, 15)

        print_btn = QPushButton("چاپ پروفایل (PDF)")
        print_btn.setStyleSheet(Styles.primary_button())
        print_btn.clicked.connect(self._print_profile)

        export_btn = QPushButton("خروجی PDF")
        export_btn.setStyleSheet(Styles.success_button())
        export_btn.clicked.connect(self._export_pdf)

        btn_layout.addWidget(print_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _info_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)

        frame = QFrame()
        frame.setStyleSheet(Styles.card())
        form = QFormLayout(frame)
        form.setSpacing(8)

        fields = [
            ("موبایل:", "mobile"), ("تلفن:", "phone"), ("کد ملی:", "national_code"),
            ("استان:", "province"), ("شهرستان:", "county"), ("بخش:", "district"),
            ("دهستان:", "rural_district"), ("روستا:", "village"),
            ("آدرس:", "address"), ("کد پستی:", "postal_code"), ("سازمان:", "organization"),
        ]

        self.info_labels = {}
        for label_text, field in fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-weight: bold; color: {c.primary}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
            lbl.setFont(get_font(10, True))
            val = QLabel("-")
            val.setStyleSheet(f"color: {c.fg_default}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
            val.setFont(get_font(10))
            form.addRow(lbl, val)
            self.info_labels[field] = val

        layout.addWidget(frame)
        layout.addStretch()
        return widget

    def _profile_tab(self):
        c = theme_manager.current
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)

        frame = QFrame()
        frame.setStyleSheet(Styles.card())
        form = QFormLayout(frame)
        form.setSpacing(8)

        fields = [
            ("تاریخ تولد:", "birth_date"), ("جنسیت:", "gender"), ("تحصیلات:", "education"),
            ("وضعیت تأهل:", "marital_status"), ("تعداد فرزندان:", "children_count"),
            ("تاریخ استخدام:", "appointment_date"), ("نوع اشتغال:", "employment_type"),
            ("گروه حقوقی:", "salary_grade"), ("شماره بیمه:", "insurance_number"),
            ("مخاطب اضطراری:", "emergency_contact_name"), ("تلفن اضطراری:", "emergency_contact_phone"),
            ("نسبت:", "emergency_contact_relation"),
        ]

        self.profile_labels = {}
        for label_text, field in fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-weight: bold; color: {c.primary}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
            lbl.setFont(get_font(10, True))
            val = QLabel("-")
            val.setStyleSheet(f"color: {c.fg_default}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;")
            val.setFont(get_font(10))
            form.addRow(lbl, val)
            self.profile_labels[field] = val

        layout.addWidget(frame)
        layout.addStretch()
        return widget

    def _files_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        upload_btn = QPushButton("بارگذاری فایل")
        upload_btn.setStyleSheet(Styles.primary_button())
        upload_btn.clicked.connect(self._upload_file)
        header.addWidget(upload_btn)
        header.addStretch()
        layout.addLayout(header)

        self.files_table = QTableWidget()
        self.files_table.setStyleSheet(Styles.table_widget())
        self.files_table.setFont(get_font(9))
        self.files_table.setColumnCount(5)
        self.files_table.setHorizontalHeaderLabels(["نام فایل", "نوع", "اندازه", "تاریخ", "عملیات"])
        self.files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.files_table)

        return widget

    def _messages_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)

        self.messages_table = QTableWidget()
        self.messages_table.setStyleSheet(Styles.table_widget())
        self.messages_table.setFont(get_font(9))
        self.messages_table.setColumnCount(4)
        self.messages_table.setHorizontalHeaderLabels(["نوع", "جهت", "متن", "تاریخ"])
        self.messages_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.messages_table)

        return widget

    def _load_data(self):
        c = self.contact
        p = c.profile

        self.name_label.setText(f"{c.first_name} {c.last_name}")
        self.position_label.setText(c.position or "")

        info_map = {
            "mobile": c.mobile, "phone": c.phone, "national_code": c.national_code,
            "province": c.province, "county": c.county, "district": c.district,
            "rural_district": c.rural_district, "village": c.village,
            "address": c.address, "postal_code": c.postal_code, "organization": c.organization,
        }
        for field, value in info_map.items():
            if field in self.info_labels:
                self.info_labels[field].setText(value or "-")

        if p:
            profile_map = {
                "birth_date": p.birth_date.strftime("%Y/%m/%d") if p.birth_date else None,
                "gender": "مرد" if p.gender == "male" else "زن" if p.gender == "female" else None,
                "education": p.education, "marital_status": p.marital_status,
                "children_count": str(p.children_count) if p.children_count else None,
                "appointment_date": p.appointment_date.strftime("%Y/%m/%d") if p.appointment_date else None,
                "employment_type": p.employment_type, "salary_grade": p.salary_grade,
                "insurance_number": p.insurance_number,
                "emergency_contact_name": p.emergency_contact_name,
                "emergency_contact_phone": p.emergency_contact_phone,
                "emergency_contact_relation": p.emergency_contact_relation,
            }
            for field, value in profile_map.items():
                if field in self.profile_labels and value:
                    self.profile_labels[field].setText(value)

        self._load_files()
        self._load_messages()

    def _load_files(self):
        c = theme_manager.current
        files = file_repo.get_by_contact(self.contact_id)
        self.files_table.setRowCount(len(files))

        for row, f in enumerate(files):
            self.files_table.setItem(row, 0, QTableWidgetItem(f.original_name))
            self.files_table.setItem(row, 1, QTableWidgetItem(f.file_category or "-"))
            size_kb = f.file_size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            self.files_table.setItem(row, 2, QTableWidgetItem(size_str))
            self.files_table.setItem(row, 3, QTableWidgetItem(f.created_at.strftime("%Y/%m/%d")))

            dl_btn = QPushButton("دانلود")
            dl_btn.setFixedHeight(26)
            dl_btn.setStyleSheet(Styles.table_action_button("primary"))
            dl_btn.clicked.connect(lambda _, fid=f.id: self._download_file(fid))
            self.files_table.setCellWidget(row, 4, dl_btn)

    def _load_messages(self):
        messages = message_repo.get_by_contact(self.contact_id)
        self.messages_table.setRowCount(len(messages))

        dir_map = {"outgoing": "ارسالی", "incoming": "دریافتی"}

        for row, m in enumerate(messages):
            self.messages_table.setItem(row, 0, QTableWidgetItem("پیامک"))
            self.messages_table.setItem(row, 1, QTableWidgetItem(dir_map.get(m.direction.value if m.direction else "", "-")))
            text_item = QTableWidgetItem(m.content or "-")
            text_item.setToolTip(m.content or "")
            self.messages_table.setItem(row, 2, text_item)
            self.messages_table.setItem(row, 3, QTableWidgetItem(m.created_at.strftime("%Y/%m/%d %H:%M") if m.created_at else "-"))

    def _upload_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل", "",
            "فایل‌ها (*.pdf *.doc *.docx *.xls *.xlsx *.jpg *.jpeg *.png *.txt *.zip *.rar)")
        if file_path:
            try:
                file_service.upload_file(self.contact_id, file_path, category="document")
                self._load_files()
                QMessageBox.information(self, "موفقیت", "فایل با موفقیت بارگذاری شد")
            except Exception as e:
                QMessageBox.critical(self, "خطا", f"خطا در بارگذاری: {str(e)}")

    def _download_file(self, file_id):
        try:
            rec = file_repo.get_by_id(file_id)
            suggested = (rec.original_name if rec and rec.original_name
                         else f"file_{file_id}")
            dest, _ = QFileDialog.getSaveFileName(
                self, "ذخیرهٔ فایل", suggested, "همهٔ فایل‌ها (*.*)"
            )
            if not dest:
                return
            path = file_service.download_file(file_id, dest_path=dest)
            QMessageBox.information(self, "موفقیت", f"فایل ذخیره شد:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در دانلود: {str(e)}")

    def _print_profile(self):
        try:
            base = f"contact_{self.contact_id}"
            if self.contact:
                name = f"{self.contact.first_name} {self.contact.last_name}".strip()
                if name:
                    base = "".join(
                        ch for ch in name if ch.isalnum() or ch in "_- "
                    ).strip() or base
            dest, _ = QFileDialog.getSaveFileName(
                self, "ذخیرهٔ فایل PDF", base + ".pdf", "PDF (*.pdf)"
            )
            if not dest:
                return
            path = export_service.export_contact_profile_pdf(
                self.contact_id, output_path=dest
            )
            QMessageBox.information(self, "موفقیت", f"فایل PDF ذخیره شد:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در خروجی: {str(e)}")

    def _export_pdf(self):
        self._print_profile()
