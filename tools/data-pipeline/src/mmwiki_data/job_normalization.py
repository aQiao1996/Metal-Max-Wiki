"""将职业技能事实离线整理为可追溯、保留旧身份的职业百科。"""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit

from mmwiki_data.job_skills import (
    _JOBS,
    _PAGES,
    _SOURCE_ALIASES,
    FactDraft,
    JobFact,
    JobSkillNames,
    JobSkillSnapshot,
    ReferencedFact,
    SkillConflict,
    SkillFact,
    SkillSourceValue,
    _conflicts,
    _legacy_value,
    load_job_skill_names,
    load_job_skills,
)
from mmwiki_data.job_skills import ConflictValue as SkillConflictValue
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
    NormalizedRecord,
    SourceRef,
    sorted_unique_source_refs,
    source_ref_key,
)

_ROOT = Path("data/raw/mm2r/0.99/job-skills")
_INTERIM = Path("data/interim/mm2r/0.99")
_LEVELS = ("Lv99", "Lv199", "Lv499", "Lv999")
_GROWTH_LABELS = {
    "HP": "HP",
    "戦闘Lv": "战斗等级",
    "運転Lv": "驾驶等级",
    "腕力": "腕力",
    "体力": "体力",
    "素早": "速度",
}
_CATEGORY_LABELS = {
    "オート": "自动",
    "クルマ": "乘车",
    "ゲージツ": "艺术",
    "バイク": "摩托",
    "人間": "白兵",
    "修理": "维修",
    "回復": "恢复",
    "犬": "犬",
    "移動": "移动",
}
_RAW_LABELS = {
    "attack_count_raw": "攻击次数",
    "attack_multiplier_raw": "攻击力倍率",
    "attribute_raw": "属性",
    "bonus_raw": "恢复增幅",
    "bug_attack_count_raw": "异常时攻击次数",
    "c_unit_defense_delta_raw": "C装置防御增量",
    "c_unit_weight_delta_raw": "C装置重量增量",
    "critical_rate_range_raw": "会心率范围",
    "damage_multiplier_raw": "伤害倍率",
    "defense_reference_raw": "防御力参照",
    "driving_level_raw": "驾驶等级",
    "duration_raw": "持续时间",
    "enemy_types_raw": "适用敌人种类",
    "engine_weight_delta_raw": "引擎重量增量",
    "first_hit_multiplier_raw": "首击倍率",
    "guide_duration_raw": "攻略本所述持续时间",
    "guide_resistance_bonus_raw": "攻略本所述抗性增幅",
    "human_job_count_raw": "人类职业数量",
    "later_hits_raw": "后续攻击",
    "level_condition_raw": "等级条件",
    "material_count_raw": "材料数量",
    "missing_hp_fraction_raw": "已损失HP的恢复比例",
    "observed_use_count_raw": "来源观测的使用次数",
    "performance_multiplier_raw": "能力倍率",
    "power_raw": "威力",
    "recovery_multiplier_raw": "恢复量倍率",
    "repair_kit_count_raw": "修理包数量",
    "source_estimated_bonus_raw": "来源估计的抗性增幅",
    "sub_job_level_cap_raw": "副职业等级上限",
    "success_rate_raw": "成功率",
    "target_raw": "对象或范围",
    "weapon_attack_delta_raw": "车载武器攻击增量",
    "weapon_weight_delta_raw": "车载武器重量增量",
    "category_raw": "技能分类",
}
_CONFLICT_LABELS = {
    "name_ja": "日文名称",
    "learning_level": "学习等级",
    "category": "技能分类",
    "target": "对象或范围",
}
_MAIN_SUB_RULES = (
    "human-main-and-sub-jobs",
    "unlock-sub-job",
    "sub-job-equipment",
    "sub-job-change",
    "field-skills-retained",
    "same-main-sub-use-counts",
    "sub-job-level-cap",
    "main-skill-use-cap-observation",
)
_PROTAGONIST_RULES = (
    "protagonist-job-selection",
    "protagonist-hunter-equivalence-and-exception",
    "protagonist-other-jobs",
)
_DOG_RULES = ("dog-no-sub-job", "dog-driving-level")
_SKILL_RULES = {
    "ハンターズアイ": "hunter-auto-requires-current-job",
    "ハンターマジック": "hunter-auto-requires-current-job",
    "薬の知識": "nurse-knowledge-retained",
}
_RULE_CODES = {
    *_MAIN_SUB_RULES,
    *_PROTAGONIST_RULES,
    *_DOG_RULES,
    *_SKILL_RULES.values(),
    "multi-rider-driving-level",
}
_USAGE_RULES = {
    "クルマ": (
        "context-vehicle",
        "乘车技能仅在战车或摩托乘车时可用，降车时不可用。",
        "乗車時のみ利用可能",
    ),
    "バイク": (
        "context-motorcycle",
        "摩托技能在摩托乘车或降车时可用，战车乘车时不可用。",
        "バイク乗車時と降車時",
    ),
    "人間": ("context-on-foot", "白兵技能仅在降车时可用。", "降車時のみ利用可能"),
    "犬": (
        "context-dog-ai",
        "犬由AI控制，技能不能由玩家逐条手动下令。",
        "自分で操作出来ず、行動はAI任せ",
    ),
}
_CONTEXT_SECTION = (
    "スキルアイコンのクルマとかバイクとか人間とか…使える状況がわかり辛い！ああわかり辛い！"
)


def _validate_page(ref: SourceRef, page: str, context: str) -> None:
    parsed = urlsplit(str(ref.source_url))
    if (
        ref.source_id != "metalmaniax-mm2r"
        or ref.target_id != f"maniax-job-skills-{_JOBS.get(page, page)}"
        or parsed.scheme != "https"
        or parsed.hostname != "metalmaniax.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.path != "/index.php"
        or unquote(parsed.query) != _PAGES[page]
        or not parsed.fragment
        or ref.retrieved_at.utcoffset() is None
    ):
        raise ValueError(f"{context}: 来源页面、身份或采集时间不一致：{ref.source_url}")


def _same_refs(actual: list[SourceRef], expected: list[SourceRef], context: str) -> None:
    if sorted_unique_source_refs(actual) != sorted_unique_source_refs(expected):
        raise ValueError(f"{context}: 聚合来源与字段出处不一致")


def _validate_fact(
    fact: ReferencedFact,
    draft: FactDraft,
    context: str,
    skill_source: SkillSourceValue | None = None,
) -> None:
    if (
        fact.code != draft.code
        or fact.summary_zh != draft.summary_zh
        or fact.evidence_ja != draft.evidence_ja
        or fact.raw_values != draft.raw_values
    ):
        raise ValueError(f"{context}: 中文事实、日文证据或原值与编辑清单不一致")
    _validate_page(fact.source_ref, draft.source_page, context)
    unknown = set(fact.raw_values) - set(_RAW_LABELS)
    if unknown:
        raise ValueError(f"{context}: 事实原值缺少中文字段标签：{sorted(unknown)}")
    is_skill_row = (
        skill_source is not None
        and draft.section_ja == "習得特技"
        and draft.source_page == skill_source.job_ja
    )
    if is_skill_row and skill_source is not None:
        if (
            fact.location_kind != "table"
            or fact.locator != f"{draft.section_ja} / {skill_source.name_ja}"
            or fact.source_ref != skill_source.source_ref
        ):
            raise ValueError(f"{context}: 技能机制未对应到同一原表行")
    elif (
        fact.location_kind != "section"
        or fact.locator != draft.section_ja
        or (fact.source_ref.table_index, fact.source_ref.row_index) != (0, 0)
    ):
        raise ValueError(f"{context}: 正文事实的章节出处不一致")


def _legacy_records(
    bundle: NormalizedBundle, domain: str, size: int
) -> dict[str, NormalizedRecord]:
    if bundle.domain != domain or len(bundle.records) != size:
        raise ValueError(f"职业标准化依赖的{domain}数据包分类或数量不正确")
    records: dict[str, NormalizedRecord] = {}
    for record in bundle.records:
        name = record.names.ja
        if (
            name is None
            or name in records
            or record.kind != ("job" if domain == "jobs" else "skill")
            or record.version_scope != ["mm2r-jp"]
            or record.verification_status.value != "source_only"
        ):
            raise ValueError(f"{record.id}: 既有日文身份、分类或版本依据不一致")
        records[name] = record
    return records


def _validate_job(
    job: JobFact, names: JobSkillNames, legacy: NormalizedRecord, position: int
) -> None:
    if (
        job.id != legacy.id
        or job.number_raw != legacy.attributes.get("number_raw")
        or job.number_raw != str(position)
        or job.name_zh_reference != names.job_names[job.name_ja]
        or job.summary_zh != names.job_summaries[job.name_ja].summary_zh
        or job.summary_zh != job.role.summary_zh
    ):
        raise ValueError(f"{job.name_ja}: 职业身份、名称或用途与依赖不一致")
    _validate_fact(job.role, names.job_summaries[job.name_ja], job.name_ja)
    samples = {sample.level_raw: sample for sample in job.growth_samples}
    for offset, level in enumerate(_LEVELS):
        sample = samples[level]
        _validate_page(sample.source_ref, "growth", f"{job.name_ja}/{level}")
        if (sample.source_ref.table_index, sample.source_ref.row_index) != (
            0,
            position + offset * 10,
        ):
            raise ValueError(f"{job.name_ja}/{level}: 成长观测的职业行或等级段错配")
    _same_refs(
        job.source_refs,
        [*legacy.source_refs, job.role.source_ref, *(s.source_ref for s in samples.values())],
        job.name_ja,
    )


def _validate_usage(skill: SkillFact, source: SkillSourceValue) -> None:
    specification = _USAGE_RULES.get(source.category_raw)
    if specification is None:
        if skill.usage_restrictions:
            raise ValueError(f"{skill.name_ja}: 未定义统一使用场景的分类被套用了限制")
        return
    if len(skill.usage_restrictions) != 1:
        raise ValueError(f"{skill.name_ja}: 缺少唯一的职业技能使用场景限制")
    code, summary, evidence = specification
    draft = FactDraft(
        code=code,
        source_page="犬" if source.category_raw == "犬" else "faq",
        section_ja="概要" if source.category_raw == "犬" else _CONTEXT_SECTION,
        summary_zh=summary,
        evidence_ja=[evidence],
        raw_values={} if source.category_raw == "犬" else {"category_raw": source.category_raw},
    )
    _validate_fact(skill.usage_restrictions[0], draft, f"{skill.name_ja}使用限制")


def _expected_conflicts(
    old: SkillSourceValue, new: SkillSourceValue, skill: SkillFact
) -> list[SkillConflict]:
    # 沿用采集器的冲突比较，防止离线转换与原快照采用不同的学习级别口径。
    conflicts = _conflicts(old, new)
    for fact in skill.mechanics:
        target = fact.raw_values.get("target_raw")
        if target and old.target_raw and target != old.target_raw:
            conflicts.append(
                SkillConflict(
                    field="target",
                    summary_zh="来源对攻击范围的记载不同；中文参考采用有明确范围的记载，未由0.99实机裁定。",
                    values=[
                        SkillConflictValue(value_raw=old.target_raw, source_ref=old.source_ref),
                        SkillConflictValue(value_raw=target, source_ref=fact.source_ref),
                    ],
                )
            )
    return conflicts


def _validate_skill(
    skill: SkillFact,
    names: JobSkillNames,
    legacy: NormalizedRecord,
    job: JobFact,
    row: int,
) -> None:
    if (
        skill.id != legacy.id
        or skill.job_id != job.id
        or skill.job_ja != job.name_ja
        or skill.canonical_name_ja != _SOURCE_ALIASES.get(skill.name_ja, skill.name_ja)
        or skill.name_zh_reference != names.skill_names[skill.name_ja]
        or skill.summary_zh != names.skill_summaries[skill.name_ja]
        or skill.target_zh != names.skill_targets[skill.name_ja]
        or len(skill.source_values) != 2
    ):
        raise ValueError(f"{skill.name_ja}: 技能身份、中文编辑或双来源数量不一致")
    old, new = skill.source_values
    if old != _legacy_value(legacy):
        raise ValueError(f"{skill.name_ja}: DQFF原值或出处已偏离既有技能数据包")
    expected_condition = {
        "男気パンチ": "男・麗人",
        "パンチラキック": "女・オカマ",
    }.get(skill.canonical_name_ja)
    expected_condition_zh = {
        "男・麗人": "男性或丽人（来源性别分类）",
        "女・オカマ": "女性或女装男性（来源オカマ分类）",
    }.get(expected_condition or "")
    if (
        new.name_ja != skill.canonical_name_ja
        or new.job_ja != skill.job_ja
        or new.number_raw is not None
        or new.target_raw is not None
        or new.learning_level_raw != skill.learning_level_raw
        or new.uses_at_lv99_raw != skill.uses_at_lv99_raw
        or new.learning_condition_raw != expected_condition
        or skill.learning_condition_zh != expected_condition_zh
        or new.category_raw not in _CATEGORY_LABELS
    ):
        raise ValueError(f"{skill.name_ja}: 完整来源表与展示字段、学习条件不一致")
    _validate_page(new.source_ref, job.name_ja, skill.name_ja)
    if (new.source_ref.table_index, new.source_ref.row_index) != (0, row):
        raise ValueError(f"{skill.name_ja}: 完整来源表的行顺序或职业归属不一致")
    drafts = names.mechanics.get(skill.name_ja, [])
    if len(skill.mechanics) != len(drafts):
        raise ValueError(f"{skill.name_ja}: 技能机制没有完整对应编辑事实")
    for fact, draft in zip(skill.mechanics, drafts, strict=True):
        _validate_fact(fact, draft, skill.name_ja, new)
    _validate_usage(skill, new)
    if skill.conflicts != _expected_conflicts(old, new, skill):
        raise ValueError(f"{skill.name_ja}: 双来源冲突遗漏或原值、出处不一致")
    _same_refs(
        skill.source_refs,
        [old.source_ref, new.source_ref]
        + [fact.source_ref for fact in [*skill.mechanics, *skill.usage_restrictions]],
        skill.name_ja,
    )


def _snapshot_refs(snapshot: JobSkillSnapshot) -> list[SourceRef]:
    refs = [ref for job in snapshot.jobs for ref in job.source_refs]
    refs.extend(job.role.source_ref for job in snapshot.jobs)
    refs.extend(sample.source_ref for job in snapshot.jobs for sample in job.growth_samples)
    refs.extend(rule.source_ref for rule in snapshot.rules)
    refs.extend(coverage.source_ref for coverage in snapshot.coverage)
    for skill in snapshot.skills:
        refs.extend(skill.source_refs)
        refs.extend(value.source_ref for value in skill.source_values)
        refs.extend(fact.source_ref for fact in [*skill.mechanics, *skill.usage_restrictions])
        refs.extend(value.source_ref for conflict in skill.conflicts for value in conflict.values)
    return refs


def _validate_source_pages(snapshot: JobSkillSnapshot, legacy_refs: list[SourceRef]) -> None:
    target_pages = {f"maniax-job-skills-{_JOBS.get(page, page)}": page for page in _PAGES}
    allowed_legacy = {source_ref_key(ref) for ref in legacy_refs}
    signatures: dict[str, tuple[str, str]] = {}
    for ref in _snapshot_refs(snapshot):
        if ref.source_id != "metalmaniax-mm2r":
            if source_ref_key(ref) not in allowed_legacy:
                raise ValueError(f"职业技能快照包含无法对应既有数据包的来源：{ref.target_id}")
            continue
        page = target_pages.get(ref.target_id)
        if page is None:
            raise ValueError(f"职业技能快照引用了11页清单之外的来源：{ref.target_id}")
        _validate_page(ref, page, ref.target_id)
        signature = (ref.content_hash, ref.retrieved_at.isoformat())
        if ref.target_id in signatures and signatures[ref.target_id] != signature:
            raise ValueError(f"{ref.target_id}: 同页出处的内容哈希或采集时间不一致")
        signatures[ref.target_id] = signature
    if set(signatures) != set(target_pages):
        raise ValueError("职业技能快照没有完整对应11个公开来源页面")


def _load_sources(
    repo_root: Path, rebuilt_bundles: Mapping[str, NormalizedBundle] | None = None
) -> JobSkillSnapshot | None:
    paths = (
        repo_root / _ROOT / "facts.json",
        repo_root / _ROOT / "names.yaml",
        repo_root / _INTERIM / "jobs.json",
        repo_root / _INTERIM / "skills.json",
    )
    if not any(path.exists() for path in paths[:2]):
        return None
    required = paths if rebuilt_bundles is None else paths[:2]
    for path in required:
        if not path.is_file():
            raise ValueError(f"职业标准化依赖文件缺失或不是文件：{path}")
    snapshot = load_job_skills(repo_root)
    if snapshot is None:
        raise ValueError("职业技能事实快照在读取前已消失")
    names = load_job_skill_names(repo_root)

    def legacy_bundle(domain: str, path: Path) -> NormalizedBundle:
        if rebuilt_bundles is None:
            return NormalizedBundle.model_validate_json(path.read_bytes())
        key = f"data/interim/mm2r/0.99/{domain}.json"
        if key not in rebuilt_bundles:
            raise ValueError(f"职业标准化缺少本次重建依赖：{key}")
        return rebuilt_bundles[key]

    legacy_jobs = _legacy_records(legacy_bundle("jobs", paths[2]), "jobs", 7)
    legacy_skills = _legacy_records(legacy_bundle("skills", paths[3]), "skills", 65)
    if (
        set(legacy_jobs) != set(_JOBS)
        or set(names.skill_names) != set(legacy_skills)
        or {skill.name_ja for skill in snapshot.skills} != set(legacy_skills)
        or len(snapshot.skills) != 65
        or snapshot.reference_note != names.reference_note
        or snapshot.limitations != names.limitations
        or {rule.code for rule in snapshot.rules} != _RULE_CODES
        or {rule.code for rule in names.rules} != _RULE_CODES
        or len(snapshot.rules) != len(_RULE_CODES)
    ):
        raise ValueError("职业技能快照、中文清单或既有65项技能的覆盖不一致")
    job_by_name = {job.name_ja: job for job in snapshot.jobs}
    coverage_by_name = {item.job_ja: item for item in snapshot.coverage}
    for position, name in enumerate(_JOBS, start=1):
        job = job_by_name[name]
        _validate_job(job, names, legacy_jobs[name], position)
        skills = [skill for skill in snapshot.skills if skill.job_ja == name]
        expected_count = 5 if name == "犬" else 10
        if len(skills) != expected_count:
            raise ValueError(f"{name}: 职业内完整技能数量不一致")
        for row, skill in enumerate(skills, start=2):
            _validate_skill(skill, names, legacy_skills[skill.name_ja], job, row)
        coverage = coverage_by_name[name]
        _validate_page(coverage.source_ref, name, f"{name}完整技能表")
        if (
            coverage.source_skill_rows != expected_count
            or coverage.matched_interim_rows != expected_count
            or coverage.missing_from_interim
            or (coverage.source_ref.table_index, coverage.source_ref.row_index) != (0, 0)
            or coverage.source_ref.source_url != skills[0].source_values[1].source_ref.source_url
        ):
            raise ValueError(f"{name}: 完整技能表的覆盖数量或出处不一致")
    if len(snapshot.rules) != len(names.rules):
        raise ValueError("职业规则事实数量与编辑清单不一致")
    for rule, draft in zip(snapshot.rules, names.rules, strict=True):
        _validate_fact(rule, draft, "职业规则")
    _validate_source_pages(
        snapshot,
        [
            ref
            for record in [*legacy_jobs.values(), *legacy_skills.values()]
            for ref in record.source_refs
        ],
    )
    return snapshot


def validate_job_sources(repo_root: Path) -> bool:
    """离线校验职业快照、中文编辑、既有身份与11页出处；部分依赖缺失即失败。"""
    return _load_sources(repo_root) is not None


def _source_label(ref: SourceRef) -> str:
    return "METAL MAniaX" if ref.source_id == "metalmaniax-mm2r" else "DQFF"


def _fact_table(fact: ReferencedFact, caption: str) -> ReferenceTable:
    return ReferenceTable(
        caption=caption,
        headers=["项目", "原始值或依据"],
        rows=[
            ["中文参考说明", fact.summary_zh],
            *[["日文依据", evidence] for evidence in fact.evidence_ja],
            *[[_RAW_LABELS[field], value] for field, value in fact.raw_values.items()],
        ],
        source_refs=[fact.source_ref],
    )


def _skill_source_table(skill: SkillFact, source: SkillSourceValue) -> ReferenceTable:
    pairs = [
        ("技能日文名", source.name_ja),
        ("职业日文名", source.job_ja),
        ("来源编号", source.number_raw),
        ("技能分类", source.category_raw),
        ("学习等级", source.learning_level_raw),
        ("学习条件", source.learning_condition_raw),
        ("对象或范围", source.target_raw),
        ("Lv99使用次数", source.uses_at_lv99_raw),
    ]
    return ReferenceTable(
        caption=f"{skill.name_zh_reference} · {_source_label(source.source_ref)}原表",
        headers=["项目", "来源原值"],
        rows=[[label, value if value is not None else "（未记载）"] for label, value in pairs],
        source_refs=[source.source_ref],
    )


def _skill_section(skill: SkillFact, rules: dict[str, ReferencedFact]) -> ReferenceSection:
    source = skill.source_values[1]
    rows = [
        ["学习等级", f"Lv{skill.learning_level_raw}"],
        ["Lv99使用次数（原值）", skill.uses_at_lv99_raw],
        ["对象或范围", skill.target_zh],
        ["技能分类", _CATEGORY_LABELS[source.category_raw]],
        ["日文身份", skill.name_ja],
    ]
    if skill.canonical_name_ja != skill.name_ja:
        rows.append(["完整来源表日文名", skill.canonical_name_ja])
    if skill.learning_condition_zh is not None:
        rows.append(["学习条件", skill.learning_condition_zh])
    paragraphs = [skill.summary_zh]
    paragraphs.extend(f"机制：{fact.summary_zh}" for fact in skill.mechanics)
    paragraphs.extend(f"使用限制：{fact.summary_zh}" for fact in skill.usage_restrictions)
    refs = [*skill.source_refs]
    specific_rule = _SKILL_RULES.get(skill.canonical_name_ja)
    if specific_rule is not None:
        paragraphs.append(f"职业条件：{rules[specific_rule].summary_zh}")
        refs.append(rules[specific_rule].source_ref)
    tables = [
        ReferenceTable(
            caption="学习与使用",
            headers=["项目", "中文参考或来源数值"],
            rows=rows,
            source_refs=[value.source_ref for value in skill.source_values],
        )
    ]
    if skill.conflicts:
        paragraphs.extend(dict.fromkeys(conflict.summary_zh for conflict in skill.conflicts))
        tables.append(
            ReferenceTable(
                caption="双来源差异（尚未由0.99实机裁定）",
                headers=["有差异的项目", "来源", "来源原值"],
                rows=[
                    [
                        _CONFLICT_LABELS[conflict.field],
                        _source_label(value.source_ref),
                        value.value_raw,
                    ]
                    for conflict in skill.conflicts
                    for value in conflict.values
                ],
                source_refs=[
                    value.source_ref for conflict in skill.conflicts for value in conflict.values
                ],
            )
        )
    return ReferenceSection(
        id=skill.id,
        title=skill.name_zh_reference,
        paragraphs=paragraphs,
        tables=tables,
        source_refs=sorted_unique_source_refs(refs),
    )


def _rule_sections(
    job: JobFact, rules: dict[str, ReferencedFact]
) -> tuple[list[ReferenceSection], list[ReferencedFact]]:
    groups: list[tuple[str, str, tuple[str, ...]]]
    if job.name_ja == "犬":
        groups = [("job-restrictions", "犬的职业限制", _DOG_RULES)]
    else:
        protagonist = (
            "protagonist-hunter-equivalence-and-exception"
            if job.name_ja == "ハンター"
            else "protagonist-other-jobs"
        )
        groups = [
            ("main-sub-jobs", "主职业与副职业", _MAIN_SUB_RULES),
            ("protagonist", "主角选择此职业时", ("protagonist-job-selection", protagonist)),
            ("driving", "多人乘车时的驾驶等级", ("multi-rider-driving-level",)),
        ]
    sections: list[ReferenceSection] = []
    applied: list[ReferencedFact] = []
    for section_id, title, codes in groups:
        facts = [rules[code] for code in codes]
        applied.extend(facts)
        sections.append(
            ReferenceSection(
                id=section_id,
                title=title,
                paragraphs=[fact.summary_zh for fact in facts],
                source_refs=sorted_unique_source_refs([fact.source_ref for fact in facts]),
            )
        )
    return sections, applied


def _growth_section(job: JobFact) -> ReferenceSection:
    samples = {sample.level_raw: sample for sample in job.growth_samples}
    return ReferenceSection(
        id="growth-observations",
        title="不同等级的成长观测",
        paragraphs=[
            "以下是来源记录的观测值；测量条件未全部注明，不能据此推算固定逐级成长率，"
            "也不保证每名同职业角色的数值完全相同。"
        ],
        tables=[
            ReferenceTable(
                caption=f"{level}观测值",
                headers=["属性", "来源观测值"],
                rows=[
                    [label, samples[level].values_raw[field]]
                    for field, label in _GROWTH_LABELS.items()
                ],
                source_refs=[samples[level].source_ref],
            )
            for level in _LEVELS
        ],
        source_refs=[sample.source_ref for sample in job.growth_samples],
    )


def _raw_section(
    job: JobFact, skills: list[SkillFact], rules: list[ReferencedFact]
) -> ReferenceSection:
    tables = [_fact_table(job.role, "职业用途的日文依据")]
    tables.extend(
        _skill_source_table(skill, source) for skill in skills for source in skill.source_values
    )
    tables.extend(
        _fact_table(fact, f"{skill.name_zh_reference} · 机制依据 {index}")
        for skill in skills
        for index, fact in enumerate(skill.mechanics, start=1)
    )
    restrictions = {fact.code: fact for skill in skills for fact in skill.usage_restrictions}
    tables.extend(
        _fact_table(fact, f"使用场景依据 {index}")
        for index, fact in enumerate(restrictions.values(), start=1)
    )
    tables.extend(
        _fact_table(fact, f"职业规则依据 {index}") for index, fact in enumerate(rules, start=1)
    )
    return ReferenceSection(
        id="raw-source-tables",
        title="原表对照与日文依据",
        paragraphs=["“（未记载）”表示该来源没有对应字段；短横线及其他原值均按来源保留。"],
        tables=tables,
        source_refs=sorted_unique_source_refs(
            [ref for table in tables for ref in table.source_refs]
        ),
    )


def load_job_references(
    repo_root: Path, *, rebuilt_bundles: Mapping[str, NormalizedBundle] | None = None
) -> KnowledgeDataset | None:
    """生成7个职业正文与65个稳定技能章节，保留原值且不提升版本核验状态。"""
    snapshot = _load_sources(repo_root, rebuilt_bundles)
    if snapshot is None:
        return None
    rules = {rule.code: rule for rule in snapshot.rules}
    coverage = {item.job_ja: item for item in snapshot.coverage}
    records: list[KnowledgeRecord] = []
    for job in snapshot.jobs:
        skills = [skill for skill in snapshot.skills if skill.job_id == job.id]
        rule_sections, applied_rules = _rule_sections(job, rules)
        specific_codes = {
            _SKILL_RULES[skill.canonical_name_ja]
            for skill in skills
            if skill.canonical_name_ja in _SKILL_RULES
        }
        applied_rules.extend(rules[code] for code in sorted(specific_codes))
        sections = [
            _growth_section(job),
            *rule_sections,
            *[_skill_section(skill, rules) for skill in skills],
            _raw_section(job, skills, applied_rules),
            ReferenceSection(
                id="source-issues",
                title="资料适用范围",
                paragraphs=[
                    snapshot.reference_note,
                    "技能学习等级与Lv99次数采用METAL MAniaX表格口径。"
                    "DQFF的旧名、学习等级、分类与对象保留在原表对照；差异未由0.99实机裁定。",
                    "次数栏的短横线保留原写法，不统一解释为无限使用；"
                    "自动技能及特殊触发条件见对应技能。",
                    "来源没有完整的逐级属性及技能次数成长公式。",
                ],
                source_refs=sorted_unique_source_refs(
                    [job.role.source_ref, *(skill.source_values[1].source_ref for skill in skills)]
                ),
            ),
        ]
        records.append(
            KnowledgeRecord(
                id=job.id,
                category="jobs",
                names=NameSet(
                    ja=job.name_ja,
                    zh_reference=job.name_zh_reference,
                    aliases=["狗", "战犬"] if job.name_ja == "犬" else [],
                ),
                summary=job.summary_zh,
                attributes=[
                    ReferenceAttribute(label="职业编号", value=job.number_raw),
                    ReferenceAttribute(label="技能数量", value=str(len(skills))),
                    ReferenceAttribute(
                        label="可设置副职业", value="否" if job.name_ja == "犬" else "是"
                    ),
                ],
                sections=sections,
                tags=["职业", "技能", "成长观测", "犬" if job.name_ja == "犬" else "主副职业"],
                version_scope=[snapshot.version_scope],
                verification_status=snapshot.verification_status,
                source_refs=[
                    *job.source_refs,
                    coverage[job.name_ja].source_ref,
                    *(ref for skill in skills for ref in skill.source_refs),
                ],
                issues=sorted({conflict.field for skill in skills for conflict in skill.conflicts}),
            )
        )
    return KnowledgeDataset(category="jobs", records=sorted(records, key=lambda record: record.id))
