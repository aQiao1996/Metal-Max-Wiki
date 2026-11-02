"""标准化领域数据的严格契约。"""

from datetime import datetime
from math import isfinite
from typing import Annotated, Literal
from unicodedata import normalize

from pydantic import Field, HttpUrl, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from mmwiki_data.models import StrictModel, VerificationStatus

Sha256Hash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
SourceRefKey = tuple[str, str, str, str, str, int, int]
SourceSpanKey = tuple[str, str, int, int, str, str, str]


class NameSet(StrictModel):
    """一条记录可用的多语言名称。"""

    ja: str | None = None
    zh_09: str | None = None
    zh_099: str | None = None
    zh_reference: str | None = Field(default=None, exclude_if=lambda value: value is None)
    aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_names(self) -> NameSet:
        """规范别名，并确保至少有一个名称。"""
        for field in ("ja", "zh_09", "zh_099", "zh_reference"):
            value = getattr(self, field)
            if value is not None:
                setattr(self, field, normalize("NFKC", value).strip() or None)
        aliases = [normalize("NFKC", alias).strip() for alias in self.aliases]
        if any(not alias for alias in aliases):
            raise ValueError("aliases cannot contain blank values")
        if len(aliases) != len(set(aliases)):
            raise ValueError("duplicate alias after NFKC normalization")
        self.aliases = sorted(aliases)
        if not any((self.ja, self.zh_09, self.zh_099, self.zh_reference, self.aliases)):
            raise ValueError("at least one name is required")
        return self


class SourceRef(StrictModel):
    """一条字段值对应的来源定位。"""

    source_id: str = Field(pattern=r"^[a-z0-9-]+$")
    target_id: str = Field(pattern=r"^[a-z0-9-]+$")
    source_url: HttpUrl
    retrieved_at: datetime
    content_hash: Sha256Hash
    table_index: int = Field(ge=0)
    row_index: int = Field(ge=0)


def source_ref_key(source_ref: SourceRef) -> SourceRefKey:
    """生成来源定位的稳定排序键。"""
    return (
        source_ref.source_id,
        source_ref.target_id,
        str(source_ref.source_url),
        source_ref.retrieved_at.isoformat(),
        source_ref.content_hash,
        source_ref.table_index,
        source_ref.row_index,
    )


def sorted_unique_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    """按完整定位去重并稳定排序来源。"""
    return [
        source_ref
        for _, source_ref in sorted(
            {source_ref_key(source_ref): source_ref for source_ref in source_refs}.items()
        )
    ]


class SourceSpan(StrictModel):
    """一条跨列表格单元格的来源定位。"""

    source_id: str = Field(pattern=r"^[a-z0-9-]+$")
    target_id: str = Field(pattern=r"^[a-z0-9-]+$")
    table_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    start_header: str = Field(min_length=1)
    end_header: str = Field(min_length=1)
    value: str = Field(min_length=1)


def source_span_key(source_span: SourceSpan) -> SourceSpanKey:
    """生成跨列来源的稳定排序键。"""
    return (
        source_span.source_id,
        source_span.target_id,
        source_span.table_index,
        source_span.row_index,
        source_span.start_header,
        source_span.end_header,
        source_span.value,
    )


def sorted_unique_source_spans(source_spans: list[SourceSpan]) -> list[SourceSpan]:
    """按完整跨列定位去重并稳定排序。"""
    return [
        source_span
        for _, source_span in sorted(
            {source_span_key(source_span): source_span for source_span in source_spans}.items()
        )
    ]


class EquipmentModification(StrictModel):
    """同一星级下的原始改造数值，不推算缺失项。"""

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


class ControlModification(StrictModel):
    """C 装置的面板改造数值，不把命中与回避换算为实际概率。"""

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


class EngineModification(StrictModel):
    """同型号引擎的逐星级载重与防御、重量改造值。"""

    stars: int = Field(ge=0, le=3)
    capacity_raw: str
    defense_min_raw: str
    defense_raw: str
    defense_max_raw: str
    weight_min_raw: str
    weight_raw: str
    weight_max_raw: str


class NormalizedRecord(StrictModel):
    """尚待本机版本核验的标准化领域记录。"""

    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    domain: Literal["equipment", "items", "quests", "jobs", "skills"]
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    names: NameSet
    attributes: dict[str, str | int | float | bool | None]
    modifications: list[EquipmentModification] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    control_modifications: list[ControlModification] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    engine_modifications: list[EngineModification] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    version_scope: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus
    source_refs: list[SourceRef] = Field(min_length=1)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    asset_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_collections(self) -> NormalizedRecord:
        """规范集合字段，并阻止中间记录越级核验。"""
        if self.verification_status is VerificationStatus.VERIFIED_0_99:
            raise ValueError("interim record cannot be verified_0_99")
        if any(
            isinstance(value, float) and not isfinite(value) for value in self.attributes.values()
        ):
            raise ValueError("record attributes must contain only finite floats")
        self.source_refs = sorted_unique_source_refs(self.source_refs)
        self.source_spans = sorted_unique_source_spans(self.source_spans)
        source_locators = {
            (
                source_ref.source_id,
                source_ref.target_id,
                source_ref.table_index,
                source_ref.row_index,
            )
            for source_ref in self.source_refs
        }
        if any(
            (
                source_span.source_id,
                source_span.target_id,
                source_span.table_index,
                source_span.row_index,
            )
            not in source_locators
            for source_span in self.source_spans
        ):
            raise ValueError("source span must match a source ref locator")
        self.version_scope = sorted(set(self.version_scope))
        self.issues = sorted(set(self.issues))
        self.asset_refs = sorted(set(self.asset_refs))
        return self


class ConflictValue(StrictModel):
    """保留字段冲突的原始标量类型和值。"""

    type: Literal["str", "int", "float", "bool", "null"]
    value: StrictStr | StrictInt | StrictFloat | StrictBool | None

    @model_validator(mode="after")
    def validate_scalar_type(self) -> ConflictValue:
        """阻止可比较字符串或布尔值伪装为其他类型。"""
        expected_types: dict[str, type[object]] = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "null": type(None),
        }
        if type(self.value) is not expected_types[self.type]:
            raise ValueError("conflict value type does not match declared type")
        if self.type == "float" and isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("conflict value float must be finite")
        return self


class FieldConflict(StrictModel):
    """同一字段的来源值冲突。"""

    record_id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    field: str = Field(min_length=1)
    values: dict[str, ConflictValue] = Field(min_length=1)
    source_refs: list[SourceRef] = Field(min_length=2)

    @model_validator(mode="after")
    def normalize_source_refs(self) -> FieldConflict:
        """规范冲突引用，并保留至少两条不同定位。"""
        self.source_refs = sorted_unique_source_refs(self.source_refs)
        if len(self.source_refs) < 2:
            raise ValueError("field conflict requires at least two source refs")
        locators = [
            f"{source_ref.source_id}:{source_ref.target_id}:"
            f"{source_ref.table_index}:{source_ref.row_index}"
            for source_ref in self.source_refs
        ]
        if len(locators) != len(set(locators)) or set(self.values) != set(locators):
            raise ValueError("field conflict values must match source ref locators")
        if len({(value.type, value.value) for value in self.values.values()}) < 2:
            raise ValueError("field conflict requires at least two distinct typed values")
        return self


class NormalizedBundle(StrictModel):
    """同一领域的标准化中间数据包。"""

    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    domain: Literal["equipment", "items", "quests", "jobs", "skills"]
    source_hashes: list[Sha256Hash]
    records: list[NormalizedRecord]

    @model_validator(mode="after")
    def normalize_records(self) -> NormalizedBundle:
        """规范来源哈希并拒绝重复记录标识。"""
        self.source_hashes = sorted(set(self.source_hashes))
        if any(record.domain != self.domain for record in self.records):
            raise ValueError("record domain must match bundle domain")
        expected_hashes = sorted(
            {
                source_ref.content_hash
                for record in self.records
                for source_ref in record.source_refs
            }
        )
        if self.source_hashes != expected_hashes:
            raise ValueError("source hashes must exactly match record source refs")
        record_ids = [record.id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("duplicate normalized record id")
        return self


class ConflictBundle(StrictModel):
    """同一目标版本的字段冲突数据包。"""

    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    conflicts: list[FieldConflict]
