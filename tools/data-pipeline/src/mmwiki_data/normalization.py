"""将已知来源表格确定性映射为可追溯记录。"""

import json
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, NamedTuple
from unicodedata import normalize

from mmwiki_data.models import CandidateSnapshot, VerificationStatus
from mmwiki_data.normalization_models import (
    ConflictBundle,
    ConflictValue,
    FieldConflict,
    NameSet,
    NormalizedBundle,
    NormalizedRecord,
    SourceRef,
    SourceSpan,
    source_ref_key,
)

type AttributeValue = str | int | float | bool | None
type Domain = Literal["equipment", "items", "quests", "jobs", "skills"]

ALIASES: dict[tuple[str, str], dict[str, str]] = {}
"""仅收录有明确来源证据的日文名称映射。"""

DISAMBIGUATION_FIELDS: dict[tuple[str, str, str], tuple[str, ...]] = {
    ("equipment", "main_cannon", "LOVEマシン"): ("attack_raw",),
}
"""同源同名变体的最小人工确认身份字段。"""

_EXPECTED_TARGET_IDS = frozenset(
    {
        "tank-parts",
        "special-shells",
        "tank-tools",
        "human-equipment",
        "human-items",
        "quests",
        "dqff-human-items",
        "dqff-tank-items",
        "dqff-special-shells",
        "dqff-jobs",
        "dqff-skills-field",
        "dqff-skills-vehicle",
        "dqff-skills-auto",
        "dqff-skills-human",
        "dqff-skills-repair",
        "dqff-skills-healing",
        "dqff-skills-art",
    }
)


class NormalizationResult(NamedTuple):
    """完整候选快照的标准化结果。"""

    bundles: dict[str, NormalizedBundle]
    conflicts: ConflictBundle


class NormalizationError(ValueError):
    """来源字段或标识不满足已知映射契约。"""


def normalized_key(value: str) -> str:
    """统一标识的全半角并去除外层空白。"""
    return normalize("NFKC", value).strip()


def stable_record_id(domain: str, kind: str, canonical_key: str) -> str:
    """按领域、种类及规范名称生成稳定标识。"""
    canonical = normalized_key(canonical_key)
    if not canonical:
        raise NormalizationError("canonical key must not be empty")
    digest = sha256(f"{domain}\0{kind}\0{canonical}".encode()).hexdigest()[:10]
    return f"{kind.replace('_', '-')}-{digest}"


def parse_optional_int(value: str) -> int | None:
    """规范全半角及空白后，仅解析无单位、无修饰的十进制整数。"""
    normalized = normalized_key(value)
    return int(normalized) if normalized.isdecimal() else None


def compact_attributes(attributes: Mapping[str, AttributeValue]) -> dict[str, AttributeValue]:
    """去除空字符串与空值，并保留其余值的原始类型。"""
    return {key: value for key, value in attributes.items() if value is not None and value != ""}


def expect_headers(target_id: str, headers: Sequence[str], expected: Set[str]) -> None:
    """精确验证表头集合，拒绝重复、未知和缺少的列。"""
    if len(headers) != len(expected) or set(headers) != expected:
        raise NormalizationError(
            f"{target_id}: unexpected headers {list(headers)!r}; expected {sorted(expected)!r}"
        )


@dataclass(frozen=True)
class _Schema:
    domain: Domain
    kind: str
    ja_header: str | None
    zh_header: str | None
    fields: Mapping[str, str]
    numeric_fields: frozenset[str] = frozenset()

    @property
    def headers(self) -> set[str]:
        result = set(self.fields)
        if self.ja_header is not None:
            result.add(self.ja_header)
        if self.zh_header is not None:
            result.add(self.zh_header)
        return result


_CANNON = _Schema(
    "equipment",
    "main_cannon",
    "名称",
    "汉译",
    {
        "攻击": "attack_raw",
        "范围": "range_raw",
        "属性": "element_raw",
        "守备": "defense_raw",
        "重量(t)": "weight_raw",
        "弹仓": "magazine_raw",
        "特殊炮弹": "special_shell_raw",
        "价格(G)": "price_raw",
        "稀有度": "rarity_raw",
    },
    frozenset({"attack", "defense", "weight", "magazine", "price", "rarity"}),
)
_WEAPON = _Schema(
    "equipment",
    "human_weapon",
    "日文",
    "汉译",
    {
        "攻击": "attack_raw",
        "范围": "range_raw",
        "属性": "element_raw",
        "追加": "additional_raw",
        "☆数": "stars_raw",
        "猎": "hunter_raw",
        "机": "mechanic_raw",
        "兵": "soldier_raw",
        "护": "nurse_raw",
        "摔": "wrestler_raw",
        "艺": "artist_raw",
        "价格": "price_raw",
        "入手": "acquisition_raw",
        "备注": "notes_raw",
    },
    frozenset({"attack", "stars", "price"}),
)
_TANK_ITEM = _Schema(
    "items",
    "tank_item",
    "名称",
    "0.9汉化",
    {
        "效果": "effect_raw",
        "对象": "usage_context_zh_09_raw",
        "消费": "consumption_raw",
        "重量(t)": "weight_raw",
        "价格(G)": "price_raw",
        "星数": "stars_raw",
    },
    frozenset({"weight", "price", "stars"}),
)
_SHELL = _Schema(
    "items",
    "special_shell",
    "名称",
    "0.9汉化",
    {
        "効果": "effect_raw",
        "材料1": "material_1_raw",
        "材料2": "material_2_raw",
        "材料3": "material_3_raw",
        "価格(G)": "price_raw",
        "備考": "notes_raw",
    },
    frozenset({"price"}),
)
_CHIP = _Schema("items", "ic_chip_location", "种类", None, {"场所": "location_raw"})
_LOVE = _Schema(
    "items",
    "love_machine_recipe",
    None,
    None,
    {
        "L": "l_raw",
        "O": "o_raw",
        "V": "v_raw",
        "E": "e_raw",
        "地图上使用效果": "field_effect_raw",
        "战斗中使用效果": "battle_effect_raw",
    },
    frozenset({"l", "o", "v", "e"}),
)
_QUEST = _Schema(
    "quests",
    "quest",
    "任务名称",
    "汉译名",
    {
        "任务接受场所": "location_raw",
        "经验值": "experience_raw",
        "有名度": "fame_raw",
        "报酬": "reward_raw",
        "备注": "notes_raw",
    },
    frozenset({"experience", "fame", "reward"}),
)
_JOB = _Schema("jobs", "job", "職業", None, {"No": "number_raw"}, frozenset({"number"}))
_DQFF_ITEM_FIELDS = {
    "No": "number_raw",
    "種類": "category_raw",
    "説明": "description_raw",
    "対象": "target_ja_raw",
}
_SKILL_FIELDS = {
    "No": "number_raw",
    "職業": "job_raw",
    "Lv": "level_raw",
    "種類": "skill_category",
    "説明": "description_raw",
}
_SKILL_NO_TARGET = _Schema(
    "skills",
    "skill",
    "スキル",
    None,
    _SKILL_FIELDS,
    frozenset({"number", "level"}),
)
_SKILL_WITH_TARGET = _Schema(
    "skills",
    "skill",
    "スキル",
    None,
    _SKILL_FIELDS | {"対象": "target_raw"},
    frozenset({"number", "level"}),
)
_SCHEMAS: dict[str, _Schema] = {
    "tank-parts": _CANNON,
    "human-equipment": _WEAPON,
    "tank-tools": _TANK_ITEM,
    "special-shells": _SHELL,
    "quests": _QUEST,
    "dqff-human-items": _Schema(
        "items",
        "human_item",
        "アイテム",
        None,
        _DQFF_ITEM_FIELDS,
        frozenset({"number"}),
    ),
    "dqff-tank-items": _Schema(
        "items",
        "tank_item",
        "アイテム",
        None,
        _DQFF_ITEM_FIELDS,
        frozenset({"number"}),
    ),
    "dqff-special-shells": _Schema(
        "items",
        "special_shell",
        "アイテム",
        None,
        _DQFF_ITEM_FIELDS,
        frozenset({"number"}),
    ),
    "dqff-jobs": _JOB,
    "dqff-skills-field": _SKILL_NO_TARGET,
    "dqff-skills-art": _SKILL_NO_TARGET,
    "dqff-skills-vehicle": _SKILL_WITH_TARGET,
    "dqff-skills-auto": _SKILL_WITH_TARGET,
    "dqff-skills-human": _SKILL_WITH_TARGET,
    "dqff-skills-repair": _SKILL_WITH_TARGET,
    "dqff-skills-healing": _SKILL_WITH_TARGET,
}


def normalize_row(
    target_id: str,
    section: str,
    headers: Sequence[str],
    row: Mapping[str, str],
    source_ref: SourceRef,
) -> NormalizedRecord:
    """验证已知来源 schema，并保留原始字段及完整来源定位。"""
    if source_ref.target_id != target_id:
        raise NormalizationError(
            f"{target_id}: source_ref.target_id {source_ref.target_id!r} does not match target"
        )
    if target_id == "human-items":
        schema = _LOVE if set(headers) & {"L", "O", "V", "E"} else _CHIP
    elif target_id in _SCHEMAS:
        schema = _SCHEMAS[target_id]
    else:
        raise NormalizationError(f"{target_id}: unknown target; headers {list(headers)!r}")
    if target_id == "tank-parts" and section != "主炮":
        raise NormalizationError(
            f"{target_id}: unsupported section {section!r}; headers {list(headers)!r}"
        )
    expect_headers(target_id, headers, schema.headers)
    expect_headers(target_id, list(row), schema.headers)

    issues: list[str] = []
    if schema is _LOVE:
        parts = [normalized_key(row[column]) for column in ("L", "O", "V", "E")]
        if not all(parts):
            raise NormalizationError(f"{target_id}: LOVE recipe requires L/O/V/E values")
        canonical = "-".join(parts)
        names = NameSet(aliases=[canonical])
    else:
        ja = row[schema.ja_header].strip() or None if schema.ja_header else None
        zh = row[schema.zh_header].strip() or None if schema.zh_header else None
        canonical = ja or zh or ""
        if not canonical:
            raise NormalizationError(f"{target_id}: canonical name must not be empty")
        names = NameSet(ja=ja, zh_09=zh)
    if names.ja is None:
        issues.append("missing_japanese_name")

    attributes: dict[str, AttributeValue] = {
        field: row[header] for header, field in schema.fields.items()
    }
    for field in sorted(schema.numeric_fields):
        raw = attributes[f"{field}_raw"]
        if isinstance(raw, str):
            attributes[field] = parse_optional_int(raw)
    if schema.domain == "skills":
        attributes["source_target"] = target_id
    dqff = target_id.startswith("dqff-")
    return NormalizedRecord(
        id=stable_record_id(schema.domain, schema.kind, canonical),
        domain=schema.domain,
        kind=schema.kind,
        names=names,
        attributes=compact_attributes(attributes),
        version_scope=["mm2r-jp"] if dqff else ["mm2r-jp", "zh-patch-0.9-family"],
        verification_status=(
            VerificationStatus.SOURCE_ONLY if dqff else VerificationStatus.COMPATIBLE_CANDIDATE
        ),
        source_refs=[source_ref],
        issues=issues,
    )


def _snapshot_sort_key(snapshot: CandidateSnapshot) -> tuple[str, str, str, str, str]:
    """按完整来源元数据稳定排列快照。"""
    return (
        snapshot.target_id,
        snapshot.source_id,
        str(snapshot.source_url),
        snapshot.retrieved_at.isoformat(),
        snapshot.content_hash,
    )


def _record_sort_key(record: NormalizedRecord) -> tuple[object, ...]:
    """按记录标识和完整来源稳定排列。"""
    return (record.id, *(source_ref_key(source_ref) for source_ref in record.source_refs))


def _records_match(left: NormalizedRecord, right: NormalizedRecord) -> bool:
    """仅按同领域种类、日文名或显式别名映射归并。"""
    if left.domain != right.domain or left.kind != right.kind:
        return False
    left_ja = _canonical_japanese_name(left)
    right_ja = _canonical_japanese_name(right)
    if left_ja is None or right_ja is None:
        return False
    return left_ja == right_ja


def _canonical_japanese_name(record: NormalizedRecord) -> str | None:
    """将日文别名映射到有来源证据的规范名称。"""
    if record.names.ja is None:
        return None
    japanese_name = normalized_key(record.names.ja)
    aliases = ALIASES.get((record.domain, record.kind), {})
    return aliases.get(japanese_name, japanese_name)


def _conflict_value(value: AttributeValue) -> ConflictValue:
    """将字段标量连同真实类型写入冲突报告。"""
    if value is None:
        return ConflictValue(type="null", value=None)
    if isinstance(value, bool):
        return ConflictValue(type="bool", value=value)
    if isinstance(value, int):
        return ConflictValue(type="int", value=value)
    if isinstance(value, float):
        return ConflictValue(type="float", value=value)
    return ConflictValue(type="str", value=value)


def _source_value_map(
    values: Sequence[tuple[NormalizedRecord, AttributeValue]],
) -> tuple[dict[str, ConflictValue], list[SourceRef]]:
    """为冲突值保留完整来源，并避免同目标键覆盖。"""
    result: dict[str, ConflictValue] = {}
    source_refs: list[SourceRef] = []
    for record, value in values:
        for source_ref in record.source_refs:
            key = (
                f"{source_ref.source_id}:{source_ref.target_id}:"
                f"{source_ref.table_index}:{source_ref.row_index}"
            )
            result[key] = _conflict_value(value)
            source_refs.append(source_ref)
    return result, source_refs


def _equal_values(values: Sequence[AttributeValue]) -> bool:
    """严格比较字段类型和值，避免布尔值与整数混同。"""
    first = values[0]
    return all(type(value) is type(first) and value == first for value in values[1:])


def _intrinsic_attribute_value(value: AttributeValue) -> dict[str, str | int | float | bool | None]:
    """保留属性类型并规范字符串，用于稳定实体指纹。"""
    if isinstance(value, str):
        return {"type": "str", "value": normalized_key(value)}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "none", "value": None}


def _ambiguous_record_id(record: NormalizedRecord, canonical_ja: str) -> str:
    """仅按实体内容为同源歧义记录生成稳定标识。"""
    fields = DISAMBIGUATION_FIELDS.get((record.domain, record.kind, canonical_ja))
    if fields is None:
        raise NormalizationError(
            f"{record.domain}:{record.kind}: missing disambiguation field rule"
        )
    if any(field not in record.attributes for field in fields):
        raise NormalizationError(
            f"{record.domain}:{record.kind}: missing disambiguation field value"
        )
    attributes = {field: _intrinsic_attribute_value(record.attributes[field]) for field in fields}
    fingerprint = json.dumps(
        {"ja": canonical_ja, "attributes": attributes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_record_id(record.domain, record.kind, fingerprint)


def _discriminator_key(
    record: NormalizedRecord,
    canonical_ja: str,
) -> tuple[tuple[str, str], ...]:
    """返回可稳定比较的人工确认身份字段。"""
    fields = DISAMBIGUATION_FIELDS.get((record.domain, record.kind, canonical_ja))
    if fields is None:
        raise NormalizationError(
            f"{record.domain}:{record.kind}: missing disambiguation field rule"
        )
    if any(field not in record.attributes for field in fields):
        raise NormalizationError(
            f"{record.domain}:{record.kind}: missing disambiguation field value"
        )
    return tuple(
        (
            field,
            json.dumps(
                _intrinsic_attribute_value(record.attributes[field]),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for field in fields
    )


def _unmatched_duplicate_id(record: NormalizedRecord) -> str:
    """为无日文名的重复标识使用不依赖来源的内容指纹。"""
    fingerprint = json.dumps(
        {
            "names": record.names.model_dump(),
            "attributes": {
                field: _intrinsic_attribute_value(record.attributes[field])
                for field in sorted(record.attributes)
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_record_id(record.domain, record.kind, fingerprint)


def _merge_records(
    records: Sequence[NormalizedRecord],
    canonical_ja: str | None = None,
) -> tuple[NormalizedRecord, list[FieldConflict]]:
    """合并同一已确认标识的记录，并产出字段冲突。"""
    ordered = sorted(records, key=_record_sort_key)
    primary = ordered[0]
    record_id = (
        stable_record_id(primary.domain, primary.kind, canonical_ja)
        if canonical_ja is not None
        else primary.id
    )
    conflict_values: list[FieldConflict] = []
    issues = [issue for record in ordered for issue in record.issues]

    name_values: dict[str, str | None] = {}
    for field in ("ja", "zh_09", "zh_099", "zh_reference"):
        if field == "ja" and canonical_ja is not None:
            name_values[field] = canonical_ja
            continue
        present = [(record, getattr(record.names, field)) for record in ordered]
        present = [(record, value) for record, value in present if value is not None]
        if not present:
            name_values[field] = None
            continue
        normalized_values = [normalized_key(value) for _, value in present]
        if len(set(normalized_values)) == 1:
            name_values[field] = min(
                (value for _, value in present),
                key=lambda value: (normalized_key(value), value),
            )
            continue
        value_map, source_refs = _source_value_map(present)
        conflict_field = f"names.{field}"
        conflict_values.append(
            FieldConflict(
                record_id=record_id,
                field=conflict_field,
                values=value_map,
                source_refs=source_refs,
            )
        )
        issues.append(f"conflict:{conflict_field}")
        name_values[field] = None

    aliases = {normalized_key(alias) for record in ordered for alias in record.names.aliases}
    if canonical_ja is not None:
        aliases.update(
            normalized_key(record.names.ja)
            for record in ordered
            if record.names.ja is not None and normalized_key(record.names.ja) != canonical_ja
        )
    names = NameSet(
        ja=name_values["ja"],
        zh_09=name_values["zh_09"],
        zh_099=name_values["zh_099"],
        zh_reference=name_values["zh_reference"],
        aliases=sorted(aliases),
    )
    attributes: dict[str, AttributeValue] = {}
    attribute_names = sorted({name for record in ordered for name in record.attributes})
    for field in attribute_names:
        present = [
            (record, record.attributes[field]) for record in ordered if field in record.attributes
        ]
        values = [value for _, value in present]
        if len(values) == 1 or _equal_values(values):
            attributes[field] = values[0]
            continue
        conflict_map, source_refs = _source_value_map(present)
        conflict_values.append(
            FieldConflict(
                record_id=record_id,
                field=field,
                values=conflict_map,
                source_refs=source_refs,
            )
        )
        issues.append(f"conflict:{field}")

    source_refs = [source_ref for record in ordered for source_ref in record.source_refs]
    source_spans = [source_span for record in ordered for source_span in record.source_spans]
    distinct_source_ids = {source_ref.source_id for source_ref in source_refs}
    if conflict_values:
        verification_status = VerificationStatus.CONFLICT
    elif len(distinct_source_ids) >= 2:
        verification_status = VerificationStatus.CROSS_CHECKED
    elif any(
        record.verification_status is VerificationStatus.COMPATIBLE_CANDIDATE for record in ordered
    ):
        verification_status = VerificationStatus.COMPATIBLE_CANDIDATE
    else:
        verification_status = VerificationStatus.SOURCE_ONLY
    return (
        NormalizedRecord(
            id=record_id,
            domain=primary.domain,
            kind=primary.kind,
            names=names,
            attributes=attributes,
            version_scope=[scope for record in ordered for scope in record.version_scope],
            verification_status=verification_status,
            source_refs=source_refs,
            source_spans=source_spans,
            issues=issues,
            asset_refs=[asset_ref for record in ordered for asset_ref in record.asset_refs],
        ),
        sorted(conflict_values, key=lambda conflict: (conflict.record_id, conflict.field)),
    )


def _merge_domain_records(
    records: Sequence[NormalizedRecord],
) -> tuple[list[NormalizedRecord], list[FieldConflict]]:
    """按可证明的名称关系归并同领域记录。"""
    groups: list[list[NormalizedRecord]] = []
    for record in sorted(records, key=_record_sort_key):
        for group in groups:
            if any(_records_match(record, existing) for existing in group):
                group.append(record)
                break
        else:
            groups.append([record])
    merged: list[NormalizedRecord] = []
    conflicts: list[FieldConflict] = []
    used_ids: set[str] = set()
    for group in groups:
        canonical_ja = _canonical_japanese_name(group[0])
        source_counts = {
            source_id: sum(
                source_ref.source_id == source_id
                for record in group
                for source_ref in record.source_refs
            )
            for source_id in {
                source_ref.source_id for record in group for source_ref in record.source_refs
            }
        }
        has_repeated_source = any(count > 1 for count in source_counts.values())
        has_entity_rule = (
            canonical_ja is not None
            and (group[0].domain, group[0].kind, canonical_ja) in DISAMBIGUATION_FIELDS
        )
        group_conflicts: list[FieldConflict]
        if has_entity_rule:
            assert canonical_ja is not None
            buckets: dict[tuple[tuple[str, str], ...], list[NormalizedRecord]] = {}
            for record in group:
                buckets.setdefault(_discriminator_key(record, canonical_ja), []).append(record)
            group_records = []
            group_conflicts = []
            for discriminator in sorted(buckets):
                bucket = buckets[discriminator]
                bucket_source_ids = [
                    source_ref.source_id for record in bucket for source_ref in record.source_refs
                ]
                if len(bucket_source_ids) != len(set(bucket_source_ids)):
                    raise NormalizationError(
                        f"{group[0].domain}:{group[0].kind}: disambiguation values are not unique"
                    )
                merged_record, bucket_conflicts = _merge_records(
                    bucket,
                    canonical_ja=canonical_ja,
                )
                record_id = _ambiguous_record_id(bucket[0], canonical_ja)
                merged_record = NormalizedRecord.model_validate(
                    {
                        **merged_record.model_dump(),
                        "id": record_id,
                        "issues": [
                            *merged_record.issues,
                            *(["ambiguous_same_source_name"] if has_repeated_source else []),
                        ],
                    }
                )
                group_records.append(merged_record)
                group_conflicts.extend(
                    FieldConflict.model_validate({**conflict.model_dump(), "record_id": record_id})
                    for conflict in bucket_conflicts
                )
        elif has_repeated_source:
            if canonical_ja is None:
                raise NormalizationError("ambiguous group requires a Japanese name")
            raise NormalizationError(
                f"{group[0].domain}:{group[0].kind}: missing disambiguation field rule"
            )
        else:
            record, group_conflicts = _merge_records(group, canonical_ja=canonical_ja)
            group_records = [record]
        for record in group_records:
            if record.id in used_ids:
                record_id = _unmatched_duplicate_id(record)
                if record_id in used_ids:
                    raise NormalizationError(
                        f"{record.domain}:{record.kind}: duplicate records have identical content"
                    )
                record = NormalizedRecord.model_validate({**record.model_dump(), "id": record_id})
                group_conflicts = [
                    FieldConflict.model_validate({**conflict.model_dump(), "record_id": record_id})
                    for conflict in group_conflicts
                ]
            used_ids.add(record.id)
            merged.append(record)
        conflicts.extend(group_conflicts)
    return sorted(merged, key=lambda record: record.id), sorted(
        conflicts, key=lambda conflict: (conflict.record_id, conflict.field)
    )


def _validate_snapshot_targets(snapshots: Sequence[CandidateSnapshot]) -> None:
    """拒绝缺失、重复或未声明的候选目标。"""
    for snapshot in snapshots:
        if snapshot.game != "mm2r":
            raise NormalizationError(
                f"{snapshot.target_id}: unexpected game {snapshot.game!r}; expected 'mm2r'"
            )
        if snapshot.target_version != "0.99":
            raise NormalizationError(
                f"{snapshot.target_id}: unexpected target_version {snapshot.target_version!r}; "
                "expected '0.99'"
            )
        if not snapshot.tables:
            raise NormalizationError(f"{snapshot.target_id}: snapshot has no tables")
        if any(not table.rows for table in snapshot.tables):
            raise NormalizationError(f"{snapshot.target_id}: snapshot has an empty table")
    target_ids = [snapshot.target_id for snapshot in snapshots]
    actual = set(target_ids)
    missing = sorted(_EXPECTED_TARGET_IDS - actual)
    duplicate = sorted({target_id for target_id in actual if target_ids.count(target_id) > 1})
    extra = sorted(actual - _EXPECTED_TARGET_IDS)
    if missing or duplicate or extra:
        raise NormalizationError(
            f"snapshot targets invalid; missing={missing}; duplicate={duplicate}; extra={extra}"
        )


def _validate_snapshot_spans(snapshot: CandidateSnapshot) -> None:
    """拒绝无法可靠关联到标准化行的跨列信息。"""
    has_merged_cells = any(table.merged_cells for table in snapshot.tables)
    if has_merged_cells and any("skipped row" in warning for warning in snapshot.warnings):
        raise NormalizationError(
            f"{snapshot.target_id}: merged cells cannot be safely linked after skipped row"
        )
    for table_index, table in enumerate(snapshot.tables):
        unmatched = [
            merged_cell.row_index
            for merged_cell in table.merged_cells
            if merged_cell.row_index - 2 not in range(len(table.rows))
        ]
        if unmatched:
            raise NormalizationError(
                f"{snapshot.target_id}: table {table_index} has unmatched merged cells {unmatched}"
            )


def normalize_snapshots(snapshots: Sequence[CandidateSnapshot]) -> NormalizationResult:
    """标准化完整候选快照集合并汇总可追溯冲突。"""
    _validate_snapshot_targets(snapshots)
    records_by_domain: dict[Domain, list[NormalizedRecord]] = {
        "equipment": [],
        "items": [],
        "quests": [],
        "jobs": [],
        "skills": [],
    }
    for snapshot in sorted(snapshots, key=_snapshot_sort_key):
        _validate_snapshot_spans(snapshot)
        for table_index, table in enumerate(snapshot.tables):
            for row_index, row in enumerate(table.rows):
                source_ref = SourceRef(
                    source_id=snapshot.source_id,
                    target_id=snapshot.target_id,
                    source_url=snapshot.source_url,
                    retrieved_at=snapshot.retrieved_at,
                    content_hash=snapshot.content_hash,
                    table_index=table_index,
                    row_index=row_index,
                )
                record = normalize_row(
                    snapshot.target_id,
                    table.section,
                    table.headers,
                    row,
                    source_ref,
                )
                source_spans = [
                    SourceSpan(
                        source_id=snapshot.source_id,
                        target_id=snapshot.target_id,
                        table_index=table_index,
                        row_index=row_index,
                        start_header=merged_cell.start_header,
                        end_header=merged_cell.end_header,
                        value=merged_cell.value,
                    )
                    for merged_cell in table.merged_cells
                    if merged_cell.row_index == source_ref.row_index + 2
                ]
                if source_spans:
                    record = NormalizedRecord.model_validate(
                        {
                            **record.model_dump(),
                            "source_spans": source_spans,
                            "issues": [*record.issues, "source_merged_cell"],
                        }
                    )
                records_by_domain[record.domain].append(record)

    bundles: dict[str, NormalizedBundle] = {}
    all_conflicts: list[FieldConflict] = []
    for domain in ("equipment", "items", "quests", "jobs", "skills"):
        records, conflicts = _merge_domain_records(records_by_domain[domain])
        bundles[domain] = NormalizedBundle(
            domain=domain,
            source_hashes=[
                source_ref.content_hash for record in records for source_ref in record.source_refs
            ],
            records=records,
        )
        all_conflicts.extend(conflicts)
    return NormalizationResult(
        bundles=bundles,
        conflicts=ConflictBundle(
            conflicts=sorted(
                all_conflicts,
                key=lambda conflict: (conflict.record_id, conflict.field),
            )
        ),
    )
