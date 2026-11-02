from typing import Literal
from unicodedata import normalize

from app.core.errors import BusinessError
from app.repositories.equipment_repository import load_equipment
from app.repositories.knowledge_repository import load_knowledge
from app.schemas.equipment import EquipmentNames, EquipmentRecord
from app.schemas.knowledge import KnowledgeCategory
from app.schemas.response import PaginationMeta
from app.schemas.search import LibrarySearchPage, LibrarySearchResult
from app.services.equipment_service import equipment_text, require_available_version
from app.services.knowledge_service import knowledge_text

_TYPE_LABELS = {
    "human-weapon": "人类武器",
    "main-cannon": "主炮",
    "sub-gun": "副炮",
    "special-equipment": "S-E",
    "c-unit": "C 装置",
    "engine": "引擎",
}
_KNOWLEDGE_LABELS: dict[KnowledgeCategory, str] = {
    "wanted-monsters": "赏金首",
    "vehicles": "战车",
    "jobs": "职业与技能",
}


def _name_source(names: EquipmentNames) -> Literal["zh_099", "zh_09", "zh_reference", "ja"]:
    if names.zh_099:
        return "zh_099"
    if names.zh_09:
        return "zh_09"
    if names.zh_reference:
        return "zh_reference"
    return "ja"


def _equipment_summary(record: EquipmentRecord) -> str:
    keys = ("attack_raw", "range_raw", "acquisition_raw")
    if record.kind == "c_unit":
        keys = ("trait_name_raw", "trait_activation_raw", "acquisition_raw")
    elif record.kind == "engine":
        keys = ("capacity_raw", "trait_name_raw", "acquisition_raw")
    values = []
    for key in keys:
        value = record.attributes.get(key)
        if value is not None:
            values.append(f"基础载重 {value}t" if key == "capacity_raw" else str(value))
    return " · ".join(values)


def search_library(
    version: str, q: str, *, page: int = 1, page_size: int = 20
) -> LibrarySearchPage:
    """搜索已接入的真实资料，结果按名称命中程度稳定排列。"""
    require_available_version(version)
    query = normalize("NFKC", q.strip()).casefold()
    if not query:
        raise BusinessError(422, "搜索关键词不能为空")
    results: list[LibrarySearchResult] = []
    for record in load_equipment():
        if query not in equipment_text(record):
            continue
        results.append(
            LibrarySearchResult(
                id=record.id,
                name=record.name,
                summary=_equipment_summary(record),
                aliases=record.names.aliases,
                href=f"/wiki/equipment/{record.id}",
                category_label=_TYPE_LABELS[record.equipment_type],
                verification_status=record.verification_status,
                name_source=_name_source(record.names),
            )
        )
    for category, label in _KNOWLEDGE_LABELS.items():
        for entry in load_knowledge(category):
            if query not in knowledge_text(entry):
                continue
            results.append(
                LibrarySearchResult(
                    id=entry.id,
                    name=entry.name,
                    summary=entry.summary,
                    aliases=entry.names.aliases,
                    href=f"/wiki/{entry.category}/{entry.id}",
                    category_label=label,
                    verification_status=entry.verification_status,
                    name_source=_name_source(entry.names),
                )
            )
    results.sort(
        key=lambda result: (
            query != normalize("NFKC", result.name).casefold(),
            query not in normalize("NFKC", " ".join([result.name, *result.aliases])).casefold(),
            result.name,
            result.id,
        )
    )
    offset = (page - 1) * page_size
    return LibrarySearchPage(
        list=results[offset : offset + page_size],
        pagination=PaginationMeta.create(page=page, page_size=page_size, total=len(results)),
    )
