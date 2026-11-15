"""صفحهٔ صورت‌جلسه و مصوبات با پیگیری اجرا."""

from datetime import datetime

import jdatetime
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QDialog, QComboBox, QMessageBox, QFrame, QTabWidget,
    QScrollArea, QGridLayout
)

from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import (
    decision_repo, minute_repo, calendar_repo, official_repo, contact_repo
)
from models.models import DecisionStatus, Decision

DECISION_STATUS_LABELS = {
    DecisionStatus.OPEN: "باز",
    DecisionStatus.IN_PROGRESS: "در حال اجرا",
    DecisionStatus.DONE: "انجام شد",
    DecisionStatus.CANCELLED: "لغو شد",
}

STATUS_COLORS = {
    DecisionStatus.OPEN: "#F57F17",
    DecisionStatus.IN_PROGRESS: "#1565C0",
    DecisionStatus.DONE: "#2E7D32",
    DecisionStatus.CANCELLED: "#9E9E9E",
}

EVENT_WINDOW_DAYS_BACK = 120
EVENT_WINDOW_DAYS_FORWARD = 180


def today_jalali() -> str:
    return jdatetime.date.today().strftime("%Y/%m/%d")


def _related(obj, attr):
    try:
        return list(getattr(obj, attr) or [])
    except Exception:
        return []


def _event_options(extra_ids=()):
    """جلسات پنجرهٔ زمانی فعلی؛ جلسات اضافی (مثل جلسهٔ مصوبهٔ قدیمی) هم اضافه می‌شوند."""
    today = jdatetime.date.today()
    start = (today - jdatetime.timedelta(days=EVENT_WINDOW_DAYS_BACK)).strftime("%Y/%m/%d")
    end = (today + jdatetime.timedelta(days=EVENT_WINDOW_DAYS_FORWARD)).strftime("%Y/%m/%d")
    events = calendar_repo.get_range(start, end)
    have = {e.id for e in events}
    for eid in extra_ids:
        if eid and eid not in have:
            ev = calendar_repo.get_by_id(eid)
            if ev:
                events.append(ev)
    events.sort(key=lambda e: (e.event_date or ""), reverse=True)
    return events


def _event_label(event) -> str:
    return f"{event.event_date or '—'} — {event.title}"


class DecisionDialog(QDialog):
    decision_saved = pyqtSignal()

    def __init__(self, parent=None, decision_id=None, event_id=None):
        super().__init__(parent)
        self.decision_id = decision_id
        self.decision = decision_repo.get_by_id(decision_id) if decision_id else None
        self.preset_event_id = event_id
        self.setWindowTitle("ویرایش مصوبه" if decision_id else "مصوبهٔ جدید")
        self.setMinimumWidth(520)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.decision:
            self._load()
        elif event_id:
            idx = self.event_combo.findData(event_id)
            if idx >= 0:
                self.event_combo.setCurrentIndex(idx)

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.canvas_overlay}; }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {c.fg_default};
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border: 2px solid {c.input_border_hover};
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.canvas_overlay};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                selection-background-color: {c.accent_blue};
                selection-color: white;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl = QLabel("جلسهٔ مربوطه")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(lbl)
        self.event_combo = QComboBox()
        for ev in _event_options(extra_ids=[self.decision.event_id] if self.decision else [self.preset_event_id]):
            self.event_combo.addItem(_event_label(ev), ev.id)
        layout.addWidget(self.event_combo)

        lbl = QLabel("متن مصوبه")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(lbl)
        self.content = QTextEdit()
        self.content.setPlaceholderText("چه چیزی مصوب شد؟")
        self.content.setMaximumHeight(90)
        layout.addWidget(self.content)

        lbl = QLabel("مسئول اجرا")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(lbl)
        self.assignee_combo = QComboBox()
        self.assignee_combo.addItem("— انتخاب کنید —", None)
        for o in official_repo.get_active():
            self.assignee_combo.addItem(f"{o.display_name} (مسئول)", ("official", o.id))
        for ct in contact_repo.get_all(limit=500):
            self.assignee_combo.addItem(f"{ct.display_name} (مخاطب)", ("contact", ct.id))
        layout.addWidget(self.assignee_combo)

        self.assignee_text = QLineEdit()
        self.assignee_text.setPlaceholderText("یا عنوان آزاد؛ مثال: واحد مالی")
        layout.addWidget(self.assignee_text)

        row = QHBoxLayout()
        col1 = QVBoxLayout()
        lbl = QLabel("مهلت (شمسی)")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        col1.addWidget(lbl)
        self.due_input = QLineEdit()
        self.due_input.setPlaceholderText(today_jalali())
        self.due_input.setFixedWidth(150)
        col1.addWidget(self.due_input)
        row.addLayout(col1)

        col2 = QVBoxLayout()
        lbl = QLabel("وضعیت")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        col2.addWidget(lbl)
        self.status_combo = QComboBox()
        for st, label in DECISION_STATUS_LABELS.items():
            self.status_combo.addItem(label, st)
        col2.addWidget(self.status_combo)
        row.addLayout(col2)
        row.addStretch()
        layout.addLayout(row)

        lbl = QLabel("یادداشت پیگیری (اختیاری)")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        layout.addWidget(lbl)
        self.followup = QTextEdit()
        self.followup.setMaximumHeight(70)
        layout.addWidget(self.followup)

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

    def _load(self):
        d = self.decision
        idx = self.event_combo.findData(d.event_id)
        if idx >= 0:
            self.event_combo.setCurrentIndex(idx)
        self.content.setPlainText(d.content or "")
        for value in (("official", d.assignee_official_id) if d.assignee_official_id else
                      ("contact", d.assignee_contact_id) if d.assignee_contact_id else None):
            for i in range(1, self.assignee_combo.count()):
                if self.assignee_combo.itemData(i) == value:
                    self.assignee_combo.setCurrentIndex(i)
                    break
        if d.assignee_official_id is None and d.assignee_contact_id is None:
            self.assignee_text.setText(d.assignee_text or "")
        self.due_input.setText(d.due_date or "")
        sidx = list(DECISION_STATUS_LABELS.keys()).index(d.status) if d.status else 0
        self.status_combo.setCurrentIndex(sidx)
        self.followup.setPlainText(d.followup_note or "")

    def _save(self):
        if self.event_combo.count() == 0 or self.event_combo.currentData() is None:
            QMessageBox.warning(self, "خطا", "جلسهٔ مربوطه را انتخاب کنید")
            return
        content = self.content.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "خطا", "متن مصوبه را وارد کنید")
            return

        due = self.due_input.text().strip() or None
        if due:
            parts = due.split("/")
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                try:
                    jdatetime.date(y, m, d)
                    due = f"{y:04d}/{m:02d}/{d:02d}"
                except (ValueError, TypeError):
                    QMessageBox.warning(self, "خطا", "تاریخ نامعتبر است. قالب: 1404/07/29")
                    return
            else:
                QMessageBox.warning(self, "خطا", "قالب تاریخ صحیح نیست. مثال: 1404/07/29")
                return

        assignee = self.assignee_combo.currentData()
        assignee_text = self.assignee_text.text().strip() or None
        data = {
            "event_id": self.event_combo.currentData(),
            "content": content,
            "assignee_official_id": assignee[1] if assignee and assignee[0] == "official" else None,
            "assignee_contact_id": assignee[1] if assignee and assignee[0] == "contact" else None,
            "assignee_text": assignee_text if not assignee else None,
            "due_date": due,
            "status": self.status_combo.currentData(),
            "followup_note": self.followup.toPlainText().strip() or None,
        }
        if data["status"] == DecisionStatus.DONE:
            data["completed_at"] = datetime.now()

        try:
            if self.decision_id:
                decision_repo.update(self.decision_id, **data)
            else:
                decision_repo.create(**data)
        except Exception as e:
            QMessageBox.critical(self, "خطا در ذخیره", str(e))
            return
        self.decision_saved.emit()
        self.accept()


class DecisionRow(QFrame):
    changed = pyqtSignal()
    deleted = pyqtSignal()

    def __init__(self, decision, parent=None):
        super().__init__(parent)
        self.decision = decision
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        d = self.decision
        status = d.status
        color = STATUS_COLORS.get(status, "#888888")
        overdue = (status in (DecisionStatus.OPEN, DecisionStatus.IN_PROGRESS)
                   and d.due_date and d.due_date < today_jalali())

        self.setStyleSheet(f"""
            DecisionRow {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-right: 4px solid {color};
                border-radius: 8px;
            }}
            DecisionRow:hover {{ background-color: {c.canvas_subtle}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        info = QVBoxLayout()
        info.setSpacing(3)

        content = QLabel(d.content)
        content.setWordWrap(True)
        content.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c.fg_default};")
        info.addWidget(content)

        sub_parts = []
        try:
            if d.event is not None:
                sub_parts.append(f"جلسه: {_event_label(d.event)}")
        except Exception:
            pass
        sub_parts.append(f"مسئول: {d.assignee_name}")
        if d.due_date:
            sub_parts.append(f"مهلت: {d.due_date}")
        actions = _related(d, "actions")
        if actions:
            sub_parts.append(f"اقدامات: {len(actions)}")
        if d.result:
            sub_parts.append(f"نتیجه: {d.result[:80]}")
        sub = QLabel(" — ".join(sub_parts))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
        info.addWidget(sub)

        if d.followup_note:
            note = QLabel(f"پیگیری: {d.followup_note}")
            note.setWordWrap(True)
            note.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
            info.addWidget(note)

        layout.addLayout(info, 1)

        if overdue:
            badge = QLabel("عقب‌افتاده")
            badge.setStyleSheet(f"color: {c.accent_red}; font-size: 11px; font-weight: bold;")
            layout.addWidget(badge)

        chip = QLabel(DECISION_STATUS_LABELS.get(status, str(status)))
        chip.setStyleSheet(f"""
            color: white; background-color: {color}; border-radius: 12px;
            padding: 5px 12px; font-size: 11px; font-weight: bold;
        """)
        layout.addWidget(chip)

        if status in (DecisionStatus.OPEN, DecisionStatus.IN_PROGRESS):
            done_btn = QPushButton("انجام شد")
            done_btn.setFixedHeight(28)
            done_btn.setStyleSheet(Styles.table_action_button("primary"))
            done_btn.clicked.connect(lambda: self._set_status(DecisionStatus.DONE))
            layout.addWidget(done_btn)

            start_btn = QPushButton("شروع")
            start_btn.setFixedHeight(28)
            start_btn.setStyleSheet(Styles.table_action_button("neutral"))
            start_btn.clicked.connect(lambda: self._set_status(DecisionStatus.IN_PROGRESS))
            layout.addWidget(start_btn)

        track_btn = QPushButton("پیگیری")
        track_btn.setFixedHeight(28)
        track_btn.setStyleSheet(Styles.table_action_button("primary"))
        track_btn.clicked.connect(self._track)
        layout.addWidget(track_btn)

        edit_btn = QPushButton("ویرایش")
        edit_btn.setFixedHeight(28)
        edit_btn.setStyleSheet(Styles.secondary_button())
        edit_btn.clicked.connect(self._edit)
        layout.addWidget(edit_btn)

        del_btn = QPushButton("حذف")
        del_btn.setFixedHeight(28)
        del_btn.setStyleSheet(Styles.table_action_button("danger"))
        del_btn.clicked.connect(self._delete)
        layout.addWidget(del_btn)

    def _set_status(self, status):
        data = {"status": status}
        if status == DecisionStatus.DONE:
            data["completed_at"] = datetime.now()
        try:
            decision_repo.update(self.decision.id, **data)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self.changed.emit()

    def _track(self):
        from ui.tracking_dialog import DecisionTrackingDialog
        dlg = DecisionTrackingDialog(self.window(), decision_id=self.decision.id)
        dlg.exec()
        self.changed.emit()

    def _edit(self):
        dlg = DecisionDialog(self.window(), decision_id=self.decision.id)
        dlg.decision_saved.connect(self.changed.emit)
        dlg.exec()

    def _delete(self):
        if confirm_delete(self, noun="مصوبه", name=self.decision.content[:40]):
            try:
                decision_repo.delete(self.decision.id)
                self.deleted.emit()
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))


class DecisionsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout.addWidget(self.tabs)

        # ---------- تب مصوبات ----------
        decisions_tab = QWidget()
        d_layout = QVBoxLayout(decisions_tab)
        d_layout.setContentsMargins(4, 12, 4, 4)
        d_layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("مصوبات جلسات")
        title.setStyleSheet(Styles.title_label())
        header.addWidget(title)
        header.addStretch()

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(Styles.subtitle_label())
        header.addWidget(self.stats_label)

        self.filter_combo = QComboBox()
        self.filter_combo.setFixedWidth(180)
        self.filter_combo.addItems([
            "همه", "باز", "در حال اجرا", "انجام شده", "لغو شده", "عقب‌افتاده",
        ])
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.filter_combo)

        self.report_btn = QPushButton("گزارش اقدامات (چاپ)")
        self.report_btn.setStyleSheet(Styles.secondary_button())
        self.report_btn.clicked.connect(self._print_report)
        header.addWidget(self.report_btn)

        add_btn = QPushButton("+ مصوبهٔ جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_decision)
        header.addWidget(add_btn)

        d_layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.list_host)
        d_layout.addWidget(self.scroll, 1)

        self.tabs.addTab(decisions_tab, "مصوبات")

        # ---------- تب صورت‌جلسه ----------
        minutes_tab = QWidget()
        m_layout = QVBoxLayout(minutes_tab)
        m_layout.setContentsMargins(4, 12, 4, 4)
        m_layout.setSpacing(12)

        row = QHBoxLayout()
        lbl = QLabel("جلسه:")
        lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
        row.addWidget(lbl)
        self.event_combo = QComboBox()
        self.event_combo.setMinimumWidth(320)
        self.event_combo.currentIndexChanged.connect(self._on_event_selected)
        row.addWidget(self.event_combo)
        row.addStretch()

        self.print_minute_btn = QPushButton("چاپ صورت‌جلسه")
        self.print_minute_btn.setStyleSheet(Styles.secondary_button())
        self.print_minute_btn.clicked.connect(self._print_minute)
        row.addWidget(self.print_minute_btn)

        m_layout.addLayout(row)

        self.minute_edit = QTextEdit()
        self.minute_edit.setPlaceholderText(
            "صورت‌جلسه را اینجا بنویسید: حاضرین، موضوعات مطرح‌شده، تصمیمات و ...")
        m_layout.addWidget(self.minute_edit, 1)

        m_btn_row = QHBoxLayout()
        m_btn_row.addStretch()
        save_minute_btn = QPushButton("ذخیره صورت‌جلسه")
        save_minute_btn.setStyleSheet(Styles.primary_button())
        save_minute_btn.clicked.connect(self._save_minute)
        m_btn_row.addWidget(save_minute_btn)
        m_layout.addLayout(m_btn_row)

        self.event_decisions_label = QLabel()
        self.event_decisions_label.setWordWrap(True)
        self.event_decisions_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px;")
        m_layout.addWidget(self.event_decisions_label)

        self.tabs.addTab(minutes_tab, "صورت‌جلسه")

    # ---------------- مصوبات ----------------
    def _add_decision(self):
        dlg = DecisionDialog(self, event_id=self.event_combo.currentData())
        dlg.decision_saved.connect(self.refresh)
        dlg.exec()

    def _print_report(self):
        rows = getattr(self, "_last_rows", [])
        if not rows:
            QMessageBox.information(self, "گزارش اقدامات", "مصوبه‌ای برای گزارش وجود ندارد.")
            return
        from ui.program_print import (
            build_decisions_actions_report_html, print_document,
        )
        html = build_decisions_actions_report_html(rows)
        print_document(self, "گزارش اقدامات مصوبات", html)

    def refresh(self, *_):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = decision_repo.get_statistics()
        self.stats_label.setText(
            f"باز: {stats['open']} • در حال اجرا: {stats['in_progress']} • "
            f"عقب‌افتاده: {stats['overdue']} • جمع: {stats['total']}"
        )

        index = self.filter_combo.currentIndex()
        if index == 1:
            rows = decision_repo.get_filtered(status=DecisionStatus.OPEN)
        elif index == 2:
            rows = decision_repo.get_filtered(status=DecisionStatus.IN_PROGRESS)
        elif index == 3:
            rows = decision_repo.get_filtered(status=DecisionStatus.DONE)
        elif index == 4:
            rows = decision_repo.get_filtered(status=DecisionStatus.CANCELLED)
        elif index == 5:
            rows = [d for d in decision_repo.get_open_with_event()
                    if d.due_date and d.due_date < today_jalali()]
        else:
            rows = decision_repo.get_filtered()

        self._last_rows = rows
        if not rows:
            empty = QLabel("مصوبه‌ای ثبت نشده است")
            empty.setStyleSheet(f"color: {c.fg_muted}; font-size: 13px; padding: 24px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_layout.addWidget(empty)

        for d in rows:
            row = DecisionRow(d)
            row.changed.connect(self.refresh)
            row.deleted.connect(self.refresh)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch()

        self._fill_event_combo()

    # ---------------- صورت‌جلسه ----------------
    def _fill_event_combo(self):
        current = self.event_combo.currentData()
        self.event_combo.blockSignals(True)
        self.event_combo.clear()
        for ev in _event_options():
            self.event_combo.addItem(_event_label(ev), ev.id)
        if current is not None:
            idx = self.event_combo.findData(current)
            if idx >= 0:
                self.event_combo.setCurrentIndex(idx)
        self.event_combo.blockSignals(False)
        if self.event_combo.currentIndex() < 0 and self.event_combo.count():
            self.event_combo.setCurrentIndex(0)
        self._on_event_selected()

    def _current_event_id(self):
        return self.event_combo.currentData()

    def _on_event_selected(self, *_):
        event_id = self._current_event_id()
        if not event_id:
            self.minute_edit.clear()
            self.event_decisions_label.setText("")
            return
        minute = minute_repo.get_by_event(event_id)
        self.minute_edit.setPlainText(minute.content if minute else "")
        decisions = decision_repo.get_by_event(event_id)
        if decisions:
            parts = [f"{i+1}. {d.content} ({DECISION_STATUS_LABELS.get(d.status, '')})"
                     for i, d in enumerate(decisions)]
            self.event_decisions_label.setText("مصوبات این جلسه:\n" + "\n".join(parts))
        else:
            self.event_decisions_label.setText("برای این جلسه مصوبه‌ای ثبت نشده است.")

    def _save_minute(self):
        event_id = self._current_event_id()
        if not event_id:
            QMessageBox.warning(self, "خطا", "ابتدا جلسه را انتخاب کنید")
            return
        content = self.minute_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "خطا", "متن صورت‌جلسه خالی است")
            return
        row = minute_repo.upsert(event_id, content)
        if row is None:
            QMessageBox.critical(self, "خطا", "ذخیرهٔ صورت‌جلسه انجام نشد")
            return
        QMessageBox.information(self, "موفق", "صورت‌جلسه ذخیره شد")

    def _print_minute(self):
        event_id = self._current_event_id()
        if not event_id:
            QMessageBox.warning(self, "خطا", "ابتدا جلسه را انتخاب کنید")
            return
        content = self.minute_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "خطا", "صورت‌جلسه خالی است")
            return
        from ui.program_print import build_minute_html, print_document
        idx = self.event_combo.currentIndex()
        title = self.event_combo.itemText(idx) if idx >= 0 else ""
        decisions = [
            (d.content, d.assignee_name, d.due_date,
             DECISION_STATUS_LABELS.get(d.status, ""))
            for d in decision_repo.get_by_event(event_id)
        ]
        print_document(self, "صورت‌جلسه", build_minute_html(title, content, decisions))
