"""百科正文、表格和掉落记录的可追溯契约。"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import (
    NameSet,
    SourceRef,
    sorted_unique_source_refs,
)

KnowledgeCategory = Literal["wanted-monsters", "vehicles"]


class ReferenceAttribute(StrictModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ReferenceTable(StrictModel):
    caption: str = Field(min_length=1)
    headers: list[str] = Field(min_length=1)
    rows: list[list[str]]
    source_refs: list[SourceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_width(self) -> ReferenceTable:
        """行宽须与表头一致，空值保留原样。"""
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError(f"{self.caption}: 表格行宽与表头不一致")
        return self


class ReferenceSection(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1)
    paragraphs: list[str] = Field(default_factory=list)
    tables: list[ReferenceTable] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)


class WantedDrop(StrictModel):
    slot: int = Field(ge=1, le=3)
    item_ja: str = Field(min_length=1)
    name: str = Field(min_length=1)
    rate_raw: str = Field(pattern=r"^(?:100|[1-9]?[0-9])%$")
    summary: str
    equipment_id: str | None = None
    attributes: list[ReferenceAttribute] = Field(default_factory=list)
    tables: list[ReferenceTable] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)


class WantedEnemy(StrictModel):
    name_ja: str = Field(min_length=1)
    encyclopedia_number: str = Field(pattern=r"^[0-9]{3}$")
    drops: list[WantedDrop] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_slots(self) -> WantedEnemy:
        if [drop.slot for drop in self.drops] != [1, 2, 3]:
            raise ValueError(f"{self.name_ja}: 掉落槽顺序不完整")
        return self


class VehicleSetup(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    kind: Literal["pattern", "preset", "fixed"]
    stage: int = Field(ge=1, le=128)
    name_ja: str = Field(min_length=1)
    name_reference: str = Field(min_length=1)
    holes_raw: list[str] = Field(min_length=5, max_length=5)
    weight_raw: str
    trait_ja: str = Field(min_length=1)
    trait_name: str = Field(min_length=1)
    cargo_raw: str
    fixed_armament_raw: str | None = None
    source_ref: SourceRef
    issues: list[str] = Field(default_factory=list)


class VehicleDetails(StrictModel):
    double_engine_supported: bool
    double_c_unit_supported: bool
    configurations: list[VehicleSetup] = Field(min_length=1, max_length=128)
    design_traits_ja: list[str] = Field(default_factory=list)
    trait_terms: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_setups(self) -> VehicleDetails:
        ids = [configuration.id for configuration in self.configurations]
        if len(ids) != len(set(ids)):
            raise ValueError("战车配置包含重复ID")
        return self


class KnowledgeRecord(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    category: KnowledgeCategory
    names: NameSet
    bounty: int | None = Field(default=None, ge=0)
    summary: str = Field(min_length=1)
    attributes: list[ReferenceAttribute]
    sections: list[ReferenceSection]
    enemies: list[WantedEnemy] = Field(default_factory=list)
    probability_note: str = ""
    vehicle: VehicleDetails | None = Field(default=None, exclude_if=lambda value: value is None)
    tags: list[str] = Field(default_factory=list)
    version_scope: list[str] = Field(min_length=1)
    verification_status: Literal["source_only", "compatible_candidate"]
    source_refs: list[SourceRef] = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> KnowledgeRecord:
        """所有正文及掉落出处都必须进入条目引用集合。"""
        if self.category == "wanted-monsters" and self.bounty is None:
            raise ValueError(f"{self.id}: 赏金首缺少赏金")
        if self.category == "vehicles" and self.vehicle is None:
            raise ValueError(f"{self.id}: 战车缺少配置信息")
        nested = [ref for section in self.sections for ref in section.source_refs]
        nested.extend(
            ref
            for section in self.sections
            for table in section.tables
            for ref in table.source_refs
        )
        if self.vehicle is not None:
            nested.extend(configuration.source_ref for configuration in self.vehicle.configurations)
        nested.extend(
            ref for enemy in self.enemies for drop in enemy.drops for ref in drop.source_refs
        )
        nested.extend(
            ref
            for enemy in self.enemies
            for drop in enemy.drops
            for table in drop.tables
            for ref in table.source_refs
        )
        self.source_refs = sorted_unique_source_refs([*self.source_refs, *nested])
        section_ids = [section.id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError(f"{self.id}: 正文存在重复定位")
        return self


class KnowledgeDataset(StrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    category: KnowledgeCategory
    records: list[KnowledgeRecord]

    @model_validator(mode="after")
    def validate_records(self) -> KnowledgeDataset:
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.category}: 包含重复条目ID")
        if any(record.category != self.category for record in self.records):
            raise ValueError(f"{self.category}: 条目分类不一致")
        return self


class KnowledgeRoute(StrictModel):
    category: KnowledgeCategory
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    legacy_slugs: list[Annotated[str, Field(pattern=r"^[a-z0-9-]+$")]] = Field(default_factory=list)


class KnowledgeRouteIndex(StrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    routes: list[KnowledgeRoute]

    @model_validator(mode="after")
    def validate_routes(self) -> KnowledgeRouteIndex:
        paths = [
            (route.category, slug)
            for route in self.routes
            for slug in [route.id, *route.legacy_slugs]
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("百科路径索引包含重复地址")
        return self


def build_knowledge_route_index(datasets: list[KnowledgeDataset]) -> KnowledgeRouteIndex:
    """生成不包含百科正文的路由索引，供请求进入页面前校验。"""
    legacy_slugs: dict[tuple[KnowledgeCategory, str], list[str]] = {
        ("wanted-monsters", "スナザメ"): ["sand-shark"],
        ("vehicles", "ウルフ"): ["red-wolf"],
    }
    routes = [
        KnowledgeRoute(
            category=record.category,
            id=record.id,
            legacy_slugs=legacy_slugs.get((record.category, record.names.ja or ""), []),
        )
        for dataset in datasets
        for record in dataset.records
    ]
    return KnowledgeRouteIndex(routes=sorted(routes, key=lambda route: (route.category, route.id)))
