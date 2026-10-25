import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import csv

from core.config import settings
from models.models import Contact, ContactProfile, ContactFile
from services.repositories import contact_repo, profile_repo, file_repo
from services.file_service import safe_filename

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _RTL_SHAPING_AVAILABLE = True
except ImportError:
    _RTL_SHAPING_AVAILABLE = False


def rtl(text) -> str:
    """
    ReportLab draws Persian/Arabic glyphs in their isolated (unjoined) form and
    left-to-right, which renders as disconnected/reversed text in the PDF.
    This reshapes + reorders the text for correct display, when the
    arabic-reshaper and python-bidi packages are installed. If they're not
    installed, text is returned unchanged (same as before).
    """
    if text is None:
        return ""
    text = str(text)
    if not _RTL_SHAPING_AVAILABLE or not text:
        return text
    return get_display(arabic_reshaper.reshape(text))


class ExportService:
    def __init__(self):
        self.export_dir = settings.EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._register_fonts()

    def _register_fonts(self):
        """Pick a font that actually contains Persian/Arabic glyphs.

        The old code only tried the relative path ``resources/fonts/Vazir.ttf``,
        which (a) never existed in this repo and (b) depended on the process
        CWD, so it always fell back to Helvetica -- a font with no Arabic block.
        Combined with rtl() reshaping that produced blank/garbled PDFs with no
        warning. Now: bundled fonts first (resolved absolutely, so it also works
        under the frozen exe), then Windows' Tahoma / Segoe UI / Arial.
        """
        from core.config import PROJECT_ROOT

        regular_candidates = [
            PROJECT_ROOT / "resources" / "fonts" / "Vazir.ttf",
            PROJECT_ROOT / "fonts" / "Vazir.ttf",
        ]
        bold_candidates = [
            PROJECT_ROOT / "resources" / "fonts" / "Vazir-Bold.ttf",
            PROJECT_ROOT / "fonts" / "Vazir-Bold.ttf",
        ]

        windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        regular_candidates += [
            windir / "tahoma.ttf",
            windir / "segoeui.ttf",
            windir / "arial.ttf",
        ]
        bold_candidates += [
            windir / "tahomabd.ttf",
            windir / "segoeuib.ttf",
            windir / "arialbd.ttf",
        ]

        regular = self._first_existing(regular_candidates)
        bold = self._first_existing(bold_candidates) or regular

        if regular is None:
            self.font_name = 'Helvetica'
            self.font_name_bold = 'Helvetica-Bold'
            print(
                "WARNING: no Persian-capable font found "
                "(looked for resources/fonts/Vazir.ttf and Windows fonts); "
                "exported PDFs will not render Persian text correctly."
            )
            return

        try:
            pdfmetrics.registerFont(TTFont('AppFont', str(regular)))
            pdfmetrics.registerFont(TTFont('AppFont-Bold', str(bold)))
            self.font_name = 'AppFont'
            self.font_name_bold = 'AppFont-Bold'
        except Exception:
            self.font_name = 'Helvetica'
            self.font_name_bold = 'Helvetica-Bold'

    @staticmethod
    def _first_existing(candidates) -> Optional[Path]:
        for p in candidates:
            try:
                if p.is_file():
                    return p
            except OSError:
                continue
        return None

    def _setup_styles(self):
        styles = getSampleStyleSheet()

        styles.add(ParagraphStyle(
            'PersianTitle',
            fontName=self.font_name_bold,
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#1a237e'),
        ))

        styles.add(ParagraphStyle(
            'PersianHeading',
            fontName=self.font_name_bold,
            fontSize=14,
            alignment=TA_RIGHT,
            spaceAfter=10,
            spaceBefore=15,
            textColor=colors.HexColor('#283593'),
        ))

        styles.add(ParagraphStyle(
            'PersianBody',
            fontName=self.font_name,
            fontSize=11,
            alignment=TA_RIGHT,
            spaceAfter=6,
            leading=18,
        ))

        styles.add(ParagraphStyle(
            'PersianLabel',
            fontName=self.font_name_bold,
            fontSize=11,
            alignment=TA_RIGHT,
        ))

        styles.add(ParagraphStyle(
            'PersianValue',
            fontName=self.font_name,
            fontSize=11,
            alignment=TA_LEFT,
        ))

        return styles

    def export_contact_profile_pdf(self, contact_id: int, output_path: str = None) -> str:
        contact = contact_repo.get_with_profile(contact_id)
        if not contact:
            raise ValueError("Contact not found")

        profile = contact.profile
        files = file_repo.get_by_contact(contact_id)

        if not output_path:
            output_path = str(self.export_dir / safe_filename(
                f"profile_{contact.id}_{contact.first_name}_{contact.last_name}.pdf",
                fallback=f"profile_{contact.id}.pdf",
            ))

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )

        styles = self._setup_styles()
        elements = []

        elements.append(Paragraph(rtl("پروفایل فرد"), styles['PersianTitle']))
        elements.append(Spacer(1, 10))

        profile_data = [
            ['نام:', contact.first_name, 'نام خانوادگی:', contact.last_name],
            ['موبایل:', contact.mobile, 'تلفن ثابت:', contact.phone or '-'],
            ['کد ملی:', contact.national_code or '-', 'سمت:', contact.position or '-'],
            ['استان:', contact.province or '-', 'شهرستان:', contact.county or '-'],
            ['بخش:', contact.district or '-', 'دهستان:', contact.rural_district or '-'],
            ['روستا:', contact.village or '-', 'کد پستی:', contact.postal_code or '-'],
            ['سازمان:', contact.organization or '-', 'وضعیت:', contact.status.value if contact.status else '-'],
        ]

        gender_labels = {'male': 'مرد', 'female': 'زن'}

        if contact.birth_date:
            gender_label = gender_labels.get(contact.gender.value, '-') if contact.gender else '-'
            profile_data.append(['تاریخ تولد:', contact.birth_date.strftime('%Y/%m/%d'), 'جنسیت:', gender_label])
        if contact.education:
            profile_data.append(['تحصیلات:', contact.education, 'وضعیت تأهل:', (getattr(profile, 'marital_status', None) or '-') if profile else '-'])

        if contact.notes:
            profile_data.append(['یادداشت:', contact.notes, '', ''])

        profile_data = [[rtl(cell) for cell in row] for row in profile_data]

        table = Table(profile_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), self.font_name_bold),
            ('FONTNAME', (2, 0), (2, -1), self.font_name_bold),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#90a4ae')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)

        if files:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph(rtl("فایل‌ها و مدارک"), styles['PersianHeading']))

            file_data = [['عنوان', 'نوع', 'تاریخ آپلود', 'اندازه']]
            for f in files:
                size_kb = f.file_size / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                file_data.append([
                    f.original_name[:30] + '...' if len(f.original_name) > 30 else f.original_name,
                    f.file_category or '-',
                    f.created_at.strftime('%Y/%m/%d') if f.created_at else '-',
                    size_str,
                ])

            file_data = [[rtl(cell) for cell in row] for row in file_data]

            file_table = Table(file_data, colWidths=[6*cm, 3*cm, 3*cm, 3*cm])
            file_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), self.font_name_bold),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#90a4ae')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ]))
            elements.append(file_table)

        doc.build(elements)
        return output_path

    def export_contacts_excel(self, contacts: List[Contact], output_path: str = None, group_name: str = None) -> str:
        if not output_path:
            suffix = f"_{group_name}" if group_name else ""
            output_path = str(self.export_dir / f"contacts{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "مخاطبین"

        header_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
        header_font = Font(name="Tahoma", bold=True, color="FFFFFF", size=11)
        cell_font = Font(name="Tahoma", size=10)
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin'),
        )
        center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        right_align = Alignment(horizontal='right', vertical='center')

        headers = [
            "ردیف", "نام", "نام خانوادگی", "موبایل", "تلفن", "کد ملی", "سمت",
            "استان", "شهرستان", "بخش", "دهستان", "روستا", "آدرس", "وضعیت", "یادداشت"
        ]

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border

        for row_idx, contact in enumerate(contacts, 2):
            row_data = [
                row_idx - 1,
                contact.first_name or "",
                contact.last_name or "",
                contact.mobile or "",
                contact.phone or "",
                contact.national_code or "",
                contact.position or "",
                contact.province or "",
                contact.county or "",
                contact.district or "",
                contact.rural_district or "",
                contact.village or "",
                contact.address or "",
                contact.status.value if contact.status else "",
                contact.notes or "",
            ]
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = cell_font
                cell.border = thin_border
                cell.alignment = center_align if col_idx == 1 else right_align

        column_widths = [6, 14, 16, 14, 12, 12, 14, 11, 11, 11, 11, 12, 28, 10, 22]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

        if contacts:
            ws.auto_filter.ref = f"A1:O{len(contacts) + 1}"
        ws.freeze_panes = "A2"

        wb.save(output_path)
        return output_path

    def export_contacts_csv(self, contacts: List[Contact], output_path: str = None, group_name: str = None) -> str:
        """خروجی سریع CSV"""
        if not output_path:
            suffix = f"_{group_name}" if group_name else ""
            output_path = str(self.export_dir / f"contacts{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

        headers = [
            "ردیف", "نام", "نام خانوادگی", "موبایل", "تلفن", "کد ملی", "سمت",
            "استان", "شهرستان", "بخش", "دهستان", "روستا", "آدرس", "وضعیت", "یادداشت"
        ]

        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for idx, contact in enumerate(contacts, 1):
                writer.writerow([
                    idx,
                    contact.first_name or "",
                    contact.last_name or "",
                    contact.mobile or "",
                    contact.phone or "",
                    contact.national_code or "",
                    contact.position or "",
                    contact.province or "",
                    contact.county or "",
                    contact.district or "",
                    contact.rural_district or "",
                    contact.village or "",
                    contact.address or "",
                    contact.status.value if contact.status else "",
                    contact.notes or "",
                ])

        return output_path

    def export_group_contacts_pdf(self, group_id: int, output_path: str = None) -> str:
        from services.repositories import group_repo
        group = group_repo.get_by_id(group_id)
        if not group:
            raise ValueError("Group not found")

        contacts = contact_repo.get_by_group(group_id)

        if not output_path:
            output_path = str(self.export_dir / safe_filename(
                f"group_{group.name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                fallback=f"group_{group.id}_{datetime.now().strftime('%Y%m%d')}.pdf",
            ))

        doc = SimpleDocTemplate(
            output_path, pagesize=landscape(A4),
            rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm
        )

        styles = self._setup_styles()
        elements = []

        elements.append(Paragraph(rtl(f"لیست اعضای گروه: {group.name}"), styles['PersianTitle']))
        if group.description:
            elements.append(Paragraph(rtl(group.description), styles['PersianBody']))
        elements.append(Spacer(1, 10))

        table_data = [['ردیف', 'نام کامل', 'موبایل', 'تلفن', 'سمت', 'روستا', 'بخش']]
        for idx, c in enumerate(contacts, 1):
            table_data.append([
                str(idx),
                f"{c.first_name} {c.last_name}",
                c.mobile or '-',
                c.phone or '-',
                c.position or '-',
                c.village or '-',
                c.district or '-',
            ])

        table_data = [[rtl(cell) for cell in row] for row in table_data]

        table = Table(table_data, colWidths=[1.5*cm, 4.5*cm, 3*cm, 2.5*cm, 3*cm, 3*cm, 3*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), self.font_name_bold),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#90a4ae')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]))
        elements.append(table)

        elements.append(Spacer(1, 15))
        elements.append(Paragraph(rtl(f"تعداد کل: {len(contacts)} نفر"), styles['PersianBody']))
        elements.append(Paragraph(rtl(f"تاریخ چاپ: {datetime.now().strftime('%Y/%m/%d %H:%M')}"), styles['PersianBody']))

        doc.build(elements)
        return output_path

    def export_all_contacts_pdf(self, output_path: str = None) -> str:
        # «همهٔ مخاطبین» یعنی همه؛ غیرفعال‌ها هم باید در خروجی بیایند
        contacts = contact_repo.get_all(limit=100000)

        if not output_path:
            output_path = str(self.export_dir / f"all_contacts_{datetime.now().strftime('%Y%m%d')}.pdf")

        doc = SimpleDocTemplate(
            output_path, pagesize=landscape(A4),
            rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm
        )

        styles = self._setup_styles()
        elements = []

        elements.append(Paragraph(rtl("لیست کل مخاطبین"), styles['PersianTitle']))
        elements.append(Spacer(1, 10))

        table_data = [['ردیف', 'نام کامل', 'موبایل', 'سمت', 'شهرستان', 'بخش', 'روستا']]
        for idx, c in enumerate(contacts, 1):
            table_data.append([
                str(idx),
                f"{c.first_name} {c.last_name}",
                c.mobile or '-',
                c.position or '-',
                c.county or '-',
                c.district or '-',
                c.village or '-',
            ])

        table_data = [[rtl(cell) for cell in row] for row in table_data]

        table = Table(table_data, colWidths=[1.5*cm, 4.5*cm, 3*cm, 3.5*cm, 3*cm, 2.5*cm, 2.5*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), self.font_name_bold),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#90a4ae')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]))
        elements.append(table)

        doc.build(elements)
        return output_path


export_service = ExportService()