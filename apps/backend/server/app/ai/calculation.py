import re
from dataclasses import dataclass
from decimal import Decimal
from unicodedata import normalize

from app.ai.evidence import EvidenceChunk
from app.ai.retrieval import explicit_entity_stars
from app.repositories.equipment_repository import load_equipment
from app.schemas.equipment import EquipmentRecord


@dataclass(frozen=True)
class DerivedCalculation:
    text: str
    missing_conditions: tuple[str, ...] = ()


def _slot(question: str, record: EquipmentRecord) -> int | None:
    names = (
        record.name,
        record.names.ja,
        record.names.zh_099,
        record.names.zh_09,
        record.names.zh_reference,
        *record.names.aliases,
    )
    slots = set()
    for clause in re.split(r"[，,。；;、]|以及|并且|和|与", normalize("NFKC", question).casefold()):
        if not any(name and normalize("NFKC", name).casefold() in clause for name in names):
            continue
        for match in re.finditer(r"([一二12])(?:号(?:引擎|槽)?|槽)|引擎\s*([12])", clause):
            value = match.group(1) or match.group(2)
            slots.add(1 if value in {"一", "1"} else 2)
    return next(iter(slots)) if len(slots) == 1 else None


def _capacity(raw: str) -> Decimal | None:
    value = raw.removesuffix("t").strip()
    return Decimal(value) if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) else None


def derive_engine_calculation(
    question: str, chunks: tuple[EvidenceChunk, ...]
) -> DerivedCalculation | None:
    """从独立解析的显式输入计算辅助引擎毛载重，不让模型重写算术结果。"""
    intent = re.sub(r"(?:不要|不用|无需|不必)(?:计算|求)[^，,。；;]*", "", question)
    comparison = any(word in question for word in ("比较", "对比", "分别", "各自", "区别"))
    slot_pair = bool(re.search(r"[一1](?:号|槽)|引擎1", question)) and bool(
        re.search(r"[二2](?:号|槽)|引擎2", question)
    )
    combined = any(
        word in intent
        for word in (
            "总载重",
            "总基础载重",
            "毛载重",
            "净载重",
            "合计",
            "载重如何计算",
            "载重怎么计算",
        )
    )
    combined = combined or (
        not comparison and slot_pair and any(word in intent for word in ("载重", "几吨", "多少吨"))
    )
    if not combined:
        return None
    entities, stars = explicit_entity_stars(question)
    records = [
        record
        for record in load_equipment()
        if record.kind == "engine" and f"equipment:{record.id}" in entities
    ]
    if not records:
        return None
    if len(records) != 2:
        return DerivedCalculation(
            "", ("该组合尚不支持可靠计算，需要分别明确两台引擎的型号、星级与槽位",)
        )
    inputs: dict[int, tuple[EquipmentRecord, int, Decimal, int]] = {}
    missing = []
    for record in records:
        entity_id = f"equipment:{record.id}"
        requested = stars.get(entity_id, set())
        slot = _slot(question, record)
        if len(requested) != 1:
            missing.append(f"{record.name}缺少唯一明确的星级")
        if slot is None or slot in inputs:
            missing.append(f"{record.name}缺少唯一明确的一号或二号槽位")
        if len(requested) != 1 or slot is None or slot in inputs:
            continue
        star = next(iter(requested))
        obtainable = str(record.attributes.get("obtainable_stars_raw", ""))
        if obtainable and str(star) not in obtainable.split(","):
            missing.append(
                f"{record.name}来源可获取星级为{obtainable}，不能将{star}星参考当作实际配装"
            )
            continue
        matching = [
            (number, chunk)
            for number, chunk in enumerate(chunks, 1)
            if chunk.entity_id == entity_id and chunk.stars == star
        ]
        if not matching:
            missing.append(f"{record.name}{star}星的完整数值证据未进入本次预算")
            continue
        mod = next((item for item in record.engine_modifications if item.stars == star), None)
        capacity = _capacity(mod.capacity_raw) if mod is not None else None
        if capacity is None:
            missing.append(f"{record.name}{star}星缺少可计算的基础载重")
            continue
        inputs[slot] = (record, star, capacity, matching[0][0])
    if missing:
        return DerivedCalculation("", tuple(missing))
    if set(inputs) != {1, 2}:
        return DerivedCalculation("", ("两台引擎必须分别明确放在一号和二号槽",))
    first, first_star, first_capacity, first_ref = inputs[1]
    second, second_star, second_capacity, second_ref = inputs[2]
    effect = str(second.attributes.get("trait_effect_raw", ""))
    match = re.search(r"装在二号槽.*一号引擎基础载重的([0-9]+(?:\.[0-9]+)?)%", effect)
    first_effect = str(first.attributes.get("trait_effect_raw", ""))
    if match is None or not any(
        word in first_effect for word in ("不提供额外载重加成", "不额外增加载重")
    ):
        return DerivedCalculation("", ("本次资料没有足以计算所给组合的完整特性加成规则",))
    rate = Decimal(match.group(1)) / 100
    bonus = first_capacity * rate
    total = first_capacity + second_capacity + bonus
    text = (
        f"一号引擎：{first_star}星{first.name}，基础载重{first_capacity}t。[{first_ref}]\n"
        f"二号引擎：{second_star}星{second.name}，基础载重{second_capacity}t。[{second_ref}]\n"
        f"额外加成以一号引擎为基数：{first_capacity}×{rate}={bonus}t。[{second_ref}]\n"
        f"未扣自重的毛载重={first_capacity}+{second_capacity}+{bonus}={total}t。[{first_ref}][{second_ref}]\n"
        f"防御改造不改变当前型号的基础载重；防御与重量上下限独立，"
        f"仅说防御改满不能确定实际自重及整车净剩余载重。[{first_ref}][{second_ref}]"
    )
    notes = str(second.attributes.get("notes_raw", ""))
    if notes:
        text += f"\n{notes}[{second_ref}]"
    return DerivedCalculation(text)
