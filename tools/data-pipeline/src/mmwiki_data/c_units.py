"""采集 C 装置的面板、特性和获取事实。"""

import re
import time
from collections.abc import Callable
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
    ControlModification,
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
TARGET_ID = "maniax-c-units"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A"
MECHANICS_URL = (
    "https://metalmaniax.com/index.php?MM2R/%E6%A4%9C%E8%A8%BC/"
    "C%E3%83%A6%E3%83%8B%E3%83%83%E3%83%88%E3%81%AE%E5%91%BD%E4%B8%AD%E3%83%BB"
    "%E5%9B%9E%E9%81%BF%E3%81%AE%E8%AC%8E"
)
_ROOT = Path("data/raw/mm2r/0.99/c-units")
_HEADERS = ("名称", "命中", "回避", "守備", "重量(t)", "特性", "価格(G)", "レア")
_STAT_GROUPS = {
    "命中率(％)": "accuracy",
    "回避率(％)": "evasion",
    "守備力": "defense",
    "重量": "weight",
}
_ATTRIBUTE_FIELDS = {
    "命中": "accuracy_raw",
    "回避": "evasion_raw",
    "守備": "defense_raw",
    "重量(t)": "weight_raw",
    "特性": "trait_raw",
    "価格(G)": "price_raw",
    "レア": "rarity_raw",
}


class CUnitNames(StrictModel):
    schema_version: Literal[1]
    names: dict[str, str]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    acquisition: dict[str, str]
    notes: dict[str, str] = Field(default_factory=dict)
    traits: dict[str, TraitDescription]
    mechanics_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_names(self) -> CUnitNames:
        """说明必须对应明确名称。"""
        for values in (self.aliases, self.acquisition, self.notes):
            if set(values) - set(self.names):
                raise ValueError("C 装置说明包含未知名称")
        return self


class CUnitFact(StrictModel):
    name_ja: str
    overview: dict[str, str]
    overview_ref: SourceRef
    detail_ref: SourceRef
    detail_trait: str
    detail_price: str
    modifications: list[ControlModification]
    acquisition_ja: list[str]
    issues: list[str] = Field(default_factory=list)


class CUnitSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    source_id: Literal["metalmaniax-mm2r"] = "metalmaniax-mm2r"
    records: list[CUnitFact] = Field(min_length=1)
    traits: list[TraitFact]
    mechanics_ref: SourceRef
    omitted: list[str]

    @model_validator(mode="after")
    def validate_records(self) -> CUnitSnapshot:
        """阻止重复条目、错源定位和无效星级。"""
        names = [record.name_ja for record in self.records]
        if len(names) != len(set(names)):
            raise ValueError("C 装置快照包含重复名称")
        trait_names = [trait.name_ja for trait in self.traits]
        if len(trait_names) != len(set(trait_names)):
            raise ValueError("C 装置快照包含重复特性")
        refs = [self.mechanics_ref, *(trait.source_ref for trait in self.traits)]
        for record in self.records:
            if set(record.overview) != set(_HEADERS):
                raise ValueError(f"{record.name_ja}: 总表字段不完整")
            stars = [item.stars for item in record.modifications]
            if len(stars) != len(set(stars)):
                raise ValueError(f"{record.name_ja}: 重复的星级记录")
            refs.extend((record.overview_ref, record.detail_ref))
        for ref in refs:
            if (
                ref.source_id != SOURCE_ID
                or ref.target_id != TARGET_ID
                or ref.source_url.host != "metalmaniax.com"
                or ref.source_url.scheme != "https"
            ):
                raise ValueError("C 装置来源标识或主机不正确")
        return self


def _load_names(repo_root: Path) -> CUnitNames:
    path = repo_root / _ROOT / "names.yaml"
    return CUnitNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _trait_key(value: str) -> str:
    return value.replace("会心の1発", "会心の一発")


def _find_table(content: Tag, headers: tuple[str, ...]) -> tuple[int, Tag]:
    tables = content.find_all("table")
    matches = [
        (index, table)
        for index, table in enumerate(tables)
        if tuple(text(cell) for cell in table.find_all("tr")[0].find_all(["td", "th"])) == headers
    ]
    if len(matches) != 1:
        raise ValueError(f"C 装置无法唯一定位表头：{headers}")
    return matches[0]


def _detail_facts(body: bytes, name: str) -> tuple[list[ControlModification], list[str], str, str]:
    content = BeautifulSoup(body, "html.parser").select_one("#body")
    if content is None:
        raise ValueError(f"{name}: 详情缺少正文")
    tables = content.find_all("table")
    if not tables:
        raise ValueError(f"{name}: 详情缺少基础数值表")
    rows = expanded_rows(tables[0])
    if len(rows) < 3 or not all(heading in rows[0] for heading in _STAT_GROUPS):
        raise ValueError(f"{name}: 基础数值表头发生变化")
    groups = {
        key: [index for index, label in enumerate(rows[0]) if label == heading]
        for heading, key in _STAT_GROUPS.items()
    }
    if any(len(columns) != 3 for columns in groups.values()):
        raise ValueError(f"{name}: 基础数值字段分组发生变化")
    modifications: list[ControlModification] = []
    for row in rows[2:]:
        if not row or row[0] not in ("無印", "-", "★", "★★", "★★★"):
            continue
        if len(row) != len(rows[0]):
            raise ValueError(f"{name}: 星级行与表头列数不一致")
        if not any(re.fullmatch(r"[0-9]+", row[columns[1]]) for columns in groups.values()):
            continue
        values: dict[str, str | int] = {"stars": row[0].count("★")}
        for key, columns in groups.items():
            values.update(
                dict(
                    zip(
                        (f"{key}_min_raw", f"{key}_raw", f"{key}_max_raw"),
                        (row[column] for column in columns),
                        strict=True,
                    )
                )
            )
        modifications.append(ControlModification.model_validate(values))
    if not modifications:
        raise ValueError(f"{name}: 未解析到有效面板数值")
    trait = price = ""
    for row_tag in tables[0].find_all("tr"):
        cells = row_tag.find_all(["td", "th"], recursive=False)
        for index, cell in enumerate(cells[:-1]):
            if text(cell) == "特性":
                trait = text(cells[index + 1])
            if text(cell) == "販売価格":
                price = text(cells[index + 1]).removesuffix("G")
    if not trait:
        raise ValueError(f"{name}: 详情缺少特性")
    return modifications, acquisition_entries(content, top_level_only=True), trait, price


def collect_c_units(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行采集 C 装置，全部通过校验后原子写入事实快照。"""
    names = _load_names(repo_root)
    records: list[CUnitFact] = []
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"},
    ) as client:
        index = fetch(client, TARGET_ID, INDEX_URL)
        content = BeautifulSoup(index.body, "html.parser").select_one("#body")
        if content is None:
            raise ValueError("C 装置总表缺少正文")
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
        for row_index, row in enumerate(table.find_all("tr")[1:]):
            cells = row.find_all(["td", "th"], recursive=False)
            name = text(cells[0])
            if name in ("LOVEマシン", "3132", "3133"):
                continue
            if len(cells) != len(_HEADERS) or name not in names.names:
                raise ValueError(f"{name}: 总表字段或参考名称不完整")
            link = cells[0].find("a", href=True)
            if not isinstance(link, Tag):
                raise ValueError(f"{name}: 缺少独立详情链接")
            url = urljoin(INDEX_URL, str(link["href"]))
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "metalmaniax.com":
                raise ValueError(f"{name}: 详情地址不在来源主机内")
            sleep(1.0)
            detail = fetch(client, TARGET_ID, url)
            modifications, acquisition, trait, price = _detail_facts(detail.body, name)
            records.append(
                CUnitFact(
                    name_ja=name,
                    overview=dict(zip(_HEADERS, map(text, cells), strict=True)),
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
                    detail_trait=trait,
                    detail_price=price,
                    modifications=modifications,
                    acquisition_ja=acquisition,
                )
            )
            print(f"C 装置 {len(records):02d}：{names.names[name]}", flush=True)
        sleep(1.0)
        mechanics = fetch(client, TARGET_ID, MECHANICS_URL)
        mechanics_content = BeautifulSoup(mechanics.body, "html.parser").select_one("#body")
        if mechanics_content is None or len(mechanics_content.find_all("table")) < 3:
            raise ValueError("C 装置命中回避验证页缺少测量表")
    snapshot = CUnitSnapshot(
        records=records,
        traits=traits,
        mechanics_ref=SourceRef(
            source_id=SOURCE_ID,
            target_id=TARGET_ID,
            source_url=HttpUrl(MECHANICS_URL),
            retrieved_at=datetime.now().astimezone(),
            content_hash=mechanics.content_hash,
            table_index=2,
            row_index=0,
        ),
        omitted=["LOVE 机器 3131/3132/3133：配方合并行尚未建立独立事实条目"],
    )
    if {record.name_ja for record in records} != set(names.names):
        raise ValueError("C 装置总表与参考名称清单不一致")
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {"records": len(records), "modifications": sum(len(r.modifications) for r in records)}


def load_c_units(repo_root: Path) -> NormalizedBundle | None:
    """离线重建日版参考记录，保留表格矛盾和效果限制。"""
    path = repo_root / _ROOT / "facts.json"
    if not path.exists():
        if (repo_root / _ROOT / "names.yaml").exists():
            raise ValueError("C 装置事实快照缺失，请执行 pnpm data:collect:c-units")
        return None
    snapshot = CUnitSnapshot.model_validate_json(path.read_bytes())
    names = _load_names(repo_root)
    if {fact.name_ja for fact in snapshot.records} != set(names.names):
        raise ValueError("C 装置事实快照与参考名称清单不一致")
    if set(names.acquisition) != set(names.names):
        raise ValueError("C 装置缺少获取摘要")
    traits = {fact.name_ja: fact for fact in snapshot.traits}
    records: list[NormalizedRecord] = []
    for fact in snapshot.records:
        name = fact.name_ja
        trait_key = _trait_key(fact.detail_trait)
        if trait_key not in names.traits:
            raise ValueError(f"{name}: 缺少特性说明 {trait_key}")
        trait = names.traits[trait_key]
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
            mechanics_note_raw=names.mechanics_note,
            acquisition_raw=names.acquisition[name],
        )
        issues = list(fact.issues)
        differences: list[str] = []
        if _trait_key(fact.overview["特性"]) != trait_key:
            differences.append(f"特性：总表 {fact.overview['特性']}，独立详情 {fact.detail_trait}")
        if fact.detail_price:
            if fact.overview["価格(G)"] and comparable_stat(
                fact.overview["価格(G)"]
            ) != comparable_stat(fact.detail_price):
                differences.append(
                    f"价格：总表 {fact.overview['価格(G)']}，独立详情 {fact.detail_price}"
                )
            attributes["price_raw"] = fact.detail_price
        rarity = fact.overview["レア"]
        fixed_stars = len(rarity) if re.fullmatch(r"★{1,3}", rarity) else 0
        primary = next((item for item in fact.modifications if item.stars == fixed_stars), None)
        if primary is None:
            raise ValueError(f"{name}: 缺少 {fixed_stars} 星初始数值")
        for header, key in _ATTRIBUTE_FIELDS.items():
            if key not in ("accuracy_raw", "evasion_raw", "defense_raw", "weight_raw"):
                continue
            value = str(getattr(primary, key))
            if (
                fixed_stars == 0
                and value
                and comparable_stat(value) != comparable_stat(fact.overview[header])
            ):
                differences.append(f"{header}：总表 {fact.overview[header]}，独立详情 {value}")
            if value not in ("", "-", "t", "?", "?t"):
                attributes[key] = value.removesuffix("t") if key == "weight_raw" else value
            else:
                attributes.pop(key, None)
        attributes["stat_condition_raw"] = f"{fixed_stars} 星初始面板值；普通改造上限不含超改造"
        available = obtainable_stars(rarity, fact.acquisition_ja, name)
        if any("入手不可" in location for location in fact.acquisition_ja):
            attributes["availability_raw"] = "租赁车专用，无法获得"
        elif available:
            attributes["obtainable_stars_raw"] = ",".join(map(str, available))
        if fact.acquisition_ja:
            attributes["acquisition_ja_raw"] = "；".join(fact.acquisition_ja)
        if name in names.notes:
            attributes["notes_raw"] = names.notes[name]
        refs = [fact.overview_ref, fact.detail_ref, snapshot.mechanics_ref]
        if trait_key != "なし":
            if trait_key not in traits:
                raise ValueError(f"{name}: 特性说明缺少来源表格")
            trait_fact = traits[trait_key]
            attributes["trait_effect_ja_raw"] = trait_fact.effect_ja
            attributes["trait_limits_ja_raw"] = trait_fact.limits_ja
            refs.append(trait_fact.source_ref)
        if differences:
            attributes["source_difference_raw"] = "；".join(differences)
            issues.append("source_value_difference")
        records.append(
            NormalizedRecord(
                id=stable_record_id("equipment", "c_unit", name),
                domain="equipment",
                kind="c_unit",
                names=NameSet(
                    ja=name, zh_reference=names.names[name], aliases=names.aliases.get(name, [])
                ),
                attributes=attributes,
                control_modifications=fact.modifications,
                version_scope=["mm2r-jp"],
                verification_status=VerificationStatus.SOURCE_ONLY,
                source_refs=refs,
                issues=issues,
            )
        )
    return NormalizedBundle(
        domain="equipment",
        records=sorted(records, key=lambda record: record.id),
        source_hashes=[source.content_hash for record in records for source in record.source_refs],
    )
