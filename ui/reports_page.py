from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QGridLayout, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QInputDialog, QFileDialog
)
from PyQt5.QtCore import Qt
import html as html_lib
import jdatetime
import os
from datetime import datetime
from ui.styles import Styles, get_font
from ui.theme import theme_manager
from services.repositories import (
    contact_repo, group_repo, message_repo,
    official_repo, calendar_repo, decision_repo, participant_repo
)
from services.export_service import export_service
from models.models import OFFICIAL_POSITION_LABELS


class ReportCard(QFrame):
    def __init__(self, title, value, color, parent=None):
        super().__init__(parent)
        c = theme_manager.current
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {c.canvas_overlay};
                border-radius: 12px;
                border-right: 5px solid {color};
                padding: 15px;
            }}
        """)
        self.setFixedHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 12px; color: {c.fg_muted};")
        layout.addWidget(title_label)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 26px; font-weight: bold; color: {color};"
        )
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self.value_label)

    def update_value(self, value):
        self.value_label.setText(str(value))


class ReportsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self._setup_ui()
        self._load_stats()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("گزارش‌ها و خروجی")
        title.setStyleSheet(Styles.title_label())
        title.setFont(get_font(18, True))
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("بروزرسانی")
        refresh_btn.setStyleSheet(Styles.primary_button())
        refresh_btn.clicked.connect(self._load_stats)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        stats_layout = QGridLayout()
        stats_layout.setSpacing(12)

        self.stat_total = ReportCard("مجموع مخاطبین", "0", c.primary)
        self.stat_active = ReportCard("فعال", "0", c.success)
        self.stat_groups = ReportCard("گروه‌ها", "0", c.primary_subtle)
        self.stat_messages = ReportCard("پیامک‌ها", "0", c.warning)
        self.stat_events = ReportCard("جلسات امسال", "0", c.accent_blue)
        self.stat_officials = ReportCard("مسئولین فعال", "0", c.primary)
        self.stat_decisions_open = ReportCard("مصوبات باز", "0", c.warning)
        self.stat_decisions_overdue = ReportCard("مصوبات عقب‌افتاده", "0", c.accent_red)

        stats_layout.addWidget(self.stat_total, 0, 0)
        stats_layout.addWidget(self.stat_active, 0, 1)
        stats_layout.addWidget(self.stat_groups, 0, 2)
        stats_layout.addWidget(self.stat_messages, 0, 3)
        stats_layout.addWidget(self.stat_events, 1, 0)
        stats_layout.addWidget(self.stat_officials, 1, 1)
        stats_layout.addWidget(self.stat_decisions_open, 1, 2)
        stats_layout.addWidget(self.stat_decisions_overdue, 1, 3)
        layout.addLayout(stats_layout)

        export_group = QGroupBox("خروجی گزارش‌ها")
        export_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
                font-weight: bold;
                color: {c.primary};
                border: 1px solid {c.border_default};
                border-radius: 8px;
                padding: 15px;
                margin-top: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                right: 12px;
            }}
        """)
        export_layout = QVBoxLayout(export_group)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(10)

        export_all_btn = QPushButton("خروجی همه مخاطبین (Excel)")
        export_all_btn.setStyleSheet(Styles.primary_button())
        export_all_btn.clicked.connect(self._export_all_excel)
        btn_grid.addWidget(export_all_btn, 0, 0)

        export_pdf_btn = QPushButton("خروجی همه مخاطبین (PDF)")
        export_pdf_btn.setStyleSheet(Styles.primary_button())
        export_pdf_btn.clicked.connect(self._export_all_pdf)
        btn_grid.addWidget(export_pdf_btn, 0, 1)

        export_active_btn = QPushButton("خروجی مخاطبین فعال (Excel)")
        export_active_btn.setStyleSheet(Styles.success_button())
        export_active_btn.clicked.connect(self._export_active)
        btn_grid.addWidget(export_active_btn, 1, 0)

        export_group_btn = QPushButton("خروجی گروه (PDF)")
        export_group_btn.setStyleSheet(Styles.success_button())
        export_group_btn.clicked.connect(self._export_group_pdf)
        btn_grid.addWidget(export_group_btn, 1, 1)

        export_csv_btn = QPushButton("خروجی CSV (سریع)")
        export_csv_btn.setStyleSheet(Styles.success_button())
        export_csv_btn.clicked.connect(self._export_csv)
        btn_grid.addWidget(export_csv_btn, 2, 0)

        export_layout.addLayout(btn_grid)
        layout.addWidget(export_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        position_frame = QFrame()
        position_frame.setStyleSheet(Styles.card())
        position_layout = QVBoxLayout(position_frame)

        pos_title = QLabel("بر اساس سمت")
        pos_title.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; font-size: 13px;")
        position_layout.addWidget(pos_title)

        self.position_table = QTableWidget()
        self.position_table.setStyleSheet(Styles.table_widget())
        self.position_table.setFont(get_font(10))
        self.position_table.setColumnCount(2)
        self.position_table.setHorizontalHeaderLabels(["سمت", "تعداد"])
        self.position_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.position_table.setAlternatingRowColors(True)
        position_layout.addWidget(self.position_table)
        splitter.addWidget(position_frame)

        district_frame = QFrame()
        district_frame.setStyleSheet(Styles.card())
        district_layout = QVBoxLayout(district_frame)

        dist_title = QLabel("بر اساس بخش")
        dist_title.setStyleSheet(f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.primary}; font-size: 13px;")
        district_layout.addWidget(dist_title)

        self.district_table = QTableWidget()
        self.district_table.setStyleSheet(Styles.table_widget())
        self.district_table.setFont(get_font(10))
        self.district_table.setColumnCount(2)
        self.district_table.setHorizontalHeaderLabels(["بخش", "تعداد"])
        self.district_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.district_table.setAlternatingRowColors(True)
        district_layout.addWidget(self.district_table)
        splitter.addWidget(district_frame)

        splitter.setSizes([400, 400])
        layout.addWidget(splitter)

        # ---------- گزارش فرمانداری: عملکرد مسئولین ----------
        gov_group = QGroupBox("عملکرد مسئولین (سال جاری)")
        gov_group.setStyleSheet(f"""
            QGroupBox {{
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma;
                font-weight: bold;
                color: {c.primary};
                border: 1px solid {c.border_default};
                border-radius: 8px;
                padding: 15px;
                margin-top: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                right: 12px;
            }}
        """)
        gov_layout = QVBoxLayout(gov_group)

        head_row = QHBoxLayout()
        head_hint = QLabel(
            "«جلسه» = تعداد جلساتی که مسئول، صاحب برنامه بوده؛ "
            "«دعوت» = دعوت‌شدگی؛ «حضور» = ثبت‌شده به‌عنوان حاضر."
        )
        head_hint.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 11px; color: {c.fg_muted};")
        head_row.addWidget(head_hint)
        head_row.addStretch()

        print_overdue_btn = QPushButton("چاپ مصوبات عقب‌افتاده")
        print_overdue_btn.setStyleSheet(Styles.secondary_button())
        print_overdue_btn.clicked.connect(self._print_overdue_decisions)
        head_row.addWidget(print_overdue_btn)
        gov_layout.addLayout(head_row)

        self.officials_table = QTableWidget()
        self.officials_table.setStyleSheet(Styles.table_widget())
        self.officials_table.setFont(get_font(10))
        self.officials_table.setColumnCount(4)
        self.officials_table.setHorizontalHeaderLabels(["مسئول", "سمت", "جلسه (صاحب برنامه)", "دعوت / حضور"])
        self.officials_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.officials_table.setAlternatingRowColors(True)
        gov_layout.addWidget(self.officials_table)

        layout.addWidget(gov_group)

    def _print_overdue_decisions(self):
        from ui.program_print import print_document
        try:
            today = jdatetime.date.today().strftime("%Y/%m/%d")
            overdue = [d for d in decision_repo.get_open_with_event()
                       if d.due_date and d.due_date < today]
            if not overdue:
                QMessageBox.information(self, "چاپ گزارش", "مصوبهٔ عقب‌افتاده‌ای وجود ندارد.")
                return

            rows = "".join(
                f"<tr>"
                f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(d.content)}</td>"
                f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(d.assignee_name)}</td>"
                f"<td style='border:1px solid #999; padding:6px;'>{html_lib.escape(d.due_date)}</td>"
                f"<td style='border:1px solid #999; padding:6px;'>"
                f"{html_lib.escape(d.event.title if d.event else '')}</td>"
                f"</tr>"
                for d in overdue
            )
            from core.config import settings as app_settings
            html = f"""
            <div dir="rtl" style="font-family:'Vazirmatn','B Nazanin',Tahoma;">
              <p align="center" style="font-size:13pt; font-weight:bold; margin-bottom:2px;">
                {app_settings.ORGANIZATION} — گزارش مصوبات عقب‌افتاده
              </p>
              <p align="center" style="font-size:11pt; color:#555;">تاریخ گزارش: {today}</p>
              <table width="100%" cellspacing="0" style="font-size:10pt; margin-top:12px;">
                <tr style="background:#efefef;">
                  <th style="border:1px solid #999; padding:6px;">مصوبه</th>
                  <th style="border:1px solid #999; padding:6px;">مسئول اجرا</th>
                  <th style="border:1px solid #999; padding:6px;">مهلت</th>
                  <th style="border:1px solid #999; padding:6px;">جلسه</th>
                </tr>
                {rows}
              </table>
            </div>
            """
            print_document(self, "گزارش مصوبات عقب‌افتاده", html)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _load_stats(self):
        try:
            stats = contact_repo.get_statistics()
            self.stat_total.update_value(stats.get("total", 0))
            self.stat_active.update_value(stats.get("active", 0))

            groups = group_repo.get_with_counts()
            self.stat_groups.update_value(len(groups))

            msg_stats = message_repo.get_statistics()
            self.stat_messages.update_value(msg_stats.get("total", 0))

            year = jdatetime.date.today().year
            events = calendar_repo.get_by_year(year)
            self.stat_events.update_value(len(events))

            officials = official_repo.get_active()
            self.stat_officials.update_value(len(officials))

            d_stats = decision_repo.get_statistics()
            self.stat_decisions_open.update_value(
                d_stats.get("open", 0) + d_stats.get("in_progress", 0))
            self.stat_decisions_overdue.update_value(d_stats.get("overdue", 0))

            owned = {}
            for ev in events:
                if ev.official_id:
                    owned[ev.official_id] = owned.get(ev.official_id, 0) + 1
            attendance = participant_repo.count_by_official(year)

            self.officials_table.setRowCount(len(officials))
            for row, o in enumerate(officials):
                att = attendance.get(o.id, {"invited": 0, "attended": 0})
                self.officials_table.setItem(row, 0, QTableWidgetItem(o.display_name))
                self.officials_table.setItem(
                    row, 1, QTableWidgetItem(OFFICIAL_POSITION_LABELS.get(o.position, "-")))
                self.officials_table.setItem(
                    row, 2, QTableWidgetItem(str(owned.get(o.id, 0))))
                self.officials_table.setItem(
                    row, 3, QTableWidgetItem(f"{att['invited']} / {att['attended']}"))

            pos_data = stats.get("by_position", {})
            self.position_table.setRowCount(len(pos_data))
            for row, (pos, count) in enumerate(pos_data.items()):
                self.position_table.setItem(row, 0, QTableWidgetItem(pos or "نامشخص"))
                self.position_table.setItem(row, 1, QTableWidgetItem(str(count)))

            dist_data = stats.get("by_district", {})
            self.district_table.setRowCount(len(dist_data))
            for row, (dist, count) in enumerate(dist_data.items()):
                self.district_table.setItem(row, 0, QTableWidgetItem(dist or "نامشخص"))
                self.district_table.setItem(row, 1, QTableWidgetItem(str(count)))

        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در بارگذاری آمار:\n{str(e)}")

    # ---------- خروجی: انتخاب محل ذخیره توسط کاربر ----------

    def _ask_save_path(self, title, default_name, filter_str):
        """دیالوگ «ذخیرهٔ فایل»؛ مسیر پیش‌فرض پوشهٔ خروجی برنامه است.
        اگر کاربر لغو کند None برمی‌گردد."""
        try:
            default_dir = str(export_service.export_dir)
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, title, os.path.join(default_dir, default_name), filter_str
        )
        return path or None

    def _notify_saved(self, path):
        """پیام موفقیت + گزینهٔ باز کردن پوشهٔ ذخیره"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("موفق")
        box.setText(f"فایل ذخیره شد:\n{path}")
        open_btn = box.addButton("باز کردن پوشه", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() == open_btn:
            try:
                os.startfile(os.path.dirname(path))
            except Exception:
                pass

    def _export_all_excel(self):
        try:
            contacts = contact_repo.get_all(limit=100000)
            if not contacts:
                QMessageBox.warning(self, "هشدار", "مخاطبی برای خروجی یافت نشد")
                return
            path = self._ask_save_path(
                "ذخیرهٔ فایل Excel",
                f"contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "Excel (*.xlsx)",
            )
            if not path:
                return
            saved = export_service.export_contacts_excel(contacts, output_path=path)
            self._notify_saved(saved)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _export_all_pdf(self):
        try:
            if not contact_repo.get_all(limit=1):
                QMessageBox.warning(self, "هشدار", "مخاطبی برای خروجی یافت نشد")
                return
            path = self._ask_save_path(
                "ذخیرهٔ فایل PDF",
                f"all_contacts_{datetime.now().strftime('%Y%m%d')}.pdf",
                "PDF (*.pdf)",
            )
            if not path:
                return
            saved = export_service.export_all_contacts_pdf(output_path=path)
            self._notify_saved(saved)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _export_active(self):
        try:
            contacts = contact_repo.get_active(limit=10000)
            if not contacts:
                QMessageBox.warning(self, "هشدار", "مخاطب فعالی برای خروجی یافت نشد")
                return
            path = self._ask_save_path(
                "ذخیرهٔ فایل Excel",
                f"contacts_active_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "Excel (*.xlsx)",
            )
            if not path:
                return
            saved = export_service.export_contacts_excel(
                contacts, output_path=path, group_name="فعال"
            )
            self._notify_saved(saved)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _export_group_pdf(self):
        groups = group_repo.get_with_counts()
        if not groups:
            QMessageBox.warning(self, "هشدار", "گروهی یافت نشد")
            return

        names = [g_data["group"].name for g_data in groups]
        name, ok = QInputDialog.getItem(self, "انتخاب گروه", "گروه:", names, 0, False)
        if ok and name:
            for g_data in groups:
                if g_data["group"].name == name:
                    try:
                        safe = "".join(ch for ch in name if ch.isalnum() or ch in "_- ").strip() or "group"
                        path = self._ask_save_path(
                            "ذخیرهٔ فایل PDF گروه",
                            f"group_{safe}.pdf",
                            "PDF (*.pdf)",
                        )
                        if not path:
                            return
                        saved = export_service.export_group_contacts_pdf(
                            g_data["group"].id, output_path=path
                        )
                        self._notify_saved(saved)
                    except Exception as e:
                        QMessageBox.critical(self, "خطا", str(e))
                    break

    def _export_csv(self):
        try:
            contacts = contact_repo.get_active(limit=20000)
            if not contacts:
                QMessageBox.warning(self, "هشدار", "مخاطبی برای خروجی یافت نشد")
                return
            path = self._ask_save_path(
                "ذخیرهٔ فایل CSV",
                f"contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "CSV (*.csv)",
            )
            if not path:
                return
            saved = export_service.export_contacts_csv(contacts, output_path=path)
            self._notify_saved(saved)
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))

    def refresh(self):
        self._load_stats()