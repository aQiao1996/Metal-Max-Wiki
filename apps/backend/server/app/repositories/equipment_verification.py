import json
import re
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unicodedata import normalize

from app.schemas.equipment import EquipmentRecord
from app.schemas.rom_names import EquipmentNameVerification, RomNameDataset

_KIND_CODES = {
    "human_weapon": 1,
    "engine": 12,
    "c_unit": 13,
    "main_cannon": 14,
    "sub_gun": 15,
    "special_equipment": 16,
}


def _reference_parameters(record: EquipmentRecord) -> dict[str, str] | None:
    kind = record.kind
    fields = (
        ("weight_raw", "defense_raw", "capacity_raw")
        if kind == "engine"
        else ("weight_raw", "defense_raw", "accuracy_raw", "evasion_raw")
        if kind == "c_unit"
        else ("weight_raw", "defense_raw", "attack_raw", "magazine_raw")
    )
    mods = (
        record.engine_modifications
        if kind == "engine"
        else record.control_modifications
        if kind == "c_unit"
        else record.modifications
    )
    zero = next((mod for mod in mods if mod.stars == 0), None)
    source = zero.model_dump() if zero is not None else record.attributes
    if (
        zero is None
        and record.attributes.get("stat_condition_raw")
        and not str(record.attributes["stat_condition_raw"]).startswith("0 ")
    ):
        return None
    result = {}
    for field in fields:
        value = str(source.get(field, "")).removesuffix("t").strip()
        if field == "magazine_raw" and value == "∞":
            value = "0"
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) is None:
            return None
        result[field] = format(Decimal(value).normalize(), "f")
    return result


def apply_verified_names(
    records: list[EquipmentRecord], data_dir: Path
) -> tuple[EquipmentRecord, ...]:
    """仅覆盖有独立名称证据的字段，整条装备仍保留原参考状态。"""
    path = data_dir / "processed/mm2r/0.99/equipment-names.json"
    proofs = RomNameDataset.model_validate_json(path.read_bytes())
    registry = [
        {"id": record.id, "kind": record.kind, "names": record.names.model_dump(mode="json")}
        for record in sorted(records, key=lambda record: record.id)
    ]
    encoded = json.dumps(registry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if proofs.equipment_hash != "sha256:" + sha256(encoded.encode()).hexdigest():
        raise ValueError("ROM 名称证据与装备名称目录不一致")
    identities = [
        {
            "id": record.id,
            "kind": record.kind,
            "parameters": _reference_parameters(record) if record.kind != "human_weapon" else None,
            "price": str(record.attributes.get("price_raw", "")),
        }
        for record in sorted(records, key=lambda record: record.id)
    ]
    identity_json = json.dumps(
        identities, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    if proofs.identity_catalog_hash != "sha256:" + sha256(identity_json.encode()).hexdigest():
        raise ValueError("ROM 名称关联的参数匹配目录已变化")
    by_id = {proof.id: proof for proof in proofs.records}
    if not by_id.keys() <= {record.id for record in records}:
        raise ValueError("ROM 名称证据包含未知装备 ID")
    result: list[EquipmentRecord] = []
    for record in records:
        proof = by_id.get(record.id)
        if proof is None:
            result.append(record)
            continue
        aliases = [
            name
            for name in (
                record.names.ja,
                record.names.zh_09,
                record.names.zh_099,
                record.names.zh_reference,
                *record.names.aliases,
            )
            if name
        ]
        if proof.item_kind != _KIND_CODES[record.kind] or proof.matched_alias not in aliases:
            raise ValueError(f"ROM 名称证据与条目不符：{record.id}")
        if proof.method == "rom_extraction_exact_name":
            if normalize("NFKC", proof.value).casefold().replace(" ", "") != normalize(
                "NFKC", proof.matched_alias
            ).casefold().replace(" ", ""):
                raise ValueError(f"ROM 同名核验证据名称不符：{record.id}")
        elif proof.method == "rom_extraction_reviewed_identity":
            raw_attributes = {}
            for key, value in record.attributes.items():
                if key.endswith("_raw"):
                    if not isinstance(value, str):
                        raise ValueError(f"身份依据的原值不是文本：{record.id}/{key}")
                    raw_attributes[key] = value
            if proof.identity_review is None or (
                proof.identity_review.reference_attributes != raw_attributes
                or proof.identity_review.reference_source_hashes
                != sorted({ref.content_hash for ref in record.source_refs})
            ):
                raise ValueError(f"ROM 人工身份的来源依据已变化：{record.id}")
        elif proof.identity_parameters != _reference_parameters(record) or (
            proof.identity_price is not None
            and str(proof.identity_price)
            != str(record.attributes.get("price_raw", "")).removeprefix("*")
        ):
            raise ValueError(f"ROM 名称参数关联已变化：{record.id}")
        old_name = record.names.zh_099
        preserved = list(record.names.aliases)
        if old_name and old_name != proof.value and old_name not in preserved:
            preserved.append(old_name)
        names = record.names.model_copy(update={"zh_099": proof.value, "aliases": preserved})
        verification = EquipmentNameVerification(**proof.model_dump(), rom_sha256=proofs.rom.sha256)
        result.append(record.model_copy(update={"names": names, "name_verification": verification}))
    return tuple(result)
