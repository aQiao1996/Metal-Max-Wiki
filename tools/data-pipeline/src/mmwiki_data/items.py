"""保留既有道具身份与各来源条件，补充中文参考资料。"""

import argparse
import json
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import ConfigDict, Field, HttpUrl, model_validator

from mmwiki_data.fetcher import FetchResult, fetch
from mmwiki_data.models import CandidateSnapshot, StrictModel
from mmwiki_data.normalization_models import NormalizedBundle, NormalizedRecord, SourceRef
from mmwiki_data.storage import model_content_hash, write_json_atomic
from mmwiki_data.vehicle_tables import text
from mmwiki_data.wanted_drop_items import WantedDropItemFact, WantedDropItemSnapshot

_ROOT = Path("data/raw/mm2r/0.99/items")
_LEGACY = Path("data/interim/mm2r/0.99/items.json")
_DROPS = Path("data/raw/mm2r/0.99/wanted-drop-items/facts.json")
_SOURCE_ID = "metalmaniax-mm2r"
_TARGET_ID = "maniax-items"
_URLS = (
    "https://metalmaniax.com/index.php?MM2R/DATA/%E4%BA%BA%E9%96%93",
    "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A",
    "https://metalmaniax.com/index.php?MM2R/DATA/LOVE%E3%83%9E%E3%82%B7%E3%83%B3",
)
NonEmpty = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
ConsumptionStatus = Literal[
    "consumable",
    "reusable",
    "random_breakage",
    "limited_uses",
    "toggle",
    "conflicting",
    "unknown",
    "not_applicable",
]
StatementField = Literal[
    "usage",
    "target",
    "acquisition",
    "consumption",
    "restriction",
    "recipe",
    "field_effect",
    "battle_effect",
    "carryover",
    "notes",
]


class ItemStrictModel(StrictModel):
    """道具资料拒绝未知字段及隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class ItemReference(ItemStrictModel):
    name_zh_reference: NonEmpty
    category: NonEmpty
    summary_zh: NonEmpty
    target_zh: str | None
    match_names: list[NonEmpty] = Field(default_factory=list)
    related_record_ids: list[str] = Field(default_factory=list)
    notes_zh: list[NonEmpty] = Field(default_factory=list)


class ItemNames(ItemStrictModel):
    schema_version: Literal[1]
    reference_note: NonEmpty
    condition_note: NonEmpty
    categories: dict[str, str]
    names: dict[str, ItemReference]
    value_translations: dict[str, str]

    @model_validator(mode="after")
    def validate_coverage(self) -> ItemNames:
        """每条稳定身份都须具备中文参考名、分类与用途。"""
        if len(self.names) != 274:
            raise ValueError("道具中文参考资料必须恰好覆盖274条记录")
        for record_id, entry in self.names.items():
            if entry.category not in self.categories:
                raise ValueError(f"{record_id}: 道具类别没有中文标签")
            if set(entry.related_record_ids) - set(self.names):
                raise ValueError(f"{record_id}: 关联了未知道具身份")
        return self


class ItemCell(ItemStrictModel):
    text: str
    rowspan: Annotated[int, Field(ge=1, le=4096)] = 1
    colspan: Annotated[int, Field(ge=1, le=128)] = 1
    is_header: bool


def merged_item_headers(headers: list[str], values: list[str], cells: list[ItemCell]) -> list[str]:
    """只在本行原格完整覆盖所有列时定位跨列字段，避免猜测继承的行跨度。"""
    if not any(cell.colspan > 1 for cell in cells):
        return []
    if len(headers) != len(values) or sum(cell.colspan for cell in cells) != len(headers):
        raise ValueError("道具跨列原格没有完整覆盖原表列，无法可靠定位合并字段")
    merged: list[str] = []
    column = 0
    for cell in cells:
        end = column + cell.colspan
        if values[column:end] != [cell.text] * cell.colspan:
            raise ValueError("道具跨列原格与展开值不一致，无法可靠定位合并字段")
        if cell.colspan > 1:
            merged.extend(headers[column:end])
        column = end
    return merged


class ItemSourceRow(ItemStrictModel):
    section_raw: NonEmpty
    values_raw: dict[str, str]
    headers_raw: list[str]
    values_list_raw: list[str]
    merged_headers: list[str] = Field(default_factory=list)
    cells: list[ItemCell]
    condition_raw: NonEmpty
    locator_scheme: Literal["candidate_data_row", "html_physical_row", "cached_drop_table"]
    version_scope: list[NonEmpty] = Field(min_length=1)
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_width(self) -> ItemSourceRow:
        """保留重复表头和原始列，禁止字典化丢失事实。"""
        if len(self.headers_raw) != len(self.values_list_raw):
            raise ValueError("道具原始表头与展开值不等宽")
        if self.values_raw != dict(zip(self.headers_raw, self.values_list_raw, strict=True)):
            raise ValueError("道具事实字典与完整原始列不一致")
        if self.locator_scheme == "html_physical_row":
            if self.source_ref.source_id != _SOURCE_ID or self.source_ref.target_id != _TARGET_ID:
                raise ValueError("新采道具事实引用了错误来源")
            _validate_url(str(self.source_ref.source_url))
            expected = merged_item_headers(self.headers_raw, self.values_list_raw, self.cells)
            if self.merged_headers != expected:
                raise ValueError("新采道具跨列字段与原始单元格跨度不一致")
        return self


class ItemStatement(ItemStrictModel):
    field: StatementField
    label_raw: NonEmpty = "原表字段"
    value_raw: NonEmpty
    value_zh_reference: str | None
    condition_raw: NonEmpty
    version_scope: list[NonEmpty] = Field(min_length=1)
    source_refs: list[SourceRef] = Field(min_length=1)


class LinkedDropItem(ItemStrictModel):
    snapshot_file: Literal["data/raw/mm2r/0.99/wanted-drop-items/facts.json"] = (
        "data/raw/mm2r/0.99/wanted-drop-items/facts.json"
    )
    snapshot_hash: Sha256
    canonical_item_ja: NonEmpty


class ItemFact(ItemStrictModel):
    id: NonEmpty
    kind: NonEmpty
    name_ja: str | None
    name_zh_reference: NonEmpty
    aliases: list[str]
    category: NonEmpty
    category_label_zh: NonEmpty
    summary_zh: NonEmpty
    target_zh: str | None
    consumption_status: ConsumptionStatus
    statements: list[ItemStatement]
    source_rows: list[ItemSourceRow] = Field(min_length=1)
    inherited_record: NormalizedRecord
    linked_drop_item: LinkedDropItem | None
    related_record_ids: list[str]
    notes_zh: list[str]
    missing_fields: list[str]
    issues: list[str]

    @model_validator(mode="after")
    def validate_identity(self) -> ItemFact:
        """保留旧记录全部事实，不把参考分类写回旧身份。"""
        if self.id != self.inherited_record.id or self.kind != self.inherited_record.kind:
            raise ValueError("道具事实与继承记录的稳定身份不一致")
        if self.name_ja != self.inherited_record.names.ja:
            raise ValueError("道具原始日文身份被更改")
        if self.consumption_status != _consumption(self.statements, self.kind):
            raise ValueError("道具消耗性摘要与各来源事实不一致")
        inherited_refs = {
            row.source_ref.model_dump_json()
            for row in self.source_rows
            if row.locator_scheme == "candidate_data_row"
        }
        if inherited_refs != {ref.model_dump_json() for ref in self.inherited_record.source_refs}:
            raise ValueError("道具事实没有逐条保留全部原来源引用")
        if self.consumption_status == "unknown" and "consumption" not in self.missing_fields:
            raise ValueError("未明确消耗性却没有标注缺失")
        for field in ("acquisition", "restriction"):
            known = {field, "carryover"} if field == "restriction" else {field}
            if not any(statement.field in known for statement in self.statements):
                if field not in self.missing_fields:
                    raise ValueError(f"{self.id}: 缺失字段没有明确标记：{field}")
        return self


class ItemSnapshot(ItemStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    verification_status: Literal["source_only"] = "source_only"
    legacy_bundle_hash: Sha256
    drop_snapshot_hash: Sha256
    reference_note: NonEmpty
    condition_note: NonEmpty
    source_locator_note: NonEmpty = (
        "candidate_data_row沿用旧候选表的从0开始数据行号（不含表头）；"
        "html_physical_row为#body内从0开始的表号与含表头物理行号；"
        "cached_drop_table沿用已采掉落物快照的逐表定位。网页content_hash是HTTP内容哈希；"
        "bundle与snapshot哈希是已验证模型的规范JSON哈希，不受文件排版影响。"
    )
    records: list[ItemFact] = Field(min_length=274, max_length=274)
    limitations: list[str]

    @model_validator(mode="after")
    def validate_complete(self) -> ItemSnapshot:
        """拒绝丢失身份或混入本机已核验结论。"""
        if len({record.id for record in self.records}) != 274:
            raise ValueError("道具快照包含重复或缺失身份")
        inherited = NormalizedBundle(
            domain="items",
            source_hashes=sorted(
                {
                    ref.content_hash
                    for record in self.records
                    for ref in record.inherited_record.source_refs
                }
            ),
            records=[record.inherited_record for record in self.records],
        )
        if model_content_hash(inherited) != self.legacy_bundle_hash:
            raise ValueError("道具快照没有完整保留原记录事实")
        for record in self.records:
            if record.linked_drop_item is not None:
                if record.linked_drop_item.snapshot_hash != self.drop_snapshot_hash:
                    raise ValueError("掉落物关联哈希与快照依赖不一致")
        return self


def load_item_names(repo_root: Path) -> ItemNames:
    """校验274条中文参考名及用途，不视为0.99实机译名。"""
    return ItemNames.model_validate(
        yaml.safe_load((repo_root / _ROOT / "names.yaml").read_text(encoding="utf-8"))
    )


def load_items(repo_root: Path) -> ItemSnapshot | None:
    """离线读取并严格校验道具事实和关联的既有掉落物快照。"""
    path = repo_root / _ROOT / "facts.json"
    if not path.exists():
        return None
    snapshot = ItemSnapshot.model_validate_json(path.read_bytes())
    drops = WantedDropItemSnapshot.model_validate_json((repo_root / _DROPS).read_bytes())
    if snapshot.drop_snapshot_hash != model_content_hash(drops):
        raise ValueError("道具引用的掉落物快照已变化，须重新采集道具快照")
    known = {record.canonical_item_ja: record for record in drops.records}
    for record in snapshot.records:
        if record.linked_drop_item and record.linked_drop_item.canonical_item_ja not in known:
            raise ValueError(f"{record.id}: 关联的掉落物不存在")
        if record.linked_drop_item:
            linked = known[record.linked_drop_item.canonical_item_ja]
            if record.id not in linked.existing_record_ids:
                raise ValueError(f"{record.id}: 关联的掉落物不属于该稳定身份")
            expected = _drop_rows(linked)
            actual = [
                row for row in record.source_rows if row.locator_scheme == "cached_drop_table"
            ]
            if {model_content_hash(row) for row in actual} != {
                model_content_hash(row) for row in expected
            }:
                raise ValueError(f"{record.id}: 关联的掉落物事实行不完整或发生变化")
    return snapshot


def _canonical(value: str) -> str:
    return unicodedata.normalize("NFKC", value).replace(" ", "").removesuffix("?")


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "metalmaniax.com"
        or parsed.path != "/index.php"
        or not unquote(parsed.query).startswith("MM2R/DATA/")
    ):
        raise ValueError(f"道具来源地址不在METAL MM2R数据范围：{url}")


def _expand(table: Tag) -> list[list[str]]:
    rows = table.find_all("tr")
    if not 1 <= len(rows) <= 4096:
        raise ValueError("道具来源表格超出行数限制")
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
                raise ValueError("道具来源合并格跨度越界")
            if row_index + rowspan > len(rows) or column + colspan > 128:
                raise ValueError("道具来源合并格超出表格边界")
            for y in range(rowspan):
                for x in range(colspan):
                    key = row_index + y, column + x
                    if key in cells:
                        raise ValueError("道具来源合并格重叠")
                    cells[key] = text(cell)
            column += colspan
    width = max((column + 1 for _, column in cells), default=0)
    if not width or any((r, c) not in cells for r in range(len(rows)) for c in range(width)):
        raise ValueError("道具来源表格缺格，无法可靠对应字段")
    return [[cells[r, c] for c in range(width)] for r in range(len(rows))]


def _new_rows(result: FetchResult, url: str, at: datetime) -> dict[str, list[ItemSourceRow]]:
    _validate_url(url)
    body = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if body is None:
        raise ValueError(f"道具来源缺少#body：{url}")
    output: dict[str, list[ItemSourceRow]] = {}
    for table_index, table in enumerate(body.find_all("table")):
        physical = table.find_all("tr")
        if not physical:
            continue
        heading = table.find_previous(re.compile(r"^h[2-6]$"))
        caption = (
            text(heading).removesuffix("†").strip() if isinstance(heading, Tag) else "基本情報"
        )
        if not any(
            term in caption for term in ("道具一覧", "特殊砲弾一覧", "チップ取得先", "組み合わせ表")
        ):
            continue
        expanded = _expand(table)
        header = expanded[0]
        if len(header) != len(set(header)):
            raise ValueError(f"{url}: {caption}表头包含重复字段")
        recipe = header[:4] == ["L", "O", "V", "E"]
        for row_index, values in enumerate(expanded[1:], start=1):
            key = "-".join(values[:4]) if recipe else _canonical(values[0])
            condition = (
                "日版MM2R；L/O/V/E芯片顺序为" + key
                if recipe
                else "日版MM2R总表原行；未明确的星级、周目或难度不外推"
            )
            rarity = dict(zip(header, values, strict=True)).get("レア")
            if rarity:
                condition += "；原表星级标记：" + rarity
            source_ref = SourceRef(
                source_id=_SOURCE_ID,
                target_id=_TARGET_ID,
                source_url=HttpUrl(url),
                retrieved_at=at,
                content_hash=result.content_hash,
                table_index=table_index,
                row_index=row_index,
            )
            cells = [
                ItemCell(
                    text=text(cell),
                    rowspan=int(str(cell.get("rowspan", "1"))),
                    colspan=int(str(cell.get("colspan", "1"))),
                    is_header=cell.name == "th",
                )
                for cell in physical[row_index].find_all(["td", "th"], recursive=False)
            ]
            output.setdefault(key, []).append(
                ItemSourceRow(
                    section_raw=caption,
                    values_raw=dict(zip(header, values, strict=True)),
                    headers_raw=header,
                    values_list_raw=values,
                    merged_headers=merged_item_headers(header, values, cells),
                    cells=cells,
                    condition_raw=condition,
                    locator_scheme="html_physical_row",
                    version_scope=["mm2r-jp"],
                    source_ref=source_ref,
                )
            )
    if not output:
        raise ValueError(f"{url}: 未发现获准的道具事实表")
    return output


def _legacy_rows(repo_root: Path, record: NormalizedRecord) -> list[ItemSourceRow]:
    rows: list[ItemSourceRow] = []
    for ref in record.source_refs:
        path = repo_root / "data/raw/mm2r/0.99/candidates" / f"{ref.target_id}.json"
        candidate = CandidateSnapshot.model_validate_json(path.read_bytes())
        if candidate.content_hash != ref.content_hash:
            raise ValueError(f"{record.id}: 继承来源与原候选快照哈希不一致")
        if (
            candidate.source_id != ref.source_id
            or candidate.target_id != ref.target_id
            or candidate.source_url != ref.source_url
            or candidate.retrieved_at != ref.retrieved_at
        ):
            raise ValueError(f"{record.id}: 继承来源定位与原候选快照不一致")
        table = candidate.tables[ref.table_index]
        values = table.rows[ref.row_index]
        rarity = values.get("星数") or values.get("★")
        condition = "旧候选原行；所属版本和合并格分别保留，不能与新来源合并覆盖"
        if rarity:
            condition += "；原表星级标记：" + rarity
        merged_headers = []
        for span in record.source_spans:
            if (
                span.source_id == ref.source_id
                and span.target_id == ref.target_id
                and span.table_index == ref.table_index
                and span.row_index == ref.row_index
            ):
                start, end = (
                    table.headers.index(span.start_header),
                    table.headers.index(span.end_header),
                )
                merged_headers.extend(table.headers[start : end + 1])
        rows.append(
            ItemSourceRow(
                section_raw=table.section,
                values_raw=values,
                headers_raw=list(values),
                values_list_raw=list(values.values()),
                merged_headers=merged_headers,
                cells=[],
                condition_raw=condition,
                locator_scheme="candidate_data_row",
                version_scope=(
                    ["mm2r-jp"]
                    if candidate.source_id == "dqff-mm2r"
                    else ["mm2r-jp", "zh-patch-0.9-family"]
                ),
                source_ref=ref,
            )
        )
    return rows


def _drop_rows(record: WantedDropItemFact) -> list[ItemSourceRow]:
    rows: list[ItemSourceRow] = []
    for table in (*record.tables, *record.overview_tables):
        for row in table.rows:
            rows.append(
                ItemSourceRow(
                    section_raw=table.caption_ja,
                    values_raw=dict(zip(table.headers, row.values, strict=True)),
                    headers_raw=table.headers,
                    values_list_raw=row.values,
                    cells=[ItemCell.model_validate(cell.model_dump()) for cell in row.cells],
                    condition_raw=row.condition_raw,
                    locator_scheme="cached_drop_table",
                    version_scope=["mm2r-jp"],
                    source_ref=row.source_ref,
                )
            )
    return rows


_FIELDS: dict[str, StatementField] = {
    "説明": "usage",
    "効果": "usage",
    "効果範囲": "target",
    "対象": "target",
    "效果": "usage",
    "对象": "target",
    "消耗": "consumption",
    "消費": "consumption",
    "消費タイプ": "consumption",
    "消费": "consumption",
    "場所": "acquisition",
    "场所": "acquisition",
    "フィールド使用": "field_effect",
    "戦闘中使用": "battle_effect",
    "地图上使用效果": "field_effect",
    "战斗中使用效果": "battle_effect",
    "フィールド": "field_effect",
    "戦闘中": "battle_effect",
    "周回持越し": "carryover",
    "備考": "notes",
    "入手場所・備考": "acquisition",
    "イベント等": "restriction",
    "要スパルク": "restriction",
}


def _statements(rows: list[ItemSourceRow], names: ItemNames) -> list[ItemStatement]:
    statements: list[ItemStatement] = []
    seen: set[tuple[str, str, str, int, int]] = set()
    for row in rows:
        for header, value in row.values_raw.items():
            if not value or value in ("-", "なし", "無し") or header not in _FIELDS:
                continue
            field = _FIELDS[header]
            if header in row.merged_headers:
                field = "usage"
            if field == "notes" and re.search(
                r"[（(](?:買|宝|落|賞)|入手|購入|買う|報酬|掘り出し|宝箱|木箱|道具屋|薬局|"
                r"自販機|クエスト|交換|金属探知機|撃破数|[购商][买店]",
                value,
            ):
                field = "acquisition"
            if field == "notes" and re.search(r"専用|使えない|使用不可|不[可能]", value):
                field = "restriction"
            key = (
                field,
                value,
                row.source_ref.content_hash,
                row.source_ref.table_index,
                row.source_ref.row_index,
            )
            if key in seen:
                continue
            seen.add(key)
            condition = row.condition_raw
            if header in row.merged_headers:
                condition += "；此值跨地图与战斗两列，不能单独归给其中一个场景"
            statements.append(
                ItemStatement(
                    field=field,
                    label_raw=header,
                    value_raw=value,
                    value_zh_reference=names.value_translations.get(value),
                    condition_raw=condition,
                    version_scope=row.version_scope,
                    source_refs=[row.source_ref],
                )
            )
            if field not in ("restriction", "consumption") and re.search(
                r"専用|使えない|使用不可|入手不可|1データにつき|のみ|できない", value
            ):
                statements.append(
                    ItemStatement(
                        field="restriction",
                        label_raw=header,
                        value_raw=value,
                        value_zh_reference=names.value_translations.get(value),
                        condition_raw=condition,
                        version_scope=row.version_scope,
                        source_refs=[row.source_ref],
                    )
                )
        materials = [row.values_raw.get(f"材料{i}", "") for i in range(1, 4)]
        if all(materials) and set(materials) != {"-"}:
            value = " + ".join(materials)
            statements.append(
                ItemStatement(
                    field="recipe",
                    label_raw="材料1 + 材料2 + 材料3",
                    value_raw=value,
                    value_zh_reference=names.value_translations.get(value),
                    condition_raw=row.condition_raw,
                    version_scope=row.version_scope,
                    source_refs=[row.source_ref],
                )
            )
    return statements


def _consumption(statements: list[ItemStatement], kind: str) -> ConsumptionStatus:
    if kind in ("love_machine_recipe", "ic_chip_location"):
        return "not_applicable"
    statuses: set[ConsumptionStatus] = set()
    for statement in statements:
        value = statement.value_raw
        if statement.field == "consumption":
            if value in ("1回", "消費", "消费", "消耗品"):
                statuses.add("consumable")
            elif value in ("∞", "無限"):
                statuses.add("reusable")
            elif value == "ON/OFF":
                statuses.add("toggle")
            elif value == "数回":
                statuses.add("limited_uses")
        if statement.field == "usage":
            if "何度でも使える" in value:
                statuses.add("reusable")
            if "ランダムで壊れる" in value:
                statuses.add("random_breakage")
    if statuses == {"toggle", "reusable"}:
        return "toggle"
    if len(statuses) > 1:
        return "conflicting"
    return next(iter(statuses), "unknown")


def _record_keys(record: NormalizedRecord, entry: ItemReference) -> set[str]:
    if record.kind == "love_machine_recipe":
        return {"-".join(str(record.attributes[key]) for key in ("l", "o", "v", "e"))}
    raw = [*entry.match_names, *record.names.aliases]
    if record.names.ja:
        raw.append(record.names.ja)
    return {_canonical(value) for value in raw}


def _row_matches(record: NormalizedRecord, row: ItemSourceRow) -> bool:
    if row.values_raw.get("名称") == "悪のブロマイド":
        expected = str(record.attributes.get("description_raw", "")).replace("・", "")
        return row.values_raw.get("効果", "").replace("・", "") == expected
    return True


def collect_items(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行提取三页道具事实表，全部成功并验证后才原子替换274条快照。"""
    names = load_item_names(repo_root)
    legacy = NormalizedBundle.model_validate_json((repo_root / _LEGACY).read_bytes())
    if set(names.names) != {record.id for record in legacy.records}:
        raise ValueError("中文道具参考资料没有完整匹配274条既有稳定身份")
    drops = WantedDropItemSnapshot.model_validate_json((repo_root / _DROPS).read_bytes())
    new_rows: dict[str, list[ItemSourceRow]] = {}
    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://metalmax.wiki)"},
    ) as client:
        for i, url in enumerate(_URLS):
            if i:
                sleep(1.0)
            result = fetch(client, _TARGET_ID, url)
            page_rows = _new_rows(result, url, datetime.now().astimezone())
            required = (
                {"回復カプセル", "LOVEマシン", "ロックハッカー", "座敷牢のカギ", "修理キット"}
                if i == 0
                else {"りゅう弾", "まひガス弾", "タイルパック100", "宇宙パーツ+10"}
                if i == 1
                else {
                    *(
                        "-".join(str(part) for part in combo)
                        for combo in product((1, 2, 3), repeat=4)
                    ),
                    *(f"{letter}-{number}" for letter in "LOVE" for number in (1, 2, 3)),
                }
            )
            if required - set(page_rows):
                raise ValueError(f"{url}: 事实表缺少必要记录：{sorted(required - set(page_rows))}")
            for key, rows in page_rows.items():
                new_rows.setdefault(key, []).extend(rows)
    snapshot = _build_snapshot(repo_root, names, legacy, drops, new_rows)
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    records = snapshot.records
    return {
        "records": len(records),
        "source_rows": sum(len(record.source_rows) for record in records),
        "statements": sum(len(record.statements) for record in records),
        "linked_drop_items": sum(record.linked_drop_item is not None for record in records),
        "acquisition_known": sum("acquisition" not in record.missing_fields for record in records),
        "consumption_known": sum(
            record.consumption_status not in ("unknown", "not_applicable") for record in records
        ),
    }


def _build_snapshot(
    repo_root: Path,
    names: ItemNames,
    legacy: NormalizedBundle,
    drops: WantedDropItemSnapshot,
    new_rows: dict[str, list[ItemSourceRow]],
) -> ItemSnapshot:
    if set(names.names) != {record.id for record in legacy.records}:
        raise ValueError("中文道具参考资料没有完整匹配274条既有稳定身份")
    drop_hash = model_content_hash(drops)
    drop_by_id = {
        record_id: drop
        for drop in drops.records
        for record_id in drop.existing_record_ids
        if record_id in names.names
    }
    records: list[ItemFact] = []
    for record in legacy.records:
        entry = names.names[record.id]
        linked = drop_by_id.get(record.id)
        rows = _legacy_rows(repo_root, record)
        if linked is not None:
            rows.extend(_drop_rows(linked))
        else:
            for key in sorted(_record_keys(record, entry)):
                rows.extend(row for row in new_rows.get(key, []) if _row_matches(record, row))
        if record.kind == "human_item" and record.names.ja and "-ICチップ" in record.names.ja:
            chip_key = record.names.ja.split("-ICチップ")[0]
            rows.extend(new_rows.get(chip_key[0] + "-" + chip_key[1:], []))
        statements = _statements(rows, names)
        if linked is not None:
            for use in linked.drop_uses:
                statements.append(
                    ItemStatement(
                        field="acquisition",
                        label_raw="赏金首掉落表",
                        value_raw=f"{use.enemy_name_ja}：掉落槽{use.slot}，原表概率{use.rate_raw}",
                        value_zh_reference=names.value_translations.get(
                            f"{use.enemy_name_ja}：掉落槽{use.slot}，原表概率{use.rate_raw}"
                        ),
                        condition_raw="原掉落表单槽物品概率；不推算星级、难度、复合概率或掉落机制",
                        version_scope=["mm2r-jp"],
                        source_refs=[use.source_ref],
                    )
                )
        status = _consumption(statements, record.kind)
        missing = [
            field
            for field in ("acquisition", "restriction")
            if not any(
                statement.field in ({field, "carryover"} if field == "restriction" else {field})
                for statement in statements
            )
        ]
        if status == "unknown":
            missing.append("consumption")
        if not any(
            re.search(r"売[却れ].*[不可な]|捨[てら].*[不可な]", statement.value_raw)
            for statement in statements
        ):
            missing.append("sell_discard_restrictions")
        if entry.target_zh is None:
            missing.append("target")
        issues = [*record.issues]
        notes = [*entry.notes_zh]
        if not any(row.locator_scheme != "candidate_data_row" for row in rows):
            issues.append("no_additional_fact_match")
            notes.append("本条暂只有既有攻略事实，尚缺少新增来源交叉核对。")
        if status == "conflicting":
            issues.append("source_consumption_conflict")
        if any(row.merged_headers for row in rows):
            issues.append("source_merged_cell")
        records.append(
            ItemFact(
                id=record.id,
                kind=record.kind,
                name_ja=record.names.ja,
                name_zh_reference=entry.name_zh_reference,
                aliases=sorted(set([*record.names.aliases, *entry.match_names])),
                category=entry.category,
                category_label_zh=names.categories[entry.category],
                summary_zh=entry.summary_zh,
                target_zh=entry.target_zh,
                consumption_status=status,
                statements=statements,
                source_rows=rows,
                inherited_record=record,
                linked_drop_item=(
                    LinkedDropItem(
                        snapshot_hash=drop_hash,
                        canonical_item_ja=linked.canonical_item_ja,
                    )
                    if linked is not None
                    else None
                ),
                related_record_ids=entry.related_record_ids,
                notes_zh=notes,
                missing_fields=missing,
                issues=sorted(set(issues)),
            )
        )
    snapshot = ItemSnapshot(
        legacy_bundle_hash=model_content_hash(legacy),
        drop_snapshot_hash=drop_hash,
        reference_note=names.reference_note,
        condition_note=names.condition_note,
        records=records,
        limitations=[
            "全部中文名称和摘要是参考翻译；原0.9名称独立保留于inherited_record，未确认0.99实机译名。",
            "各来源版本、星级、合并格及取值条件分开保存；存在冲突时不选择一个值覆盖其他来源。",
            "source_rows仅保存与274条既有记录对应的事实表行，不保存整页正文或攻略评论。",
            "LOVE配方与IC芯片位置是原目录中的独立记录，consumption_status为not_applicable，不推断芯片消失。",
            "未明确获取、消耗或关键物品限制时由missing_fields标记；售价带星号不等于可购买。",
            "linked_drop_item保留已采89种赏金掉落物中的重叠事实依赖，详情、星别数值和概率仍在原快照。",
            "保留旧目录疑似重复、旧版或不同写法记录，不自动合并稳定ID；related_record_ids仅提示关联。",
        ],
    )
    if any(
        record.inherited_record != original
        for record, original in zip(snapshot.records, legacy.records, strict=True)
    ):
        raise ValueError("道具采集改变了原记录事实")
    return snapshot


def main(argv: Sequence[str] | None = None) -> int:
    """以独立模块采集或离线校验道具，不修改共享CLI。"""
    parser = argparse.ArgumentParser(description="采集和校验MM2R道具事实")
    parser.add_argument("command", choices=("collect", "validate"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_items(args.repo_root)
    else:
        snapshot = load_items(args.repo_root)
        if snapshot is None:
            raise FileNotFoundError(args.repo_root / _ROOT / "facts.json")
        result = {"records": len(snapshot.records)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
