from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QDialog, QCheckBox, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import task_repo
import jdatetime


class TaskDialog(QDialog):
    task_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("کار جدید")
        self.setMinimumWidth(480)
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
            QLineEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                color: {c.fg_default};
            }}
            QLineEdit:focus {{
                border: 2px solid {c.input_border_hover};
            }}
            QTextEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {c.fg_default};
            }}
            QTextEdit:focus {{
                border: 2px solid {c.input_border_hover};
            }}
            QComboBox {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {c.fg_default};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.canvas_overlay};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                selection-background-color: {c.accent_blue};
                selection-color: white;
            }}
            QPushButton {{
                font-family: Tahoma;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl = QLabel("عنوان")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(lbl)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("عنوان کار...")
        layout.addWidget(self.title_input)

        lbl2 = QLabel("توضیحات (اختیاری)")
        lbl2.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(lbl2)

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("توضیحات...")
        self.desc_input.setMaximumHeight(100)
        layout.addWidget(self.desc_input)

        row = QHBoxLayout()

        lbl3 = QLabel("اولویت:")
        lbl3.setStyleSheet(f"color: {c.fg_default};")
        row.addWidget(lbl3)

        from PyQt6.QtWidgets import QComboBox
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["کم", "متوسط", "زیاد"])
        self.priority_combo.setCurrentIndex(1)
        row.addWidget(self.priority_combo)

        row.addStretch()

        lbl4 = QLabel("مهلت:")
        lbl4.setStyleSheet(f"color: {c.fg_default};")
        row.addWidget(lbl4)

        today = jdatetime.date.today().strftime("%Y/%m/%d")
        self.due_input = QLineEdit()
        self.due_input.setPlaceholderText(today)
        self.due_input.setFixedWidth(130)
        row.addWidget(self.due_input)

        layout.addLayout(row)

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

    def _save(self):
        title = self.title_input.text().strip()
        if not title:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "خطا", "عنوان را وارد کنید")
            return

        priority_map = {"کم": "low", "متوسط": "medium", "زیاد": "high"}
        priority = priority_map.get(self.priority_combo.currentText(), "medium")

        due = self.due_input.text().strip() or None
        if due:
            # تاریخ باید شمسی معتبر و قالب YYYY/MM/DD باشد؛ مقایسه‌های
            # رشته‌ای (کارهای امروز) بدون صفر ابتدا هرگز مطابقت نمی‌کنند
            from PyQt6.QtWidgets import QMessageBox
            parts = due.split("/")
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                try:
                    jdatetime.date(y, m, d)
                    due = f"{y:04d}/{m:02d}/{d:02d}"
                except (ValueError, TypeError):
                    QMessageBox.warning(
                        self, "خطا",
                        "تاریخ نامعتبر است. قالب صحیح: 1404/07/29"
                    )
                    return
            else:
                QMessageBox.warning(
                    self, "خطا", "قالب تاریخ صحیح نیست. مثال: 1404/07/29"
                )
                return

        from PyQt6.QtWidgets import QMessageBox
        try:
            task_repo.create(
                title=title,
                description=self.desc_input.toPlainText().strip(),
                priority=priority,
                due_date=due,
            )
        except Exception as e:
            # خطای مدیریت‌نشده در slot در PyQt6 کل برنامه را می‌بندد
            QMessageBox.critical(self, "خطا در ذخیره", str(e))
            return

        self.task_saved.emit()
        self.accept()


class TaskRow(QFrame):
    toggled = pyqtSignal()
    deleted = pyqtSignal()

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setFixedHeight(56)
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current

        priority_colors = {"high": c.accent_red, "medium": c.accent_orange, "low": c.accent_green}
        pcolor = priority_colors.get(self.task.priority, c.accent_orange)

        done_style = "text-decoration: line-through;" if self.task.is_done else ""
        opacity = "0.5" if self.task.is_done else "1.0"

        self.setStyleSheet(f"""
            TaskRow {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-right: 3px solid {pcolor};
                border-radius: 8px;
            }}
            TaskRow:hover {{
                background-color: {c.canvas_subtle};
                border: 1px solid {c.primary};
                border-right: 3px solid {pcolor};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.task.is_done)
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.stateChanged.connect(self._toggle_done)
        layout.addWidget(self.checkbox)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title = QLabel(self.task.title)
        title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {c.fg_default};
            opacity: {opacity};
            {done_style}
        """)
        text_col.addWidget(title)

        if self.task.description:
            desc = QLabel(self.task.description[:80])
            desc.setStyleSheet(f"font-size: 11px; color: {c.fg_muted}; opacity: {opacity};")
            text_col.addWidget(desc)

        layout.addLayout(text_col, 1)

        if self.task.due_date:
            due = QLabel(self.task.due_date)
            due.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
            due.setFixedWidth(90)
            layout.addWidget(due)

        del_btn = QPushButton("\u2715")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(f"background: transparent; border: none; color: {c.accent_red}; font-size: 14px;")
        del_btn.clicked.connect(self._delete)
        layout.addWidget(del_btn)

    def _toggle_done(self, state):
        try:
            task_repo.toggle_done(self.task.id)
            self.toggled.emit()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "خطا", str(e))

    def _delete(self):
        if confirm_delete(self, noun="کار", name=self.task.title):
            try:
                task_repo.delete(self.task.id)
                self.deleted.emit()
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "خطا", str(e))


class TasksPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("کارهای روزانه")
        title.setStyleSheet(Styles.title_label())
        header.addWidget(title)
        header.addStretch()

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(Styles.subtitle_label())
        header.addWidget(self.stats_label)

        add_btn = QPushButton("+ کار جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_task)
        header.addWidget(add_btn)

        layout.addLayout(header)

        self.pending_label = QLabel("انجام نشده")
        self.pending_label.setStyleSheet(Styles.section_title_label())
        layout.addWidget(self.pending_label)

        self.pending_layout = QVBoxLayout()
        self.pending_layout.setSpacing(6)
        layout.addLayout(self.pending_layout)

        self.done_label = QLabel("انجام شده")
        self.done_label.setStyleSheet(Styles.muted_label())
        layout.addWidget(self.done_label)

        self.done_layout = QVBoxLayout()
        self.done_layout.setSpacing(6)
        layout.addLayout(self.done_layout)

        layout.addStretch()

    def _add_task(self):
        dlg = TaskDialog(self)
        dlg.task_saved.connect(self.refresh)
        dlg.exec()

    def refresh(self):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")

        self.pending_label.setStyleSheet(Styles.section_title_label())
        self.done_label.setStyleSheet(Styles.muted_label())

        while self.pending_layout.count():
            item = self.pending_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self.done_layout.count():
            item = self.done_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = task_repo.get_statistics()
        self.stats_label.setText(f"انجام شده: {stats['done']} / {stats['total']}")

        pending = task_repo.get_pending()
        done_tasks = [t for t in task_repo.get_all() if t.is_done]

        if not pending:
            empty = QLabel("هیچ کاری ندارید")
            empty.setStyleSheet(f"color: {c.fg_muted}; font-size: 13px; padding: 16px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pending_layout.addWidget(empty)
        else:
            for task in pending:
                row = TaskRow(task)
                row.toggled.connect(self.refresh)
                row.deleted.connect(self.refresh)
                self.pending_layout.addWidget(row)

        for task in done_tasks[:10]:
            row = TaskRow(task)
            row.toggled.connect(self.refresh)
            row.deleted.connect(self.refresh)
            self.done_layout.addWidget(row)