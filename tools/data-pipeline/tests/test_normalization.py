"""固定来源字段映射和稳定标识的行为测试。"""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import HttpUrl

from mmwiki_data.models import CandidateSnapshot, MergedCell, VerificationStatus
from mmwiki_data.normalization import (
    ALIASES,
    DISAMBIGUATION_FIELDS,
    NormalizationError,
    NormalizationResult,
    _merge_domain_records,
    _merge_records,
    compact_attributes,
    expect_headers,
    normalize_row,
    normalize_snapshots,
    normalized_key,
    parse_optional_int,
    stable_record_id,
)
from mmwiki_data.normalization_models import ConflictBundle, NameSet, NormalizedRecord, SourceRef

SHELL_HEADERS = "名称 0.9汉化 効果 材料1 材料2 材料3 価格(G) 備考".split()
WEAPON_HEADERS = "汉译 日文 攻击 范围 属性 追加 ☆数 猎 机 兵 护 摔 艺 价格 入手 备注".split()
CANNON_HEADERS = "汉译 名称 攻击 范围 属性 守备 重量(t) 弹仓 特殊炮弹 价格(G) 稀有度".split()
QUEST_HEADERS = "任务名称 汉译名 任务接受场所 经验值 有名度 报酬 备注".split()
LOVE_HEADERS = "L O V E 地图上使用效果 战斗中使用效果".split()
SKILL_HEADERS = "No スキル 職業 Lv 種類 説明".split()
EXPECTED_TARGETS = {
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


def make_ref(target_id: str) -> SourceRef:
    return SourceRef(
        source_id="dqff-mm2r" if target_id.startswith("dqff-") else "zzjb-mm2r",
        target_id=target_id,
        source_url=HttpUrl("https://example.com/table"),
        retrieved_at=datetime(2026, 9, 21, tzinfo=UTC),
        content_hash="sha256:" + "a" * 64,
        table_index=0,
        row_index=1,
    )


def mapped(
    target_id: str, headers: list[str], values: dict[str, str], section: str = "一览"
) -> NormalizedRecord:
    row = dict.fromkeys(headers, "") | values
    return normalize_row(target_id, section, headers, row, make_ref(target_id))


def actual_snapshots() -> list[CandidateSnapshot]:
    """读取固定的 17 份候选快照。"""
    root = Path(__file__).parents[3] / "data/raw/mm2r/0.99/candidates"
    return [
        CandidateSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*.json"))
    ]


def mergeable_record(
    source_id: str,
    target_id: str,
    row_index: int,
    *,
    ja: str = "りゅう弾",
    zh_09: str | None = None,
    attributes: dict[str, str | int | float | bool | None] | None = None,
) -> NormalizedRecord:
    """构造可直接检验归并规则的来源记录。"""
    digest_char = "a" if source_id.endswith("a") else "b"
    return NormalizedRecord(
        id=stable_record_id("items", "special_shell", ja),
        domain="items",
        kind="special_shell",
        names=NameSet(ja=ja, zh_09=zh_09),
        attributes={} if attributes is None else attributes,
        version_scope=["mm2r-jp"],
        verification_status=VerificationStatus.COMPATIBLE_CANDIDATE,
        source_refs=[
            SourceRef(
                source_id=source_id,
                target_id=target_id,
                source_url=HttpUrl(f"https://example.com/{target_id}"),
                retrieved_at=datetime(2026, 9, 21, tzinfo=UTC),
                content_hash="sha256:" + digest_char * 64,
                table_index=0,
                row_index=row_index,
            )
        ],
    )


def with_source_metadata(
    record: NormalizedRecord,
    *,
    retrieved_at: datetime | None = None,
    content_hash: str | None = None,
    source_url: str | None = None,
    row_index: int | None = None,
) -> NormalizedRecord:
    """以重新校验的方式替换来源元数据。"""
    source_ref = record.source_refs[0]
    values = source_ref.model_dump()
    if retrieved_at is not None:
        values["retrieved_at"] = retrieved_at
    if content_hash is not None:
        values["content_hash"] = content_hash
    if source_url is not None:
        values["source_url"] = source_url
    if row_index is not None:
        values["row_index"] = row_index
    return NormalizedRecord.model_validate({**record.model_dump(), "source_refs": [values]})


def ambiguous_cannon(
    attack: str,
    row_index: int,
    *,
    ja: str = "LOVEマシン",
    source_id: str = "source-a",
    target_id: str = "target-a",
    zh_09: str | None = None,
    zh_099: str | None = None,
    aliases: list[str] | None = None,
    weight: str = "1",
    notes: str = "备注",
) -> NormalizedRecord:
    """构造同源主炮歧义变体。"""
    return NormalizedRecord(
        id=stable_record_id("equipment", "main_cannon", ja),
        domain="equipment",
        kind="main_cannon",
        names=NameSet(
            ja=ja,
            zh_09=zh_09,
            zh_099=zh_099,
            aliases=[] if aliases is None else aliases,
        ),
        attributes={"attack_raw": attack, "weight_raw": weight, "notes_raw": notes},
        version_scope=["mm2r-jp"],
        verification_status=VerificationStatus.COMPATIBLE_CANDIDATE,
        source_refs=[
            SourceRef(
                source_id=source_id,
                target_id=target_id,
                source_url=HttpUrl("https://example.com/cannons"),
                retrieved_at=datetime(2026, 9, 21, tzinfo=UTC),
                content_hash="sha256:" + "a" * 64,
                table_index=0,
                row_index=row_index,
            )
        ],
    )


def test_shell_preserves_names_effect_and_provenance() -> None:
    record = mapped(
        "special-shells",
        SHELL_HEADERS,
        {"名称": "りゅう弾", "0.9汉化": "榴弹", "効果": "通常弾の50%ダメージ"},
    )

    assert record.names.ja == "りゅう弾"
    assert record.names.zh_09 == "榴弹"
    assert record.names.zh_099 is None
    assert record.attributes["effect_raw"] == "通常弾の50%ダメージ"
    assert record.source_refs == [make_ref("special-shells")]
    assert record.version_scope == ["mm2r-jp", "zh-patch-0.9-family"]
    assert record.verification_status is VerificationStatus.COMPATIBLE_CANDIDATE


@pytest.mark.parametrize(
    "category", ["field", "art", "vehicle", "auto", "human", "repair", "healing"]
)
def test_skill_targets_keep_japanese_and_source_category(category: str) -> None:
    target_id = f"dqff-skills-{category}"
    headers = SKILL_HEADERS if category in {"field", "art"} else [*SKILL_HEADERS, "対象"]
    record = mapped(
        target_id,
        headers,
        {
            "No": "1",
            "スキル": "砲弾ゲージツ",
            "職業": "アーチスト",
            "Lv": "5",
            "種類": "ゲージツ",
            "説明": "特殊砲弾、素材を作成する",
        },
    )

    assert record.names.ja == "砲弾ゲージツ"
    assert record.names.zh_09 is None
    assert record.names.zh_099 is None
    assert record.attributes["skill_category"] == "ゲージツ"
    assert record.attributes["source_target"] == target_id
    assert record.attributes["level"] == 5
    assert record.attributes["level_raw"] == "5"
    assert record.attributes["description_raw"] == "特殊砲弾、素材を作成する"
    assert record.version_scope == ["mm2r-jp"]
    assert record.verification_status is VerificationStatus.SOURCE_ONLY


def test_ids_use_normalized_key_and_defined_digest() -> None:
    digest = sha256(b"items\0special_shell\0ABC").hexdigest()[:10]
    assert stable_record_id("items", "special_shell", " ＡＢＣ ") == f"special-shell-{digest}"
    assert stable_record_id("items", "special_shell", "ABC") == f"special-shell-{digest}"
    assert normalized_key(" ＡＢＣ ") == "ABC"
    with pytest.raises(NormalizationError, match="canonical"):
        stable_record_id("items", "special_shell", "　 ")


def test_missing_japanese_name_is_explicit() -> None:
    record = mapped("human-equipment", WEAPON_HEADERS, {"汉译": "弹弓", "攻击": "5"})
    assert record.names.ja is None
    assert record.names.zh_09 == "弹弓"
    assert record.names.zh_099 is None
    assert record.issues == ["missing_japanese_name"]
    assert record.kind == "human_weapon"


def test_quest_preserves_bilingual_names_and_rewards() -> None:
    record = mapped(
        "quests",
        QUEST_HEADERS,
        {
            "任务名称": "マリアよ、安らかに眠れ",
            "汉译名": "玛丽亚，安息吧",
            "经验值": "100",
            "有名度": "5",
            "报酬": "200G",
        },
    )
    assert record.names.ja == "マリアよ、安らかに眠れ"
    assert record.names.zh_09 == "玛丽亚,安息吧"
    assert record.names.zh_099 is None
    assert record.attributes["experience"] == 100
    assert record.attributes["experience_raw"] == "100"
    assert record.attributes["reward_raw"] == "200G"


def test_love_recipe_uses_complete_code_without_invented_names() -> None:
    record = mapped(
        "human-items",
        LOVE_HEADERS,
        {
            "L": "1",
            "O": "2",
            "V": "3",
            "E": "4",
            "地图上使用效果": "使用不可",
            "战斗中使用效果": "体力を約300回復、自分のみ",
        },
        "LOVE机器组合表",
    )
    assert record.names.aliases == ["1-2-3-4"]
    assert record.names.ja is None
    assert record.names.zh_09 is None
    assert record.names.zh_099 is None
    assert "missing_japanese_name" in record.issues
    assert record.id == stable_record_id("items", "love_machine_recipe", "1-2-3-4")
    assert record.attributes["battle_effect_raw"] == "体力を約300回復、自分のみ"
    assert record.attributes["l_raw"] == "1"
    assert record.attributes["l"] == 1
    with pytest.raises(NormalizationError, match="LOVE"):
        mapped("human-items", LOVE_HEADERS, {"L": "1", "O": "2", "V": "3"})


def test_ic_chip_code_is_language_neutral() -> None:
    record = mapped("human-items", ["种类", "场所"], {"种类": "L-1", "场所": "沙滩"})
    assert record.kind == "ic_chip_location"
    assert record.names.ja == "L-1"
    assert record.names.zh_09 is None
    assert record.names.zh_099 is None
    assert record.attributes["location_raw"] == "沙滩"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("65", 65),
        ("0", 0),
        ("001", 1),
        ("*65", None),
        ("65G", None),
        ("6.66", None),
        ("20 男", None),
        ("-1", None),
        ("+65", None),
        ("1,000", None),
        ("", None),
        (" 65 ", 65),
        ("６５", 65),
    ],
)
def test_parse_optional_int_is_unambiguous(raw: str, expected: int | None) -> None:
    assert parse_optional_int(raw) == expected


@pytest.mark.parametrize("raw", [" 65 ", "６５"])
def test_normalized_numbers_keep_original_raw_value(raw: str) -> None:
    record = mapped("human-equipment", WEAPON_HEADERS, {"汉译": "弹弓", "攻击": raw})
    assert record.attributes["attack"] == 65
    assert record.attributes["attack_raw"] == raw


def test_numeric_fields_retain_raw_units_and_stars() -> None:
    record = mapped(
        "tank-parts",
        CANNON_HEADERS,
        {
            "名称": "朽ちかけた大砲",
            "汉译": "腐烂的大炮",
            "攻击": "120",
            "守备": "5",
            "重量(t)": "6.66",
            "弹仓": "8",
            "价格(G)": "*65",
        },
        "主炮",
    )
    assert record.kind == "main_cannon"
    assert record.attributes["attack"] == 120
    assert record.attributes["attack_raw"] == "120"
    assert record.attributes["price_raw"] == "*65"
    assert "price" not in record.attributes
    assert record.attributes["weight_raw"] == "6.66"
    assert "weight" not in record.attributes


def test_compact_attributes_preserves_values_and_types() -> None:
    result = compact_attributes(
        {
            "empty": "",
            "null": None,
            "zero": 0,
            "false": False,
            "float": 1.5,
            "space": " ",
            "text": "*65",
        }
    )
    assert result == {"zero": 0, "false": False, "float": 1.5, "space": " ", "text": "*65"}
    assert type(result["zero"]) is int
    assert type(result["false"]) is bool
    assert type(result["float"]) is float


@pytest.mark.parametrize(
    "target_id,kind",
    [
        ("dqff-human-items", "human_item"),
        ("dqff-tank-items", "tank_item"),
        ("dqff-special-shells", "special_shell"),
    ],
)
def test_dqff_item_targets(target_id: str, kind: str) -> None:
    record = mapped(
        target_id,
        "No アイテム 種類 説明 対象".split(),
        {
            "No": "1",
            "アイテム": "りゅう弾",
            "種類": "特殊砲弾",
            "説明": "50%ダメージ",
        },
    )
    assert record.kind == kind
    assert record.names.ja == "りゅう弾"
    assert record.names.zh_09 is None
    assert record.attributes["number_raw"] == "1"
    assert record.attributes["number"] == 1


def test_jobs_and_tank_tools() -> None:
    job = mapped("dqff-jobs", ["No", "職業"], {"No": "1", "職業": "ハンター"})
    assert job.domain == "jobs"
    assert job.kind == "job"
    assert job.names.ja == "ハンター"
    tool = mapped(
        "tank-tools",
        "名称 0.9汉化 效果 对象 消费 重量(t) 价格(G) 星数".split(),
        {
            "名称": "タイルパック100",
            "0.9汉化": "装甲包100",
            "对象": "全体",
            "重量(t)": "0",
            "价格(G)": "50",
        },
    )
    assert tool.kind == "tank_item"
    assert tool.attributes["weight"] == 0
    assert tool.attributes["price_raw"] == "50"
    assert tool.attributes["usage_context_zh_09_raw"] == "全体"
    assert "target_raw" not in tool.attributes


@pytest.mark.parametrize("headers", [SHELL_HEADERS + ["未知列"], SHELL_HEADERS[1:]])
def test_unknown_or_missing_headers_fail_with_context(headers: list[str]) -> None:
    with pytest.raises(NormalizationError) as error:
        mapped("special-shells", headers, {"名称": "りゅう弾"})
    assert "special-shells" in str(error.value)
    assert str(headers) in str(error.value)


def test_expect_headers_rejects_duplicates_and_accepts_order_changes() -> None:
    expect_headers("test", ["b", "a"], {"a", "b"})
    with pytest.raises(NormalizationError):
        expect_headers("test", ["a", "a", "b"], {"a", "b"})


def test_dispatcher_rejects_unknown_targets_sections_and_rows() -> None:
    with pytest.raises(NormalizationError, match="unknown"):
        mapped("unknown", ["名称"], {"名称": "a"})
    with pytest.raises(NormalizationError, match="tank-parts"):
        mapped("tank-parts", CANNON_HEADERS, {"名称": "a"}, "引擎")
    with pytest.raises(NormalizationError, match="special-shells"):
        mapped("special-shells", SHELL_HEADERS, {"名称": "a", "未知": "x"})


def test_dispatcher_rejects_mismatched_source_target() -> None:
    row = dict.fromkeys(SHELL_HEADERS, "") | {"名称": "りゅう弾"}
    with pytest.raises(NormalizationError) as error:
        normalize_row("special-shells", "一览", SHELL_HEADERS, row, make_ref("tank-tools"))
    assert "special-shells" in str(error.value)
    assert "tank-tools" in str(error.value)


def test_normalize_snapshots_rejects_missing_duplicate_and_extra_targets() -> None:
    snapshots = actual_snapshots()
    extra = snapshots[0].model_copy(update={"target_id": "unexpected-target"})
    without_tank_parts = [snapshot for snapshot in snapshots if snapshot.target_id != "tank-parts"]

    with pytest.raises(NormalizationError) as error:
        normalize_snapshots([*without_tank_parts, snapshots[0], extra])

    message = str(error.value)
    assert "missing" in message
    assert "duplicate" in message
    assert "extra" in message
    assert "tank-parts" in message
    assert "unexpected-target" in message


def test_normalize_snapshots_consumes_real_rows_and_merged_source_spans() -> None:
    snapshots = actual_snapshots()
    assert {snapshot.target_id for snapshot in snapshots} == EXPECTED_TARGETS

    result = normalize_snapshots(snapshots)

    assert isinstance(result, NormalizationResult)
    assert set(result.bundles) == {"equipment", "items", "quests", "jobs", "skills"}
    assert (
        sum(
            len(record.source_refs)
            for bundle in result.bundles.values()
            for record in bundle.records
        )
        == 527
    )
    spans = [
        span
        for bundle in result.bundles.values()
        for record in bundle.records
        for span in record.source_spans
    ]
    assert len(spans) == 37
    assert all(
        record.verification_status is not VerificationStatus.VERIFIED_0_99
        for bundle in result.bundles.values()
        for record in bundle.records
    )
    tank_part_spans = [span for span in spans if span.target_id == "tank-parts"]
    assert len(tank_part_spans) == 1
    love_spans = [span for span in spans if span.target_id == "human-items"]
    assert len(love_spans) == 36
    assert all(span.value for span in spans)
    love_record = next(
        record
        for record in result.bundles["items"].records
        if any(span.target_id == "human-items" for span in record.source_spans)
    )
    love_span = love_record.source_spans[0]
    assert love_span.end_header == "战斗中使用效果"
    assert love_record.attributes["field_effect_raw"] == love_span.value
    assert "battle_effect_raw" not in love_record.attributes


def test_normalize_snapshots_is_deterministic_when_snapshot_order_is_reversed() -> None:
    snapshots = actual_snapshots()

    forward = normalize_snapshots(snapshots)
    backward = normalize_snapshots(list(reversed(snapshots)))

    assert {key: value.model_dump() for key, value in forward.bundles.items()} == {
        key: value.model_dump() for key, value in backward.bundles.items()
    }
    assert forward.conflicts.model_dump() == backward.conflicts.model_dump()


def test_real_ryudan_merges_two_sources_as_cross_checked() -> None:
    result = normalize_snapshots(actual_snapshots())

    ryuudan = next(
        record
        for record in result.bundles["items"].records
        if record.kind == "special_shell" and record.names.ja == "りゅう弾"
    )

    assert len(ryuudan.source_refs) == 2
    assert ryuudan.verification_status is VerificationStatus.CROSS_CHECKED


def test_similar_japanese_names_are_not_merged_without_explicit_aliases() -> None:
    records, conflicts = _merge_domain_records(
        [
            mergeable_record("source-a", "target-a", 0, ja="りゅう弾"),
            mergeable_record("source-b", "target-b", 0, ja="りゅう砲"),
        ]
    )

    assert len(records) == 2
    assert all(len(record.source_refs) == 1 for record in records)
    assert conflicts == []


def test_conflicting_shared_attribute_is_removed_and_reported() -> None:
    merged, conflicts = _merge_records(
        [
            mergeable_record("source-a", "target-a", 0, attributes={"price": 10}),
            mergeable_record("source-b", "target-b", 1, attributes={"price": 20}),
        ]
    )

    assert "price" not in merged.attributes
    assert merged.verification_status is VerificationStatus.CONFLICT
    assert merged.issues == ["conflict:price"]
    reported_conflicts = [
        (conflict.field, {key: value.model_dump() for key, value in conflict.values.items()})
        for conflict in conflicts
    ]
    assert reported_conflicts == [
        (
            "price",
            {
                "source-a:target-a:0:0": {"type": "int", "value": 10},
                "source-b:target-b:0:1": {"type": "int", "value": 20},
            },
        )
    ]


def test_identical_shared_attribute_is_cross_checked() -> None:
    merged, conflicts = _merge_records(
        [
            mergeable_record("source-a", "target-a", 0, attributes={"price": 10}),
            mergeable_record("source-b", "target-b", 1, attributes={"price": 10}),
        ]
    )

    assert merged.attributes["price"] == 10
    assert merged.verification_status is VerificationStatus.CROSS_CHECKED
    assert conflicts == []


def test_conflicting_values_keep_distinct_scalar_types() -> None:
    merged, conflicts = _merge_records(
        [
            mergeable_record("source-a", "target-a", 0, attributes={"number": 1}),
            mergeable_record("source-b", "target-b", 1, attributes={"number": "1"}),
        ]
    )

    assert "number" not in merged.attributes
    bundle = ConflictBundle(conflicts=conflicts)
    assert {key: value.model_dump() for key, value in bundle.conflicts[0].values.items()} == {
        "source-a:target-a:0:0": {"type": "int", "value": 1},
        "source-b:target-b:0:1": {"type": "str", "value": "1"},
    }


def test_conflicting_translations_are_removed_and_reported_as_name_conflicts() -> None:
    merged, conflicts = _merge_records(
        [
            mergeable_record("source-a", "target-a", 0, zh_09="榴弹"),
            mergeable_record("source-b", "target-b", 1, zh_09="龙弹"),
        ]
    )

    assert merged.names.zh_09 is None
    assert merged.issues == ["conflict:names.zh_09"]
    assert [conflict.field for conflict in conflicts] == ["names.zh_09"]


def test_same_source_same_japanese_name_stays_separate_and_is_marked_ambiguous() -> None:
    records, conflicts = _merge_domain_records(
        [
            ambiguous_cannon("10", 0),
            ambiguous_cannon("20", 1),
            ambiguous_cannon("30", 2),
        ]
    )

    assert len(records) == 3
    assert all(len(record.source_refs) == 1 for record in records)
    assert all(record.issues == ["ambiguous_same_source_name"] for record in records)
    assert conflicts == []


def test_ambiguous_names_bucket_by_discriminator_before_cross_source_merging() -> None:
    records, conflicts = _merge_domain_records(
        [
            ambiguous_cannon("555", 0, source_id="source-a", target_id="target-a"),
            ambiguous_cannon("666", 1, source_id="source-a", target_id="target-a"),
            ambiguous_cannon("555", 0, source_id="source-b", target_id="target-b"),
        ]
    )

    by_attack = {record.attributes["attack_raw"]: record for record in records}
    assert set(by_attack) == {"555", "666"}
    assert len(by_attack["555"].source_refs) == 2
    assert by_attack["555"].verification_status is VerificationStatus.CROSS_CHECKED
    assert len(by_attack["666"].source_refs) == 1
    assert by_attack["666"].verification_status is VerificationStatus.COMPATIBLE_CANDIDATE
    assert all(record.issues == ["ambiguous_same_source_name"] for record in records)
    assert conflicts == []
    reversed_records, _ = _merge_domain_records(
        [
            ambiguous_cannon("555", 0, source_id="source-b", target_id="target-b"),
            ambiguous_cannon("666", 1, source_id="source-a", target_id="target-a"),
            ambiguous_cannon("555", 0, source_id="source-a", target_id="target-a"),
        ]
    )
    assert [record.model_dump() for record in records] == [
        record.model_dump() for record in reversed_records
    ]


def test_love_machine_discriminator_buckets_cross_sources_without_same_source_repeats() -> None:
    records, conflicts = _merge_domain_records(
        [
            ambiguous_cannon("555", 0, source_id="source-a", target_id="target-a"),
            ambiguous_cannon("666", 0, source_id="source-b", target_id="target-b"),
        ]
    )

    assert {record.attributes["attack_raw"]: record.verification_status for record in records} == {
        "555": VerificationStatus.COMPATIBLE_CANDIDATE,
        "666": VerificationStatus.COMPATIBLE_CANDIDATE,
    }
    assert conflicts == []

    expanded, expanded_conflicts = _merge_domain_records(
        [
            ambiguous_cannon("555", 0, source_id="source-a", target_id="target-a"),
            ambiguous_cannon("666", 0, source_id="source-b", target_id="target-b"),
            ambiguous_cannon("666", 1, source_id="source-a", target_id="target-a"),
        ]
    )
    initial_ids = {record.attributes["attack_raw"]: record.id for record in records}
    expanded_ids = {record.attributes["attack_raw"]: record.id for record in expanded}
    assert set(expanded_ids) == {"555", "666"}
    assert expanded_ids == initial_ids
    expanded_666 = next(record for record in expanded if record.attributes["attack_raw"] == "666")
    assert expanded_666.verification_status is VerificationStatus.CROSS_CHECKED
    assert expanded_conflicts == []


def test_non_love_cannons_do_not_use_attack_as_a_discriminator() -> None:
    records, conflicts = _merge_domain_records(
        [
            ambiguous_cannon("555", 0, ja="別の主炮", source_id="source-a", target_id="target-a"),
            ambiguous_cannon("666", 0, ja="別の主炮", source_id="source-b", target_id="target-b"),
        ]
    )

    assert len(records) == 1
    assert records[0].verification_status is VerificationStatus.CONFLICT
    assert [conflict.field for conflict in conflicts] == ["attack_raw"]


def test_real_tank_parts_love_machines_remain_three_ambiguous_records() -> None:
    result = normalize_snapshots(actual_snapshots())

    love_machines = [
        record for record in result.bundles["equipment"].records if record.names.ja == "LOVEマシン"
    ]

    assert len(love_machines) == 3
    assert all(record.issues == ["ambiguous_same_source_name"] for record in love_machines)
    assert {record.attributes["attack"] for record in love_machines} == {555, 666, 900}


def test_duplicate_aliases_across_sources_are_normalized_before_merging() -> None:
    left = NormalizedRecord.model_validate(
        {
            **mergeable_record("source-a", "target-a", 0).model_dump(),
            "names": {"ja": "りゅう弾", "aliases": ["Ａ"]},
        }
    )
    right = NormalizedRecord.model_validate(
        {
            **mergeable_record("source-b", "target-b", 0).model_dump(),
            "names": {"ja": "りゅう弾", "aliases": [" A "]},
        }
    )

    merged, conflicts = _merge_records([left, right])

    assert merged.names.aliases == ["A"]
    assert merged.verification_status is VerificationStatus.CROSS_CHECKED
    assert conflicts == []


def test_ambiguous_ids_depend_on_intrinsic_content_not_source_metadata_or_order() -> None:
    variants = [
        ambiguous_cannon(str(attack), index) for index, attack in enumerate((555, 666, 900))
    ]
    baseline, _ = _merge_domain_records(variants)
    changed, _ = _merge_domain_records(
        [
            with_source_metadata(
                record,
                retrieved_at=datetime(2030, 1, 1, tzinfo=UTC),
                content_hash="sha256:" + "c" * 64,
                source_url="https://example.com/another-page",
                row_index=record.source_refs[0].row_index + 100,
            )
            for record in reversed(variants)
        ]
    )

    assert {record.attributes["attack_raw"]: record.id for record in baseline} == {
        record.attributes["attack_raw"]: record.id for record in changed
    }
    assert len({record.id for record in baseline}) == 3


def test_identical_ambiguous_records_fail_instead_of_using_source_locators() -> None:
    duplicate = ambiguous_cannon("555", 0)

    with pytest.raises(NormalizationError, match="not unique"):
        _merge_domain_records([duplicate, with_source_metadata(duplicate, row_index=1)])


def test_real_love_machine_ids_stay_bound_to_attack_when_snapshots_reverse() -> None:
    forward = normalize_snapshots(actual_snapshots())
    backward = normalize_snapshots(list(reversed(actual_snapshots())))

    def ids_by_attack(result: NormalizationResult) -> dict[int, str]:
        result_ids: dict[int, str] = {}
        for record in result.bundles["equipment"].records:
            if record.names.ja == "LOVEマシン":
                attack = record.attributes["attack"]
                assert isinstance(attack, int)
                result_ids[attack] = record.id
        return result_ids

    assert ids_by_attack(forward) == ids_by_attack(backward)


def test_ambiguous_cannon_ids_use_only_declared_identity_fields() -> None:
    assert DISAMBIGUATION_FIELDS[("equipment", "main_cannon", "LOVEマシン")] == ("attack_raw",)
    baseline, _ = _merge_domain_records(
        [ambiguous_cannon("555", 0), ambiguous_cannon("666", 1), ambiguous_cannon("900", 2)]
    )
    changed, _ = _merge_domain_records(
        [
            ambiguous_cannon(
                "555",
                30,
                zh_09="爱机器",
                zh_099="爱机",
                aliases=["别名"],
                weight="999",
                notes="不同备注",
            ),
            ambiguous_cannon("666", 31, weight="888", notes="另一条备注"),
            ambiguous_cannon("900", 32, weight="777", notes="又一条备注"),
        ]
    )

    assert {record.attributes["attack_raw"]: record.id for record in baseline} == {
        record.attributes["attack_raw"]: record.id for record in changed
    }


def test_real_love_machine_ids_ignore_a_prepended_row_via_public_normalization() -> None:
    snapshots = actual_snapshots()
    baseline = normalize_snapshots(snapshots)
    tank_parts = next(snapshot for snapshot in snapshots if snapshot.target_id == "tank-parts")
    table = tank_parts.tables[0]
    prefixed_row = {**table.rows[0], "名称": "前置主炮", "攻击": "1"}
    prefixed_table = table.model_copy(
        update={
            "rows": [prefixed_row, *table.rows],
            "merged_cells": [
                merged_cell.model_copy(update={"row_index": merged_cell.row_index + 1})
                for merged_cell in table.merged_cells
            ],
        }
    )
    prefixed_snapshot = tank_parts.model_copy(update={"tables": [prefixed_table]})
    changed_snapshots = [
        prefixed_snapshot if snapshot.target_id == "tank-parts" else snapshot
        for snapshot in snapshots
    ]
    changed = normalize_snapshots(changed_snapshots)

    def love_ids(result: NormalizationResult) -> dict[str, str]:
        return {
            str(record.attributes["attack"]): record.id
            for record in result.bundles["equipment"].records
            if record.names.ja == "LOVEマシン"
        }

    assert love_ids(baseline) == love_ids(changed)


@pytest.mark.parametrize("empty_kind", ["tables", "rows"])
def test_normalize_snapshots_rejects_empty_declared_target_data(empty_kind: str) -> None:
    snapshots = actual_snapshots()
    jobs = next(snapshot for snapshot in snapshots if snapshot.target_id == "dqff-jobs")
    if empty_kind == "tables":
        invalid = jobs.model_copy(update={"tables": []})
    else:
        empty_table = jobs.tables[0].model_copy(update={"rows": []})
        invalid = jobs.model_copy(update={"tables": [empty_table]})
    invalid_snapshots = [
        invalid if snapshot.target_id == "dqff-jobs" else snapshot for snapshot in snapshots
    ]

    with pytest.raises(NormalizationError, match="dqff-jobs"):
        normalize_snapshots(invalid_snapshots)


@pytest.mark.parametrize("field,value", [("game", "other-game"), ("target_version", "9.9")])
def test_normalize_snapshots_rejects_wrong_game_or_target_version(field: str, value: str) -> None:
    snapshots = actual_snapshots()
    invalid = snapshots[0].model_copy(update={field: value})

    with pytest.raises(NormalizationError, match=snapshots[0].target_id) as error:
        normalize_snapshots([invalid, *snapshots[1:]])

    assert value in str(error.value)


def test_normalize_snapshots_rejects_skipped_rows_when_merged_cells_exist() -> None:
    snapshots = actual_snapshots()
    human_items = next(snapshot for snapshot in snapshots if snapshot.target_id == "human-items")
    unsafe = human_items.model_copy(update={"warnings": ["table 2: skipped row 4"]})
    unsafe_snapshots = [
        unsafe if snapshot.target_id == "human-items" else snapshot for snapshot in snapshots
    ]

    with pytest.raises(NormalizationError, match="human-items") as error:
        normalize_snapshots(unsafe_snapshots)

    assert "merged" in str(error.value)


def test_normalize_snapshots_rejects_merged_cell_without_matching_row() -> None:
    snapshots = actual_snapshots()
    tank_parts = next(snapshot for snapshot in snapshots if snapshot.target_id == "tank-parts")
    table = tank_parts.tables[0]
    unsafe_table = table.model_copy(
        update={
            "merged_cells": [
                *table.merged_cells,
                MergedCell(
                    row_index=999,
                    start_header="名称",
                    end_header="汉译",
                    value="无法关联",
                ),
            ]
        }
    )
    unsafe = tank_parts.model_copy(update={"tables": [unsafe_table]})
    unsafe_snapshots = [
        unsafe if snapshot.target_id == "tank-parts" else snapshot for snapshot in snapshots
    ]

    with pytest.raises(NormalizationError, match="tank-parts") as error:
        normalize_snapshots(unsafe_snapshots)

    assert "merged" in str(error.value)


def test_aliases_map_to_a_canonical_japanese_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        ALIASES,
        ("items", "special_shell"),
        {"りゅうだん": "りゅう弾", "龍弾": "りゅう弾"},
    )

    records, conflicts = _merge_domain_records(
        [
            mergeable_record("source-a", "target-a", 0, ja="りゅうだん"),
            mergeable_record("source-b", "target-b", 0, ja="龍弾"),
            mergeable_record("source-c", "target-c", 0, ja="りゅう弾"),
        ]
    )

    assert len(records) == 1
    assert records[0].names.ja == "りゅう弾"
    assert records[0].names.aliases == ["りゅうだん", "龍弾"]
    assert records[0].verification_status is VerificationStatus.CROSS_CHECKED
    assert conflicts == []
