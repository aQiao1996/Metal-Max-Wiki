"""战车部件特性及底盘效果的可追溯事实。"""

import argparse
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote, urldefrag, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import Field, HttpUrl, model_validator

from mmwiki_data.fetcher import fetch
from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import SourceRef
from mmwiki_data.storage import model_content_hash, write_json_atomic
from mmwiki_data.vehicle_tables import text
from mmwiki_data.vehicles import VehicleSnapshot

SOURCE_ID = "metalmaniax-mm2r"
TARGET_ID = "maniax-vehicle-traits"
_ROOT = Path("data/raw/mm2r/0.99/vehicle-traits")
_VEHICLES = Path("data/raw/mm2r/0.99/vehicles/facts.json")
_PLACEHOLDER = "選択 *1"
NonEmpty = Annotated[str, Field(min_length=1)]
Applicability = Literal["底盘特性", "C装置对照", "双部件改造"]
EvidenceKind = Literal["共用特性表", "底盘说明", "原始验证记录", "C装置说明", "改造说明"]


class TraitDescription(StrictModel):
    """项目整理的特性说明，区分指令与被动效果。"""

    name: str = Field(min_length=1)
    activation: Literal["主动指令", "被动生效", "无特性", "效果待确认"]
    effect: str = Field(min_length=1)
    limits: str = Field(min_length=1)


class TraitFact(StrictModel):
    name_ja: str
    effect_ja: str
    limits_ja: str
    source_ref: SourceRef


class VehicleTraitParameter(StrictModel):
    """数值必须携带对象、条件和证据，不能作为无条件增益。"""

    label: NonEmpty
    value: NonEmpty
    conditions: NonEmpty
    applicability: Applicability
    evidence_ids: list[NonEmpty] = Field(min_length=1)


class VehicleTraitEvidenceSpec(StrictModel):
    source_url: HttpUrl
    section_ja: NonEmpty
    table_headers: list[NonEmpty] = Field(default_factory=list)
    row_label_ja: NonEmpty | None = None
    required_fragments_ja: list[NonEmpty] = Field(min_length=1)
    summary_zh: NonEmpty
    applicability: Applicability
    kind: EvidenceKind

    @model_validator(mode="after")
    def validate_locator(self) -> VehicleTraitEvidenceSpec:
        """表格定位和行名必须成对提供。"""
        _validate_url(str(self.source_url))
        if bool(self.table_headers) != (self.row_label_ja is not None):
            raise ValueError("特性证据的表头与行名必须同时提供")
        return self


class VehicleTraitEvidence(StrictModel):
    summary_zh: NonEmpty
    applicability: Applicability
    kind: EvidenceKind
    locator: NonEmpty
    source_ref: SourceRef


class VehicleTraitDescription(StrictModel):
    description: TraitDescription
    aliases: list[NonEmpty] = Field(default_factory=list)
    parameters: list[VehicleTraitParameter] = Field(default_factory=list)
    unknown_parameters: list[NonEmpty]
    evidence_ids: list[NonEmpty] = Field(min_length=1)


class VehicleMountRuleDescription(StrictModel):
    id: Literal["double_engine", "double_c_unit"]
    name: NonEmpty
    effect: NonEmpty
    limits: NonEmpty
    parameters: list[VehicleTraitParameter] = Field(min_length=1)
    unknown_parameters: list[NonEmpty]
    evidence_ids: list[NonEmpty] = Field(min_length=1)


class VehicleTraitNames(StrictModel):
    schema_version: Literal[1]
    reference_note: NonEmpty
    traits: dict[str, VehicleTraitDescription]
    mount_rules: list[VehicleMountRuleDescription] = Field(min_length=2, max_length=2)
    evidence: dict[str, VehicleTraitEvidenceSpec]
    limitations: list[NonEmpty] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> VehicleTraitNames:
        """所有说明和参数必须引用存在且适用对象一致的证据。"""
        if len(self.traits) != 20 or _PLACEHOLDER in self.traits:
            raise ValueError("底盘说明必须覆盖20项真实特性，不能包含设计占位")
        _validate_claims([*self.traits.values(), *self.mount_rules], self.evidence)
        return self


class VehicleTraitInventory(StrictModel):
    vehicle_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    configuration_count: Literal[355] = 355
    configuration_values: dict[str, int]
    design_choices_ja: list[NonEmpty] = Field(min_length=18, max_length=18)
    design_placeholder: Literal["選択 *1"] = "選択 *1"
    design_source_refs: list[SourceRef] = Field(min_length=4, max_length=4)


class VehicleTraitRecord(VehicleTraitDescription):
    name_ja: NonEmpty
    configuration_count: Annotated[int, Field(ge=0)]
    design_selectable: bool
    verification_status: Literal["source_only"] = "source_only"


class VehicleMountRule(VehicleMountRuleDescription):
    verification_status: Literal["source_only"] = "source_only"


class VehicleTraitSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    source_id: Literal["metalmaniax-mm2r"] = "metalmaniax-mm2r"
    verification_status: Literal["source_only"] = "source_only"
    reference_note: NonEmpty
    source_locator_note: str = (
        "table_index为#body内从0开始的表号，row_index为去除表头后的原始行号；"
        "正文证据以source_url锚点及locator定位，正文的表格坐标0不代表表格证据。"
    )
    inventory: VehicleTraitInventory
    records: list[VehicleTraitRecord] = Field(min_length=20, max_length=20)
    mount_rules: list[VehicleMountRule] = Field(min_length=2, max_length=2)
    evidence: dict[str, VehicleTraitEvidence]
    limitations: list[NonEmpty] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_records(self) -> VehicleTraitSnapshot:
        """快照必须完整覆盖车辆依赖并隔离C装置对照数值。"""
        inventory = self.inventory
        counts = inventory.configuration_values
        if len(counts) != 18 or sum(counts.values()) != 355 or counts.get(_PLACEHOLDER) != 4:
            raise ValueError("车辆特性盘点与355配置、18个原始值不符")
        if any(count <= 0 for count in counts.values()):
            raise ValueError("车辆特性配置计数必须为正数")
        choices = set(inventory.design_choices_ja)
        if len(choices) != 18:
            raise ValueError("设计特性选项重复")
        expected = (set(counts) - {_PLACEHOLDER}) | choices
        actual = {record.name_ja for record in self.records}
        if len(actual) != len(self.records) or actual != expected:
            raise ValueError("底盘特性快照有重复或遗漏")
        for record in self.records:
            if record.configuration_count != counts.get(record.name_ja, 0):
                raise ValueError(f"{record.name_ja}: 配置计数不符")
            if record.design_selectable != (record.name_ja in choices):
                raise ValueError(f"{record.name_ja}: 设计候选标记不符")
        _validate_claims([*self.records, *self.mount_rules], self.evidence)
        for evidence in self.evidence.values():
            ref = evidence.source_ref
            _validate_url(str(ref.source_url))
            if ref.source_id != SOURCE_ID or ref.target_id != TARGET_ID:
                raise ValueError("底盘特性证据的来源或目标标识不正确")
        for ref in inventory.design_source_refs:
            _validate_url(str(ref.source_url))
            if ref.source_id != SOURCE_ID or ref.target_id != "maniax-vehicles":
                raise ValueError("设计候选必须引用既有车辆快照的来源")
        return self


def _validate_claims(
    claims: list[VehicleTraitDescription | VehicleMountRuleDescription],
    evidence: dict[str, VehicleTraitEvidenceSpec] | dict[str, VehicleTraitEvidence],
) -> None:
    used: set[str] = set()
    for claim in claims:
        if len(set(claim.evidence_ids)) != len(claim.evidence_ids):
            raise ValueError("特性说明引用了重复证据")
        used.update(claim.evidence_ids)
        for parameter in claim.parameters:
            if set(parameter.evidence_ids) - set(claim.evidence_ids):
                raise ValueError("数值参数引用了所属说明未引用的证据")
            for key in parameter.evidence_ids:
                if key not in evidence or evidence[key].applicability != parameter.applicability:
                    raise ValueError(f"数值参数适用对象与证据不一致：{key}")
    if used != set(evidence):
        raise ValueError(f"底盘特性证据引用不完整：{sorted(used ^ set(evidence))}")
    mount_ids = [claim.id for claim in claims if isinstance(claim, VehicleMountRuleDescription)]
    if sorted(mount_ids) != ["double_c_unit", "double_engine"]:
        raise ValueError("双引擎与双C装置规则必须各有一条")


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "metalmaniax.com"
        or parsed.path != "/index.php"
        or not unquote(parsed.query).startswith("MM2R/")
    ):
        raise ValueError(f"底盘特性证据不在METAL MAniaX同作范围：{url}")


def _load_names(repo_root: Path) -> VehicleTraitNames:
    path = repo_root / _ROOT / "names.yaml"
    return VehicleTraitNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _inventory(repo_root: Path) -> VehicleTraitInventory:
    vehicles = VehicleSnapshot.model_validate_json((repo_root / _VEHICLES).read_bytes())
    counts = Counter(item.trait_raw for row in vehicles.records for item in row.configurations)
    designs = [row.design_traits for row in vehicles.records if row.design_traits is not None]
    if len(designs) != 4 or any(row.choices_ja != designs[0].choices_ja for row in designs):
        raise ValueError("4种巴特战车的设计特性候选不一致")
    return VehicleTraitInventory(
        vehicle_content_hash=model_content_hash(vehicles),
        configuration_values=dict(sorted(counts.items())),
        design_choices_ja=designs[0].choices_ja,
        design_source_refs=[row.source_ref for row in designs],
    )


def _section(content: Tag, label: str) -> tuple[Tag, list[Tag]]:
    headings = [
        tag
        for tag in content.find_all(re.compile(r"^h[2-6]$"))
        if text(tag).removesuffix("†").strip() == label
    ]
    if len(headings) != 1:
        raise ValueError(f"底盘特性来源不能唯一定位章节：{label}")
    heading = headings[0]
    elements: list[Tag] = []
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if re.fullmatch(r"h[2-6]", sibling.name) and int(sibling.name[1]) <= int(heading.name[1]):
            break
        elements.append(sibling)
    return heading, elements


def _evidence(
    key: str,
    spec: VehicleTraitEvidenceSpec,
    body: bytes,
    content_hash: str,
    retrieved_at: datetime,
) -> VehicleTraitEvidence:
    soup = BeautifulSoup(body, "html.parser")
    content = soup.select_one("#body")
    if content is None or soup.select_one('form[action*="cmd=edit"]') is not None:
        raise ValueError(f"{key}: 来源缺少可读取正文或返回编辑页面")
    heading, elements = _section(content, spec.section_ja)
    anchor = heading.find("a", class_="anchor_super")
    if not isinstance(anchor, Tag) or not anchor.get("id"):
        raise ValueError(f"{key}: 来源章节缺少稳定锚点")
    table_index = row_index = 0
    source_text = " ".join(text(element) for element in elements)
    locator = f"#body {heading.name}:{spec.section_ja}"
    if spec.table_headers:
        matches: list[tuple[int, Tag]] = []
        for index, table in enumerate(content.find_all("table")):
            first_row = table.find("tr")
            if not isinstance(first_row, Tag):
                continue
            headers = [text(cell) for cell in first_row.find_all(["td", "th"])]
            if headers == spec.table_headers and any(
                table is element or table in element.descendants for element in elements
            ):
                matches.append((index, table))
        if len(matches) != 1:
            raise ValueError(f"{key}: 无法唯一定位特性证据表格")
        table_index, table = matches[0]
        rows = [
            (index, row)
            for index, row in enumerate(table.find_all("tr")[1:])
            if isinstance(cell := row.find(["td", "th"]), Tag) and text(cell) == spec.row_label_ja
        ]
        if len(rows) != 1:
            raise ValueError(f"{key}: 无法唯一定位证据行：{spec.row_label_ja}")
        row_index, row = rows[0]
        source_text = text(row)
        locator += f" table[{table_index}] row[{row_index}]={spec.row_label_ja}"
    if any(fragment not in source_text for fragment in spec.required_fragments_ja):
        raise ValueError(f"{key}: 原始证据片段发生变化，保留已有完整快照")
    return VehicleTraitEvidence(
        summary_zh=spec.summary_zh,
        applicability=spec.applicability,
        kind=spec.kind,
        locator=locator,
        source_ref=SourceRef(
            source_id=SOURCE_ID,
            target_id=TARGET_ID,
            source_url=HttpUrl(urldefrag(str(spec.source_url))[0] + "#" + str(anchor["id"])),
            retrieved_at=retrieved_at,
            content_hash=content_hash,
            table_index=table_index,
            row_index=row_index,
        ),
    )


def load_vehicle_traits(repo_root: Path) -> VehicleTraitSnapshot:
    """读取完整特性快照，拒绝与当前车辆配置不一致的依赖。"""
    snapshot = VehicleTraitSnapshot.model_validate_json(
        (repo_root / _ROOT / "facts.json").read_bytes()
    )
    if snapshot.inventory != _inventory(repo_root):
        raise ValueError("底盘特性盘点已过期，请重新采集车辆特性")
    return snapshot


def collect_vehicle_traits(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行核验同作证据，所有事实通过校验后原子写入快照。"""
    names = _load_names(repo_root)
    inventory = _inventory(repo_root)
    expected = (set(inventory.configuration_values) - {_PLACEHOLDER}) | set(
        inventory.design_choices_ja
    )
    if set(names.traits) != expected:
        raise ValueError("中文特性说明未完整覆盖配置与巴特设计候选")
    evidence: dict[str, VehicleTraitEvidence] = {}
    cache: dict[str, tuple[bytes, str, datetime]] = {}
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"},
    ) as client:
        for key, spec in names.evidence.items():
            url = urldefrag(str(spec.source_url))[0]
            if url not in cache:
                if cache:
                    sleep(1.0)
                result = fetch(client, TARGET_ID, url)
                cache[url] = result.body, result.content_hash, datetime.now().astimezone()
            body, content_hash, retrieved_at = cache[url]
            evidence[key] = _evidence(key, spec, body, content_hash, retrieved_at)
    records = [
        VehicleTraitRecord(
            **description.model_dump(),
            name_ja=name,
            configuration_count=inventory.configuration_values.get(name, 0),
            design_selectable=name in inventory.design_choices_ja,
        )
        for name, description in names.traits.items()
    ]
    snapshot = VehicleTraitSnapshot(
        reference_note=names.reference_note,
        inventory=inventory,
        records=records,
        mount_rules=[VehicleMountRule(**rule.model_dump()) for rule in names.mount_rules],
        evidence=evidence,
        limitations=names.limitations,
    )
    if inventory != _inventory(repo_root):
        raise ValueError("采集期间车辆配置发生变化，保留已有完整特性快照")
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "traits": len(records),
        "parameters": sum(len(record.parameters) for record in records),
        "mount_rules": len(snapshot.mount_rules),
        "evidence": len(evidence),
        "source_pages": len(cache),
        "configurations": inventory.configuration_count,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """提供独立采集或本地依赖检查命令。"""
    parser = argparse.ArgumentParser(description="采集MM2R底盘特性及数值证据")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="仅校验本地完整快照")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    if args.check:
        snapshot = load_vehicle_traits(root)
        result = {"traits": len(snapshot.records), "mount_rules": len(snapshot.mount_rules)}
    else:
        result = collect_vehicle_traits(root)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
