from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import CamelModel
from app.schemas.rom_identity import IdentityReview


class RomIdentity(CamelModel):
    schema_version: Literal[1]
    title: Literal["METALMAX2R"]
    game_code: Literal["TMXJ"]
    user_version: Literal["0.99"]
    size: int = Field(ge=512, le=268435456)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    version_basis: str


class RomNameProof(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    verification_status: Literal["verified_0_99"]
    field: Literal["names.zh_099"]
    method: Literal[
        "rom_extraction_exact_name",
        "rom_extraction_parameter_identity",
        "rom_extraction_reviewed_identity",
    ]
    identity_parameters: dict[str, str] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    identity_price: int | None = Field(default=None, ge=0, exclude_if=lambda value: value is None)
    identity_review: IdentityReview | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    value: str = Field(min_length=1, max_length=128)
    matched_alias: str = Field(min_length=1)
    item_id: int = Field(ge=0)
    item_kind: int = Field(ge=1)
    record_offset: int = Field(ge=0)
    name_offset: int = Field(ge=0)
    name_bytes: int = Field(ge=2, le=512)


class EquipmentNameVerification(RomNameProof):
    rom_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class RomNameDataset(CamelModel):
    schema_version: Literal[1]
    verification_status: Literal["verified_0_99"]
    scope: Literal["equipment_names_only"]
    equipment_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    identity_catalog_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rom: RomIdentity
    records: list[RomNameProof] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_proofs(self) -> RomNameDataset:
        ids = [record.id for record in self.records]
        items = [record.item_id for record in self.records]
        if len(set(ids)) != len(ids) or len(set(items)) != len(items):
            raise ValueError("ROM 名称证据存在重复条目")
        for record in self.records:
            if (
                (record.method == "rom_extraction_parameter_identity")
                != (record.identity_parameters is not None)
                or (
                    record.method != "rom_extraction_parameter_identity"
                    and record.identity_price is not None
                )
                or (record.identity_parameters is not None and len(record.identity_parameters) < 3)
            ):
                raise ValueError(f"ROM 名称关联方式与参数证据不符：{record.id}")
            if (record.method == "rom_extraction_reviewed_identity") != (
                record.identity_review is not None
            ):
                raise ValueError(f"ROM 人工身份依据缺失或误用：{record.id}")
            review = record.identity_review
            if review is not None and (
                review.id != record.id
                or review.item_id != record.item_id
                or review.value != record.value
                or review.matched_alias != record.matched_alias
            ):
                raise ValueError(f"ROM 人工身份依据与名称不符：{record.id}")
            if (
                record.name_bytes != len(record.value.encode("utf-16le"))
                or record.record_offset + 12 > self.rom.size
                or record.name_offset + record.name_bytes + 2 > self.rom.size
            ):
                raise ValueError(f"ROM 名称证据位置无效：{record.id}")
        return self
