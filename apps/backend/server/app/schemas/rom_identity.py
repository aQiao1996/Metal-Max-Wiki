from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import CamelModel


class ReferenceParameter(CamelModel):
    field: Literal[
        "attack_raw",
        "defense_raw",
        "weight_raw",
        "capacity_raw",
        "magazine_raw",
        "accuracy_raw",
        "evasion_raw",
    ]
    source_path: str = Field(pattern=r"^data/raw/mm2r/0\.99/[a-z0-9/-]+\.json$")
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    json_pointer: str = Field(pattern=r"^#/.+")
    raw_value: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?t?$")


class RomByteEvidence(CamelModel):
    archive: Literal["xls/data/pack_data.pak", "xls/pack_data.pak"]
    file: str = Field(pattern=r"^[A-Z0-9_]+\.(?:ARR|NAM|SET)$")
    offset: int = Field(ge=0)
    hex: str = Field(pattern=r"^(?:[0-9a-f]{2}){1,512}$")
    note_zh: str = Field(min_length=1, max_length=1000)


class SourceEvidence(CamelModel):
    source_path: str = Field(pattern=r"^data/raw/mm2r/0\.99/[a-z0-9/-]+\.json$")
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    json_pointer: str = Field(pattern=r"^#/.+")
    value_json: str = Field(min_length=1, max_length=50000)
    note_zh: str = Field(min_length=1, max_length=1000)


class IdentityReview(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    item_id: int = Field(ge=0)
    value: str = Field(min_length=1, max_length=128)
    matched_alias: str = Field(min_length=1)
    reference_attributes: dict[str, str] = Field(min_length=2)
    reference_source_hashes: list[str] = Field(min_length=1)
    parameter_table: Literal["ENGINE.ARR", "CUNIT.ARR", "CARWEPON.ARR", "NINGEN_BUKI.ARR"]
    parameter_index: int = Field(ge=0)
    parameter_hex: str = Field(pattern=r"^(?:[0-9a-f]{2}){8,20}$")
    base_parameters: list[ReferenceParameter]
    source_evidence: list[SourceEvidence]
    rom_evidence: list[RomByteEvidence]
    note_zh: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def validate_layout(self) -> IdentityReview:
        widths = {"ENGINE.ARR": 12, "CUNIT.ARR": 12, "CARWEPON.ARR": 20, "NINGEN_BUKI.ARR": 8}
        if len(bytes.fromhex(self.parameter_hex)) != widths[self.parameter_table]:
            raise ValueError(f"人工身份记录宽度无效：{self.id}")
        if len({p.field for p in self.base_parameters}) != len(self.base_parameters):
            raise ValueError(f"人工身份基础字段重复：{self.id}")
        return self
