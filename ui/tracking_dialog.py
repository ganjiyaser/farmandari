"""پنجره‌های پیگیری نامه و مصوبه: ارجاعات، اقدامات، نتیجه و گزارش چاپی."""

from datetime import datetime

import jdatetime
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QComboBox, QMessageBox, QFrame, QScrollArea, QTabWidget,
    QWidget,
)

from ui.styles import Styles, get_font
from ui.theme import theme_manager
from ui.dialogs import confirm_delete
from services.repositories import (
    letter_repo, letter_referral_repo, letter_action_repo,
    decision_repo, decision_action_repo, setting_repo,
    official_repo, contact_repo, calendar_repo,
)
from models.models import LetterStatus, DecisionStatus

LETTER_STATUS_LABELS = {
    LetterStatus.REGISTERED: "ثبت‌شده",
    LetterStatus.IN_PROGRESS: "در حال پیگیری",
    LetterStatus.ANSWERED: "پاسخ داده شد",
    LetterStatus.ARCHIVED: "بایگانی",
}

DECISION_STATUS_LABELS = {
    DecisionStatus.OPEN: "باز",
    DecisionStatus.IN_PROGRESS: "در حال اجرا",
    DecisionStatus.DONE: "انجام شد",
    DecisionStatus.CANCELLED: "لغو شد",
}

DIALOG_QSS = """
QDialog {{ background-color: {bg}; }}
QLineEdit, QComboBox, QTextEdit {{
    background-color: {input_bg};
    border: 1px solid {input_border};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    color: {fg};
}}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
    border: 2px solid {input_border_hover};
}}
QComboBox QAbstractItemView {{
    background-color: {bg};
    color: {fg};
    border: 1px solid {border};
    selection-background-color: {accent};
    selection-color: white;
}}
"""


def today_jalali() -> str:
    return jdatetime.date.today().strftime("%Y/%m/%d")


def normalize_jalali(text: str):
    """(تاریخ نرمال‌شده، پیام خطا) — تاریخ خالی مجاز است."""
    text = (text or "").strip()
    if not text:
        return None, None
    parts = text.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None, "قالب تاریخ صحیح نیست. مثال: 1404/07/29"
    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    try:
        jdatetime.date(y, m, d)
    except (ValueError, TypeError):
        return None, "تاریخ نامعتبر است."
    return f"{y:04d}/{m:02d}/{d:02d}", None


def current_user_id():
    try:
        uid = setting_repo.get_setting("current_user_id")
        return int(uid) if uid not in (None, "") else None
    except Exception:
        return None


def _dialog_style(widget):
    c = theme_manager.current
    widget.setFont(get_font(10))
    widget.setStyleSheet(DIALOG_QSS.format(
        bg=c.canvas_overlay, input_bg=c.input_bg, input_border=c.input_border,
        input_border_hover=c.input_border_hover, fg=c.fg_default,
        border=c.border_default, accent=c.accent_blue,
    ))


def _field_label(text):
    c = theme_manager.current
    label = QLabel(text)
    label.setStyleSheet(f"color: {c.fg_default}; font-weight: bold;")
    return label


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class ReferralDialog(QDialog):
    """ثبت یک ارجاع جدید برای نامه."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ارجاع جدید")
        self.setMinimumWidth(480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        _dialog_style(self)

        self.data = None
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(_field_label("ارجاع به"))
        self.target_combo = QComboBox()
        self.target_combo.addItem("— انتخاب از مسئولین / مخاطبین —", None)
        try:
            for official in official_repo.get_active():
                self.target_combo.addItem(official.display_name, official.display_name)
        except Exception:
            pass
        try:
            for contact in contact_repo.get_all(limit=500):
                self.target_combo.addItem(contact.display_name, contact.display_name)
        except Exception:
            pass
        layout.addWidget(self.target_combo)

        self.target_text = QLineEdit()
        self.target_text.setPlaceholderText("یا نام شخص / واحد را بنویسید؛ مثال: معاونت مالی")
        layout.addWidget(self.target_text)

        layout.addWidget(_field_label("تاریخ ارجاع (شمسی)"))
        self.date_input = QLineEdit(today_jalali())
        self.date_input.setFixedWidth(150)
        layout.addWidget(self.date_input)

        layout.addWidget(_field_label("یادداشت ارجاع (اختیاری)"))
        self.note = QTextEdit()
        self.note.setMaximumHeight(80)
        layout.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("انصراف")
        cancel.setStyleSheet(Styles.secondary_button())
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("ثبت ارجاع")
        save.setStyleSheet(Styles.primary_button())
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self):
        target = self.target_combo.currentData() or self.target_text.text().strip()
        if not target:
            QMessageBox.warning(self, "خطا", "مقصد ارجاع را انتخاب یا وارد کنید")
            return
        date, error = normalize_jalali(self.date_input.text())
        if error:
            QMessageBox.warning(self, "خطا", error)
            return
        self.data = {
            "referred_to": target,
            "referral_date": date,
            "note": self.note.toPlainText().strip() or None,
        }
        self.accept()


class ActionDialog(QDialog):
    """ثبت یک اقدام و نتیجهٔ آن برای نامه یا مصوبه."""

    def __init__(self, parent=None, subject="اقدام جدید"):
        super().__init__(parent)
        self.setWindowTitle("ثبت اقدام")
        self.setMinimumWidth(520)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        _dialog_style(self)

        self.data = None
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(subject)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {theme_manager.current.fg_default}; font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        layout.addWidget(_field_label("تاریخ اقدام (شمسی)"))
        self.date_input = QLineEdit(today_jalali())
        self.date_input.setFixedWidth(150)
        layout.addWidget(self.date_input)

        layout.addWidget(_field_label("اقدام انجام‌شده"))
        self.action_text = QTextEdit()
        self.action_text.setPlaceholderText("چه اقدامی انجام شد؟")
        self.action_text.setMaximumHeight(90)
        layout.addWidget(self.action_text)

        layout.addWidget(_field_label("نتیجه (اختیاری)"))
        self.result_text = QTextEdit()
        self.result_text.setPlaceholderText("نتیجه یا اثر این اقدام چه بود؟")
        self.result_text.setMaximumHeight(80)
        layout.addWidget(self.result_text)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("انصراف")
        cancel.setStyleSheet(Styles.secondary_button())
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("ثبت اقدام")
        save.setStyleSheet(Styles.primary_button())
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self):
        action = self.action_text.toPlainText().strip()
        if not action:
            QMessageBox.warning(self, "خطا", "متن اقدام را وارد کنید")
            return
        date, error = normalize_jalali(self.date_input.text())
        if error:
            QMessageBox.warning(self, "خطا", error)
            return
        self.data = {
            "action_date": date,
            "action_text": action,
            "result": self.result_text.toPlainText().strip() or None,
        }
        self.accept()


def _tracking_row(title, meta, body, on_delete):
    c = theme_manager.current
    frame = QFrame()
    frame.setStyleSheet(f"""
        QFrame {{
            background-color: {c.canvas_overlay};
            border: 1px solid {c.border_default};
            border-radius: 8px;
        }}
    """)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(8)

    texts = QVBoxLayout()
    texts.setSpacing(3)

    head = QLabel(title)
    head.setWordWrap(True)
    head.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {c.fg_default};")
    texts.addWidget(head)

    if meta:
        meta_label = QLabel(meta)
        meta_label.setWordWrap(True)
        meta_label.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
        texts.addWidget(meta_label)

    if body:
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(f"font-size: 11px; color: {c.fg_default};")
        texts.addWidget(body_label)

    layout.addLayout(texts, 1)

    delete = QPushButton("حذف")
    delete.setFixedHeight(26)
    delete.setStyleSheet(Styles.table_action_button("danger"))
    delete.clicked.connect(on_delete)
    layout.addWidget(delete)
    return frame


class LetterTrackingDialog(QDialog):
    changed = pyqtSignal()

    def __init__(self, parent=None, letter_id=None):
        super().__init__(parent)
        self.letter = letter_repo.get_by_id(letter_id)
        if self.letter is None:
            raise ValueError("letter not found")
        self.setWindowTitle("پیگیری نامه")
        self.resize(780, 640)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        _dialog_style(self)
        self._setup_ui()
        self._refresh_referrals()
        self._refresh_actions()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        title = QLabel(f"پیگیری نامه: {self.letter.subject}")
        title.setWordWrap(True)
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {c.fg_default};")
        layout.addWidget(title)

        from ui.letters_page import DIRECTION_LABELS
        direction = DIRECTION_LABELS.get(self.letter.direction, "")
        meta = QLabel(
            f"اندیکاتور {self.letter.indicator_number}/{self.letter.indicator_year} — "
            f"{direction}" + (f" — شمارهٔ نامه: {self.letter.letter_number}"
                              if self.letter.letter_number else "")
        )
        meta.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
        layout.addWidget(meta)

        status_row = QHBoxLayout()
        status_row.addWidget(_field_label("وضعیت نامه:"))
        self.status_combo = QComboBox()
        for status, label in LETTER_STATUS_LABELS.items():
            self.status_combo.addItem(label, status)
        idx = self.status_combo.findData(self.letter.status)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        self.status_combo.setFixedWidth(170)
        status_row.addWidget(self.status_combo)
        save_status = QPushButton("ذخیره وضعیت")
        save_status.setStyleSheet(Styles.secondary_button())
        save_status.clicked.connect(self._save_status)
        status_row.addWidget(save_status)
        status_row.addStretch()
        layout.addLayout(status_row)

        self.tabs = QTabWidget()
        self.tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout.addWidget(self.tabs, 1)

        # ارجاعات
        referrals_tab = QWidget()
        r_layout = QVBoxLayout(referrals_tab)
        r_layout.setContentsMargins(4, 10, 4, 4)
        r_layout.setSpacing(8)
        r_head = QHBoxLayout()
        self.referrals_count = QLabel()
        self.referrals_count.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px;")
        r_head.addWidget(self.referrals_count)
        r_head.addStretch()
        add_referral = QPushButton("+ ارجاع جدید")
        add_referral.setStyleSheet(Styles.primary_button())
        add_referral.clicked.connect(self._add_referral)
        r_head.addWidget(add_referral)
        r_layout.addLayout(r_head)
        self.referrals_host = QWidget()
        self.referrals_list = QVBoxLayout(self.referrals_host)
        self.referrals_list.setSpacing(6)
        scroll_ref = QScrollArea()
        scroll_ref.setWidgetResizable(True)
        scroll_ref.setFrameShape(QFrame.Shape.NoFrame)
        scroll_ref.setWidget(self.referrals_host)
        r_layout.addWidget(scroll_ref, 1)
        self.tabs.addTab(referrals_tab, "ارجاعات")

        # اقدامات
        actions_tab = QWidget()
        a_layout = QVBoxLayout(actions_tab)
        a_layout.setContentsMargins(4, 10, 4, 4)
        a_layout.setSpacing(8)
        a_head = QHBoxLayout()
        self.actions_count = QLabel()
        self.actions_count.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px;")
        a_head.addWidget(self.actions_count)
        a_head.addStretch()
        add_action = QPushButton("+ ثبت اقدام")
        add_action.setStyleSheet(Styles.primary_button())
        add_action.clicked.connect(self._add_action)
        a_head.addWidget(add_action)
        a_layout.addLayout(a_head)
        self.actions_host = QWidget()
        self.actions_list = QVBoxLayout(self.actions_host)
        self.actions_list.setSpacing(6)
        scroll_actions = QScrollArea()
        scroll_actions.setWidgetResizable(True)
        scroll_actions.setFrameShape(QFrame.Shape.NoFrame)
        scroll_actions.setWidget(self.actions_host)
        a_layout.addWidget(scroll_actions, 1)
        self.tabs.addTab(actions_tab, "اقدامات")

        footer = QHBoxLayout()
        print_btn = QPushButton("چاپ گزارش اقدامات")
        print_btn.setStyleSheet(Styles.primary_button())
        print_btn.clicked.connect(self._print_report)
        footer.addWidget(print_btn)
        footer.addStretch()
        close = QPushButton("بستن")
        close.setStyleSheet(Styles.secondary_button())
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _refresh_referrals(self):
        _clear_layout(self.referrals_list)
        referrals = letter_referral_repo.get_by_letter(self.letter.id)
        self.referrals_count.setText(f"{len(referrals)} ارجاع ثبت شده")
        if not referrals:
            empty = QLabel("ارجاعی ثبت نشده است")
            empty.setStyleSheet(
                f"color: {theme_manager.current.fg_muted}; font-size: 12px; padding: 18px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.referrals_list.addWidget(empty)
        for referral in reversed(referrals):
            meta = " — ".join(x for x in (referral.referral_date,) if x)
            widget = _tracking_row(
                f"ارجاع به: {referral.referred_to}",
                meta,
                referral.note,
                lambda _=False, rid=referral.id, name=referral.referred_to:
                    self._delete_referral(rid, name),
            )
            self.referrals_list.addWidget(widget)
        self.referrals_list.addStretch()

    def _refresh_actions(self):
        _clear_layout(self.actions_list)
        actions = letter_action_repo.get_by_letter(self.letter.id)
        self.actions_count.setText(f"{len(actions)} اقدام ثبت شده")
        if not actions:
            empty = QLabel("اقدامی ثبت نشده است")
            empty.setStyleSheet(
                f"color: {theme_manager.current.fg_muted}; font-size: 12px; padding: 18px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.actions_list.addWidget(empty)
        for action in reversed(actions):
            widget = _tracking_row(
                action.action_text,
                action.action_date,
                f"نتیجه: {action.result}" if action.result else None,
                lambda _=False, aid=action.id:
                    self._delete_action(aid),
            )
            self.actions_list.addWidget(widget)
        self.actions_list.addStretch()

    def _save_status(self):
        status = self.status_combo.currentData()
        try:
            letter_repo.update(self.letter.id, status=status)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self.letter.status = status
        self.changed.emit()
        QMessageBox.information(self, "موفق", "وضعیت نامه ذخیره شد")

    def _add_referral(self):
        dialog = ReferralDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.data:
            return
        try:
            letter_referral_repo.add(
                self.letter.id, created_by=current_user_id(), **dialog.data)
            if self.letter.status == LetterStatus.REGISTERED:
                letter_repo.update(self.letter.id, status=LetterStatus.IN_PROGRESS,
                                   referral_to=dialog.data["referred_to"])
                self.letter.status = LetterStatus.IN_PROGRESS
                idx = self.status_combo.findData(LetterStatus.IN_PROGRESS)
                if idx >= 0:
                    self.status_combo.setCurrentIndex(idx)
            else:
                letter_repo.update(self.letter.id, referral_to=dialog.data["referred_to"])
        except Exception as e:
            QMessageBox.critical(self, "خطا در ثبت ارجاع", str(e))
            return
        self._refresh_referrals()
        self._refresh_actions()
        self.changed.emit()

    def _add_action(self):
        dialog = ActionDialog(self, subject=self.letter.subject)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.data:
            return
        try:
            letter_action_repo.add(
                self.letter.id, created_by=current_user_id(), **dialog.data)
            if self.letter.status == LetterStatus.REGISTERED:
                letter_repo.update(self.letter.id, status=LetterStatus.IN_PROGRESS)
                self.letter.status = LetterStatus.IN_PROGRESS
                idx = self.status_combo.findData(LetterStatus.IN_PROGRESS)
                if idx >= 0:
                    self.status_combo.setCurrentIndex(idx)
        except Exception as e:
            QMessageBox.critical(self, "خطا در ثبت اقدام", str(e))
            return
        self._refresh_actions()
        self.changed.emit()

    def _delete_referral(self, referral_id, name):
        if not confirm_delete(self, noun="ارجاع", name=name):
            return
        try:
            letter_referral_repo.delete(referral_id)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self._refresh_referrals()
        self.changed.emit()

    def _delete_action(self, action_id):
        if not confirm_delete(self, noun="اقدام", name="این اقدام"):
            return
        try:
            letter_action_repo.delete(action_id)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self._refresh_actions()
        self.changed.emit()

    def _print_report(self):
        from ui.program_print import build_letter_tracking_html, print_document
        referrals = letter_referral_repo.get_by_letter(self.letter.id)
        actions = letter_action_repo.get_by_letter(self.letter.id)
        html = build_letter_tracking_html(self.letter, referrals, actions)
        print_document(self, "گزارش اقدامات نامه", html)


class DecisionTrackingDialog(QDialog):
    changed = pyqtSignal()

    def __init__(self, parent=None, decision_id=None):
        super().__init__(parent)
        self.decision = decision_repo.get_detail(decision_id)
        if self.decision is None:
            raise ValueError("decision not found")
        self.event_label = "—"
        try:
            if self.decision.event_id:
                event = calendar_repo.get_by_id(self.decision.event_id)
                if event is not None:
                    self.event_label = f"{event.event_date or '—'} — {event.title}"
        except Exception:
            pass
        self.setWindowTitle("پیگیری مصوبه")
        self.resize(760, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        _dialog_style(self)
        self._setup_ui()
        self._refresh_actions()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        title = QLabel("پیگیری مصوبه")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {c.fg_default};")
        layout.addWidget(title)

        content = QLabel(self.decision.content)
        content.setWordWrap(True)
        content.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {c.fg_default};")
        layout.addWidget(content)

        meta = QLabel(
            f"جلسه: {self.event_label} — مسئول اجرا: {self.decision.assignee_name}"
            + (f" — مهلت: {self.decision.due_date}" if self.decision.due_date else "")
        )
        meta.setWordWrap(True)
        meta.setStyleSheet(f"font-size: 11px; color: {c.fg_muted};")
        layout.addWidget(meta)

        status_row = QHBoxLayout()
        status_row.addWidget(_field_label("وضعیت:"))
        self.status_combo = QComboBox()
        for status, label in DECISION_STATUS_LABELS.items():
            self.status_combo.addItem(label, status)
        idx = self.status_combo.findData(self.decision.status)
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        self.status_combo.setFixedWidth(150)
        status_row.addWidget(self.status_combo)
        status_row.addStretch()

        save_result = QPushButton("ذخیره نتیجه و وضعیت")
        save_result.setStyleSheet(Styles.primary_button())
        save_result.clicked.connect(self._save_result)
        status_row.addWidget(save_result)
        layout.addLayout(status_row)

        layout.addWidget(_field_label("نتیجهٔ نهایی (چه نتیجه‌ای حاصل شد؟)"))
        self.result_text = QTextEdit()
        self.result_text.setPlaceholderText(
            "نتیجهٔ اجرای مصوبه، اثر یا موانع را اینجا ثبت کنید…")
        self.result_text.setMaximumHeight(90)
        self.result_text.setPlainText(self.decision.result or "")
        layout.addWidget(self.result_text)

        actions_head = QHBoxLayout()
        self.actions_count = QLabel()
        self.actions_count.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px;")
        actions_head.addWidget(self.actions_count)
        actions_head.addStretch()
        add_action = QPushButton("+ ثبت اقدام")
        add_action.setStyleSheet(Styles.primary_button())
        add_action.clicked.connect(self._add_action)
        actions_head.addWidget(add_action)
        layout.addLayout(actions_head)

        self.actions_host = QWidget()
        self.actions_list = QVBoxLayout(self.actions_host)
        self.actions_list.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.actions_host)
        layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        print_btn = QPushButton("چاپ گزارش اقدامات")
        print_btn.setStyleSheet(Styles.primary_button())
        print_btn.clicked.connect(self._print_report)
        footer.addWidget(print_btn)
        footer.addStretch()
        close = QPushButton("بستن")
        close.setStyleSheet(Styles.secondary_button())
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _refresh_actions(self):
        _clear_layout(self.actions_list)
        actions = decision_action_repo.get_by_decision(self.decision.id)
        self.actions_count.setText(f"{len(actions)} اقدام ثبت شده")
        if not actions:
            empty = QLabel("اقدامی ثبت نشده است")
            empty.setStyleSheet(
                f"color: {theme_manager.current.fg_muted}; font-size: 12px; padding: 18px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.actions_list.addWidget(empty)
        for action in reversed(actions):
            widget = _tracking_row(
                action.action_text,
                action.action_date,
                f"نتیجه: {action.result}" if action.result else None,
                lambda _=False, aid=action.id: self._delete_action(aid),
            )
            self.actions_list.addWidget(widget)
        self.actions_list.addStretch()

    def _save_result(self):
        status = self.status_combo.currentData()
        result = self.result_text.toPlainText().strip() or None
        data = {"status": status, "result": result}
        data["completed_at"] = datetime.now() if status == DecisionStatus.DONE else None
        try:
            decision_repo.update(self.decision.id, **data)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self.decision.status = status
        self.decision.result = result
        self.changed.emit()
        QMessageBox.information(self, "موفق", "نتیجه و وضعیت مصوبه ذخیره شد")

    def _add_action(self):
        dialog = ActionDialog(self, subject=self.decision.content)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.data:
            return
        try:
            decision_action_repo.add(
                self.decision.id, created_by=current_user_id(), **dialog.data)
            if self.decision.status == DecisionStatus.OPEN:
                decision_repo.update(
                    self.decision.id, status=DecisionStatus.IN_PROGRESS)
                self.decision.status = DecisionStatus.IN_PROGRESS
                idx = self.status_combo.findData(DecisionStatus.IN_PROGRESS)
                if idx >= 0:
                    self.status_combo.setCurrentIndex(idx)
        except Exception as e:
            QMessageBox.critical(self, "خطا در ثبت اقدام", str(e))
            return
        self._refresh_actions()
        self.changed.emit()

    def _delete_action(self, action_id):
        if not confirm_delete(self, noun="اقدام", name="این اقدام"):
            return
        try:
            decision_action_repo.delete(action_id)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))
            return
        self._refresh_actions()
        self.changed.emit()

    def _print_report(self):
        from ui.program_print import build_decision_tracking_html, print_document
        actions = decision_action_repo.get_by_decision(self.decision.id)
        html = build_decision_tracking_html(
            self.decision, actions, event_label=self.event_label)
        print_document(self, "گزارش اقدامات مصوبه", html)
