"""重建带逐条出处、图片权利核对及原创流程图的主线攻略参考。"""

import argparse
import json
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urldefrag, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, Tag
from pydantic import ConfigDict, Field, HttpUrl, model_validator

from mmwiki_data.fetcher import FetchResult, fetch
from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import SourceRef, sorted_unique_source_refs
from mmwiki_data.storage import write_json_atomic
from mmwiki_data.vehicle_tables import text

_ROOT = Path("data/raw/mm2r/0.99/guides")
_CAPTION: Literal["原创流程示意 · 非实机地图 · 0.99未验证"] = (
    "原创流程示意 · 非实机地图 · 0.99未验证"
)
_CHAPTER_IDS = (
    "mado-first-vehicle",
    "party-bay-bridge",
    "tunnel-bazaska",
    "thirsty-preparation",
    "grapple-tower",
    "delta-rio-eva",
    "nemesis-u-shark",
    "swan-lock-hacker",
    "marilyn-room",
    "dark-canal-gates",
    "cagliostro-eva",
    "southern-supplies",
    "optional-south-detours",
    "fumetsu-security",
    "fumetsu-neuro-units",
    "devil-synchronizer",
    "bias-city-surface",
    "failsafe-three-locks",
    "ted-fourth-lock",
    "elevator-power",
    "cyclotron-shutdown",
    "final-three-stages",
    "clear-and-next-cycle",
)
NonEmpty = Annotated[str, Field(min_length=1)]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class GuideStrictModel(StrictModel):
    """拒绝未知字段与来源标量的隐式转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class GuideSourceDraft(GuideStrictModel):
    key: Slug
    source_id: Slug
    title: NonEmpty
    url: HttpUrl
    scope: Literal["mm2r-facts", "rights-review"]
    encoding: Literal["auto", "gb18030"] = "auto"
    declared_license: Literal["NOASSERTION", "CC-BY-NC-SA-4.0"]
    attribution: NonEmpty
    rights_scope_zh: NonEmpty

    @model_validator(mode="after")
    def validate_url(self) -> GuideSourceDraft:
        """只从已核对的公开攻略与许可页面读取HTML，不请求图片。"""
        parsed = urlsplit(str(self.url))
        if parsed.scheme != "https" or parsed.hostname not in {
            "metalmaniax.com",
            "www.zzjb.com",
            "www.962.net",
        }:
            raise ValueError(f"攻略来源不在允许的公开主机内：{self.url}")
        if self.scope == "mm2r-facts" and (
            parsed.hostname != "metalmaniax.com"
            or parsed.path != "/index.php"
            or not parsed.query.startswith("MM2R/")
        ):
            raise ValueError(f"主线事实来源不是MM2R页面：{self.url}")
        return self


class GuideFactDraft(GuideStrictModel):
    id: Slug
    text_zh: NonEmpty
    source_key: Slug
    section: NonEmpty
    evidence: list[NonEmpty] = Field(min_length=1)
    raw_values: dict[str, str] = Field(default_factory=dict)


class GuideFact(GuideFactDraft):
    locator: NonEmpty
    source_ref: SourceRef
    verification_status: Literal["source_only"] = "source_only"


class GuideBattleDraft(GuideFactDraft):
    requirement: Literal["mandatory", "optional", "scripted_loss"]


class GuideBattle(GuideFact):
    requirement: Literal["mandatory", "optional", "scripted_loss"]


class GuidePhase(GuideStrictModel):
    id: Slug
    order: int = Field(ge=1, le=6)
    title_zh: NonEmpty


class GuideChapterDraft(GuideStrictModel):
    id: Slug
    order: int = Field(ge=1, le=23)
    phase_id: Slug
    title_zh: NonEmpty
    location_zh: NonEmpty
    kind: Literal["main", "preparation", "optional"]
    summary_zh: NonEmpty
    prerequisites: list[GuideFactDraft] = Field(min_length=1)
    steps: list[GuideFactDraft] = Field(min_length=3)
    key_items: list[GuideFactDraft]
    battles: list[GuideBattleDraft]
    battle_note_zh: NonEmpty
    cautions: list[GuideFactDraft] = Field(min_length=1)
    next_steps: list[GuideFactDraft] = Field(min_length=1)
    next_chapter_ids: list[Slug]


class GuideChapter(GuideStrictModel):
    id: Slug
    order: int = Field(ge=1, le=23)
    phase_id: Slug
    title_zh: NonEmpty
    location_zh: NonEmpty
    kind: Literal["main", "preparation", "optional"]
    summary_zh: NonEmpty
    prerequisites: list[GuideFact] = Field(min_length=1)
    steps: list[GuideFact] = Field(min_length=3)
    key_items: list[GuideFact]
    battles: list[GuideBattle]
    battle_note_zh: NonEmpty
    cautions: list[GuideFact] = Field(min_length=1)
    next_steps: list[GuideFact] = Field(min_length=1)
    next_chapter_ids: list[Slug]
    source_refs: list[SourceRef] = Field(min_length=1)
    verification_status: Literal["source_only"] = "source_only"


class DiagramNode(GuideStrictModel):
    id: Slug
    label_zh: NonEmpty
    source_fact_id: Slug


class DiagramDraft(GuideStrictModel):
    id: Slug
    title_zh: NonEmpty
    alt_zh: NonEmpty
    chapter_ids: list[Slug] = Field(min_length=1)
    nodes: list[DiagramNode] = Field(min_length=2, max_length=10)


class ImageReferenceDraft(GuideStrictModel):
    id: Slug
    title_zh: NonEmpty
    source_key: Slug
    image_url_match: NonEmpty
    rights_status: Literal["reference_only", "rejected_wrong_version"]
    image_license: Literal["NOASSERTION"] = "NOASSERTION"
    reason_zh: NonEmpty
    evidence: list[NonEmpty] = Field(min_length=1)


class GuideNames(GuideStrictModel):
    schema_version: Literal[1]
    verification_status: Literal["source_only"]
    title_zh: NonEmpty
    reference_note: NonEmpty
    route_note: NonEmpty
    sources: list[GuideSourceDraft] = Field(min_length=1)
    phases: list[GuidePhase] = Field(min_length=6, max_length=6)
    chapters: list[GuideChapterDraft] = Field(min_length=23, max_length=23)
    diagrams: list[DiagramDraft] = Field(min_length=3, max_length=3)
    image_references: list[ImageReferenceDraft] = Field(min_length=2)
    limitations: list[NonEmpty] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_editorial_structure(self) -> GuideNames:
        """编辑清单必须覆盖完整章节、阶段和唯一事实身份。"""
        if tuple(chapter.id for chapter in self.chapters) != _CHAPTER_IDS:
            raise ValueError("主线23章缺失、重复或顺序变化")
        if [chapter.order for chapter in self.chapters] != list(range(1, 24)):
            raise ValueError("主线章节序号不连续")
        source_keys = [source.key for source in self.sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("攻略来源键重复")
        phase_ids = {phase.id for phase in self.phases}
        facts: list[GuideFactDraft] = []
        for chapter in self.chapters:
            if chapter.phase_id not in phase_ids:
                raise ValueError(f"{chapter.id}: 未知阶段")
            if set(chapter.next_chapter_ids) - set(_CHAPTER_IDS):
                raise ValueError(f"{chapter.id}: 下一章不存在")
            facts.extend(_chapter_drafts(chapter))
        ids = [fact.id for fact in facts]
        if len(ids) != len(set(ids)):
            raise ValueError("攻略事实ID重复")
        if any(fact.source_key not in source_keys for fact in facts):
            raise ValueError("攻略事实引用了未知来源")
        for diagram in self.diagrams:
            if set(diagram.chapter_ids) - set(_CHAPTER_IDS):
                raise ValueError(f"{diagram.id}: 图表引用未知章节")
            if any(node.source_fact_id not in ids for node in diagram.nodes):
                raise ValueError(f"{diagram.id}: 图表节点没有事实出处")
        return self


class GuideSource(GuideSourceDraft):
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    license_evidence_text: str | None
    license_url: HttpUrl | None
    source_ref: SourceRef


class GuideImageReference(GuideStrictModel):
    id: Slug
    title_zh: NonEmpty
    source_page_url: HttpUrl
    source_image_url: HttpUrl
    rights_status: Literal["reference_only", "rejected_wrong_version"]
    image_license: Literal["NOASSERTION"] = "NOASSERTION"
    page_declared_license: NonEmpty
    local_path: None = None
    reason_zh: NonEmpty
    evidence: list[NonEmpty]
    source_ref: SourceRef


class GuideDiagram(GuideStrictModel):
    id: Slug
    title_zh: NonEmpty
    alt_zh: NonEmpty
    chapter_ids: list[Slug]
    repo_relative_path: str = Field(
        pattern=r"^data/raw/mm2r/0\.99/guides/diagrams/[a-z0-9-]+-[0-9a-f]{12}\.svg$"
    )
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    rights_status: Literal["original_diagram"] = "original_diagram"
    license: Literal["LicenseRef-Project-Original"] = "LicenseRef-Project-Original"
    author: Literal["Metal Max Wiki 项目原创"] = "Metal Max Wiki 项目原创"
    caption_zh: Literal["原创流程示意 · 非实机地图 · 0.99未验证"] = _CAPTION
    source_refs: list[SourceRef] = Field(min_length=1)


class GuideSnapshot(GuideStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    version_scope: Literal["mm2r-jp-reference"] = "mm2r-jp-reference"
    verification_status: Literal["source_only"] = "source_only"
    title_zh: NonEmpty
    reference_note: NonEmpty
    route_note: NonEmpty
    source_locator_note: str = (
        "所有攻略事实以source_url锚点、section和locator定位；正文SourceRef的table_index和"
        "row_index使用0，不表示来自表格行。证据为用于核对的短片段，不保存完整攻略正文。"
    )
    phases: list[GuidePhase] = Field(min_length=6, max_length=6)
    chapters: list[GuideChapter] = Field(min_length=23, max_length=23)
    diagrams: list[GuideDiagram] = Field(min_length=3, max_length=3)
    image_references: list[GuideImageReference] = Field(min_length=2)
    sources: list[GuideSource] = Field(min_length=1)
    limitations: list[NonEmpty] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_coverage(self) -> GuideSnapshot:
        """终盘机制和本地原创图不能在序列化时被遗漏或替换。"""
        if tuple(chapter.id for chapter in self.chapters) != _CHAPTER_IDS:
            raise ValueError("攻略快照没有完整覆盖主线23章")
        if len({diagram.id for diagram in self.diagrams}) != 3:
            raise ValueError("攻略原创图ID重复")
        sources = {source.key: source for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("攻略来源键重复")
        if [phase.order for phase in self.phases] != list(range(1, 7)):
            raise ValueError("攻略阶段序号不连续")
        fact_ids: set[str] = set()
        for chapter in self.chapters:
            chapter_facts = _chapter_facts(chapter)
            for fact in chapter_facts:
                if fact.id in fact_ids:
                    raise ValueError(f"{fact.id}: 攻略事实身份重复")
                fact_ids.add(fact.id)
                source = sources.get(fact.source_key)
                if source is None or source.scope != "mm2r-facts":
                    raise ValueError(f"{fact.id}: 攻略事实误用了许可或旧版本页面")
                ref = fact.source_ref
                if (
                    ref.content_hash != source.content_hash
                    or ref.source_id != source.source_id
                    or ref.target_id != source.source_ref.target_id
                    or ref.retrieved_at != source.retrieved_at
                    or urldefrag(str(ref.source_url))[0] != str(source.url)
                ):
                    raise ValueError(f"{fact.id}: 事实来源页面、时间或哈希错配")
            expected_refs = sorted_unique_source_refs([fact.source_ref for fact in chapter_facts])
            if chapter.source_refs != expected_refs:
                raise ValueError(f"{chapter.id}: 章节出处与逐条事实不一致")
        return self


@dataclass(frozen=True, slots=True)
class _Page:
    source: GuideSourceDraft
    result: FetchResult
    retrieved_at: datetime
    document: BeautifulSoup
    content: Tag


def _chapter_drafts(chapter: GuideChapterDraft) -> list[GuideFactDraft]:
    return [
        *chapter.prerequisites,
        *chapter.steps,
        *chapter.key_items,
        *chapter.battles,
        *chapter.cautions,
        *chapter.next_steps,
    ]


def _chapter_facts(chapter: GuideChapter) -> list[GuideFact]:
    return [
        *chapter.prerequisites,
        *chapter.steps,
        *chapter.key_items,
        *chapter.battles,
        *chapter.cautions,
        *chapter.next_steps,
    ]


def _fetch_pages(names: GuideNames, sleep: Callable[[float], None]) -> dict[str, _Page]:
    result: dict[str, _Page] = {}
    with httpx.Client(timeout=40, follow_redirects=True) as client:
        for source in names.sources:
            if result:
                sleep(1.0)
            fetched = fetch(client, f"guides-{source.key}", str(source.url))
            document = BeautifulSoup(
                fetched.body,
                "html.parser",
                from_encoding=None if source.encoding == "auto" else source.encoding,
            )
            content = (
                document.select_one("#body") if source.scope == "mm2r-facts" else document.body
            )
            if content is None or (
                source.scope == "mm2r-facts" and content.find("textarea") is not None
            ):
                raise ValueError(f"{source.key}: 来源不存在或没有可定位正文")
            result[source.key] = _Page(
                source, fetched, datetime.now().astimezone(), document, content
            )
    return result


def _ref(page: _Page, url: str | None = None) -> SourceRef:
    return SourceRef(
        source_id=page.source.source_id,
        target_id=f"guides-{page.source.key}",
        source_url=page.source.url if url is None else HttpUrl(url),
        retrieved_at=page.retrieved_at,
        content_hash=page.result.content_hash,
        table_index=0,
        row_index=0,
    )


def _fact(draft: GuideFactDraft, pages: dict[str, _Page]) -> GuideFact:
    page = pages[draft.source_key]
    matches = [
        tag
        for tag in page.content.find_all(re.compile(r"^h[2-6]$"))
        if "".join(text(tag).removesuffix("†").split()) == "".join(draft.section.split())
    ]
    if len(matches) != 1:
        raise ValueError(f"{draft.id}: 不能唯一定位来源章节 {draft.section!r}")
    heading = matches[0]
    level = int(heading.name[1])
    pieces: list[str] = []
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if re.fullmatch(r"h[2-6]", sibling.name) and int(sibling.name[1]) <= level:
            break
        pieces.append(text(sibling))
    source_text = "".join(" ".join(pieces).split())
    for evidence in draft.evidence:
        if "".join(evidence.split()) not in source_text:
            raise ValueError(f"{draft.id}: 来源证据变化，找不到 {evidence!r}")
    anchor = heading.find("a", class_="anchor_super")
    anchor_id = anchor.get("id") if isinstance(anchor, Tag) else heading.get("id")
    if not isinstance(anchor_id, str) or not anchor_id:
        raise ValueError(f"{draft.id}: 来源章节缺少稳定锚点")
    url = urldefrag(str(page.source.url))[0] + "#" + anchor_id
    values = draft.model_dump(exclude={"requirement"})
    return GuideFact.model_validate(
        {**values, "locator": draft.section, "source_ref": _ref(page, url)}
    )


def _chapter(draft: GuideChapterDraft, pages: dict[str, _Page]) -> GuideChapter:
    groups = {
        name: [_fact(fact, pages) for fact in getattr(draft, name)]
        for name in ("prerequisites", "steps", "key_items", "cautions", "next_steps")
    }
    battles = [
        GuideBattle.model_validate(
            {**_fact(battle, pages).model_dump(), "requirement": battle.requirement}
        )
        for battle in draft.battles
    ]
    facts = [*(fact for group in groups.values() for fact in group), *battles]
    fields = draft.model_dump(exclude={*groups, "battles"})
    return GuideChapter.model_validate(
        {
            **fields,
            **groups,
            "battles": battles,
            "source_refs": sorted_unique_source_refs([fact.source_ref for fact in facts]),
        }
    )


def _source_metadata(page: _Page) -> GuideSource:
    evidence = None
    license_url = None
    if page.source.declared_license == "CC-BY-NC-SA-4.0":
        evidence = "除额外注明的地方外，本维基上的内容按下列许可协议发布"
        if evidence not in text(page.content):
            raise ValueError(f"{page.source.key}: CC页脚许可证据不存在")
        links = [
            str(link["href"])
            for link in page.document.find_all("a", href=True)
            if str(link["href"]).startswith("https://creativecommons.org/licenses/by-nc-sa/4.0/")
        ]
        if not links:
            raise ValueError(f"{page.source.key}: CC BY-NC-SA 4.0许可链接不存在")
        license_url = HttpUrl(links[0])
    return GuideSource(
        **page.source.model_dump(),
        retrieved_at=page.retrieved_at,
        content_hash=page.result.content_hash,
        license_evidence_text=evidence,
        license_url=license_url,
        source_ref=_ref(page),
    )


def _image_reference(draft: ImageReferenceDraft, pages: dict[str, _Page]) -> GuideImageReference:
    page = pages[draft.source_key]
    source_text = text(page.content)
    if any(evidence not in source_text for evidence in draft.evidence):
        raise ValueError(f"{draft.id}: 图片许可或版本的核对证据变化")
    images = [
        str(image["src"])
        for image in page.document.find_all("img", src=True)
        if draft.image_url_match in str(image["src"])
    ]
    if len(set(images)) != 1:
        raise ValueError(f"{draft.id}: 不能唯一定位外链图片")
    image_url = images[0]
    if image_url.startswith("/"):
        parsed = urlsplit(str(page.source.url))
        image_url = f"{parsed.scheme}://{parsed.netloc}" + image_url
    return GuideImageReference(
        id=draft.id,
        title_zh=draft.title_zh,
        source_page_url=page.source.url,
        source_image_url=HttpUrl(image_url),
        rights_status=draft.rights_status,
        page_declared_license=page.source.declared_license,
        reason_zh=draft.reason_zh,
        evidence=draft.evidence,
        source_ref=_ref(page),
    )


def _svg(draft: DiagramDraft) -> bytes:
    width, gap, top = 840, 118, 112
    height = top + len(draft.nodes) * gap + 100
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {width} {height}",
            "role": "img",
            "aria-labelledby": "title desc",
        },
    )
    ET.SubElement(root, "title", {"id": "title"}).text = draft.title_zh
    ET.SubElement(root, "desc", {"id": "desc"}).text = draft.alt_zh + "。" + _CAPTION
    ET.SubElement(
        root, "rect", {"width": str(width), "height": str(height), "rx": "20", "fill": "#f4f7fa"}
    )
    ET.SubElement(
        root,
        "text",
        {
            "x": "48",
            "y": "51",
            "fill": "#183243",
            "font-size": "25",
            "font-family": "sans-serif",
            "font-weight": "700",
        },
    ).text = draft.title_zh
    ET.SubElement(
        root,
        "text",
        {"x": "48", "y": "80", "fill": "#546878", "font-size": "15", "font-family": "sans-serif"},
    ).text = "箭头表示推荐推进次序与事件条件，不表示地理距离或坐标。"
    for index, node in enumerate(draft.nodes):
        y = top + index * gap
        if index:
            ET.SubElement(
                root,
                "path",
                {
                    "d": f"M420 {y - 31} V{y - 9} M414 {y - 16} L420 {y - 9} L426 {y - 16}",
                    "fill": "none",
                    "stroke": "#6d8797",
                    "stroke-width": "2.5",
                },
            )
        ET.SubElement(
            root,
            "rect",
            {
                "x": "48",
                "y": str(y),
                "width": "744",
                "height": "84",
                "rx": "12",
                "fill": "#ffffff",
                "stroke": "#c9d7df",
                "stroke-width": "1.5",
            },
        )
        ET.SubElement(root, "circle", {"cx": "80", "cy": str(y + 42), "r": "16", "fill": "#176c73"})
        ET.SubElement(
            root,
            "text",
            {
                "x": "80",
                "y": str(y + 48),
                "text-anchor": "middle",
                "fill": "#ffffff",
                "font-size": "16",
                "font-family": "sans-serif",
            },
        ).text = str(index + 1)
        lines = node.label_zh.split("\n")
        for line_index, line in enumerate(lines):
            ET.SubElement(
                root,
                "text",
                {
                    "x": "112",
                    "y": str(y + (35 if len(lines) > 1 else 49) + line_index * 26),
                    "fill": "#183243",
                    "font-size": "18",
                    "font-family": "sans-serif",
                },
            ).text = line
    ET.SubElement(
        root,
        "text",
        {
            "x": "48",
            "y": str(height - 47),
            "fill": "#546878",
            "font-size": "15",
            "font-family": "sans-serif",
        },
    ).text = _CAPTION
    ET.SubElement(
        root,
        "text",
        {
            "x": "48",
            "y": str(height - 23),
            "fill": "#546878",
            "font-size": "13",
            "font-family": "sans-serif",
        },
    ).text = "Metal Max Wiki 项目原创；事实出处见同章引用，未复用外部截图或地图像素。"
    ET.indent(root, space="  ")
    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if not isinstance(serialized, bytes):
        raise TypeError("原创SVG序列化没有返回UTF-8字节")
    result = serialized + b"\n"
    _validate_svg(result)
    return result


def _validate_svg(data: bytes) -> None:
    root = ET.fromstring(data)
    allowed = {"svg", "title", "desc", "rect", "circle", "path", "text"}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] not in allowed:
            raise ValueError("原创SVG包含非图表元素")
        if any(key.lower().startswith("on") or "href" in key.lower() for key in node.attrib):
            raise ValueError("原创SVG包含外链或事件处理器")
    if _CAPTION not in data.decode("utf-8"):
        raise ValueError("原创SVG缺少非实机地图声明")


def _write_svg_atomic(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"内容寻址的原创SVG已损坏，未覆盖：{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as file:
            temporary = Path(file.name)
            os.fchmod(file.fileno(), 0o644)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_guides(repo_root: Path) -> GuideSnapshot | None:
    """离线读取主线攻略，并校验原创SVG路径、内容哈希和安全结构。"""
    path = repo_root / _ROOT / "facts.json"
    if not path.exists():
        return None
    snapshot = GuideSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    for diagram in snapshot.diagrams:
        data = (repo_root / diagram.repo_relative_path).read_bytes()
        if "sha256:" + sha256(data).hexdigest() != diagram.content_hash:
            raise ValueError(f"{diagram.id}: 原创SVG内容哈希不匹配")
        _validate_svg(data)
    return snapshot


def collect_guides(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行采集主线事实与许可证据，全部校验后原子替换攻略快照。"""
    names = GuideNames.model_validate(
        yaml.safe_load((repo_root / _ROOT / "names.yaml").read_text(encoding="utf-8"))
    )
    pages = _fetch_pages(names, sleep)
    chapters = [_chapter(chapter, pages) for chapter in names.chapters]
    facts = {fact.id: fact for chapter in chapters for fact in _chapter_facts(chapter)}
    diagrams: list[GuideDiagram] = []
    files: dict[Path, bytes] = {}
    for draft in names.diagrams:
        data = _svg(draft)
        digest = sha256(data).hexdigest()
        path = _ROOT / "diagrams" / f"{draft.id}-{digest[:12]}.svg"
        files[repo_root / path] = data
        diagrams.append(
            GuideDiagram(
                id=draft.id,
                title_zh=draft.title_zh,
                alt_zh=draft.alt_zh,
                chapter_ids=draft.chapter_ids,
                repo_relative_path=path.as_posix(),
                content_hash="sha256:" + digest,
                source_refs=sorted_unique_source_refs(
                    [facts[node.source_fact_id].source_ref for node in draft.nodes]
                ),
            )
        )
    snapshot = GuideSnapshot(
        title_zh=names.title_zh,
        reference_note=names.reference_note,
        route_note=names.route_note,
        phases=names.phases,
        chapters=chapters,
        diagrams=diagrams,
        image_references=[_image_reference(image, pages) for image in names.image_references],
        sources=[_source_metadata(page) for page in pages.values()],
        limitations=names.limitations,
    )
    for path, data in files.items():
        _write_svg_atomic(path, data)
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "chapters": len(chapters),
        "phases": len(snapshot.phases),
        "steps": sum(len(chapter.steps) for chapter in chapters),
        "facts": len(facts),
        "source_pages": len(pages),
        "diagrams": len(diagrams),
        "external_image_references": len(snapshot.image_references),
    }


def main() -> None:
    """独立运行主线攻略采集或离线校验。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if args.validate_only:
        snapshot = load_guides(root)
        if snapshot is None:
            raise ValueError("主线攻略快照不存在")
        result = {"chapters": len(snapshot.chapters), "diagrams": len(snapshot.diagrams)}
    else:
        result = collect_guides(root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
