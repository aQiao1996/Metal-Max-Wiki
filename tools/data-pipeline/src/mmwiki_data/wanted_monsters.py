"""采集日版赏金首事实、逐槽掉落与出现条件的可追溯参考快照。"""

import argparse
import re
import time
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import ConfigDict, Field, HttpUrl, model_validator

from mmwiki_data.fetcher import FetchResult, fetch
from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import SourceRef
from mmwiki_data.storage import write_json_atomic
from mmwiki_data.vehicle_tables import expanded_rows, text

SOURCE_ID = "metalmaniax-mm2r"
TARGET_ID = "maniax-wanted-monsters"
FROG_SOURCE_ID = "kaerulabo-mm2r"
FROG_TARGET_ID = "kaerulabo-wanted-monster-drops"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E8%B3%9E%E9%87%91%E9%A6%96"
DROPS_URL = "http://kaerulabo.web.fc2.com/etc/mm2r/item_monsterDrop.html"
_ROOT = Path("data/raw/mm2r/0.99/wanted-monsters")
_SLOTS: tuple[Literal[1, 2, 3], ...] = (1, 2, 3)
_HEADERS = (
    "モンスター名",
    "賞金",
    "有名度",
    "落とすアイテム1",
    "落とすアイテム2",
    "落とすアイテム3",
    "生息地",
    "備考",
)


class WantedStrictModel(StrictModel):
    """拒绝未知字段和隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class AppearanceSummary(WantedStrictModel):
    section_ja: str = Field(min_length=1)
    summary_ja: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)


class ConflictSummary(WantedStrictModel):
    code: str = Field(pattern=r"^[a-z_]+$")
    section_ja: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)


class WantedNames(WantedStrictModel):
    schema_version: Literal[1]
    reference_note: str = Field(min_length=1)
    probability_note: str = Field(min_length=1)
    names: dict[str, str]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    source_aliases: dict[str, str]
    source_alias_notes: dict[str, str]
    enemy_forms: dict[str, list[str]]
    appearance: dict[str, list[AppearanceSummary]]
    conflicts: dict[str, list[ConflictSummary]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_coverage(self) -> WantedNames:
        """每个悬赏必须有名称、敌人形态和经过核对的出现事实。"""
        keys = set(self.names)
        if len(keys) != 30 or set(self.enemy_forms) != keys or set(self.appearance) != keys:
            raise ValueError("赏金首参考名称、敌人形态和出现摘要必须完整覆盖30个悬赏")
        if set(self.aliases) - keys or set(self.conflicts) - keys:
            raise ValueError("赏金首别名或冲突说明引用了未知悬赏")
        forms = [form for values in self.enemy_forms.values() for form in values]
        if len(forms) != 31 or len(set(forms)) != 31:
            raise ValueError("赏金首必须包含31个不重复敌人形态")
        if any(not values for values in self.appearance.values()):
            raise ValueError("赏金首出现事实摘要不能为空")
        if set(self.source_aliases) != set(self.source_alias_notes):
            raise ValueError("每个来源别名或错字映射都必须有说明")
        return self


class WantedOverviewRow(WantedStrictModel):
    fields: dict[str, str]
    source_ref: SourceRef


class WantedOverview(WantedStrictModel):
    name_ja: str = Field(min_length=1)
    bounty_raw: str = Field(pattern=r"^[0-9,]+$")
    fame_raw: str = Field(pattern=r"^[0-9]+$")
    location_ja_raw: str = Field(min_length=1)
    notes_ja_raw: list[str]
    detail_url: HttpUrl
    source_ref: SourceRef
    rows: list[WantedOverviewRow] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validate_rows(self) -> WantedOverview:
        """展开合并行后仍保留每行原字段和定位。"""
        for row in self.rows:
            if set(row.fields) != set(_HEADERS) or row.fields["モンスター名"] != self.name_ja:
                raise ValueError(f"{self.name_ja}: 赏金首总表字段或名称不一致")
            if (
                row.fields["賞金"] != self.bounty_raw
                or row.fields["有名度"] != self.fame_raw
                or row.fields["生息地"] != self.location_ja_raw
            ):
                raise ValueError(f"{self.name_ja}: 悬赏合并行的公共字段不一致")
        return self


class WantedDrop(WantedStrictModel):
    slot: Literal[1, 2, 3]
    item_ja: str = Field(min_length=1)
    canonical_item_ja: str = Field(min_length=1)
    rate_raw: str = Field(pattern=r"^(?:100|[1-9]?[0-9])%$")


class WantedEnemyForm(WantedStrictModel):
    frog_enemy_id: str = Field(pattern=r"^[0-9]{3}$")
    encyclopedia_number: str = Field(pattern=r"^[0-9]{3}$")
    kana_order_raw: str = Field(pattern=r"^[0-9]{3}$")
    name_ja: str = Field(min_length=1)
    canonical_name_ja: str = Field(min_length=1)
    drops: list[WantedDrop] = Field(min_length=3, max_length=3)
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_slots(self) -> WantedEnemyForm:
        """相同物品也必须保留来源中的三个槽位。"""
        if [drop.slot for drop in self.drops] != [1, 2, 3]:
            raise ValueError(f"{self.name_ja}: 掉落槽位缺失、重复或乱序")
        return self


class WantedAppearanceFact(WantedStrictModel):
    section_ja: str = Field(min_length=1)
    section_anchor: str = Field(min_length=1)
    summary_ja: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)
    source_ref: SourceRef


class WantedConflict(WantedStrictModel):
    code: str = Field(pattern=r"^[a-z_]+$")
    summary_zh: str = Field(min_length=1)
    source_refs: list[SourceRef] = Field(min_length=2)


class WantedMonsterFact(WantedStrictModel):
    overview: WantedOverview
    enemy_forms: list[WantedEnemyForm] = Field(min_length=1, max_length=2)
    appearance_facts: list[WantedAppearanceFact] = Field(min_length=1)
    conflicts: list[WantedConflict] = Field(default_factory=list)


class WantedMonsterSnapshot(WantedStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    version_scope: Literal["mm2r-jp"] = "mm2r-jp"
    verification_status: Literal["source_only"] = "source_only"
    reference_note: str = Field(min_length=1)
    probability_note: str = Field(min_length=1)
    records: list[WantedMonsterFact] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_complete_snapshot(self) -> WantedMonsterSnapshot:
        """拒绝不完整悬赏、重复敌人和来源错配。"""
        names = [record.overview.name_ja for record in self.records]
        forms = [form for record in self.records for form in record.enemy_forms]
        if len(set(names)) != 30 or len(forms) != 31:
            raise ValueError("赏金首快照必须包含30次悬赏、31名敌人")
        if len({form.frog_enemy_id for form in forms}) != 31:
            raise ValueError("赏金首快照包含重复敌人ID")
        for record in self.records:
            overview = record.overview
            refs = [overview.source_ref, *(row.source_ref for row in overview.rows)]
            refs.extend(fact.source_ref for fact in record.appearance_facts)
            for ref in refs:
                _validate_ref(ref, SOURCE_ID, TARGET_ID, "metalmaniax.com", "https")
            for form in record.enemy_forms:
                _validate_ref(
                    form.source_ref, FROG_SOURCE_ID, FROG_TARGET_ID, "kaerulabo.web.fc2.com", "http"
                )
            if len(overview.rows) != len(record.enemy_forms):
                raise ValueError(f"{overview.name_ja}: 总表行数与敌人形态数不一致")
            if overview.name_ja == "ピチピチブラザーズ":
                if {form.canonical_name_ja for form in record.enemy_forms} != {
                    "オトピチ",
                    "ステピチ",
                }:
                    raise ValueError("皮奇兄弟必须保留两名敌人的独立掉落")
            elif len(record.enemy_forms) != 1:
                raise ValueError(f"{overview.name_ja}: 悬赏被错误拆分")
        return self


def _validate_ref(ref: SourceRef, source: str, target: str, host: str, scheme: str) -> None:
    if (
        ref.source_id != source
        or ref.target_id != target
        or ref.source_url.host != host
        or ref.source_url.scheme != scheme
    ):
        raise ValueError(f"赏金首来源标识或地址不正确：{ref.source_url}")


def _load_names(repo_root: Path) -> WantedNames:
    path = repo_root / _ROOT / "names.yaml"
    return WantedNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _canonical_name(value: str, names: WantedNames) -> str:
    """显式纠正已知来源错字，再统一全角英数和横线。"""
    value = names.source_aliases.get(value, value)
    return unicodedata.normalize("NFKC", value).replace("‐", "-").replace("‑", "-")


def _make_ref(
    result: FetchResult,
    url: str,
    *,
    source_id: str = SOURCE_ID,
    target_id: str = TARGET_ID,
    table_index: int = 0,
    row_index: int = 0,
) -> SourceRef:
    return SourceRef(
        source_id=source_id,
        target_id=target_id,
        source_url=HttpUrl(url),
        retrieved_at=datetime.now().astimezone(),
        content_hash=result.content_hash,
        table_index=table_index,
        row_index=row_index,
    )


def _parse_overviews(result: FetchResult, names: WantedNames) -> list[WantedOverview]:
    content = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if content is None:
        raise ValueError("赏金首总表缺少正文")
    matches = [
        (index, table)
        for index, table in enumerate(content.find_all("table"))
        if (first := table.find("tr")) is not None
        and tuple(text(cell) for cell in first.find_all(["td", "th"])) == _HEADERS
    ]
    if len(matches) != 1:
        raise ValueError("赏金首总表无法唯一定位预期表头")
    table_index, table = matches[0]
    expanded = expanded_rows(table)
    grouped: dict[str, list[WantedOverviewRow]] = {}
    detail_urls: dict[str, str] = {}
    for row_index, (tag, values) in enumerate(
        zip(table.find_all("tr")[1:], expanded[1:], strict=True)
    ):
        if len(values) != len(_HEADERS) or values[0] not in names.names:
            raise ValueError(f"赏金首总表第{row_index + 1}行字段或名称发生变化：{values}")
        name = values[0]
        cells = tag.find_all(["td", "th"], recursive=False)
        if name not in grouped:
            link = cells[0].find("a", href=True)
            if not isinstance(link, Tag):
                raise ValueError(f"{name}: 缺少赏金首详情链接")
            url = urljoin(INDEX_URL, str(link["href"]))
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname != "metalmaniax.com":
                raise ValueError(f"{name}: 详情地址不在来源主机内")
            detail_urls[name] = url
            grouped[name] = []
        grouped[name].append(
            WantedOverviewRow(
                fields=dict(zip(_HEADERS, values, strict=True)),
                source_ref=_make_ref(
                    result, INDEX_URL, table_index=table_index, row_index=row_index
                ),
            )
        )
    if set(grouped) != set(names.names) or len(expanded) != 32:
        raise ValueError("赏金首总表未完整覆盖30次悬赏、31个物理数据行")
    return [
        WantedOverview(
            name_ja=name,
            bounty_raw=rows[0].fields["賞金"],
            fame_raw=rows[0].fields["有名度"],
            location_ja_raw=rows[0].fields["生息地"],
            notes_ja_raw=list(
                dict.fromkeys(row.fields["備考"] for row in rows if row.fields["備考"])
            ),
            detail_url=HttpUrl(detail_urls[name]),
            source_ref=rows[0].source_ref,
            rows=rows,
        )
        for name, rows in grouped.items()
    ]


def _parse_drops(result: FetchResult, names: WantedNames) -> dict[str, WantedEnemyForm]:
    soup = BeautifulSoup(result.body, "html.parser")
    matches = soup.select("table.data.tblsorter")
    if len(matches) != 1:
        raise ValueError("敌掉落表无法唯一定位 data.tblsorter 表格")
    table = matches[0]
    table_index = next(index for index, tag in enumerate(soup.find_all("table")) if tag is table)
    heading = table.find("tr")
    if heading is None or [text(cell) for cell in heading.find_all("th")] != [
        "ID",
        "図鑑 No.",
        "50 音順",
        "名前",
        "ドロップ1",
        "ドロップ2",
        "ドロップ3",
    ]:
        raise ValueError("敌掉落表的表头发生变化")
    forms: dict[str, WantedEnemyForm] = {}
    for row_index, row in enumerate(table.find_all("tr")[1:]):
        if "WANTED" not in row.get_attribute_list("class"):
            continue
        cells = row.find_all("td", recursive=False)
        if len(cells) != 10:
            raise ValueError(f"敌掉落表第{row_index + 1}行不是十个字段")
        values = [cell.get_text("", strip=True) for cell in cells]
        canonical = _canonical_name(values[3], names)
        if canonical in forms:
            raise ValueError(f"敌掉落表出现重复赏金首形态：{values[3]}")
        forms[canonical] = WantedEnemyForm(
            frog_enemy_id=values[0],
            encyclopedia_number=values[1],
            kana_order_raw=values[2],
            name_ja=values[3],
            canonical_name_ja=canonical,
            drops=[
                WantedDrop(
                    slot=slot,
                    item_ja=values[2 + 2 * slot],
                    canonical_item_ja=_canonical_name(values[2 + 2 * slot], names),
                    rate_raw=values[3 + 2 * slot],
                )
                for slot in _SLOTS
            ],
            source_ref=_make_ref(
                result,
                DROPS_URL,
                source_id=FROG_SOURCE_ID,
                target_id=FROG_TARGET_ID,
                table_index=table_index,
                row_index=row_index,
            ),
        )
    expected = {
        _canonical_name(form, names) for forms in names.enemy_forms.values() for form in forms
    }
    if len(forms) != 31 or set(forms) != expected:
        raise ValueError(
            f"赏金首掉落形态不完整，缺少{expected - set(forms)}，多出{set(forms) - expected}"
        )
    return forms


def _section(body: Tag, name: str, label: str) -> tuple[str, str]:
    headings = [
        heading
        for heading in body.find_all(["h2", "h3", "h4"])
        if text(heading).removesuffix("†").strip() == label
    ]
    if len(headings) != 1:
        raise ValueError(f"{name}: 无法唯一定位事实小节「{label}」")
    heading = headings[0]
    anchor_tag = heading.find("a", id=True)
    anchor = anchor_tag.get("id") if isinstance(anchor_tag, Tag) else heading.get("id")
    if not isinstance(anchor, str) or not anchor:
        raise ValueError(f"{name}: 事实小节「{label}」缺少定位锚点")
    parts: list[str] = []
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if re.fullmatch(r"h[1-6]", sibling.name) and sibling.name <= heading.name:
            break
        parts.append(text(sibling))
    return anchor, re.sub(r"\s+", "", " ".join(parts))


def _appearance_facts(
    result: FetchResult, overview: WantedOverview, names: WantedNames
) -> list[WantedAppearanceFact]:
    body = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if body is None:
        raise ValueError(f"{overview.name_ja}: 赏金首详情缺少正文")
    facts: list[WantedAppearanceFact] = []
    for summary in names.appearance[overview.name_ja]:
        anchor, content = _section(body, overview.name_ja, summary.section_ja)
        missing = [term for term in summary.evidence if re.sub(r"\s+", "", term) not in content]
        if missing:
            raise ValueError(
                f"{overview.name_ja}: 事实小节「{summary.section_ja}」缺少证据{missing}"
            )
        facts.append(
            WantedAppearanceFact(
                section_ja=summary.section_ja,
                section_anchor=anchor,
                summary_ja=summary.summary_ja,
                summary_zh=summary.summary_zh,
                source_ref=_make_ref(result, f"{overview.detail_url}#{anchor}"),
            )
        )
    return facts


def collect_wanted_monsters(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行采集全部赏金首，通过交叉校验后才原子替换完整事实快照。"""
    names = _load_names(repo_root)
    records: list[WantedMonsterFact] = []
    request_count = 0
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"},
    ) as client:

        def request(target_id: str, url: str) -> FetchResult:
            nonlocal request_count
            if request_count:
                sleep(1.0)
            request_count += 1
            return fetch(client, target_id, url)

        overviews = _parse_overviews(request(TARGET_ID, INDEX_URL), names)
        all_forms = _parse_drops(request(FROG_TARGET_ID, DROPS_URL), names)
        for overview in overviews:
            name = overview.name_ja
            forms = [all_forms[_canonical_name(form, names)] for form in names.enemy_forms[name]]
            if len(forms) != len(overview.rows):
                raise ValueError(f"{name}: 形态清单与总表行数不一致")
            for row, form in zip(overview.rows, forms, strict=True):
                if name == "ピチピチブラザーズ" and row.fields["備考"] != form.canonical_name_ja:
                    raise ValueError(f"{name}: 兄弟掉落行错配")
                overview_items = [
                    _canonical_name(row.fields[f"落とすアイテム{slot}"], names)
                    for slot in (1, 2, 3)
                ]
                if overview_items != [drop.canonical_item_ja for drop in form.drops]:
                    raise ValueError(f"{name}: 总表与概率表的三槽物品不一致")
            detail = request(TARGET_ID, str(overview.detail_url))
            facts = _appearance_facts(detail, overview, names)
            conflicts: list[WantedConflict] = []
            for conflict in names.conflicts.get(name, []):
                refs = [fact.source_ref for fact in facts if fact.section_ja == conflict.section_ja]
                if not refs:
                    raise ValueError(f"{name}: 冲突说明引用了未采集小节")
                conflicts.append(
                    WantedConflict(
                        code=conflict.code,
                        summary_zh=conflict.summary_zh,
                        source_refs=[overview.source_ref, *refs],
                    )
                )
            records.append(
                WantedMonsterFact(
                    overview=overview,
                    enemy_forms=forms,
                    appearance_facts=facts,
                    conflicts=conflicts,
                )
            )
            print(f"赏金首 {len(records):02d}：{names.names[name]}", flush=True)
    snapshot = WantedMonsterSnapshot(
        reference_note=names.reference_note,
        probability_note=names.probability_note,
        records=records,
    )
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "bounties": len(records),
        "enemy_forms": sum(len(record.enemy_forms) for record in records),
        "drop_slots": sum(len(form.drops) for record in records for form in record.enemy_forms),
        "appearance_facts": sum(len(record.appearance_facts) for record in records),
        "conflicts": sum(len(record.conflicts) for record in records),
        "requests": request_count,
    }


def main() -> None:
    """支持独立执行赏金首采集，不接入其他类别的标准化流程。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    arguments = parser.parse_args()
    result = collect_wanted_monsters(arguments.repo_root.resolve())
    print(result)


if __name__ == "__main__":
    main()
