"""ورود چارت سازمانی از فایل اکسلِ ترسیمی (کادرهای ادغام‌شده).

هر کادر اکسل یک «پست سازمانی» می‌شود. سلسله‌مراتب از چیدمان کادرها
استنتاج می‌شود: معاونین زیر فرماندار، رئیس اداره زیر معاون، کارشناسان
هم‌ستون زیر رئیس اداره، و بخشداران با کارکنانشان در ردیف جداگانه.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import openpyxl

from core.database import get_db
from models.models import OrgPost


@dataclass
class _Box:
    title: str
    row1: int
    row2: int
    col1: int
    col2: int
    key: str


@dataclass
class ChartNode:
    key: str
    title: str
    parent_key: Optional[str]
    category: str
    sort_order: int
    depth: int = 0


@dataclass
class ParsedChart:
    nodes: List[ChartNode]
    root_title: str
    warnings: List[str] = field(default_factory=list)

    @property
    def root(self) -> ChartNode:
        return next(n for n in self.nodes if n.parent_key is None)


def _clean(value) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    text = text.replace("بخسدار", "بخشدار")
    return text


def _collect_boxes(ws) -> List[_Box]:
    merged_coords = set()
    for rng in ws.merged_cells.ranges:
        for row in ws[rng.coord]:
            for cell in row:
                merged_coords.add(cell.coordinate)

    boxes = []
    for rng in ws.merged_cells.ranges:
        title = _clean(ws.cell(rng.min_row, rng.min_col).value)
        if not title:
            continue
        boxes.append(_Box(
            title=title, row1=rng.min_row, row2=rng.max_row,
            col1=rng.min_col, col2=rng.max_col,
            key=f"{ws.title}!{rng.coord.split(':')[0]}",
        ))

    seen = {(b.row1, b.col1) for b in boxes}
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value is None or cell.coordinate in merged_coords:
                continue
            if (cell.row, cell.column) in seen:
                continue
            title = _clean(cell.value)
            if not title:
                continue
            boxes.append(_Box(
                title=title, row1=cell.row, row2=cell.row,
                col1=cell.column, col2=cell.column,
                key=f"{ws.title}!{cell.coordinate}",
            ))
    return boxes


def _within(box: _Box, container: _Box) -> bool:
    return box.col1 >= container.col1 and box.col2 <= container.col2


def parse_org_chart(path: str) -> ParsedChart:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    try:
        ws = wb.active
        boxes = [
            b for b in _collect_boxes(ws)
            if b.title not in ("چارت سازمانی", "چارت", "نمودار سازمانی")
        ]
        if not boxes:
            raise ValueError("در فایل هیچ کادر سازمانی شناسایی نشد.")

        warnings = []
        governor_boxes = [b for b in boxes if "فرماندار" in b.title]
        if governor_boxes:
            root_box = min(governor_boxes, key=lambda b: b.row1)
        else:
            root_box = min(boxes, key=lambda b: (b.row1, b.col1))
            warnings.append("کادر فرماندار پیدا نشد؛ بالاترین کادر به‌عنوان ریشه انتخاب شد.")

        others = [b for b in boxes if b.key != root_box.key]
        district_boxes = [b for b in others if b.title.startswith("بخشدار")]
        district_row = min((b.row1 for b in district_boxes), default=None)

        deputy_boxes = [
            b for b in others
            if b.title.startswith("معاون")
            and (district_row is None or b.row1 < district_row)
        ]
        if not deputy_boxes:
            warnings.append("کادر معاونت شناسایی نشد؛ همهٔ کادرها زیر فرماندار قرار می‌گیرند.")

        parent_of = {}
        assigned = set()

        for deputy in deputy_boxes:
            parent_of[deputy.key] = root_box.key
            assigned.add(deputy.key)
            candidates = [
                b for b in others
                if b.key not in assigned and b.key != root_box.key
                and _within(b, deputy) and b.row1 > deputy.row1
                and (district_row is None or b.row1 < district_row)
            ]
            if not candidates:
                continue
            heads = [b for b in candidates if b.title.startswith("رئیس اداره")]
            head = min(heads or candidates, key=lambda b: (b.row1, b.col1))
            parent_of[head.key] = deputy.key
            assigned.add(head.key)
            for b in candidates:
                if b.key == head.key:
                    continue
                parent_of[b.key] = head.key
                assigned.add(b.key)

        for district in district_boxes:
            parent_of[district.key] = root_box.key
            assigned.add(district.key)
            for b in others:
                if b.key in assigned or b.key == root_box.key:
                    continue
                if _within(b, district) and b.row1 > district.row1:
                    parent_of[b.key] = district.key
                    assigned.add(b.key)

        # حراست: کارشناس زیر «کارشناس مسئول حراست» همان ستون قرار می‌گیرد.
        security_boxes = sorted(
            [b for b in others if "حراست" in b.title and b.key not in assigned],
            key=lambda b: (b.row1, b.col1),
        )
        for box in security_boxes:
            heads = [
                h for h in security_boxes
                if h.key != box.key and h.row1 < box.row1
                and h.col1 <= box.col1 <= h.col2
            ]
            if heads:
                parent_of[box.key] = max(heads, key=lambda h: h.row1).key
                assigned.add(box.key)

        for b in others:
            if b.key not in assigned:
                parent_of[b.key] = root_box.key
                assigned.add(b.key)

        nodes_by_key = {}
        nodes_by_key[root_box.key] = ChartNode(
            key=root_box.key, title=root_box.title, parent_key=None,
            category="فرمانداری", sort_order=0,
        )

        def category_for(box: _Box) -> str:
            chain = []
            key = box.key
            seen = set()
            while key and key not in seen:
                seen.add(key)
                chain.append(key)
                key = parent_of.get(key)
            chain.append(root_box.key)
            for key in reversed(chain):
                if key in {d.key for d in deputy_boxes}:
                    return next(d.title for d in deputy_boxes if d.key == key)
                if key in {d.key for d in district_boxes}:
                    return next(d.title for d in district_boxes if d.key == key)
                if key != root_box.key and "حراست" in next(
                        b.title for b in boxes if b.key == key):
                    return "حراست"
            return "حوزهٔ فرماندار"

        sibling_order = {}
        for b in others:
            parent_key = parent_of[b.key]
            sibling_order.setdefault(parent_key, []).append(b)

        for parent_key, children in sibling_order.items():
            children.sort(key=lambda b: (b.row1, b.col1))
            base = 0
            for box in children:
                base += 10
                nodes_by_key[box.key] = ChartNode(
                    key=box.key, title=box.title,
                    parent_key=parent_key,
                    category=category_for(box),
                    sort_order=base,
                )

        def depth_of(node: ChartNode) -> int:
            depth = 0
            seen = set()
            current = node
            while current.parent_key and current.parent_key not in seen:
                seen.add(current.parent_key)
                current = nodes_by_key[current.parent_key]
                depth += 1
            return depth

        nodes = list(nodes_by_key.values())
        for node in nodes:
            node.depth = depth_of(node)
        nodes.sort(key=lambda n: (n.depth, n.sort_order))

        return ParsedChart(nodes=nodes, root_title=root_box.title, warnings=warnings)
    finally:
        wb.close()


def apply_org_chart(chart: ParsedChart) -> dict:
    """درج/به‌روزرسانی پست‌های چارت؛ دادهٔ پرسنل دست‌نخورده می‌ماند."""
    session = get_db()
    try:
        existing = {
            post.chart_key: post
            for post in session.query(OrgPost).filter(OrgPost.chart_key.isnot(None)).all()
        }
        key_to_id = {}
        added = updated = 0
        for node in sorted(chart.nodes, key=lambda n: (n.depth, n.sort_order)):
            parent_id = key_to_id.get(node.parent_key) if node.parent_key else None
            row = existing.get(node.key)
            if row is None:
                row = OrgPost(
                    title=node.title,
                    parent_id=parent_id,
                    category=node.category,
                    sort_order=node.sort_order,
                    chart_key=node.key,
                )
                session.add(row)
                session.flush()
                added += 1
            else:
                row.title = node.title
                row.parent_id = parent_id
                row.category = node.category
                row.sort_order = node.sort_order
                updated += 1
            key_to_id[node.key] = row.id
        session.commit()
        return {"added": added, "updated": updated, "total": len(chart.nodes)}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
