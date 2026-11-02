"""采集101项日版任务和特别委托的事实与中文参考摘要。"""

import argparse
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlsplit

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
TARGET_ID = "maniax-quests"
ZZJB_SOURCE_ID = "zzjb-mm2r"
ZZJB_TARGET_ID = "quests"
INDEX_URL = "https://metalmaniax.com/index.php?MM2R/DATA/%E3%82%AF%E3%82%A8%E3%82%B9%E3%83%88"
ZZJB_URL = "https://www.zzjb.com/wiki/mm2r/mm2r_quest"
_DETAIL_PREFIX = "MM2R/DATA/クエスト/"
_ROOT = Path("data/raw/mm2r/0.99/quests")
_HEADERS = ("No.", "名称", "受注場所", "開始条件", "達成条件", "経験値", "有名度", "報酬(条件)")
_ZZJB_HEADERS = ("任务名称", "汉译名", "任务接受场所", "经验值", "有名度", "报酬", "备注")
_ZZJB_NAMES = (
    "マリアよ、安らかに眠れ",
    "砂漠を越えて",
    "埋もれたマンホール",
    "木材ハンター",
    "デヤークのおつかい",
    "タケノコ狩り",
    "並ばされし者たち",
    "昔のボトルで出ています",
)
_DETAIL_SECTIONS = ("発生場所", "発生条件", "ガイド項目一覧", "達成条件", "報酬", "コメント")
_FACT_SECTIONS: tuple[Literal["発生場所", "発生条件", "報酬"], ...] = (
    "発生場所",
    "発生条件",
    "報酬",
)
_MISSING_KEYS: tuple[Literal["location", "acceptance", "rewards"], ...] = (
    "location",
    "acceptance",
    "rewards",
)
_OVERVIEW_FALLBACK_FIELDS = (("受注場所",), ("開始条件",), ("経験値", "有名度", "報酬(条件)"))
_MISSING_FAILURE_NOTE = "来源未明确提供失败或错过条件，不代表不存在此类条件。"


class QuestStrictModel(StrictModel):
    """拒绝未知字段及隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class QuestDetailCheck(QuestStrictModel):
    section_ja: str = Field(min_length=1)
    terms: list[str] = Field(min_length=1)


class QuestReferenceName(QuestStrictModel):
    name_ja: str = Field(min_length=1)
    name_zh_reference: str = Field(min_length=1)
    detail_title_aliases: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    location_zh: str = Field(min_length=1)
    acceptance_zh: str = Field(min_length=1)
    steps_zh: list[str] = Field(min_length=1)
    reward_notes_zh: list[str] = Field(default_factory=list)
    source_uncertainties_zh: list[str] = Field(default_factory=list)
    failure_notes_zh: list[str] | None = None
    detail_checks: list[QuestDetailCheck] = Field(default_factory=list)
    vehicle_related: bool = False

    @model_validator(mode="after")
    def validate_summaries(self) -> QuestReferenceName:
        """明确缺失与有据说明不能以空列表混淆。"""
        if self.failure_notes_zh == []:
            raise ValueError(f"{self.name_ja}: 未知失败条件请用null，不使用空列表")
        if self.failure_notes_zh is not None and not self.detail_checks:
            raise ValueError(f"{self.name_ja}: 失败或错过说明缺少详情证据核对")
        return self


class QuestNames(QuestStrictModel):
    schema_version: Literal[1]
    reference_note: str = Field(min_length=1)
    coverage_note: str = Field(min_length=1)
    quests: dict[int, QuestReferenceName]

    @model_validator(mode="after")
    def validate_coverage(self) -> QuestNames:
        """使用完整编号集合防止缺项和错名。"""
        if set(self.quests) != set(range(1, 102)):
            raise ValueError("任务参考清单必须完整覆盖编号1至101")
        names = [quest.name_ja for quest in self.quests.values()]
        if len(names) != len(set(names)):
            raise ValueError("任务参考清单包含重复日文名")
        return self


class QuestOverview(QuestStrictModel):
    number: int = Field(ge=1, le=101)
    name_ja: str = Field(min_length=1)
    fields: dict[str, str]
    detail_url: HttpUrl
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_identity(self) -> QuestOverview:
        """原表编号、名称、来源和详情地址必须一致。"""
        if (
            set(self.fields) != set(_HEADERS)
            or self.fields["No."] != str(self.number)
            or self.fields["名称"] != self.name_ja
        ):
            raise ValueError(f"{self.name_ja}: 任务原表字段或身份不一致")
        _validate_detail_url(str(self.detail_url), self.name_ja)
        _validate_source_ref(self.source_ref, SOURCE_ID, TARGET_ID, INDEX_URL)
        expected_row = self.number + sum(self.number > boundary for boundary in (25, 50, 75))
        if self.source_ref.row_index != expected_row:
            raise ValueError(f"{self.name_ja}: 任务编号与总表物理行定位不一致")
        return self


class QuestChineseReference(QuestStrictModel):
    fields: dict[str, str]
    source_ref: SourceRef

    @model_validator(mode="after")
    def validate_fields(self) -> QuestChineseReference:
        """只接受现有中文来源的七个事实字段。"""
        if set(self.fields) != set(_ZZJB_HEADERS):
            raise ValueError("中文任务对照的原字段不完整")
        _validate_source_ref(self.source_ref, ZZJB_SOURCE_ID, ZZJB_TARGET_ID, ZZJB_URL)
        row = self.source_ref.row_index
        if row >= len(_ZZJB_NAMES) or self.fields["任务名称"] != _ZZJB_NAMES[row]:
            raise ValueError("中文任务原名与源行定位不一致")
        return self


class QuestDetailField(QuestStrictModel):
    section_ja: Literal["発生場所", "発生条件", "報酬"]
    section_anchor: str = Field(min_length=1)
    values_ja_raw: list[str]
    source_ref: SourceRef


class QuestFailureConditions(QuestStrictModel):
    status: Literal["documented", "not_documented"]
    notes_zh: list[str] = Field(min_length=1)
    source_refs: list[SourceRef]

    @model_validator(mode="after")
    def validate_absence(self) -> QuestFailureConditions:
        """缺失标记不能伪装成有据的无失败条件结论。"""
        if self.status == "documented" and not self.source_refs:
            raise ValueError("已记录失败或错过条件必须有来源定位")
        if self.status == "not_documented" and (
            self.notes_zh != [_MISSING_FAILURE_NOTE] or self.source_refs
        ):
            raise ValueError("缺失的失败条件只能使用明确缺失说明")
        return self


class QuestFact(QuestStrictModel):
    number: int = Field(ge=1, le=101)
    name_ja: str = Field(min_length=1)
    name_zh_reference: str = Field(min_length=1)
    aliases: list[str]
    overview: QuestOverview
    chinese_reference: QuestChineseReference | None
    request_kind: Literal["special_request", "ordinary_or_event"]
    location_zh: str = Field(min_length=1)
    acceptance_zh: str = Field(min_length=1)
    steps_zh: list[str] = Field(min_length=1)
    reward_notes_zh: list[str]
    source_uncertainties_zh: list[str]
    failure_conditions: QuestFailureConditions
    detail_fields: list[QuestDetailField] = Field(min_length=3, max_length=3)
    summary_refs: list[SourceRef] = Field(min_length=1)
    missing_fields: list[Literal["location", "acceptance", "rewards", "failure_conditions"]]
    vehicle_related: bool
    verification_status: Literal["source_only"] = "source_only"

    @model_validator(mode="after")
    def validate_record(self) -> QuestFact:
        """拒绝记录身份、中文对照和详情引用错配。"""
        if self.number != self.overview.number or self.name_ja != self.overview.name_ja:
            raise ValueError(f"{self.name_ja}: 任务记录与原表身份不一致")
        if self.chinese_reference is not None:
            if self.chinese_reference.fields["任务名称"] != self.name_ja:
                raise ValueError(f"{self.name_ja}: 中文参考行身份不一致")
        if [field.section_ja for field in self.detail_fields] != ["発生場所", "発生条件", "報酬"]:
            raise ValueError(f"{self.name_ja}: 详情事实字段缺失或乱序")
        for field in self.detail_fields:
            _validate_source_ref(
                field.source_ref, SOURCE_ID, TARGET_ID, str(self.overview.detail_url)
            )
            if field.source_ref.source_url.fragment != field.section_anchor:
                raise ValueError(f"{self.name_ja}: 详情小节锚点不一致")
        for ref in self.summary_refs:
            if str(ref.source_url).split("#", 1)[0] not in (
                INDEX_URL,
                str(self.overview.detail_url),
            ):
                raise ValueError(f"{self.name_ja}: 中文摘要引用其他任务页面")
            _validate_source_ref(ref, SOURCE_ID, TARGET_ID, str(ref.source_url).split("#", 1)[0])
            if str(ref.source_url) == INDEX_URL and ref != self.overview.source_ref:
                raise ValueError(f"{self.name_ja}: 摘要的总表引用不是本任务原行")
        if any(ref not in self.summary_refs for ref in self.failure_conditions.source_refs):
            raise ValueError(f"{self.name_ja}: 失败条件引用未经过任务摘要证据核对")
        if (self.failure_conditions.status == "not_documented") != (
            "failure_conditions" in self.missing_fields
        ):
            raise ValueError(f"{self.name_ja}: 失败条件缺失标记不一致")
        expected_missing = _missing_primary_fields(self.overview, self.detail_fields)
        if self.failure_conditions.status == "not_documented":
            expected_missing.append("failure_conditions")
        if self.missing_fields != expected_missing:
            raise ValueError(f"{self.name_ja}: 字段缺失标记没有合并总表和详情的事实")
        return self


class QuestSnapshot(QuestStrictModel):
    schema_version: Literal[1] = 1
    game: Literal["mm2r"] = "mm2r"
    target_version: Literal["0.99"] = "0.99"
    version_scope: Literal["mm2r-jp"] = "mm2r-jp"
    verification_status: Literal["source_only"] = "source_only"
    reference_note: str = Field(min_length=1)
    coverage_note: str = Field(min_length=1)
    row_index_note: str = (
        "SourceRef.row_index从首行表头后的物理行开始按0计数，重复表头所占行仍保留。"
        "正文事实以URL片段和section_anchor定位，table_index与row_index使用0。"
    )
    repeated_header_rows: int = Field(ge=5, le=5)
    records: list[QuestFact] = Field(min_length=101, max_length=101)

    @model_validator(mode="after")
    def validate_complete_snapshot(self) -> QuestSnapshot:
        """完整快照必须逐号覆盖，且每行来源只对应一项任务。"""
        if [record.number for record in self.records] != list(range(1, 102)):
            raise ValueError("任务快照必须按顺序完整包含编号1至101")
        names = {record.name_ja for record in self.records}
        rows = {record.overview.source_ref.row_index for record in self.records}
        if len(names) != 101 or len(rows) != 101:
            raise ValueError("任务快照出现重复名称或源行定位")
        if sum(record.chinese_reference is not None for record in self.records) != 8:
            raise ValueError("中文来源当前应完整覆盖8条参考行")
        return self


def _validate_detail_url(url: str, name: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "metalmaniax.com"
        or parsed.path != "/index.php"
        or unquote(parsed.query) != f"{_DETAIL_PREFIX}{name}"
        or parsed.fragment
    ):
        raise ValueError(f"{name}: 任务详情链接不符合来源路径：{url}")


def _validate_source_ref(ref: SourceRef, source_id: str, target_id: str, url: str) -> None:
    if (
        ref.source_id != source_id
        or ref.target_id != target_id
        or str(ref.source_url).split("#", 1)[0] != url
        or ref.table_index != 0
    ):
        raise ValueError(f"任务来源标识或地址不一致：{ref.source_url}")
    if url not in (INDEX_URL, ZZJB_URL) and (ref.row_index != 0 or not ref.source_url.fragment):
        raise ValueError(f"任务正文引用缺少小节定位：{ref.source_url}")


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


def _load_names(repo_root: Path) -> QuestNames:
    path = repo_root / _ROOT / "names.yaml"
    return QuestNames.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _missing_primary_fields(
    overview: QuestOverview, fields: list[QuestDetailField]
) -> list[Literal["location", "acceptance", "rewards", "failure_conditions"]]:
    """正文留空时核对总表，避免把空小节误判为整个事实字段缺失。"""
    missing: list[Literal["location", "acceptance", "rewards", "failure_conditions"]] = []
    for field, key, headers in zip(fields, _MISSING_KEYS, _OVERVIEW_FALLBACK_FIELDS, strict=True):
        values = [*field.values_ja_raw, *(overview.fields[header] for header in headers)]
        if not any(value.strip() not in ("", "?", "？", "不明", "未確認") for value in values):
            missing.append(key)
    return missing


def _find_table(content: Tag, headers: tuple[str, ...]) -> tuple[int, Tag]:
    matches = [
        (index, table)
        for index, table in enumerate(content.find_all("table"))
        if (row := table.find("tr")) is not None
        and tuple(text(cell) for cell in row.find_all(["th", "td"])) == headers
    ]
    if len(matches) != 1:
        raise ValueError(f"任务页面无法唯一定位表头：{headers}")
    return matches[0]


def _parse_overview(result: FetchResult, names: QuestNames) -> tuple[list[QuestOverview], int]:
    content = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if content is None:
        raise ValueError("日文任务总表缺少正文")
    table_index, table = _find_table(content, _HEADERS)
    rows = expanded_rows(table)
    overviews: list[QuestOverview] = []
    headers = 0
    for physical_index, (row, values) in enumerate(zip(table.find_all("tr"), rows, strict=True)):
        if tuple(values) == _HEADERS:
            headers += 1
            continue
        if len(values) != len(_HEADERS) or not values[0].isdigit():
            raise ValueError(f"任务总表第{physical_index}行字段变化：{values}")
        number = int(values[0])
        if number not in names.quests or names.quests[number].name_ja != values[1]:
            raise ValueError(f"任务总表编号与名称清单不一致：{values[:2]}")
        link = row.find("a", href=True)
        if not isinstance(link, Tag) or text(link) != values[1]:
            raise ValueError(f"{values[1]}: 总表缺少正确的详情链接")
        url = urljoin(INDEX_URL, str(link["href"]))
        _validate_detail_url(url, values[1])
        overviews.append(
            QuestOverview(
                number=number,
                name_ja=values[1],
                fields=dict(zip(_HEADERS, values, strict=True)),
                detail_url=HttpUrl(url),
                source_ref=_make_ref(
                    result, INDEX_URL, table_index=table_index, row_index=physical_index - 1
                ),
            )
        )
    if [overview.number for overview in overviews] != list(range(1, 102)) or headers != 5:
        raise ValueError("日文任务总表不再是101条任务与5行重复表头，拒绝覆盖快照")
    return overviews, headers


def _parse_chinese(result: FetchResult) -> dict[str, QuestChineseReference]:
    soup = BeautifulSoup(result.body, "html.parser")
    table_index, table = _find_table(soup, _ZZJB_HEADERS)
    references: dict[str, QuestChineseReference] = {}
    for row_index, values in enumerate(expanded_rows(table)[1:]):
        if len(values) != len(_ZZJB_HEADERS) or not values[0] or values[0] in references:
            raise ValueError(f"中文任务表第{row_index}行字段或名称无效")
        references[values[0]] = QuestChineseReference(
            fields=dict(zip(_ZZJB_HEADERS, values, strict=True)),
            source_ref=_make_ref(
                result,
                ZZJB_URL,
                source_id=ZZJB_SOURCE_ID,
                target_id=ZZJB_TARGET_ID,
                table_index=table_index,
                row_index=row_index,
            ),
        )
    if len(references) != 8:
        raise ValueError("中文任务来源不再是8条，请先复核覆盖范围")
    return references


def _section(body: Tag, name: str, label: str) -> tuple[str, list[str], str]:
    matches = [
        heading
        for heading in body.find_all("h3")
        if text(heading).removesuffix("†").strip() == label
    ]
    if len(matches) != 1:
        raise ValueError(f"{name}: 无法唯一定位详情小节「{label}」")
    heading = matches[0]
    anchor_tag = heading.find("a", id=True)
    anchor = anchor_tag.get("id") if isinstance(anchor_tag, Tag) else heading.get("id")
    if not isinstance(anchor, str) or not anchor:
        raise ValueError(f"{name}: 详情小节「{label}」缺少锚点")
    values: list[str] = []
    content: list[str] = []
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.name in ("h2", "h3"):
            break
        content.append(text(sibling))
        if sibling.name in ("ul", "ol"):
            values.extend(text(item) for item in sibling.find_all("li", recursive=False))
        elif sibling.name == "p" and text(sibling) not in ("", "↑"):
            values.append(text(sibling))
    return anchor, values, re.sub(r"\s+", "", " ".join(content))


def _detail_facts(
    result: FetchResult, overview: QuestOverview, reference: QuestReferenceName
) -> tuple[list[QuestDetailField], list[SourceRef]]:
    body = BeautifulSoup(result.body, "html.parser").select_one("#body")
    if body is None:
        raise ValueError(f"{overview.name_ja}: 任务详情缺少正文")
    heading = body.find("h2")
    allowed_titles = [overview.name_ja, *reference.detail_title_aliases]
    if heading is None or text(heading).removesuffix("†").strip() not in allowed_titles:
        raise ValueError(f"{overview.name_ja}: 任务详情标题不匹配")
    actual = [text(tag).removesuffix("†").strip() for tag in body.find_all("h3")]
    expected = (
        (*_DETAIL_SECTIONS[:4], "有名度", *_DETAIL_SECTIONS[4:])
        if overview.number == 43
        else _DETAIL_SECTIONS
    )
    if tuple(actual) != expected:
        raise ValueError(f"{overview.name_ja}: 任务详情事实小节结构变化：{actual}")
    facts: list[QuestDetailField] = []
    for label in _FACT_SECTIONS:
        anchor, values, _content = _section(body, overview.name_ja, label)
        facts.append(
            QuestDetailField(
                section_ja=label,
                section_anchor=anchor,
                values_ja_raw=values,
                source_ref=_make_ref(result, f"{overview.detail_url}#{anchor}"),
            )
        )
    refs: list[SourceRef] = []
    for check in reference.detail_checks:
        anchor, _values, content = _section(body, overview.name_ja, check.section_ja)
        missing = [term for term in check.terms if re.sub(r"\s+", "", term) not in content]
        if missing:
            raise ValueError(f"{overview.name_ja}: 小节「{check.section_ja}」缺少核对证据{missing}")
        refs.append(_make_ref(result, f"{overview.detail_url}#{anchor}"))
    return facts, refs


def collect_quests(
    repo_root: Path, *, sleep: Callable[[float], None] = time.sleep
) -> dict[str, int]:
    """串行采集全部任务，通过完整性校验后原子写入事实快照。"""
    names = _load_names(repo_root)
    request_count = 0
    records: list[QuestFact] = []
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

        overviews, repeated_headers = _parse_overview(request(TARGET_ID, INDEX_URL), names)
        chinese = _parse_chinese(request(ZZJB_TARGET_ID, ZZJB_URL))
        if set(chinese) - {overview.name_ja for overview in overviews}:
            raise ValueError("中文任务来源出现未匹配的任务名称")
        for overview in overviews:
            reference = names.quests[overview.number]
            fields, checked_refs = _detail_facts(
                request(TARGET_ID, str(overview.detail_url)), overview, reference
            )
            missing = _missing_primary_fields(overview, fields)
            if reference.failure_notes_zh is None:
                missing.append("failure_conditions")
                failure = QuestFailureConditions(
                    status="not_documented", notes_zh=[_MISSING_FAILURE_NOTE], source_refs=[]
                )
            else:
                failure = QuestFailureConditions(
                    status="documented",
                    notes_zh=reference.failure_notes_zh,
                    source_refs=checked_refs,
                )
            special = "特別な依頼" in overview.fields["開始条件"] or any(
                "特別な依頼" in value for value in fields[1].values_ja_raw
            )
            records.append(
                QuestFact(
                    number=overview.number,
                    name_ja=overview.name_ja,
                    name_zh_reference=reference.name_zh_reference,
                    aliases=reference.aliases,
                    overview=overview,
                    chinese_reference=chinese.get(overview.name_ja),
                    request_kind="special_request" if special else "ordinary_or_event",
                    location_zh=reference.location_zh,
                    acceptance_zh=reference.acceptance_zh,
                    steps_zh=reference.steps_zh,
                    reward_notes_zh=reference.reward_notes_zh,
                    source_uncertainties_zh=reference.source_uncertainties_zh,
                    failure_conditions=failure,
                    detail_fields=fields,
                    summary_refs=[overview.source_ref, *checked_refs],
                    missing_fields=missing,
                    vehicle_related=reference.vehicle_related,
                )
            )
            print(f"任务 {overview.number:03d}：{reference.name_zh_reference}", flush=True)
    snapshot = QuestSnapshot(
        reference_note=names.reference_note,
        coverage_note=names.coverage_note,
        repeated_header_rows=repeated_headers,
        records=records,
    )
    write_json_atomic(repo_root / _ROOT / "facts.json", snapshot)
    return {
        "quests": len(records),
        "special_requests": sum(record.request_kind == "special_request" for record in records),
        "chinese_references": sum(record.chinese_reference is not None for record in records),
        "documented_failure_conditions": sum(
            record.failure_conditions.status == "documented" for record in records
        ),
        "vehicle_related": sum(record.vehicle_related for record in records),
        "requests": request_count,
    }


def main() -> None:
    """提供独立任务采集入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    arguments = parser.parse_args()
    print(collect_quests(arguments.repo_root.resolve()))


if __name__ == "__main__":
    main()
