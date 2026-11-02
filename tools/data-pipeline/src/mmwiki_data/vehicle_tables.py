"""战车部件来源的表格与获取地点解析。"""

import re
from decimal import Decimal

from bs4 import Tag


def text(tag: Tag) -> str:
    """合并页面空白，保留单元格原值。"""
    return " ".join(tag.get_text(" ", strip=True).split())


def expanded_rows(table: Tag) -> list[list[str]]:
    """展开行列合并单元格，避免把数值错配到其他字段。"""
    cells: dict[tuple[int, int], str] = {}
    output: list[list[str]] = []
    for row_index, row in enumerate(table.find_all("tr")):
        column = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (row_index, column) in cells:
                column += 1
            colspan = int(str(cell.get("colspan", "1")))
            rowspan = int(str(cell.get("rowspan", "1")))
            if not 1 <= colspan <= 20 or not 1 <= rowspan <= 20:
                raise ValueError("战车部件表格包含不支持的跨行或跨列范围")
            for row_offset in range(rowspan):
                for column_offset in range(colspan):
                    key = (row_index + row_offset, column + column_offset)
                    if key in cells:
                        raise ValueError("战车部件表格的合并单元格发生重叠")
                    cells[key] = text(cell)
            column += colspan
        width = max((key[1] + 1 for key in cells if key[0] == row_index), default=0)
        output.append([cells.get((row_index, index), "") for index in range(width)])
    return output


def acquisition_entries(content: Tag, *, top_level_only: bool = False) -> list[str]:
    """仅提取销售和其他获取地点，排除攻略评论。"""
    acquisition: list[str] = []
    for section in content.find_all(["h2", "h3"]):
        if not any(label in text(section) for label in ("販売箇所", "その他入手法")):
            continue
        label = "店铺" if "販売箇所" in text(section) else "其他获取"
        for sibling in section.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            if sibling.name in ("h2", "h3"):
                break
            if sibling.name not in ("ul", "ol", "p"):
                continue
            if top_level_only and sibling.name in ("ul", "ol"):
                parts = [
                    child.get_text(" ", strip=True) if isinstance(child, Tag) else str(child)
                    for item in sibling.find_all("li", recursive=False)
                    for child in item.contents
                    if not isinstance(child, Tag) or child.name not in ("ul", "ol")
                ]
                value = " ".join(" ".join(parts).split())
            else:
                value = text(sibling)
            if value and value not in ("なし", "無し", "↑"):
                acquisition.append(f"{label}：{value}")
    return acquisition


def comparable_stat(value: str) -> Decimal | str:
    """数值比较忽略小数末尾零，保留复合记法。"""
    value = value.removesuffix("t")
    if re.fullmatch(r"-+", value):
        return "-"
    return Decimal(value) if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) else value


def obtainable_stars(rarity: str, acquisition: list[str], name: str) -> list[int]:
    """合并总表标记与获取地点中的明确星级范围。"""
    stars: set[int] = set()
    if re.fullmatch(r"★{1,3}", rarity):
        stars.add(len(rarity))
    elif re.fullmatch(r"☆{1,3}", rarity):
        stars.update(range(len(rarity) + 1))
    elif rarity == "-":
        stars.add(0)
    for location in acquisition:
        for match in re.finditer(r"★([0-3])(?:\s*[～〜~-]\s*★?([0-3]))?", location):
            start = int(match[1])
            end = int(match[2]) if match[2] is not None else start
            if end < start:
                raise ValueError(f"{name}: 来源星级范围倒置")
            stars.update(range(start, end + 1))
    return sorted(stars)
