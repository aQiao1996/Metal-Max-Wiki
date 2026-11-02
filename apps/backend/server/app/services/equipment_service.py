import re
from math import isfinite
from unicodedata import normalize

from app.core.errors import BusinessError
from app.repositories.equipment_repository import load_equipment
from app.schemas.equipment import (
    EquipmentListData,
    EquipmentProfession,
    EquipmentRecord,
    EquipmentSort,
    EquipmentType,
)
from app.schemas.response import PaginationMeta
from app.services.game_version_service import list_game_versions

EQUIPMENT_TYPES: tuple[EquipmentType, ...] = (
    "human-weapon",
    "main-cannon",
    "sub-gun",
    "special-equipment",
    "c-unit",
    "engine",
)

_ATTRIBUTE_LABELS = {
    "attack_raw": "攻击力",
    "defense_raw": "防御力",
    "weight_raw": "重量",
    "magazine_raw": "弹仓",
    "range_raw": "范围",
    "element_raw": "属性",
    "special_shell_raw": "特殊炮弹",
    "price_raw": "价格",
    "rarity_raw": "稀有度",
    "stars_raw": "星级",
    "acquisition_raw": "获取方式",
    "additional_raw": "追加效果",
    "notes_raw": "备注",
    "stat_condition_raw": "数值条件",
    "attack_max_raw": "普通改造攻击上限",
    "defense_max_raw": "普通改造防御上限",
    "magazine_max_raw": "普通改造弹仓上限",
    "weight_max_raw": "重量参考上限",
    "acquisition_ja_raw": "获取地点原始记录（日文）",
    "obtainable_stars_raw": "来源标注可获取星级",
    "source_difference_raw": "同星级来源数值差异（尚待核对）",
}
_PROFESSION_LABELS = {
    "hunter": "猎人",
    "mechanic": "机械师",
    "soldier": "战士",
    "nurse": "护士",
    "artist": "艺术家",
    "wrestler": "摔跤手",
}


def equipment_facts(record: EquipmentRecord) -> dict[str, str]:
    """用中文字段组织资料，数值和原文保持不变。"""
    facts = {
        label: str(record.attributes[key])
        for key, label in _ATTRIBUTE_LABELS.items()
        if key in record.attributes
    }
    if record.kind == "human_weapon":
        facts["可用职业"] = "、".join(
            label
            for key, label in _PROFESSION_LABELS.items()
            if record.attributes.get(f"{key}_raw") == "○"
        )
    if record.kind == "special_equipment":
        facts["名称说明"] = "中文参考译名，未核对 0.99 实机名称"
        if "range_raw" in record.attributes:
            facts["攻击方式"] = (
                str(record.attributes["range_raw"])
                .replace("連射", "连射")
                .replace("回", "次攻击")
                .replace("迎撃", "迎击")
            )
        facts["逐星级普通改造"] = (
            "；".join(
                f"{item.stars} 星：攻击 {item.attack_raw} → {item.attack_max_raw or '未收录'}，"
                f"防御 {item.defense_raw} → {item.defense_max_raw or '未收录'}，"
                f"弹仓 {item.magazine_raw} → {item.magazine_max_raw or '未收录'}，"
                f"重量 {item.weight_raw} → {item.weight_max_raw or '未收录'}"
                for item in record.modifications
            )
            or "来源未提供改造数值"
        )
        facts["改造说明"] = (
            "各星级独立列出，不含超改造；固定星级装备的其他星级仅为图鉴参考，不能当作可获取星级；横杠表示来源未注明或不可改造"
        )
    return facts


def require_available_version(version: str) -> None:
    """确保查询不会跨越尚未开放的版本。"""
    if not any(
        item.slug == version and item.status == "available" for item in list_game_versions()
    ):
        raise BusinessError(404, "该版本的资料尚未开放")


def equipment_text(record: EquipmentRecord) -> str:
    """生成覆盖名称、别名与属性的检索文本。"""
    values = [
        record.name,
        record.names.ja or "",
        record.names.zh_09 or "",
        record.names.zh_099 or "",
        record.names.zh_reference or "",
        *record.names.aliases,
    ]
    values.extend(str(value) for value in record.attributes.values())
    return normalize("NFKC", " ".join(values)).casefold()


def numeric_attribute(record: EquipmentRecord, key: str) -> float | None:
    """仅将有限数值和无符号纯十进制原文用于排序。"""
    value = record.attributes.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if isfinite(number) else None
    raw = record.attributes.get(f"{key}_raw")
    if isinstance(raw, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        number = float(raw)
        return number if isfinite(number) else None
    return None


def list_equipment(
    version: str,
    *,
    equipment_type: EquipmentType | None = None,
    q: str = "",
    element: str = "",
    profession: EquipmentProfession | None = None,
    sort: EquipmentSort = "name-asc",
    page: int = 1,
    page_size: int = 20,
) -> EquipmentListData:
    """按版本查询装备，返回稳定分页与筛选选项。"""
    require_available_version(version)
    records = load_equipment()
    query = normalize("NFKC", q.strip()).casefold()
    type_counts = {kind: sum(r.equipment_type == kind for r in records) for kind in EQUIPMENT_TYPES}
    typed = [r for r in records if equipment_type is None or r.equipment_type == equipment_type]
    elements = sorted(
        {str(r.attributes["element_raw"]) for r in typed if "element_raw" in r.attributes}
    )
    filtered = [
        r
        for r in typed
        if (not query or query in equipment_text(r))
        and (not element or r.attributes.get("element_raw") == element)
        and (profession is None or r.attributes.get(f"{profession}_raw") == "○")
    ]
    if sort == "name-asc":
        filtered.sort(key=lambda r: (r.name, r.id))
    else:
        key = {"attack-desc": "attack", "price-asc": "price", "weight-asc": "weight"}[sort]

        def sort_key(record: EquipmentRecord) -> tuple[bool, float, str]:
            value = numeric_attribute(record, key)
            return (
                value is None,
                -(value or 0) if sort == "attack-desc" else (value or 0),
                record.id,
            )

        filtered.sort(key=sort_key)
    start = (page - 1) * page_size
    return EquipmentListData(
        list=filtered[start : start + page_size],
        pagination=PaginationMeta.create(page=page, page_size=page_size, total=len(filtered)),
        type_counts=type_counts,
        elements=elements,
    )


def get_equipment(version: str, equipment_id: str) -> EquipmentRecord:
    """按稳定 ID 获取装备详情。"""
    require_available_version(version)
    record = next((r for r in load_equipment() if r.id == equipment_id), None)
    if record is None:
        raise BusinessError(404, "没有找到这件装备")
    return record
