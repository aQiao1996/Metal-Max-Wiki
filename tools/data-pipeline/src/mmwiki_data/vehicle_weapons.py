"""采集战车武器事实，保留原始数值和逐页出处。"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import Field, HttpUrl, model_validator

from mmwiki_data.fetcher import fetch
from mmwiki_data.models import StrictModel, VerificationStatus
from mmwiki_data.normalization import stable_record_id
from mmwiki_data.normalization_models import (
    EquipmentModification,
    NameSet,
    NormalizedBundle,
    NormalizedRecord,
    SourceRef,
)
from mmwiki_data.storage import write_json_atomic
from mmwiki_data.vehicle_tables import (
    acquisition_entries,
    comparable_stat,
    expanded_rows,
    obtainable_stars,
    text,
)

SOURCE_ID = "metalmaniax-mm2r"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A"
_STAT_GROUPS = {"攻撃力": "attack", "守備力": "defense", "弾倉": "magazine", "重量": "weight"}
_COMMON_FIELDS = {
    "攻撃": "attack_raw",
    "範囲": "range_raw",
    "属性": "element_raw",
    "守備": "defense_raw",
    "重量(t)": "weight_raw",
    "弾倉": "magazine_raw",
    "価格(G)": "price_raw",
    "レア": "rarity_raw",
}


@dataclass(frozen=True)
class WeaponProfile:
    kind: Literal["special_equipment", "sub_gun"]
    target_id: str
    directory: str
    label: str
    extra_header: str
    extra_attribute: str

    @property
    def headers(self) -> tuple[str, ...]:
        return (
            "名称",
            "攻撃",
            "範囲",
            "属性",
            "守備",
            "重量(t)",
            "弾倉",
            self.extra_header,
            "価格(G)",
            "レア",
        )

    @property
    def root(self) -> Path:
        return Path("data/raw/mm2r/0.99") / self.directory

    @property
    def attribute_fields(self) -> dict[str, str]:
        return {
            header: self.extra_attribute if header == self.extra_header else _COMMON_FIELDS[header]
            for header in self.headers
            if header != "名称"
        }


SPECIAL_EQUIPMENT = WeaponProfile(
    "special_equipment",
    "maniax-special-equipment",
    "special-equipment",
    "S-E",
    "弾薬(G)",
    "ammunition_price_raw",
)
SUB_GUNS = WeaponProfile(
    "sub_gun", "maniax-sub-guns", "sub-guns", "副炮", "迎撃兵装化", "interception_raw"
)


class VehicleWeaponNames(StrictModel):
    """项目整理的参考译名，不冒充特定汉化版本名称。"""

    schema_version: Literal[1]
    names: dict[str, str]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    effects: dict[str, str] = Field(default_factory=dict)
    acquisition: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_names(self) -> VehicleWeaponNames:
        """别名与说明必须对应已声明的参考名称。"""
        for values in (self.aliases, self.effects, self.acquisition):
            unknown = set(values) - set(self.names)
            if unknown:
                raise ValueError(f"战车武器说明对应未知名称：{sorted(unknown)}")
        return self


class VehicleWeaponFact(StrictModel):
    """一件战车武器的总表与详情事实。"""

    name_ja: str
    overview: dict[str, str]
    overview_ref: SourceRef
    detail_ref: SourceRef
    modifications: list[EquipmentModification]
    acquisition_ja: list[str]
    issues: list[str] = Field(default_factory=list)


class VehicleWeaponSnapshot(StrictModel):
    """不含整页正文和图片的武器事实快照。"""

    schema_version: Literal[1] = 1
    source_id: Literal["metalmaniax-mm2r"] = "metalmaniax-mm2r"
    records: list[VehicleWeaponFact] = Field(min_length=1)
    omitted: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_records(self) -> VehicleWeaponSnapshot:
        """拒绝重复名称、错源引用和重复星级。"""
        names = [record.name_ja for record in self.records]
        if len(names) != len(set(names)):
            raise ValueError("战车武器快照包含重复名称")
        for record in self.records:
            for source in (record.overview_ref, record.detail_ref):
                if (
                    source.source_id != SOURCE_ID
                    or source.target_id != record.overview_ref.target_id
                ):
                    raise ValueError(f"{record.name_ja}: 战车武器来源标识不一致")
                if source.source_url.host != "metalmaniax.com":
                    raise ValueError(f"{record.name_ja}: 战车武器来源主机不正确")
            stars = [item.stars for item in record.modifications]
            if len(stars) != len(set(stars)):
                raise ValueError(f"{record.name_ja}: 重复的星级记录")
        return self


def _detail_facts(
    body: bytes, name: str, *, top_level_only: bool = False
) -> tuple[list[EquipmentModification], list[str], list[str]]:
    soup = BeautifulSoup(body, "html.parser")
    content = soup.select_one("#body")
    if content is None:
        raise ValueError(f"{name}: 缺少详情正文")
    has_heading = any("基本情報" in text(section) for section in content.find_all(["h2", "h3"]))
    tables = content.find_all("table")
    if not tables:
        return [], [], ["source_detail_unavailable"]
    table = tables[0]
    rows = expanded_rows(table)
    if len(rows) < 3 or not all(label in rows[0] for label in ("攻撃力", "守備力", "弾倉", "重量")):
        raise ValueError(f"{name}: 基础数值表头发生变化")
    groups = {
        key: [index for index, label in enumerate(rows[0]) if label == heading]
        for heading, key in _STAT_GROUPS.items()
    }
    if any(len(columns) not in (1, 3) for columns in groups.values()):
        raise ValueError(f"{name}: 基础数值表的字段分组发生变化")
    modifications: list[EquipmentModification] = []
    for row in rows[2:]:
        if not row or row[0] not in ("無印", "★", "★★", "★★★"):
            continue
        if len(row) != len(rows[0]):
            raise ValueError(f"{name}: 星级行与表头列数不一致")
        attack_columns = groups["attack"]
        initial_attack_column = attack_columns[1] if len(attack_columns) == 3 else attack_columns[0]
        if not re.fullmatch(r"[0-9]+", row[initial_attack_column]):
            continue
        values: dict[str, str | int] = {"stars": row[0].count("★")}
        for key, columns in groups.items():
            if len(columns) == 1:
                values.update(
                    {f"{key}_min_raw": "", f"{key}_raw": row[columns[0]], f"{key}_max_raw": ""}
                )
            else:
                values.update(
                    dict(
                        zip(
                            (f"{key}_min_raw", f"{key}_raw", f"{key}_max_raw"),
                            (row[column] for column in columns),
                            strict=True,
                        )
                    )
                )
        modifications.append(
            EquipmentModification.model_validate(
                {
                    **values,
                }
            )
        )
    acquisition = acquisition_entries(content, top_level_only=top_level_only)
    issues = [] if modifications else ["source_modification_unavailable"]
    if not has_heading and not modifications:
        issues.append("source_detail_unavailable")
    return modifications, acquisition, issues


def _load_names(repo_root: Path, profile: WeaponProfile) -> VehicleWeaponNames:
    path = repo_root / profile.root / "names.yaml"
    return VehicleWeaponNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def collect_vehicle_weapons(
    repo_root: Path,
    profile: WeaponProfile,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """串行获取战车武器事实，全部成功后才写入新的快照。"""
    names = _load_names(repo_root, profile)
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)",
        },
    ) as client:
        index = fetch(client, profile.target_id, INDEX_URL)
        soup = BeautifulSoup(index.body, "html.parser")
        content = soup.select_one("#body")
        if content is None:
            raise ValueError("战车武器总表缺少正文")
        candidates = [
            table
            for table in content.find_all("table")
            if tuple(text(cell) for cell in table.find_all("tr")[0].find_all(["td", "th"]))
            == profile.headers
        ]
        if len(candidates) != 1:
            raise ValueError("战车武器总表无法唯一定位")
        table = candidates[0]
        table_index = content.find_all("table").index(table)
        retrieved_at = datetime.now().astimezone()
        records: list[VehicleWeaponFact] = []
        omitted: list[str] = []
        for row_index, row in enumerate(table.find_all("tr")[1:]):
            cells = row.find_all(["td", "th"], recursive=False)
            name = text(cells[0])
            if name == "LOVEマシン":
                omitted.append("LOVEマシン：总表存在配方合并列，独立详情未提供有效数值表")
                continue
            if len(cells) != len(profile.headers):
                raise ValueError(f"{name}: 总表列数不符合预期")
            if name not in names.names:
                raise ValueError(f"{name}: 缺少中文参考名称")
            link = cells[0].find("a", href=True)
            if not isinstance(link, Tag):
                raise ValueError(f"{name}: 缺少独立详情链接")
            url = urljoin(INDEX_URL, str(link["href"]))
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname != "metalmaniax.com":
                raise ValueError(f"{name}: 独立详情地址不在来源主机内")
            sleep(1.0)
            detail = fetch(client, profile.target_id, url)
            modifications, acquisition, issues = _detail_facts(
                detail.body, name, top_level_only=profile.kind == "sub_gun"
            )
            records.append(
                VehicleWeaponFact(
                    name_ja=name,
                    overview=dict(zip(profile.headers, map(text, cells), strict=True)),
                    overview_ref=SourceRef(
                        source_id=SOURCE_ID,
                        target_id=profile.target_id,
                        source_url=HttpUrl(INDEX_URL),
                        retrieved_at=retrieved_at,
                        content_hash=index.content_hash,
                        table_index=table_index,
                        row_index=row_index,
                    ),
                    detail_ref=SourceRef(
                        source_id=SOURCE_ID,
                        target_id=profile.target_id,
                        source_url=HttpUrl(url),
                        retrieved_at=datetime.now().astimezone(),
                        content_hash=detail.content_hash,
                        table_index=0,
                        row_index=0,
                    ),
                    modifications=modifications,
                    acquisition_ja=acquisition,
                    issues=issues,
                )
            )
            print(f"{profile.label} {len(records):02d}：{names.names[name]}", flush=True)
    actual = {record.name_ja for record in records}
    if actual != set(names.names):
        raise ValueError(f"战车武器名称清单与总表不一致：{sorted(set(names.names) ^ actual)}")
    snapshot = VehicleWeaponSnapshot(records=records, omitted=omitted)
    write_json_atomic(repo_root / profile.root / "facts.json", snapshot)
    return {"records": len(records), "modifications": sum(len(r.modifications) for r in records)}


def load_vehicle_weapons(repo_root: Path, profile: WeaponProfile) -> NormalizedBundle | None:
    """从事实快照重建候选战车武器；旧资料集合可独立标准化。"""
    path = repo_root / profile.root / "facts.json"
    if not path.exists():
        if (repo_root / profile.root / "names.yaml").exists():
            raise ValueError(f"{profile.label} 来源快照缺失，请执行对应采集命令")
        return None
    snapshot = VehicleWeaponSnapshot.model_validate_json(path.read_bytes())
    names = _load_names(repo_root, profile)
    if {fact.name_ja for fact in snapshot.records} != set(names.names):
        raise ValueError("战车武器事实快照与中文名称清单不一致")
    records: list[NormalizedRecord] = []
    for fact in snapshot.records:
        name = fact.name_ja
        if set(fact.overview) != set(profile.headers) or any(
            ref.target_id != profile.target_id for ref in (fact.overview_ref, fact.detail_ref)
        ):
            raise ValueError(f"{name}: 武器总表字段或来源标识不一致")
        issues = list(fact.issues)
        attributes: dict[str, str | int | float | bool | None] = {
            field: fact.overview[header]
            for header, field in profile.attribute_fields.items()
            if fact.overview[header]
        }
        rarity = fact.overview["レア"]
        fixed_stars = len(rarity) if re.fullmatch(r"★{1,3}", rarity) else 0
        available_stars = obtainable_stars(rarity, fact.acquisition_ja, name)
        if available_stars:
            attributes["obtainable_stars_raw"] = ",".join(map(str, sorted(available_stars)))
        primary = next((m for m in fact.modifications if m.stars == fixed_stars), None)
        if primary is not None:
            differences: list[str] = []
            if fixed_stars == 0:
                for header, field in (
                    ("攻撃", "attack_raw"),
                    ("守備", "defense_raw"),
                    ("弾倉", "magazine_raw"),
                    ("重量(t)", "weight_raw"),
                ):
                    overview_value = fact.overview[header]
                    detail_value = str(getattr(primary, field))
                    if detail_value and comparable_stat(overview_value) != comparable_stat(
                        detail_value
                    ):
                        differences.append(
                            f"{header}：总表 {overview_value}，独立详情 {detail_value}"
                        )
            if differences:
                attributes["source_difference_raw"] = "；".join(differences)
                issues.append("source_value_difference")
            for field in (
                "attack_raw",
                "attack_max_raw",
                "defense_raw",
                "defense_max_raw",
                "magazine_raw",
                "magazine_max_raw",
                "weight_raw",
                "weight_max_raw",
            ):
                value = getattr(primary, field)
                if value and value not in ("-", "t", "?", "?t"):
                    attributes[field] = (
                        value.removesuffix("t") if field.startswith("weight_") else value
                    )
                else:
                    attributes.pop(field, None)
            attributes["stat_condition_raw"] = (
                f"{fixed_stars} 星初始值；取自独立详情，改造上限不含超改造"
            )
        else:
            attributes["stat_condition_raw"] = "来源总表参考值；独立详情尚未提供完整改造数值"
        if fact.acquisition_ja:
            attributes["acquisition_ja_raw"] = "；".join(fact.acquisition_ja)
        if name in names.acquisition:
            attributes["acquisition_raw"] = names.acquisition[name]
        if name in names.effects:
            attributes["notes_raw"] = names.effects[name]
        if profile.kind == "sub_gun":
            attributes["interception_note_raw"] = (
                "源表只标记迎击兵装化适用性，不代表装备后无条件自动迎击。"
            )
        records.append(
            NormalizedRecord(
                id=stable_record_id("equipment", profile.kind, name),
                domain="equipment",
                kind=profile.kind,
                names=NameSet(
                    ja=name, zh_reference=names.names[name], aliases=names.aliases.get(name, [])
                ),
                attributes=attributes,
                modifications=fact.modifications,
                version_scope=["mm2r-jp"],
                verification_status=VerificationStatus.SOURCE_ONLY,
                source_refs=[fact.overview_ref, fact.detail_ref],
                issues=issues,
            )
        )
    return NormalizedBundle(
        domain="equipment",
        records=sorted(records, key=lambda record: record.id),
        source_hashes=[source.content_hash for record in records for source in record.source_refs],
    )
