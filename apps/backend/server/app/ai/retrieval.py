import re
from unicodedata import normalize

from app.repositories.equipment_repository import load_equipment
from app.schemas.equipment import EquipmentRecord
from app.services.equipment_service import equipment_text


def _terms(text: str) -> set[str]:
    normalized = normalize("NFKC", text).casefold()
    terms = set(re.findall(r"[a-z0-9]+", normalized))
    for segment in re.findall(r"[\u4e00-\u9fff]+", normalized):
        terms.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return terms - {"什么", "怎么", "如何", "可以", "哪个", "哪些", "一下", "重装", "机兵"}


def retrieve_equipment(question: str, *, limit: int = 4) -> list[EquipmentRecord]:
    """按名称命中和中文二元词检索当前版本资料。"""
    query = normalize("NFKC", question).casefold()
    terms = _terms(query)
    ranked: list[tuple[float, EquipmentRecord]] = []
    for record in load_equipment():
        names = [record.name, *record.names.aliases]
        exact = any(normalize("NFKC", name).casefold() in query for name in names)
        title_hits = len(terms & _terms(" ".join(names)))
        body_hits = len(terms & _terms(equipment_text(record)))
        type_hit = "主炮" in query and record.kind == "main_cannon"
        score = 30 * exact + 4 * title_hits + body_hits + 2 * type_hit
        if score > 0:
            ranked.append((score, record))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    return [record for _, record in ranked[:limit]]
