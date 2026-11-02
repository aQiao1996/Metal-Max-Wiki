"""读取装备的未加星基础常量，并保留每个字段的 ROM 位置。"""

import re
import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from mmwiki_data.normalization_models import NormalizedRecord
from mmwiki_data.rom_reader import RomFile, RomItemName, read_nds_file, read_pak_files

ParameterField = Literal[
    "attack_raw",
    "defense_raw",
    "weight_raw",
    "capacity_raw",
    "magazine_raw",
    "accuracy_raw",
    "evasion_raw",
]
ParameterTable = Literal["ENGINE.ARR", "CUNIT.ARR", "CARWEPON.ARR", "NINGEN_BUKI.ARR"]
PARAMETER_FIELDS: dict[
    int,
    tuple[
        ParameterTable,
        Literal[8, 12, 20],
        tuple[tuple[ParameterField, int, Literal[1, 2], Literal[1, 100]], ...],
    ],
] = {
    1: ("NINGEN_BUKI.ARR", 8, (("attack_raw", 2, 2, 1),)),
    12: (
        "ENGINE.ARR",
        12,
        (
            ("weight_raw", 2, 2, 100),
            ("defense_raw", 4, 1, 1),
            ("capacity_raw", 6, 2, 100),
        ),
    ),
    13: (
        "CUNIT.ARR",
        12,
        (
            ("weight_raw", 2, 2, 100),
            ("defense_raw", 4, 1, 1),
            ("accuracy_raw", 6, 1, 1),
            ("evasion_raw", 7, 1, 1),
        ),
    ),
}
for _kind in (14, 15, 16):
    PARAMETER_FIELDS[_kind] = (
        "CARWEPON.ARR",
        20,
        (
            ("weight_raw", 2, 2, 100),
            ("defense_raw", 4, 1, 1),
            ("attack_raw", 6, 2, 1),
            ("magazine_raw", 13, 1, 1),
        ),
    )


@dataclass(frozen=True)
class RomParameter:
    field: ParameterField
    value: Decimal
    offset: int
    byte_length: Literal[1, 2]
    encoded: int
    scale: Literal[1, 100]


@dataclass(frozen=True)
class RomEquipment:
    item: RomItemName
    item_price: int
    parameter_index: int
    table: ParameterTable
    record_offset: int
    record_width: Literal[8, 12, 20]
    parameters: tuple[RomParameter, ...]


def decimal_text(value: Decimal) -> str:
    """将可比较数值序列化为不带指数的规范字符串。"""
    return format(value.normalize(), "f")


def reference_parameters(record: NormalizedRecord) -> dict[str, Decimal] | None:
    """只取来源明确的无星基础值，保留非零星级和成长装备的条件边界。"""
    kind = record.kind
    code = {
        "human_weapon": 1,
        "engine": 12,
        "c_unit": 13,
        "main_cannon": 14,
        "sub_gun": 15,
        "special_equipment": 16,
    }.get(kind)
    if code is None:
        return None
    values: dict[str, str | int | float | bool | None] = dict(record.attributes)
    modifications = (
        record.engine_modifications
        if kind == "engine"
        else record.control_modifications
        if kind == "c_unit"
        else record.modifications
    )
    zero = next((mod for mod in modifications if mod.stars == 0), None)
    if zero is not None:
        values = zero.model_dump()
    else:
        condition = str(record.attributes.get("stat_condition_raw", ""))
        if condition and not condition.startswith("0 "):
            return None
    result: dict[str, Decimal] = {}
    for field, _, _, _ in PARAMETER_FIELDS[code][2]:
        raw = str(values.get(field, "")).removesuffix("t").strip()
        if field == "magazine_raw" and raw == "∞":
            raw = "0"
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw) is None:
            return None
        result[field] = Decimal(raw)
    return result


def _file(files: dict[str, RomFile], name: str, width: int) -> RomFile:
    file = files[name]
    if len(file.data) % width:
        raise ValueError(f"ROM 装备表长度不完整：{name}")
    return file


def read_equipment(rom: bytes, items: tuple[RomItemName, ...]) -> tuple[RomEquipment, ...]:
    """按物品记录中的参数索引读取基础常量，不解释星级、改造或战斗公式。"""
    files = read_pak_files(read_nds_file(rom, "xls/data/pack_data.pak"))
    index = _file(files, "ITEMLIST.ARR", 12)
    result: list[RomEquipment] = []
    for item in items:
        layout = PARAMETER_FIELDS.get(item.kind)
        if layout is None or not item.name:
            continue
        table_name, width, fields = layout
        table = _file(files, table_name, width)
        entry = item.item_id * 12
        if entry + 12 > len(index.data):
            raise ValueError(f"ROM 物品索引越界：{item.item_id}")
        param_index = int(struct.unpack_from("<H", index.data, entry + 10)[0])
        price = int(struct.unpack_from("<I", index.data, entry + 4)[0])
        at = param_index * width
        if at + width > len(table.data):
            raise ValueError(f"ROM 装备参数索引越界：{item.item_id}")
        values = []
        for field, relative, size, scale in fields:
            encoded = int.from_bytes(table.data[at + relative : at + relative + size], "little")
            values.append(
                RomParameter(
                    field,
                    Decimal(encoded) / scale,
                    table.offset + at + relative,
                    size,
                    encoded,
                    scale,
                )
            )
        result.append(
            RomEquipment(
                item, price, param_index, table_name, table.offset + at, width, tuple(values)
            )
        )
    return tuple(result)
