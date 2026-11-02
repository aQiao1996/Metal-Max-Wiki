"""把既有274条道具身份与逐来源条件整理为可追溯正文。"""

import re
from pathlib import Path

from mmwiki_data.items import (
    ConsumptionStatus,
    ItemFact,
    ItemNames,
    ItemSnapshot,
    ItemSourceRow,
    ItemStatement,
    StatementField,
    _drop_rows,
    _legacy_rows,
    _statements,
    load_item_names,
    load_items,
)
from mmwiki_data.knowledge_models import (
    KnowledgeDataset,
    KnowledgeRecord,
    ReferenceAttribute,
    ReferenceSection,
    ReferenceTable,
)
from mmwiki_data.normalization_models import (
    NameSet,
    NormalizedBundle,
    SourceRef,
    sorted_unique_source_refs,
)
from mmwiki_data.storage import model_content_hash
from mmwiki_data.wanted_drop_items import WantedDropItemSnapshot

_ROOT = Path("data/raw/mm2r/0.99/items")
_LEGACY = Path("data/interim/mm2r/0.99/items.json")
_DROPS = Path("data/raw/mm2r/0.99/wanted-drop-items/facts.json")
_KINDS = {
    "human_item": "人类道具",
    "tank_item": "战车道具",
    "special_shell": "特殊炮弹",
    "love_machine_recipe": "LOVE配方",
    "ic_chip_location": "IC位置",
}
_CONSUMPTION: dict[ConsumptionStatus, str] = {
    "consumable": "一次性使用",
    "reusable": "可反复使用",
    "random_breakage": "使用后可能随机损坏",
    "limited_uses": "可使用数次，具体次数未明",
    "toggle": "可切换开启与关闭",
    "conflicting": "来源记载冲突，按各来源分别保留",
    "unknown": "来源未明确记载消耗性，不能据此认定可无限使用",
    "not_applicable": "配方或位置资料，不适用道具使用次数；不推断芯片是否消失",
}
_FIELDS: dict[StatementField, str] = {
    "usage": "用途",
    "target": "使用对象",
    "acquisition": "获取方式",
    "consumption": "消耗性",
    "restriction": "使用限制",
    "recipe": "配方材料",
    "field_effect": "地图使用效果",
    "battle_effect": "战斗使用效果",
    "carryover": "周目继承",
    "notes": "补充说明",
}
_MISSING = {
    "acquisition": "来源未明确提供获取方式。",
    "consumption": "来源未明确记载消耗性，不能据此认定可无限使用。",
    "restriction": "来源未明确提供使用或周目继承限制。",
    "sell_discard_restrictions": "来源未明确提供出售、丢弃限制。",
    "target": "来源未明确提供使用对象。",
}
_ISSUES = {
    "source_consumption_conflict": "各来源对使用次数或损坏机制的记载不同。",
    "no_additional_fact_match": "本条暂只有既有攻略事实，尚缺少新增来源交叉核对。",
    "missing_japanese_name": "原目录未提供日文名称，以原有配方身份保留。",
    "source_merged_cell": "原表存在合并单元格，不能把跨列值拆成独立场景结论。",
}
_ATTRIBUTES = {
    "battle_effect_raw": "战斗使用效果（原值）",
    "category_raw": "原分类",
    "consumption_raw": "消耗（原值）",
    "description_raw": "用途说明（原值）",
    "e": "E芯片编号",
    "e_raw": "E芯片编号（原值）",
    "effect_raw": "效果（原值）",
    "field_effect_raw": "地图使用效果（原值）",
    "l": "L芯片编号",
    "l_raw": "L芯片编号（原值）",
    "location_raw": "位置（原值）",
    "material_1_raw": "材料一（原值）",
    "material_2_raw": "材料二（原值）",
    "material_3_raw": "材料三（原值）",
    "notes_raw": "备注（原值）",
    "number": "图鉴编号",
    "number_raw": "图鉴编号（原值）",
    "o": "O芯片编号",
    "o_raw": "O芯片编号（原值）",
    "price": "价格",
    "price_raw": "价格（原值）",
    "stars_raw": "星级（原值）",
    "target_ja_raw": "对象（日文原值）",
    "usage_context_zh_09_raw": "使用场景（旧中文原值）",
    "v": "V芯片编号",
    "v_raw": "V芯片编号（原值）",
    "weight": "重量",
    "weight_raw": "重量（原值）",
}
_SOURCES = {
    "metalmaniax-mm2r": "METAL MAniaX",
    "zzjb-mm2r": "重装机兵专题站",
    "dqff-mm2r": "组长式攻略",
    "kaerulabo-mm2r": "Kaerulabo掉落资料",
}
_VERSIONS = {"mm2r-jp": "日版MM2R", "zh-patch-0.9-family": "0.9系列中文资料"}


def _references(fact: ItemFact) -> list[SourceRef]:
    return sorted_unique_source_refs(
        [
            *fact.inherited_record.source_refs,
            *(row.source_ref for row in fact.source_rows),
            *(ref for statement in fact.statements for ref in statement.source_refs),
        ]
    )


def _validate_fact(fact: ItemFact, names: ItemNames, drops: WantedDropItemSnapshot) -> None:
    entry = names.names[fact.id]
    expected_reference = (
        entry.name_zh_reference,
        entry.category,
        names.categories[entry.category],
        entry.summary_zh,
        entry.target_zh,
        entry.related_record_ids,
        sorted(set([*fact.inherited_record.names.aliases, *entry.match_names])),
    )
    actual_reference = (
        fact.name_zh_reference,
        fact.category,
        fact.category_label_zh,
        fact.summary_zh,
        fact.target_zh,
        fact.related_record_ids,
        fact.aliases,
    )
    if actual_reference != expected_reference:
        raise ValueError(f"{fact.id}: 道具快照与中文参考清单不一致，请重新采集")
    if fact.kind not in _KINDS:
        raise ValueError(f"{fact.id}: 道具原目录类别尚未核对")
    unknown_fields = set(fact.inherited_record.attributes) - set(_ATTRIBUTES)
    if unknown_fields or set(fact.issues) - set(_ISSUES):
        raise ValueError(f"{fact.id}: 道具包含尚未核对的旧字段或来源问题")
    for row in fact.source_rows:
        if row.source_ref.source_id not in _SOURCES or set(row.version_scope) - set(_VERSIONS):
            raise ValueError(f"{fact.id}: 道具来源或版本范围尚未核对")
    expected_statements = _statements(fact.source_rows, names)
    linked_by_id = {
        record_id: drop
        for drop in drops.records
        for record_id in drop.existing_record_ids
        if record_id in names.names
    }
    linked = linked_by_id.get(fact.id)
    if (linked is not None) != (fact.linked_drop_item is not None):
        raise ValueError(f"{fact.id}: 道具遗漏或多出了掉落物依赖")
    if [row for row in fact.source_rows if row.locator_scheme == "cached_drop_table"] != (
        _drop_rows(linked) if linked is not None else []
    ):
        raise ValueError(f"{fact.id}: 道具关联掉落物的来源行重复、缺失或发生变化")
    if linked is not None:
        if fact.linked_drop_item is None or (
            fact.linked_drop_item.canonical_item_ja != linked.canonical_item_ja
        ):
            raise ValueError(f"{fact.id}: 道具关联了其他掉落物")
        for use in linked.drop_uses:
            value = f"{use.enemy_name_ja}：掉落槽{use.slot}，原表概率{use.rate_raw}"
            expected_statements.append(
                ItemStatement(
                    field="acquisition",
                    label_raw="赏金首掉落表",
                    value_raw=value,
                    value_zh_reference=names.value_translations.get(value),
                    condition_raw="原掉落表单槽物品概率；不推算星级、难度、复合概率或掉落机制",
                    version_scope=["mm2r-jp"],
                    source_refs=[use.source_ref],
                )
            )
    if sorted(model_content_hash(statement) for statement in fact.statements) != sorted(
        model_content_hash(statement) for statement in expected_statements
    ):
        raise ValueError(f"{fact.id}: 道具中文说明、原字段或条件与来源行不一致")
    expected_missing = [
        field
        for field in ("acquisition", "restriction")
        if not any(
            statement.field in ({field, "carryover"} if field == "restriction" else {field})
            for statement in fact.statements
        )
    ]
    if fact.consumption_status == "unknown":
        expected_missing.append("consumption")
    if not any(
        re.search(r"売[却れ].*[不可な]|捨[てら].*[不可な]", statement.value_raw)
        for statement in fact.statements
    ):
        expected_missing.append("sell_discard_restrictions")
    if fact.target_zh is None:
        expected_missing.append("target")
    if fact.missing_fields != expected_missing:
        raise ValueError(f"{fact.id}: 道具缺失说明与来源事实不一致")
    expected_notes = list(entry.notes_zh)
    expected_issues = list(fact.inherited_record.issues)
    if all(row.locator_scheme == "candidate_data_row" for row in fact.source_rows):
        expected_notes.append(_ISSUES["no_additional_fact_match"])
        expected_issues.append("no_additional_fact_match")
    if fact.consumption_status == "conflicting":
        expected_issues.append("source_consumption_conflict")
    if any(row.merged_headers for row in fact.source_rows):
        expected_issues.append("source_merged_cell")
    if fact.notes_zh != expected_notes or fact.issues != sorted(set(expected_issues)):
        raise ValueError(f"{fact.id}: 道具来源问题或编辑备注与原资料不一致")


def _legacy_rows_from_snapshot(fact: ItemFact) -> list[ItemSourceRow]:
    """原表完整列与继承属性分开保留，不把重复字段压成单一结论。"""
    return [row for row in fact.source_rows if row.locator_scheme == "candidate_data_row"]


def _load_sources(
    repo_root: Path, *, rebuilt_bundle: NormalizedBundle | None = None
) -> tuple[ItemSnapshot, ItemNames] | None:
    required = [repo_root / _ROOT / filename for filename in ("facts.json", "names.yaml")]
    if not any(path.exists() for path in required):
        return None
    for path in [*required, repo_root / _LEGACY, repo_root / _DROPS]:
        if not path.is_file():
            raise FileNotFoundError(f"道具资料依赖缺失：{path}")
    snapshot = load_items(repo_root)
    if snapshot is None:
        raise ValueError("道具事实快照在校验时缺失")
    names = load_item_names(repo_root)
    legacy = (
        rebuilt_bundle
        if rebuilt_bundle is not None
        else NormalizedBundle.model_validate_json((repo_root / _LEGACY).read_bytes())
    )
    if legacy.domain != "items" or model_content_hash(legacy) != snapshot.legacy_bundle_hash:
        raise ValueError("道具继承的旧数据包已变化，请重新采集道具快照")
    if [record.inherited_record for record in snapshot.records] != legacy.records:
        raise ValueError("道具快照没有逐条完整保留旧记录及身份")
    if set(names.names) != {record.id for record in snapshot.records}:
        raise ValueError("道具快照与274条中文参考清单的身份集合不一致")
    if (snapshot.reference_note, snapshot.condition_note) != (
        names.reference_note,
        names.condition_note,
    ):
        raise ValueError("道具快照的参考译名或条件说明已过期")
    drops = WantedDropItemSnapshot.model_validate_json((repo_root / _DROPS).read_bytes())
    if sum(record.linked_drop_item is not None for record in snapshot.records) != 8:
        raise ValueError("道具快照必须保留8个已有赏金掉落物依赖")
    for fact in snapshot.records:
        expected_rows = _legacy_rows(repo_root, fact.inherited_record)
        actual_rows = _legacy_rows_from_snapshot(fact)
        if actual_rows != expected_rows:
            raise ValueError(f"{fact.id}: 道具原候选行、合并格或条件与旧来源不一致")
        _validate_fact(fact, names, drops)
    return snapshot, names


def validate_item_sources(
    repo_root: Path, *, rebuilt_bundle: NormalizedBundle | None = None
) -> bool:
    """离线核对完整道具快照、中文参考清单与两个规范模型哈希依赖。"""
    return _load_sources(repo_root, rebuilt_bundle=rebuilt_bundle) is not None


def _version_text(versions: list[str]) -> str:
    return "、".join(_VERSIONS[version] for version in versions)


def _statement_table(statement: ItemStatement, index: int) -> ReferenceTable:
    rows = [
        ["原表字段", statement.label_raw],
        ["原文", statement.value_raw],
        ["适用条件", statement.condition_raw],
        ["版本范围", _version_text(statement.version_scope)],
    ]
    if statement.value_zh_reference is not None:
        rows.insert(0, ["中文参考", statement.value_zh_reference])
    return ReferenceTable(
        caption=f"{_FIELDS[statement.field]} · {index}",
        headers=["项目", "来源内容"],
        rows=rows,
        source_refs=statement.source_refs,
    )


def _statement_section(
    fact: ItemFact,
    section_id: str,
    title: str,
    fields: set[StatementField],
    paragraphs: list[str],
) -> ReferenceSection:
    statements = [statement for statement in fact.statements if statement.field in fields]
    return ReferenceSection(
        id=section_id,
        title=title,
        paragraphs=paragraphs,
        tables=[
            _statement_table(statement, index) for index, statement in enumerate(statements, 1)
        ],
        source_refs=sorted_unique_source_refs(
            [ref for statement in statements for ref in statement.source_refs]
        )
        or _references(fact),
    )


def _raw_table(row: ItemSourceRow, index: int) -> ReferenceTable:
    rows = [
        ["原表小节", row.section_raw],
        ["适用条件", row.condition_raw],
        ["版本范围", _version_text(row.version_scope)],
        *[
            [f"第{column}列 · {header}", value]
            for column, (header, value) in enumerate(
                zip(row.headers_raw, row.values_list_raw, strict=True), 1
            )
        ],
    ]
    if row.merged_headers:
        rows.append(["跨列字段（原表顺序）", "、".join(row.merged_headers)])
    rows.extend(
        [
            f"原格{cell_index}（{'表头' if cell.is_header else '数据'}；"
            f"跨{cell.rowspan}行、{cell.colspan}列）",
            cell.text,
        ]
        for cell_index, cell in enumerate(row.cells, 1)
    )
    return ReferenceTable(
        caption=f"来源原表 {index} · {_SOURCES[row.source_ref.source_id]}",
        headers=["原字段", "原始值"],
        rows=rows,
        source_refs=[row.source_ref],
    )


def _legacy_table(fact: ItemFact) -> ReferenceTable:
    inherited = fact.inherited_record
    rows = [
        [_ATTRIBUTES[key], "（空值）" if value is None else str(value)]
        for key, value in inherited.attributes.items()
    ]
    rows.extend(
        [f"原合并格 · {span.start_header} 至 {span.end_header}", span.value]
        for span in inherited.source_spans
    )
    return ReferenceTable(
        caption="既有目录字段（独立保留）",
        headers=["项目", "既有值"],
        rows=rows,
        source_refs=inherited.source_refs,
    )


def _readable_note(value: str) -> str:
    replacements = {
        **_KINDS,
        "inherited_record": "旧记录",
        "source_rows": "原表记录",
        "consumption_status": "消耗性",
        "not_applicable": "不适用",
        "missing_fields": "缺失说明",
        "linked_drop_item": "关联掉落物",
        "related_record_ids": "关联道具",
        "稳定ID": "稳定身份",
    }
    for raw, label in replacements.items():
        value = value.replace(raw, label)
    return value


def _record(fact: ItemFact, snapshot: ItemSnapshot, names: ItemNames) -> KnowledgeRecord:
    refs = _references(fact)
    sections = [
        _statement_section(
            fact,
            "usage",
            "用途与使用方式",
            {"usage", "field_effect", "battle_effect", "notes"},
            [fact.summary_zh],
        ),
        _statement_section(
            fact,
            "target",
            "使用对象",
            {"target"},
            [fact.target_zh or _MISSING["target"]],
        ),
        _statement_section(
            fact,
            "acquisition",
            "获取方式与地点",
            {"acquisition"},
            [_MISSING["acquisition"]] if "acquisition" in fact.missing_fields else [],
        ),
        _statement_section(
            fact,
            "consumption-restrictions",
            "消耗性与使用限制",
            {"consumption", "restriction", "carryover"},
            [
                _CONSUMPTION[fact.consumption_status],
                *[
                    _MISSING[field]
                    for field in ("restriction", "sell_discard_restrictions")
                    if field in fact.missing_fields
                ],
            ],
        ),
    ]
    if fact.kind in ("love_machine_recipe", "ic_chip_location"):
        sections.append(
            _statement_section(
                fact,
                "love-machine",
                "LOVE机器配方与芯片资料",
                {"recipe"},
                [
                    "配方按L、O、V、E的芯片顺序保留；来源明确分列时分别记录地图与战斗效果，"
                    "跨两列的装备类别或说明按组合效果保留。"
                    if fact.kind == "love_machine_recipe"
                    else "本条记录对应芯片的位置，各来源地点写法分别保留。"
                ],
            )
        )
    notes = [
        snapshot.reference_note,
        _readable_note(snapshot.condition_note),
        *(_readable_note(note) for note in fact.notes_zh),
        *(_ISSUES[issue] for issue in fact.issues),
        *(_MISSING[field] for field in fact.missing_fields),
        *(_readable_note(note) for note in snapshot.limitations),
    ]
    if fact.related_record_ids:
        notes.append(
            "关联目录条目："
            + "、".join(
                names.names[record_id].name_zh_reference for record_id in fact.related_record_ids
            )
            + "。各条原有身份分别保留。"
        )
    sections.extend(
        [
            ReferenceSection(
                id="raw-source-tables",
                title="原表与既有字段",
                paragraphs=["原表按列顺序竖向展开，空白、重复字段及合并单元格原样保留。"],
                tables=[
                    *[_raw_table(row, index) for index, row in enumerate(fact.source_rows, 1)],
                    _legacy_table(fact),
                ],
                source_refs=refs,
            ),
            ReferenceSection(
                id="source-issues",
                title="来源说明与待确认事项",
                paragraphs=list(dict.fromkeys(notes)),
                source_refs=refs,
            ),
        ]
    )
    attributes = [
        ReferenceAttribute(label="分类", value=fact.category_label_zh),
        ReferenceAttribute(label="原目录类别", value=_KINDS[fact.kind]),
        ReferenceAttribute(label="使用对象", value=fact.target_zh or "来源未明确记载"),
        ReferenceAttribute(label="消耗性", value=_CONSUMPTION[fact.consumption_status]),
    ]
    if fact.kind == "love_machine_recipe":
        attributes.append(
            ReferenceAttribute(
                label="芯片组合（L/O/V/E）",
                value=" / ".join(
                    str(fact.inherited_record.attributes[key]) for key in ("l", "o", "v", "e")
                ),
            )
        )
    inherited_names = fact.inherited_record.names
    return KnowledgeRecord(
        id=fact.id,
        category="items",
        names=NameSet(
            ja=inherited_names.ja,
            zh_09=inherited_names.zh_09,
            zh_099=inherited_names.zh_099,
            zh_reference=fact.name_zh_reference,
            aliases=fact.aliases,
        ),
        summary=fact.summary_zh,
        attributes=attributes,
        sections=sections,
        tags=list(dict.fromkeys([_KINDS[fact.kind], fact.category_label_zh])),
        version_scope=["mm2r-jp"],
        verification_status="source_only",
        source_refs=refs,
        issues=list(
            dict.fromkeys(
                [
                    *(_ISSUES[issue] for issue in fact.issues),
                    *(_readable_note(note) for note in fact.notes_zh),
                ]
            )
        ),
    )


def load_item_references(
    repo_root: Path, *, rebuilt_bundle: NormalizedBundle | None = None
) -> KnowledgeDataset | None:
    """离线生成道具、81项LOVE配方及12条IC位置资料，保留274个旧身份。"""
    sources = _load_sources(repo_root, rebuilt_bundle=rebuilt_bundle)
    if sources is None:
        return None
    snapshot, names = sources
    return KnowledgeDataset(
        category="items", records=[_record(fact, snapshot, names) for fact in snapshot.records]
    )
