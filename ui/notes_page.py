from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QDialog, QFrame, QGridLayout,
    QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import note_repo


class NoteDialog(QDialog):
    note_saved = pyqtSignal()

    def __init__(self, parent=None, note=None):
        super().__init__(parent)
        self.note = note
        self.setWindowTitle("یادداشت جدید" if not note else "ویرایش یادداشت")
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)
        self.setFont(get_font(10))
        self._setup_ui()
        if note:
            self.title_input.setText(note.title or "")
            self.content_input.setText(note.content or "")

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
            QPushButton {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title_label = QLabel("عنوان")
        title_label.setStyleSheet(f"color: {c.fg_default}; font-weight: bold; font-size: 13px;")
        layout.addWidget(title_label)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("عنوان یادداشت...")
        layout.addWidget(self.title_input)

        content_label = QLabel("متن")
        content_label.setStyleSheet(f"color: {c.fg_default}; font-weight: bold; font-size: 13px;")
        layout.addWidget(content_label)

        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("متن یادداشت...")
        layout.addWidget(self.content_input)

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
            QMessageBox.warning(self, "خطا", "عنوان را وارد کنید")
            return

        content = self.content_input.toPlainText().strip()

        try:
            if self.note:
                # Persist the update to the repository
                note_repo.update(
                    self.note.id,
                    title=title,
                    content=content,
                )
            else:
                note_repo.create(title=title, content=content)

            self.note_saved.emit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ذخیره یادداشت:\n{e}")


class NoteCard(QFrame):
    edit_requested = pyqtSignal(object)
    deleted = pyqtSignal()
    pin_toggled = pyqtSignal()

    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note = note
        self.setFixedHeight(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        color = getattr(self.note, "color", None) or c.primary

        self.setStyleSheet(f"""
            NoteCard {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 10px;
                border-top: 3px solid {color};
            }}
            NoteCard:hover {{
                border: 1px solid {c.primary};
                background-color: {c.canvas_subtle};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        pin_prefix = "📌 " if getattr(self.note, "is_pinned", False) else ""
        title = QLabel(f"{pin_prefix}{self.note.title}")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {c.fg_default};")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        layout.addLayout(header)

        content = QLabel((self.note.content or "")[:120])
        content.setStyleSheet(f"font-size: 12px; color: {c.fg_muted};")
        content.setWordWrap(True)
        layout.addWidget(content, 1)

        footer = QHBoxLayout()
        footer.addStretch()

        pin_btn = QPushButton("📌" if getattr(self.note, "is_pinned", False) else "📍")
        pin_btn.setFixedSize(28, 28)
        pin_btn.setStyleSheet(
            f"background: transparent; border: none; color: {c.accent_orange}; font-size: 14px;"
        )
        pin_btn.setToolTip("سنجاق / برداشتن سنجاق")
        pin_btn.clicked.connect(self._toggle_pin)
        footer.addWidget(pin_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(
            f"background: transparent; border: none; color: {c.accent_red}; font-size: 14px;"
        )
        del_btn.setToolTip("حذف")
        del_btn.clicked.connect(self._delete)
        footer.addWidget(del_btn)

        layout.addLayout(footer)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Ignore clicks on the action buttons (they handle themselves)
            child = self.childAt(event.pos())
            if child is None or not isinstance(child, QPushButton):
                self.edit_requested.emit(self.note)
        super().mousePressEvent(event)

    def _toggle_pin(self):
        try:
            note_repo.toggle_pin(self.note.id)
            self.pin_toggled.emit()
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _delete(self):
        if confirm_delete(self, noun="یادداشت", name=self.note.title):
            try:
                note_repo.delete(self.note.id)
                self.deleted.emit()
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))


class NotesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("یادداشت‌ها")
        title.setStyleSheet(Styles.title_label())
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجوی یادداشت...")
        self.search_input.setFixedWidth(280)
        self.search_input.setStyleSheet(Styles.line_edit())
        # Debounce: each keystroke re-queried the DB and rebuilt the card grid.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(
            lambda: self.refresh(self.search_input.text())
        )
        self.search_input.textChanged.connect(self._filter)
        header.addWidget(self.search_input)

        add_btn = QPushButton("+ یادداشت جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_note)
        header.addWidget(add_btn)

        layout.addLayout(header)

        self.grid = QGridLayout()
        self.grid.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_content.setLayout(self.grid)
        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll, 1)

        self.notes_area = scroll

    def _add_note(self):
        dlg = NoteDialog(self)
        dlg.note_saved.connect(self.refresh)
        dlg.exec()

    def _filter(self, text):
        if not text:
            # Clearing the box restores everything immediately.
            self._search_timer.stop()
            self.refresh()
            return
        self._search_timer.start()

    def refresh(self, search_text=None):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")

        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            if search_text and len(search_text.strip()) >= 2:
                notes = note_repo.search(search_text.strip())
            else:
                notes = note_repo.get_all()
        except Exception:
            notes = []

        if not notes:
            empty = QLabel("یادداشتی وجود ندارد")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {c.fg_muted}; font-size: 14px; padding: 40px;")
            self.grid.addWidget(empty, 0, 0, 1, 3)
            return

        cols = 3
        for i, note in enumerate(notes):
            card = NoteCard(note)
            card.edit_requested.connect(self._edit_note)
            card.deleted.connect(self.refresh)
            card.pin_toggled.connect(self.refresh)
            row, col = divmod(i, cols)
            self.grid.addWidget(card, row, col)

    def _edit_note(self, note):
        dlg = NoteDialog(self, note=note)
        dlg.note_saved.connect(self.refresh)
        dlg.exec()
