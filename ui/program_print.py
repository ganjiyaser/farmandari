"""چاپ یا PDF برنامهٔ جلسات، صورت‌جلسه و گزارش‌های پیگیری (خروجی رسمی فرمانداری)."""

import html as html_lib

import jdatetime
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument, QPageLayout
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QDialog

from core.config import settings
from models.models import DecisionStatus, LetterDirection, LetterStatus

LETTER_DIRECTION_LABELS = {
    LetterDirection.INCOMING: "وارده",
    LetterDirection.OUTGOING: "صادره",
}

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


def _today_jalali() -> str:
    return jdatetime.date.today().strftime("%Y/%m/%d")


def _cell(value) -> str:
    if value is None or value == "":
        return "—"
    return html_lib.escape(str(value)).replace("\n", "<br>")


def _table(headers, rows) -> str:
    if not rows:
        return ""
    th = "".join(
        f'<th style="border:1px solid #999; padding:6px; background:#efefef;">'
        f'{html_lib.escape(h)}</th>' for h in headers
    )
    body = "".join(
        "<tr>" + "".join(
            f'<td style="border:1px solid #999; padding:6px; vertical-align:top;">{_cell(v)}</td>'
            for v in row
        ) + "</tr>"
        for row in rows
    )
    return (f'<table width="100%" cellspacing="0" style="font-size:10pt; margin-top:8px;">'
            f'<tr>{th}</tr>{body}</table>')


def _document(title, subtitle, body) -> str:
    return f"""
    <div dir="rtl" style="font-family:'Vazirmatn','B Nazanin',Tahoma;">
      <p align="center" style="font-size:13pt; font-weight:bold; margin-bottom:2px;">
        {html_lib.escape(settings.ORGANIZATION)} — {html_lib.escape(title)}
      </p>
      <p align="center" style="font-size:11pt; color:#555; margin-top:0;">{_cell(subtitle)}</p>
      <p align="center" style="font-size:9pt; color:#777; margin-top:0;">تاریخ گزارش: {_today_jalali()}</p>
      <hr style="border:none; border-top:2px double #1a1a1a; margin:12px 0;">
      {body}
    </div>
    """


def build_program_html(title, subtitle, events, owner_of=None) -> str:
    """جدول HTML برنامه؛ owner_of(event) باید (رنگ، نام صاحب برنامه) بدهد."""
    owner_of = owner_of or (lambda ev: (None, None))

    rows = []
    for ev in sorted(events, key=lambda e: (e.event_date, e.event_time or "")):
        color, owner = owner_of(ev)
        owner_cell = (f'<span style="display:inline-block; width:10px; height:10px; '
                      f'background:{color}; border-radius:5px;"></span> ' if color else "")
        owner_cell += owner or "—"
        rows.append(f"""
        <tr>
          <td style="border:1px solid #999; padding:6px;">{ev.event_date or ''}</td>
          <td style="border:1px solid #999; padding:6px;">{ev.event_time or ''}{f' تا {ev.end_time}' if ev.end_time else ''}</td>
          <td style="border:1px solid #999; padding:6px;">{ev.title}</td>
          <td style="border:1px solid #999; padding:6px;">{owner_cell}</td>
          <td style="border:1px solid #999; padding:6px;">{ev.location or '—'}</td>
        </tr>""")

    return f"""
    <div dir="rtl" style="font-family:'Vazirmatn','B Nazanin',Tahoma;">
      <p align="center" style="font-size:13pt; font-weight:bold; margin-bottom:2px;">
        {settings.ORGANIZATION} — {title}
      </p>
      <p align="center" style="font-size:11pt; color:#555; margin-top:0;">{subtitle}</p>
      <table width="100%" cellspacing="0" style="font-size:10pt; margin-top:12px;">
        <tr style="background:#efefef;">
          <th style="border:1px solid #999; padding:6px;">تاریخ</th>
          <th style="border:1px solid #999; padding:6px;">ساعت</th>
          <th style="border:1px solid #999; padding:6px;">موضوع</th>
          <th style="border:1px solid #999; padding:6px;">صاحب برنامه</th>
          <th style="border:1px solid #999; padding:6px;">محل</th>
        </tr>
        {''.join(rows)}
      </table>
    </div>
    """


def print_program(parent, title, subtitle, events, owner_of=None):
    """نمایش پیش‌نمایش چاپ برنامه؛ در صورت نبود برنامه پیام می‌دهد."""
    if not events:
        QMessageBox.information(parent, "چاپ برنامه", "برنامه‌ای برای چاپ وجود ندارد.")
        return
    html = build_program_html(title, subtitle, events, owner_of)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)

    doc = QTextDocument()
    doc.setHtml(html)

    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(f"چاپ {title}")
    dlg.paintRequested.connect(doc.print_)
    dlg.exec()


def export_program_pdf(parent, title, subtitle, events, owner_of=None) -> None:
    """ذخیرهٔ برنامه به‌صورت PDF با انتخاب مسیر."""
    if not events:
        QMessageBox.information(parent, "خروجی PDF", "برنامه‌ای برای ذخیره وجود ندارد.")
        return
    path, _ = QFileDialog.getSaveFileName(parent, "ذخیره برنامه", f"{title}.pdf", "PDF (*.pdf)")
    if not path:
        return
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    doc = QTextDocument()
    doc.setHtml(build_program_html(title, subtitle, events, owner_of))
    doc.print_(printer)
    printer.setOutputFileName("")
    QMessageBox.information(parent, "موفق", f"برنامه ذخیره شد:\n{path}")


def build_minute_html(title, body, decisions=()):
    """HTML صورت‌جلسه؛ decisions فهرست (متن، مسئول، مهلت، وضعیت)."""
    rows = "".join(
        f"<tr>"
        f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(c)}</td>"
        f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(a or '-')}</td>"
        f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(d or '-')}</td>"
        f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(s or '')}</td>"
        f"</tr>"
        for c, a, d, s in decisions
    )
    decisions_block = ""
    if decisions:
        decisions_block = f"""
          <p style="font-size:12pt; font-weight:bold; margin-top:24px;">مصوبات</p>
          <table width="100%" cellspacing="0" style="font-size:10pt;">
            <tr style="background:#efefef;">
              <th style="border:1px solid #999; padding:6px;">مصوبه</th>
              <th style="border:1px solid #999; padding:6px;">مسئول اجرا</th>
              <th style="border:1px solid #999; padding:6px;">مهلت</th>
              <th style="border:1px solid #999; padding:6px;">وضعیت</th>
            </tr>
            {rows}
          </table>"""

    return f"""
    <div dir="rtl" style="font-family:'Vazirmatn','B Nazanin',Tahoma;">
      <p align="center" style="font-size:13pt; font-weight:bold; margin-bottom:2px;">
        {settings.ORGANIZATION} — صورت‌جلسه
      </p>
      <p align="center" style="font-size:11pt; color:#555; margin-top:0;">{html_lib.escape(title)}</p>
      <hr style="border:none; border-top:2px double #1a1a1a; margin:12px 0;">
      <p style="font-size:11pt; white-space:pre-wrap; line-height:2;">{html_lib.escape(body)}</p>
      {decisions_block}
    </div>
    """


def _kv_table(pairs) -> str:
    rows = "".join(
        f'<tr><th style="border:1px solid #999; padding:6px; background:#f4f4f4; '
        f'width:140px; text-align:right;">{html_lib.escape(str(k))}</th>'
        f'<td style="border:1px solid #999; padding:6px;">{_cell(v)}</td></tr>'
        for k, v in pairs
    )
    return f'<table width="100%" cellspacing="0" style="font-size:10pt; margin-top:8px;">{rows}</table>'


def _safe_list(obj, attr):
    try:
        return list(getattr(obj, attr) or [])
    except Exception:
        return []


def _assignee_name(decision) -> str:
    try:
        return decision.assignee_name
    except Exception:
        return decision.assignee_text or "—"


def build_letter_tracking_html(letter, referrals=(), actions=()) -> str:
    """گزارش کامل یک نامه: مشخصات، ارجاعات و اقدامات."""
    referrals = list(referrals or ())
    actions = list(actions or ())
    direction = LETTER_DIRECTION_LABELS.get(letter.direction, "")
    status = LETTER_STATUS_LABELS.get(letter.status, "")

    info = [
        ("شمارهٔ اندیکاتور", f"{letter.indicator_number} / {letter.indicator_year}"),
        ("نوع نامه", direction),
        ("شمارهٔ روی نامه", letter.letter_number),
        ("تاریخ نامه", letter.letter_date),
    ]
    if letter.direction == LetterDirection.INCOMING:
        info.append(("فرستنده", letter.sender))
    else:
        info.append(("گیرنده", letter.receiver))
    info.append(("وضعیت فعلی", status))

    body = f'<p style="font-size:12pt; font-weight:bold;">موضوع: {_cell(letter.subject)}</p>'
    body += _kv_table(info)
    if letter.summary:
        body += (f'<p style="font-size:11pt; margin-top:14px;"><b>خلاصهٔ نامه:</b><br>'
                 f'<span style="white-space:pre-wrap; line-height:1.9;">{_cell(letter.summary)}</span></p>')

    body += '<p style="font-size:12pt; font-weight:bold; margin-top:20px;">ارجاعات</p>'
    if referrals:
        body += _table(
            ["تاریخ ارجاع", "ارجاع به", "یادداشت"],
            [(r.referral_date, r.referred_to, r.note) for r in referrals],
        )
    else:
        body += '<p style="font-size:10pt; color:#666;">ارجاعی ثبت نشده است.</p>'

    body += '<p style="font-size:12pt; font-weight:bold; margin-top:20px;">اقدامات انجام‌شده</p>'
    if actions:
        body += _table(
            ["تاریخ اقدام", "اقدام", "نتیجه"],
            [(a.action_date, a.action_text, a.result) for a in actions],
        )
    else:
        body += '<p style="font-size:10pt; color:#666;">اقدامی ثبت نشده است.</p>'

    subtitle = f"{direction} — {letter.subject}"
    return _document("گزارش پیگیری نامه", subtitle, body)


def build_decision_tracking_html(decision, actions=(), event_label=None) -> str:
    """گزارش کامل یک مصوبه: مشخصات، نتیجه و اقدامات."""
    actions = list(actions or ())
    status = DECISION_STATUS_LABELS.get(decision.status, "")

    info = [
        ("جلسه", event_label or "—"),
        ("مسئول اجرا", _assignee_name(decision)),
        ("مهلت", decision.due_date),
        ("وضعیت", status),
    ]

    body = f'<p style="font-size:12pt; font-weight:bold;">مصوبه: {_cell(decision.content)}</p>'
    body += _kv_table(info)
    body += (f'<p style="font-size:11pt; margin-top:14px;"><b>نتیجهٔ حاصل‌شده:</b><br>'
             f'<span style="white-space:pre-wrap; line-height:1.9;">'
             f'{_cell(decision.result or "نتیجه‌ای ثبت نشده است.")}</span></p>')

    body += '<p style="font-size:12pt; font-weight:bold; margin-top:20px;">اقدامات انجام‌شده</p>'
    if actions:
        body += _table(
            ["تاریخ اقدام", "اقدام", "نتیجه"],
            [(a.action_date, a.action_text, a.result) for a in actions],
        )
    else:
        body += '<p style="font-size:10pt; color:#666;">اقدامی ثبت نشده است.</p>'

    subtitle = event_label or "مصوبهٔ جلسه"
    return _document("گزارش پیگیری مصوبه", subtitle, body)


def build_letters_actions_report_html(letters, title="گزارش پیگیری نامه‌ها") -> str:
    """گزارش جدولی نامه‌ها همراه با آخرین ارجاع و اقدام."""
    rows = []
    for i, letter in enumerate(letters, 1):
        referrals = _safe_list(letter, "referrals")
        actions = _safe_list(letter, "actions")
        last_ref = referrals[-1].referred_to if referrals else None
        last_action = actions[-1] if actions else None
        last_action_text = None
        if last_action is not None:
            last_action_text = " — ".join(
                str(x) for x in (last_action.action_date, last_action.action_text) if x)
        rows.append((
            i,
            f"{letter.indicator_number}/{letter.indicator_year}",
            letter.subject,
            LETTER_STATUS_LABELS.get(letter.status, ""),
            last_ref,
            len(referrals),
            len(actions),
            last_action_text,
        ))
    body = _table(
        ["#", "اندیکاتور", "موضوع", "وضعیت", "آخرین ارجاع", "ارجاعات", "اقدامات", "آخرین اقدام"],
        rows,
    )
    if not rows:
        body = '<p style="font-size:11pt; color:#666;">نامه‌ای برای گزارش وجود ندارد.</p>'
    return _document(title, f"{len(rows)} نامه", body)


def build_decisions_actions_report_html(decisions, title="گزارش اقدامات مصوبات") -> str:
    """گزارش جدولی مصوبات همراه با نتیجه و آخرین اقدام."""
    rows = []
    for i, decision in enumerate(decisions, 1):
        actions = _safe_list(decision, "actions")
        try:
            event_label = (f"{decision.event.event_date} — {decision.event.title}"
                           if decision.event is not None else None)
        except Exception:
            event_label = None
        last_action = actions[-1] if actions else None
        last_action_text = None
        if last_action is not None:
            last_action_text = " — ".join(
                str(x) for x in (last_action.action_date, last_action.action_text) if x)
        rows.append((
            i,
            decision.content,
            event_label,
            _assignee_name(decision),
            decision.due_date,
            DECISION_STATUS_LABELS.get(decision.status, ""),
            decision.result,
            len(actions),
            last_action_text,
        ))
    body = _table(
        ["#", "مصوبه", "جلسه", "مسئول", "مهلت", "وضعیت", "نتیجه", "اقدامات", "آخرین اقدام"],
        rows,
    )
    if not rows:
        body = '<p style="font-size:11pt; color:#666;">مصوبه‌ای برای گزارش وجود ندارد.</p>'
    return _document(title, f"{len(rows)} مصوبه", body)


def ordered_posts_tree(posts):
    """[(post, عمق)] به ترتیب سلسله‌مراتبی چارت (والد پیش از فرزند)."""
    posts = list(posts or ())
    by_id = {p.id: p for p in posts}
    children = {}
    roots = []
    for p in posts:
        if p.parent_id and p.parent_id in by_id:
            children.setdefault(p.parent_id, []).append(p)
        else:
            roots.append(p)

    def sort_key(p):
        return (p.sort_order or 0, p.id)

    for group in children.values():
        group.sort(key=sort_key)
    roots.sort(key=sort_key)

    ordered = []
    seen = set()

    def walk(post, depth):
        if post.id in seen:
            return
        seen.add(post.id)
        ordered.append((post, depth))
        for child in children.get(post.id, ()):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    # پست‌های یتیم یا گرفتار چرخهٔ داده‌ای نباید از گزارش حذف شوند
    for post in posts:
        if post.id not in seen:
            ordered.append((post, 0))
            seen.add(post.id)
    return ordered


def build_org_chart_list_html(posts, employees_by_post, title="چارت سازمانی") -> str:
    """گزارش فهرستی چارت: پست سازمانی، متصدی و محل خدمت فعلی (جدا از پست)."""
    ordered = ordered_posts_tree(posts)
    if not ordered:
        return _document(title, "چارت خالی است",
                         '<p style="font-size:11pt; color:#666;">'
                         'هنوز پستی در چارت سازمانی ثبت نشده است.</p>')

    rows = []
    for post, depth in ordered:
        employees = list(employees_by_post.get(post.id, ()))
        active = [e for e in employees if e.is_active]
        listed = active or employees
        names = "، ".join(e.full_name for e in listed) or "—"
        workplaces = []
        for emp in listed:
            place = (emp.workplace or "").strip()
            if place and place != (post.title or "").strip() and place not in workplaces:
                workplaces.append(place)
        if workplaces:
            place_text = "، ".join(workplaces)
        elif listed:
            place_text = "طبق پست"
        else:
            place_text = "—"
        rows.append((
            ("— " * depth) + (post.title or ""),
            post.category,
            names,
            place_text,
            post.approved_count or 1,
        ))

    body = _table(
        ["پست سازمانی", "حوزه / دسته", "متصدی (پست سازمانی)", "محل خدمت فعلی", "پست مصوب"],
        rows,
    )
    root_title = ordered[0][0].title if ordered else ""
    subtitle = (f"ریشه: {root_title} — {len(ordered)} پست سازمانی "
                f"(محل خدمت فعلی مستقل از پست سازمانی است)")
    return _document(title, subtitle, body)


def build_employees_report_html(employees, title="فهرست پرسنل") -> str:
    """گزارش جدولی پرسنل همراه با پست سازمانی و محل خدمت فعلی."""
    employees = list(employees or ())
    rows = []
    for i, emp in enumerate(employees, 1):
        try:
            post_title = emp.post.title if emp.post is not None else None
        except Exception:
            post_title = None
        place = (emp.workplace or "").strip()
        if not place:
            place = "طبق پست" if post_title else "—"
        rows.append((
            i,
            emp.full_name,
            emp.personnel_code,
            post_title or "—",
            place,
            emp.mobile,
            emp.employment_status,
            "بله" if emp.is_active else "خیر",
        ))
    body = _table(
        ["#", "نام و نام خانوادگی", "کد پرسنلی", "پست سازمانی",
         "محل خدمت فعلی", "موبایل", "وضعیت خدمت", "فعال"],
        rows,
    )
    if not rows:
        body = '<p style="font-size:11pt; color:#666;">پرسنلی ثبت نشده است.</p>'
    active_count = sum(1 for e in employees if e.is_active)
    subtitle = (f"{len(employees)} نفر — {active_count} فعال | "
                "پست سازمانی و محل خدمت فعلی دو مفهوم جدا هستند")
    return _document(title, subtitle, body)


def print_document(parent, title, html, landscape=False):
    """پیش‌نمایش چاپ یک سند HTML (صورت‌جلسه و امثال آن)."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageOrientation(
        QPageLayout.Orientation.Landscape if landscape
        else QPageLayout.Orientation.Portrait
    )
    doc = QTextDocument()
    doc.setHtml(html)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(f"چاپ {title}")
    dlg.paintRequested.connect(doc.print_)
    dlg.exec()
