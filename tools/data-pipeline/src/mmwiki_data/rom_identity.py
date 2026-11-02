"""保存人工逐项核对的身份依据，并在重读时验证来源与 ROM 字节。"""

import json
import re
import struct
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import NormalizedRecord
from mmwiki_data.rom_equipment import ParameterField, RomEquipment
from mmwiki_data.rom_reader import RomFile, read_nds_file, read_pak_files

REVIEW_PATH = "data/raw/mm2r/0.99/rom/identity-reviews.json"


class ReferenceParameter(StrictModel):
    field: ParameterField
    source_path: str = Field(pattern=r"^data/raw/mm2r/0\.99/[a-z0-9/-]+\.json$")
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    json_pointer: str = Field(pattern=r"^#/.+")
    raw_value: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?t?$")


class RomByteEvidence(StrictModel):
    archive: Literal["xls/data/pack_data.pak", "xls/pack_data.pak"]
    file: str = Field(pattern=r"^[A-Z0-9_]+\.(?:ARR|NAM|SET)$")
    offset: int = Field(ge=0)
    hex: str = Field(pattern=r"^(?:[0-9a-f]{2}){1,512}$")
    note_zh: str = Field(min_length=1, max_length=1000)


class SourceEvidence(StrictModel):
    source_path: str = Field(pattern=r"^data/raw/mm2r/0\.99/[a-z0-9/-]+\.json$")
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    json_pointer: str = Field(pattern=r"^#/.+")
    value_json: str = Field(min_length=1, max_length=50000)
    note_zh: str = Field(min_length=1, max_length=1000)


class IdentityReview(StrictModel):
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
        if len({field.field for field in self.base_parameters}) != len(self.base_parameters):
            raise ValueError(f"人工身份基础字段重复：{self.id}")
        if any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", h) is None for h in self.reference_source_hashes
        ):
            raise ValueError(f"人工身份来源哈希无效：{self.id}")
        return self


class IdentityReviews(StrictModel):
    schema_version: Literal[1] = 1
    scope: Literal["equipment_identity_only"] = "equipment_identity_only"
    rom_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    records: list[IdentityReview] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique(self) -> IdentityReviews:
        if len({r.id for r in self.records}) != len(self.records) or len(
            {r.item_id for r in self.records}
        ) != len(self.records):
            raise ValueError("人工身份清单存在重复条目或物品 ID")
        return self


def reference_attributes(record: NormalizedRecord) -> dict[str, str]:
    """保留原资料的原值字段，避免身份记录在来源改变后继续生效。"""
    result = {}
    for key, value in record.attributes.items():
        if key.endswith("_raw"):
            if not isinstance(value, str):
                raise ValueError(f"身份依据的原值不是文本：{record.id}/{key}")
            result[key] = value
    return result


def reference_sources(record: NormalizedRecord) -> list[str]:
    """以来源内容哈希绑定人工核对时使用的资料。"""
    return sorted({ref.content_hash for ref in record.source_refs})


def review_parameters(review: IdentityReview) -> dict[str, Decimal] | None:
    """只取有独立原始字段定位的基础值，不反算星级倍率。"""
    if not review.base_parameters:
        return None
    return {p.field: Decimal(p.raw_value.removesuffix("t")) for p in review.base_parameters}


def _source_value(
    repo_root: Path, path_text: str, content_hash: str, pointer: str, identity: str
) -> object:
    path = repo_root / path_text
    if not path.resolve().is_relative_to((repo_root / "data/raw/mm2r/0.99").resolve()):
        raise ValueError(f"人工身份来源路径越界：{identity}")
    data = path.read_bytes()
    if "sha256:" + sha256(data).hexdigest() != content_hash:
        raise ValueError(f"人工身份来源已变化：{identity}/{path_text}")
    value: object = json.loads(data)
    for part in pointer[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list) and key.isdecimal():
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError(f"人工身份来源定位无效：{identity}/{pointer}")
    return value


def _validate_sources(repo_root: Path, review: IdentityReview) -> None:
    for field in review.base_parameters:
        value = _source_value(
            repo_root, field.source_path, field.source_sha256, field.json_pointer, review.id
        )
        if not isinstance(value, str) or value != field.raw_value:
            raise ValueError(f"人工身份基础原值已变化：{review.id}/{field.field}")
    for source in review.source_evidence:
        value = _source_value(
            repo_root, source.source_path, source.source_sha256, source.json_pointer, review.id
        )
        if value != json.loads(source.value_json):
            raise ValueError(f"人工身份辅助来源已变化：{review.id}/{source.json_pointer}")


def load_identity_reviews(
    repo_root: Path, records: list[NormalizedRecord], rom_sha256: str
) -> dict[str, IdentityReview]:
    """核对人工清单的来源依赖，不把人工关联伪装成自动同名匹配。"""
    dataset = IdentityReviews.model_validate_json((repo_root / REVIEW_PATH).read_bytes())
    if dataset.rom_sha256 != rom_sha256:
        raise ValueError("人工身份清单与登记 ROM 指纹不一致")
    by_id = {record.id: record for record in records}
    for review in dataset.records:
        record = by_id.get(review.id)
        if (
            record is None
            or review.reference_attributes != reference_attributes(record)
            or (review.reference_source_hashes != reference_sources(record))
        ):
            raise ValueError(f"人工身份清单的装备来源已变化：{review.id}")
        aliases = [
            record.names.ja,
            record.names.zh_09,
            record.names.zh_099,
            record.names.zh_reference,
            *record.names.aliases,
        ]
        if review.matched_alias not in aliases:
            raise ValueError(f"人工身份原名称已变化：{review.id}")
        _validate_sources(repo_root, review)
    return {review.id: review for review in dataset.records}


def _record_bytes(equip: RomEquipment, files: dict[str, RomFile]) -> bytes:
    at = equip.parameter_index * equip.record_width
    return files[equip.table].data[at : at + equip.record_width]


def _check_unique_identity(
    review: IdentityReview,
    equip: RomEquipment,
    files: dict[str, RomFile],
    catalog: tuple[RomEquipment, ...],
) -> None:
    price = review.reference_attributes.get("price_raw", "").removeprefix("*")
    candidates = [
        candidate
        for candidate in catalog
        if candidate.item.kind == equip.item.kind
        and (not price.isdecimal() or candidate.item_price == int(price))
    ]
    if equip.item.kind == 1:
        target = _record_bytes(equip, files)
        candidates = [
            c
            for c in candidates
            if _record_bytes(c, files)[2:4] == target[2:4]
            and (_record_bytes(c, files)[0] | _record_bytes(c, files)[1]) & 126
            == (target[0] | target[1]) & 126
        ]
        recipe = re.fullmatch(
            r"LOVE组合([123]{4})", review.reference_attributes.get("acquisition_raw", "")
        )
        if recipe is not None:
            index = sum((int(digit) - 1) * 3 ** (3 - i) for i, digit in enumerate(recipe[1]))
            item_id, description = struct.unpack_from(
                "<HH", files["LOVE_KUMIAWASE.ARR"].data, index * 4
            )
            text = files["LOVE_KUMIAWASE.NAM"].data
            end = description
            while text[end : end + 2] != b"\0\0":
                if end + 2 > len(text):
                    raise ValueError(f"LOVE身份说明越界：{review.id}")
                end += 2
            if review.reference_attributes["additional_raw"] not in text[description:end].decode(
                "utf-16le"
            ):
                raise ValueError(f"LOVE配方说明与来源不符：{review.id}")
            candidates = [c for c in candidates if c.item.item_id == item_id]
        drop_ids = {
            int.from_bytes(bytes.fromhex(e.hex)[:2], "little")
            for e in review.rom_evidence
            if e.file == "ENE_MONSTER.ARR" and e.offset % 108 in {96, 100, 104} and len(e.hex) == 8
        }
        if drop_ids:
            candidates = [c for c in candidates if c.item.item_id in drop_ids]
        families = [
            bytes.fromhex(e.hex)
            for e in review.rom_evidence
            if e.file == "NINGEN_BUKI.ARR" and e.offset % 8 == 4 and len(e.hex) == 8
        ]
        if families:
            candidates = [
                c
                for c in candidates
                if all(_record_bytes(c, files)[4:] == family for family in families)
            ]
    else:
        expected = review_parameters(review)
        candidates = [c for c in candidates if {p.field: p.value for p in c.parameters} == expected]
        # 只解释本批已逐项交叉核对的特性码，不据此推广战斗公式。
        traits = {
            "CUNIT.ARR": {13: "キャノンラッシュ", 15: "S-Eラッシュ", 16: "ダーティラッシュ"},
            "ENGINE.ARR": {
                1: "カーボーナス",
                4: "バイクボーナス",
                5: "シングルボーナス",
                6: "無双タイプ",
            },
        }
        if equip.table in traits:
            candidates = [
                c
                for c in candidates
                if traits[equip.table].get(_record_bytes(c, files)[10])
                == review.reference_attributes["trait_raw"]
            ]
    if len(candidates) != 1 or candidates[0].item.item_id != equip.item.item_id:
        raise ValueError(f"人工身份无法由独立条件唯一对应：{review.id}")


def check_review_rom(
    review: IdentityReview,
    equip: RomEquipment,
    files: dict[str, RomFile],
    rom: bytes,
    catalog: tuple[RomEquipment, ...],
) -> None:
    """重读物品索引、完整参数记录与辅助证据，拒绝漂移或截断记录。"""
    actual = files[equip.table].data[
        equip.parameter_index * equip.record_width : (equip.parameter_index + 1)
        * equip.record_width
    ]
    if (
        review.item_id != equip.item.item_id
        or review.value != equip.item.name
        or review.parameter_table != equip.table
        or review.parameter_index != equip.parameter_index
        or review.parameter_hex != actual.hex()
    ):
        raise ValueError(f"人工身份与 ROM 记录不一致：{review.id}")
    if equip.item.kind == 1:
        roles = {
            "hunter": 2,
            "mechanic": 4,
            "soldier": 8,
            "nurse": 16,
            "wrestler": 32,
            "artist": 64,
        }
        expected = 0
        for role, bit in roles.items():
            flag = review.reference_attributes.get(role + "_raw")
            if flag not in {"○", "-"}:
                raise ValueError(f"人工身份职业依据不完整：{review.id}/{role}")
            if flag == "○":
                expected |= bit
        if (actual[0] | actual[1]) & 126 != expected or int.from_bytes(
            actual[2:4], "little"
        ) != int(review.reference_attributes["attack_raw"]):
            raise ValueError(f"人工身份攻击力或职业投影不符：{review.id}")
    else:
        expected_parameters = review_parameters(review)
        actual_parameters = {p.field: p.value for p in equip.parameters}
        if expected_parameters != actual_parameters:
            raise ValueError(f"人工身份基础参数不符：{review.id}")
    price = review.reference_attributes.get("price_raw", "").removeprefix("*")
    if price.isdecimal() and int(price) != equip.item_price:
        raise ValueError(f"人工身份价格不符：{review.id}")
    archives = {"xls/data/pack_data.pak": files}
    for evidence in review.rom_evidence:
        if evidence.archive not in archives:
            archives[evidence.archive] = read_pak_files(read_nds_file(rom, evidence.archive))
        data = archives[evidence.archive][evidence.file].data
        expected_bytes = bytes.fromhex(evidence.hex)
        start = evidence.offset
        if (
            start + len(expected_bytes) > len(data)
            or data[start : start + len(expected_bytes)] != expected_bytes
        ):
            raise ValueError(f"人工身份 ROM 辅助证据不符：{review.id}/{evidence.file}")
    _check_unique_identity(review, equip, files, catalog)
