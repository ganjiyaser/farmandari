from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QCheckBox, QMessageBox, QGroupBox, QFileDialog,
    QColorDialog, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from ui.styles import Styles, get_font
from ui.theme import theme_manager, CustomColors
from services.repositories import setting_repo


class ColorButton(QPushButton):
    def __init__(self, color="", parent=None):
        super().__init__(parent)
        self._color = color or ""
        self.setFixedSize(40, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _update_style(self):
        c = theme_manager.current
        bg = self._color if self._color else c.input_placeholder
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: 2px solid {c.border_default};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {c.accent_blue};
            }}
        """)

    def _pick_color(self):
        initial = QColor(self._color) if self._color else QColor("#ffffff")
        color = QColorDialog.getColor(initial, self, "انتخاب رنگ")
        if color.isValid():
            self._color = color.name()
            self._update_style()

    def get_color(self) -> str:
        return self._color

    def set_color(self, color: str):
        self._color = color or ""
        self._update_style()


class ColorSettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(get_font(10))
        self.color_buttons = {}
        self._setup_ui()
        self._load_custom_colors()

    def _setup_ui(self):
        c = theme_manager.current
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title = QLabel("تنظیمات رنگ سفارشی")
        title.setFont(get_font(14, True))
        title.setStyleSheet(
            f"color: {c.fg_default}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.apply_check = QCheckBox("فعال‌سازی رنگ‌های سفارشی")
        self.apply_check.setChecked(theme_manager.apply_custom)
        self.apply_check.setStyleSheet(
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default};"
        )
        self.apply_check.toggled.connect(self._on_apply_toggled)
        header_layout.addWidget(self.apply_check)
        layout.addLayout(header_layout)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)

        groups = [
            ("رنگ‌های اصلی", [
                ("رنگ اصلی (Primary)", "primary"),
                ("رنگ موفقیت", "success"),
                ("رنگ خطا", "danger"),
                ("رنگ هشدار", "warning"),
                ("رنگ اطلاعات", "info"),
            ]),
            ("رنگ‌های پس‌زمینه", [
                ("پس‌زمینه اصلی", "bg_default"),
                ("پس‌زمینه فرعی", "bg_subtle"),
                ("پس‌زمینه کارت‌ها", "bg_card"),
                ("پس‌زمینه سایدبار", "bg_sidebar"),
                ("پس‌زمینه هدر", "bg_header"),
            ]),
            ("رنگ‌های متن", [
                ("متن اصلی", "text_primary"),
                ("متن فرعی", "text_secondary"),
            ]),
            ("رنگ‌های حاشیه", [
                ("حاشیه پیش‌فرض", "border_default"),
            ]),
            ("رنگ‌های لهجه", [
                ("آبی", "accent_blue"),
                ("بنفش", "accent_purple"),
                ("نارنجی", "accent_orange"),
                ("سبز", "accent_green"),
            ]),
        ]

        for group_title, colors in groups:
            group = QGroupBox(group_title)
            group.setStyleSheet(f"""
                QGroupBox {{
                    font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                    border: 1px solid {c.border_default}; border-radius: 6px;
                    padding: 12px; margin-top: 8px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin; left: 12px; padding: 0 6px;
                    background: {c.canvas_overlay};
                }}
            """)
            grid = QGridLayout()
            grid.setSpacing(8)

            for i, (label_text, key) in enumerate(colors):
                row = i // 3
                col = (i % 3) * 2

                lbl = QLabel(label_text)
                lbl.setStyleSheet(
                    f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 11px;"
                )
                grid.addWidget(lbl, row * 2, col, Qt.AlignmentFlag.AlignRight)

                btn = ColorButton()
                self.color_buttons[key] = btn
                grid.addWidget(btn, row * 2, col + 1)

            group.setLayout(grid)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        layout.addWidget(scroll_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        save_btn = QPushButton("ذخیره رنگ‌ها")
        save_btn.setStyleSheet(Styles.primary_button())
        save_btn.clicked.connect(self._save_colors)
        btn_layout.addWidget(save_btn)

        reset_btn = QPushButton("بازنشانی پیش‌فرض")
        reset_btn.setStyleSheet(Styles.secondary_button())
        reset_btn.clicked.connect(self._reset_colors)
        btn_layout.addWidget(reset_btn)

        export_btn = QPushButton("خروجی JSON")
        export_btn.setStyleSheet(Styles.secondary_button())
        export_btn.clicked.connect(self._export_colors)
        btn_layout.addWidget(export_btn)

        import_btn = QPushButton("ورودی JSON")
        import_btn.setStyleSheet(Styles.secondary_button())
        import_btn.clicked.connect(self._import_colors)
        btn_layout.addWidget(import_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _load_custom_colors(self):
        custom = theme_manager.custom_overrides  # returns CustomColors instance
        for key, btn in self.color_buttons.items():
            val = getattr(custom, key, "") or ""
            if val:
                btn.set_color(val)

    def _on_apply_toggled(self, checked):
        theme_manager.set_apply_custom(checked)
        main_window = self.window()
        if hasattr(main_window, "_apply_theme_style"):
            main_window._apply_theme_style()
        self._repaint_all(main_window)

    def _save_colors(self):
        custom = CustomColors()
        for key, btn in self.color_buttons.items():
            color = btn.get_color()
            if color:
                setattr(custom, key, color)

        theme_manager.set_custom_colors(custom)
        setting_repo.set_setting("custom_colors", custom.to_dict())

        main_window = self.window()
        if hasattr(main_window, "_apply_theme_style"):
            main_window._apply_theme_style()
        self._repaint_all(main_window)

        QMessageBox.information(self, "موفق", "رنگ‌ها ذخیره شدند و بلافاصله اعمال شدند")

    def _reset_colors(self):
        theme_manager.reset_custom_colors()
        setting_repo.set_setting("custom_colors", {})

        for btn in self.color_buttons.values():
            btn.set_color("")

        main_window = self.window()
        if hasattr(main_window, "_apply_theme_style"):
            main_window._apply_theme_style()
        self._repaint_all(main_window)

        QMessageBox.information(self, "موفق", "رنگ‌ها به حالت پیش‌فرض بازگشتند")

    def _repaint_all(self, widget):
        if widget is None:
            return
        from PyQt6.QtWidgets import QApplication
        for w in QApplication.allWidgets():
            try:
                w.repaint()
            except Exception:
                pass

    def _export_colors(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره تنظیمات رنگ", "theme_colors.json",
            "فایل JSON (*.json)"
        )
        if path:
            try:
                data = theme_manager.export_custom_colors()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data)
                QMessageBox.information(self, "موفق", f"فایل ذخیره شد:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))

    def _import_colors(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل رنگ", "", "فایل JSON (*.json)"
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                if theme_manager.import_custom_colors(data):
                    custom = theme_manager.custom_overrides
                    setting_repo.set_setting("custom_colors", custom.to_dict())
                    self._load_custom_colors()

                    main_window = self.window()
                    if hasattr(main_window, "_apply_theme_style"):
                        main_window._apply_theme_style()
                    self._repaint_all(main_window)

                    QMessageBox.information(self, "موفق", "رنگ‌ها با موفقیت وارد شدند")
                else:
                    QMessageBox.warning(self, "خطا", "فایل معتبر نیست")
            except Exception as e:
                QMessageBox.critical(self, "خطا", str(e))

    def refresh(self):
        c = theme_manager.current
        self.setStyleSheet(f"background: {c.canvas_default};")

        header = self.layout().itemAt(0).layout()
        if header:
            title = header.itemAt(0).widget()
            if title:
                title.setStyleSheet(
                    f"color: {c.fg_default}; font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold;"
                )
            apply_check = header.itemAt(2).widget() if header.count() > 2 else None
            if apply_check and isinstance(apply_check, QCheckBox):
                apply_check.setStyleSheet(
                    f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_default};"
                )

        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(f"""
                QGroupBox {{
                    font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-weight: bold; color: {c.fg_default};
                    border: 1px solid {c.border_default}; border-radius: 6px;
                    padding: 12px; margin-top: 8px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin; left: 12px; padding: 0 6px;
                    background: {c.canvas_overlay};
                }}
            """)
            for label in group.findChildren(QLabel):
                label.setStyleSheet(
                    f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; color: {c.fg_muted}; font-size: 11px;"
                )

        for btn in self.color_buttons.values():
            btn._update_style()

        for btn in self.findChildren(QPushButton):
            text = btn.text()
            if text == "ذخیره رنگ‌ها":
                btn.setStyleSheet(Styles.primary_button())
            elif text in ("بازنشانی پیش‌فرض", "خروجی JSON", "ورودی JSON"):
                btn.setStyleSheet(Styles.secondary_button())
