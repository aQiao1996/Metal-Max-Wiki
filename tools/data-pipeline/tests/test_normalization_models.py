"""标准化领域契约的行为测试。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from mmwiki_data.models import VerificationStatus
from mmwiki_data.normalization_models import (
    ConflictValue,
    FieldConflict,
    NameSet,
    NormalizedBundle,
    NormalizedRecord,
    SourceRef,
    SourceSpan,
)


def source_ref(**changes: object) -> dict[str, object]:
    """构造可用于标准化记录的来源定位。"""
    value: dict[str, object] = {
        "source_id": "official-guide",
        "target_id": "equipment-table",
        "source_url": "https://example.com/equipment",
        "retrieved_at": datetime.fromisoformat("2026-09-21T12:00:00+08:00"),
        "content_hash": "sha256:" + "a" * 64,
        "table_index": 0,
        "row_index": 0,
    }
    value.update(changes)
    return value


def record(**changes: object) -> dict[str, object]:
    """构造有效的标准化中间记录。"""
    value: dict[str, object] = {
        "id": "equipment-0123456789",
        "domain": "equipment",
        "kind": "tank_cannon",
        "names": {"ja": "\u3062\u3046\u3058\u3093\u307b\u3046"},
        "attributes": {"attack": 42},
        "version_scope": ["0.99"],
        "verification_status": VerificationStatus.SOURCE_ONLY,
        "source_refs": [source_ref()],
        "issues": [],
        "asset_refs": [],
    }
    value.update(changes)
    return value


def test_interim_record_cannot_claim_verified_0_99() -> None:
    with pytest.raises(ValidationError, match="interim record cannot be verified_0_99"):
        NormalizedRecord.model_validate(
            record(verification_status=VerificationStatus.VERIFIED_0_99)
        )


def test_source_ref_validates_locator_and_sha256_hash() -> None:
    valid = SourceRef.model_validate(source_ref())

    assert valid.table_index == 0
    with pytest.raises(ValidationError):
        SourceRef.model_validate(source_ref(content_hash="sha256:not-a-hash"))
    with pytest.raises(ValidationError):
        SourceRef.model_validate(source_ref(source_url="file:///tmp/source.html"))
    with pytest.raises(ValidationError):
        SourceRef.model_validate(source_ref(row_index=-1))


def test_normalized_record_requires_at_least_one_name() -> None:
    with pytest.raises(ValidationError, match="at least one name is required"):
        NormalizedRecord.model_validate(record(names=NameSet()))


def test_nameset_rejects_original_duplicate_aliases() -> None:
    with pytest.raises(ValidationError, match="duplicate alias"):
        NameSet.model_validate(
            {"ja": "\u3057\u3087\u307c\u3046\u3057\u3083", "aliases": ["A", "A"]}
        )


def test_nameset_rejects_normalized_duplicate_aliases() -> None:
    with pytest.raises(ValidationError, match="duplicate alias"):
        NameSet.model_validate(
            {"ja": "\u3057\u3087\u307c\u3046\u3057\u3083", "aliases": [" \uff21", "A"]}
        )


def test_nameset_normalizes_and_sorts_distinct_aliases() -> None:
    names = NameSet.model_validate(
        {"ja": "\u3057\u3087\u307c\u3046\u3057\u3083", "aliases": [" \uff22", "\uff21 "]}
    )

    assert names.aliases == ["A", "B"]


def test_nameset_normalizes_primary_names_and_rejects_blank_values() -> None:
    names = NameSet.model_validate({"ja": "　Ａ ", "zh_09": "　汉译　"})

    assert names.ja == "A"
    assert names.zh_09 == "汉译"
    with pytest.raises(ValidationError, match="at least one name"):
        NameSet.model_validate({"ja": "　 "})


def test_normalized_record_normalizes_collection_fields() -> None:
    earlier = source_ref(source_id="a-source", target_id="a-target")
    later = source_ref(source_id="z-source", target_id="z-target")

    normalized = NormalizedRecord.model_validate(
        record(
            source_refs=[later, earlier, later],
            version_scope=["1.00", "0.99", "1.00"],
            issues=["z-issue", "a-issue", "z-issue"],
            asset_refs=["z-asset", "a-asset", "z-asset"],
        )
    )

    assert [ref.source_id for ref in normalized.source_refs] == ["a-source", "z-source"]
    assert normalized.version_scope == ["0.99", "1.00"]
    assert normalized.issues == ["a-issue", "z-issue"]
    assert normalized.asset_refs == ["a-asset", "z-asset"]


def test_normalized_record_rejects_source_spans_without_matching_source_refs() -> None:
    span = {
        "source_id": "other-source",
        "target_id": "other-target",
        "table_index": 0,
        "row_index": 0,
        "start_header": "名称",
        "end_header": "汉译",
        "value": "同一单元格",
    }

    with pytest.raises(ValidationError, match="source span"):
        NormalizedRecord.model_validate(record(source_spans=[span]))


def test_source_span_is_strict_and_normalized_with_records() -> None:
    earlier = {
        "source_id": "a-source",
        "target_id": "a-target",
        "table_index": 0,
        "row_index": 0,
        "start_header": "名称",
        "end_header": "汉译",
        "value": "同一单元格",
    }
    later = {**earlier, "source_id": "z-source"}

    span = SourceSpan.model_validate(earlier)
    normalized = NormalizedRecord.model_validate(
        record(
            source_refs=[
                source_ref(source_id="a-source", target_id="a-target"),
                source_ref(source_id="z-source", target_id="a-target"),
            ],
            source_spans=[later, earlier, later],
        )
    )

    assert span.value == "同一单元格"
    assert [item.source_id for item in normalized.source_spans] == ["a-source", "z-source"]
    with pytest.raises(ValidationError):
        SourceSpan.model_validate({**earlier, "start_header": ""})
    with pytest.raises(ValidationError):
        SourceSpan.model_validate({**earlier, "row_index": -1})


def test_normalized_bundle_rejects_duplicate_record_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate normalized record id"):
        NormalizedBundle.model_validate(
            {
                "domain": "equipment",
                "source_hashes": ["sha256:" + "a" * 64],
                "records": [record(), record()],
            }
        )


def test_normalized_bundle_normalizes_and_validates_source_hashes() -> None:
    bundle = NormalizedBundle.model_validate(
        {
            "domain": "equipment",
            "source_hashes": ["sha256:" + "a" * 64],
            "records": [record()],
        }
    )

    assert bundle.source_hashes == ["sha256:" + "a" * 64]
    with pytest.raises(ValidationError):
        NormalizedBundle.model_validate(
            {"domain": "equipment", "source_hashes": ["invalid"], "records": [record()]}
        )
    with pytest.raises(ValidationError, match="source hashes"):
        NormalizedBundle.model_validate(
            {"domain": "equipment", "source_hashes": ["sha256:" + "b" * 64], "records": [record()]}
        )
    with pytest.raises(ValidationError, match="record domain"):
        NormalizedBundle.model_validate(
            {"domain": "items", "source_hashes": ["sha256:" + "a" * 64], "records": [record()]}
        )


def test_normalized_bundle_deduplicates_unsorted_hashes_that_match_refs() -> None:
    second = record(
        id="equipment-abcdef0123",
        source_refs=[
            source_ref(
                source_id="second-source",
                target_id="second-target",
                content_hash="sha256:" + "b" * 64,
            )
        ],
    )

    bundle = NormalizedBundle.model_validate(
        {
            "domain": "equipment",
            "source_hashes": ["sha256:" + "b" * 64, "sha256:" + "a" * 64, "sha256:" + "b" * 64],
            "records": [record(), second],
        }
    )

    assert bundle.source_hashes == ["sha256:" + "a" * 64, "sha256:" + "b" * 64]


def test_field_conflict_requires_exact_nonempty_locator_values() -> None:
    first = SourceRef.model_validate(source_ref(source_id="a-source", target_id="a-target"))
    second = SourceRef.model_validate(
        source_ref(source_id="b-source", target_id="b-target", row_index=1)
    )
    values = {
        "a-source:a-target:0:0": ConflictValue(type="int", value=10),
        "b-source:b-target:0:1": ConflictValue(type="int", value=20),
    }

    conflict = FieldConflict(
        record_id="equipment-0123456789",
        field="attack",
        values=values,
        source_refs=[second, first],
    )

    assert {key: value.model_dump() for key, value in conflict.values.items()} == {
        "a-source:a-target:0:0": {"type": "int", "value": 10},
        "b-source:b-target:0:1": {"type": "int", "value": 20},
    }
    with pytest.raises(ValidationError, match="values"):
        FieldConflict(
            record_id="equipment-0123456789",
            field="attack",
            values={},
            source_refs=[first, second],
        )
    with pytest.raises(ValidationError, match="locator"):
        FieldConflict(
            record_id="equipment-0123456789",
            field="attack",
            values={
                "a-source:a-target": ConflictValue(type="int", value=10),
                "b-source:b-target": ConflictValue(type="int", value=20),
            },
            source_refs=[first, second],
        )


@pytest.mark.parametrize(
    ("value_type", "value"),
    [("str", "1"), ("int", 1), ("float", 1.5), ("bool", True), ("null", None)],
)
def test_conflict_value_preserves_the_scalar_type(value_type: str, value: object) -> None:
    conflict_value = ConflictValue.model_validate({"type": value_type, "value": value})

    assert conflict_value.type == value_type
    assert conflict_value.value == value


@pytest.mark.parametrize(
    ("value_type", "value"),
    [("int", "1"), ("str", 1), ("bool", 1), ("null", False)],
)
def test_conflict_value_rejects_mismatched_scalar_type(value_type: str, value: object) -> None:
    with pytest.raises(ValidationError, match="type"):
        ConflictValue.model_validate({"type": value_type, "value": value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_conflict_value_rejects_nonfinite_floats(value: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        ConflictValue.model_validate({"type": "float", "value": value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_normalized_record_rejects_nonfinite_attribute_floats(value: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        NormalizedRecord.model_validate(record(attributes={"attack": value}))


def test_field_conflict_requires_two_distinct_typed_values() -> None:
    first = SourceRef.model_validate(source_ref(source_id="a-source", target_id="a-target"))
    second = SourceRef.model_validate(
        source_ref(source_id="b-source", target_id="b-target", row_index=1)
    )

    with pytest.raises(ValidationError, match="distinct"):
        FieldConflict(
            record_id="equipment-0123456789",
            field="attack",
            values={
                "a-source:a-target:0:0": ConflictValue(type="int", value=10),
                "b-source:b-target:0:1": ConflictValue(type="int", value=10),
            },
            source_refs=[first, second],
        )
