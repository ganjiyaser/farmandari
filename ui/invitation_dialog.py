"""دعوتنامه: پیگیری وضعیت پاسخ شرکت‌کنندگان (RSVP) و چاپ دعوتنامهٔ رسمی."""

import jdatetime
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextDocument, QFont, QPageLayout
from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QTextBrowser, QFileDialog,
    QAbstractItemView, QMessageBox, QFrame
)

from core.config import settings
from models.models import ParticipantStatus, EventType
from services.repositories import participant_repo
from ui.officials_page import position_label
from ui.styles import Styles, get_font
from ui.theme import theme_manager

RSVP_LABELS = {
    ParticipantStatus.INVITED: "در انتظار پاسخ",
    ParticipantStatus.ACCEPTED: "تایید حضور",
    ParticipantStatus.DECLINED: "عدم حضور",
    ParticipantStatus.ATTENDED: "حاضر شد",
    ParticipantStatus.ABSENT: "غایب",
}

RSVP_COLORS = {
    ParticipantStatus.INVITED: "#F57F17",
    ParticipantStatus.ACCEPTED: "#2E7D32",
    ParticipantStatus.DECLINED: "#C62828",
    ParticipantStatus.ATTENDED: "#1565C0",
    ParticipantStatus.ABSENT: "#757575",
}


class ParticipantsDialog(QDialog):
    """فهرست دعوت‌شدگان جلسه و ثبت پاسخ آن‌ها (حضور/عدم حضور)."""

    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.event = event
        self.setWindowTitle(f"دعوت‌شدگان جلسه «{event.title}»")
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFont(get_font(10))
        self.setMinimumSize(560, 420)
        self._setup_ui()
        self._load_participants()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"QDialog {{ background-color: {c.canvas_overlay}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 12px; background: transparent;")
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["نام", "سمت / دسته", "وضعیت پاسخ", "زمان ثبت پاسخ"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c.canvas_overlay};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                border-radius: 8px;
                gridline-color: {c.border_default};
            }}
            QTableWidget::item {{ padding: 6px; }}
            QHeaderView::section {{
                background-color: {c.canvas_subtle};
                color: {c.fg_default};
                border: none;
                padding: 8px;
                font-weight: bold;
            }}
        """)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        hint = QLabel("با تغییر «وضعیت پاسخ»، پاسخ مخاطب یا مسئول بلافاصله ثبت می‌شود.")
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px; background: transparent;")
        root.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("بستن")
        close_btn.setStyleSheet(Styles.secondary_button())
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _load_participants(self):
        c = theme_manager.current
        rows = participant_repo.get_by_event(self.event.id)
        self.table.setRowCount(len(rows))

        counts = {}
        for i, p in enumerate(rows):
            if p.official is not None:
                category = position_label(p.official.position)
            else:
                category = "مخاطب"
            self.table.setItem(i, 0, QTableWidgetItem(p.name or "—"))
            self.table.setItem(i, 1, QTableWidgetItem(category))

            status_item = QTableWidgetItem()
            combo = QComboBox()
            for st, label in RSVP_LABELS.items():
                combo.addItem(label, st)
            idx = list(RSVP_LABELS.keys()).index(p.status)
            combo.setCurrentIndex(idx)
            combo.setStyleSheet(
                f"QComboBox {{ background-color: {RSVP_COLORS.get(p.status, '#888')}; "
                f"color: white; border: none; border-radius: 10px; padding: 4px 10px; "
                f"font-family: Tahoma; font-size: 11px; }}"
                f"QComboBox QAbstractItemView {{ background-color: {c.canvas_overlay}; "
                f"color: {c.fg_default}; selection-background-color: {c.primary}; }}"
            )
            combo.currentIndexChanged.connect(
                lambda _i, pid=p.id, cb=combo: self._change_status(pid, cb))
            self.table.setCellWidget(i, 2, combo)
            self.table.setItem(i, 2, status_item)

            responded = ""
            if p.responded_at:
                try:
                    responded = jdatetime.datetime.fromgregorian(datetime=p.responded_at)\
                        .strftime("%Y/%m/%d %H:%M")
                except Exception:
                    responded = str(p.responded_at)
            self.table.setItem(i, 3, QTableWidgetItem(responded))

            counts[p.status] = counts.get(p.status, 0) + 1

        parts = []
        for st in ParticipantStatus:
            if counts.get(st):
                parts.append(f"{RSVP_LABELS[st]}: {counts[st]}")
        self.summary_label.setText(
            f"{len(rows)} دعوت‌شده — " + " • ".join(parts) if parts else "هنوز دعوت‌شدگی ثبت نشده است."
        )

    def _change_status(self, participant_id, combo):
        status = combo.currentData()
        if participant_repo.set_status(participant_id, status):
            self._load_participants()
        else:
            QMessageBox.warning(self, "خطا", "ثبت وضعیت انجام نشد")


def _event_type_label(event) -> str:
    try:
        value = event.event_type.value if event.event_type else ""
    except Exception:
        value = ""
    return {
        "meeting": "جلسه",
        "conference": "همایش",
        "visit": "بازدید / دیدار",
        "followup": "پیگیری",
        "reminder": "یادآوری",
        "other": "برنامه",
    }.get(value, "برنامه")


def build_invitation_html(event) -> str:
    """HTML دعوتنامهٔ رسمی برای چاپ یا PDF."""
    c = theme_manager.current
    date_jalali = event.event_date or ""
    try:
        y, m, d = (int(x) for x in date_jalali.split("/"))
        date_text = f"{jdatetime.date(y, m, d).strftime('%A')} {date_jalali}"
    except Exception:
        date_text = date_jalali

    return f"""
    <div dir="rtl" style="font-family:'Vazirmatn','B Nazanin',Tahoma; line-height:2;">
      <table width="100%" style="border-bottom:3px double #1a1a1a; margin-bottom:18px;">
        <tr>
          <td align="center">
            <span style="font-size:15pt; font-weight:bold;">جمهوری اسلامی ایران</span><br>
            <span style="font-size:13pt;">{settings.ORGANIZATION}</span><br>
            <span style="font-size:9pt; color:#555;">{settings.APP_NAME}</span>
          </td>
        </tr>
      </table>

      <p align="center" style="font-size:14pt; font-weight:bold; margin:24px 0;">دعوتنامه</p>

      <p style="font-size:12pt;">
        با سلام و احترام؛
      </p>
      <p style="font-size:12pt;">
        به استحضار می‌رساند جلسهٔ «<b>{event.title}</b>» با موضوع
        {_event_type_label(event)} در تاریخ <b>{date_text}</b> ساعت
        <b>{event.event_time or '—'}</b>
        {f'لغایت {event.end_time}' if event.end_time else ''}
        در محل <b>{event.location or 'دفتر فرمانداری'}</b> برگزار می‌گردد.
        حضور بموقع جنابعالی موجب امتنان است.
      </p>
      {f'<p style="font-size:11pt; color:#444;">میزبانی: {event.host}</p>' if event.host else ''}
      {f'<div style="font-size:10pt; color:#555; background:#f5f5f5; padding:10px; border-radius:6px;">{event.description}</div>' if event.description else ''}

      <table width="100%" style="margin-top:48px;">
        <tr>
          <td align="left" style="font-size:11pt;">
            روابط عمومی فرمانداری
          </td>
        </tr>
      </table>
    </div>
    """


class InvitationPreviewDialog(QDialog):
    """پیش‌نمایش دعوتنامه با امکان چاپ یا ذخیرهٔ PDF."""

    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.event = event
        self.html = build_invitation_html(event)
        self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        self.setWindowTitle(f"چاپ دعوتنامه «{event.title}»")
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFont(get_font(10))
        self.setMinimumSize(640, 640)
        self._setup_ui()

    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"QDialog {{ background-color: {c.canvas_overlay}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setHtml(self.html)
        self.preview.setStyleSheet(f"""
            QTextBrowser {{
                background-color: white;
                color: #1a1a1a;
                border: 1px solid {c.border_default};
                border-radius: 8px;
                padding: 24px;
                font-family: Tahoma;
            }}
        """)
        root.addWidget(self.preview, 1)

        btn_row = QHBoxLayout()

        pdf_btn = QPushButton("ذخیره PDF")
        pdf_btn.setStyleSheet(Styles.secondary_button())
        pdf_btn.clicked.connect(self._save_pdf)
        btn_row.addWidget(pdf_btn)

        print_btn = QPushButton("چاپ")
        print_btn.setStyleSheet(Styles.primary_button())
        print_btn.clicked.connect(self._print)
        btn_row.addWidget(print_btn)

        btn_row.addStretch()

        close_btn = QPushButton("بستن")
        close_btn.setStyleSheet(Styles.secondary_button())
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    def _print(self):
        dlg = QPrintPreviewDialog(self._printer, self)
        doc = QTextDocument()
        doc.setHtml(self.html)
        dlg.paintRequested.connect(doc.print_)
        dlg.exec()

    def _save_pdf(self):
        default_name = f"invitation-{self.event.event_date or ''}.pdf".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره دعوتنامه", default_name, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self._printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        self._printer.setOutputFileName(path)
        doc = QTextDocument()
        doc.setHtml(self.html)
        doc.print_(self._printer)
        self._printer.setOutputFileName("")
        QMessageBox.information(self, "موفق", f"دعوتنامه ذخیره شد:\n{path}")
