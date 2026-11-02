"""将本机 ROM 的唯一同名记录保存为字段级核验证据。"""

import json
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal
from unicodedata import normalize

from pydantic import Field, model_validator

from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import NormalizedBundle, NormalizedRecord
from mmwiki_data.rom_equipment import decimal_text, read_equipment, reference_parameters
from mmwiki_data.rom_identity import IdentityReview, check_review_rom, load_identity_reviews
from mmwiki_data.rom_reader import read_item_names, read_nds_file, read_pak_files, read_rom
from mmwiki_data.storage import write_json_atomic

KIND_CODES = {
    "human_weapon": 1,
    "engine": 12,
    "c_unit": 13,
    "main_cannon": 14,
    "sub_gun": 15,
    "special_equipment": 16,
}
SOURCE_PATH = "data/raw/mm2r/0.99/rom/source.json"
OUTPUT_PATH = "data/processed/mm2r/0.99/equipment-names.json"
INPUT_PATH = "data/interim/mm2r/0.99/equipment.json"


class RomSource(StrictModel):
    schema_version: Literal[1]
    title: Literal["METALMAX2R"]
    game_code: Literal["TMXJ"]
    user_version: Literal["0.99"]
    size: int = Field(ge=512, le=268435456)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    version_basis: str = Field(min_length=1)


class VerifiedName(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9-]+-[0-9a-f]{10}$")
    verification_status: Literal["verified_0_99"] = "verified_0_99"
    field: Literal["names.zh_099"] = "names.zh_099"
    method: Literal[
        "rom_extraction_exact_name",
        "rom_extraction_parameter_identity",
        "rom_extraction_reviewed_identity",
    ] = "rom_extraction_exact_name"
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


class VerifiedNames(StrictModel):
    schema_version: Literal[1] = 1
    verification_status: Literal["verified_0_99"] = "verified_0_99"
    scope: Literal["equipment_names_only"] = "equipment_names_only"
    equipment_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    identity_catalog_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rom: RomSource
    records: list[VerifiedName] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_records(self) -> VerifiedNames:
        """每份证据只对应一个目录条目和一个 ROM 物品，不推测重名映射。"""
        ids = [record.id for record in self.records]
        item_ids = [record.item_id for record in self.records]
        if len(set(ids)) != len(ids) or len(set(item_ids)) != len(item_ids):
            raise ValueError("ROM 名称证据存在重复条目或重复物品")
        for record in self.records:
            if (record.method == "rom_extraction_parameter_identity") != (
                record.identity_parameters is not None
            ) or (
                record.method != "rom_extraction_parameter_identity"
                and record.identity_price is not None
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
            if record.identity_parameters is not None and len(record.identity_parameters) < 3:
                raise ValueError(f"ROM 名称参数对应至少需要三个字段：{record.id}")
            if record.name_bytes != len(record.value.encode("utf-16le")):
                raise ValueError(f"ROM 名称字节数不符：{record.id}")
            if (
                record.record_offset + 12 > self.rom.size
                or record.name_offset + record.name_bytes + 2 > self.rom.size
            ):
                raise ValueError(f"ROM 名称证据范围无效：{record.id}")
        return self


def equipment_name_hash(path: Path) -> str:
    """只绑定名称目录，数值变化不会将名称证据扩张为属性核验。"""
    records = NormalizedBundle.model_validate_json(path.read_bytes()).records
    value = [
        {
            "id": record.id,
            "kind": record.kind,
            "names": {
                **record.names.model_dump(mode="json"),
                "zh_reference": record.names.zh_reference,
            },
        }
        for record in sorted(records, key=lambda record: record.id)
    ]
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + sha256(encoded.encode()).hexdigest()


def equipment_identity_hash(records: list[NormalizedRecord]) -> str:
    """参数对应与反向唯一性依赖整个目录，包括尚未对应的条目。"""
    registry = []
    for record in sorted(records, key=lambda record: record.id):
        signature = reference_parameters(record) if record.kind != "human_weapon" else None
        registry.append(
            {
                "id": record.id,
                "kind": record.kind,
                "parameters": {key: decimal_text(value) for key, value in signature.items()}
                if signature is not None
                else None,
                "price": str(record.attributes.get("price_raw", "")),
            }
        )
    encoded = json.dumps(registry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + sha256(encoded.encode()).hexdigest()


def _key(value: str) -> str:
    return normalize("NFKC", value).casefold().replace(" ", "")


def _aliases(record: NormalizedRecord) -> list[str]:
    return [
        name
        for name in (
            record.names.zh_099,
            record.names.zh_09,
            record.names.zh_reference,
            record.names.ja,
            *record.names.aliases,
        )
        if name
    ]


def validate_rom_names(repo_root: Path) -> VerifiedNames | None:
    """离线核对依赖、字段范围和唯一同名匹配，不冒充重新读取 ROM。"""
    source_path, output_path = repo_root / SOURCE_PATH, repo_root / OUTPUT_PATH
    if not source_path.exists() and not output_path.exists():
        return None
    source = RomSource.model_validate_json(source_path.read_bytes())
    result = VerifiedNames.model_validate_json(output_path.read_bytes())
    if result.rom != source or result.equipment_hash != equipment_name_hash(repo_root / INPUT_PATH):
        raise ValueError("ROM 名称证据的来源或装备依赖已变化，请重新核验")
    records = NormalizedBundle.model_validate_json((repo_root / INPUT_PATH).read_bytes()).records
    reviews = load_identity_reviews(repo_root, records, source.sha256)
    saved_reviews = {
        p.id: p.identity_review for p in result.records if p.identity_review is not None
    }
    if saved_reviews != reviews:
        raise ValueError("ROM 人工名称证据与核对清单不一致")
    if result.identity_catalog_hash != equipment_identity_hash(records):
        raise ValueError("ROM 名称关联的参数匹配目录已变化，请重新核验")
    by_id = {record.id: record for record in records}
    for proof in result.records:
        record = by_id.get(proof.id)
        if (
            record is None
            or KIND_CODES.get(record.kind) != proof.item_kind
            or proof.matched_alias not in _aliases(record)
        ):
            raise ValueError(f"ROM 名称证据不能关联到装备条目：{proof.id}")
        if proof.method == "rom_extraction_exact_name":
            if _key(proof.matched_alias) != _key(proof.value):
                raise ValueError(f"ROM 同名核验证据名称不一致：{proof.id}")
        elif proof.method == "rom_extraction_parameter_identity":
            expected = reference_parameters(record)
            if expected is None or proof.identity_parameters != {
                key: decimal_text(value) for key, value in expected.items()
            }:
                raise ValueError(f"ROM 名称参数关联已过期：{proof.id}")
            if proof.identity_price is not None and str(proof.identity_price) != str(
                record.attributes.get("price_raw", "")
            ).removeprefix("*"):
                raise ValueError(f"ROM 名称价格关联已变化：{proof.id}")
    return result


def verify_rom_names(repo_root: Path, rom_path: Path, *, check: bool = False) -> dict[str, int]:
    """按登记指纹只读提取名称，仅保存分类内唯一且双向唯一的同名结果。"""
    source = RomSource.model_validate_json((repo_root / SOURCE_PATH).read_bytes())
    rom = read_rom(rom_path, expected_hash=source.sha256, expected_size=source.size)
    items = read_item_names(rom)
    equipment = read_equipment(rom, items)
    bundle = NormalizedBundle.model_validate_json((repo_root / INPUT_PATH).read_bytes())
    reviews = load_identity_reviews(repo_root, bundle.records, source.sha256)
    files = read_pak_files(read_nds_file(rom, "xls/data/pack_data.pak"))
    equipment_by_id = {equip.item.item_id: equip for equip in equipment}
    by_name: dict[tuple[int, str], list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        if item.name:
            by_name[item.kind, _key(item.name)].append(index)
    proposed: list[VerifiedName] = []
    signatures: dict[tuple[int, tuple[tuple[str, Decimal], ...]], list[int]] = defaultdict(list)
    for index, equip in enumerate(equipment):
        signatures[equip.item.kind, tuple((p.field, p.value) for p in equip.parameters)].append(
            index
        )
    for record in bundle.records:
        review = reviews.get(record.id)
        if review is not None:
            equip = equipment_by_id[review.item_id]
            if equip.item.kind != KIND_CODES[record.kind]:
                raise ValueError(f"人工身份的 ROM 分类不符：{record.id}")
            check_review_rom(review, equip, files, rom, equipment)
            item = equip.item
            proposed.append(
                VerifiedName(
                    id=record.id,
                    value=item.name,
                    matched_alias=review.matched_alias,
                    method="rom_extraction_reviewed_identity",
                    identity_review=review,
                    item_id=item.item_id,
                    item_kind=item.kind,
                    record_offset=item.record_offset,
                    name_offset=item.name_offset,
                    name_bytes=item.name_bytes,
                )
            )
            continue
        aliases = _aliases(record)
        candidates = {
            index for alias in aliases for index in by_name[KIND_CODES[record.kind], _key(alias)]
        }
        identity: dict[str, str] | None = None
        identity_price: int | None = None
        if len(candidates) == 1:
            item = items[next(iter(candidates))]
            matched_alias = next(alias for alias in aliases if _key(alias) == _key(item.name))
        else:
            expected = reference_parameters(record)
            if expected is None or len(expected) < 3:
                continue
            matching = signatures[KIND_CODES[record.kind], tuple(expected.items())]
            if len(matching) > 1:
                price = str(record.attributes.get("price_raw", "")).removeprefix("*")
                matching = [
                    index
                    for index in matching
                    if price.isdecimal() and equipment[index].item_price == int(price)
                ]
                if len(matching) == 1:
                    identity_price = int(price)
            if len(matching) != 1:
                continue
            item = equipment[matching[0]].item
            matched_alias = aliases[0]
            identity = {key: decimal_text(value) for key, value in expected.items()}
        proposed.append(
            VerifiedName(
                id=record.id,
                value=item.name,
                matched_alias=matched_alias,
                method="rom_extraction_parameter_identity"
                if identity
                else "rom_extraction_exact_name",
                identity_parameters=identity,
                identity_price=identity_price,
                item_id=item.item_id,
                item_kind=item.kind,
                record_offset=item.record_offset,
                name_offset=item.name_offset,
                name_bytes=item.name_bytes,
            )
        )
    owners: dict[int, list[str]] = defaultdict(list)
    for proof in proposed:
        owners[proof.item_id].append(proof.id)
    if any(len(owners[review.item_id]) != 1 for review in reviews.values()):
        raise ValueError("人工身份关联与其他装备争用同一个 ROM 物品")
    result = VerifiedNames(
        equipment_hash=equipment_name_hash(repo_root / INPUT_PATH),
        identity_catalog_hash=equipment_identity_hash(bundle.records),
        rom=source,
        records=sorted((p for p in proposed if len(owners[p.item_id]) == 1), key=lambda p: p.id),
    )
    output = repo_root / OUTPUT_PATH
    if check:
        if validate_rom_names(repo_root) != result:
            raise ValueError("ROM 重新提取的名称与已保存证据不一致")
    else:
        write_json_atomic(output, result)
    return {
        "verified_names": len(result.records),
        "unresolved_equipment": len(bundle.records) - len(result.records),
    }
