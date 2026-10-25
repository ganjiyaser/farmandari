"""دفتر اندیکاتور — ثبت و پیگیری نامه‌های ورودی (وارده) و صادره."""

import os

import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QDialog, QComboBox, QMessageBox, QFrame, QScrollArea,
    QFileDialog
)

from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import letter_repo
from models.models import LetterDirection, LetterStatus

DIRECTION_LABELS = {
    LetterDirection.INCOMING: "وارده",
    LetterDirection.OUTGOING: "صادره",
}

LETTER_STATUS_LABELS = {
    LetterStatus.REGISTERED: "ثبت‌شده",
    LetterStatus.IN_PROGRESS: "در حال پیگیری",
    LetterStatus.ANSWERED: "پاسخ داده شد",
    LetterStatus.ARCHIVED: "بایگانی",
}

STATUS_COLORS = {
    LetterStatus.REGISTERED: "#1565C0",
    LetterStatus.IN_PROGRESS: "#F57F17",
    LetterStatus.ANSWERED: "#2E7D32",
    LetterStatus.ARCHIVED: "#9E9E9E",
}

DIRECTION_COLORS = {
    LetterDirection.INCOMING: "#8250df",
    LetterDirection.OUTGOING: "#1a7f37",
}


def today_jalali() -> str:
    return jdatetime.date.today().strftime("%Y/%m/%d")


def _related(obj, attr):
    try:
        return list(getattr(obj, attr) or [])
    except Exception:
        return []


class LetterDialog(QDialog):
    letter_saved = pyqtSignal()

    def __init__(self, parent=None, letter_id=None):
        super().__init__(parent)
        self.letter_id = letter_id
        self.letter = letter_repo.get_by_id(letter_id) if letter_id else None
        self.setWindowTitle("ویرایش نامه" if letter_id else "نامهٔ جدید")
        self.setMinimumWidth(520)
        self.setFont(get_font(10))
        self._setup_ui()
        if self.letter:
            self._load()
        else:
            self._update_indicator_preview()
        self.direction_combo.currentIndexChanged.connect(self._update_indicator_preview)

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

        def field_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
            layout.addWidget(lbl)

        row = QHBoxLayout()
        col = QVBoxLayout()
        field_label("جهت نامه")
        self.direction_combo = QComboBox()
        for dr, label in DIRECTION_LABELS.items():
            self.direction_combo.addItem(label, dr)
        col.addWidget(self.direction_combo)
        row.addLayout(col, 1)

        col = QVBoxLayout()
        field_label("وضعیت")
        self.status_combo = QComboBox()
        for st, label in LETTER_STATUS_LABELS.items():
            self.status_combo.addItem(label, st)
        col.addWidget(self.status_combo)
        row.addLayout(col, 1)
        layout.addLayout(row)

        self.indicator_preview = QLabel()
        self.indicator_preview.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 11px; background: transparent;")
        layout.addWidget(self.indicator_preview)

        field_label("موضوع")
        self.subject = QLineEdit()
        self.subject.setPlaceholderText("موضوع نامه")
        layout.addWidget(self.subject)

        row2 = QHBoxLayout()
        col = QVBoxLayout()
        field_label("شمارهٔ روی نامه (اختیاری)")
        self.letter_number = QLineEdit()
        self.letter_number.setPlaceholderText("مثال: 1472/م/5")
        col.addWidget(self.letter_number)
        row2.addLayout(col, 1)

        col = QVBoxLayout()
        field_label("تاریخ نامه (شمسی)")
        self.letter_date = QLineEdit()
        self.letter_date.setPlaceholderText(today_jalali())
        self.letter_date.setFixedWidth(150)
        col.addWidget(self.letter_date)
        row2.addLayout(col, 1)
        layout.addLayout(row2)

        field_label("فرستنده (برای وارده)")
        self.sender = QLineEdit()
        layout.addWidget(self.sender)

        field_label("گیرنده (برای صادره)")
        self.receiver = QLineEdit()
        layout.addWidget(self.receiver)

        field_label("خلاصه نامه")
        self.summary = QTextEdit()
        self.summary.setMaximumHeight(80)
        layout.addWidget(self.summary)

        row3 = QHBoxLayout()
        col = QVBoxLayout()
        field_label("ارجاع به واحد / شخص")
        self.referral_to = QLineEdit()
        self.referral_to.setPlaceholderText("مثال: معاونت مالی")
        col.addWidget(self.referral_to)
        row3.addLayout(col, 1)
        layout.addLayout(row3)

        field_label("یادداشت ارجاع (اختیاری)")
        self.referral_note = QTextEdit()
        self.referral_note.setMaximumHeight(60)
        layout.addWidget(self.referral_note)

        field_label("فایل اسکن نامه (اختیاری)")
        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("مسیر فایل انتخاب نشده")
        file_row.addWidget(self.file_path_edit, 1)
        pick_btn = QPushButton("انتخاب فایل…")
        pick_btn.setStyleSheet(Styles.secondary_button())
        pick_btn.clicked.connect(self._pick_file)
        file_row.addWidget(pick_btn)
        layout.addLayout(file_row)

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

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل نامه")
        if path:
            self.file_path_edit.setText(path)

    def _update_indicator_preview(self, *_):
        direction = self.direction_combo.currentData()
        year = jdatetime.date.today().year
        nxt = letter_repo.next_indicator_number(direction, year)
        self.indicator_preview.setText(
            f"شمارهٔ اندیکاتور ثبت بعدی برای {DIRECTION_LABELS[direction]} سال {year}: {nxt}"
            " (به‌صورت خودکار اختصاص می‌یابد)")

    def _load(self):
        d = self.letter
        idx = list(DIRECTION_LABELS.keys()).index(d.direction) if d.direction else 0
        self.direction_combo.setCurrentIndex(idx)
        self.direction_combo.setEnabled(False)  # شماره اندیکاتور به جهت گره خورده
        sidx = list(LETTER_STATUS_LABELS.keys()).index(d.status) if d.status else 0
        self.status_combo.setCurrentIndex(sidx)
        self.subject.setText(d.subject or "")
        self.letter_number.setText(d.letter_number or "")
        self.letter_date.setText(d.letter_date or "")
        self.sender.setText(d.sender or "")
        self.receiver.setText(d.receiver or "")
        self.summary.setPlainText(d.summary or "")
        self.referral_to.setText(d.referral_to or "")
        self.referral_note.setPlainText(d.referral_note or "")
        self.file_path_edit.setText(d.file_path or "")

    def _save(self):
        subject = self.subject.text().strip()
        if not subject:
            QMessageBox.warning(self, "خطا", "موضوع نامه را وارد کنید")
            return

        letter_date = self.letter_date.text().strip() or None
        if letter_date:
            parts = letter_date.split("/")
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                y, m, dd = int(parts[0]), int(parts[1]), int(parts[2])
                try:
                    jdatetime.date(y, m, dd)
                    letter_date = f"{y:04d}/{m:02d}/{dd:02d}"
                except (ValueError, TypeError):
                    QMessageBox.warning(self, "خطا", "تاریخ نامعتبر است. قالب: 1404/07/29")
                    return
            else:
                QMessageBox.warning(self, "خطا", "قالب تاریخ صحیح نیست. مثال: 1404/07/29")
                return

        direction = self.direction_combo.currentData()
        data = {
            "direction": direction,
            "subject": subject,
            "letter_number": self.letter_number.text().strip() or None,
            "letter_date": letter_date,
            "sender": self.sender.text().strip() or None if direction == LetterDirection.INCOMING else None,
            "receiver": self.receiver.text().strip() or None if direction == LetterDirection.OUTGOING else None,
            "summary": self.summary.toPlainText().strip() or None,
            "referral_to": self.referral_to.text().strip() or None,
            "referral_note": self.referral_note.toPlainText().strip() or None,
            "status": self.status_combo.currentData(),
            "file_path": self.file_path_edit.text().strip() or None,
        }

        try:
            if self.letter_id:
                letter_repo.update(self.letter_id, **data)
            else:
                data["indicator_year"] = jdatetime.date.today().year
                letter_repo.create_numbered(**data)
        except Exception as e:
            QMessageBox.critical(self, "خطا در ذخیره", str(e))
            return
        self.letter_saved.emit()
        self.accept()


class LetterRow(QFrame):
    edited = pyqtSignal()
    deleted = pyqtSignal()

    def __init__(self, letter, parent=None):
        super().__init__(parent)
        self.letter = letter
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        l = self.letter
        dcolor = DIRECTION_COLORS.get(l.direction, "#888888")
        scolor = STATUS_COLORS.get(l.status, "#888888")

        self.setStyleSheet(f"""
            LetterRow {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-right: 4px solid {dcolor};
                border-radius: 8px;
            }}
            LetterRow:hover {{ background-color: {c.canvas_subtle}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        indicator = QLabel(f"{l.indicator_number}\n{l.indicator_year}")
        indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        indicator.setFixedWidth(52)
        indicator.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: white; "
            f"background-color: {dcolor}; border-radius: 6px; padding: 4px;")
        layout.addWidget(indicator)

        info = QVBoxLayout()
        info.setSpacing(3)

        subject = QLabel(l.subject)
        subject.setWordWrap(True)
        subject.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {c.fg_default};")
        info.addWidget(subject)

        parts = [f"شمارهٔ نامه: {l.letter_number}" if l.letter_number else None,
                 f"تاریخ: {l.letter_date}" if l.letter_date else None]
        if l.direction == LetterDirection.INCOMING and l.sender:
            parts.append(f"از: {l.sender}")
        if l.direction == LetterDirection.OUTGOING and l.receiver:
            parts.append(f"به: {l.receiver}")
        if l.referral_to:
            parts.append(f"ارجاع: {l.referral_to}")
        referrals = _related(l, "referrals")
        actions = _related(l, "actions")
        if referrals:
            parts.append(f"ارجاعات: {len(referrals)}")
        if actions:
            parts.append(f"اقدامات: {len(actions)}")
            parts.append(f"آخرین اقدام: {actions[-1].action_text[:60]}")
        sub = QLabel(" — ".join(p for p in parts if p))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
        info.addWidget(sub)

        layout.addLayout(info, 1)

        status_chip = QLabel(LETTER_STATUS_LABELS.get(l.status, ""))
        status_chip.setStyleSheet(
            f"color: white; background-color: {scolor}; border-radius: 12px; "
            f"padding: 5px 12px; font-size: 11px; font-weight: bold;")
        layout.addWidget(status_chip)

        if l.file_path and os.path.exists(l.file_path):
            file_btn = QPushButton("فایل")
            file_btn.setFixedHeight(28)
            file_btn.setStyleSheet(Styles.table_action_button("neutral"))
            file_btn.clicked.connect(self._open_file)
            layout.addWidget(file_btn)

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

    def _open_file(self):
        try:
            os.startfile(self.letter.file_path)
        except Exception as e:
            QMessageBox.warning(self, "خطا", f"باز کردن فایل ممکن نشد:\n{e}")

    def _track(self):
        from ui.tracking_dialog import LetterTrackingDialog
        dlg = LetterTrackingDialog(self.window(), letter_id=self.letter.id)
        dlg.exec()
        self.edited.emit()

    def _edit(self):
        dlg = LetterDialog(self.window(), letter_id=self.letter.id)
        dlg.letter_saved.connect(self.edited.emit)
        dlg.exec()

    def _delete(self):
        if confirm_delete(self, noun="نامه", name=self.letter.subject[:40],
                          extra="با حذف نامه، شماره اندیکاتور آن دوباره استفاده نمی‌شود."):
            try:
                letter_repo.delete(self.letter.id)
                self.deleted.emit()
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))


class LettersPage(QWidget):
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
        title = QLabel("دفتر اندیکاتور")
        title.setStyleSheet(Styles.title_label())
        header.addWidget(title)
        header.addStretch()

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(Styles.subtitle_label())
        header.addWidget(self.stats_label)
        layout.addLayout(header)

        filters = QHBoxLayout()

        self.direction_filter = QComboBox()
        self.direction_filter.addItem("همهٔ نامه‌ها", None)
        for dr, label in DIRECTION_LABELS.items():
            self.direction_filter.addItem(label, dr)
        self.direction_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.direction_filter)

        self.year_filter = QComboBox()
        self.year_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.year_filter)

        self.status_filter = QComboBox()
        self.status_filter.addItem("هر وضعیتی", None)
        for st, label in LETTER_STATUS_LABELS.items():
            self.status_filter.addItem(label, st)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.status_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("جستجو در موضوع، فرستنده، گیرنده…")
        self.search_input.setFixedWidth(280)
        self.search_input.returnPressed.connect(self.refresh)
        filters.addWidget(self.search_input, 1)

        search_btn = QPushButton("جستجو")
        search_btn.setStyleSheet(Styles.secondary_button())
        search_btn.clicked.connect(self.refresh)
        filters.addWidget(search_btn)

        self.report_btn = QPushButton("گزارش پیگیری‌ها (چاپ)")
        self.report_btn.setStyleSheet(Styles.secondary_button())
        self.report_btn.clicked.connect(self._print_report)
        filters.addWidget(self.report_btn)

        add_btn = QPushButton("+ ثبت نامهٔ جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(self._add_letter)
        filters.addWidget(add_btn)

        layout.addLayout(filters)

        hint = QLabel("شمارهٔ اندیکاتور برای هر جهت (وارده/صادره) در هر سال شمسی جداگانه و خودکار ثبت می‌شود.")
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px;")
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.list_host)
        layout.addWidget(self.scroll, 1)

    def _fill_years(self):
        current_year = jdatetime.date.today().year
        years = {current_year}
        for dr in DIRECTION_LABELS:
            for l in letter_repo.get_filtered(direction=dr, limit=1000):
                years.add(l.indicator_year)
        selected = self.year_filter.currentData()
        self.year_filter.blockSignals(True)
        self.year_filter.clear()
        self.year_filter.addItem("همهٔ سال‌ها", None)
        for y in sorted(years, reverse=True):
            self.year_filter.addItem(str(y), y)
        if selected is not None:
            idx = self.year_filter.findData(selected)
            if idx >= 0:
                self.year_filter.setCurrentIndex(idx)
        self.year_filter.blockSignals(False)

    def _add_letter(self):
        dlg = LetterDialog(self)
        dlg.letter_saved.connect(self.refresh)
        dlg.exec()

    def _print_report(self):
        rows = getattr(self, "_last_rows", [])
        if not rows:
            QMessageBox.information(self, "گزارش پیگیری", "نامه‌ای برای گزارش وجود ندارد.")
            return
        from ui.program_print import (
            build_letters_actions_report_html, print_document,
        )
        html = build_letters_actions_report_html(rows)
        print_document(self, "گزارش پیگیری نامه‌ها", html)

    def refresh(self, *_):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")

        self._fill_years()

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = letter_repo.get_filtered(
            direction=self.direction_filter.currentData(),
            year=self.year_filter.currentData(),
            status=self.status_filter.currentData(),
            query=self.search_input.text().strip() or None,
        )

        self._last_rows = rows
        incoming = sum(1 for r in rows if r.direction == LetterDirection.INCOMING)
        self.stats_label.setText(f"{len(rows)} نامه ({incoming} وارده، {len(rows) - incoming} صادره)")

        if not rows:
            empty = QLabel("نامه‌ای ثبت نشده است — با دکمهٔ «ثبت نامهٔ جدید» شروع کنید")
            empty.setStyleSheet(f"color: {c.fg_muted}; font-size: 13px; padding: 24px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_layout.addWidget(empty)

        for letter in rows:
            row = LetterRow(letter)
            row.edited.connect(self.refresh)
            row.deleted.connect(self.refresh)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch()
