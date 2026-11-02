"""采集职业、完整技能表与主副职业规则的中文参考事实。"""

import argparse
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote, urldefrag, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import ConfigDict, Field, HttpUrl, model_validator

from mmwiki_data.fetcher import FetchResult, fetch
from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import NormalizedBundle, NormalizedRecord, SourceRef
from mmwiki_data.storage import write_json_atomic
from mmwiki_data.vehicle_tables import expanded_rows, text

_ROOT = Path("data/raw/mm2r/0.99/job-skills")
_JOBS = {
    "ハンター": "hunter",
    "メカニック": "mechanic",
    "ソルジャー": "soldier",
    "ナース": "nurse",
    "レスラー": "wrestler",
    "アーチスト": "artist",
    "犬": "dog",
}
_PAGES = {
    **{name: f"MM2R/DATA/キャラクターデータ/{name}" for name in _JOBS},
    "growth": "MM2R/DATA/キャラクターデータ/ステータス成長率",
    "protagonist": "MM2R/DATA/キャラクターデータ/主人公",
    "faq": "MM2R/FAQ",
    "unlock": "MM2R/攻略/攻略ガイド/酒場サースティ",
}
_SOURCE_ALIASES = {
    "男気キック": "男気パンチ",
    "男気パンチ2": "男気パンチ",
    "男気パンチ3": "男気パンチ",
    "男気パンチ4": "男気パンチ",
    "男気キック2": "男気パンチ",
    **{f"パンチラキック{number}": "パンチラキック" for number in range(2, 7)},
}
_GROWTH_HEADERS = ("HP", "戦闘Lv", "運転Lv", "腕力", "体力", "素早")
_CONTEXT_SECTION = (
    "スキルアイコンのクルマとかバイクとか人間とか…使える状況がわかり辛い！ああわかり辛い！"
)
NonEmpty = Annotated[str, Field(min_length=1)]
RecordId = Annotated[str, Field(pattern=r"^[a-z-]+-[0-9a-f]{10}$")]


class JobSkillStrictModel(StrictModel):
    """拒绝未知字段与来源标量的隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class FactDraft(JobSkillStrictModel):
    code: NonEmpty
    source_page: NonEmpty
    section_ja: NonEmpty
    summary_zh: NonEmpty
    evidence_ja: list[NonEmpty] = Field(min_length=1)
    raw_values: dict[str, str] = Field(default_factory=dict)


class JobSkillNames(JobSkillStrictModel):
    schema_version: Literal[1]
    verification_status: Literal["source_only"]
    reference_note: NonEmpty
    job_names: dict[NonEmpty, NonEmpty]
    skill_names: dict[NonEmpty, NonEmpty] = Field(min_length=65)
    job_summaries: dict[NonEmpty, FactDraft]
    skill_summaries: dict[NonEmpty, NonEmpty]
    skill_targets: dict[NonEmpty, NonEmpty]
    mechanics: dict[NonEmpty, list[FactDraft]]
    rules: list[FactDraft] = Field(min_length=1)
    limitations: list[NonEmpty] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_editorial_coverage(self) -> JobSkillNames:
        """中文编辑覆盖全部职业与技能，规则只引用本轮允许的页面。"""
        if set(self.job_names) != set(_JOBS) or set(self.job_summaries) != set(_JOBS):
            raise ValueError("职业中文名称和用途必须完整覆盖7个职业")
        skills = set(self.skill_names)
        if skills != set(self.skill_summaries) or skills != set(self.skill_targets):
            raise ValueError("技能中文名称、用途和目标的覆盖不一致")
        if set(self.mechanics) - skills:
            raise ValueError("技能机制引用了没有中文参考名的技能")
        drafts = [
            *self.job_summaries.values(),
            *self.rules,
            *(fact for facts in self.mechanics.values() for fact in facts),
        ]
        if any(draft.source_page not in _PAGES for draft in drafts):
            raise ValueError("中文事实引用了未允许的来源页面")
        codes = [draft.code for draft in self.rules]
        if len(codes) != len(set(codes)):
            raise ValueError("主副职业或成长规则代码重复")
        return self


class ReferencedFact(JobSkillStrictModel):
    code: NonEmpty
    summary_zh: NonEmpty
    evidence_ja: list[NonEmpty] = Field(min_length=1)
    raw_values: dict[str, str]
    locator: NonEmpty
    location_kind: Literal["section", "table"]
    source_ref: SourceRef
    verification_status: Literal["source_only"] = "source_only"


class GrowthSample(JobSkillStrictModel):
    level_raw: str = Field(pattern=r"^Lv(?:99|199|499|999)$")
    values_raw: dict[str, str]
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_source_values(self) -> GrowthSample:
        """成长观测只接受来源表原列，不推算每级增量。"""
        if set(self.values_raw) != set(_GROWTH_HEADERS):
            raise ValueError("成长观测的属性列不完整")
        if any(not value.isdecimal() for value in self.values_raw.values()):
            raise ValueError("成长观测包含非整数原值")
        return self


class JobFact(JobSkillStrictModel):
    id: RecordId
    name_ja: NonEmpty
    name_zh_reference: NonEmpty
    number_raw: str = Field(pattern=r"^[1-7]$")
    summary_zh: NonEmpty
    role: ReferencedFact
    growth_samples: list[GrowthSample] = Field(min_length=4, max_length=4)
    source_refs: list[SourceRef] = Field(min_length=1)
    verification_status: Literal["source_only"] = "source_only"


class SkillSourceValue(JobSkillStrictModel):
    name_ja: NonEmpty
    job_ja: NonEmpty
    number_raw: str | None
    category_raw: NonEmpty
    learning_level_raw: NonEmpty
    learning_condition_raw: str | None
    target_raw: str | None
    uses_at_lv99_raw: str | None
    source_ref: SourceRef


class ConflictValue(JobSkillStrictModel):
    value_raw: NonEmpty
    source_ref: SourceRef


class SkillConflict(JobSkillStrictModel):
    field: Literal["name_ja", "learning_level", "category", "target"]
    summary_zh: NonEmpty
    values: list[ConflictValue] = Field(min_length=2)


class SkillFact(JobSkillStrictModel):
    id: RecordId
    name_ja: NonEmpty
    canonical_name_ja: NonEmpty
    name_zh_reference: NonEmpty
    job_id: RecordId
    job_ja: NonEmpty
    summary_zh: NonEmpty
    target_zh: NonEmpty
    learning_level: int = Field(ge=1, le=99)
    learning_level_raw: str = Field(pattern=r"^[0-9]+$")
    learning_condition_zh: str | None
    uses_at_lv99_raw: str = Field(pattern=r"^(?:[0-9]+|-)$")
    source_values: list[SkillSourceValue] = Field(min_length=1)
    usage_restrictions: list[ReferencedFact]
    mechanics: list[ReferencedFact]
    conflicts: list[SkillConflict]
    source_refs: list[SourceRef] = Field(min_length=1)
    verification_status: Literal["source_only"] = "source_only"

    @model_validator(mode="after")
    def validate_learning_level(self) -> SkillFact:
        """展示学习级别必须与保留的来源原值相符。"""
        if self.learning_level != int(self.learning_level_raw):
            raise ValueError("技能学习级别与来源原值不一致")
        return self


class SourceCoverage(JobSkillStrictModel):
    job_ja: NonEmpty
    source_skill_rows: int = Field(ge=1)
    matched_interim_rows: int = Field(ge=0)
    missing_from_interim: list[NonEmpty]
    source_ref: SourceRef


class JobSkillSnapshot(JobSkillStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    version_scope: Literal["mm2r-jp"] = "mm2r-jp"
    verification_status: Literal["source_only"] = "source_only"
    reference_note: NonEmpty
    source_locator_note: str = (
        "METAL MAniaX的table_index为#body内从0起算的表号，row_index为展开后从0起算的tr行号，"
        "包含表头及空行；DQFF引用沿用现有interim坐标。正文事实以锚点和locator定位，"
        "其SourceRef的0/0不表示正文位于表格。Lv99次数只适用于来源表标出的等级口径。"
    )
    jobs: list[JobFact] = Field(min_length=7, max_length=7)
    skills: list[SkillFact] = Field(min_length=65)
    rules: list[ReferencedFact] = Field(min_length=1)
    coverage: list[SourceCoverage] = Field(min_length=7, max_length=7)
    limitations: list[NonEmpty] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_snapshot(self) -> JobSkillSnapshot:
        """拒绝职业、现有技能或完整来源表的遗漏和身份重叠。"""
        by_job = {job.name_ja: job for job in self.jobs}
        if set(by_job) != set(_JOBS) or len({job.id for job in self.jobs}) != 7:
            raise ValueError("职业快照名单不完整或ID重复")
        if len({skill.id for skill in self.skills}) != len(self.skills):
            raise ValueError("职业技能快照ID重复")
        identities = {(skill.job_ja, skill.canonical_name_ja) for skill in self.skills}
        if len(identities) != len(self.skills):
            raise ValueError("同一职业的规范技能名称重复")
        coverage = {item.job_ja: item for item in self.coverage}
        if set(coverage) != set(_JOBS):
            raise ValueError("完整技能表覆盖统计缺少职业")
        for name, job in by_job.items():
            if {sample.level_raw for sample in job.growth_samples} != {
                "Lv99",
                "Lv199",
                "Lv499",
                "Lv999",
            }:
                raise ValueError(f"{name}: 成长观测等级不完整")
            job_skills = [skill for skill in self.skills if skill.job_ja == name]
            expected = coverage[name]
            if len(job_skills) != expected.source_skill_rows:
                raise ValueError(f"{name}: 技能数与完整来源表不符")
            if expected.matched_interim_rows + len(expected.missing_from_interim) != len(
                job_skills
            ):
                raise ValueError(f"{name}: 技能覆盖统计不一致")
            if any(skill.job_id != job.id for skill in job_skills):
                raise ValueError(f"{name}: 技能职业ID错配")
        return self


@dataclass(frozen=True, slots=True)
class _Page:
    key: str
    url: str
    result: FetchResult
    retrieved_at: datetime
    content: Tag


@dataclass(frozen=True, slots=True)
class _SourceSkill:
    values: SkillSourceValue
    description_ja: str


def _heading_text(heading: Tag) -> str:
    return text(heading).removesuffix("†").strip()


def _section(page: _Page, label: str) -> tuple[Tag, list[Tag]]:
    matches = [
        heading
        for heading in page.content.find_all(re.compile(r"^h[2-6]$"))
        if _heading_text(heading) == label
    ]
    if len(matches) != 1:
        raise ValueError(f"{page.key}: 不能唯一定位章节 {label!r}")
    heading = matches[0]
    level = int(heading.name[1])
    nodes: list[Tag] = []
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if re.fullmatch(r"h[2-6]", sibling.name) and int(sibling.name[1]) <= level:
            break
        nodes.append(sibling)
    return heading, nodes


def _section_url(page: _Page, heading: Tag) -> str:
    anchor = heading.find("a", class_="anchor_super")
    anchor_id = anchor.get("id") if isinstance(anchor, Tag) else heading.get("id")
    if not isinstance(anchor_id, str) or not anchor_id:
        raise ValueError(f"{page.key}: 来源章节没有稳定锚点")
    return urldefrag(page.url)[0] + "#" + anchor_id


def _ref(page: _Page, url: str, table_index: int = 0, row_index: int = 0) -> SourceRef:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "metalmaniax.com":
        raise ValueError(f"职业技能来源地址不在允许主机：{url}")
    if parsed.path != "/index.php" or not parsed.query.startswith("MM2R/"):
        raise ValueError(f"职业技能来源地址不在MM2R范围：{url}")
    slug = _JOBS.get(page.key, page.key)
    return SourceRef(
        source_id="metalmaniax-mm2r",
        target_id=f"maniax-job-skills-{slug}",
        source_url=HttpUrl(url),
        retrieved_at=page.retrieved_at,
        content_hash=page.result.content_hash,
        table_index=table_index,
        row_index=row_index,
    )


def _fetch_pages(sleep: Callable[[float], None]) -> dict[str, _Page]:
    pages: dict[str, _Page] = {}
    with httpx.Client(
        timeout=40,
        follow_redirects=True,
        headers={"User-Agent": "MetalMaxWikiData/0.1 (source-only factual reference)"},
    ) as client:
        for key, path in _PAGES.items():
            if pages:
                sleep(1.0)
            url = "https://metalmaniax.com/index.php?" + quote(path, safe="/")
            result = fetch(client, f"job-skills-{_JOBS.get(key, key)}", url)
            content = BeautifulSoup(result.body, "html.parser").select_one("#body")
            if content is None or content.find("textarea") is not None:
                raise ValueError(f"{key}: 来源页面不存在或缺少#body正文")
            pages[key] = _Page(key, url, result, datetime.now().astimezone(), content)
    return pages


def _fact(
    draft: FactDraft, pages: dict[str, _Page], skill: _SourceSkill | None = None
) -> ReferencedFact:
    page = pages[draft.source_page]
    heading, nodes = _section(page, draft.section_ja)
    url = _section_url(page, heading)
    source_text = " ".join(text(node) for node in nodes)
    source_ref = _ref(page, url)
    location_kind: Literal["section", "table"] = "section"
    locator = draft.section_ja
    if (
        skill is not None
        and draft.section_ja == "習得特技"
        and draft.source_page == skill.values.job_ja
    ):
        source_text = skill.description_ja
        source_ref = skill.values.source_ref
        location_kind = "table"
        locator += " / " + skill.values.name_ja
    for evidence in draft.evidence_ja:
        if evidence not in source_text:
            raise ValueError(f"{draft.code}: 来源证据已变化，未找到 {evidence!r} ({url})")
    return ReferencedFact(
        code=draft.code,
        summary_zh=draft.summary_zh,
        evidence_ja=draft.evidence_ja,
        raw_values=draft.raw_values,
        locator=locator,
        location_kind=location_kind,
        source_ref=source_ref,
    )


def _source_skills(page: _Page) -> list[_SourceSkill]:
    heading, nodes = _section(page, "習得特技")
    tables = [
        table
        for node in nodes
        for table in ([node] if node.name == "table" else node.find_all("table"))
    ]
    if len(tables) != 1:
        raise ValueError(f"{page.key}: 習得特技必须有且只有一张表")
    table = tables[0]
    table_index = page.content.find_all("table").index(table)
    rows = expanded_rows(table)
    if rows[:2] != [
        ["種別", "スキル", "習得LV", "使用回数", "説明"],
        ["種別", "スキル", "習得LV", "LV99", "説明"],
    ]:
        raise ValueError(f"{page.key}: 职业技能表头发生变化")
    result: list[_SourceSkill] = []
    for row_index, row in enumerate(rows[2:], start=2):
        if len(row) != 5:
            raise ValueError(f"{page.key}: 技能表行宽异常，行 {row_index}")
        category, name, level, uses, description = row
        if not level.isdecimal() or not re.fullmatch(r"[0-9]+|-", uses):
            raise ValueError(f"{page.key}/{name}: 学习级别或Lv99次数格式异常")
        condition = None
        if name in ("男気パンチ", "パンチラキック"):
            condition = "男・麗人" if name == "男気パンチ" else "女・オカマ"
            if condition not in description:
                raise ValueError(f"{page.key}/{name}: 性别学习条件变化")
        result.append(
            _SourceSkill(
                SkillSourceValue(
                    name_ja=name,
                    job_ja=page.key,
                    number_raw=None,
                    category_raw=category,
                    learning_level_raw=level,
                    learning_condition_raw=condition,
                    target_raw=None,
                    uses_at_lv99_raw=uses,
                    source_ref=_ref(page, _section_url(page, heading), table_index, row_index),
                ),
                description,
            )
        )
    expected = 5 if page.key == "犬" else 10
    if len(result) != expected or len({item.values.name_ja for item in result}) != expected:
        raise ValueError(f"{page.key}: 来源技能名单变化，须复核完整表与中文编辑")
    return result


def _growth_samples(page: _Page) -> dict[str, list[GrowthSample]]:
    heading, _nodes = _section(page, "Lv99～のステータス")
    tables = page.content.find_all("table")
    if len(tables) != 1:
        raise ValueError("职业成长来源应有一张多等级数据表")
    result: dict[str, list[GrowthSample]] = {job: [] for job in _JOBS}
    level: str | None = None
    for row_index, row in enumerate(expanded_rows(tables[0])):
        if len(row) != 7:
            raise ValueError(f"成长表列数变化，行 {row_index}")
        if re.fullmatch(r"Lv[0-9]+", row[0]):
            if tuple(row[1:]) != _GROWTH_HEADERS:
                raise ValueError("职业成长表头变化")
            level = row[0]
        elif row[0] in _JOBS:
            if level is None:
                raise ValueError("职业成长表数据位于等级表头之前")
            result[row[0]].append(
                GrowthSample(
                    level_raw=level,
                    values_raw=dict(zip(_GROWTH_HEADERS, row[1:], strict=True)),
                    source_ref=_ref(page, _section_url(page, heading), 0, row_index),
                )
            )
        elif row[0] not in ("", "金食い虫"):
            raise ValueError(f"职业成长表出现未知职业：{row[0]}")
    return result


def _load_bundle(repo_root: Path, domain: Literal["jobs", "skills"]) -> NormalizedBundle:
    path = repo_root / f"data/interim/mm2r/0.99/{domain}.json"
    bundle = NormalizedBundle.model_validate_json(path.read_text(encoding="utf-8"))
    if bundle.domain != domain:
        raise ValueError(f"{path}: 中间数据领域错配")
    return bundle


def _string_attribute(record: NormalizedRecord, field: str) -> str:
    value = record.attributes.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{record.id}: 既有资料缺少字符串字段 {field}")
    return value


def _legacy_value(record: NormalizedRecord) -> SkillSourceValue:
    name = record.names.ja
    if name is None or len(record.source_refs) != 1:
        raise ValueError(f"{record.id}: 既有技能名称或来源数量异常")
    level = _string_attribute(record, "level_raw")
    condition = level.partition(" ")[2] or None
    target = record.attributes.get("target_raw")
    if target is not None and not isinstance(target, str):
        raise ValueError(f"{record.id}: 既有技能目标不是字符串")
    return SkillSourceValue(
        name_ja=name,
        job_ja=_string_attribute(record, "job_raw"),
        number_raw=_string_attribute(record, "number_raw"),
        category_raw=_string_attribute(record, "skill_category"),
        learning_level_raw=level,
        learning_condition_raw=condition,
        target_raw=target,
        uses_at_lv99_raw=None,
        source_ref=record.source_refs[0],
    )


def _conflicts(old: SkillSourceValue, new: SkillSourceValue) -> list[SkillConflict]:
    result: list[SkillConflict] = []
    old_level = re.match(r"^[0-9]+", old.learning_level_raw)
    if old_level is None:
        raise ValueError(f"{old.name_ja}: 既有学习级别缺少数字")
    comparisons: list[tuple[Literal["name_ja", "learning_level", "category"], str, str]] = [
        ("name_ja", old.name_ja, new.name_ja),
        ("learning_level", old_level[0], new.learning_level_raw),
        ("category", old.category_raw, new.category_raw),
    ]
    labels = {"name_ja": "技能名称", "learning_level": "学习等级", "category": "技能分类"}
    for field, before, after in comparisons:
        if before != after:
            result.append(
                SkillConflict(
                    field=field,
                    summary_zh=(
                        f"DQFF与METAL MAniaX的{labels[field]}记载不同，"
                        "两份原值并存；未由0.99实机裁定。"
                    ),
                    values=[
                        ConflictValue(value_raw=before, source_ref=old.source_ref),
                        ConflictValue(value_raw=after, source_ref=new.source_ref),
                    ],
                )
            )
    return result


def _usage(source: _SourceSkill, pages: dict[str, _Page]) -> list[ReferencedFact]:
    category = source.values.category_raw
    labels = {
        "クルマ": ("乘车技能仅在战车或摩托乘车时可用，降车时不可用。", "乗車時のみ利用可能"),
        "バイク": ("摩托技能在摩托乘车或降车时可用，战车乘车时不可用。", "バイク乗車時と降車時"),
        "人間": ("白兵技能仅在降车时可用。", "降車時のみ利用可能"),
    }
    if category in labels:
        summary, evidence = labels[category]
        return [
            _fact(
                FactDraft(
                    code="context-"
                    + {"クルマ": "vehicle", "バイク": "motorcycle", "人間": "on-foot"}[category],
                    source_page="faq",
                    section_ja=_CONTEXT_SECTION,
                    summary_zh=summary,
                    evidence_ja=[evidence],
                    raw_values={"category_raw": category},
                ),
                pages,
            )
        ]
    if category == "犬":
        return [
            _fact(
                FactDraft(
                    code="context-dog-ai",
                    source_page="犬",
                    section_ja="概要",
                    summary_zh="犬由AI控制，技能不能由玩家逐条手动下令。",
                    evidence_ja=["自分で操作出来ず、行動はAI任せ"],
                ),
                pages,
            )
        ]
    return []


def load_job_skill_names(repo_root: Path) -> JobSkillNames:
    """校验中文参考名与人工摘要，不将其视为0.99汉化实机名称。"""
    path = repo_root / _ROOT / "names.yaml"
    return JobSkillNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_job_skills(repo_root: Path) -> JobSkillSnapshot | None:
    """离线读取并严格校验职业技能事实快照。"""
    path = repo_root / _ROOT / "facts.json"
    if not path.exists():
        return None
    return JobSkillSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def collect_job_skills(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行采集完整职业技能表，全部校验成功后原子替换事实快照。"""
    names = load_job_skill_names(repo_root)
    legacy_jobs = _load_bundle(repo_root, "jobs")
    legacy_skills = _load_bundle(repo_root, "skills")
    old_jobs = {record.names.ja: record for record in legacy_jobs.records}
    old_skills = {record.names.ja: record for record in legacy_skills.records}
    if set(old_jobs) != set(_JOBS) or None in old_skills:
        raise ValueError("既有职业或技能没有完整日文身份")
    if set(names.skill_names) != set(old_skills):
        raise ValueError("中文参考编辑没有完整覆盖全部既有技能")
    legacy_by_key = {
        (_string_attribute(record, "job_raw"), _SOURCE_ALIASES.get(name, name)): record
        for name, record in old_skills.items()
        if name is not None
    }
    if len(legacy_by_key) != len(legacy_skills.records):
        raise ValueError("既有技能规范化后出现职业与名称重叠")
    pages = _fetch_pages(sleep)
    growth = _growth_samples(pages["growth"])
    jobs: list[JobFact] = []
    skills: list[SkillFact] = []
    coverage: list[SourceCoverage] = []
    matched: set[str] = set()
    for job_ja in _JOBS:
        old_job = old_jobs[job_ja]
        role = _fact(names.job_summaries[job_ja], pages)
        jobs.append(
            JobFact(
                id=old_job.id,
                name_ja=job_ja,
                name_zh_reference=names.job_names[job_ja],
                number_raw=_string_attribute(old_job, "number_raw"),
                summary_zh=role.summary_zh,
                role=role,
                growth_samples=growth[job_ja],
                source_refs=[
                    *old_job.source_refs,
                    role.source_ref,
                    *(sample.source_ref for sample in growth[job_ja]),
                ],
            )
        )
        page = pages[job_ja]
        source_skills = _source_skills(page)
        missing = [
            item.values.name_ja
            for item in source_skills
            if (job_ja, item.values.name_ja) not in legacy_by_key
        ]
        if missing:
            raise ValueError(f"{job_ja}: 完整来源表存在未编辑技能 {missing}，旧快照未覆盖")
        for source in source_skills:
            new = source.values
            record = legacy_by_key[(job_ja, new.name_ja)]
            old = _legacy_value(record)
            mechanics = [
                _fact(draft, pages, source) for draft in names.mechanics.get(old.name_ja, [])
            ]
            usage = _usage(source, pages)
            condition = None
            if new.learning_condition_raw:
                condition = (
                    "男性或丽人（来源性别分类）"
                    if new.name_ja == "男気パンチ"
                    else "女性或女装男性（来源オカマ分类）"
                )
            conflicts = _conflicts(old, new)
            for fact in mechanics:
                corrected_target = fact.raw_values.get("target_raw")
                if corrected_target and old.target_raw and corrected_target != old.target_raw:
                    conflicts.append(
                        SkillConflict(
                            field="target",
                            summary_zh="来源对攻击范围的记载不同；中文参考采用有明确范围的记载，未由0.99实机裁定。",
                            values=[
                                ConflictValue(value_raw=old.target_raw, source_ref=old.source_ref),
                                ConflictValue(
                                    value_raw=corrected_target, source_ref=fact.source_ref
                                ),
                            ],
                        )
                    )
            if new.uses_at_lv99_raw is None:
                raise ValueError(f"{job_ja}/{new.name_ja}: 来源缺少Lv99次数原值")
            skills.append(
                SkillFact(
                    id=record.id,
                    name_ja=old.name_ja,
                    canonical_name_ja=new.name_ja,
                    name_zh_reference=names.skill_names[old.name_ja],
                    job_id=old_job.id,
                    job_ja=job_ja,
                    summary_zh=names.skill_summaries[old.name_ja],
                    target_zh=names.skill_targets[old.name_ja],
                    learning_level=int(new.learning_level_raw),
                    learning_level_raw=new.learning_level_raw,
                    learning_condition_zh=condition,
                    uses_at_lv99_raw=new.uses_at_lv99_raw,
                    source_values=[old, new],
                    usage_restrictions=usage,
                    mechanics=mechanics,
                    conflicts=conflicts,
                    source_refs=[
                        old.source_ref,
                        new.source_ref,
                        *(item.source_ref for item in [*usage, *mechanics]),
                    ],
                )
            )
            matched.add(record.id)
        heading, _nodes = _section(page, "習得特技")
        coverage.append(
            SourceCoverage(
                job_ja=job_ja,
                source_skill_rows=len(source_skills),
                matched_interim_rows=len(source_skills),
                missing_from_interim=[],
                source_ref=_ref(page, _section_url(page, heading)),
            )
        )
    if matched != {record.id for record in legacy_skills.records}:
        raise ValueError("完整来源表未覆盖全部既有技能，旧快照未覆盖")
    rules = [_fact(draft, pages) for draft in names.rules]
    snapshot = JobSkillSnapshot(
        reference_note=names.reference_note,
        jobs=jobs,
        skills=skills,
        rules=rules,
        coverage=coverage,
        limitations=names.limitations,
    )
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "jobs": len(jobs),
        "skills": len(skills),
        "source_pages": len(pages),
        "growth_samples": sum(len(job.growth_samples) for job in jobs),
        "rules": len(rules),
        "mechanics": sum(len(skill.mechanics) for skill in skills),
        "conflicts": sum(len(skill.conflicts) for skill in skills),
        "missing_skills": sum(len(item.missing_from_interim) for item in coverage),
    }


def main() -> None:
    """独立运行职业技能事实采集或离线快照校验。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.validate_only:
        load_job_skill_names(repo_root)
        snapshot = load_job_skills(repo_root)
        if snapshot is None:
            raise ValueError("职业技能事实快照不存在")
        result = {
            "jobs": len(snapshot.jobs),
            "skills": len(snapshot.skills),
            "rules": len(snapshot.rules),
        }
    else:
        result = collect_job_skills(repo_root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
