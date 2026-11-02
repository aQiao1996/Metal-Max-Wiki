"""采集引擎型号、逐星级数值和马力强化路径。"""

import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import Field, HttpUrl, model_validator

from mmwiki_data.fetcher import fetch
from mmwiki_data.models import StrictModel, VerificationStatus
from mmwiki_data.normalization import stable_record_id
from mmwiki_data.normalization_models import (
    EngineModification,
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
from mmwiki_data.vehicle_traits import TraitDescription, TraitFact

SOURCE_ID = "metalmaniax-mm2r"
TARGET_ID = "maniax-engines"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A"
_ROOT = Path("data/raw/mm2r/0.99/engines")
_HEADERS = ("名称", "積載量", "守備", "重量(t)", "特性", "価格(G)", "レア")
_ATTRIBUTE_FIELDS = {
    "積載量": "capacity_raw",
    "守備": "defense_raw",
    "重量(t)": "weight_raw",
    "特性": "trait_raw",
    "価格(G)": "price_raw",
    "レア": "rarity_raw",
}


class EngineTraitDescription(TraitDescription):
    calculation_source: HttpUrl | None = None


class EngineNames(StrictModel):
    schema_version: Literal[1]
    names: dict[str, str]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    acquisition: dict[str, str] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    rental_only_stars: dict[str, list[Annotated[int, Field(ge=0, le=3)]]] = Field(
        default_factory=dict
    )
    traits: dict[str, EngineTraitDescription]
    capacity_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_names(self) -> EngineNames:
        """说明只能引用已声明的型号。"""
        for values in (self.aliases, self.acquisition, self.notes, self.rental_only_stars):
            if set(values) - set(self.names):
                raise ValueError("引擎说明包含未知名称")
        for trait in self.traits.values():
            if trait.calculation_source is not None and (
                trait.calculation_source.scheme != "https"
                or trait.calculation_source.host != "metalmaniax.com"
            ):
                raise ValueError("引擎加成说明地址不在来源主机内")
        return self


class EngineDetail(StrictModel):
    detail_trait: str
    detail_price: str
    upgrade_to_ja: str | None
    upgrade_cost_raw: str | None
    modifications: list[EngineModification] = Field(min_length=1)
    acquisition_ja: list[str]


class EngineFact(EngineDetail):
    name_ja: str
    overview: dict[str, str]
    overview_ref: SourceRef
    detail_ref: SourceRef


class EngineSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    source_id: Literal["metalmaniax-mm2r"] = "metalmaniax-mm2r"
    records: list[EngineFact] = Field(min_length=1)
    traits: list[TraitFact]
    omitted: list[str]

    @model_validator(mode="after")
    def validate_records(self) -> EngineSnapshot:
        """拒绝重复型号、错源引用和无法闭合的强化路径。"""
        by_name = {record.name_ja: record for record in self.records}
        if len(by_name) != len(self.records):
            raise ValueError("引擎快照包含重复型号")
        if len({trait.name_ja for trait in self.traits}) != len(self.traits):
            raise ValueError("引擎快照包含重复特性")
        refs = [trait.source_ref for trait in self.traits]
        for record in self.records:
            if set(record.overview) != set(_HEADERS):
                raise ValueError(f"{record.name_ja}: 总表字段不完整")
            if len({item.stars for item in record.modifications}) != len(record.modifications):
                raise ValueError(f"{record.name_ja}: 星级重复")
            if (record.upgrade_to_ja is None) != (record.upgrade_cost_raw is None):
                raise ValueError(f"{record.name_ja}: 强化型号与费用不完整")
            if record.upgrade_cost_raw is not None and not re.fullmatch(
                r"[0-9,]+", record.upgrade_cost_raw
            ):
                raise ValueError(f"{record.name_ja}: 强化费用格式不正确")
            visited = {record.name_ja}
            target = record.upgrade_to_ja
            while target is not None:
                if target not in by_name or target in visited:
                    raise ValueError(f"{record.name_ja}: 强化路径缺少型号或形成循环")
                visited.add(target)
                target = by_name[target].upgrade_to_ja
            refs.extend((record.overview_ref, record.detail_ref))
        for ref in refs:
            if (
                ref.source_id != SOURCE_ID
                or ref.target_id != TARGET_ID
                or ref.source_url.scheme != "https"
                or ref.source_url.host != "metalmaniax.com"
            ):
                raise ValueError("引擎来源标识或地址不正确")
        return self


def _load_names(repo_root: Path) -> EngineNames:
    return EngineNames.model_validate(
        yaml.safe_load((repo_root / _ROOT / "names.yaml").read_text(encoding="utf-8"))
    )


def _find_table(content: Tag, headers: tuple[str, ...]) -> tuple[int, Tag]:
    matches = [
        (index, table)
        for index, table in enumerate(content.find_all("table"))
        if tuple(text(cell) for cell in table.find_all("tr")[0].find_all(["td", "th"])) == headers
    ]
    if len(matches) != 1:
        raise ValueError(f"引擎无法唯一定位表头：{headers}")
    return matches[0]


def _detail_facts(body: bytes, name: str) -> EngineDetail:
    content = BeautifulSoup(body, "html.parser").select_one("#body")
    if content is None or not (tables := content.find_all("table")):
        raise ValueError(f"{name}: 缺少详情数值表")
    table = tables[0]
    rows = expanded_rows(table)
    headings = ("積載量", "守備力", "重量", "販売価格")
    if len(rows) < 3 or not all(heading in rows[0] for heading in headings):
        raise ValueError(f"{name}: 数值表头发生变化")
    groups = {
        heading: [index for index, label in enumerate(rows[0]) if label == heading]
        for heading in headings
    }
    if [len(groups[heading]) for heading in headings] != [1, 3, 3, 1]:
        raise ValueError(f"{name}: 数值字段分组发生变化")
    modifications: list[EngineModification] = []
    prices: list[str] = []
    for row in rows[2:]:
        if not row or row[0] not in ("無印", "-", "★", "★★", "★★★"):
            continue
        if len(row) != len(rows[0]):
            raise ValueError(f"{name}: 星级行与表头列数不一致")
        capacity = row[groups["積載量"][0]]
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?t", capacity):
            if capacity in ("", "t", "?", "?t"):
                continue
            raise ValueError(f"{name}: 载重格式无法识别：{capacity}")
        values: dict[str, str | int] = {"stars": row[0].count("★"), "capacity_raw": capacity}
        for heading, key in (("守備力", "defense"), ("重量", "weight")):
            values.update(
                dict(
                    zip(
                        (f"{key}_min_raw", f"{key}_raw", f"{key}_max_raw"),
                        (row[index] for index in groups[heading]),
                        strict=True,
                    )
                )
            )
        modifications.append(EngineModification.model_validate(values))
        prices.append(row[groups["販売価格"][0]].removesuffix("G"))
    if not modifications or len(set(prices)) != 1:
        raise ValueError(f"{name}: 数值缺失或不同星级价格存在差异")
    trait = upgrade = ""
    for row_tag in table.find_all("tr"):
        cells = row_tag.find_all(["td", "th"], recursive=False)
        for index, cell in enumerate(cells[:-1]):
            if text(cell) == "特性":
                trait = text(cells[index + 1])
            if text(cell) == "馬力強化":
                upgrade = text(cells[index + 1])
    upgrade_to: str | None = None
    upgrade_cost: str | None = None
    if upgrade != "不可":
        match = re.fullmatch(r"可\s*\(\s*(.+?)\s*[:：]\s*([0-9,]+)G\s*\)", upgrade)
        if match is None:
            raise ValueError(f"{name}: 马力强化内容无法识别：{upgrade}")
        upgrade_to, upgrade_cost = match[1], match[2]
    if not trait:
        raise ValueError(f"{name}: 详情缺少特性")
    return EngineDetail(
        detail_trait=trait,
        detail_price=prices[0],
        upgrade_to_ja=upgrade_to,
        upgrade_cost_raw=upgrade_cost,
        modifications=modifications,
        acquisition_ja=acquisition_entries(content, top_level_only=True),
    )


def collect_engines(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行采集所有引擎型号，完成校验后原子写入事实快照。"""
    names = _load_names(repo_root)
    records: list[EngineFact] = []
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"},
    ) as client:
        index = fetch(client, TARGET_ID, INDEX_URL)
        content = BeautifulSoup(index.body, "html.parser").select_one("#body")
        if content is None:
            raise ValueError("引擎总表缺少正文")
        table_index, table = _find_table(content, _HEADERS)
        trait_index, trait_table = _find_table(content, ("名称", "効果", "備考"))
        retrieved_at = datetime.now().astimezone()

        def index_ref(table_id: int, row_id: int) -> SourceRef:
            return SourceRef(
                source_id=SOURCE_ID,
                target_id=TARGET_ID,
                source_url=HttpUrl(INDEX_URL),
                retrieved_at=retrieved_at,
                content_hash=index.content_hash,
                table_index=table_id,
                row_index=row_id,
            )

        traits = [
            TraitFact(
                name_ja=text(cells[0]),
                effect_ja=text(cells[1]),
                limits_ja=text(cells[2]),
                source_ref=index_ref(trait_index, row_index),
            )
            for row_index, row in enumerate(trait_table.find_all("tr")[1:])
            if len(cells := row.find_all(["td", "th"], recursive=False)) == 3
            and text(cells[0]) in names.traits
        ]
        expanded = expanded_rows(table)[1:]
        original = table.find_all("tr")[1:]
        for row_index, (values, row) in enumerate(zip(expanded, original, strict=True)):
            name = values[0]
            if name == "LOVEマシン":
                continue
            if len(values) != 8 or values[0] != values[1]:
                raise ValueError(f"{name}: 总表名称合并列发生变化")
            values = [values[0], *values[2:]]
            if len(values) != len(_HEADERS) or name not in names.names:
                raise ValueError(f"{name}: 总表字段或参考名称不完整")
            cell = row.find(["td", "th"])
            link = cell.find("a", href=True) if cell is not None else None
            if not isinstance(link, Tag):
                raise ValueError(f"{name}: 缺少独立详情链接")
            url = urljoin(INDEX_URL, str(link["href"]))
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "metalmaniax.com":
                raise ValueError(f"{name}: 详情地址不在来源主机内")
            sleep(1.0)
            detail = fetch(client, TARGET_ID, url)
            parsed = _detail_facts(detail.body, name)
            records.append(
                EngineFact(
                    **parsed.model_dump(),
                    name_ja=name,
                    overview=dict(zip(_HEADERS, values, strict=True)),
                    overview_ref=index_ref(table_index, row_index),
                    detail_ref=SourceRef(
                        source_id=SOURCE_ID,
                        target_id=TARGET_ID,
                        source_url=HttpUrl(url),
                        retrieved_at=datetime.now().astimezone(),
                        content_hash=detail.content_hash,
                        table_index=0,
                        row_index=0,
                    ),
                )
            )
            print(f"引擎 {len(records):03d}：{names.names[name]}", flush=True)
    snapshot = EngineSnapshot(
        records=records,
        traits=traits,
        omitted=["LOVE 机器 2311/2312/2313：配方合并行尚未建立独立事实条目"],
    )
    if {record.name_ja for record in records} != set(names.names):
        raise ValueError("引擎总表与参考名称清单不一致")
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {"records": len(records), "modifications": sum(len(r.modifications) for r in records)}


def load_engines(repo_root: Path) -> NormalizedBundle | None:
    """离线重建引擎参考资料，型号升级与星级分别保存。"""
    path = repo_root / _ROOT / "facts.json"
    if not path.exists():
        if (repo_root / _ROOT / "names.yaml").exists():
            raise ValueError("引擎事实快照缺失，请执行 pnpm data:collect:engines")
        return None
    snapshot = EngineSnapshot.model_validate_json(path.read_bytes())
    names = _load_names(repo_root)
    if {fact.name_ja for fact in snapshot.records} != set(names.names):
        raise ValueError("引擎事实快照与参考名称清单不一致")
    traits = {fact.name_ja: fact for fact in snapshot.traits}
    predecessors: dict[str, list[str]] = {}
    for fact in snapshot.records:
        if fact.upgrade_to_ja is not None:
            predecessors.setdefault(fact.upgrade_to_ja, []).append(fact.name_ja)
    records: list[NormalizedRecord] = []
    for fact in snapshot.records:
        name = fact.name_ja
        if fact.detail_trait not in names.traits or fact.detail_trait not in traits:
            raise ValueError(f"{name}: 特性缺少说明或来源")
        trait = names.traits[fact.detail_trait]
        trait_fact = traits[fact.detail_trait]
        attributes: dict[str, str | int | float | bool | None] = {
            field: fact.overview[header]
            for header, field in _ATTRIBUTE_FIELDS.items()
            if fact.overview[header]
        }
        attributes.update(
            trait_raw=fact.detail_trait,
            trait_name_raw=trait.name,
            trait_activation_raw=trait.activation,
            trait_effect_raw=trait.effect,
            trait_limits_raw=trait.limits,
            trait_effect_ja_raw=trait_fact.effect_ja,
            trait_limits_ja_raw=trait_fact.limits_ja,
            capacity_note_raw=names.capacity_note,
        )
        if trait.calculation_source is not None:
            attributes["trait_calculation_source_raw"] = str(trait.calculation_source)
        differences: list[str] = []
        if fact.overview["特性"] != fact.detail_trait:
            differences.append(f"特性：总表 {fact.overview['特性']}，独立详情 {fact.detail_trait}")
        if fact.detail_price:
            overview_price = fact.overview["価格(G)"]
            if overview_price and comparable_stat(overview_price) != comparable_stat(
                fact.detail_price
            ):
                differences.append(f"价格：总表 {overview_price}，独立详情 {fact.detail_price}")
            attributes["price_raw"] = fact.detail_price
        rarity = fact.overview["レア"]
        fixed_stars = len(rarity) if re.fullmatch(r"★{1,3}", rarity) else 0
        primary = next((item for item in fact.modifications if item.stars == fixed_stars), None)
        if primary is None:
            raise ValueError(f"{name}: 缺少 {fixed_stars} 星初始数值")
        for header, key in _ATTRIBUTE_FIELDS.items():
            if key not in ("capacity_raw", "defense_raw", "weight_raw"):
                continue
            value = str(getattr(primary, key))
            if (
                fixed_stars == 0
                and value
                and comparable_stat(value) != comparable_stat(fact.overview[header])
            ):
                differences.append(f"{header}：总表 {fact.overview[header]}，独立详情 {value}")
            if value not in ("", "-", "t", "?", "?t"):
                attributes[key] = value.removesuffix("t")
            else:
                attributes.pop(key, None)
        attributes["stat_condition_raw"] = f"{fixed_stars} 星、当前型号的初始值；未计特性加成"
        available = obtainable_stars(rarity, fact.acquisition_ja, name)
        if any(re.search(r"★(?:無し|なし|無印)", location) for location in fact.acquisition_ja):
            available = sorted({*available, 0})
        rental_stars = names.rental_only_stars.get(name, [])
        if not set(rental_stars).issubset(available):
            raise ValueError(f"{name}: 租赁星级与来源记录不一致")
        if rental_stars:
            attributes["rental_stars_raw"] = ",".join(map(str, rental_stars))
            available = sorted(set(available) - set(rental_stars))
        if available:
            attributes["obtainable_stars_raw"] = ",".join(map(str, available))
        acquisition = []
        if name in predecessors:
            acquisition.append(
                "由" + "、".join(names.names[p] for p in predecessors[name]) + "马力强化获得"
            )
        if name in names.acquisition:
            acquisition.append(names.acquisition[name])
        if not acquisition:
            raise ValueError(f"{name}: 缺少中文获取说明")
        attributes["acquisition_raw"] = "；".join(acquisition)
        if fact.acquisition_ja:
            attributes["acquisition_ja_raw"] = "；".join(fact.acquisition_ja)
        if fact.upgrade_to_ja is not None:
            attributes["upgrade_to_ja_raw"] = fact.upgrade_to_ja
            attributes["upgrade_to_raw"] = names.names[fact.upgrade_to_ja]
            attributes["upgrade_cost_raw"] = fact.upgrade_cost_raw
        else:
            attributes["upgrade_note_raw"] = "来源记录此型号不能继续马力强化"
        if name in names.notes:
            attributes["notes_raw"] = names.notes[name]
        issues: list[str] = []
        if differences:
            attributes["source_difference_raw"] = "；".join(differences)
            issues.append("source_value_difference")
        records.append(
            NormalizedRecord(
                id=stable_record_id("equipment", "engine", name),
                domain="equipment",
                kind="engine",
                names=NameSet(
                    ja=name, zh_reference=names.names[name], aliases=names.aliases.get(name, [])
                ),
                attributes=attributes,
                engine_modifications=fact.modifications,
                version_scope=["mm2r-jp"],
                verification_status=VerificationStatus.SOURCE_ONLY,
                source_refs=[fact.overview_ref, fact.detail_ref, trait_fact.source_ref],
                issues=issues,
            )
        )
    return NormalizedBundle(
        domain="equipment",
        records=sorted(records, key=lambda record: record.id),
        source_hashes=[source.content_hash for record in records for source in record.source_refs],
    )
