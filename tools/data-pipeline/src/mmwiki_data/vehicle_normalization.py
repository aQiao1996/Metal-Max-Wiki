"""把战车与特性原始事实整理为网站可追溯的百科条目。"""

import re
from pathlib import Path
from unicodedata import normalize
from urllib.parse import unquote, urldefrag, urlsplit

import yaml

from mmwiki_data.knowledge_models import (
    KnowledgeDataset,
    KnowledgeRecord,
    ReferenceAttribute,
    ReferenceSection,
    ReferenceTable,
    VehicleDetails,
    VehicleSetup,
)
from mmwiki_data.normalization import stable_record_id
from mmwiki_data.normalization_models import NameSet, SourceRef, sorted_unique_source_refs
from mmwiki_data.storage import model_content_hash
from mmwiki_data.vehicle_traits import (
    VehicleMountRule,
    VehicleTraitDescription,
    VehicleTraitNames,
    VehicleTraitParameter,
    VehicleTraitRecord,
    VehicleTraitSnapshot,
    load_vehicle_traits,
)
from mmwiki_data.vehicles import (
    VehicleConfiguration,
    VehicleFact,
    VehicleNames,
    VehiclePurchaseOption,
    VehicleRawTable,
    VehicleSnapshot,
)

_ROOT = Path("data/raw/mm2r/0.99")
_SOURCE_ID = "metalmaniax-mm2r"
_VEHICLE_TARGET = "maniax-vehicles"
_TRAIT_TARGET = "maniax-vehicle-traits"
_DESIGN_PLACEHOLDER = "選択 *1"
_INITIAL_HEADERS = ["部位", "部位", "装備", "性能", "重さ", "店売", "店売"]
_MODIFICATION_HEADERS = ["部位", "大砲タイプ", "機銃タイプ", "S-Eタイプ"]
_STAGE_PARAMETER_VEHICLES = {"狼式开放阶段": "ウルフ", "猎豹开放阶段": "ゲパルト"}


def _page_key(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    return parsed.path, unquote(parsed.query)


def _validate_ref(ref: SourceRef, target: str, context: str) -> None:
    parsed = urlsplit(str(ref.source_url))
    if (
        ref.source_id != _SOURCE_ID
        or ref.target_id != target
        or parsed.scheme != "https"
        or parsed.hostname != "metalmaniax.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.path != "/index.php"
        or not unquote(parsed.query).startswith("MM2R/")
    ):
        raise ValueError(f"{context}: 来源标识或HTTPS同作地址不正确：{ref.source_url}")


def _expect_vehicle_page(ref: SourceRef, name: str, context: str) -> None:
    if _page_key(str(ref.source_url)) != ("/index.php", f"MM2R/DATA/戦車/{name}"):
        raise ValueError(f"{context}: 来源页面与车型{name}不一致")


def _raw_table_refs(table: VehicleRawTable) -> list[SourceRef]:
    return [row.source_ref for row in table.rows]


def _vehicle_refs(fact: VehicleFact) -> list[SourceRef]:
    refs = [
        fact.defense.source_ref,
        fact.ammunition.source_ref,
        fact.double_engine.source_ref,
        fact.double_c_unit.source_ref,
        *(item.source_ref for item in fact.configurations),
        *(item.source_ref for item in fact.mount_exceptions),
        *(item.source_ref for item in fact.acquisition_ja),
        *(item.source_ref for item in fact.conditions_zh),
        *(ref for table in fact.individual_modifications for ref in _raw_table_refs(table)),
    ]
    if fact.initial_equipment is not None:
        refs.extend(_raw_table_refs(fact.initial_equipment))
    if fact.design_traits is not None:
        refs.append(fact.design_traits.source_ref)
    if fact.branch_source_ref is not None:
        refs.append(fact.branch_source_ref)
    return sorted_unique_source_refs(refs)


def _validate_table(table: VehicleRawTable, name: str, index: int) -> None:
    for row_index, row in enumerate(table.rows):
        _expect_vehicle_page(row.source_ref, name, f"{name}原表{index}")
        if (row.source_ref.table_index, row.source_ref.row_index) != (index, row_index):
            raise ValueError(f"{name}: 原表{index}的行来源坐标不一致")


def _validate_vehicle(fact: VehicleFact, names: VehicleNames) -> None:
    name = fact.name_ja
    NameSet(ja=name, zh_reference=names.names[name], aliases=names.aliases.get(name, []))
    for ref in _vehicle_refs(fact):
        _validate_ref(ref, _VEHICLE_TARGET, name)
    for row_index, stat in enumerate((fact.defense, fact.ammunition)):
        _expect_vehicle_page(stat.source_ref, name, f"{name}底盘数值")
        if (stat.source_ref.table_index, stat.source_ref.row_index) != (0, row_index):
            raise ValueError(f"{name}: 防御或弹仓的字段来源坐标不一致")
        if any(
            re.fullmatch(r"[0-9]+|-", value) is None
            for value in (stat.minimum_raw, stat.initial_raw, stat.maximum_raw)
        ):
            raise ValueError(f"{name}: 防御或弹仓包含未识别的原始值")
    for row_index, mount in enumerate((fact.double_engine, fact.double_c_unit), start=2):
        _expect_vehicle_page(mount.source_ref, name, f"{name}双部件")
        if (mount.source_ref.table_index, mount.source_ref.row_index) != (0, row_index):
            raise ValueError(f"{name}: 双部件的字段来源坐标不一致")
        expected = (
            False
            if mount.value_ja.startswith("不可")
            else True
            if mount.value_ja.startswith("可")
            else None
        )
        if expected is None or expected != mount.supported:
            raise ValueError(f"{name}: 双部件支持标记与原文不一致")
    expected_initial = name not in ("スーパーカー", "サイファイ")
    if (fact.initial_equipment is not None) != expected_initial:
        raise ValueError(f"{name}: 初始装备表缺失或错配")
    table_index = 2 if expected_initial else 1
    for row_index, configuration in enumerate(fact.configurations):
        ref = configuration.source_ref
        _expect_vehicle_page(ref, name, f"{name}配置{configuration.name_ja}")
        if (ref.table_index, ref.row_index) != (table_index, row_index):
            raise ValueError(f"{name}: 配置来源行重复、缺失或顺序变化")
        if (configuration.fixed_armament_raw is not None) != (name == "スーパーカー"):
            raise ValueError(f"{name}: 固定武装列缺失或错配")
        if configuration.trait_raw == _DESIGN_PLACEHOLDER and fact.design_traits is None:
            raise ValueError(f"{name}: 非设计车型出现特性选择占位")
    if fact.initial_equipment is not None:
        _validate_table(fact.initial_equipment, name, 1)
    for index, table in enumerate(fact.individual_modifications, start=table_index + 1):
        _validate_table(table, name, index)
    for item in fact.acquisition_ja:
        _expect_vehicle_page(item.source_ref, name, f"{name}获取原文")
    if fact.branch_source_ref is not None:
        _expect_vehicle_page(fact.branch_source_ref, name, f"{name}分支章节")
    if fact.design_traits is not None:
        _expect_vehicle_page(fact.design_traits.source_ref, name, f"{name}设计脚注")
    if name == "野バス":
        if len(fact.mount_exceptions) != 1:
            raise ValueError("野巴士必须保留唯一的租赁10号初始双引擎例外")
        exception = fact.mount_exceptions[0]
        if (
            fact.double_engine.supported
            or exception.evidence_ja != fact.double_engine.value_ja
            or exception.source_ref != fact.double_engine.source_ref
            or "10号のみ初期仕様" not in exception.evidence_ja
        ):
            raise ValueError("野巴士租赁10号的初始双引擎证据不一致")
    specifications = names.condition_sources[name]
    if len(fact.conditions_zh) != len(specifications):
        raise ValueError(f"{name}: 获取条件与编辑来源清单数量不一致")
    for condition, specification in zip(fact.conditions_zh, specifications, strict=True):
        if (
            condition.summary_zh != specification.summary_zh
            or condition.evidence_ja != specification.evidence_ja
            or _page_key(str(condition.source_ref.source_url))
            != _page_key(str(specification.source_url))
            or not condition.locator.endswith(":" + specification.section_ja)
        ):
            raise ValueError(f"{name}: 获取条件说明或证据与编辑来源清单不一致")


def _validate_purchase(option: VehiclePurchaseOption) -> None:
    context = f"租赁{option.rental_number}号"
    _validate_ref(option.source_ref, _VEHICLE_TARGET, context)
    _expect_vehicle_page(option.source_ref, "レンタルタンク", context)
    if (option.source_ref.table_index, option.source_ref.row_index) != (
        0,
        option.rental_number - 1,
    ):
        raise ValueError(f"{context}: 购买选项的来源行不一致")
    for value in (option.defense_raw, option.ammunition_raw, option.cargo_raw):
        if re.fullmatch(r"[0-9]+", value) is None:
            raise ValueError(f"{context}: 防御、弹仓或车载原始值无法识别")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", option.weight_raw) is None:
        raise ValueError(f"{context}: 重量原始值无法识别")
    if re.fullmatch(r"[0-9]+(?:,[0-9]{3})*", option.price_raw) is None:
        raise ValueError(f"{context}: 价格原始值无法识别")


def _validate_trait_names(snapshot: VehicleTraitSnapshot, names: VehicleTraitNames) -> None:
    if snapshot.reference_note != names.reference_note or snapshot.limitations != names.limitations:
        raise ValueError("车辆特性快照的说明或限制与编辑清单不一致，请重新采集")
    if {item.name_ja for item in snapshot.records} != set(names.traits):
        raise ValueError("车辆特性快照与编辑名称清单不一致")
    for item in snapshot.records:
        description = VehicleTraitDescription(
            description=item.description,
            aliases=item.aliases,
            parameters=item.parameters,
            unknown_parameters=item.unknown_parameters,
            evidence_ids=item.evidence_ids,
        )
        if description != names.traits[item.name_ja]:
            raise ValueError(f"{item.name_ja}: 特性说明或参数与编辑清单不一致，请重新采集")
    rules = {rule.id: rule for rule in names.mount_rules}
    for rule in snapshot.mount_rules:
        if rule.model_dump(exclude={"verification_status"}) != rules[rule.id].model_dump():
            raise ValueError(f"{rule.name}: 双部件规则与编辑清单不一致，请重新采集")
    if set(snapshot.evidence) != set(names.evidence):
        raise ValueError("车辆特性快照与编辑证据清单不一致")
    for key, evidence in snapshot.evidence.items():
        specification = names.evidence[key]
        _validate_ref(evidence.source_ref, _TRAIT_TARGET, key)
        if (
            evidence.summary_zh != specification.summary_zh
            or evidence.applicability != specification.applicability
            or evidence.kind != specification.kind
            or _page_key(str(evidence.source_ref.source_url))
            != _page_key(str(specification.source_url))
            or f":{specification.section_ja}" not in evidence.locator
        ):
            raise ValueError(f"{key}: 特性证据与编辑来源清单不一致，请重新采集")


def _load_sources(
    repo_root: Path,
) -> tuple[VehicleSnapshot, VehicleNames, VehicleTraitSnapshot] | None:
    root = repo_root / _ROOT
    fact_path = root / "vehicles/facts.json"
    name_path = root / "vehicles/names.yaml"
    if not fact_path.exists():
        if name_path.exists():
            raise ValueError("战车来源快照缺失，请先采集")
        return None
    for path in (name_path, root / "vehicle-traits/facts.json", root / "vehicle-traits/names.yaml"):
        if not path.is_file():
            raise ValueError(f"战车标准化依赖文件缺失：{path}")
    snapshot = VehicleSnapshot.model_validate_json(fact_path.read_bytes())
    names = VehicleNames.model_validate(yaml.safe_load(name_path.read_text(encoding="utf-8")))
    if {fact.name_ja for fact in snapshot.records} != set(names.names):
        raise ValueError("战车快照与参考车型清单不一致")
    if sum(len(fact.individual_modifications) for fact in snapshot.records) != 22:
        raise ValueError("战车单孔改造表数量变化，需人工复核来源")
    for fact in snapshot.records:
        _validate_vehicle(fact, names)
    for option in snapshot.purchase_options:
        _validate_purchase(option)
    traits = load_vehicle_traits(repo_root)
    if traits.inventory.vehicle_content_hash != model_content_hash(snapshot):
        raise ValueError("车辆快照在读取期间发生变化，请重新执行标准化")
    trait_names = VehicleTraitNames.model_validate(
        yaml.safe_load((root / "vehicle-traits/names.yaml").read_text(encoding="utf-8"))
    )
    _validate_trait_names(traits, trait_names)
    known_traits = {item.name_ja for item in traits.records}
    if {option.trait_raw for option in snapshot.purchase_options} - known_traits:
        raise ValueError("租赁购买版本引用了没有说明的特性")
    refs = [
        *(ref for fact in snapshot.records for ref in _vehicle_refs(fact)),
        *(option.source_ref for option in snapshot.purchase_options),
        *(item.source_ref for item in traits.evidence.values()),
        *traits.inventory.design_source_refs,
    ]
    hashes: dict[tuple[str, str, str], str] = {}
    for ref in refs:
        key = (ref.target_id, urldefrag(str(ref.source_url))[0], ref.retrieved_at.isoformat())
        if key in hashes and hashes[key] != ref.content_hash:
            raise ValueError(f"同次采集的页面内容哈希不一致：{ref.source_url}")
        hashes[key] = ref.content_hash
    return snapshot, names, traits


def validate_vehicle_sources(repo_root: Path) -> bool:
    """离线验证车辆、参考名称和特性快照；来源未启用时返回False。"""
    return _load_sources(repo_root) is not None


def _reference_name(value: str, names: VehicleNames) -> str:
    result = normalize("NFKC", value)
    for original in sorted(names.names, key=lambda name: (-len(name), name)):
        reference = "狼" if original == "ウルフ" else names.names[original]
        result = result.replace(normalize("NFKC", original), reference)
    return result


def _setup(
    fact: VehicleFact, item: VehicleConfiguration, names: VehicleNames, traits: dict[str, str]
) -> VehicleSetup:
    key = (
        f"{fact.name_ja}\0{item.kind}\0{item.stage}\0{item.name_ja}"
        f"\0{item.source_ref.table_index}\0{item.source_ref.row_index}"
    )
    return VehicleSetup(
        id=stable_record_id("vehicles", "vehicle-setup", key),
        kind=item.kind,
        stage=item.stage,
        name_ja=item.name_ja,
        name_reference=_reference_name(item.name_ja, names),
        holes_raw=item.holes_raw,
        weight_raw=item.weight_raw,
        trait_ja=item.trait_raw,
        trait_name=(
            "设计时选择一项（见设计特性候选）"
            if item.trait_raw == _DESIGN_PLACEHOLDER
            else traits[item.trait_raw]
        ),
        cargo_raw=item.cargo_raw,
        fixed_armament_raw=item.fixed_armament_raw,
        source_ref=item.source_ref,
        issues=["来源未填写重量，保留空值，不按0t处理。"] if item.unresolved_fields else [],
    )


def _row_tables(table: VehicleRawTable, caption: str, *, initial: bool) -> list[ReferenceTable]:
    recognized = (
        table.headers == _INITIAL_HEADERS
        if initial
        else table.headers[:4] == _MODIFICATION_HEADERS
        and bool(table.headers[4:])
        and set(table.headers[4:]) == {"固定武器"}
    )
    if not recognized:
        return [
            ReferenceTable(
                caption=f"{caption} · 原表结构完整保留",
                headers=table.headers,
                rows=[row.values for row in table.rows],
                source_refs=_raw_table_refs(table),
            )
        ]
    return [
        ReferenceTable(
            caption=f"{caption} · {row.values[0]} · 原行{index + 1}",
            headers=["原字段", "原始值"],
            rows=[list(pair) for pair in zip(table.headers, row.values, strict=True)],
            source_refs=[row.source_ref],
        )
        for index, row in enumerate(table.rows)
    ]


def _acquisition_section(fact: VehicleFact, names: VehicleNames) -> ReferenceSection:
    return ReferenceSection(
        id="acquisition",
        title="获取方式与条件",
        paragraphs=[
            names.acquisition[fact.name_ja],
            *(item.summary_zh for item in fact.conditions_zh),
        ],
        tables=[
            ReferenceTable(
                caption="获取地点与方式（日文原文）",
                headers=["原文", "定位"],
                rows=[[item.text_ja, item.locator] for item in fact.acquisition_ja],
                source_refs=[item.source_ref for item in fact.acquisition_ja],
            ),
            *(
                ReferenceTable(
                    caption=f"获取条件证据{index + 1}",
                    headers=["项目", "来源内容"],
                    rows=[
                        ["参考说明", item.summary_zh],
                        *(["日文证据", value] for value in item.evidence_ja),
                        ["正文定位", item.locator],
                    ],
                    source_refs=[item.source_ref],
                )
                for index, item in enumerate(fact.conditions_zh)
            ),
        ],
        source_refs=[
            *(item.source_ref for item in fact.acquisition_ja),
            *(item.source_ref for item in fact.conditions_zh),
        ],
    )


def _initial_section(fact: VehicleFact) -> ReferenceSection:
    table = fact.initial_equipment
    return ReferenceSection(
        id="initial-equipment",
        title="初始装备",
        paragraphs=(
            [*table.context_ja, "按原表逐行展示；空白、缺件及“随选择变化”保留原值。"]
            if table is not None
            else ["来源没有单独列出本车型初始装备表；租赁购买版本另见购买选项。"]
        ),
        tables=_row_tables(table, "初始装备", initial=True) if table is not None else [],
        source_refs=(
            _raw_table_refs(table)
            if table is not None
            else [item.source_ref for item in fact.acquisition_ja]
        ),
    )


def _modification_section(fact: VehicleFact) -> ReferenceSection:
    refs = [ref for table in fact.individual_modifications for ref in _raw_table_refs(table)]
    paragraphs = [
        "各原表的适用配置和限制分别保留；括号、S、◯/S及空白按原文读取，不作为无条件许可。"
    ]
    for index, table in enumerate(fact.individual_modifications):
        paragraphs.append(
            f"原表{index + 1}适用条件（日文原文）："
            + (" / ".join(table.context_ja) if table.context_ja else "来源未另列条件标题")
        )
    if fact.branch_source_ref is not None:
        refs.append(fact.branch_source_ref)
        paragraphs.append("改造分支章节保留来源链接；不按配置行序或阶段推断升级连线。")
    return ReferenceSection(
        id="individual-modifications",
        title="单孔改造与适用条件",
        paragraphs=paragraphs,
        tables=[
            result
            for index, table in enumerate(fact.individual_modifications)
            for result in _row_tables(table, f"单孔改造原表{index + 1}", initial=False)
        ],
        source_refs=sorted_unique_source_refs(refs),
    )


def _parameter_rows(parameters: list[VehicleTraitParameter]) -> list[list[str]]:
    return [
        [f"参数：{item.label}（{item.applicability}）", f"{item.value}；条件：{item.conditions}"]
        for item in parameters
    ]


def _evidence_refs(ids: list[str], traits: VehicleTraitSnapshot) -> list[SourceRef]:
    return sorted_unique_source_refs([traits.evidence[key].source_ref for key in ids])


def _evidence_rows(ids: list[str], traits: VehicleTraitSnapshot) -> list[list[str]]:
    return [
        [
            f"来源记录（{traits.evidence[key].applicability}／{traits.evidence[key].kind}）",
            traits.evidence[key].summary_zh,
        ]
        for key in ids
    ]


def _trait_table(
    trait: VehicleTraitRecord,
    fact: VehicleFact,
    purchases: list[VehiclePurchaseOption],
    traits: VehicleTraitSnapshot,
) -> ReferenceTable:
    scope = []
    if any(item.trait_raw == trait.name_ja for item in fact.configurations):
        scope.append("底盘配置（以每个配置所列特性为准）")
    if fact.design_traits is not None and trait.name_ja in fact.design_traits.choices_ja:
        scope.append("巴特设计候选（任选一项）")
    scope.extend(item.name_ja for item in purchases if item.trait_raw == trait.name_ja)
    return ReferenceTable(
        caption=f"{trait.description.name}（{trait.name_ja}）",
        headers=["项目", "来源说明"],
        rows=[
            ["本车型涉及范围", "；".join(scope)],
            ["生效方式", trait.description.activation],
            ["作用", trait.description.effect],
            ["限制", trait.description.limits],
            *([["参考别名", "、".join(trait.aliases)]] if trait.aliases else []),
            *_parameter_rows(trait.parameters),
            *(["尚缺参数", value] for value in trait.unknown_parameters),
            *_evidence_rows(trait.evidence_ids, traits),
        ],
        source_refs=_evidence_refs(trait.evidence_ids, traits),
    )


def _relevant_traits(
    fact: VehicleFact, purchases: list[VehiclePurchaseOption], traits: VehicleTraitSnapshot
) -> list[VehicleTraitRecord]:
    relevant = {item.trait_raw for item in fact.configurations}
    relevant.update(item.trait_raw for item in purchases)
    if fact.design_traits is not None:
        relevant.update(fact.design_traits.choices_ja)
    relevant.discard(_DESIGN_PLACEHOLDER)
    return [trait for trait in traits.records if trait.name_ja in relevant]


def _traits_section(
    fact: VehicleFact, purchases: list[VehiclePurchaseOption], traits: VehicleTraitSnapshot
) -> ReferenceSection:
    paragraphs = [
        "以下汇集本车配置、设计候选及租赁购买版本涉及的特性；C装置对照数值保留原适用对象，不能作为底盘定值。"
    ]
    tables: list[ReferenceTable] = []
    refs: list[SourceRef] = []
    if fact.design_traits is not None:
        refs.append(fact.design_traits.source_ref)
        by_name = {item.name_ja: item.description.name for item in traits.records}
        paragraphs.append("四行均为阶段1的独立设计预设；“選択 *1”表示设计时从脚注选一项特性。")
        tables.append(
            ReferenceTable(
                caption="设计特性候选（日文脚注原顺序）",
                headers=["参考名", "日文原名"],
                rows=[[by_name[name], name] for name in fact.design_traits.choices_ja],
                source_refs=[fact.design_traits.source_ref],
            )
        )
    for trait in _relevant_traits(fact, purchases, traits):
        table = _trait_table(trait, fact, purchases, traits)
        tables.append(table)
        refs.extend(table.source_refs)
    return ReferenceSection(
        id="traits",
        title="特性作用、参数与待确认项",
        paragraphs=paragraphs,
        tables=tables,
        source_refs=sorted_unique_source_refs(refs),
    )


def _mount_rule_table(
    rule: VehicleMountRule, fact: VehicleFact, traits: VehicleTraitSnapshot
) -> ReferenceTable:
    support = fact.double_engine if rule.id == "double_engine" else fact.double_c_unit
    parameters = [
        parameter
        for parameter in rule.parameters
        if _STAGE_PARAMETER_VEHICLES.get(parameter.label, fact.name_ja) == fact.name_ja
    ]
    return ReferenceTable(
        caption=rule.name,
        headers=["项目", "来源说明"],
        rows=[
            ["本车型普通改造支持", "可" if support.supported else "不可"],
            ["本车型来源标记（日文原文）", support.value_ja],
            ["作用", rule.effect],
            ["限制", rule.limits],
            *_parameter_rows(parameters),
            *(["尚缺参数", value] for value in rule.unknown_parameters),
            *_evidence_rows(rule.evidence_ids, traits),
        ],
        source_refs=sorted_unique_source_refs(
            [support.source_ref, *_evidence_refs(rule.evidence_ids, traits)]
        ),
    )


def _mount_section(fact: VehicleFact, traits: VehicleTraitSnapshot) -> ReferenceSection:
    paragraphs = ["双引擎与双C装置为互斥选择；改造后不能恢复为两类部件都只有单件的状态。"]
    refs = [fact.double_engine.source_ref, fact.double_c_unit.source_ref]
    if fact.mount_exceptions:
        paragraphs.append(
            "野巴士的租赁10号以初始双引擎入手，是普通野巴士不可改双引擎的单独例外；改为双C装置后不能恢复双引擎。"
        )
        for exception in fact.mount_exceptions:
            paragraphs.append(f"例外原文：{exception.evidence_ja}")
            refs.append(exception.source_ref)
    tables = [_mount_rule_table(rule, fact, traits) for rule in traits.mount_rules]
    refs.extend(ref for table in tables for ref in table.source_refs)
    return ReferenceSection(
        id="mount-rules",
        title="双部件改造与不可逆限制",
        paragraphs=paragraphs,
        tables=tables,
        source_refs=sorted_unique_source_refs(refs),
    )


def _purchase_section(
    fact: VehicleFact,
    purchases: list[VehiclePurchaseOption],
    names: VehicleNames,
    traits: dict[str, str],
) -> ReferenceSection:
    tables = [
        ReferenceTable(
            caption=f"租赁{item.rental_number}号购买选项（{item.name_ja}）",
            headers=["项目", "来源原始值"],
            rows=[
                ["租赁编号（来源编号）", str(item.rental_number)],
                ["名称（日文原文）", item.name_ja],
                ["配置参考名", _reference_name(item.configuration_ja, names)],
                ["配置（日文原文）", item.configuration_ja],
                ["基础车型（日文原文）", item.base_vehicle_ja],
                ["防御", item.defense_raw],
                ["重量（t）", item.weight_raw],
                ["弹仓", item.ammunition_raw],
                ["特性参考名", traits[item.trait_raw]],
                ["特性（日文原文）", item.trait_raw],
                ["车载", item.cargo_raw],
                ["租赁店（日文原文）", item.shops_ja],
                ["购买价格（G）", item.price_raw],
            ],
            source_refs=[item.source_ref],
        )
        for item in purchases
    ]
    return ReferenceSection(
        id="purchase-options",
        title="对应租赁战车与购买价格",
        paragraphs=(
            ["租赁版本保留总表各自数值；型号与普通配置表不能完全对应时，不补造配置或合并数值。"]
            if purchases
            else ["来源租赁购买总表没有列出本车型的购买选项。"]
        ),
        tables=tables,
        source_refs=(
            [item.source_ref for item in purchases]
            if purchases
            else [item.source_ref for item in fact.acquisition_ja]
        ),
    )


def _attributes(fact: VehicleFact) -> list[ReferenceAttribute]:
    attributes = [
        ReferenceAttribute(label=f"{label}·{condition}", value=value)
        for label, stat in (("防御", fact.defense), ("弹仓", fact.ammunition))
        for condition, value in (
            ("最小", stat.minimum_raw),
            ("初始", stat.initial_raw),
            ("最大", stat.maximum_raw),
        )
    ]
    attributes.extend(
        ReferenceAttribute(
            label=label,
            value=("可选" if support.supported else "不可改造") + f"（原文：{support.value_ja}）",
        )
        for label, support in (("双引擎", fact.double_engine), ("双C装置", fact.double_c_unit))
    )
    return attributes


def _summary(fact: VehicleFact, names: VehicleNames, traits: VehicleTraitSnapshot) -> str:
    supports = []
    if fact.double_engine.supported:
        supports.append("双引擎")
    if fact.double_c_unit.supported:
        supports.append("双C装置")
    mount = "支持" + "／".join(supports) + ("（二者互斥）" if len(supports) == 2 else "")
    stages = {
        parameter.value
        for rule in traits.mount_rules
        for parameter in rule.parameters
        if _STAGE_PARAMETER_VEHICLES.get(parameter.label) == fact.name_ja
    }
    if len(stages) == 1:
        mount += f"；{next(iter(stages))}开放"
    elif stages:
        mount += "；" + "／".join(
            f"{rule.name}{parameter.value}开放"
            for rule in traits.mount_rules
            for parameter in rule.parameters
            if _STAGE_PARAMETER_VEHICLES.get(parameter.label) == fact.name_ja
        )
    if fact.mount_exceptions:
        mount += "；租赁10号初始双引擎为单独例外"
    kind = "设计预设" if fact.design_traits is not None else "来源配置"
    return f"{mount}。收录{len(fact.configurations)}项{kind}。{names.acquisition[fact.name_ja]}"


def load_vehicle_references(repo_root: Path) -> KnowledgeDataset | None:
    """合成16车型及355配置的来源资料，不推断升级路径或提升版本核验状态。"""
    sources = _load_sources(repo_root)
    if sources is None:
        return None
    snapshot, names, traits = sources
    trait_names = {trait.name_ja: trait.description.name for trait in traits.records}
    records = []
    for fact in snapshot.records:
        purchases = [
            item for item in snapshot.purchase_options if item.base_vehicle_ja == fact.name_ja
        ]
        setups = [_setup(fact, item, names, trait_names) for item in fact.configurations]
        refs = _vehicle_refs(fact)
        issues = list(
            dict.fromkeys([*fact.source_issues, *snapshot.limitations, *traits.limitations])
        )
        issues.extend(
            f"{item.name_ja}（阶段{item.stage}）：{issue}"
            for item in setups
            for issue in item.issues
        )
        notes = [
            names.reference_note,
            traits.reference_note,
            "配置参考名仅作NFKC规范化与已知底盘词替换，日文原名并列保留。",
            snapshot.source_locator_note,
            traits.source_locator_note,
            *issues,
        ]
        if fact.name_ja in names.notes:
            notes.insert(0, names.notes[fact.name_ja])
        sections = [
            _acquisition_section(fact, names),
            _initial_section(fact),
            _modification_section(fact),
            _traits_section(fact, purchases, traits),
            _mount_section(fact, traits),
            _purchase_section(fact, purchases, names, trait_names),
            ReferenceSection(
                id="source-issues",
                title="来源说明与待确认事项",
                paragraphs=list(dict.fromkeys(notes)),
                source_refs=refs,
            ),
        ]
        records.append(
            KnowledgeRecord(
                id=stable_record_id("vehicles", "vehicle", fact.name_ja),
                category="vehicles",
                names=NameSet(
                    ja=fact.name_ja,
                    zh_reference=names.names[fact.name_ja],
                    aliases=names.aliases.get(fact.name_ja, []),
                ),
                summary=_summary(fact, names, traits),
                attributes=_attributes(fact),
                sections=sections,
                vehicle=VehicleDetails(
                    double_engine_supported=fact.double_engine.supported,
                    double_c_unit_supported=fact.double_c_unit.supported,
                    configurations=setups,
                    design_traits_ja=fact.design_traits.choices_ja if fact.design_traits else [],
                    trait_terms=list(
                        dict.fromkeys(
                            term
                            for trait in _relevant_traits(fact, purchases, traits)
                            for term in [trait.name_ja, trait.description.name, *trait.aliases]
                        )
                    ),
                ),
                tags=[
                    "战车",
                    *(["双引擎"] if fact.double_engine.supported else []),
                    *(["双C装置"] if fact.double_c_unit.supported else []),
                    *(["巴特设计"] if fact.design_traits is not None else []),
                ],
                version_scope=["mm2r-jp"],
                verification_status="source_only",
                source_refs=refs,
                issues=issues,
            )
        )
    return KnowledgeDataset(category="vehicles", records=records)
