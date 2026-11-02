from unicodedata import normalize

from app.core.errors import BusinessError
from app.repositories.knowledge_repository import load_knowledge
from app.schemas.knowledge import (
    KnowledgeCategory,
    KnowledgeListData,
    KnowledgeRecord,
    KnowledgeSort,
    KnowledgeSummary,
)
from app.schemas.response import PaginationMeta
from app.services.equipment_service import require_available_version


def knowledge_text(record: KnowledgeRecord) -> str:
    """检索名称、地点、正文和逐槽掉落，不拼接其他版本。"""
    values = [record.name, record.names.ja or "", *record.names.aliases, record.summary]
    values.extend(attribute.value for attribute in record.attributes)
    values.extend(paragraph for section in record.sections for paragraph in section.paragraphs)
    values.extend(
        f"{drop.name} {drop.item_ja} {drop.summary}"
        for enemy in record.enemies
        for drop in enemy.drops
    )
    return normalize("NFKC", " ".join(values)).casefold()


def list_knowledge(
    version: str,
    category: KnowledgeCategory,
    *,
    q: str = "",
    sort: KnowledgeSort = "name-asc",
    page: int = 1,
    page_size: int = 20,
) -> KnowledgeListData:
    """按分类和关键词查询百科，保留稳定分页。"""
    require_available_version(version)
    query = normalize("NFKC", q.strip()).casefold()
    records = [
        record
        for record in load_knowledge(category)
        if not query or query in knowledge_text(record)
    ]
    if sort == "bounty-desc":

        def bounty_key(record: KnowledgeRecord) -> tuple[int, str]:
            if record.bounty is None:
                raise ValueError(f"赏金首缺少排序所需赏金：{record.id}")
            return (-record.bounty, record.id)

        records.sort(key=bounty_key)
    else:
        records.sort(key=lambda record: (record.name, record.id))
    offset = (page - 1) * page_size
    return KnowledgeListData(
        list=[
            KnowledgeSummary.model_validate(record)
            for record in records[offset : offset + page_size]
        ],
        pagination=PaginationMeta.create(page=page, page_size=page_size, total=len(records)),
    )


def get_knowledge(version: str, category: KnowledgeCategory, record_id: str) -> KnowledgeRecord:
    """查找当前版本中的真实百科条目。"""
    require_available_version(version)
    for record in load_knowledge(category):
        if record.id == record_id:
            return record
    raise BusinessError(404, "没有找到这条百科资料")
