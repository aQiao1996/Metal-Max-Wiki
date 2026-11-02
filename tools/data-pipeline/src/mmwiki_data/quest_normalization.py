"""把101项日版任务及8条中文旧表整理成可追溯的任务正文。"""

from pathlib import Path

import yaml

from mmwiki_data.knowledge_models import (
    KnowledgeDataset,
    KnowledgeRecord,
    ReferenceAttribute,
    ReferenceSection,
    ReferenceTable,
)
from mmwiki_data.normalization import stable_record_id
from mmwiki_data.normalization_models import (
    NameSet,
    NormalizedBundle,
    NormalizedRecord,
    SourceRef,
    sorted_unique_source_refs,
)
from mmwiki_data.quests import (
    INDEX_URL,
    SOURCE_ID,
    ZZJB_SOURCE_ID,
    ZZJB_TARGET_ID,
    ZZJB_URL,
    QuestDetailField,
    QuestFact,
    QuestNames,
    QuestSnapshot,
)
from mmwiki_data.storage import model_content_hash

_ROOT = Path("data/raw/mm2r/0.99/quests")
_LEGACY = Path("data/interim/mm2r/0.99/quests.json")
_KIND_LABELS = {"ordinary_or_event": "普通任务", "special_request": "特别委托"}
_FIELD_LABELS = {
    "No.": "编号",
    "名称": "任务名称",
    "受注場所": "接取地点",
    "開始条件": "接取条件",
    "達成条件": "完成条件",
    "経験値": "经验值",
    "有名度": "有名度",
    "報酬(条件)": "其他报酬与条件",
}
_DETAIL_LABELS = {"発生場所": "接取地点", "発生条件": "接取条件", "報酬": "报酬"}
_MISSING = {
    "location": "来源未明确提供接取地点。",
    "acceptance": "来源未明确提供接取条件。",
    "rewards": "来源未明确提供报酬。",
    "failure_conditions": "来源未明确提供失败或错过条件，不代表不存在此类条件。",
}
_LEGACY_ATTRIBUTES = {
    "experience": "经验值",
    "experience_raw": "经验值（原值）",
    "fame": "有名度",
    "fame_raw": "有名度（原值）",
    "location_raw": "接取地点（原值）",
    "notes_raw": "备注（原值）",
    "reward_raw": "报酬（原值）",
}


def _references(fact: QuestFact, inherited: NormalizedRecord | None) -> list[SourceRef]:
    refs = [
        fact.overview.source_ref,
        *(field.source_ref for field in fact.detail_fields),
        *fact.summary_refs,
        *fact.failure_conditions.source_refs,
    ]
    if fact.chinese_reference is not None:
        refs.append(fact.chinese_reference.source_ref)
    if inherited is not None:
        refs.extend(inherited.source_refs)
    return sorted_unique_source_refs(refs)


def _validate_fact(fact: QuestFact, names: QuestNames) -> None:
    reference = names.quests[fact.number]
    if (
        fact.name_ja,
        fact.name_zh_reference,
        fact.aliases,
        fact.location_zh,
        fact.acceptance_zh,
        fact.steps_zh,
        fact.reward_notes_zh,
        fact.source_uncertainties_zh,
        fact.vehicle_related,
    ) != (
        reference.name_ja,
        reference.name_zh_reference,
        reference.aliases,
        reference.location_zh,
        reference.acceptance_zh,
        reference.steps_zh,
        reference.reward_notes_zh,
        reference.source_uncertainties_zh,
        reference.vehicle_related,
    ):
        raise ValueError(f"{fact.name_ja}: 任务快照与中文参考清单不一致，请重新采集")
    special = "特別な依頼" in fact.overview.fields["開始条件"] or any(
        "特別な依頼" in value for value in fact.detail_fields[1].values_ja_raw
    )
    if (fact.request_kind == "special_request") != special:
        raise ValueError(f"{fact.name_ja}: 特别委托标记与原表或详情接取条件不一致")
    if len(fact.summary_refs) != len(reference.detail_checks) + 1:
        raise ValueError(f"{fact.name_ja}: 任务摘要证据小节不完整")
    if fact.summary_refs[0] != fact.overview.source_ref:
        raise ValueError(f"{fact.name_ja}: 任务摘要没有沿用本条总表来源")
    if reference.failure_notes_zh is None:
        if fact.failure_conditions.status != "not_documented":
            raise ValueError(f"{fact.name_ja}: 未知失败条件被改成了已记载结论")
    elif (
        fact.failure_conditions.status != "documented"
        or fact.failure_conditions.notes_zh != reference.failure_notes_zh
        or fact.failure_conditions.source_refs != fact.summary_refs[1:]
    ):
        raise ValueError(f"{fact.name_ja}: 失败或错过条件与来源证据不一致")
    detail_hashes = {field.source_ref.content_hash for field in fact.detail_fields}
    if len(detail_hashes) != 1:
        raise ValueError(f"{fact.name_ja}: 同一任务详情的小节来自不同内容快照")
    for ref in fact.summary_refs[1:]:
        if ref.content_hash not in detail_hashes:
            raise ValueError(f"{fact.name_ja}: 任务摘要与详情事实的内容哈希不一致")


def _validate_legacy(
    legacy: NormalizedBundle, snapshot: QuestSnapshot
) -> dict[str, NormalizedRecord]:
    if legacy.domain != "quests" or len(legacy.records) != 8:
        raise ValueError("既有任务数据包必须完整保留8项中文旧表记录")
    expected = {
        record.name_ja: record.chinese_reference
        for record in snapshot.records
        if record.chinese_reference is not None
    }
    by_name: dict[str, NormalizedRecord] = {}
    for record in legacy.records:
        name = record.names.ja
        if name is None or name not in expected or name in by_name or record.kind != "quest":
            raise ValueError(f"{record.id}: 既有任务身份与中文旧表没有一一对应")
        chinese = expected[name]
        if chinese is None:
            raise ValueError(f"{record.id}: 既有任务缺少中文原表对照")
        if set(record.attributes) - set(_LEGACY_ATTRIBUTES):
            raise ValueError(f"{record.id}: 既有任务包含尚未核对的原字段")
        if len(record.source_refs) != 1:
            raise ValueError(f"{record.id}: 既有任务来源未唯一对应中文旧表原行")
        ref = record.source_refs[0]
        if (
            ref.source_id != ZZJB_SOURCE_ID
            or ref.target_id != ZZJB_TARGET_ID
            or str(ref.source_url) != ZZJB_URL
            or (ref.table_index, ref.row_index)
            != (chinese.source_ref.table_index, chinese.source_ref.row_index)
        ):
            raise ValueError(f"{record.id}: 既有任务来源与中文旧表行身份不一致")
        by_name[name] = record
    if set(by_name) != set(expected):
        raise ValueError("既有8项任务没有完整对应已采中文旧表")
    return by_name


def _load_sources(
    repo_root: Path, *, rebuilt_bundle: NormalizedBundle | None = None
) -> tuple[QuestSnapshot, QuestNames, dict[str, NormalizedRecord]] | None:
    required = [repo_root / _ROOT / filename for filename in ("facts.json", "names.yaml")]
    if not any(path.exists() for path in required):
        return None
    for path in [*required, repo_root / _LEGACY]:
        if not path.is_file():
            raise FileNotFoundError(f"任务资料依赖缺失：{path}")
    snapshot = QuestSnapshot.model_validate_json(required[0].read_bytes())
    names = QuestNames.model_validate(yaml.safe_load(required[1].read_text(encoding="utf-8")))
    if (snapshot.reference_note, snapshot.coverage_note) != (
        names.reference_note,
        names.coverage_note,
    ):
        raise ValueError("任务快照的中文参考名或覆盖范围说明已过期")
    for fact in snapshot.records:
        _validate_fact(fact, names)
    if sum(fact.request_kind == "special_request" for fact in snapshot.records) != 25:
        raise ValueError("任务快照应保留25项有据的特别委托")
    if sum(fact.failure_conditions.status == "documented" for fact in snapshot.records) != 21:
        raise ValueError("任务快照应保留21项有据的失败或错过说明")
    overview_refs = [fact.overview.source_ref for fact in snapshot.records]
    if len({(str(ref.source_url), ref.content_hash) for ref in overview_refs}) != 1:
        raise ValueError("任务总表的101项记录来自不同内容快照")
    if any(ref.source_id != SOURCE_ID or str(ref.source_url) != INDEX_URL for ref in overview_refs):
        raise ValueError("任务总表来源不一致")
    legacy = NormalizedBundle.model_validate_json((repo_root / _LEGACY).read_bytes())
    if rebuilt_bundle is not None:
        if model_content_hash(rebuilt_bundle) != model_content_hash(legacy):
            raise ValueError("本轮任务数据包与已采任务依赖的8项旧记录不一致，请先复核来源")
        legacy = rebuilt_bundle
    inherited = _validate_legacy(legacy, snapshot)
    return snapshot, names, inherited


def validate_quest_sources(
    repo_root: Path, *, rebuilt_bundle: NormalizedBundle | None = None
) -> bool:
    """离线核对101项任务、中文摘要及8项旧记录的身份与来源。"""
    return _load_sources(repo_root, rebuilt_bundle=rebuilt_bundle) is not None


def _detail_table(field: QuestDetailField) -> ReferenceTable:
    return ReferenceTable(
        caption=f"详情原文 · {_DETAIL_LABELS[field.section_ja]}",
        headers=["项目", "日文原值"],
        rows=[[f"第{index}项", value] for index, value in enumerate(field.values_ja_raw, 1)],
        source_refs=[field.source_ref],
    )


def _raw_tables(fact: QuestFact, inherited: NormalizedRecord | None) -> list[ReferenceTable]:
    tables = [
        ReferenceTable(
            caption="METAL MAniaX任务总表原行",
            headers=["原表字段", "原始值"],
            rows=[[header, value] for header, value in fact.overview.fields.items()],
            source_refs=[fact.overview.source_ref],
        ),
        *[_detail_table(field) for field in fact.detail_fields],
    ]
    if fact.chinese_reference is not None:
        tables.append(
            ReferenceTable(
                caption="中文旧表原行（全部字段）",
                headers=["原表字段", "原始值"],
                rows=[[header, value] for header, value in fact.chinese_reference.fields.items()],
                source_refs=[fact.chinese_reference.source_ref],
            )
        )
    if inherited is not None:
        tables.append(
            ReferenceTable(
                caption="既有任务目录字段（独立保留）",
                headers=["项目", "既有值"],
                rows=[
                    [_LEGACY_ATTRIBUTES[key], "（空值）" if value is None else str(value)]
                    for key, value in inherited.attributes.items()
                ],
                source_refs=inherited.source_refs,
            )
        )
    return tables


def _differences(fact: QuestFact, refs: list[SourceRef]) -> ReferenceSection | None:
    paragraphs = list(fact.source_uncertainties_zh)
    tables = []
    if fact.chinese_reference is not None:
        paragraphs.append(
            "日文总表与中文旧表各自保留。中文旧表只收录八项任务，译名、空白、问号和报酬条件"
            "均不能自动当作已核验的0.99资料。"
        )
        rows = []
        for ja, zh in (
            ("受注場所", "任务接受场所"),
            ("経験値", "经验值"),
            ("有名度", "有名度"),
            ("報酬(条件)", "报酬"),
        ):
            rows.extend(
                [
                    [f"{_FIELD_LABELS[ja]} · 日文总表", fact.overview.fields[ja]],
                    [f"{_FIELD_LABELS[ja]} · 中文旧表", fact.chinese_reference.fields[zh]],
                ]
            )
        tables.append(
            ReferenceTable(
                caption="日文总表与中文旧表分别列示",
                headers=["项目与来源", "原始值"],
                rows=rows,
                source_refs=[fact.overview.source_ref, fact.chinese_reference.source_ref],
            )
        )
    if not paragraphs:
        return None
    return ReferenceSection(
        id="source-differences",
        title="来源差异与待确认条件",
        paragraphs=paragraphs,
        tables=tables,
        source_refs=refs,
    )


def _record(
    fact: QuestFact,
    snapshot: QuestSnapshot,
    names: QuestNames,
    inherited: NormalizedRecord | None,
) -> KnowledgeRecord:
    refs = _references(fact, inherited)
    location, acceptance, rewards = fact.detail_fields
    kind = _KIND_LABELS[fact.request_kind]
    sections = [
        ReferenceSection(
            id="acceptance-location",
            title="接取地点",
            paragraphs=[fact.location_zh],
            source_refs=[fact.overview.source_ref, location.source_ref],
        ),
        ReferenceSection(
            id="acceptance-conditions",
            title="接取条件",
            paragraphs=[
                "特别委托：来源的接取条件明确写有「特別な依頼」。"
                if fact.request_kind == "special_request"
                else "普通或事件任务：按来源记载的具体条件触发。",
                fact.acceptance_zh,
            ],
            source_refs=[fact.overview.source_ref, acceptance.source_ref, *fact.summary_refs],
        ),
        ReferenceSection(
            id="steps",
            title="完成步骤",
            paragraphs=[f"{index}. {step}" for index, step in enumerate(fact.steps_zh, 1)],
            source_refs=fact.summary_refs,
        ),
        ReferenceSection(
            id="rewards",
            title="报酬与获得条件",
            paragraphs=fact.reward_notes_zh,
            tables=[
                ReferenceTable(
                    caption="日文总表报酬（保留原值与条件）",
                    headers=["项目", "原表值"],
                    rows=[
                        [_FIELD_LABELS[field], fact.overview.fields[field]]
                        for field in ("経験値", "有名度", "報酬(条件)")
                    ],
                    source_refs=[fact.overview.source_ref],
                )
            ],
            source_refs=[fact.overview.source_ref, rewards.source_ref, *fact.summary_refs],
        ),
        ReferenceSection(
            id="failure-missable",
            title="失败与错过条件",
            paragraphs=fact.failure_conditions.notes_zh,
            source_refs=fact.failure_conditions.source_refs or fact.summary_refs,
        ),
    ]
    differences = _differences(fact, refs)
    if differences is not None:
        sections.append(differences)
    notes = [
        snapshot.reference_note,
        snapshot.coverage_note.replace("special_request", "特别委托"),
        "中文任务名、地点与步骤为参考译名和编辑摘要，全部尚未经过0.99实机核对。",
        "经验值、有名度与报酬的空白、横线、问号按原表保留，不补成零或无报酬。",
        *(_MISSING[field] for field in fact.missing_fields),
    ]
    if names.quests[fact.number].detail_title_aliases:
        notes.append(
            "详情页标题原有其他写法："
            + "、".join(names.quests[fact.number].detail_title_aliases)
            + "；任务仍以总表原名对应。"
        )
    sections.extend(
        [
            ReferenceSection(
                id="raw-source-tables",
                title="原表与详情原文",
                paragraphs=["总表、详情小节和中文旧表分别保留，字段与空白不互相覆盖。"],
                tables=_raw_tables(fact, inherited),
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
    aliases = sorted(set([*fact.aliases, *(inherited.names.aliases if inherited else [])]))
    return KnowledgeRecord(
        id=inherited.id if inherited else stable_record_id("quests", "quest", fact.name_ja),
        category="quests",
        names=NameSet(
            ja=fact.name_ja,
            zh_09=inherited.names.zh_09 if inherited else None,
            zh_099=inherited.names.zh_099 if inherited else None,
            zh_reference=fact.name_zh_reference,
            aliases=aliases,
        ),
        summary=f"{kind}。{fact.location_zh}。{fact.acceptance_zh}",
        attributes=[
            ReferenceAttribute(label="任务编号", value=str(fact.number)),
            ReferenceAttribute(label="任务类型", value=kind),
            ReferenceAttribute(label="接取地点", value=fact.location_zh),
            ReferenceAttribute(label="经验值（总表原值）", value=fact.overview.fields["経験値"]),
            ReferenceAttribute(label="有名度（总表原值）", value=fact.overview.fields["有名度"]),
            ReferenceAttribute(
                label="失败与错过条件",
                value="来源已记载"
                if fact.failure_conditions.status == "documented"
                else "来源未明确记载",
            ),
        ],
        sections=sections,
        tags=[
            kind,
            *(["有错过条件"] if fact.failure_conditions.status == "documented" else []),
            *(["战车相关"] if fact.vehicle_related else []),
        ],
        version_scope=["mm2r-jp"],
        verification_status="source_only",
        source_refs=refs,
        issues=fact.source_uncertainties_zh,
    )


def load_quest_references(
    repo_root: Path, *, rebuilt_bundle: NormalizedBundle | None = None
) -> KnowledgeDataset | None:
    """离线生成101项任务正文，沿用8个旧身份并明确未知失败条件。"""
    sources = _load_sources(repo_root, rebuilt_bundle=rebuilt_bundle)
    if sources is None:
        return None
    snapshot, names, inherited = sources
    return KnowledgeDataset(
        category="quests",
        records=[
            _record(fact, snapshot, names, inherited.get(fact.name_ja)) for fact in snapshot.records
        ],
    )
