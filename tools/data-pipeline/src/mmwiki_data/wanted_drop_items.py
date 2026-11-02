"""采集赏金首掉落物的逐页事实表，保留星级和数值条件。"""

import argparse
import json
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import ConfigDict, Field, HttpUrl, model_validator

from mmwiki_data.fetcher import FetchResult, fetch
from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import NormalizedBundle, SourceRef
from mmwiki_data.storage import model_content_hash, write_json_atomic
from mmwiki_data.vehicle_tables import text
from mmwiki_data.wanted_monsters import WantedMonsterSnapshot

SOURCE_ID = "metalmaniax-mm2r"
TARGET_ID = "maniax-wanted-drop-items"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E8%B3%9E%E9%87%91%E9%A6%96"
HUMAN_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E4%BA%BA%E9%96%93"
TANK_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A"
_ROOT = Path("data/raw/mm2r/0.99/wanted-drop-items")
_WANTED = Path("data/raw/mm2r/0.99/wanted-monsters/facts.json")
_STAR = re.compile(r"(?:無印|[-－]|★{1,3})")
NonEmpty = Annotated[str, Field(min_length=1)]
Scalar = str | int | float | bool | None


class DropItemStrictModel(StrictModel):
    """拒绝未声明字段和隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class DropItemNames(DropItemStrictModel):
    schema_version: Literal[1]
    reference_note: NonEmpty
    condition_note: NonEmpty
    names: dict[str, str]
    effects: dict[str, str]
    categories: dict[str, str]
    category_labels: dict[str, str]
    field_labels: dict[str, str]
    source_aliases: dict[str, str]
    source_alias_notes: dict[str, str]

    @model_validator(mode="after")
    def validate_coverage(self) -> DropItemNames:
        """每种物品都必须具备参考名、类别与简要作用。"""
        expected = set(self.names)
        if len(expected) != 89 or set(self.effects) != expected or set(self.categories) != expected:
            raise ValueError("掉落物参考名、类别和作用必须完整覆盖89种物品")
        if set(self.source_aliases) != set(self.source_alias_notes):
            raise ValueError("掉落物来源别名必须有逐项说明")
        if set(self.source_aliases.values()) - expected:
            raise ValueError("掉落物来源别名指向未知物品")
        if set(self.categories.values()) - set(self.category_labels):
            raise ValueError("掉落物类别缺少中文标签")
        if any(
            not value.strip() for group in (self.names, self.effects) for value in group.values()
        ):
            raise ValueError("掉落物参考名称或作用为空")
        return self


class DropItemCell(DropItemStrictModel):
    text: str
    rowspan: Annotated[int, Field(ge=1, le=4096)] = 1
    colspan: Annotated[int, Field(ge=1, le=128)] = 1
    is_header: bool


class DropItemTableRow(DropItemStrictModel):
    values: list[str] = Field(min_length=1, max_length=128)
    condition_raw: NonEmpty
    source_ref: SourceRef
    cells: list[DropItemCell] = Field(min_length=1, max_length=128)


class DropItemTable(DropItemStrictModel):
    caption_ja: NonEmpty
    headers: list[str] = Field(min_length=1, max_length=128)
    header_rows: list[list[str]] = Field(max_length=4)
    rows: list[DropItemTableRow] = Field(min_length=1, max_length=128)
    source_ref: SourceRef
    alignment_issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_width(self) -> DropItemTable:
        """展开列必须等宽，原始合并格另行保留。"""
        if any(len(row.values) != len(self.headers) for row in self.rows):
            raise ValueError("掉落物事实表的展开行与表头列数不一致")
        return self


class DropItemProperty(DropItemStrictModel):
    label_ja: NonEmpty
    value_raw: str
    condition_raw: NonEmpty
    source_ref: SourceRef


class DropItemUse(DropItemStrictModel):
    wanted_name_ja: NonEmpty
    enemy_name_ja: NonEmpty
    slot: Literal[1, 2, 3]
    item_ja: NonEmpty
    rate_raw: NonEmpty
    source_ref: SourceRef


class InheritedDropItemFacts(DropItemStrictModel):
    record_id: NonEmpty
    bundle_file: NonEmpty
    bundle_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: NonEmpty
    attributes: dict[str, Scalar]
    condition_raw: NonEmpty
    source_refs: list[SourceRef] = Field(min_length=1)


class WantedDropItemFact(DropItemStrictModel):
    canonical_item_ja: NonEmpty
    raw_names_ja: list[NonEmpty] = Field(min_length=1)
    detail_url: HttpUrl | None
    detail_ref: SourceRef | None
    discovery_refs: list[SourceRef] = Field(min_length=1)
    drop_uses: list[DropItemUse] = Field(min_length=1)
    tables: list[DropItemTable]
    overview_tables: list[DropItemTable]
    properties: list[DropItemProperty]
    inherited_facts: list[InheritedDropItemFacts]
    existing_record_ids: list[str]
    issues: list[str]

    @model_validator(mode="after")
    def validate_sources(self) -> WantedDropItemFact:
        """缺失详情与空页必须显式标记，不能伪造页内数值。"""
        if (self.detail_url is None) != (self.detail_ref is None):
            raise ValueError("掉落物详情地址与来源引用不完整")
        if self.detail_url is None and "no_detail_link" not in self.issues:
            raise ValueError("缺少详情链接却未记录来源限制")
        if (
            self.detail_url is not None
            and not self.tables
            and "detail_without_fact_tables" not in self.issues
        ):
            raise ValueError("空详情页未记录来源限制")
        refs = [*self.discovery_refs]
        if self.detail_ref is not None:
            refs.append(self.detail_ref)
        for table in (*self.tables, *self.overview_tables):
            refs.extend((table.source_ref, *(row.source_ref for row in table.rows)))
        refs.extend(item.source_ref for item in self.properties)
        for ref in refs:
            if ref.source_id != SOURCE_ID or ref.target_id != TARGET_ID:
                raise ValueError("掉落物新采集事实引用了错误来源")
            _validate_url(str(ref.source_url))
        return self


class WantedDropItemSnapshot(DropItemStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    version_scope: Literal["mm2r-jp"] = "mm2r-jp"
    verification_status: Literal["source_only"] = "source_only"
    wanted_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_locator_note: NonEmpty = (
        "新采集表格的table_index为#body内从0开始的表号，row_index为包含表头的原表物理行号；"
        "cells保留原格合并信息，values为同一行的展开值。继承记录和掉落槽沿用各自来源坐标。"
    )
    records: list[WantedDropItemFact] = Field(min_length=89, max_length=89)
    limitations: list[str]

    @model_validator(mode="after")
    def validate_complete(self) -> WantedDropItemSnapshot:
        """89种物品必须恰好覆盖93个原始掉落槽。"""
        if len({record.canonical_item_ja for record in self.records}) != 89:
            raise ValueError("掉落物快照包含重复物品")
        uses = [use for record in self.records for use in record.drop_uses]
        if len(uses) != 93 or len({(use.enemy_name_ja, use.slot) for use in uses}) != 93:
            raise ValueError("掉落物快照没有完整覆盖93个独立掉落槽")
        return self


def load_wanted_drop_item_names(repo_root: Path) -> DropItemNames:
    """读取中文参考名称、作用及字段标签。"""
    return DropItemNames.model_validate(
        yaml.safe_load((repo_root / _ROOT / "names.yaml").read_text(encoding="utf-8"))
    )


def wanted_snapshot_hash(snapshot: WantedMonsterSnapshot) -> str:
    """哈希已验证的规范JSON内容，排除缩进与换行等文件排版差异。"""
    return model_content_hash(snapshot)


def _canonical(value: str, names: DropItemNames) -> str:
    value = names.source_aliases.get(value, value)
    return unicodedata.normalize("NFKC", value).replace("‐", "-").replace("‑", "-")


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "metalmaniax.com"
        or parsed.path != "/index.php"
        or not unquote(parsed.query).startswith("MM2R/DATA/")
    ):
        raise ValueError(f"掉落物来源地址不在METAL MM2R数据范围：{url}")


def _ref(result: FetchResult, url: str, at: datetime, table: int = 0, row: int = 0) -> SourceRef:
    _validate_url(url)
    return SourceRef(
        source_id=SOURCE_ID,
        target_id=TARGET_ID,
        source_url=HttpUrl(url),
        retrieved_at=at,
        content_hash=result.content_hash,
        table_index=table,
        row_index=row,
    )


def _body(result: FetchResult, url: str) -> Tag:
    content = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if content is None:
        raise ValueError(f"掉落物来源缺少#body：{url}")
    return content


def _expanded(table: Tag) -> tuple[list[list[str]], list[int]]:
    """有界展开来源合并格，保留缺格标记而不补造数值。"""
    rows = table.find_all("tr")
    if not 1 <= len(rows) <= 4096:
        raise ValueError("掉落物表格超出1至4096行限制")
    cells: dict[tuple[int, int], str] = {}
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (row_index, column) in cells:
                column += 1
            rowspan, colspan = (
                int(str(cell.get("rowspan", "1"))),
                int(str(cell.get("colspan", "1"))),
            )
            if not 1 <= rowspan <= 4096 or not 1 <= colspan <= 128:
                raise ValueError("掉落物表格合并格跨度越界")
            if row_index + rowspan > len(rows) or column + colspan > 128:
                raise ValueError("掉落物表格合并格超出表格边界")
            for dy in range(rowspan):
                for dx in range(colspan):
                    key = row_index + dy, column + dx
                    if key in cells:
                        raise ValueError("掉落物表格合并格重叠")
                    cells[key] = text(cell)
            column += colspan
    if not cells:
        raise ValueError("掉落物表格没有单元格")
    width = max(column + 1 for _, column in cells)
    missing = [r for r in range(len(rows)) if any((r, c) not in cells for c in range(width))]
    return [[cells.get((r, c), "") for c in range(width)] for r in range(len(rows))], missing


def _caption(table: Tag) -> str:
    heading = table.find_previous(re.compile(r"^h[2-6]$"))
    return text(heading).removesuffix("†").strip() if isinstance(heading, Tag) else "基本情報"


def _header_count(table: Tag) -> int:
    head = table.find("thead")
    if isinstance(head, Tag):
        count = len(head.find_all("tr"))
        if count > 4:
            raise ValueError("掉落物表头超过四层")
        return count
    return 0


def _headers(header_rows: list[list[str]], width: int) -> list[str]:
    if not header_rows:
        return [f"列{i + 1}" for i in range(width)]
    return [
        "/".join(dict.fromkeys(row[column] for row in header_rows if row[column]))
        or f"列{column + 1}"
        for column in range(width)
    ]


def _page_rarity(content: Tag) -> str | None:
    for table in content.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            for i, cell in enumerate(cells[:-1]):
                if text(cell) == "レア度" and cells[i + 1].name == "td":
                    return text(cells[i + 1]) or None
    return None


def _condition(values: list[str], page_rarity: str | None, *, overview: bool) -> str:
    if values and _STAR.fullmatch(values[0]):
        return f"レア度：{values[0]}（同じ行の数値）"
    if overview:
        return "総表の掲載値；詳細ページの星別数値とは別条件"
    if page_rarity is not None:
        return f"ページのレア度表記：{page_rarity}"
    return "この行の原表値；星級未明示、星別行とは結合しない"


def _read_table(
    table: Tag,
    result: FetchResult,
    url: str,
    at: datetime,
    table_index: int,
    *,
    selected_rows: list[int] | None = None,
    page_rarity: str | None = None,
) -> DropItemTable:
    expanded, missing = _expanded(table)
    raw_rows = table.find_all("tr")
    count = _header_count(table)
    header_rows = expanded[:count]
    headers = _headers(header_rows, len(expanded[0]))
    indexes = selected_rows if selected_rows is not None else list(range(count, len(raw_rows)))
    rows = [
        DropItemTableRow(
            values=expanded[i],
            condition_raw=_condition(expanded[i], page_rarity, overview=selected_rows is not None),
            source_ref=_ref(result, url, at, table_index, i),
            cells=[
                DropItemCell(
                    text=text(cell),
                    rowspan=int(str(cell.get("rowspan", "1"))),
                    colspan=int(str(cell.get("colspan", "1"))),
                    is_header=cell.name == "th",
                )
                for cell in raw_rows[i].find_all(["td", "th"], recursive=False)
            ],
        )
        for i in indexes
    ]
    return DropItemTable(
        caption_ja=_caption(table),
        headers=headers,
        header_rows=header_rows,
        rows=rows,
        source_ref=_ref(result, url, at, table_index),
        alignment_issues=[
            f"原表第{i}物理行缺少单元格；展开值以空串保留，不能可靠对应缺失字段。"
            for i in indexes
            if i in missing
        ],
    )


def _properties(tables: list[DropItemTable], names: DropItemNames) -> list[DropItemProperty]:
    output: list[DropItemProperty] = []
    for table in tables:
        for row in table.rows:
            if table.alignment_issues:
                continue
            if table.header_rows and table.headers[0] == "名称":
                for header, value in zip(table.headers, row.values, strict=True):
                    output.append(
                        DropItemProperty(
                            label_ja=header,
                            value_raw=value,
                            condition_raw=row.condition_raw,
                            source_ref=row.source_ref,
                        )
                    )
            else:
                for left, right in zip(row.cells, row.cells[1:], strict=False):
                    if left.is_header and not right.is_header and left.text in names.field_labels:
                        output.append(
                            DropItemProperty(
                                label_ja=left.text,
                                value_raw=right.text,
                                condition_raw=row.condition_raw,
                                source_ref=row.source_ref,
                            )
                        )
    return output


def _inherited(
    repo_root: Path,
    names: DropItemNames,
) -> tuple[dict[str, list[InheritedDropItemFacts]], dict[str, list[str]]]:
    inherited: dict[str, list[InheritedDropItemFacts]] = {}
    record_ids: dict[str, list[str]] = {}
    for domain in ("items", "equipment"):
        relative = Path(f"data/interim/mm2r/0.99/{domain}.json")
        payload = (repo_root / relative).read_bytes()
        bundle = NormalizedBundle.model_validate_json(payload)
        digest = model_content_hash(bundle)
        for record in bundle.records:
            if record.names.ja is None:
                continue
            canonical = _canonical(record.names.ja, names)
            if canonical not in names.names:
                continue
            record_ids.setdefault(canonical, []).append(record.id)
            inherited.setdefault(canonical, []).append(
                InheritedDropItemFacts(
                    record_id=record.id,
                    bundle_file=str(relative),
                    bundle_hash=digest,
                    kind=record.kind,
                    attributes=record.attributes,
                    condition_raw=str(
                        record.attributes.get("stat_condition_raw") or "原记录未明示星级条件"
                    ),
                    source_refs=record.source_refs,
                )
            )
    return inherited, record_ids


def collect_wanted_drop_items(
    repo_root: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """串行采集89种掉落物，所有来源成功并完成校验后原子替换快照。"""
    names = load_wanted_drop_item_names(repo_root)
    wanted_bytes = (repo_root / _WANTED).read_bytes()
    wanted = WantedMonsterSnapshot.model_validate_json(wanted_bytes)
    uses: dict[str, list[DropItemUse]] = {}
    raw_names: dict[str, set[str]] = {}
    for record in wanted.records:
        for form in record.enemy_forms:
            for drop in form.drops:
                canonical = drop.canonical_item_ja
                if _canonical(drop.item_ja, names) != canonical:
                    raise ValueError(f"{canonical}: 掉落物错字或全角映射不一致")
                raw_names.setdefault(canonical, set()).add(drop.item_ja)
                uses.setdefault(canonical, []).append(
                    DropItemUse(
                        wanted_name_ja=record.overview.name_ja,
                        enemy_name_ja=form.canonical_name_ja,
                        slot=drop.slot,
                        item_ja=drop.item_ja,
                        rate_raw=drop.rate_raw,
                        source_ref=form.source_ref,
                    )
                )
    if set(uses) != set(names.names):
        raise ValueError("掉落物参考名称与93槽内的89种物品不一致")
    inherited, existing_ids = _inherited(repo_root, names)
    cached: dict[str, tuple[FetchResult, datetime]] = {}
    links: dict[str, str] = {}
    discoveries: dict[str, list[SourceRef]] = {name: [] for name in uses}
    overview_tables: dict[str, list[DropItemTable]] = {name: [] for name in uses}
    records: list[WantedDropItemFact] = []
    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"},
    ) as client:

        def get(url: str) -> tuple[FetchResult, datetime]:
            _validate_url(url)
            page = urldefrag(url)[0]
            if page not in cached:
                if cached:
                    sleep(1.0)
                cached[page] = fetch(client, TARGET_ID, page), datetime.now().astimezone()
            return cached[page]

        for url in (INDEX_URL, HUMAN_URL, TANK_URL):
            result, at = get(url)
            body = _body(result, url)
            for table_index, table in enumerate(body.find_all("table")):
                expanded, _missing = _expanded(table)
                groups: dict[str, list[int]] = {}
                for row_index, (row, values) in enumerate(
                    zip(table.find_all("tr"), expanded, strict=True)
                ):
                    if url != INDEX_URL and values:
                        canonical = _canonical(values[0], names)
                        if canonical in uses:
                            groups.setdefault(canonical, []).append(row_index)
                    for cell in row.find_all(["td", "th"], recursive=False):
                        canonical = _canonical(text(cell), names)
                        if canonical not in uses:
                            continue
                        raw_names[canonical].add(text(cell))
                        discoveries[canonical].append(_ref(result, url, at, table_index, row_index))
                        for link in cell.find_all("a", href=True):
                            if _canonical(text(link), names) != canonical:
                                continue
                            detail = urljoin(url, str(link["href"]))
                            _validate_url(detail)
                            if (
                                canonical in links
                                and urldefrag(links[canonical])[0] != urldefrag(detail)[0]
                            ):
                                raise ValueError(f"{canonical}: 发现多个不同独立详情链接")
                            links[canonical] = detail
                for canonical, selected in groups.items():
                    overview_tables[canonical].append(
                        _read_table(
                            table,
                            result,
                            url,
                            at,
                            table_index,
                            selected_rows=selected,
                        )
                    )
        for canonical in sorted(uses):
            if not discoveries[canonical]:
                raise ValueError(f"{canonical}: 悬赏及装备总表均找不到来源")
            detail_url = links.get(canonical)
            detail_ref = None
            tables: list[DropItemTable] = []
            issues = []
            if detail_url is None:
                issues.append("no_detail_link")
            else:
                result, at = get(detail_url)
                content = _body(result, detail_url)
                detail_ref = _ref(result, detail_url, at)
                rarity = _page_rarity(content)
                tables = [
                    _read_table(table, result, detail_url, at, index, page_rarity=rarity)
                    for index, table in enumerate(content.find_all("table"))
                ]
                if not tables:
                    issues.append("detail_without_fact_tables")
            supplemental = inherited.get(canonical, []) if not tables else []
            if tables and any(
                item.kind != names.categories[canonical] for item in inherited.get(canonical, [])
            ):
                issues.append("legacy_category_difference")
            if supplemental and canonical in ("いれずみシール", "修理キット"):
                issues.append("source_effect_or_consumption_difference")
            if not tables and not overview_tables[canonical] and not supplemental:
                issues.append("attributes_not_collected")
            if any(table.alignment_issues for table in (*tables, *overview_tables[canonical])):
                issues.append("source_table_alignment_incomplete")
            records.append(
                WantedDropItemFact(
                    canonical_item_ja=canonical,
                    raw_names_ja=sorted(raw_names[canonical]),
                    detail_url=HttpUrl(detail_url) if detail_url is not None else None,
                    detail_ref=detail_ref,
                    discovery_refs=discoveries[canonical],
                    drop_uses=uses[canonical],
                    tables=tables,
                    overview_tables=overview_tables[canonical],
                    properties=_properties([*tables, *overview_tables[canonical]], names),
                    inherited_facts=supplemental,
                    existing_record_ids=existing_ids.get(canonical, []),
                    issues=issues,
                )
            )
            print(f"掉落物 {len(records):02d}/89：{names.names[canonical]}", flush=True)
    snapshot = WantedDropItemSnapshot(
        wanted_snapshot_hash=wanted_snapshot_hash(wanted),
        records=records,
        limitations=[
            "中文参考名与作用为资料整理，未与0.99汉化实机逐项核验。",
            "wanted_snapshot_hash是已验证WantedMonsterSnapshot的规范JSON内容哈希，不包含文件排版差异。",
            "同物品的多个掉落槽保留原始敌人、槽号和概率，不合并计算掉落率。",
            "星级数值、最小/初始/最大和改造费用按来源行及表分别保留，不抽取跨行组合数值。",
            "总表与独立详情来自不同数值条件；总表数据不覆盖独立页的逐星级数据。",
            "空字段和来源缺格不当成零；物品类别、中文作用摘要在同目录names.yaml。",
            "没有独立详情链接不代表没有属性；overview_tables保留匹配总表行，inherited_facts保留可复用旧记录及各自出处。",
            "已有记录按原条件单独保留；不同来源的消耗、效果等差异未经实机裁定。",
        ],
    )
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "records": len(records),
        "drop_slots": sum(len(item.drop_uses) for item in records),
        "detail_pages": sum(item.detail_url is not None for item in records),
        "detail_tables": sum(len(item.tables) for item in records),
        "overview_tables": sum(len(item.overview_tables) for item in records),
        "items_without_detail_tables": sum(not item.tables for item in records),
        "items_without_attributes": sum(
            "attributes_not_collected" in item.issues for item in records
        ),
        "source_pages": len(cached),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """提供独立采集入口，不修改共享CLI。"""
    parser = argparse.ArgumentParser(description="采集MM2R赏金首掉落物属性")
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(collect_wanted_drop_items(args.repo_root.resolve()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
