from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import CamelModel
from app.schemas.equipment import EquipmentNames, EquipmentSource
from app.schemas.response import PaginationMeta

KnowledgeCategory = Literal["wanted-monsters"]
KnowledgeSort = Literal["name-asc", "bounty-desc"]


class ReferenceAttribute(CamelModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ReferenceTable(CamelModel):
    caption: str = Field(min_length=1)
    headers: list[str] = Field(min_length=1)
    rows: list[list[str]]
    source_refs: list[EquipmentSource] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_width(self) -> ReferenceTable:
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError(f"{self.caption}: 表格行宽与表头不一致")
        return self


class ReferenceSection(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1)
    paragraphs: list[str]
    tables: list[ReferenceTable]
    source_refs: list[EquipmentSource] = Field(min_length=1)


class WantedDrop(CamelModel):
    slot: int = Field(ge=1, le=3)
    item_ja: str = Field(min_length=1)
    name: str = Field(min_length=1)
    rate_raw: str = Field(pattern=r"^(?:100|[1-9]?[0-9])%$")
    summary: str
    equipment_id: str | None
    attributes: list[ReferenceAttribute]
    tables: list[ReferenceTable]
    source_refs: list[EquipmentSource] = Field(min_length=1)
    issues: list[str]


class WantedEnemy(CamelModel):
    name_ja: str = Field(min_length=1)
    encyclopedia_number: str = Field(pattern=r"^[0-9]{3}$")
    drops: list[WantedDrop] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_slots(self) -> WantedEnemy:
        if [drop.slot for drop in self.drops] != [1, 2, 3]:
            raise ValueError(f"{self.name_ja}: 掉落槽顺序不完整")
        return self


class KnowledgeSummary(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    game: Literal["mm2r"]
    target_version: Literal["0.99"]
    category: KnowledgeCategory
    names: EquipmentNames
    bounty: int | None = Field(default=None, ge=0)
    summary: str = Field(min_length=1)
    tags: list[str]
    verification_status: Literal["source_only", "compatible_candidate"]

    @model_validator(mode="after")
    def validate_summary(self) -> KnowledgeSummary:
        if self.category == "wanted-monsters" and self.bounty is None:
            raise ValueError(f"赏金首缺少赏金：{self.id}")
        if not any((self.names.zh_099, self.names.zh_09, self.names.zh_reference, self.names.ja)):
            raise ValueError(f"百科条目缺少显示名称：{self.id}")
        return self

    @property
    def name(self) -> str:
        return (
            self.names.zh_099 or self.names.zh_09 or self.names.zh_reference or self.names.ja or ""
        )


class KnowledgeRecord(KnowledgeSummary):
    attributes: list[ReferenceAttribute]
    sections: list[ReferenceSection]
    enemies: list[WantedEnemy]
    probability_note: str
    version_scope: list[str] = Field(min_length=1)
    source_refs: list[EquipmentSource] = Field(min_length=1)
    issues: list[str]

    @model_validator(mode="after")
    def validate_names(self) -> KnowledgeRecord:
        if len({section.id for section in self.sections}) != len(self.sections):
            raise ValueError(f"百科条目存在重复正文定位：{self.id}")
        return self


class KnowledgeDataset(CamelModel):
    schema_version: Literal[1]
    game: Literal["mm2r"]
    target_version: Literal["0.99"]
    category: KnowledgeCategory
    records: list[KnowledgeRecord]

    @model_validator(mode="after")
    def validate_records(self) -> KnowledgeDataset:
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("百科资料包含重复ID")
        if any(record.category != self.category for record in self.records):
            raise ValueError("百科条目与数据集分类不一致")
        return self


class KnowledgeListData(CamelModel):
    list: list[KnowledgeSummary]
    pagination: PaginationMeta
