"""
سیستم طراحی مرکزی برنامه - بر اساس GitHub Primer Design System
تمام صفحات باید ظاهر خودشان را از اینجا بگیرند تا یکدست و حرفه‌ای بمانند.
"""
from PyQt5.QtGui import QFont
from ui.theme import theme_manager

# --- پشته‌ی فونت حرفه‌ای -------------------------------------------------
FONT_STACK = ["Vazirmatn", "IRANSansX", "Segoe UI", "Tahoma"]
FONT_FAMILY = FONT_STACK[0]
FONT_CSS = ", ".join(f"'{f}'" if " " in f else f for f in FONT_STACK)


def alpha(color: str, a: int) -> str:
    """Hex colour with an alpha channel, written the way Qt expects.

    Qt parses an 8-digit hex as ``#AARRGGBB`` (alpha FIRST). Appending the
    alpha at the end the way web CSS does -- ``f"{color}15"`` -- therefore
    yielded ``#0969da15`` = alpha 0x09 with RGB ``#699da1``: a ~3% tint of
    a completely different hue instead of the intended 8% blue.
    """
    hexs = color.lstrip("#")
    if len(hexs) != 6:
        return color
    return f"#{a & 0xFF:02x}{hexs}"

# --- مقیاس فاصله‌گذاری و اندازه (Design tokens) ---------------------------
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 12
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24

FS_TITLE = 20
FS_SUBTITLE = 12
FS_SECTION = 14
FS_BODY = 13
FS_SMALL = 11
FS_TINY = 10

CTRL_HEIGHT = 36
BTN_HEIGHT = 34


def get_font(size=11, bold=False):
    f = QFont()
    f.setFamilies(FONT_STACK)
    f.setPointSize(size)
    f.setBold(bold)
    return f


class Styles:
    """استایل‌های واحد بر اساس GitHub Primer + Fluent Design"""
    
    @staticmethod
    def _c():
        return theme_manager.current

    # ------------------------------------------------------------------ #
    #  دکمه‌ها (GitHub Primer Button Styles)
    # ------------------------------------------------------------------ #
    @staticmethod
    def primary_button():
        """دکمه اصلی - GitHub Primary Button"""
        c = Styles._c()
        return f"""
            QPushButton, PrimaryPushButton {{
                background-color: {c.primary};
                color: {c.fg_on_emphasis};
                border: 1px solid {c.primary};
                border-radius: {RADIUS_SM}px;
                padding: 6px 16px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 600;
                min-height: {BTN_HEIGHT}px;
            }}
            QPushButton:hover, PrimaryPushButton:hover {{
                background-color: {c.primary_hover};
                border-color: {c.primary_hover};
            }}
            QPushButton:pressed, PrimaryPushButton:pressed {{
                background-color: {c.primary_active};
                border-color: {c.primary_active};
            }}
            QPushButton:disabled, PrimaryPushButton:disabled {{
                background-color: {c.control_bg};
                color: {c.fg_muted};
                border-color: {c.border_default};
            }}
        """

    @staticmethod
    def danger_button():
        """دکمه خطرناک - GitHub Danger Button"""
        c = Styles._c()
        return f"""
            QPushButton {{
                background-color: {c.danger};
                color: {c.fg_on_emphasis};
                border: 1px solid {c.danger};
                border-radius: {RADIUS_SM}px;
                padding: 6px 16px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 600;
                min-height: {BTN_HEIGHT}px;
            }}
            QPushButton:hover {{
                background-color: {c.danger_hover};
                border-color: {c.danger_hover};
            }}
            QPushButton:pressed {{
                background-color: {c.danger_active};
                border-color: {c.danger_active};
            }}
            QPushButton:disabled {{
                background-color: {c.control_bg};
                color: {c.fg_muted};
                border-color: {c.border_default};
            }}
        """

    @staticmethod
    def success_button():
        """دکمه موفقیت - GitHub Success Button"""
        c = Styles._c()
        return f"""
            QPushButton {{
                background-color: {c.success};
                color: {c.fg_on_emphasis};
                border: 1px solid {c.success};
                border-radius: {RADIUS_SM}px;
                padding: 6px 16px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 600;
                min-height: {BTN_HEIGHT}px;
            }}
            QPushButton:hover {{
                background-color: {c.success_hover};
                border-color: {c.success_hover};
            }}
            QPushButton:pressed {{
                background-color: {c.success_active};
                border-color: {c.success_active};
            }}
        """

    @staticmethod
    def secondary_button():
        """دکمه ثانویه - GitHub Secondary Button"""
        c = Styles._c()
        return f"""
            QPushButton, SecondaryPushButton {{
                background-color: {c.control_bg};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_SM}px;
                padding: 6px 16px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 500;
                min-height: {BTN_HEIGHT}px;
            }}
            QPushButton:hover, SecondaryPushButton:hover {{
                background-color: {c.control_hover};
                border-color: {c.control_border_hover};
            }}
            QPushButton:pressed, SecondaryPushButton:pressed {{
                background-color: {c.control_active};
            }}
            QPushButton:disabled, SecondaryPushButton:disabled {{
                background-color: {c.control_bg};
                color: {c.fg_muted};
                border-color: {c.border_default};
            }}
        """

    @staticmethod
    def transparent_button():
        """دکمه شفاف - GitHub Invisible Button"""
        c = Styles._c()
        return f"""
            QPushButton, TransparentPushButton {{
                background-color: transparent;
                color: {c.fg_default};
                border: 1px solid transparent;
                border-radius: {RADIUS_SM}px;
                padding: 6px 12px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 500;
                min-height: {BTN_HEIGHT}px;
            }}
            QPushButton:hover, TransparentPushButton:hover {{
                background-color: {c.control_hover};
                color: {c.fg_default};
            }}
            QPushButton:pressed, TransparentPushButton:pressed {{
                background-color: {c.control_active};
            }}
        """

    @staticmethod
    def icon_button():
        """دکمه آیکون مربعی کوچک"""
        c = Styles._c()
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c.fg_muted};
                border: 1px solid transparent;
                border-radius: {RADIUS_SM}px;
                padding: 6px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                min-width: 32px;
                min-height: 32px;
            }}
            QPushButton:hover {{
                background-color: {c.control_hover};
                color: {c.fg_default};
                border-color: {c.border_default};
            }}
            QPushButton:pressed {{
                background-color: {c.control_active};
            }}
        """

    @staticmethod
    def table_action_button(variant: str = "neutral", font_size: int = None):
        """دکمهٔ فشردهٔ داخل سلول جدول (ستون «عملیات»).

        برخلاف secondary/danger_button هیچ min-height و padding بزرگ ندارد تا
        با setFixedHeight کوچک هماهنگ بماند و از ارتفاع ردیف جدول بیرون نزند؛
        وگرنه متن دکمه بریده (ناخوانا) و ناحیهٔ کلیک آن از سلول خارج می‌شود.
        variant: neutral | subtle | danger | primary | success | warning
        font_size: برای بزرگ‌نمایی جدول؛ پیش‌فرض FS_SMALL است.
        """
        c = Styles._c()
        variants = {
            "danger": (c.danger, c.fg_on_emphasis, c.danger, c.danger_hover),
            "primary": (c.primary, c.fg_on_emphasis, c.primary, c.primary_hover),
            "success": (c.success, c.fg_on_emphasis, c.success, c.success),
            "warning": (c.warning, c.fg_on_emphasis, c.warning, c.warning_hover),
            "subtle": (c.canvas_subtle, c.fg_default, c.border_default, c.border_default),
            "neutral": (c.control_bg, c.fg_default, c.border_default, c.control_hover),
        }
        bg, fg, border, bg_hover = variants.get(variant, variants["neutral"])
        btn_fs = FS_SMALL if font_size is None else int(font_size)
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: {RADIUS_SM}px;
                padding: 2px 8px;
                font-size: {btn_fs}px;
                font-family: {FONT_CSS};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
        """

    @staticmethod
    def table_action_buttons(font_size: int = None):
        """QSS دکمه‌های ستون «عملیات» با انتخاب‌گر ویژگی پویای variant

        به‌جای setStyleSheet روی هر دکمه (با هزاران ردیف یعنی هزاران repolish
        هنگام بزرگ‌نمایی)، یک بار روی جدول ست می‌شود و به فرزندانش اعمال
        می‌گردد. دکمه‌ها باید variant را با setProperty ست کرده باشند.
        """
        c = Styles._c()
        fs = FS_SMALL if font_size is None else int(font_size)
        variants = {
            "danger": (c.danger, c.fg_on_emphasis, c.danger, c.danger_hover),
            "primary": (c.primary, c.fg_on_emphasis, c.primary, c.primary_hover),
            "success": (c.success, c.fg_on_emphasis, c.success, c.success),
            "warning": (c.warning, c.fg_on_emphasis, c.warning, c.warning_hover),
            "subtle": (c.canvas_subtle, c.fg_default, c.border_default, c.border_default),
            "neutral": (c.control_bg, c.fg_default, c.border_default, c.control_hover),
        }
        rules = []
        for name, (bg, fg, border, bg_hover) in variants.items():
            rules.append(f"""
            QPushButton[variant="{name}"] {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: {RADIUS_SM}px;
                padding: 2px 8px;
                font-size: {fs}px;
                font-family: {FONT_CSS};
                font-weight: 500;
            }}
            QPushButton[variant="{name}"]:hover {{
                background-color: {bg_hover};
            }}""")
        return "\n".join(rules)

    # ------------------------------------------------------------------ #
    #  ورودی‌ها (GitHub Primer Form Controls)
    # ------------------------------------------------------------------ #
    @staticmethod
    def line_edit():
        c = Styles._c()
        return f"""
            QLineEdit, LineEdit, SearchLineEdit, PasswordLineEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: {RADIUS_SM}px;
                padding: 7px 12px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                min-height: {CTRL_HEIGHT}px;
                selection-background-color: {c.selection_bg};
            }}
            QLineEdit:focus, LineEdit:focus, SearchLineEdit:focus, PasswordLineEdit:focus {{
                border: 1px solid {c.input_border_hover};
                outline: none;
            }}
            QLineEdit:disabled, LineEdit:disabled {{
                background-color: {c.control_bg};
                color: {c.fg_muted};
                border-color: {c.border_default};
            }}
            QLineEdit::placeholder, LineEdit::placeholder {{
                color: {c.input_placeholder};
            }}
        """

    @staticmethod
    def search_input():
        """کادر جست‌وجوی گرد برای بالای صفحات لیستی."""
        c = Styles._c()
        return f"""
            QLineEdit, SearchLineEdit {{
                background-color: {c.canvas_subtle};
                border: 1px solid transparent;
                border-radius: {CTRL_HEIGHT // 2}px;
                padding: 7px 16px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                min-height: {CTRL_HEIGHT}px;
            }}
            QLineEdit:focus, SearchLineEdit:focus {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border_hover};
            }}
            QLineEdit::placeholder {{
                color: {c.input_placeholder};
            }}
        """

    @staticmethod
    def combo_box():
        c = Styles._c()
        return f"""
            QComboBox, ComboBox {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: {RADIUS_SM}px;
                padding: 7px 12px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                min-height: {CTRL_HEIGHT}px;
            }}
            QComboBox:hover, ComboBox:hover {{
                border-color: {c.control_border_hover};
            }}
            QComboBox:focus, ComboBox:focus {{
                border-color: {c.input_border_hover};
            }}
            QComboBox::drop-down, ComboBox::drop-down {{
                border: none;
                width: 28px;
                subcontrol-origin: padding;
                subcontrol-position: center left;
            }}
            QComboBox QAbstractItemView, ComboBox QAbstractItemView {{
                background-color: {c.canvas_overlay};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                selection-background-color: {c.selection_bg};
                selection-color: {c.selection_fg};
                border-radius: {RADIUS_SM}px;
                padding: 4px;
                outline: none;
            }}
        """

    @staticmethod
    def text_edit():
        c = Styles._c()
        return f"""
            QTextEdit, TextEdit, PlainTextEdit {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: {RADIUS_SM}px;
                padding: 10px 12px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                selection-background-color: {c.selection_bg};
            }}
            QTextEdit:focus, TextEdit:focus {{
                border: 1px solid {c.input_border_hover};
            }}
            QTextEdit:disabled, TextEdit:disabled {{
                background-color: {c.control_bg};
                color: {c.fg_muted};
                border-color: {c.border_default};
            }}
        """

    # ------------------------------------------------------------------ #
    #  جدول‌ها (GitHub Primer Table)
    # ------------------------------------------------------------------ #
    @staticmethod
    def table_widget(font_size=None, header_font_size=None, item_padding=None, header_padding=None):
        """QSS جدول؛ آرگومان‌ها برای بزرگ‌نمایی (Zoom) صفحهٔ مخاطبین

        font-size و padding داخل QSS هستند، پس setFont به‌تنهایی اثری ندارد؛
        برای zoom باید همین مقادیر مقیاس شوند.
        """
        c = Styles._c()
        body_fs = FS_BODY if font_size is None else int(font_size)
        head_fs = FS_SMALL if header_font_size is None else int(header_font_size)
        item_pad = "8px 12px" if item_padding is None else item_padding
        head_pad = "8px 12px" if header_padding is None else header_padding
        return f"""
            QTableWidget, TableWidget {{
                background-color: {c.canvas_default};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
                gridline-color: transparent;
                font-size: {body_fs}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                alternate-background-color: {c.canvas_subtle};
                selection-background-color: {c.selection_bg};
                selection-color: {c.fg_default};
                outline: none;
            }}
            QTableWidget::item {{
                padding: {item_pad};
                border-bottom: 1px solid {c.border_default};
            }}
            QTableWidget::item:selected {{
                background-color: {c.selection_bg};
                color: {c.fg_default};
            }}
            QHeaderView::section {{
                background-color: {c.canvas_subtle};
                color: {c.fg_default};
                padding: {head_pad};
                border: none;
                border-bottom: 1px solid {c.border_default};
                font-size: {head_fs}px;
                font-family: {FONT_CSS};
                font-weight: 600;
                text-align: right;
            }}
            QHeaderView::section:first {{ border-top-right-radius: {RADIUS_MD}px; }}
            QHeaderView::section:last {{ border-top-left-radius: {RADIUS_MD}px; }}
        """

    # ------------------------------------------------------------------ #
    #  کارت‌ها و کانتینرها (GitHub Primer Box/Card)
    # ------------------------------------------------------------------ #
    @staticmethod
    def card():
        c = Styles._c()
        return f"""
            QFrame, CardWidget, SimpleCardWidget, ElevatedCardWidget {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
            }}
            QLabel {{ border: none; background-color: transparent; border-radius: 0; padding: 0; margin: 0; }}
        """

    @staticmethod
    def card_with_padding(padding=SPACE_MD):
        c = Styles._c()
        return f"""
            QFrame, CardWidget, SimpleCardWidget, ElevatedCardWidget {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
                padding: {padding}px;
            }}
            QLabel {{ border: none; background-color: transparent; border-radius: 0; padding: 0; margin: 0; }}
        """

    @staticmethod
    def stat_card(accent_color=None):
        c = Styles._c()
        if accent_color is None:
            accent_color = c.accent_blue
        return f"""
            QFrame, CardWidget, SimpleCardWidget, ElevatedCardWidget {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_MD}px;
            }}
            QFrame:hover, CardWidget:hover {{ border-color: {accent_color}; }}
            QLabel {{ border: none; background-color: transparent; border-radius: 0; padding: 0; margin: 0; }}
            QLabel#value {{ color: {accent_color}; }}
        """

    # ------------------------------------------------------------------ #
    #  متن‌ها (GitHub Primer Typography)
    # ------------------------------------------------------------------ #
    @staticmethod
    def title_label():
        c = Styles._c()
        return f"""
            QLabel {{
                font-size: {FS_TITLE}px;
                font-family: {FONT_CSS};
                font-weight: 600;
                color: {c.fg_default};
                padding: 0;
            }}
        """

    @staticmethod
    def section_title_label():
        c = Styles._c()
        return f"""
            QLabel {{
                font-size: {FS_SECTION}px;
                font-family: {FONT_CSS};
                font-weight: 600;
                color: {c.fg_default};
                padding: 0;
            }}
        """

    @staticmethod
    def subtitle_label():
        c = Styles._c()
        return f"""
            QLabel {{
                font-size: {FS_SUBTITLE}px;
                font-family: {FONT_CSS};
                color: {c.fg_muted};
                padding: 0;
            }}
        """

    @staticmethod
    def body_label():
        c = Styles._c()
        return f"""
            QLabel {{
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                padding: 0;
            }}
        """

    @staticmethod
    def muted_label():
        c = Styles._c()
        return f"""
            QLabel {{
                font-size: {FS_SMALL}px;
                font-family: {FONT_CSS};
                color: {c.fg_muted};
                padding: 0;
            }}
        """

    @staticmethod
    def empty_state_label():
        c = Styles._c()
        return f"""
            QLabel {{
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_muted};
                padding: {SPACE_LG}px;
            }}
        """

    # ------------------------------------------------------------------ #
    #  بейج‌ها و وضعیت‌ها (GitHub Primer Badges/States)
    # ------------------------------------------------------------------ #
    @staticmethod
    def badge(color=None, variant="default"):
        """GitHub Primer Labels/Badges
        variant: default, outline, subtle
        """
        c = Styles._c()
        if color is None:
            color = c.accent_blue
        
        if variant == "subtle":
            bg = alpha(color, 0x15)  # 8% opacity
            border = "transparent"
        elif variant == "outline":
            bg = "transparent"
            border = f"1px solid {color}"
        else:
            bg = alpha(color, 0x22)  # 13% opacity
            border = "transparent"
        
        return f"""
            QLabel {{
                background-color: {bg};
                color: {color};
                border: {border};
                border-radius: 12px;
                padding: 2px 10px;
                font-size: {FS_TINY}px;
                font-family: {FONT_CSS};
                font-weight: 600;
            }}
        """

    @staticmethod
    def status_badge(status: str):
        """بейج وضعیت: success, danger, warning, info, default"""
        c = Styles._c()
        colors = {
            "success": c.success,
            "danger": c.danger,
            "warning": c.warning,
            "info": c.accent_blue,
            "default": c.fg_muted,
        }
        color = colors.get(status, colors["default"])
        return Styles.badge(color, "subtle")

    # ------------------------------------------------------------------ #
    #  کانتینرهای صفحه
    # ------------------------------------------------------------------ #
    @staticmethod
    def page_header_container():
        c = Styles._c()
        return f"""
            QFrame {{
                background-color: {c.canvas_overlay};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_MD}px {SPACE_LG}px;
            }}
        """

    @staticmethod
    def page_container():
        c = Styles._c()
        return f"""
            QFrame {{
                background-color: {c.canvas_default};
                border: none;
            }}
        """

    @staticmethod
    def section_container():
        c = Styles._c()
        return f"""
            QFrame {{
                background-color: {c.canvas_subtle};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_MD}px;
            }}
        """

    # ------------------------------------------------------------------ #
    #  تب‌ها (GitHub Primer Tabs)
    # ------------------------------------------------------------------ #
    @staticmethod
    def tab_bar_button(active=False):
        c = Styles._c()
        if active:
            return f"""
                QPushButton {{
                    background-color: {alpha(c.primary, 0x15)};
                    color: {c.primary};
                    border: 1px solid {c.primary};
                    border-radius: {RADIUS_SM}px;
                    padding: 6px 16px;
                    font-size: {FS_SMALL}px;
                    font-family: {FONT_CSS};
                    font-weight: 600;
                }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c.fg_muted};
                border: 1px solid transparent;
                border-radius: {RADIUS_SM}px;
                padding: 6px 16px;
                font-size: {FS_SMALL}px;
                font-family: {FONT_CSS};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {c.control_hover};
                color: {c.fg_default};
            }}
        """

    # ------------------------------------------------------------------ #
    #  کنترل‌های فرم خاص
    # ------------------------------------------------------------------ #
    @staticmethod
    def spin_box():
        c = Styles._c()
        return f"""
            QSpinBox, DoubleSpinBox, SpinBox {{
                background-color: {c.input_bg};
                border: 1px solid {c.input_border};
                border-radius: {RADIUS_SM}px;
                padding: 7px 12px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
                min-height: {CTRL_HEIGHT}px;
            }}
            QSpinBox:focus, DoubleSpinBox:focus {{
                border: 1px solid {c.input_border_hover};
            }}
        """

    @staticmethod
    def checkbox():
        c = Styles._c()
        return f"""
            QCheckBox, CheckBox {{
                color: {c.fg_default};
                spacing: 8px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
            }}
            QCheckBox::indicator, CheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {c.border_default};
                background-color: {c.input_bg};
            }}
            QCheckBox::indicator:checked, CheckBox::indicator:checked {{
                background-color: {c.primary};
                border-color: {c.primary};
                image: url(:/qfluentwidgets/check.svg);
            }}
        """

    @staticmethod
    def radio_button():
        c = Styles._c()
        return f"""
            QRadioButton, RadioButton {{
                color: {c.fg_default};
                spacing: 8px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
            }}
            QRadioButton::indicator, RadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid {c.border_default};
                background-color: {c.input_bg};
            }}
            QRadioButton::indicator:checked, RadioButton::indicator:checked {{
                border: 4px solid {c.primary};
                background-color: {c.input_bg};
            }}
        """

    @staticmethod
    def scroll_area():
        c = Styles._c()
        return f"""
            QScrollArea, ScrollArea, SmoothScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
        """

    @staticmethod
    def group_box():
        c = Styles._c()
        return f"""
            QGroupBox {{
                font-family: {FONT_CSS};
                font-weight: 600;
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_MD}px;
                margin-top: {SPACE_MD}px;
                padding: {SPACE_MD}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {SPACE_MD}px;
                padding: 0 {SPACE_SM}px;
                background: {c.canvas_overlay};
            }}
        """

    @staticmethod
    def tooltip():
        c = Styles._c()
        return f"""
            QToolTip {{
                background-color: {c.canvas_overlay};
                color: {c.fg_default};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_SM}px;
                padding: 6px 10px;
                font-size: {FS_TINY}px;
                font-family: {FONT_CSS};
            }}
        """

    @staticmethod
    def progress_bar():
        c = Styles._c()
        return f"""
            QProgressBar {{
                background-color: {c.control_bg};
                border: 1px solid {c.border_default};
                border-radius: {RADIUS_SM}px;
                text-align: center;
                height: 8px;
                font-size: {FS_TINY}px;
                font-family: {FONT_CSS};
                color: {c.fg_default};
            }}
            QProgressBar::chunk {{
                background-color: {c.primary};
                border-radius: {RADIUS_SM}px;
            }}
        """

    @staticmethod
    def divider():
        c = Styles._c()
        return f"""
            QFrame[frameShape="4"] {{  /* HLine */
                border: none;
                border-top: 1px solid {c.border_default};
            }}
            QFrame[frameShape="5"] {{  /* VLine */
                border: none;
                border-right: 1px solid {c.border_default};
            }}
        """

    @staticmethod
    def link_button():
        """لینک دکمه - GitHub Link Button"""
        c = Styles._c()
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c.primary};
                border: none;
                padding: 0;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 500;
            }}
            QPushButton:hover {{
                text-decoration: underline;
                color: {c.primary_hover};
            }}
            QPushButton:pressed {{
                color: {c.primary_active};
            }}
        """

    @staticmethod
    def avatar(border=True):
        c = Styles._c()
        border_style = f"border: 2px solid {c.border_default};" if border else "border: none;"
        return f"""
            QLabel, AvatarWidget {{
                background-color: {c.primary_subtle};
                color: {c.primary};
                border-radius: 50%;
                {border_style}
                font-family: {FONT_CSS};
                font-weight: 600;
            }}
        """

    @staticmethod
    def sidebar_item(active=False):
        c = Styles._c()
        if active:
            return f"""
                QPushButton {{
                    background-color: {alpha(c.primary, 0x15)};
                    color: {c.primary};
                    border: none;
                    border-left: 3px solid {c.primary};
                    border-radius: 0;
                    padding: 10px 16px;
                    font-size: {FS_BODY}px;
                    font-family: {FONT_CSS};
                    font-weight: 500;
                    text-align: right;
                }}
                QPushButton:hover {{
                    background-color: {alpha(c.primary, 0x20)};
                }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {c.fg_muted};
                border: none;
                border-left: 3px solid transparent;
                border-radius: 0;
                padding: 10px 16px;
                font-size: {FS_BODY}px;
                font-family: {FONT_CSS};
                font-weight: 400;
                text-align: right;
            }}
            QPushButton:hover {{
                background-color: {c.control_hover};
                color: {c.fg_default};
            }}
        """