"""
GitHub-inspired Theme System for Fluent Design
Based on GitHub's Primer design system colors
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme, setTheme
import json
import copy


class ThemeMode(Enum):
    LIGHT = "light"
    DARK = "dark"


@dataclass
class GitHubTheme:
    """GitHub Primer-inspired color palette"""
    mode: ThemeMode

    # Primary - GitHub Blue
    primary: str = "#0969da"
    primary_hover: str = "#0860ca"
    primary_active: str = "#0550ae"
    primary_subtle: str = "#d0e4ff"
    primary_muted: str = "#9ecbff"

    # Success - GitHub Green
    success: str = "#1a7f37"
    success_hover: str = "#166b2e"
    success_active: str = "#145829"
    success_subtle: str = "#dafbe1"
    success_muted: str = "#6cc644"

    # Danger - GitHub Red
    danger: str = "#cf222e"
    danger_hover: str = "#b31d28"
    danger_active: str = "#991b24"
    danger_subtle: str = "#ffdcd7"
    danger_muted: str = "#ff7b72"

    # Warning - GitHub Orange/Yellow
    warning: str = "#9a6700"
    warning_hover: str = "#825700"
    warning_active: str = "#6a4700"
    warning_subtle: str = "#fff8c5"
    warning_muted: str = "#d29922"

    # Background
    canvas_default: str = "#ffffff"
    canvas_subtle: str = "#f6f8fa"
    canvas_inset: str = "#f6f8fa"
    canvas_overlay: str = "#ffffff"

    # Text
    fg_default: str = "#1f2328"
    fg_muted: str = "#656d76"
    fg_subtle: str = "#656d76"
    fg_on_emphasis: str = "#ffffff"
    fg_accent: str = "#0969da"
    fg_success: str = "#1a7f37"
    fg_danger: str = "#cf222e"
    fg_warning: str = "#9a6700"

    # Border
    border_default: str = "#d0d7de"
    border_muted: str = "#d0d7de"
    border_subtle: str = "#d0d7de"
    border_accent: str = "#0969da"
    border_danger: str = "#cf222e"

    # Control
    control_bg: str = "#ffffff"
    control_hover: str = "#f6f8fa"
    control_active: str = "#f3f4f6"
    control_border: str = "#d0d7de"
    control_border_hover: str = "#8c959f"

    # Input
    input_bg: str = "#ffffff"
    input_border: str = "#d0d7de"
    input_border_hover: str = "#0969da"
    input_placeholder: str = "#656d76"

    # Selection
    selection_bg: str = "#d0e4ff"
    selection_fg: str = "#0969da"

    # Shadow
    shadow_small: str = "rgba(27, 31, 35, 0.04)"
    shadow_medium: str = "rgba(27, 31, 35, 0.08)"
    shadow_large: str = "rgba(27, 31, 35, 0.12)"

    # Accent colors
    accent_blue: str = "#0969da"
    accent_purple: str = "#8250df"
    accent_green: str = "#1a7f37"
    accent_orange: str = "#d29922"
    accent_red: str = "#cf222e"
    accent_pink: str = "#db61a2"
    accent_yellow: str = "#d29922"

    # Fluent theme
    fluent_theme: Theme = Theme.LIGHT


# Light Theme (GitHub Light Default)
LIGHT_THEME = GitHubTheme(
    mode=ThemeMode.LIGHT,
    primary="#0969da",
    primary_hover="#0860ca",
    primary_active="#0550ae",
    primary_subtle="#d0e4ff",
    primary_muted="#9ecbff",
    success="#1a7f37",
    success_hover="#166b2e",
    success_active="#145829",
    success_subtle="#dafbe1",
    success_muted="#6cc644",
    danger="#cf222e",
    danger_hover="#b31d28",
    danger_active="#991b24",
    danger_subtle="#ffdcd7",
    danger_muted="#ff7b72",
    warning="#9a6700",
    warning_hover="#825700",
    warning_active="#6a4700",
    warning_subtle="#fff8c5",
    warning_muted="#d29922",
    canvas_default="#ffffff",
    canvas_subtle="#f6f8fa",
    canvas_inset="#f6f8fa",
    canvas_overlay="#ffffff",
    fg_default="#1f2328",
    fg_muted="#656d76",
    fg_subtle="#656d76",
    fg_on_emphasis="#ffffff",
    fg_accent="#0969da",
    fg_success="#1a7f37",
    fg_danger="#cf222e",
    fg_warning="#9a6700",
    border_default="#d0d7de",
    border_muted="#d0d7de",
    border_subtle="#d0d7de",
    border_accent="#0969da",
    border_danger="#cf222e",
    control_bg="#ffffff",
    control_hover="#f6f8fa",
    control_active="#f3f4f6",
    control_border="#d0d7de",
    control_border_hover="#8c959f",
    input_bg="#ffffff",
    input_border="#d0d7de",
    input_border_hover="#0969da",
    input_placeholder="#656d76",
    selection_bg="#d0e4ff",
    selection_fg="#0969da",
    shadow_small="rgba(27, 31, 35, 0.04)",
    shadow_medium="rgba(27, 31, 35, 0.08)",
    shadow_large="rgba(27, 31, 35, 0.12)",
    accent_blue="#0969da",
    accent_purple="#8250df",
    accent_green="#1a7f37",
    accent_orange="#d29922",
    accent_red="#cf222e",
    accent_pink="#db61a2",
    accent_yellow="#d29922",
)


# Dark Theme (GitHub Dark Default)
DARK_THEME = GitHubTheme(
    mode=ThemeMode.DARK,
    primary="#58a6ff",
    primary_hover="#79b8ff",
    primary_active="#a5cfff",
    primary_subtle="#1f3a5f",
    primary_muted="#4a7bc8",
    success="#3fb950",
    success_hover="#56d364",
    success_active="#6de57a",
    success_subtle="#1e3d25",
    success_muted="#3fb950",
    danger="#f85149",
    danger_hover="#ff7b72",
    danger_active="#ff9c93",
    danger_subtle="#49080c",
    danger_muted="#f85149",
    warning="#d29922",
    warning_hover="#e3b341",
    warning_active="#f0c75c",
    warning_subtle="#3d2e00",
    warning_muted="#d29922",
    canvas_default="#0d1117",
    canvas_subtle="#161b22",
    canvas_inset="#161b22",
    canvas_overlay="#161b22",
    fg_default="#e6edf3",
    fg_muted="#8b949e",
    fg_subtle="#8b949e",
    fg_on_emphasis="#ffffff",
    fg_accent="#58a6ff",
    fg_success="#3fb950",
    fg_danger="#f85149",
    fg_warning="#d29922",
    border_default="#30363d",
    border_muted="#30363d",
    border_subtle="#30363d",
    border_accent="#58a6ff",
    border_danger="#f85149",
    control_bg="#161b22",
    control_hover="#1f2428",
    control_active="#21262d",
    control_border="#30363d",
    control_border_hover="#8b949e",
    input_bg="#0d1117",
    input_border="#30363d",
    input_border_hover="#58a6ff",
    input_placeholder="#8b949e",
    selection_bg="#1f3a5f",
    selection_fg="#58a6ff",
    shadow_small="rgba(0, 0, 0, 0.4)",
    shadow_medium="rgba(0, 0, 0, 0.5)",
    shadow_large="rgba(0, 0, 0, 0.6)",
    accent_blue="#58a6ff",
    accent_purple="#a371f7",
    accent_green="#3fb950",
    accent_orange="#d29922",
    accent_red="#f85149",
    accent_pink="#f783ac",
    accent_yellow="#d29922",
)

LIGHT_THEME.fluent_theme = Theme.LIGHT
DARK_THEME.fluent_theme = Theme.DARK

THEMES = {
    ThemeMode.LIGHT: LIGHT_THEME,
    ThemeMode.DARK: DARK_THEME,
}


# Mapping from CustomColors / UI keys → GitHubTheme attributes
_KEY_MAP = {
    "primary": "primary",
    "primary_hover": "primary_hover",
    "primary_active": "primary_active",
    "success": "success",
    "danger": "danger",
    "warning": "warning",
    "info": "accent_blue",
    "bg_default": "canvas_default",
    "bg_subtle": "canvas_subtle",
    "bg_card": "canvas_overlay",
    "bg_sidebar": "canvas_overlay",
    "bg_header": "canvas_subtle",
    "text_primary": "fg_default",
    "text_secondary": "fg_muted",
    "border_default": "border_default",
    "accent_blue": "accent_blue",
    "accent_purple": "accent_purple",
    "accent_orange": "accent_orange",
    "accent_green": "accent_green",
    # Direct theme keys also accepted
    "canvas_default": "canvas_default",
    "canvas_subtle": "canvas_subtle",
    "canvas_overlay": "canvas_overlay",
    "fg_default": "fg_default",
    "fg_muted": "fg_muted",
}


@dataclass
class CustomColors:
    """Legacy custom colors for backward compatibility with ColorSettingsWidget"""
    primary: str = ""
    primary_hover: str = ""
    primary_active: str = ""
    success: str = ""
    success_hover: str = ""
    danger: str = ""
    danger_hover: str = ""
    warning: str = ""
    warning_hover: str = ""
    info: str = ""
    bg_default: str = ""
    bg_subtle: str = ""
    bg_card: str = ""
    bg_sidebar: str = ""
    bg_header: str = ""
    text_primary: str = ""
    text_secondary: str = ""
    border_default: str = ""
    accent_blue: str = ""
    accent_purple: str = ""
    accent_orange: str = ""
    accent_green: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}

    @classmethod
    def from_dict(cls, data: dict) -> "CustomColors":
        if not isinstance(data, dict):
            return cls()
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_keys and v}
        return cls(**filtered)

    def is_empty(self) -> bool:
        return all(not v for v in self.__dict__.values())


class ThemeManager(QObject):
    """Manages theme state and custom color overrides"""
    theme_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._mode = ThemeMode.LIGHT
        self._custom_overrides: Dict[str, str] = {}
        self._apply_custom = True

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def current(self) -> GitHubTheme:
        base = THEMES[self._mode]
        if self._apply_custom and self._custom_overrides:
            return self._apply_overrides(base)
        return base

    @property
    def current_name(self) -> str:
        return self._mode.value

    @property
    def custom_overrides(self) -> CustomColors:
        """Return a CustomColors object so getattr(custom, key) works in ColorSettingsWidget."""
        return CustomColors.from_dict(self._custom_overrides)

    @property
    def apply_custom(self) -> bool:
        return self._apply_custom

    def _apply_overrides(self, base: GitHubTheme) -> GitHubTheme:
        """Apply custom color overrides to base theme"""
        theme = copy.copy(base)

        for ui_key, value in self._custom_overrides.items():
            if not value:
                continue
            theme_attr = _KEY_MAP.get(ui_key, ui_key)
            if hasattr(theme, theme_attr):
                setattr(theme, theme_attr, value)

        # Auto-derive related colors when primary is overridden
        primary = self._custom_overrides.get("primary")
        if primary:
            theme.primary = primary
            theme.primary_hover = self._adjust_brightness(primary, -15)
            theme.primary_active = self._adjust_brightness(primary, -25)
            theme.primary_subtle = self._adjust_brightness(primary, 85)
            theme.primary_muted = self._adjust_brightness(primary, 40)
            theme.fg_accent = primary
            theme.border_accent = primary
            theme.selection_bg = self._adjust_brightness(primary, 80)
            theme.selection_fg = primary
            theme.accent_blue = primary

        danger = self._custom_overrides.get("danger")
        if danger:
            theme.danger = danger
            theme.danger_hover = self._adjust_brightness(danger, -15)
            theme.danger_active = self._adjust_brightness(danger, -25)
            theme.danger_subtle = self._adjust_brightness(danger, 85)
            theme.danger_muted = self._adjust_brightness(danger, 40)
            theme.fg_danger = danger
            theme.border_danger = danger
            theme.accent_red = danger

        success = self._custom_overrides.get("success")
        if success:
            theme.success = success
            theme.success_hover = self._adjust_brightness(success, -15)
            theme.success_active = self._adjust_brightness(success, -25)
            theme.success_subtle = self._adjust_brightness(success, 85)
            theme.success_muted = self._adjust_brightness(success, 40)
            theme.fg_success = success
            theme.accent_green = success

        warning = self._custom_overrides.get("warning")
        if warning:
            theme.warning = warning
            theme.warning_hover = self._adjust_brightness(warning, -15)
            theme.warning_active = self._adjust_brightness(warning, -25)
            theme.warning_subtle = self._adjust_brightness(warning, 85)
            theme.warning_muted = self._adjust_brightness(warning, 40)
            theme.fg_warning = warning
            theme.accent_orange = warning
            theme.accent_yellow = warning

        bg = (
            self._custom_overrides.get("bg_default")
            or self._custom_overrides.get("canvas_default")
        )
        if bg:
            theme.canvas_default = bg
            theme.canvas_subtle = self._adjust_brightness(
                bg, 5 if self._mode == ThemeMode.LIGHT else -5
            )
            theme.canvas_inset = self._adjust_brightness(
                bg, 5 if self._mode == ThemeMode.LIGHT else -5
            )
            theme.canvas_overlay = self._adjust_brightness(
                bg, 3 if self._mode == ThemeMode.LIGHT else -3
            )
            theme.control_bg = bg
            theme.input_bg = bg

        return theme

    @staticmethod
    def _adjust_brightness(hex_color: str, percent: int) -> str:
        """Adjust brightness of hex color by percentage (-100 to 100)"""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return f"#{hex_color}" if not hex_color.startswith("#") else hex_color

        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        if percent > 0:
            factor = 1 + percent / 100
            r = min(255, int(r * factor))
            g = min(255, int(g * factor))
            b = min(255, int(b * factor))
        else:
            factor = 1 + percent / 100
            r = max(0, int(r * factor))
            g = max(0, int(g * factor))
            b = max(0, int(b * factor))

        return f"#{r:02x}{g:02x}{b:02x}"

    def set_mode(self, mode):
        """Accept ThemeMode enum or string 'light'/'dark'."""
        if isinstance(mode, str):
            try:
                mode = ThemeMode(mode)
            except ValueError:
                return
        if mode in THEMES and mode != self._mode:
            self._mode = mode
            try:
                setTheme(Theme.DARK if mode == ThemeMode.DARK else Theme.LIGHT)
            except Exception:
                pass
            self.theme_changed.emit(mode.value)

    def set_custom_overrides(self, overrides: Dict[str, str]):
        self._custom_overrides = {k: v for k, v in overrides.items() if v}
        self.theme_changed.emit(self._mode.value)

    def set_apply_custom(self, apply: bool):
        self._apply_custom = apply
        self.theme_changed.emit(self._mode.value)

    def reset_custom_overrides(self):
        self._custom_overrides = {}
        self.theme_changed.emit(self._mode.value)

    # ------------------------------------------------------------------ #
    #  Compatibility aliases used by ColorSettingsWidget & SettingsPage
    # ------------------------------------------------------------------ #
    def set_custom_colors(self, custom: Any):
        """Accept CustomColors instance or dict and store as overrides."""
        if isinstance(custom, CustomColors):
            data = custom.to_dict()
        elif isinstance(custom, dict):
            data = {k: v for k, v in custom.items() if v}
        else:
            data = {}
        self._custom_overrides = data
        self.theme_changed.emit(self._mode.value)

    def reset_custom_colors(self):
        self.reset_custom_overrides()

    def export_custom_colors(self) -> str:
        return json.dumps(self._custom_overrides, ensure_ascii=False, indent=2)

    def import_custom_colors(self, json_str: str) -> bool:
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return False
            self._custom_overrides = {k: v for k, v in data.items() if v}
            self.theme_changed.emit(self._mode.value)
            return True
        except Exception:
            return False

    def export_custom_overrides(self) -> str:
        return self.export_custom_colors()

    def import_custom_overrides(self, json_str: str) -> bool:
        return self.import_custom_colors(json_str)

    def get_theme_list(self):
        return [(k.value, k.value.capitalize()) for k in ThemeMode]


theme_manager = ThemeManager()
