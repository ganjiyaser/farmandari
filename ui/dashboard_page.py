from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QFrame
)
from PyQt5.QtCore import Qt
from qfluentwidgets import (
    TitleLabel, SubtitleLabel, StrongBodyLabel, BodyLabel,
    ElevatedCardWidget, PrimaryPushButton, FluentIcon as FIF,
    setFont
)
from ui.styles import get_font, FONT_CSS, alpha
from ui.theme import theme_manager
from services.repositories import contact_repo, calendar_repo, task_repo
import jdatetime


class StatCard(ElevatedCardWidget):
    def __init__(self, title, value, icon_char, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(108)
        c = theme_manager.current

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        lbl_title = BodyLabel(title)
        lbl_title.setStyleSheet(f"color: {c.fg_muted}; background: transparent; border: none;")
        text_col.addWidget(lbl_title)

        self.value_label = StrongBodyLabel(str(value))
        setFont(self.value_label, 26)
        self.value_label.setStyleSheet(
            f"color: {c.fg_default}; background: transparent; border: none; font-weight: 700;"
        )
        text_col.addWidget(self.value_label)
        text_col.addStretch()
        layout.addLayout(text_col, 1)

        icon_lbl = QLabel(icon_char)
        icon_lbl.setFixedSize(48, 48)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            background-color: {alpha(color, 0x22)};
            color: {color};
            border-radius: 12px;
            font-size: 22px;
            border: none;
        """)
        layout.addWidget(icon_lbl)

        # accent bar via stylesheet on card
        self.setStyleSheet(f"""
            ElevatedCardWidget {{
                border-top: 3px solid {color};
            }}
        """)

    def set_value(self, value):
        self.value_label.setText(str(value))


class ListRow(QFrame):
    def __init__(self, icon, title, detail, meta, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        c = theme_manager.current
        self.setStyleSheet(f"""
            ListRow {{
                background: transparent;
                border-bottom: 1px solid {c.border_default};
                border-radius: 0;
            }}
            ListRow:hover {{
                background: {c.canvas_subtle};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(12)

        dot = QLabel(icon)
        dot.setFixedSize(34, 34)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setStyleSheet(f"""
            background: {alpha(color, 0x20)};
            border-radius: 17px;
            font-size: 14px;
            border: none;
        """)
        layout.addWidget(dot)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        t = StrongBodyLabel(title)
        t.setStyleSheet(f"color: {c.fg_default}; background: transparent; border: none;")
        text_col.addWidget(t)
        d = BodyLabel((detail or "")[:80])
        d.setStyleSheet(f"color: {c.fg_muted}; background: transparent; border: none; font-size: 11px;")
        text_col.addWidget(d)
        layout.addLayout(text_col, 1)

        if meta:
            m = BodyLabel(str(meta))
            m.setStyleSheet(f"color: {c.fg_muted}; background: transparent; border: none; font-size: 11px;")
            layout.addWidget(m)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title = TitleLabel("داشبورد")
        header.addWidget(title)
        header.addStretch()
        self.date_lbl = SubtitleLabel("")
        header.addWidget(self.date_lbl)
        layout.addLayout(header)

        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(14)
        layout.addLayout(self.stats_grid)

        sections = QHBoxLayout()
        sections.setSpacing(16)

        # Meetings card
        self.meetings_card = ElevatedCardWidget()
        meet_l = QVBoxLayout(self.meetings_card)
        meet_l.setContentsMargins(16, 14, 16, 14)
        meet_l.setSpacing(8)
        meet_l.addWidget(StrongBodyLabel("جلسات امروز"))
        self.meetings_box = QVBoxLayout()
        self.meetings_box.setSpacing(2)
        meet_l.addLayout(self.meetings_box)
        meet_l.addStretch()
        sections.addWidget(self.meetings_card, 1)

        # Tasks card
        self.tasks_card = ElevatedCardWidget()
        task_l = QVBoxLayout(self.tasks_card)
        task_l.setContentsMargins(16, 14, 16, 14)
        task_l.setSpacing(8)
        task_l.addWidget(StrongBodyLabel("کارهای باز"))
        self.tasks_box = QVBoxLayout()
        self.tasks_box.setSpacing(2)
        task_l.addLayout(self.tasks_box)
        task_l.addStretch()
        sections.addWidget(self.tasks_card, 1)

        layout.addLayout(sections, 1)

        # Activity
        self.activity_card = ElevatedCardWidget()
        act_l = QVBoxLayout(self.activity_card)
        act_l.setContentsMargins(16, 14, 16, 14)
        act_l.setSpacing(8)
        act_l.addWidget(StrongBodyLabel("خلاصه وضعیت"))
        self.activity_box = QVBoxLayout()
        self.activity_box.setSpacing(2)
        act_l.addLayout(self.activity_box)
        layout.addWidget(self.activity_card)

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self):
        c = theme_manager.current
        self.setStyleSheet(f"background-color: {c.canvas_default};")

        today = jdatetime.date.today().strftime("%A  %Y/%m/%d")
        self.date_lbl.setText(today)

        self._clear_layout(self.stats_grid)
        self._clear_layout(self.meetings_box)
        self._clear_layout(self.tasks_box)
        self._clear_layout(self.activity_box)

        contact_count = contact_repo.count()
        today_str = jdatetime.date.today().strftime("%Y/%m/%d")

        try:
            events = calendar_repo.get_by_date(today_str)
        except Exception:
            events = []

        try:
            stats = task_repo.get_statistics()
        except Exception:
            stats = {"total": 0, "done": 0, "pending": 0}

        cards = [
            ("مخاطبین", contact_count, "👤", c.accent_blue),
            ("جلسات امروز", len(events), "📅", c.accent_orange),
            ("کارهای باز", stats.get("pending", 0), "☑", c.accent_green),
        ]
        for i, (title, value, icon, color) in enumerate(cards):
            self.stats_grid.addWidget(StatCard(title, value, icon, color), 0, i)

        if events:
            for ev in events[:6]:
                color = c.accent_red if getattr(ev.priority, "value", "") == "high" else c.accent_blue
                self.meetings_box.addWidget(
                    ListRow("📅", ev.title, ev.location or (ev.description or ""), ev.event_time or "", color)
                )
        else:
            empty = BodyLabel("جلسه‌ای برای امروز ثبت نشده است")
            empty.setStyleSheet(f"color: {c.fg_muted}; padding: 12px;")
            self.meetings_box.addWidget(empty)

        try:
            pending_tasks = task_repo.get_pending()
        except Exception:
            pending_tasks = []

        if pending_tasks:
            for task in pending_tasks[:6]:
                pcolor = {
                    "high": c.accent_red,
                    "medium": c.accent_orange,
                    "low": c.accent_green,
                }.get(task.priority, c.accent_orange)
                self.tasks_box.addWidget(
                    ListRow("☐", task.title, task.description or "", task.due_date or "", pcolor)
                )
        else:
            empty = BodyLabel("کار بازی ندارید — عالی است!")
            empty.setStyleSheet(f"color: {c.fg_muted}; padding: 12px;")
            self.tasks_box.addWidget(empty)

        summary = [
            ("👤", f"{contact_count} مخاطب", "دفترچه تلفن", c.accent_blue),
            ("✓", f"{stats.get('done', 0)} / {stats.get('total', 0)} کار", "انجام‌شده از کل", c.accent_green),
        ]
        for icon, title, detail, color in summary:
            self.activity_box.addWidget(ListRow(icon, title, detail, "", color))
