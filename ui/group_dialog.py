from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox
)
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm
from services.repositories import group_repo, contact_repo, contact_group_repo


class ManageContactGroupsDialog(QDialog):
    def __init__(self, parent=None, contact_id: int = None):
        super().__init__(parent)
        self.contact_id = contact_id
        self.contact = contact_repo.get_by_id(contact_id)
        title = "مدیریت گروه‌ها"
        if self.contact:
            title = f"مدیریت گروه‌ها - {self.contact.first_name} {self.contact.last_name}"
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self.setMinimumHeight(450)
        self.setFont(get_font(10))
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel(
            f"گروه‌های {self.contact.first_name} {self.contact.last_name}"
            if self.contact else "مدیریت گروه‌ها"
        )
        header.setStyleSheet(Styles.title_label())
        header.setFont(get_font(16, True))
        layout.addWidget(header)

        # بخش افزودن
        add_layout = QHBoxLayout()
        self.group_combo = QComboBox()
        self.group_combo.setStyleSheet(Styles.combo_box())
        self.group_combo.setFont(get_font(10))
        self.group_combo.setMinimumWidth(280)
        add_layout.addWidget(self.group_combo)

        add_btn = QPushButton("افزودن به گروه")
        add_btn.setStyleSheet(Styles.success_button())
        add_btn.clicked.connect(self._add_to_group)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        layout.addWidget(QLabel("گروه‌های فعلی این مخاطب:"))

        self.groups_table = QTableWidget()
        self.groups_table.setStyleSheet(Styles.table_widget())
        self.groups_table.setFont(get_font(10))
        self.groups_table.setColumnCount(3)
        self.groups_table.setHorizontalHeaderLabels(["نام گروه", "تعداد اعضا", "عملیات"])
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.groups_table.setAlternatingRowColors(True)
        layout.addWidget(self.groups_table)

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("بستن")
        close_btn.setStyleSheet(Styles.danger_button())
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_data(self):
        c = theme_manager.current
        contact_groups = contact_group_repo.get_contact_groups(self.contact_id)
        self.groups_table.setRowCount(len(contact_groups))

        for row, g in enumerate(contact_groups):
            self.groups_table.setItem(row, 0, QTableWidgetItem(g.name))
            count = group_repo.get_contact_count(g.id)
            self.groups_table.setItem(row, 1, QTableWidgetItem(str(count)))

            remove_btn = QPushButton("حذف")
            remove_btn.setFixedHeight(30)
            remove_btn.setStyleSheet(Styles.table_action_button("danger"))
            remove_btn.clicked.connect(lambda checked=False, gid=g.id: self._remove_from_group(gid))
            self.groups_table.setCellWidget(row, 2, remove_btn)
            self.groups_table.setRowHeight(row, 42)

        # پر کردن لیست گروه‌ها
        all_groups = group_repo.get_with_counts()
        existing_ids = {g.id for g in contact_groups}
        self.group_combo.clear()
        self.group_combo.addItem("انتخاب گروه...", None)
        for g_data in all_groups:
            g = g_data["group"]
            if g.id not in existing_ids:
                self.group_combo.addItem(f"{g.name}  ({g_data['contact_count']} عضو)", g.id)

    def _add_to_group(self):
        group_id = self.group_combo.currentData()
        if not group_id:
            QMessageBox.warning(self, "خطا", "لطفاً یک گروه انتخاب کنید")
            return
        try:
            contact_group_repo.add_contact_to_group(self.contact_id, group_id)
            self._load_data()
            QMessageBox.information(self, "موفق", "مخاطب با موفقیت به گروه اضافه شد")
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _remove_from_group(self, group_id):
        if confirm(
            self, title="حذف از گروه",
            message="این مخاطب فقط از گروه حذف می‌شود و خود مخاطب باقی می‌ماند.",
            yes_text="حذف از گروه", danger=True,
        ):
            contact_group_repo.remove_contact_from_group(self.contact_id, group_id)
            self._load_data()