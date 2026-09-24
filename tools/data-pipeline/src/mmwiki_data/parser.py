"""从 HTML 中提取表格事实与有限上下文。"""

from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from mmwiki_data.models import ExtractedTable, MergedCell


@dataclass(frozen=True, slots=True)
class PageExtraction:
    """不包含完整页面正文的解析结果。"""

    title: str
    tables: list[ExtractedTable]
    excerpts: list[str]
    warnings: list[str]


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def extract_page(body: bytes) -> PageExtraction:
    """提取带表头的表格，并限制保存的上下文长度。"""
    soup = BeautifulSoup(body, "html.parser")
    title_tag = soup.find("h1")
    title = _text(title_tag) if isinstance(title_tag, Tag) else ""
    tables: list[ExtractedTable] = []
    excerpts: list[str] = []
    warnings: list[str] = []

    for table_index, table in enumerate(soup.find_all("table"), start=1):
        rows = table.find_all("tr")
        if not rows:
            warnings.append(f"table {table_index}: skipped because it has no rows")
            continue

        header_cells = rows[0].find_all("th")
        if not header_cells:
            warnings.append(f"table {table_index}: skipped because it has no header cells")
            continue

        headers = [_text(cell) for cell in header_cells]
        if any(not header for header in headers) or len(set(headers)) != len(headers):
            warnings.append(
                f"table {table_index}: skipped because its headers are empty or repeated"
            )
            continue

        heading = table.find_previous(["h1", "h2", "h3"])
        section = _text(heading) if isinstance(heading, Tag) else title or f"table-{table_index}"
        extracted_rows: list[dict[str, str]] = []
        merged_cells: list[MergedCell] = []
        for row_index, row in enumerate(rows[1:], start=2):
            cells = row.find_all(["td", "th"])
            values: list[str] = []
            row_merged_cells: list[MergedCell] = []
            for cell in cells:
                value = _text(cell)
                raw_colspan = cell.get("colspan", "1")
                try:
                    colspan = max(1, int(str(raw_colspan)))
                except ValueError:
                    colspan = 1
                    warnings.append(
                        f"{section}: row {row_index} has invalid colspan {raw_colspan!r}"
                    )
                start_index = len(values)
                values.append(value)
                values.extend("" for _ in range(colspan - 1))
                end_index = len(values) - 1
                if colspan > 1 and end_index < len(headers):
                    row_merged_cells.append(
                        MergedCell(
                            row_index=row_index,
                            start_header=headers[start_index],
                            end_header=headers[end_index],
                            value=value,
                        )
                    )
            if len(values) != len(headers):
                warnings.append(
                    f"{section}: skipped row {row_index} because it has {len(values)} cells, "
                    f"expected {len(headers)}"
                )
                continue
            extracted_rows.append(dict(zip(headers, values, strict=True)))
            merged_cells.extend(row_merged_cells)

        tables.append(
            ExtractedTable(
                section=section,
                headers=headers,
                rows=extracted_rows,
                merged_cells=merged_cells,
            )
        )

        context = table.find_previous("p")
        if isinstance(context, Tag):
            excerpt = _text(context)[:300]
            if excerpt and excerpt not in excerpts and len(excerpts) < 3:
                excerpts.append(excerpt)

    return PageExtraction(title=title, tables=tables, excerpts=excerpts, warnings=warnings)
