"""将赏金首及掉落物事实整理为网站百科资料。"""

from collections.abc import Mapping
from pathlib import Path
from unicodedata import normalize

import yaml

from mmwiki_data.knowledge_models import (
    KnowledgeDataset,
    KnowledgeRecord,
    ReferenceAttribute,
    ReferenceSection,
    ReferenceTable,
    WantedDrop,
    WantedEnemy,
)
from mmwiki_data.normalization import stable_record_id
from mmwiki_data.normalization_models import NameSet, NormalizedBundle, NormalizedRecord, SourceRef
from mmwiki_data.storage import model_content_hash
from mmwiki_data.wanted_drop_items import (
    DropItemNames,
    DropItemTable,
    InheritedDropItemFacts,
    WantedDropItemFact,
    WantedDropItemSnapshot,
    load_wanted_drop_item_names,
    wanted_snapshot_hash,
)
from mmwiki_data.wanted_monsters import WantedMonsterSnapshot, WantedNames

_ROOT = Path("data/raw/mm2r/0.99")
_INHERITED_LABELS = {
    "description_raw": "作用说明",
    "target_ja_raw": "适用对象",
    "target_raw": "适用对象",
    "category_raw": "来源分类",
    "price_raw": "价格（G）",
    "attack_raw": "攻击力",
    "defense_raw": "防御力",
    "range_raw": "范围",
    "element_raw": "属性",
    "weight_raw": "重量（t）",
    "magazine_raw": "弹仓",
    "notes_raw": "备注",
    "additional_raw": "追加效果",
    "acquisition_raw": "获取方式",
}
_TERMS = {
    "無印": "无星",
    "通常": "普通",
    "火炎": "火焰",
    "冷気": "冷气",
    "電気": "电气",
    "電撃": "电气",
    "ガス": "毒气",
    "ビーム": "光束",
    "1体": "单体",
    "アクセサリー": "饰品",
    "頭": "头部防具",
    "体": "身体防具",
    "腕": "腕部防具",
    "足": "足部防具",
}
_RANGES = {
    "1体": "单体",
    "一体": "单体",
    "全体": "全体",
    "2連射": "2连射",
    "3連射": "3连射",
    "4回": "4次攻击",
    "扇範囲大": "大扇形",
    "扇範囲可変": "可变扇形",
    "貫通小": "小范围贯穿",
    "迎撃": "迎击",
}


def _key(value: str) -> str:
    return normalize("NFKC", value).replace("‐", "-").replace("‑", "-")


def _header(value: str, names: DropItemNames) -> str:
    if value in names.field_labels:
        return names.field_labels[value]
    return "/".join(names.field_labels.get(part, part) for part in value.split("/"))


def _value(value: str, field: str) -> str:
    if field in ("範囲", "攻撃範囲"):
        return _RANGES.get(value, value)
    return _TERMS.get(value, value)


def _condition_label(value: str) -> str:
    if value == "この行の原表値；星級未明示、星別行とは結合しない":
        return "星级未注明"
    if value == "総表の掲載値；詳細ページの星別数値とは別条件":
        return "总表参考值"
    if value.startswith("レア度：") and value.endswith("（同じ行の数値）"):
        stars = value.removeprefix("レア度：").removesuffix("（同じ行の数値）")
        return f"{_TERMS.get(stars, stars)}（原表星级）"
    return value.replace("ページのレア度表記：", "页面稀有度：")


def _detail_tables(
    table: DropItemTable, name: str, index: int, names: DropItemNames
) -> list[ReferenceTable]:
    metadata_rows: dict[str, list[list[str]]] = {}
    metadata_refs: dict[str, list[SourceRef]] = {}
    star_tables: list[ReferenceTable] = []
    for row in table.rows:
        condition = _condition_label(row.condition_raw)
        if table.headers[0] in ("レア度", "レア", "★") and row.values[0] in (
            "無印",
            "-",
            "★",
            "★★",
            "★★★",
        ):
            table_kind = (
                "改造费用"
                if any("/ダウン" in h or "/アップ" in h for h in table.headers)
                else "数值"
            )
            star_tables.append(
                ReferenceTable(
                    caption=f"{name} · {condition} · {table_kind}",
                    headers=["项目", "来源数值"],
                    rows=[
                        [_header(header, names), _TERMS.get(value, value)]
                        for header, value in zip(table.headers[1:], row.values[1:], strict=True)
                    ],
                    source_refs=[table.source_ref, row.source_ref],
                )
            )
            continue
        pairs: list[list[str]] = []
        used_cells: set[int] = set()
        for cell_index, (left, right) in enumerate(zip(row.cells, row.cells[1:], strict=False)):
            if left.is_header and not right.is_header and left.text:
                pairs.append([_header(left.text, names), _value(right.text, left.text)])
                used_cells.update((cell_index, cell_index + 1))
        unpaired = any(cell.text and i not in used_cells for i, cell in enumerate(row.cells))
        if not pairs or unpaired:
            raise ValueError(f"{name}: 详情表第 {row.source_ref.row_index + 1} 行结构未识别")
        metadata_rows.setdefault(condition, []).extend(pairs)
        metadata_refs.setdefault(condition, []).append(row.source_ref)
    return [
        ReferenceTable(
            caption=f"{name} · 基础资料 {index} · {condition}",
            headers=["项目", "来源数值或说明"],
            rows=rows,
            source_refs=[table.source_ref, *metadata_refs[condition]],
        )
        for condition, rows in metadata_rows.items()
    ] + star_tables


def _item_tables(fact: WantedDropItemFact, names: DropItemNames) -> list[ReferenceTable]:
    item_name = names.names[fact.canonical_item_ja]
    tables = [
        output
        for index, table in enumerate(fact.tables, 1)
        for output in _detail_tables(table, item_name, index, names)
    ]
    for table in fact.overview_tables:
        for row in table.rows:
            tables.append(
                ReferenceTable(
                    caption=f"{item_name} · 总表对照（独立于各星级详情）",
                    headers=["项目", "总表参考值"],
                    rows=[
                        [_header(header, names), _value(value, header)]
                        for header, value in zip(table.headers, row.values, strict=True)
                    ],
                    source_refs=[table.source_ref, row.source_ref],
                )
            )
    for inherited in fact.inherited_facts:
        values = [
            [label, str(inherited.attributes[key])]
            for key, label in _INHERITED_LABELS.items()
            if inherited.attributes.get(key) is not None
        ]
        if values:
            tables.append(
                ReferenceTable(
                    caption=f"{item_name} · 交叉来源：{inherited.condition_raw}",
                    headers=["项目", "来源原始值"],
                    rows=values,
                    source_refs=inherited.source_refs,
                )
            )
    return tables


def _item_refs(fact: WantedDropItemFact) -> list[SourceRef]:
    refs = [*fact.discovery_refs, *(prop.source_ref for prop in fact.properties)]
    if fact.detail_ref is not None:
        refs.append(fact.detail_ref)
    refs.extend(ref for inherited in fact.inherited_facts for ref in inherited.source_refs)
    return refs


def _validate_inherited(
    repo_root: Path,
    items: WantedDropItemSnapshot,
    names: DropItemNames,
    rebuilt_bundles: Mapping[str, NormalizedBundle] | None,
) -> None:
    bundles: dict[str, NormalizedBundle] = {}
    allowed = {"data/interim/mm2r/0.99/items.json", "data/interim/mm2r/0.99/equipment.json"}
    for fact in items.records:
        for inherited in fact.inherited_facts:
            filename = inherited.bundle_file
            if filename not in allowed:
                raise ValueError(f"{fact.canonical_item_ja}: 继承来源不在允许的数据包内")
            if filename not in bundles:
                if rebuilt_bundles is not None:
                    if filename not in rebuilt_bundles:
                        raise ValueError(f"{fact.canonical_item_ja}: 缺少重建的继承来源 {filename}")
                    bundles[filename] = rebuilt_bundles[filename]
                else:
                    path = repo_root / filename
                    if not path.resolve().is_relative_to(repo_root.resolve()):
                        raise ValueError(f"继承来源路径越出项目：{filename}")
                    bundles[filename] = NormalizedBundle.model_validate_json(path.read_bytes())
            bundle = bundles[filename]
            expected_domain = "items" if filename.endswith("/items.json") else "equipment"
            if bundle.domain != expected_domain:
                raise ValueError(f"{fact.canonical_item_ja}: 继承来源分类不一致")
            digest = model_content_hash(bundle)
            if inherited.bundle_hash != digest:
                raise ValueError(f"{fact.canonical_item_ja}: 继承来源哈希已变化，请重新采集掉落物")
            record = next((r for r in bundle.records if r.id == inherited.record_id), None)
            if record is None or record.names.ja is None:
                raise ValueError(f"{fact.canonical_item_ja}: 继承来源记录不存在")
            name = names.source_aliases.get(record.names.ja, record.names.ja)
            if _key(name) != fact.canonical_item_ja:
                raise ValueError(f"{fact.canonical_item_ja}: 继承记录的物品名称不一致")
            expected = InheritedDropItemFacts(
                record_id=record.id,
                bundle_file=filename,
                bundle_hash=digest,
                kind=record.kind,
                attributes=record.attributes,
                condition_raw=str(
                    record.attributes.get("stat_condition_raw") or "原记录未明示星级条件"
                ),
                source_refs=record.source_refs,
            )
            if model_content_hash(inherited) != model_content_hash(expected):
                raise ValueError(f"{fact.canonical_item_ja}: 继承属性或来源定位与原记录不一致")


def validate_wanted_sources(
    repo_root: Path, rebuilt_bundles: Mapping[str, NormalizedBundle] | None = None
) -> bool:
    """离线校验两个完整快照、编辑名称与它们的依赖哈希。"""
    root = repo_root / _ROOT
    wanted_path = root / "wanted-monsters/facts.json"
    if not wanted_path.exists():
        if (root / "wanted-monsters/names.yaml").exists():
            raise ValueError("赏金首来源快照缺失，请先采集")
        return False
    wanted_bytes = wanted_path.read_bytes()
    wanted = WantedMonsterSnapshot.model_validate_json(wanted_bytes)
    names = WantedNames.model_validate(
        yaml.safe_load((root / "wanted-monsters/names.yaml").read_text(encoding="utf-8"))
    )
    if {record.overview.name_ja for record in wanted.records} != set(names.names):
        raise ValueError("赏金首快照与参考名称清单不一致")
    items = WantedDropItemSnapshot.model_validate_json(
        (root / "wanted-drop-items/facts.json").read_bytes()
    )
    if items.wanted_snapshot_hash != wanted_snapshot_hash(wanted):
        raise ValueError("掉落物快照与当前赏金首快照哈希不一致，请重新采集掉落物")
    item_names = load_wanted_drop_item_names(repo_root)
    expected_items = {
        drop.canonical_item_ja
        for record in wanted.records
        for enemy in record.enemy_forms
        for drop in enemy.drops
    }
    if {fact.canonical_item_ja for fact in items.records} != expected_items or set(
        item_names.names
    ) != expected_items:
        raise ValueError("赏金首掉落与89种物品事实没有完整对应")
    wanted_drops = {
        (record.overview.name_ja, enemy.canonical_name_ja, drop.slot): (
            drop.item_ja,
            drop.canonical_item_ja,
            drop.rate_raw,
            model_content_hash(enemy.source_ref),
        )
        for record in wanted.records
        for enemy in record.enemy_forms
        for drop in enemy.drops
    }
    actual_drops = {
        (
            use.wanted_name_ja,
            _key(names.source_aliases.get(use.enemy_name_ja, use.enemy_name_ja)),
            use.slot,
        ): (use.item_ja, fact.canonical_item_ja, use.rate_raw, model_content_hash(use.source_ref))
        for fact in items.records
        for use in fact.drop_uses
    }
    if wanted_drops != actual_drops:
        raise ValueError("掉落物来源中的槽位、物品或概率与赏金首不一致")
    _validate_inherited(repo_root, items, item_names, rebuilt_bundles)
    return True


def load_wanted_monsters(
    repo_root: Path,
    equipment: list[NormalizedRecord],
    *,
    rebuilt_bundles: Mapping[str, NormalizedBundle] | None = None,
) -> KnowledgeDataset | None:
    """生成赏金首正文与逐槽掉落，不提升来源核验状态。"""
    if not validate_wanted_sources(repo_root, rebuilt_bundles):
        return None
    root = repo_root / _ROOT
    snapshot = WantedMonsterSnapshot.model_validate_json(
        (root / "wanted-monsters/facts.json").read_bytes()
    )
    names = WantedNames.model_validate(
        yaml.safe_load((root / "wanted-monsters/names.yaml").read_text(encoding="utf-8"))
    )
    item_snapshot = WantedDropItemSnapshot.model_validate_json(
        (root / "wanted-drop-items/facts.json").read_bytes()
    )
    item_names = load_wanted_drop_item_names(repo_root)
    item_facts = {item.canonical_item_ja: item for item in item_snapshot.records}
    equipment_matches: dict[str, list[NormalizedRecord]] = {}
    for record in equipment:
        if record.names.ja:
            equipment_matches.setdefault(_key(record.names.ja), []).append(record)
    records: list[KnowledgeRecord] = []
    for fact in snapshot.records:
        overview = fact.overview
        appearance = ReferenceSection(
            id="appearance",
            title="位置与触发条件",
            paragraphs=[item.summary_zh for item in fact.appearance_facts],
            source_refs=[item.source_ref for item in fact.appearance_facts],
        )
        sections = [appearance]
        if fact.conflicts:
            sections.append(
                ReferenceSection(
                    id="source-conflicts",
                    title="来源差异",
                    paragraphs=[item.summary_zh for item in fact.conflicts],
                    source_refs=[ref for item in fact.conflicts for ref in item.source_refs],
                )
            )
        enemies: list[WantedEnemy] = []
        for enemy in fact.enemy_forms:
            drops: list[WantedDrop] = []
            for drop in enemy.drops:
                item = item_facts[drop.canonical_item_ja]
                matches = equipment_matches.get(_key(drop.canonical_item_ja), [])
                attributes = [
                    ReferenceAttribute(
                        label="类别",
                        value=item_names.category_labels[
                            item_names.categories[drop.canonical_item_ja]
                        ],
                    )
                ]
                for prop in item.properties:
                    if prop.label_ja in ("範囲", "属性", "特殊効果", "攻撃範囲") and prop.value_raw:
                        label = _header(prop.label_ja, item_names)
                        attributes.append(
                            ReferenceAttribute(
                                label=f"{label}（{_condition_label(prop.condition_raw)}）",
                                value=_value(prop.value_raw, prop.label_ja),
                            )
                        )
                drops.append(
                    WantedDrop(
                        slot=drop.slot,
                        item_ja=drop.canonical_item_ja,
                        name=item_names.names[drop.canonical_item_ja],
                        rate_raw=drop.rate_raw,
                        summary=item_names.effects[drop.canonical_item_ja],
                        equipment_id=matches[0].id if len(matches) == 1 else None,
                        attributes=attributes,
                        tables=_item_tables(item, item_names),
                        source_refs=[enemy.source_ref, *_item_refs(item)],
                        issues=[
                            *item.issues,
                            *(["ambiguous_equipment_name"] if len(matches) > 1 else []),
                        ],
                    )
                )
            enemies.append(
                WantedEnemy(
                    name_ja=enemy.name_ja,
                    encyclopedia_number=enemy.encyclopedia_number,
                    drops=drops,
                )
            )
        attributes = [
            ReferenceAttribute(label="赏金（G）", value=overview.bounty_raw),
            ReferenceAttribute(label="知名度", value=overview.fame_raw),
            ReferenceAttribute(label="位置原始记录（日文）", value=overview.location_ja_raw),
        ]
        if overview.notes_ja_raw:
            attributes.append(
                ReferenceAttribute(label="来源备注（日文）", value="；".join(overview.notes_ja_raw))
            )
        records.append(
            KnowledgeRecord(
                id=stable_record_id("wanted-monsters", "wanted-monster", overview.name_ja),
                category="wanted-monsters",
                names=NameSet(
                    ja=overview.name_ja,
                    zh_reference=names.names[overview.name_ja],
                    aliases=names.aliases.get(overview.name_ja, []),
                ),
                bounty=int(overview.bounty_raw.replace(",", "")),
                summary="".join(appearance.paragraphs),
                attributes=attributes,
                sections=sections,
                enemies=enemies,
                probability_note=snapshot.probability_note,
                tags=["赏金首", "位置", "掉落"],
                version_scope=[snapshot.version_scope],
                verification_status=snapshot.verification_status,
                source_refs=[overview.source_ref, *(row.source_ref for row in overview.rows)],
                issues=[item.code for item in fact.conflicts],
            )
        )
    return KnowledgeDataset(category="wanted-monsters", records=sorted(records, key=lambda r: r.id))
