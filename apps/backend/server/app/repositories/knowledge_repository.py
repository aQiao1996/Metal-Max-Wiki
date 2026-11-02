from functools import lru_cache

from app.core.config import get_settings
from app.schemas.knowledge import KnowledgeCategory, KnowledgeDataset, KnowledgeRecord


@lru_cache(maxsize=8)
def load_knowledge(category: KnowledgeCategory) -> tuple[KnowledgeRecord, ...]:
    """读取对应分类的已校验百科快照。"""
    filename = {
        "jobs": "job-entries.json",
        "items": "item-entries.json",
        "quests": "quest-entries.json",
    }.get(category, f"{category}.json")
    path = get_settings().data_dir / f"interim/mm2r/0.99/{filename}"
    try:
        dataset = KnowledgeDataset.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as error:
        raise RuntimeError(f"读取百科资料失败：{path}") from error
    if dataset.category != category:
        raise RuntimeError(f"百科数据集分类不符：{path}")
    return tuple(dataset.records)
