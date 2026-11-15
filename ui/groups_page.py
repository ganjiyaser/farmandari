from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QComboBox,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QTimer
import uuid
from qfluentwidgets import TitleLabel, PrimaryPushButton, PushButton, FluentIcon as FIF, ElevatedCardWidget
from ui.styles import Styles, get_font, alpha
from ui.theme import theme_manager
from ui.dialogs import confirm, confirm_delete
from services.repositories import group_repo, contact_repo, contact_group_repo


class GroupDialog(QDialog):
    def __init__(self, parent=None, group_id=None):
        super().__init__(parent)
        self.group_id = group_id
        self.group = group_repo.get_by_id(group_id) if group_id else None
        self.setWindowTitle("ویرایش گروه" if group_id else "گروه جدید")
        self.setMinimumWidth(450)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.group:
            self._load_data()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("ویرایش گروه" if self.group_id else "گروه جدید")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(16, True))
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        self.name = QLineEdit()
        self.name.setPlaceholderText("نام گروه")
        self.name.setStyleSheet(Styles.line_edit())
        self.name.setFont(get_font(10))
        form.addRow("نام:", self.name)

        self.description = QTextEdit()
        self.description.setMaximumHeight(80)
        self.description.setStyleSheet(Styles.text_edit())
        self.description.setFont(get_font(10))
        form.addRow("توضیحات:", self.description)

        self.parent_combo = QComboBox()
        self.parent_combo.setStyleSheet(Styles.combo_box())
        self.parent_combo.setFont(get_font(10))
        self.parent_combo.addItem("بدون گروه والد", None)
        groups = group_repo.get_all(limit=100)
        for g in groups:
            if g.id != self.group_id:
                self.parent_combo.addItem(g.name, g.id)
        form.addRow("گروه والد:", self.parent_combo)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("ذخیره")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _load_data(self):
        self.name.setText(self.group.name)
        self.description.setText(self.group.description or "")
        if self.group.parent_id:
            for i in range(self.parent_combo.count()):
                if self.parent_combo.itemData(i) == self.group.parent_id:
                    self.parent_combo.setCurrentIndex(i)
                    break

    def _save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "خطا", "نام گروه الزامی است")
            return
        data = {
            "name": name,
            "description": self.description.toPlainText().strip() or None,
            "parent_id": self.parent_combo.currentData(),
        }
        try:
            if self.group_id:
                group_repo.update(self.group_id, **data)
            else:
                data["uuid"] = str(uuid.uuid4())
                group_repo.create(**data)
            QMessageBox.information(self, "موفق", "گروه ذخیره شد")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))


class AddContactsDialog(QDialog):
    def __init__(self, parent=None, group_id=None):
        super().__init__(parent)
        self.group_id = int(group_id) if group_id is not None else None
        self.group = group_repo.get_by_id(self.group_id) if self.group_id else None
        self.existing_ids = set()
        title_name = self.group.name if self.group else ""
        self.setWindowTitle(f"اضافه کردن مخاطب به گروه «{title_name}»")
        self.setMinimumWidth(620)
        self.setMinimumHeight(420)
        self.setFont(get_font(10))
        self._setup_ui()
        self._load_contacts()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"انتخاب مخاطبین برای گروه «{self.group.name if self.group else ''}»")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(14, True))
        layout.addWidget(title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجو بر اساس نام یا شماره موبایل...")
        self.search_input.setStyleSheet(Styles.line_edit())
        self.search_input.setFont(get_font(10))
        # Debounce: each keystroke re-queried contacts and rebuilt the table.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(
            lambda: self._load_contacts(self.search_input.text())
        )
        self.search_input.textChanged.connect(self._filter_contacts)
        layout.addWidget(self.search_input)

        self.contacts_table = QTableWidget()
        self.contacts_table.setStyleSheet(Styles.table_widget())
        self.contacts_table.setFont(get_font(9))
        self.contacts_table.setColumnCount(4)
        self.contacts_table.setHorizontalHeaderLabels(["انتخاب", "نام", "موبایل", "روستا"])
        self.contacts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.contacts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.contacts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.contacts_table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.contacts_table)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px;")
        layout.addWidget(self.count_label)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("افزودن انتخاب شده‌ها")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_selected)
        cancel_btn = QPushButton("لغو")
        cancel_btn.setStyleSheet(Styles.secondary_button())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_item_changed(self, item):
        if item and item.column() == 0:
            self._update_count()

    def _load_contacts(self, search_text=""):
        self.contacts_table.blockSignals(True)
        try:
            self.existing_ids = set()
            if self.group_id:
                existing_contacts = contact_repo.get_by_group(self.group_id, limit=5000)
                self.existing_ids = {c.id for c in existing_contacts}

            if search_text and len(search_text.strip()) >= 1:
                all_contacts = contact_repo.search(search_text.strip(), limit=500)
            else:
                all_contacts = contact_repo.get_active(limit=2000) or contact_repo.get_all(limit=2000)

            self.contacts_table.setRowCount(len(all_contacts))
            for row, contact in enumerate(all_contacts):
                check_item = QTableWidgetItem()
                check_item.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                # store contact id on the check item
                check_item.setData(Qt.ItemDataRole.UserRole, contact.id)

                if contact.id in self.existing_ids:
                    check_item.setCheckState(Qt.CheckState.Checked)
                    # keep enabled so user can see; we skip re-adding later
                    check_item.setFlags(check_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                else:
                    check_item.setCheckState(Qt.CheckState.Unchecked)

                self.contacts_table.setItem(row, 0, check_item)
                self.contacts_table.setItem(
                    row, 1, QTableWidgetItem(f"{contact.first_name or ''} {contact.last_name or ''}".strip())
                )
                self.contacts_table.setItem(row, 2, QTableWidgetItem(contact.mobile or "-"))
                self.contacts_table.setItem(row, 3, QTableWidgetItem(contact.village or "-"))
                self.contacts_table.setRowHeight(row, 32)
        finally:
            self.contacts_table.blockSignals(False)
        self._update_count()

    def _filter_contacts(self, text):
        if not text:
            self._search_timer.stop()
            self._load_contacts(text)
            return
        self._search_timer.start()

    def _update_count(self):
        total = self.contacts_table.rowCount()
        selected_new = 0
        for row in range(total):
            item = self.contacts_table.item(row, 0)
            if not item:
                continue
            cid = item.data(Qt.ItemDataRole.UserRole)
            if item.checkState() == Qt.CheckState.Checked and cid not in self.existing_ids:
                selected_new += 1
        self.count_label.setText(
            f"تعداد: {total} مخاطب | انتخاب جدید: {selected_new} | عضو فعلی گروه: {len(self.existing_ids)}"
        )

    def _add_selected(self):
        if not self.group_id:
            QMessageBox.warning(self, "خطا", "گروه مشخص نیست")
            return

        to_add = []
        for row in range(self.contacts_table.rowCount()):
            item = self.contacts_table.item(row, 0)
            if not item:
                continue
            if item.checkState() != Qt.CheckState.Checked:
                continue
            cid = item.data(Qt.ItemDataRole.UserRole)
            if cid is None:
                continue
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                continue
            if cid in self.existing_ids:
                continue  # already member
            to_add.append(cid)

        if not to_add:
            QMessageBox.warning(
                self, "هشدار",
                "هیچ مخاطب جدیدی انتخاب نشده است.\n"
                "مخاطبینی که از قبل عضو گروه هستند دوباره اضافه نمی‌شوند."
            )
            return

        added = 0
        errors = []
        for contact_id in to_add:
            try:
                contact_group_repo.add_contact_to_group(contact_id, self.group_id)
                added += 1
            except Exception as e:
                errors.append(f"{contact_id}: {e}")

        if added > 0:
            msg = f"{added} مخاطب به گروه اضافه شد"
            if errors:
                msg += f"\n\nخطا در {len(errors)} مورد:\n" + "\n".join(errors[:5])
            QMessageBox.information(self, "موفق", msg)
            self.accept()
        else:
            detail = "\n".join(errors[:8]) if errors else "علت نامشخص"
            QMessageBox.critical(self, "خطا", f"مخاطبی اضافه نشد.\n{detail}")


class GroupsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_group_id = None
        self.setFont(get_font(10))
        self._setup_ui()
        self._load_groups()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        title = TitleLabel("مدیریت گروه‌ها")
        header.addWidget(title)
        header.addStretch()

        add_btn = PrimaryPushButton(FIF.ADD, "گروه جدید")
        add_btn.clicked.connect(self._add_group)
        header.addWidget(add_btn)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        tree_frame = QFrame()
        tree_frame.setStyleSheet(Styles.card())
        tree_layout = QVBoxLayout(tree_frame)

        tree_header = QLabel("درخت گروه‌ها")
        tree_header.setStyleSheet(
            f"font-weight: bold; color: {c.primary}; font-size: 13px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        tree_layout.addWidget(tree_header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ border: none; font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; }} "
            f"QTreeWidget::item {{ padding: 6px; }} "
            f"QTreeWidget::item:selected {{ background-color: {alpha(c.primary, 0x15)}; color: {c.primary}; }}"
        )
        self.tree.currentItemChanged.connect(self._on_tree_select)
        tree_layout.addWidget(self.tree)
        splitter.addWidget(tree_frame)

        detail_frame = QFrame()
        detail_frame.setStyleSheet(Styles.card())
        detail_layout = QVBoxLayout(detail_frame)

        self.detail_title = QLabel("یک گروه انتخاب کنید")
        self.detail_title.setStyleSheet(
            f"font-weight: bold; color: {c.primary}; font-size: 13px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        detail_layout.addWidget(self.detail_title)

        self.detail_info = QLabel("")
        self.detail_info.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 12px; font-family: 'Vazirmatn', 'Segoe UI', Tahoma;"
        )
        detail_layout.addWidget(self.detail_info)

        self.members_table = QTableWidget()
        self.members_table.setStyleSheet(Styles.table_widget())
        self.members_table.setFont(get_font(9))
        self.members_table.setColumnCount(5)
        self.members_table.setHorizontalHeaderLabels(["نام", "موبایل", "سمت", "روستا", "عملیات"])
        self.members_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        detail_layout.addWidget(self.members_table)

        btn_layout = QHBoxLayout()
        self.add_member_btn = PrimaryPushButton(FIF.ADD, "اضافه کردن مخاطب")
        self.add_member_btn.setEnabled(False)
        self.add_member_btn.clicked.connect(self._add_contacts_to_group)

        self.edit_btn = PushButton(FIF.EDIT, "ویرایش گروه")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_group)

        self.delete_btn = PushButton(FIF.DELETE, "حذف گروه")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_group)

        btn_layout.addWidget(self.add_member_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        detail_layout.addLayout(btn_layout)

        splitter.addWidget(detail_frame)
        splitter.setSizes([350, 550])
        layout.addWidget(splitter)

    def _load_groups(self):
        self.tree.clear()
        groups = group_repo.get_tree()
        for g in groups:
            item = QTreeWidgetItem()
            item.setText(0, g.name)
            item.setData(0, Qt.ItemDataRole.UserRole, g.id)
            self._add_children(item, g.id)
            self.tree.addTopLevelItem(item)
        self.tree.expandAll()
        # Auto-select first group so action buttons become usable
        if self.tree.topLevelItemCount() > 0:
            first = self.tree.topLevelItem(0)
            self.tree.setCurrentItem(first)
            # setCurrentItem triggers currentItemChanged → _on_tree_select
        else:
            self.current_group_id = None
            self._clear_detail()

    def _add_children(self, parent_item, parent_id):
        for child in group_repo.get_children(parent_id):
            item = QTreeWidgetItem()
            item.setText(0, child.name)
            item.setData(0, Qt.ItemDataRole.UserRole, child.id)
            self._add_children(item, child.id)
            parent_item.addChild(item)

    def _on_tree_select(self, item, prev):
        if item is None:
            self.current_group_id = None
            self._clear_detail()
            return
        group_id = item.data(0, Qt.ItemDataRole.UserRole)
        if group_id is None:
            self.current_group_id = None
            self._clear_detail()
            return
        self.current_group_id = group_id
        self._load_group_detail(group_id)

    def _load_group_detail(self, group_id):
        group = group_repo.get_by_id(group_id)
        if not group:
            return
        self.detail_title.setText(group.name)
        contacts = contact_repo.get_by_group(group_id)
        info = [f"تعداد اعضا: {len(contacts)}"]
        if group.description:
            info.append(f"توضیحات: {group.description}")
        self.detail_info.setText(" | ".join(info))

        self.members_table.setRowCount(len(contacts))
        for row, c in enumerate(contacts):
            self.members_table.setItem(row, 0, QTableWidgetItem(f"{c.first_name} {c.last_name}"))
            self.members_table.setItem(row, 1, QTableWidgetItem(c.mobile or "-"))
            self.members_table.setItem(row, 2, QTableWidgetItem(c.position or "-"))
            self.members_table.setItem(row, 3, QTableWidgetItem(c.village or "-"))

            remove_btn = QPushButton("حذف")
            remove_btn.setFixedHeight(26)
            remove_btn.setStyleSheet(Styles.table_action_button("danger"))
            remove_btn.clicked.connect(lambda checked, cid=c.id: self._remove_contact(cid))
            self.members_table.setCellWidget(row, 4, remove_btn)
            self.members_table.setRowHeight(row, 32)

        self.add_member_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)

    def _add_contacts_to_group(self):
        group_id = self.current_group_id
        if not group_id:
            QMessageBox.warning(self, "هشدار", "ابتدا یک گروه از درخت سمت چپ انتخاب کنید")
            return
        if AddContactsDialog(self, group_id=group_id).exec():
            self._load_group_detail(group_id)

    def _remove_contact(self, contact_id):
        if not self.current_group_id:
            return
        if confirm(
            self, title="حذف عضو از گروه",
            message="این مخاطب فقط از گروه حذف می‌شود و خود مخاطب باقی می‌ماند.",
            yes_text="حذف از گروه", danger=True,
        ):
            contact_group_repo.remove_contact_from_group(contact_id, self.current_group_id)
            self._load_group_detail(self.current_group_id)

    def _add_group(self):
        if GroupDialog(self).exec():
            self._load_groups()

    def _edit_group(self):
        group_id = self.current_group_id
        if not group_id:
            QMessageBox.warning(self, "هشدار", "ابتدا یک گروه انتخاب کنید")
            return
        if GroupDialog(self, group_id=group_id).exec():
            self._load_groups()
            # reselect after reload
            self._select_group_in_tree(group_id)

    def _delete_group(self):
        group_id = self.current_group_id
        if not group_id:
            QMessageBox.warning(self, "هشدار", "ابتدا یک گروه انتخاب کنید")
            return
        group = group_repo.get_by_id(group_id)
        if not group:
            return
        if group.children:
            QMessageBox.warning(
                self, "حذف ممکن نیست",
                f"گروه «{group.name}» {len(group.children)} زیرگروه دارد.\n"
                "ابتدا زیرگروه‌ها را حذف یا جابه‌جا کنید.",
            )
            return
        if confirm_delete(self, noun="گروه", name=group.name):
            try:
                group_repo.delete(group_id)
            except Exception as e:
                QMessageBox.critical(self, "خطا", f"حذف گروه انجام نشد:\n{e}")
                return
            self.current_group_id = None
            self._load_groups()
            self._clear_detail()

    def _clear_detail(self):
        self.detail_title.setText("یک گروه انتخاب کنید")
        self.detail_info.setText("")
        self.members_table.setRowCount(0)
        self.add_member_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

    def _select_group_in_tree(self, group_id):
        """Find and select a group item by id after tree reload."""
        def walk(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == group_id:
                self.tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    return True
            return False
        for i in range(self.tree.topLevelItemCount()):
            if walk(self.tree.topLevelItem(i)):
                return

    def refresh(self):
        self._load_groups()
