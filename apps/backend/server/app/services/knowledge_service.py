from unicodedata import normalize

from app.core.errors import BusinessError
from app.repositories.knowledge_repository import load_knowledge
from app.schemas.knowledge import (
    KnowledgeCategory,
    KnowledgeListData,
    KnowledgeMount,
    KnowledgeRecord,
    KnowledgeSort,
    KnowledgeSummary,
)
from app.schemas.response import PaginationMeta
from app.services.equipment_service import require_available_version


def knowledge_text(record: KnowledgeRecord) -> str:
    """检索名称、正文与条件表，排除全局来源说明。"""
    values = [record.name, record.names.ja or "", *record.names.aliases, record.summary]
    values.extend(attribute.value for attribute in record.attributes)
    values.extend(
        paragraph
        for section in record.sections
        if section.id != "source-issues"
        for paragraph in section.paragraphs
    )
    values.extend(
        f"{drop.name} {drop.item_ja} {drop.summary}"
        for enemy in record.enemies
        for drop in enemy.drops
    )
    values.extend(section.title for section in record.sections if section.id != "source-issues")
    if record.vehicle is None:
        values.extend(
            " ".join([table.caption, *table.headers, *(cell for row in table.rows for cell in row)])
            for section in record.sections
            if section.id != "source-issues"
            for table in section.tables
        )
    if record.vehicle is not None:
        values.extend(record.vehicle.trait_terms)
        values.extend(
            " ".join(
                [
                    setup.name_ja,
                    setup.name_reference,
                    setup.trait_ja,
                    setup.trait_name,
                    *setup.holes_raw,
                ]
            )
            for setup in record.vehicle.configurations
        )
    return normalize("NFKC", " ".join(values)).casefold()


def list_knowledge(
    version: str,
    category: KnowledgeCategory,
    *,
    q: str = "",
    sort: KnowledgeSort = "name-asc",
    mount: KnowledgeMount = "all",
    page: int = 1,
    page_size: int = 20,
) -> KnowledgeListData:
    """按分类和关键词查询百科，保留稳定分页。"""
    require_available_version(version)
    if category != "wanted-monsters" and sort == "bounty-desc":
        raise BusinessError(422, "此分类不支持赏金排序")
    if category != "vehicles" and mount != "all":
        raise BusinessError(422, "此分类不支持战车动力筛选")
    query = normalize("NFKC", q.strip()).casefold()
    records = [
        record
        for record in load_knowledge(category)
        if not query or query in knowledge_text(record)
    ]
    exact = [
        record
        for record in records
        if any(
            query == normalize("NFKC", name).casefold()
            for name in (record.name, record.names.ja or "", *record.names.aliases)
        )
    ]
    if query and exact:
        records = exact
    if mount != "all":

        def supports_mount(record: KnowledgeRecord) -> bool:
            if record.vehicle is None:
                raise ValueError(f"战车缺少动力配置：{record.id}")
            return (
                record.vehicle.double_engine_supported
                if mount == "double-engine"
                else record.vehicle.double_c_unit_supported
            )

        records = [record for record in records if supports_mount(record)]
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
