from functools import lru_cache

from app.core.config import get_settings
from app.schemas.guides import GuideDataset


@lru_cache(maxsize=1)
def load_guides() -> GuideDataset:
    """读取完整已校验攻略快照，缺失或损坏时携带上下文失败。"""
    path = get_settings().data_dir / "interim/mm2r/0.99/guides.json"
    try:
        return GuideDataset.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as error:
        raise RuntimeError(f"读取主线攻略资料失败：{path}") from error
