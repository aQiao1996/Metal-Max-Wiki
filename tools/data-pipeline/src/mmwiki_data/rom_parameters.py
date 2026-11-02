"""保存 ROM 基础参数与现有资料的逐字段对照，不推算星级或隐藏机制。"""

from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import NormalizedBundle
from mmwiki_data.rom_equipment import (
    PARAMETER_FIELDS,
    decimal_text,
    read_equipment,
    reference_parameters,
)
from mmwiki_data.rom_identity import review_parameters
from mmwiki_data.rom_names import (
    INPUT_PATH,
    RomSource,
    validate_rom_names,
    verify_rom_names,
)
from mmwiki_data.rom_reader import read_item_names, read_rom
from mmwiki_data.storage import model_content_hash, write_json_atomic

OUTPUT_PATH = "data/processed/mm2r/0.99/equipment-parameters.json"


class ParameterValue(StrictModel):
    field: Literal[
        "attack_raw",
        "defense_raw",
        "weight_raw",
        "capacity_raw",
        "magazine_raw",
        "accuracy_raw",
        "evasion_raw",
    ]
    value: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$")
    encoded: int = Field(ge=0, le=65535)
    scale: Literal[1, 100]
    offset: int = Field(ge=0)
    byte_length: Literal[1, 2]
    reference_value: str | None
    comparison: Literal["equal", "different", "condition_unavailable"]


class EquipmentParameters(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    verification_status: Literal["verified_0_99"] = "verified_0_99"
    scope: Literal["unmodified_base_constants_only"] = "unmodified_base_constants_only"
    item_id: int = Field(ge=0)
    parameter_index: int = Field(ge=0)
    table: Literal["ENGINE.ARR", "CUNIT.ARR", "CARWEPON.ARR", "NINGEN_BUKI.ARR"]
    record_offset: int = Field(ge=0)
    record_width: Literal[8, 12, 20]
    fields: list[ParameterValue] = Field(min_length=1)


class ParameterDataset(StrictModel):
    schema_version: Literal[1] = 1
    verification_status: Literal["verified_0_99"] = "verified_0_99"
    scope: Literal["equipment_base_parameters_only"] = "equipment_base_parameters_only"
    condition: Literal[
        "ROM未加星未改造基础常量；不证明可获取星级及运行效果；弹仓0表示无有限弹仓"
    ] = "ROM未加星未改造基础常量；不证明可获取星级及运行效果；弹仓0表示无有限弹仓"
    equipment_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    names_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rom: RomSource
    records: list[EquipmentParameters] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fields(self) -> ParameterDataset:
        if len({record.id for record in self.records}) != len(self.records):
            raise ValueError("ROM 参数证据包含重复装备")
        for record in self.records:
            if record.record_offset + record.record_width > self.rom.size:
                raise ValueError(f"ROM 参数记录越界：{record.id}")
            if len({field.field for field in record.fields}) != len(record.fields):
                raise ValueError(f"ROM 参数证据包含重复字段：{record.id}")
            for field in record.fields:
                if (
                    not record.record_offset
                    <= field.offset
                    <= (record.record_offset + record.record_width - field.byte_length)
                    or field.encoded >= 256**field.byte_length
                ):
                    raise ValueError(f"ROM 参数字段越界：{record.id}/{field.field}")
                if decimal_text(Decimal(field.encoded) / field.scale) != field.value:
                    raise ValueError(f"ROM 参数编码与值不符：{record.id}/{field.field}")
                expected = (
                    "condition_unavailable"
                    if field.reference_value is None
                    else "equal"
                    if field.reference_value == field.value
                    else "different"
                )
                if field.comparison != expected:
                    raise ValueError(f"ROM 参数对照结论无效：{record.id}/{field.field}")
        return self


def _compare(repo_root: Path, rom: bytes) -> ParameterDataset:
    names = validate_rom_names(repo_root)
    if names is None:
        raise ValueError("缺少 ROM 名称关联证据，不能核对参数")
    bundle = NormalizedBundle.model_validate_json((repo_root / INPUT_PATH).read_bytes())
    by_id = {record.id: record for record in bundle.records}
    equipment = {equip.item.item_id: equip for equip in read_equipment(rom, read_item_names(rom))}
    records = []
    for proof in names.records:
        equip = equipment[proof.item_id]
        reference = reference_parameters(by_id[proof.id])
        if reference is None and proof.identity_review is not None:
            reference = review_parameters(proof.identity_review)
        fields = []
        for field in equip.parameters:
            value = decimal_text(field.value)
            ref = decimal_text(reference[field.field]) if reference is not None else None
            comparison: Literal["equal", "different", "condition_unavailable"] = (
                "condition_unavailable" if ref is None else "equal" if ref == value else "different"
            )
            fields.append(
                ParameterValue(
                    field=field.field,
                    value=value,
                    encoded=field.encoded,
                    scale=field.scale,
                    offset=field.offset,
                    byte_length=field.byte_length,
                    reference_value=ref,
                    comparison=comparison,
                )
            )
        records.append(
            EquipmentParameters(
                id=proof.id,
                item_id=proof.item_id,
                parameter_index=equip.parameter_index,
                table=equip.table,
                record_offset=equip.record_offset,
                record_width=equip.record_width,
                fields=fields,
            )
        )
    return ParameterDataset(
        equipment_hash=model_content_hash(bundle),
        names_hash=model_content_hash(names),
        rom=names.rom,
        records=records,
    )


def validate_rom_parameters(repo_root: Path) -> ParameterDataset | None:
    """离线验证参数证据的类型、位置与依赖，不替代重新读取 ROM。"""
    path = repo_root / OUTPUT_PATH
    if not path.exists():
        return None
    dataset = ParameterDataset.model_validate_json(path.read_bytes())
    names = validate_rom_names(repo_root)
    bundle = NormalizedBundle.model_validate_json((repo_root / INPUT_PATH).read_bytes())
    if (
        names is None
        or dataset.rom != names.rom
        or (
            dataset.names_hash != model_content_hash(names)
            or dataset.equipment_hash != model_content_hash(bundle)
            or {record.id for record in dataset.records} != {proof.id for proof in names.records}
        )
    ):
        raise ValueError("ROM 参数证据依赖已变化，请重新核对")
    name_proofs = {proof.id: proof for proof in names.records}
    references = {record.id: record for record in bundle.records}
    for record in dataset.records:
        name = name_proofs[record.id]
        table, width, layout = PARAMETER_FIELDS[name.item_kind]
        if record.item_id != name.item_id or record.table != table or record.record_width != width:
            raise ValueError(f"ROM 参数证据与名称分类不一致：{record.id}")
        by_field = {field.field: field for field in record.fields}
        if set(by_field) != {field for field, _, _, _ in layout}:
            raise ValueError(f"ROM 参数证据字段集合不一致：{record.id}")
        reference = reference_parameters(references[record.id])
        if reference is None and name.identity_review is not None:
            reference = review_parameters(name.identity_review)
        for field_name, relative, size, scale in layout:
            field = by_field[field_name]
            expected_ref = decimal_text(reference[field_name]) if reference is not None else None
            if (
                field.offset != record.record_offset + relative
                or field.byte_length != size
                or field.scale != scale
                or field.reference_value != expected_ref
            ):
                raise ValueError(f"ROM 参数位置或参考条件不一致：{record.id}/{field_name}")
    return dataset


def verify_rom_parameters(
    repo_root: Path, rom_path: Path, *, check: bool = False
) -> dict[str, int]:
    """先重读名称关联，再生成或校验逐字段参数证据。"""
    verify_rom_names(repo_root, rom_path, check=True)
    names = validate_rom_names(repo_root)
    if names is None:
        raise ValueError("缺少 ROM 名称关联证据")
    rom = read_rom(rom_path, expected_hash=names.rom.sha256, expected_size=names.rom.size)
    result = _compare(repo_root, rom)
    if check:
        if validate_rom_parameters(repo_root) != result:
            raise ValueError("ROM 重新提取参数与已保存证据不一致")
    else:
        write_json_atomic(repo_root / OUTPUT_PATH, result)
    counts: Counter[str] = Counter(
        field.comparison for record in result.records for field in record.fields
    )
    return {
        "equipment_records": len(result.records),
        "parameter_fields": sum(counts.values()),
        **dict(counts),
    }
