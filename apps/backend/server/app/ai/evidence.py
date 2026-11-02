import re
from dataclasses import dataclass
from typing import Literal, cast, get_args

from app.repositories.equipment_repository import load_equipment
from app.repositories.guide_repository import load_guides
from app.repositories.knowledge_repository import load_knowledge
from app.schemas.equipment import EquipmentNames, EquipmentRecord
from app.schemas.guides import GuideBattle, GuideFact, GuideRecord
from app.schemas.knowledge import KnowledgeCategory, KnowledgeRecord, ReferenceTable
from app.services.equipment_service import equipment_facts

VerificationStatus = Literal["source_only", "compatible_candidate"]


@dataclass(frozen=True)
class EvidenceChunk:
    """可被词法或后续向量检索复用的完整事实块，不包含来源机器元数据。"""

    id: str
    entity_id: str
    category: str
    title: str
    entity_names: tuple[str, ...]
    subject_names: tuple[str, ...]
    text: str
    path: str
    verification_status: VerificationStatus
    stars: int | None = None

    def render(self, number: int) -> str:
        """将完整证据和可引用编号交给模型，预算按同一文本计算。"""
        status = "日版参考" if self.verification_status == "source_only" else "汉化兼容候选"
        return f"[{number}] {self.title}（{status}）\n{self.text}"


def _names(names: EquipmentNames) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name
            for name in (names.zh_099, names.zh_09, names.zh_reference, names.ja, *names.aliases)
            if name
        )
    )


def _table_text(table: ReferenceTable) -> str:
    rows = [
        "｜".join(f"{header}：{cell}" for header, cell in zip(table.headers, row, strict=True))
        for row in table.rows
    ]
    return "\n".join([table.caption, *rows])


def _range(label: str, value: str, minimum: str, maximum: str) -> str:
    return f"{label}：{value}（下限 {minimum}，上限 {maximum}）"


def _human_issues(issues: list[str]) -> list[str]:
    return [
        f"待确认：{issue}" for issue in issues if re.fullmatch(r"[A-Za-z0-9_./:-]+", issue) is None
    ]


def _equipment_chunks(record: EquipmentRecord) -> list[EvidenceChunk]:
    facts = equipment_facts(record)
    facts.pop("逐星级普通改造", None)
    facts.pop("名称说明", None)
    name_scope = (
        "名称核验范围：当前名称来自本机0.99 ROM提取；"
        "仅核对名称，数值、获取条件与机制仍为参考资料。\n"
        if record.name_verification is not None
        else ""
    )
    facts.pop("加成计算补充出处", None)
    path = f"/wiki/equipment/{record.id}"
    names = _names(record.names)

    def chunk(suffix: str, heading: str, text: str, stars: int | None = None) -> EvidenceChunk:
        return EvidenceChunk(
            id=f"equipment:{record.id}:{suffix}",
            entity_id=f"equipment:{record.id}",
            category="equipment",
            title=f"{record.name}｜{heading}",
            entity_names=names,
            subject_names=(),
            text=name_scope + text,
            path=path + ("#equipment-modifications-heading" if stars is not None else ""),
            verification_status=record.verification_status,
            stars=stars,
        )

    chunks = [
        chunk("facts", "基本属性、特性与获取", "\n".join(f"{k}：{v}" for k, v in facts.items()))
    ]
    # 每个星级都携带获取限制和效果条件，避免独立检索数值后丢失适用范围。
    conditions = "\n".join(
        f"{key}：{value}"
        for key, value in facts.items()
        if key
        in {
            "来源标注可获取星级",
            "获取限制",
            "同星级来源数值差异（尚待核对）",
            "仅见租赁装备的星级，不能当作自有装备获取星级",
            "改造说明",
            "载重条件说明",
            "特性名称（中文参考）",
            "生效方式",
            "特性作用",
            "特性限制",
            "备注",
            "面板效果验证说明",
            "马力强化后型号",
            "本次马力强化费用（G）",
            "马力强化限制",
        }
    )
    if record.kind == "engine":
        chunks.append(chunk("rules", "特性规则与载重条件", conditions))
        acquisition = "\n".join(
            f"{key}：{value}"
            for key, value in facts.items()
            if key in {"获取方式", "获取限制", "来源标注可获取星级", "备注", "马力强化限制"}
        )
        chunks.append(chunk("acquisition", "获取方式与可获取星级", acquisition))
        supplement = "\n".join(
            f"{key}：{value}"
            for key, value in facts.items()
            if key in {"价格", "马力强化后型号", "本次马力强化费用（G）", "马力强化限制"}
        )
        if supplement:
            chunks.append(chunk("upgrade", "价格与型号强化", supplement))
    for mod in record.modifications:
        values = "\n".join(
            [
                _range("攻击力", mod.attack_raw, mod.attack_min_raw, mod.attack_max_raw),
                _range("防御力", mod.defense_raw, mod.defense_min_raw, mod.defense_max_raw),
                _range("弹仓", mod.magazine_raw, mod.magazine_min_raw, mod.magazine_max_raw),
                _range("重量", mod.weight_raw, mod.weight_min_raw, mod.weight_max_raw),
            ]
        )
        chunks.append(
            chunk(
                f"stars-{mod.stars}", f"{mod.stars}星普通改造", f"{conditions}\n{values}", mod.stars
            )
        )
    for control in record.control_modifications:
        values = "\n".join(
            [
                _range(
                    "面板命中",
                    control.accuracy_raw,
                    control.accuracy_min_raw,
                    control.accuracy_max_raw,
                ),
                _range(
                    "面板回避",
                    control.evasion_raw,
                    control.evasion_min_raw,
                    control.evasion_max_raw,
                ),
                _range(
                    "防御力", control.defense_raw, control.defense_min_raw, control.defense_max_raw
                ),
                _range("重量", control.weight_raw, control.weight_min_raw, control.weight_max_raw),
            ]
        )
        chunks.append(
            chunk(
                f"stars-{control.stars}",
                f"{control.stars}星普通改造",
                f"{conditions}\n{values}",
                control.stars,
            )
        )
    for engine in record.engine_modifications:
        values = "\n".join(
            [
                f"当前型号{engine.stars}星单台基础载重：{engine.capacity_raw}",
                _range(
                    "防御力", engine.defense_raw, engine.defense_min_raw, engine.defense_max_raw
                ),
                _range("重量", engine.weight_raw, engine.weight_min_raw, engine.weight_max_raw),
            ]
        )
        chunks.append(
            chunk(
                f"stars-{engine.stars}",
                f"{engine.stars}星引擎数值",
                f"{conditions}\n{values}",
                engine.stars,
            )
        )
    return chunks


def _knowledge_chunks(record: KnowledgeRecord) -> list[EvidenceChunk]:
    path = f"/wiki/{record.category}/{record.id}"
    names = _names(record.names)
    condition_ids = (
        {"acceptance-location", "acceptance-conditions", "failure-missable", "source-differences"}
        if record.category == "quests"
        else {"consumption-restrictions"}
        if record.category == "items"
        else set()
    )
    shared_conditions = [
        "\n".join(
            [
                f"{section.title}：{'；'.join(section.paragraphs)}",
                *(_table_text(table) for table in section.tables),
            ]
        )
        for section in record.sections
        if section.id in condition_ids
    ]
    if record.category == "items":
        shared_conditions.extend(
            f"{attribute.label}：{attribute.value}"
            for attribute in record.attributes
            if attribute.label in {"使用对象", "消耗性"}
        )

    def chunk(
        suffix: str, heading: str, text: str, anchor: str = "", subjects: tuple[str, ...] = ()
    ) -> EvidenceChunk:
        return EvidenceChunk(
            id=f"{record.category}:{record.id}:{suffix}",
            entity_id=f"{record.category}:{record.id}",
            category=record.category,
            title=f"{record.name}｜{heading}",
            entity_names=names,
            subject_names=subjects,
            text=text,
            path=path + (f"#{anchor}" if anchor else ""),
            verification_status=record.verification_status,
        )

    summary = "\n".join(
        [
            record.summary,
            *(f"{a.label}：{a.value}" for a in record.attributes),
            *shared_conditions,
        ]
    )
    chunks = [chunk("summary", "概况", summary)]
    for section in record.sections:
        # 原表备份和全局来源说明保留在百科页，不作为每条记录的检索信号。
        if section.id in {"source-issues", "raw-source-tables"}:
            continue
        context = "\n".join(section.paragraphs)
        if section.id not in condition_ids:
            context = "\n".join([*shared_conditions, context])
        if record.category == "items":
            context = f"用途与来源差异摘要：{record.summary}\n{context}"
        subjects = (section.title,) if section.id.startswith("skill-") else ()
        if not section.tables or section.id.startswith("skill-"):
            text = "\n".join([context, *(_table_text(table) for table in section.tables)])
            chunks.append(chunk(section.id, section.title, text, section.id, subjects))
        else:
            if context:
                chunks.append(chunk(section.id, section.title, context, section.id))
            for index, table in enumerate(section.tables):
                chunks.append(
                    chunk(
                        f"{section.id}:table-{index}",
                        f"{section.title}／{table.caption}",
                        f"{context}\n{_table_text(table)}",
                        section.id,
                    )
                )
    for enemy in record.enemies:
        probability = f"概率条件：{record.probability_note}"
        slots = [
            f"槽{drop.slot}：{drop.name}（{drop.item_ja}），"
            f"单槽概率 {drop.rate_raw}；{drop.summary}"
            for drop in enemy.drops
        ]
        chunks.append(
            chunk(
                f"drops:{enemy.encyclopedia_number}",
                f"掉落槽与概率／{enemy.name_ja}",
                "\n".join(
                    [
                        f"敌人：{enemy.name_ja}；图鉴编号：{enemy.encyclopedia_number}",
                        probability,
                        *slots,
                    ]
                ),
                "drops",
                tuple(drop.name for drop in enemy.drops),
            )
        )
        for drop in enemy.drops:
            context = "\n".join(
                [
                    f"{enemy.name_ja}槽{drop.slot}：{drop.name}（{drop.item_ja}），"
                    f"单槽概率 {drop.rate_raw}",
                    probability,
                    drop.summary,
                    *(f"{a.label}：{a.value}" for a in drop.attributes),
                    *_human_issues(drop.issues),
                ]
            )
            for index, table in enumerate(drop.tables):
                chunks.append(
                    chunk(
                        f"drops:{enemy.encyclopedia_number}:{drop.slot}:table-{index}",
                        f"掉落物／{table.caption}",
                        f"{context}\n{_table_text(table)}",
                        "drops",
                        (drop.name, drop.item_ja),
                    )
                )
    if record.vehicle is not None:
        traits = [
            table
            for section in record.sections
            if section.id == "traits"
            for table in section.tables
        ]
        for setup in record.vehicle.configurations:
            values = [
                f"配置：{setup.name_reference}（{setup.name_ja}）；"
                f"资料顺序 {setup.stage}，不代表升级连线",
                *(f"孔{index}：{hole}" for index, hole in enumerate(setup.holes_raw, 1)),
                f"底盘重量原值：{setup.weight_raw}；货仓原值：{setup.cargo_raw}",
                f"此配置特性：{setup.trait_name}（{setup.trait_ja}）",
                f"固定武器原值：{setup.fixed_armament_raw or '来源未注明'}",
                *_human_issues(setup.issues),
            ]
            values.extend(
                _table_text(table)
                for table in traits
                if setup.trait_name in table.caption or setup.trait_ja in table.caption
            )
            chunks.append(
                chunk(
                    setup.id,
                    f"具体配置／{setup.name_reference}",
                    "\n".join(values),
                    f"setup-{setup.id}",
                    tuple(
                        name for name in (setup.name_reference, setup.name_ja) if name not in names
                    ),
                )
            )
    return chunks


def _guide_fact(fact: GuideFact) -> str:
    values = [fact.text_zh]
    if isinstance(fact, GuideBattle):
        requirements = {"mandatory": "必打", "optional": "可选", "scripted_loss": "剧情必败"}
        values.append(f"战斗要求：{requirements[fact.requirement]}")
    values.extend(f"{key}：{value}" for key, value in fact.raw_values.items())
    values.append(f"原文依据：{'；'.join(fact.evidence)}")
    return "；".join(values)


def _guide_chunks(record: GuideRecord) -> list[EvidenceChunk]:
    sections: tuple[tuple[str, str, list[GuideFact]], ...] = (
        ("prerequisites", "前提条件", record.prerequisites),
        ("steps", "操作步骤", record.steps),
        ("key-items", "关键道具", record.key_items),
        ("battles", "战斗与是否必打", list(record.battles)),
        ("cautions", "注意事项", record.cautions),
        ("next-steps", "后续推进", record.next_steps),
    )
    chunks = []
    for section_id, title, facts in sections:
        if not facts:
            continue
        context = [f"地点：{record.location}", f"本章目标：{record.summary}"]
        if section_id != "prerequisites":
            context.extend(f"前提：{fact.text_zh}" for fact in record.prerequisites)
        if section_id in {"steps", "battles"}:
            context.append(f"战斗条件：{record.battle_note}")
            context.extend(f"注意：{fact.text_zh}" for fact in record.cautions)
        values = [f"{index}. {_guide_fact(fact)}" for index, fact in enumerate(facts, 1)]
        chunks.append(
            EvidenceChunk(
                id=f"guides:{record.slug}:{section_id}",
                entity_id=f"guides:{record.slug}",
                category="guides",
                title=f"{record.title}｜{title}",
                entity_names=(record.title, record.location),
                subject_names=(),
                text="\n".join([*context, *values]),
                path=f"/guides/{record.slug}#{section_id}",
                verification_status=record.verification_status,
            )
        )
    return chunks


def load_evidence_chunks() -> tuple[EvidenceChunk, ...]:
    """从已校验快照建立统一事实块；新百科分类沿用同一契约。"""
    chunks = [chunk for record in load_equipment() for chunk in _equipment_chunks(record)]
    categories = cast(tuple[KnowledgeCategory, ...], get_args(KnowledgeCategory))
    for category in categories:
        chunks.extend(
            chunk for record in load_knowledge(category) for chunk in _knowledge_chunks(record)
        )
    chunks.extend(chunk for record in load_guides().records for chunk in _guide_chunks(record))
    return tuple(chunks)
