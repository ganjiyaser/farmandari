from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QPushButton
)
from PyQt6.QtCore import Qt, QTimer
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from services.repositories import (
    contact_repo, calendar_repo,
    group_repo, note_repo, task_repo
)


class SearchResult(QFrame):
    def __init__(self, title, subtitle, category, icon, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        c = theme_manager.current

        self.setStyleSheet(f"""
            SearchResult {{
                background: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: 8px;
                padding: 0px;
            }}
            SearchResult:hover {{
                background: {c.canvas_subtle};
                border: 1px solid {c.primary};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            background: {c.canvas_inset};
            border-radius: 8px;
            font-size: 18px;
        """)
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {c.fg_default}; border: none;")
        text_col.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle[:100])
        sub_lbl.setStyleSheet(f"font-size: 11px; color: {c.fg_muted}; border: none;")
        text_col.addWidget(sub_lbl)

        layout.addLayout(text_col, 1)

        cat_lbl = QLabel(category)
        cat_lbl.setStyleSheet(f"""
            font-size: 11px;
            color: {c.fg_muted};
            background: {c.canvas_inset};
            padding: 3px 8px;
            border-radius: 4px;
            border: none;
        """)
        layout.addWidget(cat_lbl)


class SearchDialog(QDialog):
    def __init__(self, parent=None, query=""):
        super().__init__(parent)
        self.query = query
        self.setWindowTitle(f"نتایج جستجو: {query}")
        self.setMinimumSize(650, 520)
        self.setFont(get_font(10))
        self._setup_ui()
        self._search(query)

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.canvas_default};
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
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجو در همه بخش\u200cها...")
        # Debounce: a single keystroke used to fire five DB queries at once and
        # rebuild the whole result list, in this case freezing the dialog.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._search)
        self.search_input.setText(self.query)
        self.search_input.textChanged.connect(lambda *_: self._search_timer.start())
        layout.addWidget(self.search_input)

        self.count_label = QLabel()
        self.count_label.setStyleSheet(f"font-size: 12px; color: {c.fg_muted}; border: none;")
        layout.addWidget(self.count_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.results_container = QFrame()
        self.results_container.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(6)
        self.results_layout.addStretch()
        scroll.setWidget(self.results_container)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton("بستن")
        close_btn.setStyleSheet(Styles.secondary_button())
        close_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _search(self, text=None):
        if text is None:
            text = self.search_input.text()
        c = theme_manager.current

        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if len(text) < 2:
            self.count_label.setText("حداقل ۲ کاراکتر وارد کنید")
            return

        results = []

        contacts = contact_repo.search(text)
        for ct in contacts[:10]:
            title = ct.first_name + " " + (ct.last_name or "")
            results.append((title, ct.phone or "", "مخاطبین", "\U0001F464"))

        try:
            events = calendar_repo.search(text)
            for ev in events[:10]:
                results.append((ev.title, ev.event_date or "", "تقویم", "\U0001F4C5"))
        except Exception:
            pass

        groups = group_repo.search(text)
        for g in groups[:10]:
            results.append((g.name, g.description or "", "گروه\u200cها", "\U0001F465"))

        try:
            notes = note_repo.search(text)
            for n in notes[:10]:
                results.append((n.title, (n.content or "")[:80], "یادداشت", "\U0001F4DD"))
        except Exception:
            pass

        self.count_label.setText(f"{len(results)} نتیجه یافت شد")

        if not results:
            empty = QLabel("نتیجه‌ای یافت نشد")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {c.input_placeholder}; font-size: 14px; padding: 40px; border: none;")
            self.results_layout.addWidget(empty)
            return

        for title, subtitle, category, icon in results:
            card = SearchResult(title, subtitle, category, icon)
            self.results_layout.addWidget(card)

        self.results_layout.addStretch()
