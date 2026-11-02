from functools import lru_cache

from app.core.config import get_settings
from app.repositories.equipment_verification import apply_verified_names
from app.schemas.equipment import EquipmentDataset, EquipmentRecord


@lru_cache(maxsize=1)
def load_equipment() -> tuple[EquipmentRecord, ...]:
    """读取并校验标准化装备资料，损坏的数据不能进入业务链路。"""
    path = get_settings().data_dir / "interim/mm2r/0.99/equipment.json"
    try:
        dataset = EquipmentDataset.model_validate_json(path.read_bytes())
        return apply_verified_names(dataset.records, get_settings().data_dir)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"读取装备资料失败：{path}") from error
