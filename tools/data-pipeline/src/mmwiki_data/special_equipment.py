"""S-E事实采集与标准化入口。"""

import time
from collections.abc import Callable
from pathlib import Path

from mmwiki_data.normalization_models import NormalizedBundle
from mmwiki_data.vehicle_weapons import (
    SPECIAL_EQUIPMENT,
    collect_vehicle_weapons,
    load_vehicle_weapons,
)


def collect_special_equipment(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """采集S-E总表与独立详情。"""
    return collect_vehicle_weapons(repo_root, SPECIAL_EQUIPMENT, sleep=sleep)


def load_special_equipment(repo_root: Path) -> NormalizedBundle | None:
    """从离线快照重建S-E参考资料。"""
    return load_vehicle_weapons(repo_root, SPECIAL_EQUIPMENT)
