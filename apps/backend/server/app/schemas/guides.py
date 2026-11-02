from typing import Literal
from urllib.parse import urldefrag, urlsplit

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from app.schemas.base import CamelModel
from app.schemas.equipment import EquipmentSource

GuidePhaseId = Literal[
    "opening", "ship-and-key", "dark-canal", "southern-gate", "bias-facility", "finale"
]
GuideKind = Literal["main", "preparation", "optional"]
BattleRequirement = Literal["mandatory", "optional", "scripted_loss"]


class GuidePhase(CamelModel):
    id: GuidePhaseId
    order: int = Field(ge=1, le=6)
    title_zh: str = Field(min_length=1)


class GuideFact(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    text_zh: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    section: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    raw_values: dict[str, str]
    locator: str = Field(min_length=1)
    source_ref: EquipmentSource
    verification_status: Literal["source_only"]


class GuideBattle(GuideFact):
    requirement: BattleRequirement


class GuideDiagram(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title_zh: str = Field(min_length=1)
    alt_zh: str = Field(min_length=1)
    chapter_ids: list[str] = Field(min_length=1)
    repo_relative_path: str = Field(
        pattern=r"^data/raw/mm2r/0\.99/guides/diagrams/[a-z0-9-]+-[0-9a-f]{12}\.svg$"
    )
    public_path: str = Field(pattern=r"^/wiki/mm2r/0\.99/guides/[a-z0-9-]+-[0-9a-f]{12}\.svg$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rights_status: Literal["original_diagram"]
    license: Literal["LicenseRef-Project-Original"]
    author: Literal["Metal Max Wiki 项目原创"]
    caption_zh: Literal["原创流程示意 · 非实机地图 · 0.99未验证"]
    source_refs: list[EquipmentSource] = Field(min_length=1)


class GuideSource(CamelModel):
    key: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    scope: Literal["mm2r-facts", "rights-review"]
    encoding: Literal["auto", "gb18030"]
    declared_license: Literal["NOASSERTION", "CC-BY-NC-SA-4.0"]
    attribution: str = Field(min_length=1)
    rights_scope_zh: str = Field(min_length=1)
    retrieved_at: AwareDatetime
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    license_evidence_text: str | None
    license_url: HttpUrl | None
    source_ref: EquipmentSource

    @model_validator(mode="after")
    def validate_source(self) -> GuideSource:
        parsed = urlsplit(str(self.url))
        if self.scope == "mm2r-facts" and (
            parsed.scheme != "https"
            or parsed.hostname != "metalmaniax.com"
            or parsed.path != "/index.php"
            or not parsed.query.startswith("MM2R/")
        ):
            raise ValueError("攻略事实只允许引用MM2R来源")
        if (
            self.source_ref.source_id != self.source_id
            or self.source_ref.content_hash != self.content_hash
            or self.source_ref.retrieved_at != self.retrieved_at
            or self.source_ref.source_url != self.url
        ):
            raise ValueError("攻略来源元数据和页面出处不一致")
        return self


class GuideImageReference(CamelModel):
    id: str = Field(min_length=1)
    title_zh: str = Field(min_length=1)
    source_page_url: HttpUrl
    source_image_url: HttpUrl
    rights_status: Literal["reference_only", "rejected_wrong_version"]
    image_license: Literal["NOASSERTION"]
    page_declared_license: str = Field(min_length=1)
    local_path: None
    reason_zh: str = Field(min_length=1)
    evidence: list[str]
    source_ref: EquipmentSource


class GuideSummary(CamelModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    order: int = Field(ge=1, le=23)
    phase_id: GuidePhaseId
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    kind: GuideKind
    summary: str = Field(min_length=1)
    step_count: int = Field(ge=3)
    verification_status: Literal["source_only"]


class GuideRecord(CamelModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    order: int = Field(ge=1, le=23)
    phase_id: GuidePhaseId
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    kind: GuideKind
    summary: str = Field(min_length=1)
    prerequisites: list[GuideFact] = Field(min_length=1)
    steps: list[GuideFact] = Field(min_length=3)
    key_items: list[GuideFact]
    battles: list[GuideBattle]
    battle_note: str = Field(min_length=1)
    cautions: list[GuideFact] = Field(min_length=1)
    next_steps: list[GuideFact] = Field(min_length=1)
    next_chapter_slugs: list[str]
    source_refs: list[EquipmentSource] = Field(min_length=1)
    verification_status: Literal["source_only"]


class GuideDataset(CamelModel):
    schema_version: Literal[1]
    game: Literal["mm2r"]
    target_version: Literal["0.99"]
    version_scope: Literal["mm2r-jp-reference"]
    verification_status: Literal["source_only"]
    title: str = Field(min_length=1)
    reference_note: str = Field(min_length=1)
    route_note: str = Field(min_length=1)
    source_locator_note: str = Field(min_length=1)
    names_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    phases: list[GuidePhase] = Field(min_length=6, max_length=6)
    records: list[GuideRecord] = Field(min_length=23, max_length=23)
    diagrams: list[GuideDiagram] = Field(min_length=3, max_length=3)
    image_references: list[GuideImageReference] = Field(min_length=2)
    sources: list[GuideSource] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_records(self) -> GuideDataset:
        slugs = {record.slug for record in self.records}
        if len(slugs) != len(self.records):
            raise ValueError("攻略条目包含重复路径")
        if [record.order for record in self.records] != list(range(1, 24)):
            raise ValueError("攻略条目顺序不连续")
        if [phase.order for phase in self.phases] != list(range(1, 7)):
            raise ValueError("攻略阶段顺序不连续")
        sources = {source.key: source for source in self.sources}
        phase_ids = {phase.id for phase in self.phases}
        facts: set[str] = set()
        for record in self.records:
            if record.phase_id not in phase_ids or set(record.next_chapter_slugs) - slugs:
                raise ValueError(f"{record.slug}: 阶段或下一章引用不存在")
            refs: set[str] = set()
            for fact in (
                *record.prerequisites,
                *record.steps,
                *record.key_items,
                *record.battles,
                *record.cautions,
                *record.next_steps,
            ):
                if fact.id in facts:
                    raise ValueError("攻略事实包含重复身份")
                facts.add(fact.id)
                source = sources.get(fact.source_key)
                ref = fact.source_ref
                if source is None or source.scope != "mm2r-facts":
                    raise ValueError("攻略事实误用非MM2R资料")
                if (
                    ref.content_hash != source.content_hash
                    or ref.source_id != source.source_id
                    or ref.target_id != source.source_ref.target_id
                    or ref.retrieved_at != source.retrieved_at
                    or urldefrag(str(ref.source_url))[0] != str(source.url)
                    or not urldefrag(str(ref.source_url))[1]
                ):
                    raise ValueError("攻略事实来源页面、时间或哈希不一致")
                refs.add(ref.model_dump_json())
            if refs != {ref.model_dump_json() for ref in record.source_refs}:
                raise ValueError("攻略章节出处与逐条事实不一致")
        if any(set(diagram.chapter_ids) - slugs for diagram in self.diagrams):
            raise ValueError("攻略流程图引用未知章节")
        return self


class GuideListData(CamelModel):
    title: str
    reference_note: str
    route_note: str
    phases: list[GuidePhase]
    total: int = Field(ge=0)
    chapter_count: int = Field(ge=1)
    diagrams: list[GuideDiagram]
    image_references: list[GuideImageReference]
    limitations: list[str]
    list: list[GuideSummary]


class GuideDetail(GuideRecord):
    reference_note: str
    route_note: str
    phase: GuidePhase
    phases: list[GuidePhase]
    chapters: list[GuideSummary]
    next_chapters: list[GuideSummary]
    diagrams: list[GuideDiagram]
    sources: list[GuideSource]
    limitations: list[str]
