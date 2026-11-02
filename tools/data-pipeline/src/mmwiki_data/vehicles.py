"""采集可自有战车的底盘数值、配置与获取条件事实。"""

import argparse
import json
import re
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote, urldefrag, urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import Field, HttpUrl, model_validator

from mmwiki_data.fetcher import FetchResult, fetch
from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import SourceRef
from mmwiki_data.storage import write_json_atomic
from mmwiki_data.vehicle_tables import text

SOURCE_ID = "metalmaniax-mm2r"
TARGET_ID = "maniax-vehicles"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A"
_ROOT = Path("data/raw/mm2r/0.99/vehicles")
_EXPECTED_COUNTS = {
    "バギー": 19,
    "装甲車": 43,
    "野バス": 57,
    "ウルフ": 35,
    "ゲパルト": 26,
    "マンムート": 41,
    "エレファント": 1,
    "アビシニアン": 4,
    "ストラディバリ": 4,
    "ティーガー": 4,
    "レオパルト": 4,
    "ストレイドッグ": 10,
    "白バイ": 23,
    "ゼロ": 29,
    "スーパーカー": 35,
    "サイファイ": 20,
}
_PRESETS = frozenset(("アビシニアン", "ストラディバリ", "ティーガー", "レオパルト"))
_PATTERN_HEADERS = ("段階", "名称", "穴1", "穴2", "穴3", "穴4", "穴5", "重量(t)", "特性", "荷台")
_RENTAL_HEADERS = (
    "No.",
    "名称",
    "シャシー",
    "元シャシー",
    "守備",
    "重量(t)",
    "弾倉",
    "特性",
    "車載",
    "レンタル店",
    "価格(G)",
)
NonEmpty = Annotated[str, Field(min_length=1)]
SmallPositive = Annotated[int, Field(ge=1, le=128)]


class VehicleConditionSource(StrictModel):
    source_url: HttpUrl
    section_ja: NonEmpty
    summary_zh: NonEmpty
    evidence_ja: list[NonEmpty] = Field(min_length=1)


class VehicleNames(StrictModel):
    schema_version: Literal[1]
    reference_note: NonEmpty
    names: dict[str, str]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    acquisition: dict[str, str]
    notes: dict[str, str] = Field(default_factory=dict)
    condition_sources: dict[str, list[VehicleConditionSource]]

    @model_validator(mode="after")
    def validate_names(self) -> VehicleNames:
        """参考名和条件必须覆盖同一组基础车型。"""
        expected = set(_EXPECTED_COUNTS)
        if set(self.names) != expected or set(self.acquisition) != expected:
            raise ValueError("战车参考名称或获取摘要没有完整覆盖16种车型")
        if set(self.condition_sources) != expected:
            raise ValueError("战车获取条件来源没有完整覆盖16种车型")
        if (set(self.aliases) | set(self.notes)) - expected:
            raise ValueError("战车别名或说明引用了未知车型")
        if any(not value.strip() for value in (*self.names.values(), *self.acquisition.values())):
            raise ValueError("战车参考名或获取摘要为空")
        for sources in self.condition_sources.values():
            if not sources:
                raise ValueError("战车获取条件来源为空")
            for source in sources:
                _validate_url(str(source.source_url))
        return self


class VehicleStatRange(StrictModel):
    minimum_raw: NonEmpty
    initial_raw: NonEmpty
    maximum_raw: NonEmpty
    source_ref: SourceRef


class VehicleMountSupport(StrictModel):
    supported: bool
    value_ja: NonEmpty
    source_ref: SourceRef


class VehicleMountException(StrictModel):
    origin_ja: Literal["レンタル10号"] = "レンタル10号"
    double_engine: Literal[True] = True
    initial_only: Literal[True] = True
    evidence_ja: NonEmpty
    source_ref: SourceRef


class VehicleConfiguration(StrictModel):
    kind: Literal["pattern", "preset", "fixed"]
    stage: SmallPositive
    name_ja: NonEmpty
    holes_raw: list[NonEmpty] = Field(min_length=5, max_length=5)
    weight_raw: str = Field(pattern=r"^(?:[0-9]+(?:\.[0-9]+)?)?$")
    trait_raw: NonEmpty
    cargo_raw: str = Field(pattern=r"^[0-9]+$")
    fixed_armament_raw: str | None = None
    unresolved_fields: list[Literal["weight_raw"]] = Field(default_factory=list)
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_unknown_weight(self) -> VehicleConfiguration:
        """来源未填写的重量必须显式保留为待确认字段。"""
        if self.unresolved_fields != ([] if self.weight_raw else ["weight_raw"]):
            raise ValueError("战车配置的空重量与待确认字段不一致")
        return self


class VehicleTableRow(StrictModel):
    values: list[str] = Field(min_length=1, max_length=128)
    source_ref: SourceRef


class VehicleRawTable(StrictModel):
    context_ja: list[str]
    headers: list[str] = Field(min_length=1, max_length=128)
    rows: list[VehicleTableRow] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_width(self) -> VehicleRawTable:
        """原始数值表的展开行必须与表头等宽。"""
        if any(len(row.values) != len(self.headers) for row in self.rows):
            raise ValueError("战车原始表格行与表头列数不一致")
        return self


class VehicleAcquisition(StrictModel):
    text_ja: NonEmpty
    locator: NonEmpty
    source_ref: SourceRef


class VehicleConditionFact(StrictModel):
    summary_zh: NonEmpty
    evidence_ja: list[NonEmpty] = Field(min_length=1)
    locator: NonEmpty
    source_ref: SourceRef


class VehicleDesignTraits(StrictModel):
    choices_ja: list[NonEmpty] = Field(min_length=18, max_length=18)
    locator: NonEmpty
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_unique_choices(self) -> VehicleDesignTraits:
        """设计特性脚注的选项不可重复。"""
        if len(set(self.choices_ja)) != len(self.choices_ja):
            raise ValueError("巴特战车设计特性选项重复")
        return self


class VehicleFact(StrictModel):
    name_ja: NonEmpty
    defense: VehicleStatRange
    ammunition: VehicleStatRange
    double_engine: VehicleMountSupport
    double_c_unit: VehicleMountSupport
    mount_exceptions: list[VehicleMountException]
    configurations: list[VehicleConfiguration] = Field(min_length=1)
    initial_equipment: VehicleRawTable | None
    individual_modifications: list[VehicleRawTable] = Field(min_length=1)
    acquisition_ja: list[VehicleAcquisition] = Field(min_length=1)
    conditions_zh: list[VehicleConditionFact] = Field(min_length=1)
    design_traits: VehicleDesignTraits | None
    branch_source_ref: SourceRef | None
    source_issues: list[str] = Field(default_factory=list)


class VehiclePurchaseOption(StrictModel):
    rental_number: Annotated[int, Field(ge=1, le=19)]
    name_ja: NonEmpty
    configuration_ja: NonEmpty
    base_vehicle_ja: NonEmpty
    defense_raw: NonEmpty
    weight_raw: NonEmpty
    ammunition_raw: NonEmpty
    trait_raw: NonEmpty
    cargo_raw: NonEmpty
    shops_ja: NonEmpty
    price_raw: NonEmpty
    source_ref: SourceRef


class VehicleSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    source_id: Literal["metalmaniax-mm2r"] = "metalmaniax-mm2r"
    verification_status: Literal["source_only"] = "source_only"
    source_locator_note: str = (
        "table_index为#body内从0开始的表号；表格row_index为去除表头后的原始行号。"
        "非表格事实以source_url锚点和locator定位，SourceRef表格坐标不用于定位正文。"
    )
    records: list[VehicleFact] = Field(min_length=16, max_length=16)
    purchase_options: list[VehiclePurchaseOption] = Field(min_length=19, max_length=19)
    limitations: list[str]

    @model_validator(mode="after")
    def validate_records(self) -> VehicleSnapshot:
        """拒绝遗漏车型、配置数变化和被误排成升级顺序的设计预设。"""
        by_name = {record.name_ja: record for record in self.records}
        if len(by_name) != len(self.records) or set(by_name) != set(_EXPECTED_COUNTS):
            raise ValueError("战车快照车型重复或名单不完整")
        for name, record in by_name.items():
            configurations = record.configurations
            if len(configurations) != _EXPECTED_COUNTS[name]:
                raise ValueError(f"{name}: 配置数变化，需人工复核来源")
            if len({(item.stage, item.name_ja) for item in configurations}) != len(configurations):
                raise ValueError(f"{name}: 同阶段的配置名称重复")
            expected_kind = (
                "preset" if name in _PRESETS else ("fixed" if name == "エレファント" else "pattern")
            )
            if any(item.kind != expected_kind for item in configurations):
                raise ValueError(f"{name}: 配置类别与车型不符")
            if name in _PRESETS and any(item.stage != 1 for item in configurations):
                raise ValueError(f"{name}: 设计预设被错误解释为升级阶段")
            if (name in _PRESETS) != (record.design_traits is not None):
                raise ValueError(f"{name}: 设计特性脚注缺失或错配")
            if (name == "野バス") != bool(record.mount_exceptions):
                raise ValueError(f"{name}: 双引擎例外缺失或错配")
        if {item.rental_number for item in self.purchase_options} != set(range(1, 20)):
            raise ValueError("租赁购买选项编号不完整")
        if any(item.base_vehicle_ja not in by_name for item in self.purchase_options):
            raise ValueError("租赁购买选项引用未知车型")
        return self


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "metalmaniax.com":
        raise ValueError(f"战车来源地址不在来源主机内：{url}")
    if parsed.path != "/index.php" or not parsed.query.startswith("MM2R/"):
        raise ValueError(f"战车来源地址不在MM2R资料范围：{url}")


def _detail_url(name: str) -> str:
    return "https://metalmaniax.com/index.php?MM2R/DATA/" + quote("戦車/" + name)


def _heading_text(heading: Tag) -> str:
    return text(heading).removesuffix("†").strip()


def _section(content: Tag, label: str) -> tuple[Tag, list[Tag]]:
    matches = [
        tag for tag in content.find_all(re.compile(r"^h[2-6]$")) if _heading_text(tag) == label
    ]
    if len(matches) != 1:
        raise ValueError(f"战车来源不能唯一定位章节：{label}")
    heading = matches[0]
    level = int(heading.name[1])
    siblings: list[Tag] = []
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if re.fullmatch(r"h[2-6]", sibling.name) and int(sibling.name[1]) <= level:
            break
        siblings.append(sibling)
    return heading, siblings


def _section_url(url: str, heading: Tag) -> str:
    anchor = heading.find("a", class_="anchor_super")
    if isinstance(anchor, Tag) and anchor.get("id"):
        return urldefrag(url)[0] + "#" + str(anchor["id"])
    return urldefrag(url)[0] + "#" + str(heading["id"])


def _expanded_rows(table: Tag) -> list[list[str]]:
    """展开底盘表的合并格，限制尺寸并拒绝重叠与越界。"""
    rows = table.find_all("tr")
    if not 1 <= len(rows) <= 128:
        raise ValueError("战车表格行数超出1至128行限制")
    cells: dict[tuple[int, int], str] = {}
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (row_index, column) in cells:
                column += 1
            colspan = int(str(cell.get("colspan", "1")))
            rowspan = int(str(cell.get("rowspan", "1")))
            if not 1 <= colspan <= 128 or not 1 <= rowspan <= 128:
                raise ValueError("战车表格合并格跨度超出1至128限制")
            if column + colspan > 128 or row_index + rowspan > len(rows):
                raise ValueError("战车表格合并格越界")
            for dy in range(rowspan):
                for dx in range(colspan):
                    key = (row_index + dy, column + dx)
                    if key in cells:
                        raise ValueError("战车表格合并格重叠")
                    cells[key] = text(cell)
            column += colspan
    width = max(column + 1 for _, column in cells)
    if any((row, column) not in cells for row in range(len(rows)) for column in range(width)):
        raise ValueError("战车表格展开后存在未声明的空洞")
    return [[cells[(row, column)] for column in range(width)] for row in range(len(rows))]


def _body(result: FetchResult, url: str) -> Tag:
    content = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if content is None:
        raise ValueError(f"战车来源缺少#body正文：{url}")
    return content


def _ref(
    result: FetchResult, url: str, retrieved_at: datetime, table: int = 0, row: int = 0
) -> SourceRef:
    _validate_url(url)
    return SourceRef(
        source_id=SOURCE_ID,
        target_id=TARGET_ID,
        source_url=HttpUrl(url),
        retrieved_at=retrieved_at,
        content_hash=result.content_hash,
        table_index=table,
        row_index=row,
    )


def _raw_table(table: Tag, table_ref: SourceRef, context: list[str]) -> VehicleRawTable:
    rows = _expanded_rows(table)
    return VehicleRawTable(
        context_ja=context,
        headers=rows[0],
        rows=[
            VehicleTableRow(values=values, source_ref=table_ref.model_copy(update={"row_index": i}))
            for i, values in enumerate(rows[1:])
        ],
    )


def _table_context(table: Tag, content: Tag) -> list[str]:
    item = table.find_parent("li")
    if isinstance(item, Tag):
        pieces = [
            text(child) if isinstance(child, Tag) else str(child)
            for child in item.contents
            if not isinstance(child, Tag) or (child.name != "table" and child.find("table") is None)
        ]
        label = " ".join(" ".join(pieces).split())
        if label:
            return [label]
    owner = table
    while isinstance(owner.parent, Tag) and owner.parent is not content:
        owner = owner.parent
    context: list[str] = []
    for sibling in owner.previous_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.find("table") is not None or sibling.name == "table":
            break
        if sibling.name in ("h3", "h4", "h5", "p", "ul"):
            value = text(sibling)
            if value and value != "↑":
                context.append(value)
        if sibling.name in ("h2", "h3"):
            break
    return list(reversed(context))


def _acquisition(content: Tag, page_ref: SourceRef) -> list[VehicleAcquisition]:
    heading, elements = _section(content, "入手場所")
    source_ref = page_ref.model_copy(
        update={"source_url": HttpUrl(_section_url(str(page_ref.source_url), heading))}
    )
    facts: list[VehicleAcquisition] = []
    for element in elements:
        if element.name not in ("ul", "ol"):
            continue
        for item in element.find_all("li", recursive=False):
            pieces = [
                text(child) if isinstance(child, Tag) else str(child)
                for child in item.contents
                if not isinstance(child, Tag) or child.name not in ("ul", "ol")
            ]
            value = " ".join(" ".join(pieces).split())
            if value:
                facts.append(
                    VehicleAcquisition(
                        text_ja=value,
                        locator=f"#body 入手場所 li[{len(facts)}] (子リスト除外)",
                        source_ref=source_ref,
                    )
                )
    if not facts:
        raise ValueError("战车详情缺少获取地点事实")
    return facts


def _vehicle_detail(
    name: str,
    result: FetchResult,
    url: str,
    retrieved_at: datetime,
    conditions: list[VehicleConditionFact],
) -> VehicleFact:
    content = _body(result, url)
    tables = content.find_all("table")
    if not tables:
        raise ValueError(f"{name}: 缺少底盘数值表")
    basic = _expanded_rows(tables[0])
    if len(basic) != 5 or basic[0] != ["", "最小", "初期", "最大"]:
        raise ValueError(f"{name}: 底盘数值表格式变化")
    labels = [row[0] for row in basic[1:]]
    if labels != ["守備力", "弾倉", "ダブルエンジン", "ダブルCユニット"]:
        raise ValueError(f"{name}: 底盘数值字段变化")
    page_ref = _ref(result, url, retrieved_at)

    def stat(row_number: int) -> VehicleStatRange:
        values = basic[row_number]
        if any(not re.fullmatch(r"[0-9]+|-", value) for value in values[1:]):
            raise ValueError(f"{name}: 数值范围格式变化")
        return VehicleStatRange(
            minimum_raw=values[1],
            initial_raw=values[2],
            maximum_raw=values[3],
            source_ref=_ref(result, url, retrieved_at, row=row_number - 1),
        )

    def support(row_number: int) -> VehicleMountSupport:
        value = basic[row_number][1]
        if not (value.startswith("可") or value.startswith("不可")):
            raise ValueError(f"{name}: 双部件支持标记无法识别")
        return VehicleMountSupport(
            supported=value.startswith("可"),
            value_ja=value,
            source_ref=_ref(result, url, retrieved_at, row=row_number - 1),
        )

    configurations: list[VehicleConfiguration] = []
    modifications: list[VehicleRawTable] = []
    initial: VehicleRawTable | None = None
    for table_index, table in enumerate(tables[1:], start=1):
        header = [text(cell) for cell in table.find_all("tr")[0].find_all(["td", "th"])]
        table_ref = _ref(result, url, retrieved_at, table=table_index)
        if header[0] == "段階":
            expected_headers = list(_PATTERN_HEADERS)
            if name == "スーパーカー":
                expected_headers.insert(7, "固定武装")
            rows = _expanded_rows(table)
            if rows[0] != expected_headers or configurations:
                raise ValueError(f"{name}: 阶段配置表头变化或存在多张配置表")
            kind: Literal["pattern", "preset", "fixed"] = (
                "preset" if name in _PRESETS else "fixed" if name == "エレファント" else "pattern"
            )
            for row_index, row in enumerate(rows[1:]):
                values = dict(zip(rows[0], row, strict=True))
                configurations.append(
                    VehicleConfiguration(
                        kind=kind,
                        stage=int(values["段階"]),
                        name_ja=values["名称"],
                        holes_raw=[values[f"穴{number}"] for number in range(1, 6)],
                        weight_raw=values["重量(t)"],
                        trait_raw=values["特性"],
                        cargo_raw=values["荷台"],
                        fixed_armament_raw=values.get("固定武装"),
                        unresolved_fields=[] if values["重量(t)"] else ["weight_raw"],
                        source_ref=table_ref.model_copy(update={"row_index": row_index}),
                    )
                )
        elif header[:4] == ["部位", "大砲タイプ", "機銃タイプ", "S-Eタイプ"]:
            modifications.append(_raw_table(table, table_ref, _table_context(table, content)))
        elif header == ["部位", "装備", "性能", "重さ", "店売"]:
            if initial is not None:
                raise ValueError(f"{name}: 初期装备表重复")
            initial = _raw_table(table, table_ref, [])
        else:
            raise ValueError(f"{name}: 出现未知底盘表格：{header}")
    branch_headings = [
        heading
        for heading in content.find_all(["h3", "h4"])
        if _heading_text(heading) == "パターン改造分岐表"
    ]
    if len(branch_headings) > 1:
        raise ValueError(f"{name}: 改造分支章节重复")
    branch_ref = (
        _ref(result, _section_url(url, branch_headings[0]), retrieved_at)
        if branch_headings
        else None
    )
    double_engine = support(3)
    exceptions = []
    if name == "野バス":
        if "10号のみ初期仕様" not in double_engine.value_ja or double_engine.supported:
            raise ValueError("野巴士租赁10号双引擎例外发生变化")
        exceptions.append(
            VehicleMountException(
                evidence_ja=double_engine.value_ja,
                source_ref=double_engine.source_ref,
            )
        )
    design_traits = None
    if name in _PRESETS:
        note = BeautifulSoup(result.body, "html.parser").select_one("#note span.small")
        if note is None or not text(note).endswith("の中から一つ選択"):
            raise ValueError(f"{name}: 缺少设计特性选项脚注")
        design_traits = VehicleDesignTraits(
            choices_ja=text(note).removesuffix("の中から一つ選択").split(","),
            locator="#note span.small (#notefoot_1)",
            source_ref=_ref(result, url + "#notefoot_1", retrieved_at),
        )
    repeated_names = sorted(
        {
            item.name_ja
            for item in configurations
            if sum(other.name_ja == item.name_ja for other in configurations) > 1
        }
    )
    return VehicleFact(
        name_ja=name,
        defense=stat(1),
        ammunition=stat(2),
        double_engine=double_engine,
        double_c_unit=support(4),
        mount_exceptions=exceptions,
        configurations=configurations,
        initial_equipment=initial,
        individual_modifications=modifications,
        acquisition_ja=_acquisition(content, page_ref),
        conditions_zh=conditions,
        design_traits=design_traits,
        branch_source_ref=branch_ref,
        source_issues=[
            f"来源在不同阶段重复使用型号名{label}；保留原行，不合并配置。"
            for label in repeated_names
        ],
    )


def collect_vehicles(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """间隔至少一秒串行采集，校验16车型和355配置后原子写入快照。"""
    names = VehicleNames.model_validate(
        yaml.safe_load((repo_root / _ROOT / "names.yaml").read_text(encoding="utf-8"))
    )
    cached: dict[str, tuple[FetchResult, datetime]] = {}
    records: list[VehicleFact] = []
    purchase_options: list[VehiclePurchaseOption] = []
    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"},
    ) as client:

        def get(url: str) -> tuple[FetchResult, datetime]:
            _validate_url(url)
            page_url = urldefrag(url)[0]
            if page_url not in cached:
                if cached:
                    sleep(1.0)
                cached[page_url] = (fetch(client, TARGET_ID, page_url), datetime.now().astimezone())
            return cached[page_url]

        index, _index_time = get(INDEX_URL)
        index_content = _body(index, INDEX_URL)
        _heading, index_elements = _section(index_content, "シャシー一覧")
        discovered = {
            text(link): urljoin(INDEX_URL, str(link["href"]))
            for element in index_elements
            for link in element.find_all("a", href=True)
            if text(link) in _EXPECTED_COUNTS
        }
        rental_url = _detail_url("レンタルタンク")
        rental, rental_time = get(rental_url)
        rental_content = _body(rental, rental_url)
        rental_table = rental_content.find("table")
        if not isinstance(rental_table, Tag):
            raise ValueError("缺少租赁购买选项总表")
        rental_rows = _expanded_rows(rental_table)
        if rental_rows[0] != list(_RENTAL_HEADERS):
            raise ValueError("租赁购买选项总表字段变化")
        for row_index, row in enumerate(rental_rows[1:]):
            values = dict(zip(_RENTAL_HEADERS, row, strict=True))
            purchase_options.append(
                VehiclePurchaseOption(
                    rental_number=int(values["No."]),
                    name_ja=values["名称"],
                    configuration_ja=values["シャシー"],
                    base_vehicle_ja=values["元シャシー"],
                    defense_raw=values["守備"],
                    weight_raw=values["重量(t)"],
                    ammunition_raw=values["弾倉"],
                    trait_raw=values["特性"],
                    cargo_raw=values["車載"],
                    shops_ja=values["レンタル店"],
                    price_raw=values["価格(G)"],
                    source_ref=_ref(rental, rental_url, rental_time, row=row_index),
                )
            )
        for link in rental_table.find_all("a", href=True):
            if text(link) in ("スーパーカー", "サイファイ"):
                discovered[text(link)] = urljoin(rental_url, str(link["href"]))
        if set(discovered) != set(_EXPECTED_COUNTS):
            raise ValueError("战车索引与租赁总表未覆盖16种可自有车型")
        for name in _EXPECTED_COUNTS:
            url = discovered[name]
            _validate_url(url)
            if urldefrag(url)[0] != _detail_url(name):
                raise ValueError(f"{name}: 底盘详情链接与预期不符")
            result, retrieved_at = get(url)
            conditions = []
            for source in names.condition_sources[name]:
                condition_url = str(source.source_url)
                condition_result, condition_time = get(condition_url)
                content = _body(condition_result, condition_url)
                heading, elements = _section(content, source.section_ja)
                evidence = " ".join(text(element) for element in elements)
                if any(fragment not in evidence for fragment in source.evidence_ja):
                    raise ValueError(f"{name}: 获取条件原文发生变化：{source.section_ja}")
                conditions.append(
                    VehicleConditionFact(
                        summary_zh=source.summary_zh,
                        evidence_ja=source.evidence_ja,
                        locator=f"#body {heading.name}:{source.section_ja}",
                        source_ref=_ref(
                            condition_result, _section_url(condition_url, heading), condition_time
                        ),
                    )
                )
            records.append(_vehicle_detail(name, result, url, retrieved_at, conditions))
            print(f"战车 {len(records):02d}/16：{names.names[name]}", flush=True)
    snapshot = VehicleSnapshot(
        records=records,
        purchase_options=purchase_options,
        limitations=[
            "日文公开资料事实，中文名称和摘要仅为参考，未与0.99汉化游戏逐项核验。",
            "常规索引含12个编号，No.8有4种制造候选；No.11为租赁车，购买车型另列。",
            "355个配置包含巴特战车的16个设计预设和象式战车的1个初始配置。",
            "保留来源阶段，不根据表格行序推断升级连线；分支图仅保留原页章节链接。",
            "单孔改造保留来源条件标题与原始标记，括号、S等条件标记不推断成无条件许可。",
            "同时支持双引擎和双C装置只表示分别可选，不表示可同时装备两套双部件。",
            "制造所需废铁量、各个改造费用与未在数值表明示的字段不作推算。",
        ],
    )
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "records": len(records),
        "configurations": sum(len(r.configurations) for r in records),
        "individual_tables": sum(len(r.individual_modifications) for r in records),
        "purchase_options": len(purchase_options),
        "source_pages": len(cached),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """提供独立采集命令，不依赖共享CLI注册。"""
    parser = argparse.ArgumentParser(description="采集MM2R可自有战车事实")
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(collect_vehicles(args.repo_root.resolve()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
