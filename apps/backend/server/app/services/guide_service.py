from unicodedata import normalize

from app.core.errors import BusinessError
from app.repositories.guide_repository import load_guides
from app.schemas.guides import (
    GuideDetail,
    GuideListData,
    GuidePhaseId,
    GuideRecord,
    GuideSummary,
)
from app.services.equipment_service import require_available_version


def guide_text(record: GuideRecord) -> str:
    """检索本章条件、步骤、道具和战斗，保留原值且不混入其他版本。"""
    values = [record.title, record.summary, record.location, record.battle_note]
    for fact in (
        *record.prerequisites,
        *record.steps,
        *record.key_items,
        *record.battles,
        *record.cautions,
        *record.next_steps,
    ):
        values.extend([fact.text_zh, *fact.raw_values.values()])
    return normalize("NFKC", " ".join(values)).casefold()


def _summary(record: GuideRecord) -> GuideSummary:
    return GuideSummary(
        slug=record.slug,
        order=record.order,
        phase_id=record.phase_id,
        title=record.title,
        location=record.location,
        kind=record.kind,
        summary=record.summary,
        step_count=len(record.steps),
        verification_status=record.verification_status,
    )


def list_guides(version: str, *, q: str = "", phase: GuidePhaseId | None = None) -> GuideListData:
    """按关键词与推进阶段返回章节摘要，正文仅由详情接口提供。"""
    require_available_version(version)
    dataset = load_guides()
    query = normalize("NFKC", q.strip()).casefold()
    records = [
        record
        for record in dataset.records
        if (phase is None or record.phase_id == phase)
        and (not query or query in guide_text(record))
    ]
    return GuideListData(
        title=dataset.title,
        reference_note=dataset.reference_note,
        route_note=dataset.route_note,
        phases=dataset.phases,
        list=[_summary(record) for record in records],
        total=len(records),
        chapter_count=len(dataset.records),
        diagrams=[diagram for diagram in dataset.diagrams if diagram.id == "mainline-overview"],
        image_references=[
            image for image in dataset.image_references if image.rights_status == "reference_only"
        ],
        limitations=dataset.limitations,
    )


def get_guide(version: str, slug: str) -> GuideDetail:
    """返回本章全部操作、条件、证据、原创流程图和章节导航。"""
    require_available_version(version)
    dataset = load_guides()
    record = next((record for record in dataset.records if record.slug == slug), None)
    if record is None:
        raise BusinessError(404, "没有找到这篇攻略章节")
    source_keys = {
        fact.source_key
        for fact in (
            *record.prerequisites,
            *record.steps,
            *record.key_items,
            *record.battles,
            *record.cautions,
            *record.next_steps,
        )
    }
    diagrams = [diagram for diagram in dataset.diagrams if record.slug in diagram.chapter_ids]
    diagram_targets = {ref.target_id for diagram in diagrams for ref in diagram.source_refs}
    return GuideDetail(
        **record.model_dump(),
        reference_note=dataset.reference_note,
        route_note=dataset.route_note,
        phase=next(phase for phase in dataset.phases if phase.id == record.phase_id),
        phases=dataset.phases,
        chapters=[_summary(chapter) for chapter in dataset.records],
        next_chapters=[
            _summary(chapter)
            for chapter in dataset.records
            if chapter.slug in record.next_chapter_slugs
        ],
        diagrams=diagrams,
        sources=[
            source
            for source in dataset.sources
            if source.key in source_keys or source.source_ref.target_id in diagram_targets
        ],
        limitations=dataset.limitations,
    )
