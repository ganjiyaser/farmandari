"""چارت سازمانی: نمایش گرافیکی ساختار اکسل، مدیریت پست‌ها و اطلاعات کامل پرسنل."""

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import jdatetime
from PyQt6.QtCore import (
    QMarginsF, QLineF, QPointF, QRectF, QStandardPaths, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QFont, QFontMetrics, QCursor, QPageLayout,
    QPageSize, QPainter, QPainterPath, QPen, QTextLayout, QTextOption,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileDialog, QFrame, QGraphicsItem,
    QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from core.config import settings
from services.org_chart_import import apply_org_chart, parse_org_chart
from services.repositories import employee_repo, org_post_repo
from ui.dialogs import confirm, confirm_delete
from ui.org_chart_dialogs import EmployeeDialog, OrgPostDialog
from ui.program_print import (
    build_employees_report_html, build_org_chart_list_html, print_document,
)
from ui.styles import FONT_STACK, Styles, get_font
from ui.theme import theme_manager

logger = logging.getLogger(__name__)

CARD_WIDTH = 214
ROOT_WIDTH = 300
H_GAP_MIN = 34
V_GAP = 26
PAD = 10
LEFT_MARGIN = 64
RIGHT_MARGIN = 36
TOP_MARGIN = 24
BOTTOM_MARGIN = 40

_FA_DIGITS = str.maketrans("0123456789٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹")


def _fa(value) -> str:
    return str(value).translate(_FA_DIGITS)


def _norm(text: str) -> str:
    return (text or "").translate(_FA_DIGITS).lower()


def _is_district(post) -> bool:
    title = (post.title or "").strip()
    category = (post.category or "").strip()
    return title.startswith("بخشدار") or category.startswith("بخشدار")


def _accent_for(post) -> str:
    c = theme_manager.current
    category = (post.category or "").strip()
    title = (post.title or "").strip()
    if category == "فرمانداری" or (not post.parent_id and "فرماندار" in title):
        return c.primary
    if "حراست" in category or "حراست" in title:
        return c.danger
    if category.startswith("معاون") or title.startswith("معاون"):
        return c.accent_purple
    if "بخشدار" in category or "بخشدار" in title:
        return c.accent_orange
    if title.startswith("رئیس"):
        return c.accent_blue
    return c.fg_muted


def _root_fill_color() -> QColor:
    color = QColor(theme_manager.current.primary)
    if color.lightness() > 170:
        color = color.darker(155)
    return color


def _wrapped_height(text: str, font: QFont, width: float) -> float:
    if not text:
        return 0.0
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setAlignment(Qt.AlignmentFlag.AlignRight)
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    height = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(20.0, width))
        height += line.height()
    layout.endLayout()
    return height


def _draw_wrapped_text(painter: QPainter, text: str, font: QFont,
                       x: float, y: float, width: float, color: QColor) -> float:
    if not text:
        return 0.0
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setAlignment(Qt.AlignmentFlag.AlignRight)
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    height = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(20.0, width))
        line.setPosition(QPointF(0.0, height))
        height += line.height()
    layout.endLayout()
    painter.setPen(QPen(color))
    layout.draw(painter, QPointF(x, y))
    return height


def _draw_elided_line(painter: QPainter, text: str, font: QFont,
                      x: float, y: float, width: float, color: QColor) -> None:
    """رسم یک خط تک‌سطری با QTextLayout.

    QPainter.drawText(rect, ...) هنگام رندر صحنه روی QPrinter با مقیاس بزرگ،
    قلم را دوباره مقیاس می‌کند و متن خروجی چاپی خراب می‌شود؛ QTextLayout این
    مشکل را ندارد.
    """
    if not text:
        return
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setAlignment(Qt.AlignmentFlag.AlignRight)
    option.setWrapMode(QTextOption.WrapMode.NoWrap)
    layout.setTextOption(option)
    layout.beginLayout()
    line = layout.createLine()
    if line.isValid():
        line.setLineWidth(max(20.0, width))
        line.setPosition(QPointF(0.0, 0.0))
    layout.endLayout()
    painter.setPen(QPen(color))
    layout.draw(painter, QPointF(x, y))


def _employee_card_text(post, employees) -> Tuple[str, str, bool]:
    active = [e for e in employees if e.is_active]
    inactive = [e for e in employees if not e.is_active]
    listed = active or inactive
    if not listed:
        return "بدون متصدی", "", True

    names = [e.full_name for e in listed[:2]]
    occupant = "، ".join(names)
    extra = len(listed) - len(names)
    if extra > 0:
        occupant += f" و {_fa(extra)} نفر دیگر"
    if not active and inactive:
        occupant += " (غیرفعال)"

    workplaces = []
    for emp in listed:
        place = (emp.workplace or "").strip()
        if place and place != (post.title or "").strip() and place not in workplaces:
            workplaces.append(place)
    workplace = ("محل خدمت: " + "، ".join(workplaces)) if workplaces else ""
    return occupant, workplace, False


@dataclass
class _CardSpec:
    post: object
    width: float
    height: float
    title_height: float
    occupant_text: str
    workplace_text: str
    vacant: bool
    accent: str
    is_root: bool
    search_blob: str


@dataclass
class _Column:
    items: List[Tuple[object, int]]
    connected: bool = True


def _make_card_spec(post, employees, depth, fonts, is_root=False) -> _CardSpec:
    c = theme_manager.current
    title_font = fonts["root_title"] if is_root else fonts["title"]
    body_font = fonts["root_body"] if is_root else fonts["body"]
    small_font = fonts["root_small"] if is_root else fonts["small"]
    width = ROOT_WIDTH if is_root else max(160, CARD_WIDTH - min(depth, 3) * 12)
    side = 0 if is_root else 10
    text_width = width - 2 * PAD - side
    title_height = _wrapped_height(post.title or "", title_font, text_width)
    title_height = max(title_height, float(QFontMetrics(title_font).height()))
    occupant, workplace, vacant = _employee_card_text(post, employees)
    height = (2 * PAD + title_height + 5 + QFontMetrics(body_font).height()
              + ((4 + QFontMetrics(small_font).height()) if workplace else 0))
    height = max(height, 78.0 if is_root else 66.0)

    parts = [post.title, post.category, post.code, occupant, workplace]
    for emp in employees:
        parts.extend([emp.full_name, emp.personnel_code, emp.workplace])
    search_blob = _norm(" ".join(str(p) for p in parts if p))

    return _CardSpec(
        post=post, width=float(width), height=float(height),
        title_height=title_height, occupant_text=occupant,
        workplace_text=workplace, vacant=vacant,
        accent=_accent_for(post), is_root=is_root, search_blob=search_blob,
    )


class PostCardItem(QGraphicsItem):
    def __init__(self, spec: _CardSpec, fonts, on_double_click: Callable = None,
                 parent=None):
        super().__init__(parent)
        self.spec = spec
        self.post = spec.post
        self.search_blob = spec.search_blob
        self._fonts = fonts
        self._on_double_click = on_double_click
        self._hover = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(2)
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        post = self.post
        lines = [post.title or ""]
        if post.category:
            lines.append(f"حوزه: {post.category}")
        if post.code:
            lines.append(f"کد پست: {post.code}")
        appro = post.approved_count or 0
        if appro:
            lines.append(f"پست مصوب: {_fa(appro)}")
        if self.spec.occupant_text:
            lines.append(f"متصدی: {self.spec.occupant_text}")
        if self.spec.workplace_text:
            lines.append(self.spec.workplace_text)
        return "\n".join(lines)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.spec.width, self.spec.height)

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._on_double_click is not None:
            self._on_double_click(self.post.id)
        event.accept()

    def paint(self, painter: QPainter, option, widget=None):
        c = theme_manager.current
        spec = self.spec
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        rect = QRectF(0.5, 0.5, spec.width - 1.0, spec.height - 1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 9, 9)

        selected = self.isSelected()
        if spec.is_root:
            fill = _root_fill_color()
            if self._hover or selected:
                fill = fill.lighter(112)
            painter.fillPath(path, fill)
            border = QColor("#ffffff")
            border.setAlpha(170 if selected else 80)
            painter.setPen(QPen(border, 2.2 if selected else 1.1))
            painter.drawPath(path)
        else:
            painter.fillPath(path, QColor(c.canvas_overlay))
            tint = QColor(spec.accent)
            tint.setAlpha(32 if (selected or self._hover) else 16)
            painter.fillPath(path, tint)
            if selected:
                pen_color = QColor(c.primary)
                pen_width = 2.2
            elif self._hover:
                pen_color = QColor(spec.accent)
                pen_color.setAlpha(230)
                pen_width = 1.4
            else:
                pen_color = QColor(spec.accent)
                pen_color.setAlpha(120)
                pen_width = 1.0
            pen = QPen(pen_color, pen_width)
            if spec.vacant:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPath(path)

            bar_color = QColor(spec.accent)
            bar_color.setAlpha(230 if (selected or self._hover) else 190)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(
                QRectF(spec.width - 8, 8, 3, max(8.0, spec.height - 16)), 1.5, 1.5)

        if spec.is_root:
            title_color = QColor(c.fg_on_emphasis)
            body_color = QColor(c.fg_on_emphasis)
            body_color.setAlpha(235)
            small_color = QColor(c.fg_on_emphasis)
            small_color.setAlpha(185)
            empty_color = QColor(c.fg_on_emphasis)
            empty_color.setAlpha(160)
        else:
            title_color = QColor(c.fg_default)
            body_color = QColor(c.fg_default)
            small_color = QColor(c.fg_muted)
            empty_color = QColor(c.fg_muted)

        side = 0 if spec.is_root else 10
        text_x = float(PAD)
        text_width = spec.width - 2 * PAD - side
        y = float(PAD)

        _draw_wrapped_text(painter, self.post.title or "", self._fonts[
            "root_title" if spec.is_root else "title"],
            text_x, y, text_width, title_color)
        y += spec.title_height + 5.0

        body_font = self._fonts["root_body" if spec.is_root else "body"]
        body_metrics = QFontMetrics(body_font)
        occupant = body_metrics.elidedText(
            spec.occupant_text, Qt.TextElideMode.ElideRight, int(text_width))
        if spec.vacant:
            body_font = QFont(body_font)
            body_font.setItalic(True)
        _draw_elided_line(
            painter, occupant, body_font, text_x, y, text_width,
            empty_color if spec.vacant else body_color)
        y += body_metrics.height()

        if spec.workplace_text:
            y += 4.0
            small_font = self._fonts["root_small" if spec.is_root else "small"]
            small_metrics = QFontMetrics(small_font)
            place = small_metrics.elidedText(
                spec.workplace_text, Qt.TextElideMode.ElideRight, int(text_width))
            _draw_elided_line(
                painter, place, small_font, text_x, y, text_width, small_color)


def _flatten_tree(root, children, seen=None):
    seen = seen if seen is not None else set()
    out = []
    stack = [(root, 0)]
    while stack:
        post, depth = stack.pop()
        if post.id in seen:
            continue
        seen.add(post.id)
        out.append((post, depth))
        kids = children.get(post.id, [])
        for child in reversed(kids):
            stack.append((child, depth + 1))
    return out


def _make_columns(root_children, children) -> List[_Column]:
    columns = []
    leaf_buffer = []
    for post in root_children:
        if children.get(post.id):
            if leaf_buffer:
                columns.append(_Column([(p, 0) for p in leaf_buffer]))
                leaf_buffer = []
            columns.append(_Column(_flatten_tree(post, children)))
        else:
            leaf_buffer.append(post)
    if leaf_buffer:
        columns.append(_Column([(p, 0) for p in leaf_buffer]))
    return columns


def _spread_centers(content_x, content_w, count) -> List[float]:
    """چیدمان راست‌به‌چپ؛ ستون اول در سمت راست قرار می‌گیرد."""
    if count <= 0:
        return []
    return [content_x + content_w - content_w * (i + 0.5) / count
            for i in range(count)]


def _connector_pen() -> QPen:
    c = theme_manager.current
    color = QColor(c.border_default)
    if color.lightness() < 60:
        color = QColor(c.fg_muted)
    pen = QPen(color, 1.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _add_connector(scene, path: QPainterPath):
    item = scene.addPath(path, _connector_pen())
    item.setZValue(0)


def _add_section_label(scene, right_x, y, text, font) -> float:
    c = theme_manager.current
    item = QGraphicsSimpleTextItem(text)
    item.setFont(font)
    item.setBrush(QBrush(QColor(c.fg_default)))
    item.setZValue(3)
    width = item.boundingRect().width()
    height = item.boundingRect().height()
    item.setPos(right_x - width, y)
    scene.addItem(item)

    pen = _connector_pen()
    line = scene.addLine(QLineF(right_x - width, y + height + 3,
                                right_x, y + height + 3), pen)
    line.setZValue(2)
    return height


def _add_column(scene, column: _Column, x, top_y, employees_by_post, fonts,
                cards, on_double_click):
    specs = []
    offset = 0.0
    for post, depth in column.items:
        spec = _make_card_spec(
            post, employees_by_post.get(post.id, []), depth, fonts)
        specs.append((spec, offset))
        offset += spec.height + V_GAP
    if not specs:
        return 0.0

    column_height = offset - V_GAP
    for spec, y_offset in specs:
        card = PostCardItem(spec, fonts, on_double_click)
        card.setPos(x, top_y + y_offset)
        scene.addItem(card)
        cards[spec.post.id] = card

    if len(specs) > 1:
        spine_x = x - 15.0
        centers = [top_y + y_offset + spec.height / 2.0
                   for spec, y_offset in specs]
        path = QPainterPath()
        path.moveTo(spine_x, centers[0])
        path.lineTo(spine_x, centers[-1])
        for spec, center_y in zip(specs, centers):
            path.moveTo(spine_x, center_y)
            path.lineTo(x, center_y)
        _add_connector(scene, path)

    return column_height


def build_chart_scene(posts, employees_by_post, roots, children,
                      selected_post_id=None, on_double_click=None):
    """ساخت صحنهٔ چارت؛ خروجی (scene, cards) است."""
    c = theme_manager.current
    scene = QGraphicsScene()
    scene.setBackgroundBrush(QBrush(QColor(c.canvas_default)))
    scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

    fonts = {
        "root_title": get_font(12, True),
        "root_body": get_font(10),
        "root_small": get_font(8),
        "title": get_font(10, True),
        "body": get_font(9),
        "small": get_font(8),
        "section": get_font(11, True),
    }
    cards = {}
    if not posts or not roots:
        scene.setSceneRect(0, 0, 800, 500)
        return scene, cards

    main_root = roots[0]
    extra_roots = list(roots[1:])
    root_employees = employees_by_post.get(main_root.id, [])
    root_spec = _make_card_spec(
        main_root, root_employees, 0, fonts, is_root=True)

    root_children = children.get(main_root.id, [])
    district_children = [p for p in root_children if _is_district(p)]
    top_children = [p for p in root_children if not _is_district(p)]

    top_columns = _make_columns(top_children, children)
    for extra in extra_roots:
        top_columns.append(
            _Column(_flatten_tree(extra, children), connected=False))
    district_columns = []
    for district in district_children:
        district_columns.append(_Column(_flatten_tree(district, children)))

    top_width = (len(top_columns) * CARD_WIDTH
                 + max(0, len(top_columns) - 1) * H_GAP_MIN)
    district_width = (len(district_columns) * CARD_WIDTH
                      + max(0, len(district_columns) - 1) * H_GAP_MIN)
    content_w = max(top_width, district_width, ROOT_WIDTH + 120, 640.0)
    content_x = float(LEFT_MARGIN)
    scene_w = content_x + content_w + RIGHT_MARGIN

    root_x = content_x + (content_w - root_spec.width) / 2.0
    root_y = float(TOP_MARGIN)
    root_card = PostCardItem(root_spec, fonts, on_double_click)
    root_card.setPos(root_x, root_y)
    scene.addItem(root_card)
    cards[main_root.id] = root_card
    root_bottom = root_y + root_spec.height
    root_center_x = root_x + root_spec.width / 2.0

    top_centers = _spread_centers(content_x, content_w, len(top_columns))
    top_bottom = root_bottom
    top_y = None
    if top_columns:
        label_y = root_bottom + 24
        _add_section_label(
            scene, content_x + content_w, label_y,
            "ستاد فرمانداری", fonts["section"])
        bus_y = label_y + 34
        top_y = bus_y + 20
        connected = [col for col, center in zip(top_columns, top_centers)
                     if col.connected]
        connected_centers = [center for col, center in
                             zip(top_columns, top_centers) if col.connected]
        if connected:
            xs = connected_centers + [root_center_x]
            bus_left, bus_right = min(xs), max(xs)
            path = QPainterPath()
            path.moveTo(root_center_x, root_bottom)
            path.lineTo(root_center_x, bus_y)
            path.moveTo(bus_left, bus_y)
            path.lineTo(bus_right, bus_y)
            for center in connected_centers:
                path.moveTo(center, bus_y)
                path.lineTo(center, top_y)
            _add_connector(scene, path)
        for column, center in zip(top_columns, top_centers):
            column_x = center - CARD_WIDTH / 2.0
            height = _add_column(
                scene, column, column_x, top_y, employees_by_post, fonts,
                cards, on_double_click)
            top_bottom = max(top_bottom, top_y + height)

    district_bottom = top_bottom
    if district_columns:
        label_y = top_bottom + 34
        _add_section_label(
            scene, content_x + content_w, label_y,
            "بخشداران و حوزه‌های تابعه", fonts["section"])
        bus_y = label_y + 34
        district_y = bus_y + 20
        centers = _spread_centers(content_x, content_w, len(district_columns))
        bus_left, bus_right = min(centers), max(centers)
        trunk_x = 24.0
        root_line_y = root_y + root_spec.height / 2.0
        path = QPainterPath()
        path.moveTo(root_x, root_line_y)
        path.lineTo(trunk_x, root_line_y)
        path.lineTo(trunk_x, bus_y)
        path.lineTo(bus_right, bus_y)
        for center in centers:
            path.moveTo(center, bus_y)
            path.lineTo(center, district_y)
        _add_connector(scene, path)
        for column, center in zip(district_columns, centers):
            column_x = center - CARD_WIDTH / 2.0
            height = _add_column(
                scene, column, column_x, district_y, employees_by_post, fonts,
                cards, on_double_click)
            district_bottom = max(district_bottom, district_y + height)

    bottom = max(root_bottom, top_bottom, district_bottom) + BOTTOM_MARGIN
    scene.setSceneRect(0, 0, scene_w, bottom)

    if selected_post_id in cards:
        cards[selected_post_id].setSelected(True)
    return scene, cards


class ChartView(QGraphicsView):
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(QColor(theme_manager.current.canvas_default)))
        self.setStyleSheet("QGraphicsView { border: none; background: transparent; }")
        self._panning = False
        self._pan_start = None

    def _content_rect(self) -> QRectF:
        scene = self.scene()
        if scene is None:
            return QRectF()
        rect = scene.itemsBoundingRect()
        if rect.isEmpty():
            return QRectF()
        return rect.adjusted(-20, -16, 20, 24)

    def zoom_by(self, factor: float):
        current = self.transform().m11()
        if current <= 0:
            return
        target = min(2.5, max(0.2, current * factor))
        if abs(target - current) < 1e-5:
            return
        self.scale(target / current, target / current)
        self.zoom_changed.emit(self.transform().m11())

    def set_zoom_scale(self, value: float):
        current = self.transform().m11()
        if current <= 0:
            return
        value = min(2.5, max(0.2, value))
        self.scale(value / current, value / current)
        self.zoom_changed.emit(self.transform().m11())

    def fit_width(self):
        rect = self._content_rect()
        if rect.isEmpty() or self.viewport().width() < 80:
            return
        scale = (self.viewport().width() - 8) / rect.width()
        scale = min(1.15, max(0.15, scale))
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center().x(),
                      rect.top() + self.viewport().height() / (2 * scale))
        self.horizontalScrollBar().setValue(
            (self.horizontalScrollBar().minimum()
             + self.horizontalScrollBar().maximum()) // 2)
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().minimum())
        self.zoom_changed.emit(self.transform().m11())

    def fit_all(self):
        rect = self._content_rect()
        if rect.isEmpty():
            return
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.0:
            self.set_zoom_scale(1.0)
        self.zoom_changed.emit(self.transform().m11())

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_by(1.15 if delta > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        empty_left = (
            event.button() == Qt.MouseButton.LeftButton
            and self.itemAt(event.pos()) is None)
        if event.button() == Qt.MouseButton.MiddleButton or empty_left:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (
                Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._panning = False
            self._pan_start = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def print_org_chart_scene(parent, scene, title="چارت سازمانی", subtitle=""):
    """پیش‌نمایش چاپ گرافیکی چارت روی کاغذ A3 افقی.

    چارت با مقیاس طبیعی (هر ۹۶ پیکسل صحنه = یک اینچ) چاپ می‌شود تا نوشته‌های
    کارت‌ها خوانا بمانند؛ اگر چارت از یک صفحه بزرگ‌تر باشد به‌صورت چندصفحه‌ای و
    کاشی‌کاشی (از راست به چپ) چاپ می‌شود و سرصفحه در هر صفحه تکرار می‌گردد.
    """
    source = scene.itemsBoundingRect() if scene is not None else QRectF()
    if source.isEmpty():
        QMessageBox.information(parent, "چاپ چارت", "چارت سازمانی خالی است.")
        return
    source = source.adjusted(-12, -12, 12, 12)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A3))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    printer.setPageMargins(
        QMarginsF(8, 8, 8, 8), QPageLayout.Unit.Millimeter)

    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(f"چاپ {title}")

    def _plan(total, tile):
        """کاشی‌بندی یک محور؛ خروجی موقعیت شروع کاشی‌ها از چپ است."""
        # اگر سرریز جزئی است، به‌جای صفحهٔ تقریباً تکراری کمی کوچک می‌کنیم تا
        # همه‌چیز در یک صفحه جا شود (مثلاً چارتی که ۵ واحد از عرض صفحه بیشتر است).
        if total <= tile * 1.15:
            return [0.0]
        count = max(2, math.ceil(total / (tile * 0.94)))
        last = total - tile
        if count == 2:
            return [0.0, last]
        return [round(i * last / (count - 1), 3) for i in range(count)]

    def render(prn):
        painter = QPainter()
        if not painter.begin(prn):
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            viewport = QRectF(painter.viewport())
            painter.fillRect(viewport, QColor("#ffffff"))
            painter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

            resolution = max(96.0, float(prn.resolution()))
            mm = resolution / 25.4
            margin = int(5 * mm)
            header_h = int(16 * mm)
            footer_h = int(7 * mm)
            gap = int(3 * mm)
            content_rect = QRectF(
                margin,
                margin + header_h + gap,
                viewport.width() - 2 * margin,
                viewport.height() - (margin + header_h + gap)
                - margin - footer_h)

            scale = resolution / 96.0
            tile_w = max(80.0, content_rect.width() / scale)
            tile_h = max(80.0, content_rect.height() / scale)
            xs = list(reversed(_plan(source.width(), tile_w)))
            ys = _plan(source.height(), tile_h)
            single_x = len(xs) == 1
            single_y = len(ys) == 1
            if single_x and source.width() > tile_w:
                scale = min(scale, content_rect.width() / source.width())
            if single_y and source.height() > tile_h:
                scale = min(scale, content_rect.height() / source.height())
            total_pages = len(xs) * len(ys)
            page_no = 0

            title_font = QFont()
            title_font.setFamilies(FONT_STACK)
            title_font.setPointSize(16)
            title_font.setBold(True)
            info_font = QFont()
            info_font.setFamilies(FONT_STACK)
            info_font.setPointSize(10)
            page_font = QFont()
            page_font.setFamilies(FONT_STACK)
            page_font.setPointSize(9)
            today = jdatetime.date.today().strftime("%Y/%m/%d")

            def draw_frame():
                title_rect = QRectF(
                    margin, margin, viewport.width() - 2 * margin,
                    header_h * 0.56)
                sub_rect = QRectF(
                    margin, margin + header_h * 0.56,
                    viewport.width() - 2 * margin, header_h * 0.44)
                painter.setFont(title_font)
                painter.setPen(QColor("#1f2328"))
                painter.drawText(
                    title_rect,
                    int(Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter),
                    f"{settings.ORGANIZATION} — {title}")
                painter.setFont(info_font)
                painter.setPen(QColor("#555555"))
                painter.drawText(
                    title_rect,
                    int(Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter),
                    f"تاریخ: {today}")
                painter.drawText(
                    sub_rect,
                    int(Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter),
                    subtitle or "")

                line_y = margin + header_h
                painter.setPen(QPen(QColor("#1a1a1a"), max(1.0, 0.4 * mm)))
                painter.drawLine(QLineF(margin, line_y,
                                        viewport.width() - margin, line_y))
                painter.setPen(QPen(QColor("#c9c9c9"), max(1.0, 0.2 * mm)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(content_rect)
                painter.setFont(page_font)
                painter.setPen(QColor("#555555"))
                footer_rect = QRectF(
                    margin, viewport.height() - margin - footer_h,
                    viewport.width() - 2 * margin, footer_h)
                painter.drawText(
                    footer_rect,
                    int(Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter),
                    f"صفحه {_fa(page_no)} از {_fa(total_pages)}")

            for y in ys:
                for x in xs:
                    if page_no:
                        prn.newPage()
                    page_no += 1
                    draw_frame()
                    tile_w_used = source.width() if single_x else min(
                        tile_w, source.width() - x)
                    tile_h_used = source.height() if single_y else min(
                        tile_h, source.height() - y)
                    tile_rect = QRectF(
                        source.left() + x, source.top() + y,
                        tile_w_used, tile_h_used)
                    target = QRectF(
                        content_rect.left(), content_rect.top(),
                        tile_rect.width() * scale, tile_rect.height() * scale)
                    if target.width() > 10 and target.height() > 10:
                        scene.render(
                            painter, target, tile_rect,
                            Qt.AspectRatioMode.KeepAspectRatio)
        finally:
            painter.end()

    dlg.paintRequested.connect(render)
    dlg.exec()


class OrgChartPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._posts = []
        self._posts_by_id = {}
        self._roots = []
        self._children = {}
        self._employees = []
        self._employees_by_post = {}
        self._selected_post_id = None
        self._chart_scene = None
        self._cards = {}
        self._search_term = ""
        self._fit_pending = True
        self._populating = False
        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        c = theme_manager.current
        self.setStyleSheet(f"OrgChartPage {{ background: {c.canvas_default}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("چارت سازمانی")
        title.setStyleSheet(Styles.title_label())
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(Styles.subtitle_label())
        title_col.addWidget(title)
        title_col.addWidget(self.stats_label)
        header.addLayout(title_col)
        header.addStretch(1)

        self.import_btn = QPushButton("ورود چارت از Excel")
        self.import_btn.setStyleSheet(Styles.secondary_button())
        self.import_btn.clicked.connect(self._import_excel)
        header.addWidget(self.import_btn)

        self.print_btn = QPushButton("چاپ")
        self.print_btn.setStyleSheet(Styles.secondary_button())
        self.print_menu = QMenu(self.print_btn)
        self.print_menu.setStyleSheet(
            f"QMenu {{ background: {c.canvas_overlay}; color: {c.fg_default}; "
            f"border: 1px solid {c.border_default}; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 26px 6px 14px; border-radius: 4px; }}"
            f"QMenu::item:selected {{ background: {c.canvas_subtle}; }}"
            f"QMenu::item:disabled {{ color: {c.fg_muted}; }}")
        self.print_chart_action = self.print_menu.addAction("چاپ گرافیکی چارت")
        self.print_chart_action.triggered.connect(self._print_chart)
        self.print_org_list_action = self.print_menu.addAction(
            "چاپ فهرست چارت (جدولی)")
        self.print_org_list_action.triggered.connect(self._print_org_list)
        self.print_employees_action = self.print_menu.addAction(
            "چاپ فهرست پرسنل")
        self.print_employees_action.triggered.connect(self._print_employees)
        self.print_btn.clicked.connect(self._show_print_menu)
        header.addWidget(self.print_btn)

        self.refresh_btn = QPushButton("بروزرسانی")
        self.refresh_btn.setStyleSheet(Styles.secondary_button())
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        outer.addLayout(header)

        hint = QLabel(
            "پست سازمانی، جایگاه ثابت هر فرد در چارت است. محل خدمت فعلی جداگانه "
            "ثبت می‌شود و معمولاً با پست سازمانی یکسان نیست (جابجایی پرسنل).")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px;")
        outer.addWidget(hint)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {c.border_default}; "
            f"border-radius: 8px; background: {c.canvas_overlay}; top: -1px; }}"
            f"QTabBar::tab {{ background: {c.canvas_subtle}; color: {c.fg_muted}; "
            f"font-family: 'Vazirmatn', 'Segoe UI', Tahoma; font-size: 13px; "
            f"padding: 8px 22px; border: 1px solid {c.border_default}; "
            f"border-bottom: none; border-top-left-radius: 8px; "
            f"border-top-right-radius: 8px; margin-left: 4px; }}"
            f"QTabBar::tab:selected {{ background: {c.canvas_overlay}; "
            f"color: {c.primary}; font-weight: bold; }}")
        self._build_chart_tab()
        self._build_employees_tab()
        outer.addWidget(self.tabs, 1)

    def _build_chart_tab(self):
        self.chart_tab = QWidget()
        layout = QVBoxLayout(self.chart_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("جستجوی پست، نام متصدی یا محل خدمت...")
        self.search_edit.setStyleSheet(Styles.search_input())
        self.search_edit.setMaximumWidth(340)
        self.search_edit.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        self.add_post_btn = QPushButton("+ پست سازمانی")
        self.add_post_btn.setStyleSheet(Styles.secondary_button())
        self.add_post_btn.clicked.connect(lambda: self._add_post())
        toolbar.addWidget(self.add_post_btn)

        self.add_employee_btn = QPushButton("+ پرسنل جدید")
        self.add_employee_btn.setStyleSheet(Styles.primary_button())
        self.add_employee_btn.clicked.connect(lambda: self._add_employee())
        toolbar.addWidget(self.add_employee_btn)

        toolbar.addSpacing(10)
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setStyleSheet(Styles.icon_button())
        self.zoom_out_btn.setFixedSize(34, 34)
        self.zoom_out_btn.setToolTip("کوچک‌نمایی")
        self.zoom_out_btn.clicked.connect(lambda: self.view.zoom_by(1 / 1.2))
        toolbar.addWidget(self.zoom_out_btn)

        self.zoom_label = QLabel("۱۰۰٪")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setStyleSheet(
            f"color: {theme_manager.current.fg_muted}; font-size: 11px;")
        toolbar.addWidget(self.zoom_label)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setStyleSheet(Styles.icon_button())
        self.zoom_in_btn.setFixedSize(34, 34)
        self.zoom_in_btn.setToolTip("بزرگ‌نمایی")
        self.zoom_in_btn.clicked.connect(lambda: self.view.zoom_by(1.2))
        toolbar.addWidget(self.zoom_in_btn)

        self.fit_btn = QPushButton("نمایش کامل")
        self.fit_btn.setStyleSheet(Styles.secondary_button())
        self.fit_btn.clicked.connect(self._fit_all)
        toolbar.addWidget(self.fit_btn)
        layout.addLayout(toolbar)

        self.chart_stack = QStackedWidget()
        self.empty_chart = self._make_chart_empty_state()
        self.chart_stack.addWidget(self.empty_chart)

        self.view = ChartView()
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.setMinimumWidth(420)
        self.view.scene().selectionChanged.connect(self._on_scene_selection)

        self.details_panel = self._build_details_panel()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.details_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([900, 330])
        self.splitter.setChildrenCollapsible(False)
        self.chart_stack.addWidget(self.splitter)
        layout.addWidget(self.chart_stack, 1)

        self.tabs.addTab(self.chart_tab, "نمای چارت")

    def _make_chart_empty_state(self):
        c = theme_manager.current
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addStretch(1)
        title = QLabel("چارت سازمانی هنوز وارد نشده است")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(Styles.section_title_label())
        lay.addWidget(title)
        hint = QLabel(
            "فایل اکسل چارت سازمانی فرمانداری را وارد کنید تا ساختار ترسیمی "
            "آن (فرماندار، معاونین، حراست، بخشداران و کارکنان) به‌صورت "
            "گرافیکی در برنامه نمایش داده شود. سپس اطلاعات پرسنل را ثبت کنید.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px;")
        hint.setMaximumWidth(640)
        lay.addWidget(hint, 0, Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.addStretch(1)
        import_btn = QPushButton("ورود چارت از Excel")
        import_btn.setStyleSheet(Styles.primary_button())
        import_btn.clicked.connect(self._import_excel)
        row.addWidget(import_btn)
        create_btn = QPushButton("ساخت پست اول به‌صورت دستی")
        create_btn.setStyleSheet(Styles.secondary_button())
        create_btn.clicked.connect(lambda: self._add_post())
        row.addWidget(create_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(2)
        return widget

    def _build_details_panel(self):
        c = theme_manager.current
        panel = QFrame()
        panel.setObjectName("orgDetailsPanel")
        panel.setStyleSheet(
            f"QFrame#orgDetailsPanel {{ background: {c.canvas_overlay}; "
            f"border: 1px solid {c.border_default}; border-radius: 8px; }}")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(430)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        self.detail_stack = QStackedWidget()
        placeholder = QWidget()
        ph_lay = QVBoxLayout(placeholder)
        ph_lay.setContentsMargins(10, 10, 10, 10)
        ph_label = QLabel(
            "برای دیدن اطلاعات یک پست، روی کارت آن در چارت کلیک کنید.\n"
            "با دوبار کلیک روی کارت، پست ویرایش می‌شود.")
        ph_label.setWordWrap(True)
        ph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_label.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px;")
        ph_lay.addStretch(1)
        ph_lay.addWidget(ph_label)
        ph_lay.addStretch(1)
        self.detail_stack.addWidget(placeholder)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(6)

        self.detail_title = QLabel("—")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(Styles.section_title_label())
        content_lay.addWidget(self.detail_title)

        self.detail_category = QLabel("")
        self.detail_category.setWordWrap(True)
        self.detail_category.setFixedHeight(24)
        content_lay.addWidget(self.detail_category, 0, Qt.AlignmentFlag.AlignRight)

        meta = QGridLayout()
        meta.setHorizontalSpacing(8)
        meta.setVerticalSpacing(4)

        def meta_label(text):
            label = QLabel(text)
            label.setStyleSheet(f"color: {c.fg_muted}; font-size: 10px;")
            return label

        def meta_value():
            label = QLabel("—")
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {c.fg_default}; font-size: 11px;")
            return label

        self.detail_parent = meta_value()
        self.detail_code = meta_value()
        self.detail_approved = meta_value()
        self.detail_children = meta_value()
        for row, (label_text, value_label) in enumerate([
                ("پست بالادستی", self.detail_parent),
                ("کد پست سازمانی", self.detail_code),
                ("تعداد پست مصوب", self.detail_approved),
                ("پست‌های زیرمجموعه", self.detail_children)]):
            meta.addWidget(meta_label(label_text), row, 0)
            meta.addWidget(value_label, row, 1)
        meta.setColumnStretch(1, 1)
        content_lay.addLayout(meta)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {c.border_default};")
        content_lay.addWidget(line)

        emp_title = QLabel("پرسنل این پست")
        emp_title.setStyleSheet(f"color: {c.fg_default}; font-size: 12px; font-weight: bold;")
        content_lay.addWidget(emp_title)
        emp_hint = QLabel("محل خدمت فعلی ممکن است با پست سازمانی متفاوت باشد.")
        emp_hint.setWordWrap(True)
        emp_hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 10px;")
        content_lay.addWidget(emp_hint)

        self.detail_emp_table = QTableWidget(0, 2)
        self.detail_emp_table.setHorizontalHeaderLabels(
            ["نام و نام خانوادگی", "محل خدمت فعلی"])
        self._style_small_table(self.detail_emp_table)
        self.detail_emp_table.setMinimumHeight(110)
        header = self.detail_emp_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.detail_emp_table.itemSelectionChanged.connect(
            self._update_detail_employee_buttons)
        self.detail_emp_table.cellDoubleClicked.connect(
            lambda row, col: self._edit_detail_employee())
        content_lay.addWidget(self.detail_emp_table, 1)

        self.detail_no_emp = QLabel("برای این پست هنوز پرسنلی ثبت نشده است.")
        self.detail_no_emp.setWordWrap(True)
        self.detail_no_emp.setStyleSheet(
            f"color: {c.fg_muted}; font-size: 11px; padding: 8px;")
        content_lay.addWidget(self.detail_no_emp)

        emp_actions = QHBoxLayout()
        emp_actions.setSpacing(6)
        self.detail_emp_edit_btn = QPushButton("ویرایش پرسنل")
        self.detail_emp_edit_btn.setStyleSheet(Styles.table_action_button("neutral"))
        self.detail_emp_edit_btn.setEnabled(False)
        self.detail_emp_edit_btn.clicked.connect(self._edit_detail_employee)
        emp_actions.addWidget(self.detail_emp_edit_btn)
        self.detail_emp_del_btn = QPushButton("حذف پرسنل")
        self.detail_emp_del_btn.setStyleSheet(Styles.table_action_button("danger"))
        self.detail_emp_del_btn.setEnabled(False)
        self.detail_emp_del_btn.clicked.connect(self._delete_detail_employee)
        emp_actions.addWidget(self.detail_emp_del_btn)
        emp_actions.addStretch(1)
        content_lay.addLayout(emp_actions)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"color: {c.border_default};")
        content_lay.addWidget(line2)

        self.detail_add_emp_btn = QPushButton("افزودن پرسنل به این پست")
        self.detail_add_emp_btn.setStyleSheet(Styles.primary_button())
        self.detail_add_emp_btn.clicked.connect(
            lambda: self._add_employee(self._selected_post_id))
        content_lay.addWidget(self.detail_add_emp_btn)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.detail_add_child_btn = QPushButton("پست زیرمجموعه")
        self.detail_add_child_btn.setStyleSheet(Styles.secondary_button())
        self.detail_add_child_btn.clicked.connect(
            lambda: self._add_post(self._selected_post_id))
        row.addWidget(self.detail_add_child_btn, 1)
        self.detail_edit_btn = QPushButton("ویرایش پست")
        self.detail_edit_btn.setStyleSheet(Styles.secondary_button())
        self.detail_edit_btn.clicked.connect(
            lambda: self._edit_post(self._selected_post_id))
        row.addWidget(self.detail_edit_btn, 1)
        content_lay.addLayout(row)

        delete_row = QHBoxLayout()
        delete_row.setSpacing(6)
        self.detail_delete_btn = QPushButton("حذف پست")
        self.detail_delete_btn.setStyleSheet(Styles.secondary_button())
        self.detail_delete_btn.clicked.connect(
            lambda: self._delete_post(self._selected_post_id))
        delete_row.addWidget(self.detail_delete_btn)
        delete_row.addStretch(1)
        content_lay.addLayout(delete_row)

        self.detail_stack.addWidget(content)
        self.detail_content = content
        lay.addWidget(self.detail_stack, 1)
        return panel

    def _style_small_table(self, table):
        table.setStyleSheet(Styles.table_widget(font_size=11, header_font_size=10))
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setFixedHeight(30)
        table.verticalHeader().setDefaultSectionSize(30)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)

    def _build_employees_tab(self):
        c = theme_manager.current
        self.employees_tab = QWidget()
        layout = QVBoxLayout(self.employees_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        hint = QLabel(
            "در این فهرست، «پست سازمانی» جایگاه ثابت فرد طبق چارت است و "
            "«محل خدمت فعلی» جایی است که اکنون مشغول به کار است. این دو "
            "ممکن است متفاوت باشند.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 11px;")
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.emp_search = QLineEdit()
        self.emp_search.setPlaceholderText(
            "جستجوی نام، کد پرسنلی، پست سازمانی یا محل خدمت...")
        self.emp_search.setStyleSheet(Styles.search_input())
        self.emp_search.textChanged.connect(self._fill_employee_table)
        toolbar.addWidget(self.emp_search, 1)
        self.emp_count_label = QLabel("")
        self.emp_count_label.setStyleSheet(Styles.subtitle_label())
        self.emp_count_label.setMinimumWidth(90)
        self.emp_count_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        toolbar.addWidget(self.emp_count_label)
        self.emp_edit_btn = QPushButton("ویرایش")
        self.emp_edit_btn.setStyleSheet(Styles.secondary_button())
        self.emp_edit_btn.setEnabled(False)
        self.emp_edit_btn.clicked.connect(self._edit_selected_employee)
        toolbar.addWidget(self.emp_edit_btn)
        self.emp_delete_btn = QPushButton("حذف")
        self.emp_delete_btn.setStyleSheet(Styles.secondary_button())
        self.emp_delete_btn.setEnabled(False)
        self.emp_delete_btn.clicked.connect(self._delete_selected_employee)
        toolbar.addWidget(self.emp_delete_btn)
        add_btn = QPushButton("+ پرسنل جدید")
        add_btn.setStyleSheet(Styles.primary_button())
        add_btn.clicked.connect(lambda: self._add_employee())
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)

        self.emp_stack = QStackedWidget()

        empty = QWidget()
        empty_lay = QVBoxLayout(empty)
        empty_lay.addStretch(1)
        empty_title = QLabel("هنوز پرسنلی ثبت نشده است")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(Styles.section_title_label())
        empty_lay.addWidget(empty_title)
        empty_hint = QLabel(
            "اطلاعات کامل پرسنل (مشخصات فردی، پست سازمانی طبق چارت، محل خدمت "
            "فعلی، تماس و سوابق) را از اینجا وارد کنید.")
        empty_hint.setWordWrap(True)
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setStyleSheet(f"color: {c.fg_muted}; font-size: 12px;")
        empty_hint.setMaximumWidth(600)
        empty_lay.addWidget(empty_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        row = QHBoxLayout()
        row.addStretch(1)
        first_btn = QPushButton("+ ثبت اولین پرسنل")
        first_btn.setStyleSheet(Styles.primary_button())
        first_btn.clicked.connect(lambda: self._add_employee())
        row.addWidget(first_btn)
        row.addStretch(1)
        empty_lay.addLayout(row)
        empty_lay.addStretch(2)
        self.emp_stack.addWidget(empty)

        self.emp_table = QTableWidget(0, 8)
        self.emp_table.setHorizontalHeaderLabels([
            "#", "نام و نام خانوادگی", "کد پرسنلی", "پست سازمانی",
            "محل خدمت فعلی", "موبایل", "وضعیت خدمت", "فعال",
        ])
        self._style_small_table(self.emp_table)
        self.emp_table.verticalHeader().setDefaultSectionSize(34)
        header = self.emp_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.emp_table.itemSelectionChanged.connect(self._update_employee_buttons)
        self.emp_table.cellDoubleClicked.connect(
            lambda row, col: self._edit_selected_employee())
        self.emp_stack.addWidget(self.emp_table)
        layout.addWidget(self.emp_stack, 1)
        self.tabs.addTab(self.employees_tab, "فهرست پرسنل")

    # -------------------------------------------------------------- refresh
    def refresh(self):
        try:
            self._load_data()
            self._rebuild_chart()
            self._fill_employee_table()
            self._update_header_stats()
            self._update_action_states()
        except Exception:
            logger.exception("Could not refresh org chart page")
            QMessageBox.critical(
                self, "خطا", "بارگذاری چارت سازمانی با خطا مواجه شد.\n"
                "جزئیات در فایل log ثبت شد.")
        if self._fit_pending:
            QTimer.singleShot(0, self._try_fit)

    def _load_data(self):
        self._posts = org_post_repo.get_ordered()
        self._posts_by_id = {p.id: p for p in self._posts}
        self._children = defaultdict(list)
        roots = []
        for post in self._posts:
            if post.parent_id and post.parent_id in self._posts_by_id:
                self._children[post.parent_id].append(post)
            else:
                roots.append(post)

        def order(post):
            return (post.sort_order or 0, post.id)

        for group in self._children.values():
            group.sort(key=order)
        roots.sort(key=order)

        reachable = set()

        def mark(post):
            if post.id in reachable:
                return
            reachable.add(post.id)
            for child in self._children.get(post.id, []):
                mark(child)

        for root in roots:
            mark(root)
        for post in self._posts:
            if post.id not in reachable:
                roots.append(post)
        self._roots = roots

        self._employees = employee_repo.get_all_with_post()
        self._employees_by_post = defaultdict(list)
        for emp in self._employees:
            if emp.post_id:
                self._employees_by_post[emp.post_id].append(emp)

        if (self._selected_post_id is not None
                and self._selected_post_id not in self._posts_by_id):
            self._selected_post_id = None
        if self._selected_post_id is None and self._roots and not self._cards:
            self._selected_post_id = self._roots[0].id

    def _rebuild_chart(self):
        old_scale = None
        old_center = None
        if (not self._fit_pending and self._chart_scene is not None
                and not self._chart_scene.itemsBoundingRect().isEmpty()):
            old_scale = self.view.transform().m11()
            old_center = self.view.mapToScene(self.view.viewport().rect().center())

        scene, cards = build_chart_scene(
            self._posts, self._employees_by_post, self._roots, self._children,
            selected_post_id=self._selected_post_id,
            on_double_click=self._edit_post)
        old_scene = self._chart_scene
        self._chart_scene = scene
        self._cards = cards
        self.view.setScene(scene)
        self.view.setBackgroundBrush(
            QBrush(QColor(theme_manager.current.canvas_default)))
        try:
            scene.selectionChanged.connect(self._on_scene_selection)
        except Exception:
            pass
        if old_scene is not None:
            old_scene.deleteLater()

        if self._posts:
            self.chart_stack.setCurrentWidget(self.splitter)
        else:
            self.chart_stack.setCurrentWidget(self.empty_chart)
            self.detail_stack.setCurrentIndex(0)

        if self._selected_post_id in cards:
            self._show_details(self._selected_post_id)
        elif self._posts:
            self.detail_stack.setCurrentIndex(0)
        self._apply_search(self._search_term, center=False)

        if self._fit_pending or old_scale is None:
            QTimer.singleShot(0, self._try_fit)
        else:
            self.view.resetTransform()
            self.view.scale(old_scale, old_scale)
            if old_center is not None:
                self.view.centerOn(old_center)
            self.zoom_label.setText(f"{_fa(round(old_scale * 100))}٪")

    def _try_fit(self):
        if not self._posts:
            self._fit_pending = True
            return
        if self.view.viewport().width() < 300:
            return
        self.view.fit_width()
        self._fit_pending = False

    def _fit_all(self):
        if not self._posts:
            return
        self.view.fit_all()
        self._fit_pending = False

    def _on_zoom_changed(self, value):
        self.zoom_label.setText(f"{_fa(round(value * 100))}٪")

    def _update_header_stats(self):
        posts_count = len(self._posts)
        active = sum(1 for e in self._employees if e.is_active)
        total = len(self._employees)
        occupied = {e.post_id for e in self._employees
                    if e.is_active and e.post_id}
        vacant = sum(1 for p in self._posts if p.id not in occupied)
        text = (f"{_fa(posts_count)} پست سازمانی • {_fa(total)} پرسنل "
                f"({_fa(active)} شاغل)")
        if posts_count:
            text += f" • {_fa(vacant)} پست بدون متصدی"
        self.stats_label.setText(text)

    def _update_action_states(self):
        has_posts = bool(self._posts)
        has_emp = bool(self._employees)
        self.print_chart_action.setEnabled(has_posts)
        self.print_org_list_action.setEnabled(has_posts)
        self.print_employees_action.setEnabled(has_emp)
        self.print_btn.setEnabled(has_posts or has_emp)
        self.add_post_btn.setEnabled(True)
        self.add_employee_btn.setEnabled(True)
        self.search_edit.setEnabled(has_posts)
        self.zoom_in_btn.setEnabled(has_posts)
        self.zoom_out_btn.setEnabled(has_posts)
        self.fit_btn.setEnabled(has_posts)

    # --------------------------------------------------------------- chart
    def _on_scene_selection(self):
        if self._populating:
            return
        scene = self._chart_scene
        if scene is None:
            return
        card = next((x for x in scene.selectedItems()
                     if isinstance(x, PostCardItem)), None)
        if card is None:
            self._selected_post_id = None
            self.detail_stack.setCurrentIndex(0)
        else:
            self._selected_post_id = card.post.id
            self._show_details(card.post.id)

    def _show_details(self, post_id):
        post = self._posts_by_id.get(post_id)
        if post is None:
            self.detail_stack.setCurrentIndex(0)
            return
        self._populating = True
        try:
            self.detail_stack.setCurrentIndex(1)
            self.detail_title.setText(post.title or "—")
            accent = _accent_for(post)
            self.detail_category.setText(post.category or "بدون حوزه")
            self.detail_category.setStyleSheet(
                Styles.badge(accent, "subtle")
                + "QLabel { padding: 3px 10px; }")
            parent = self._posts_by_id.get(post.parent_id)
            self.detail_parent.setText(parent.title if parent else "— سطح اول —")
            self.detail_code.setText(post.code or "—")
            self.detail_approved.setText(_fa(post.approved_count or 0))
            child_count = len(self._children.get(post.id, []))
            self.detail_children.setText(f"{_fa(child_count)} پست")

            employees = list(self._employees_by_post.get(post.id, []))
            self.detail_emp_table.setRowCount(0)
            for emp in employees:
                row = self.detail_emp_table.rowCount()
                self.detail_emp_table.insertRow(row)
                name_item = QTableWidgetItem(
                    emp.full_name + ("" if emp.is_active else " (غیرفعال)"))
                name_item.setData(Qt.ItemDataRole.UserRole, emp.id)
                name_item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                place = (emp.workplace or "").strip()
                post_title = (emp.post.title if emp.post else post.title) or ""
                place_text = place or "طبق پست"
                place_item = QTableWidgetItem(place_text)
                place_item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                if not emp.is_active:
                    name_item.setForeground(QBrush(QColor(theme_manager.current.fg_muted)))
                    place_item.setForeground(QBrush(QColor(theme_manager.current.fg_muted)))
                elif place and place != post_title:
                    place_item.setForeground(QBrush(QColor(theme_manager.current.accent_blue)))
                self.detail_emp_table.setItem(row, 0, name_item)
                self.detail_emp_table.setItem(row, 1, place_item)

            has_emp = bool(employees)
            self.detail_emp_table.setVisible(has_emp)
            self.detail_no_emp.setVisible(not has_emp)
            self.detail_emp_edit_btn.setEnabled(False)
            self.detail_emp_del_btn.setEnabled(False)
            self.detail_add_emp_btn.setText("افزودن پرسنل به این پست")
        finally:
            self._populating = False

    def _on_search(self, text):
        self._search_term = text or ""
        self._apply_search(self._search_term, center=True)

    def _apply_search(self, term, center=False):
        normalized = _norm(term).strip()
        first = None
        for card in self._cards.values():
            match = (not normalized) or (normalized in card.search_blob)
            card.setOpacity(1.0 if match else 0.24)
            if match and first is None:
                first = card
        if normalized and center and first is not None:
            self.view.centerOn(first)
        if not normalized:
            for card in self._cards.values():
                card.setOpacity(1.0)

    # ------------------------------------------------------------- actions
    def _import_excel(self):
        start_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation) or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل چارت سازمانی", start_dir,
            "فایل اکسل (*.xlsx *.xlsm)")
        if not path:
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            chart = parse_org_chart(path)
        except Exception as e:
            logger.exception("Org chart import parse failed")
            QMessageBox.critical(
                self, "خطا در خواندن فایل",
                f"خواندن فایل چارت ممکن نشد:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        levels = max((n.depth for n in chart.nodes), default=0) + 1
        message = (
            f"{_fa(len(chart.nodes))} پست سازمانی در فایل شناسایی شد.\n"
            f"ریشهٔ چارت: {chart.root_title}\n"
            f"تعداد سطوح: {_fa(levels)}\n\n"
            "پست‌های قبلیِ واردشده از همین فایل به‌روزرسانی می‌شوند و "
            "اطلاعات پرسنل دست‌نخورده می‌ماند. پست‌هایی که دستی ساخته "
            "شده‌اند حذف نمی‌شوند.")
        if chart.warnings:
            message += "\n\nهشدارها:\n" + "\n".join(chart.warnings)
        message += "\n\nورود چارت انجام شود؟"
        if not confirm(self, "ورود چارت از Excel", message,
                       yes_text="ورود چارت"):
            return

        try:
            result = apply_org_chart(chart)
        except Exception as e:
            logger.exception("Org chart import failed")
            QMessageBox.critical(self, "خطا در ورود چارت", str(e))
            return
        self._fit_pending = True
        root_key = chart.root.key
        self.refresh()
        root_post = next(
            (p for p in self._posts if p.chart_key == root_key), None)
        if root_post is not None:
            self._select_post(root_post.id)
        QMessageBox.information(
            self, "ورود چارت",
            f"چارت سازمانی وارد شد.\n"
            f"{_fa(result.get('added', 0))} پست جدید و "
            f"{_fa(result.get('updated', 0))} پست به‌روزرسانی شد.\n"
            "حالا می‌توانید پرسنل را به پست‌ها متصل کنید.")

    def _select_post(self, post_id):
        self._selected_post_id = post_id
        card = self._cards.get(post_id)
        if card is None:
            self.detail_stack.setCurrentIndex(0)
            return
        scene = self._chart_scene
        if scene is not None:
            scene.clearSelection()
        card.setSelected(True)
        self.view.ensureVisible(card, 60, 60)
        self._show_details(post_id)

    def _add_post(self, parent_id=None):
        if parent_id is None:
            if self._selected_post_id in self._posts_by_id:
                parent_id = self._selected_post_id
            elif self._roots:
                parent_id = self._roots[0].id
        dlg = OrgPostDialog(
            self, posts=self._posts, default_parent_id=parent_id)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.saved_id:
            self._selected_post_id = dlg.saved_id
            self.refresh()
            self._select_post(dlg.saved_id)

    def _edit_post(self, post_id):
        if post_id not in self._posts_by_id:
            return
        dlg = OrgPostDialog(self, post_id=post_id, posts=self._posts)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._selected_post_id = post_id
            self.refresh()
            self._select_post(post_id)

    def _delete_post(self, post_id):
        post = self._posts_by_id.get(post_id)
        if post is None:
            return
        descendants = 0
        stack = [post.id]
        seen = set()
        while stack:
            current = stack.pop()
            for child in self._children.get(current, []):
                if child.id not in seen:
                    seen.add(child.id)
                    stack.append(child.id)
        descendants = len(seen)
        extra = ""
        if descendants:
            extra = (f"{_fa(descendants)} پست زیرمجموعه هم حذف می‌شود. ")
        extra += "پرسنل این پست‌ها بدون پست سازمانی می‌مانند (اطلاعاتشان حذف نمی‌شود)."
        if not confirm_delete(self, noun="پست سازمانی", name=post.title,
                              extra=extra):
            return
        try:
            org_post_repo.delete(post.id)
        except Exception as e:
            logger.exception("Could not delete org post")
            QMessageBox.critical(self, "خطا در حذف", str(e))
            return
        if self._selected_post_id == post.id:
            self._selected_post_id = None
        self.refresh()

    def _add_employee(self, post_id=None):
        if post_id is None:
            post_id = self._selected_post_id
        dlg = EmployeeDialog(
            self, posts=self._posts, default_post_id=post_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            if post_id is not None:
                self._select_post(post_id)
            if self.emp_search.text().strip():
                self.emp_search.clear()

    def _edit_employee(self, employee_id):
        dlg = EmployeeDialog(self, employee_id=employee_id, posts=self._posts)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _delete_employee(self, employee_id):
        emp = next((e for e in self._employees if e.id == employee_id), None)
        if emp is None:
            return
        if not confirm_delete(self, noun="پرسنل", name=emp.full_name):
            return
        try:
            employee_repo.delete(emp.id)
        except Exception as e:
            logger.exception("Could not delete employee")
            QMessageBox.critical(self, "خطا در حذف", str(e))
            return
        self.refresh()

    def _current_detail_employee_id(self):
        row = self.detail_emp_table.currentRow()
        if row < 0:
            return None
        item = self.detail_emp_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _edit_detail_employee(self):
        emp_id = self._current_detail_employee_id()
        if emp_id is not None:
            self._edit_employee(emp_id)

    def _delete_detail_employee(self):
        emp_id = self._current_detail_employee_id()
        if emp_id is not None:
            self._delete_employee(emp_id)

    def _update_detail_employee_buttons(self):
        has_selection = self._current_detail_employee_id() is not None
        self.detail_emp_edit_btn.setEnabled(has_selection)
        self.detail_emp_del_btn.setEnabled(has_selection)

    # ----------------------------------------------------------- employees
    def _filtered_employees(self):
        term = _norm(self.emp_search.text()).strip()
        if not term:
            return list(self._employees)
        out = []
        for emp in self._employees:
            try:
                post_title = emp.post.title if emp.post else ""
            except Exception:
                post_title = ""
            blob = _norm(" ".join(str(x) for x in [
                emp.full_name, emp.personnel_code, emp.national_code,
                post_title, emp.workplace, emp.mobile, emp.phone,
                emp.employment_status, emp.employment_type,
            ] if x))
            if term in blob:
                out.append(emp)
        return out

    def _fill_employee_table(self):
        rows = self._filtered_employees()
        self.emp_stack.setCurrentWidget(
            self.emp_table if self._employees else self.emp_stack.widget(0))
        self.emp_table.setRowCount(0)
        c = theme_manager.current
        for index, emp in enumerate(rows, 1):
            row = self.emp_table.rowCount()
            self.emp_table.insertRow(row)
            post_title = ""
            try:
                post_title = emp.post.title if emp.post else ""
            except Exception:
                post_title = ""
            place = (emp.workplace or "").strip()
            place_text = place or ("طبق پست" if post_title else "—")
            values = [
                str(index), emp.full_name, emp.personnel_code or "—",
                post_title or "—", place_text, emp.mobile or "—",
                emp.employment_status or "—",
                "بله" if emp.is_active else "خیر",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in (0, 7):
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                else:
                    item.setTextAlignment(
                        int(Qt.AlignmentFlag.AlignRight
                            | Qt.AlignmentFlag.AlignVCenter))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, emp.id)
                if not emp.is_active:
                    item.setForeground(QBrush(QColor(c.fg_muted)))
                elif col == 4 and place and place != post_title:
                    item.setForeground(QBrush(QColor(c.accent_blue)))
                self.emp_table.setItem(row, col, item)
            tooltip = [emp.full_name]
            if post_title:
                tooltip.append(f"پست سازمانی: {post_title}")
            if place:
                tooltip.append(f"محل خدمت فعلی: {place}")
            if emp.national_code:
                tooltip.append(f"کد ملی: {emp.national_code}")
            if emp.mobile:
                tooltip.append(f"موبایل: {emp.mobile}")
            for col in range(self.emp_table.columnCount()):
                cell = self.emp_table.item(row, col)
                if cell is not None:
                    cell.setToolTip("\n".join(tooltip))

        self.emp_edit_btn.setEnabled(False)
        self.emp_delete_btn.setEnabled(False)
        total = len(self._employees)
        if self.emp_search.text().strip():
            self.emp_count_label.setText(
                f"{_fa(len(rows))} از {_fa(total)} نفر")
        else:
            self.emp_count_label.setText(f"{_fa(total)} نفر")

    def _selected_employee_id(self):
        row = self.emp_table.currentRow()
        if row < 0:
            return None
        item = self.emp_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_employee_buttons(self):
        has_selection = self._selected_employee_id() is not None
        self.emp_edit_btn.setEnabled(has_selection)
        self.emp_delete_btn.setEnabled(has_selection)

    def _edit_selected_employee(self):
        emp_id = self._selected_employee_id()
        if emp_id is not None:
            self._edit_employee(emp_id)

    def _delete_selected_employee(self):
        emp_id = self._selected_employee_id()
        if emp_id is not None:
            self._delete_employee(emp_id)

    # -------------------------------------------------------------- prints
    def _root_title(self):
        return self._roots[0].title if self._roots else ""

    def _show_print_menu(self):
        self.print_menu.exec(
            self.print_btn.mapToGlobal(self.print_btn.rect().bottomLeft()))

    def _print_chart(self):
        if not self._posts or self._chart_scene is None:
            QMessageBox.information(
                self, "چاپ چارت", "چارت سازمانی برای چاپ وجود ندارد.")
            return
        subtitle = (f"ریشه: {self._root_title()} — "
                    f"{_fa(len(self._posts))} پست سازمانی")
        print_org_chart_scene(
            self, self._chart_scene, "چارت سازمانی", subtitle)

    def _print_org_list(self):
        if not self._posts:
            QMessageBox.information(
                self, "چاپ فهرست", "چارت سازمانی برای چاپ وجود ندارد.")
            return
        html = build_org_chart_list_html(
            self._posts, self._employees_by_post, "چارت سازمانی")
        print_document(self, "چارت سازمانی", html, landscape=True)

    def _print_employees(self):
        if not self._employees:
            QMessageBox.information(
                self, "چاپ فهرست پرسنل", "پرسنلی برای چاپ وجود ندارد.")
            return
        html = build_employees_report_html(self._employees, "فهرست پرسنل")
        print_document(self, "فهرست پرسنل", html, landscape=True)

    def showEvent(self, event):
        super().showEvent(event)
        if self._fit_pending:
            QTimer.singleShot(0, self._try_fit)
