"""采集 S-E 的表格事实，保留原始数值和逐页出处。"""

import re
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
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

SOURCE_ID = "metalmaniax-mm2r"
TARGET_ID = "maniax-special-equipment"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E6%88%A6%E8%BB%8A"
_ROOT = Path("data/raw/mm2r/0.99/special-equipment")
_HEADERS = ("名称", "攻撃", "範囲", "属性", "守備", "重量(t)", "弾倉", "弾薬(G)", "価格(G)", "レア")
_STAT_GROUPS = {"攻撃力": "attack", "守備力": "defense", "弾倉": "magazine", "重量": "weight"}
_ATTRIBUTE_FIELDS = {
    "攻撃": "attack_raw",
    "範囲": "range_raw",
    "属性": "element_raw",
    "守備": "defense_raw",
    "重量(t)": "weight_raw",
    "弾倉": "magazine_raw",
    "弾薬(G)": "ammunition_price_raw",
    "価格(G)": "price_raw",
    "レア": "rarity_raw",
}


class SpecialEquipmentNames(StrictModel):
    """项目整理的参考译名，不冒充特定汉化版本名称。"""

    schema_version: Literal[1]
    names: dict[str, str]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    effects: dict[str, str] = Field(default_factory=dict)
    acquisition: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_names(self) -> SpecialEquipmentNames:
        """别名与说明必须对应已声明的参考名称。"""
        for values in (self.aliases, self.effects, self.acquisition):
            unknown = set(values) - set(self.names)
            if unknown:
                raise ValueError(f"S-E 说明对应未知名称：{sorted(unknown)}")
        return self


class SpecialEquipmentFact(StrictModel):
    """一个 S-E 的总表事实与独立详情事实。"""

    name_ja: str
    overview: dict[str, str]
    overview_ref: SourceRef
    detail_ref: SourceRef
    modifications: list[EquipmentModification]
    acquisition_ja: list[str]
    issues: list[str] = Field(default_factory=list)


class SpecialEquipmentSnapshot(StrictModel):
    """不含整页正文和图片的 S-E 来源快照。"""

    schema_version: Literal[1] = 1
    source_id: Literal["metalmaniax-mm2r"] = "metalmaniax-mm2r"
    records: list[SpecialEquipmentFact] = Field(min_length=1)
    omitted: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_records(self) -> SpecialEquipmentSnapshot:
        """拒绝重复名称、错源引用和重复星级。"""
        names = [record.name_ja for record in self.records]
        if len(names) != len(set(names)):
            raise ValueError("S-E 快照包含重复名称")
        for record in self.records:
            if set(record.overview) != set(_HEADERS):
                raise ValueError(f"{record.name_ja}: 来源总表字段不完整")
            for source in (record.overview_ref, record.detail_ref):
                if source.source_id != SOURCE_ID or source.target_id != TARGET_ID:
                    raise ValueError(f"{record.name_ja}: S-E 来源标识不一致")
                if source.source_url.host != "metalmaniax.com":
                    raise ValueError(f"{record.name_ja}: S-E 来源主机不正确")
            stars = [item.stars for item in record.modifications]
            if len(stars) != len(set(stars)):
                raise ValueError(f"{record.name_ja}: 重复的星级记录")
        return self


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _expanded_rows(table: Tag) -> list[list[str]]:
    """展开行列合并单元格，避免把星级数值错配到其他字段。"""
    cells: dict[tuple[int, int], str] = {}
    output: list[list[str]] = []
    for row_index, row in enumerate(table.find_all("tr")):
        column = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (row_index, column) in cells:
                column += 1
            colspan = int(str(cell.get("colspan", "1")))
            rowspan = int(str(cell.get("rowspan", "1")))
            if not 1 <= colspan <= 20 or not 1 <= rowspan <= 20:
                raise ValueError("S-E 表格包含不支持的跨行或跨列范围")
            for row_offset in range(rowspan):
                for column_offset in range(colspan):
                    key = (row_index + row_offset, column + column_offset)
                    if key in cells:
                        raise ValueError("S-E 表格的合并单元格发生重叠")
                    cells[key] = _text(cell)
            column += colspan
        width = max((key[1] + 1 for key in cells if key[0] == row_index), default=0)
        output.append([cells.get((row_index, index), "") for index in range(width)])
    return output


def _detail_facts(
    body: bytes, name: str
) -> tuple[list[EquipmentModification], list[str], list[str]]:
    soup = BeautifulSoup(body, "html.parser")
    content = soup.select_one("#body")
    if content is None:
        raise ValueError(f"{name}: 缺少详情正文")
    has_heading = any("基本情報" in _text(section) for section in content.find_all(["h2", "h3"]))
    tables = content.find_all("table")
    if not tables:
        return [], [], ["source_detail_unavailable"]
    table = tables[0]
    rows = _expanded_rows(table)
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
    acquisition: list[str] = []
    for section in content.find_all(["h2", "h3"]):
        if not any(label in _text(section) for label in ("販売箇所", "その他入手法")):
            continue
        label = "店铺" if "販売箇所" in _text(section) else "其他获取"
        for sibling in section.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            if sibling.name in ("h2", "h3"):
                break
            if sibling.name not in ("ul", "ol", "p"):
                continue
            value = _text(sibling)
            if value and value not in ("なし", "無し", "↑"):
                acquisition.append(f"{label}：{value}")
    issues = [] if modifications else ["source_modification_unavailable"]
    if not has_heading and not modifications:
        issues.append("source_detail_unavailable")
    return modifications, acquisition, issues


def _load_names(repo_root: Path) -> SpecialEquipmentNames:
    path = repo_root / _ROOT / "names.yaml"
    return SpecialEquipmentNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _comparable_stat(value: str) -> Decimal | str:
    text = value.removesuffix("t")
    return Decimal(text) if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text) else text


def collect_special_equipment(
    repo_root: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """串行获取 S-E 事实，全部成功后才写入新的快照。"""
    names = _load_names(repo_root)
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)",
        },
    ) as client:
        index = fetch(client, TARGET_ID, INDEX_URL)
        soup = BeautifulSoup(index.body, "html.parser")
        content = soup.select_one("#body")
        if content is None:
            raise ValueError("S-E 总表缺少正文")
        candidates = [
            table
            for table in content.find_all("table")
            if tuple(_text(cell) for cell in table.find_all("tr")[0].find_all(["td", "th"]))
            == _HEADERS
        ]
        if len(candidates) != 1:
            raise ValueError("S-E 总表无法唯一定位")
        table = candidates[0]
        table_index = content.find_all("table").index(table)
        retrieved_at = datetime.now().astimezone()
        records: list[SpecialEquipmentFact] = []
        omitted: list[str] = []
        for row_index, row in enumerate(table.find_all("tr")[1:]):
            cells = row.find_all(["td", "th"], recursive=False)
            name = _text(cells[0])
            if name == "LOVEマシン":
                omitted.append("LOVEマシン：总表存在配方合并列，独立详情未提供有效数值表")
                continue
            if len(cells) != len(_HEADERS):
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
            detail = fetch(client, TARGET_ID, url)
            modifications, acquisition, issues = _detail_facts(detail.body, name)
            records.append(
                SpecialEquipmentFact(
                    name_ja=name,
                    overview=dict(zip(_HEADERS, map(_text, cells), strict=True)),
                    overview_ref=SourceRef(
                        source_id=SOURCE_ID,
                        target_id=TARGET_ID,
                        source_url=HttpUrl(INDEX_URL),
                        retrieved_at=retrieved_at,
                        content_hash=index.content_hash,
                        table_index=table_index,
                        row_index=row_index,
                    ),
                    detail_ref=SourceRef(
                        source_id=SOURCE_ID,
                        target_id=TARGET_ID,
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
            print(f"S-E {len(records):02d}：{names.names[name]}", flush=True)
    actual = {record.name_ja for record in records}
    if actual != set(names.names):
        raise ValueError(f"S-E 名称清单与总表不一致：{sorted(set(names.names) ^ actual)}")
    snapshot = SpecialEquipmentSnapshot(records=records, omitted=omitted)
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {"records": len(records), "modifications": sum(len(r.modifications) for r in records)}


def load_special_equipment(repo_root: Path) -> NormalizedBundle | None:
    """从事实快照重建候选 S-E；旧资料集合可独立标准化。"""
    path = repo_root / _ROOT / "facts.json"
    if not path.exists():
        if (repo_root / _ROOT / "names.yaml").exists():
            raise ValueError("S-E 来源快照缺失，请执行 pnpm data:collect:se")
        return None
    snapshot = SpecialEquipmentSnapshot.model_validate_json(path.read_bytes())
    names = _load_names(repo_root)
    if {fact.name_ja for fact in snapshot.records} != set(names.names):
        raise ValueError("S-E 事实快照与中文名称清单不一致")
    records: list[NormalizedRecord] = []
    for fact in snapshot.records:
        name = fact.name_ja
        issues = list(fact.issues)
        attributes: dict[str, str | int | float | bool | None] = {
            field: fact.overview[header]
            for header, field in _ATTRIBUTE_FIELDS.items()
            if fact.overview[header]
        }
        rarity = fact.overview["レア"]
        fixed_stars = len(rarity) if re.fullmatch(r"★{1,3}", rarity) else 0
        available_stars: set[int] = set()
        if re.fullmatch(r"★{1,3}", rarity):
            available_stars.add(fixed_stars)
        elif re.fullmatch(r"☆{1,3}", rarity):
            available_stars.update(range(len(rarity) + 1))
        elif rarity == "-":
            available_stars.add(0)
        for acquisition in fact.acquisition_ja:
            for match in re.finditer(r"★([0-3])(?:\s*[～〜~-]\s*★?([0-3]))?", acquisition):
                start = int(match[1])
                end = int(match[2]) if match[2] is not None else start
                if end < start:
                    raise ValueError(f"{name}: 来源星级范围倒置")
                available_stars.update(range(start, end + 1))
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
                    if detail_value and _comparable_stat(overview_value) != _comparable_stat(
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
        records.append(
            NormalizedRecord(
                id=stable_record_id("equipment", "special_equipment", name),
                domain="equipment",
                kind="special_equipment",
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
