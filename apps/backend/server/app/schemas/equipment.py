from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from app.schemas.base import CamelModel
from app.schemas.response import PaginationMeta

EquipmentType = Literal[
    "human-weapon", "main-cannon", "sub-gun", "special-equipment", "c-unit", "engine"
]
EquipmentSort = Literal["name-asc", "attack-desc", "capacity-desc", "price-asc", "weight-asc"]
EquipmentProfession = Literal["hunter", "mechanic", "soldier", "nurse", "artist", "wrestler"]


class EquipmentNames(CamelModel):
    ja: str | None
    zh_09: str | None
    zh_099: str | None
    zh_reference: str | None = None
    aliases: list[str]


class EquipmentSource(CamelModel):
    source_id: str
    target_id: str
    source_url: HttpUrl
    retrieved_at: AwareDatetime
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    table_index: int = Field(ge=0)
    row_index: int = Field(ge=0)


class EquipmentSourceSpan(CamelModel):
    source_id: str
    target_id: str
    table_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    start_header: str
    end_header: str
    value: str


class EquipmentModification(CamelModel):
    stars: int = Field(ge=0, le=3)
    attack_min_raw: str
    attack_raw: str
    attack_max_raw: str
    defense_min_raw: str
    defense_raw: str
    defense_max_raw: str
    magazine_min_raw: str
    magazine_raw: str
    magazine_max_raw: str
    weight_min_raw: str
    weight_raw: str
    weight_max_raw: str


class ControlModification(CamelModel):
    stars: int = Field(ge=0, le=3)
    accuracy_min_raw: str
    accuracy_raw: str
    accuracy_max_raw: str
    evasion_min_raw: str
    evasion_raw: str
    evasion_max_raw: str
    defense_min_raw: str
    defense_raw: str
    defense_max_raw: str
    weight_min_raw: str
    weight_raw: str
    weight_max_raw: str


class EngineModification(CamelModel):
    stars: int = Field(ge=0, le=3)
    capacity_raw: str
    defense_min_raw: str
    defense_raw: str
    defense_max_raw: str
    weight_min_raw: str
    weight_raw: str
    weight_max_raw: str


class EquipmentRecord(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    game: Literal["mm2r"]
    target_version: Literal["0.99"]
    domain: Literal["equipment"]
    kind: Literal["human_weapon", "main_cannon", "special_equipment", "c_unit", "engine"]
    names: EquipmentNames
    attributes: dict[str, str | int | float]
    modifications: list[EquipmentModification] = Field(default_factory=list)
    control_modifications: list[ControlModification] = Field(default_factory=list)
    engine_modifications: list[EngineModification] = Field(default_factory=list)
    version_scope: list[str]
    verification_status: Literal["source_only", "compatible_candidate"]
    source_refs: list[EquipmentSource] = Field(min_length=1)
    source_spans: list[EquipmentSourceSpan]
    issues: list[str]
    asset_refs: list[str]

    @model_validator(mode="after")
    def validate_display_name(self) -> EquipmentRecord:
        if not any((self.names.zh_099, self.names.zh_09, self.names.zh_reference, self.names.ja)):
            raise ValueError(f"装备缺少可显示名称：{self.id}")
        return self

    @property
    def name(self) -> str:
        return (
            self.names.zh_099 or self.names.zh_09 or self.names.zh_reference or self.names.ja or ""
        )

    @property
    def equipment_type(self) -> EquipmentType:
        types: dict[str, EquipmentType] = {
            "human_weapon": "human-weapon",
            "main_cannon": "main-cannon",
            "special_equipment": "special-equipment",
            "c_unit": "c-unit",
            "engine": "engine",
        }
        return types[self.kind]


class EquipmentDataset(CamelModel):
    schema_version: Literal[1]
    game: Literal["mm2r"]
    target_version: Literal["0.99"]
    domain: Literal["equipment"]
    source_hashes: list[str]
    records: list[EquipmentRecord]

    @model_validator(mode="after")
    def validate_records(self) -> EquipmentDataset:
        ids = [record.id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("装备资料包含重复 ID")
        hashes = {source.content_hash for record in self.records for source in record.source_refs}
        if set(self.source_hashes) != hashes:
            raise ValueError("装备资料的来源哈希不一致")
        return self


class EquipmentListData(CamelModel):
    pagination: PaginationMeta
    type_counts: dict[EquipmentType, int]
    elements: list[str]
    traits: list[str] = Field(default_factory=list)
    list: list[EquipmentRecord]
