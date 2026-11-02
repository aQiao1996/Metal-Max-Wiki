"""将离线主线快照整理为可浏览、可检索且保留原始证据的攻略数据。"""

from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urldefrag

import yaml
from pydantic import Field, model_validator

from mmwiki_data.guides import (
    GuideBattle,
    GuideChapter,
    GuideChapterDraft,
    GuideDiagram,
    GuideFact,
    GuideImageReference,
    GuideNames,
    GuidePhase,
    GuideSnapshot,
    GuideSource,
    GuideSourceDraft,
    GuideStrictModel,
    _svg,
    load_guides,
)
from mmwiki_data.normalization_models import SourceRef, sorted_unique_source_refs
from mmwiki_data.storage import model_content_hash

_ROOT = Path("data/raw/mm2r/0.99/guides")
_PUBLIC_ROOT = "/wiki/mm2r/0.99/guides/"
_GROUPS = ("prerequisites", "steps", "key_items", "battles", "cautions", "next_steps")


class GuideReferenceDiagram(GuideDiagram):
    public_path: str = Field(pattern=r"^/wiki/mm2r/0\.99/guides/[a-z0-9-]+-[0-9a-f]{12}\.svg$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class GuideRecord(GuideStrictModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    order: int = Field(ge=1, le=23)
    phase_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    kind: Literal["main", "preparation", "optional"]
    summary: str = Field(min_length=1)
    prerequisites: list[GuideFact] = Field(min_length=1)
    steps: list[GuideFact] = Field(min_length=3)
    key_items: list[GuideFact]
    battles: list[GuideBattle]
    battle_note: str = Field(min_length=1)
    cautions: list[GuideFact] = Field(min_length=1)
    next_steps: list[GuideFact] = Field(min_length=1)
    next_chapter_slugs: list[str]
    source_refs: list[SourceRef] = Field(min_length=1)
    verification_status: Literal["source_only"] = "source_only"


class GuideDataset(GuideStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    version_scope: Literal["mm2r-jp-reference"] = "mm2r-jp-reference"
    verification_status: Literal["source_only"] = "source_only"
    title: str = Field(min_length=1)
    reference_note: str = Field(min_length=1)
    route_note: str = Field(min_length=1)
    source_locator_note: str = Field(min_length=1)
    names_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    phases: list[GuidePhase] = Field(min_length=6, max_length=6)
    records: list[GuideRecord] = Field(min_length=23, max_length=23)
    diagrams: list[GuideReferenceDiagram] = Field(min_length=3, max_length=3)
    image_references: list[GuideImageReference] = Field(min_length=2)
    sources: list[GuideSource] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_records(self) -> GuideDataset:
        """整套攻略必须保留阶段、下一章与每条事实的出处关系。"""
        slugs = {record.slug for record in self.records}
        if len(slugs) != len(self.records):
            raise ValueError("攻略条目包含重复路径")
        if [record.order for record in self.records] != list(range(1, 24)):
            raise ValueError("攻略条目顺序不连续")
        phase_ids = {phase.id for phase in self.phases}
        for record in self.records:
            if record.phase_id not in phase_ids or set(record.next_chapter_slugs) - slugs:
                raise ValueError(f"{record.slug}: 阶段或下一章引用不存在")
            refs = [fact.source_ref for name in _GROUPS for fact in getattr(record, name)]
            if record.source_refs != sorted_unique_source_refs(refs):
                raise ValueError(f"{record.slug}: 条目与逐条事实的出处不一致")
        return self


class GuideRouteIndex(GuideStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    slugs: list[Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]] = Field(
        min_length=23, max_length=23
    )

    @model_validator(mode="after")
    def validate_slugs(self) -> GuideRouteIndex:
        if len(self.slugs) != len(set(self.slugs)):
            raise ValueError("攻略路径索引包含重复章节")
        return self


def _draft_chapter(chapter: GuideChapter) -> GuideChapterDraft:
    values = chapter.model_dump(exclude={"source_refs", "verification_status"})
    for name in _GROUPS:
        values[name] = [
            fact.model_dump(exclude={"locator", "source_ref", "verification_status"})
            for fact in getattr(chapter, name)
        ]
    return GuideChapterDraft.model_validate(values)


def _validated_sources(repo_root: Path) -> tuple[GuideNames, GuideSnapshot] | None:
    root = repo_root / _ROOT
    names_path, snapshot_path = root / "names.yaml", root / "facts.json"
    if not names_path.exists() and not snapshot_path.exists():
        return None
    if not names_path.is_file() or not snapshot_path.is_file():
        raise ValueError("主线攻略的编辑清单或事实快照缺失，请先采集完整来源")
    names = GuideNames.model_validate(yaml.safe_load(names_path.read_text(encoding="utf-8")))
    snapshot = load_guides(repo_root)
    if snapshot is None:
        raise ValueError("主线攻略事实快照缺失")
    if (
        snapshot.title_zh != names.title_zh
        or snapshot.reference_note != names.reference_note
        or snapshot.route_note != names.route_note
        or snapshot.phases != names.phases
        or snapshot.limitations != names.limitations
        or [_draft_chapter(chapter) for chapter in snapshot.chapters] != names.chapters
    ):
        raise ValueError("攻略事实与当前编辑清单不一致，请重新采集，不可混用旧条件或原始值")
    actual_sources = [
        GuideSourceDraft.model_validate(
            source.model_dump(include=set(GuideSourceDraft.model_fields))
        )
        for source in snapshot.sources
    ]
    if actual_sources != names.sources:
        raise ValueError("攻略来源、许可或归属与当前编辑清单不一致")
    for source in snapshot.sources:
        ref = source.source_ref
        if (
            ref.source_id != source.source_id
            or str(ref.source_url) != str(source.url)
            or ref.target_id != f"guides-{source.key}"
            or ref.retrieved_at != source.retrieved_at
            or ref.content_hash != source.content_hash
        ):
            raise ValueError(f"{source.key}: 来源元数据和页面出处不一致")
    facts = {
        fact.id: fact
        for chapter in snapshot.chapters
        for group in _GROUPS
        for fact in getattr(chapter, group)
    }
    if len(snapshot.diagrams) != len(names.diagrams):
        raise ValueError("攻略原创流程图数量变化")
    for diagram, draft in zip(snapshot.diagrams, names.diagrams, strict=True):
        expected_refs = sorted_unique_source_refs(
            [facts[node.source_fact_id].source_ref for node in draft.nodes]
        )
        data = _svg(draft)
        digest = "sha256:" + sha256(data).hexdigest()
        expected_path = _ROOT / "diagrams" / f"{draft.id}-{digest.removeprefix('sha256:')[:12]}.svg"
        if (
            diagram.id != draft.id
            or diagram.title_zh != draft.title_zh
            or diagram.alt_zh != draft.alt_zh
            or diagram.chapter_ids != draft.chapter_ids
            or diagram.source_refs != expected_refs
            or diagram.content_hash != digest
            or diagram.repo_relative_path != expected_path.as_posix()
        ):
            raise ValueError(f"{draft.id}: 原创流程图与编辑清单、事实出处或内容哈希不一致")
        path = repo_root / diagram.repo_relative_path
        if not path.resolve().is_relative_to(root.resolve()) or path.read_bytes() != data:
            raise ValueError(f"{draft.id}: 原创流程图路径或字节内容不一致")
    if len(snapshot.image_references) != len(names.image_references):
        raise ValueError("攻略外部图片权利核对记录不完整")
    sources = {source.key: source for source in snapshot.sources}
    for image, image_draft in zip(snapshot.image_references, names.image_references, strict=True):
        source = sources[image_draft.source_key]
        if (
            image.id != image_draft.id
            or image.title_zh != image_draft.title_zh
            or image.rights_status != image_draft.rights_status
            or image.image_license != image_draft.image_license
            or image.reason_zh != image_draft.reason_zh
            or image.evidence != image_draft.evidence
            or image.source_page_url != source.url
            or image.source_ref != source.source_ref
            or image_draft.image_url_match not in str(image.source_image_url)
            or image.page_declared_license != source.declared_license
        ):
            raise ValueError(f"{image_draft.id}: 外部图片权利核对与编辑清单不一致")
    for fact in facts.values():
        source = sources[fact.source_key]
        if source.scope != "mm2r-facts" or urldefrag(str(fact.source_ref.source_url))[1] == "":
            raise ValueError(f"{fact.id}: 攻略事实不是带章节锚点的MM2R来源")
    return names, snapshot


def validate_guide_sources(repo_root: Path) -> bool:
    """离线核对编辑清单、MM2R事实快照、逐条出处与三张原创图的依赖哈希。"""
    return _validated_sources(repo_root) is not None


def load_guide_references(repo_root: Path) -> GuideDataset | None:
    """生成完整主线攻略，缺少声明依赖时失败，不联网补齐或提升核验状态。"""
    validated = _validated_sources(repo_root)
    if validated is None:
        return None
    names, snapshot = validated
    records = [
        GuideRecord(
            slug=chapter.id,
            order=chapter.order,
            phase_id=chapter.phase_id,
            title=chapter.title_zh,
            location=chapter.location_zh,
            kind=chapter.kind,
            summary=chapter.summary_zh,
            prerequisites=chapter.prerequisites,
            steps=chapter.steps,
            key_items=chapter.key_items,
            battles=chapter.battles,
            battle_note=chapter.battle_note_zh,
            cautions=chapter.cautions,
            next_steps=chapter.next_steps,
            next_chapter_slugs=chapter.next_chapter_ids,
            source_refs=chapter.source_refs,
        )
        for chapter in snapshot.chapters
    ]
    diagrams = [
        GuideReferenceDiagram(
            **diagram.model_dump(),
            public_path=_PUBLIC_ROOT + Path(diagram.repo_relative_path).name,
            width=840,
            height=212 + len(draft.nodes) * 118,
        )
        for diagram, draft in zip(snapshot.diagrams, names.diagrams, strict=True)
    ]
    return GuideDataset(
        title=snapshot.title_zh,
        reference_note=snapshot.reference_note,
        route_note=snapshot.route_note,
        source_locator_note=snapshot.source_locator_note,
        names_hash=model_content_hash(names),
        snapshot_hash=model_content_hash(snapshot),
        phases=snapshot.phases,
        records=records,
        diagrams=diagrams,
        image_references=snapshot.image_references,
        sources=snapshot.sources,
        limitations=snapshot.limitations,
    )
