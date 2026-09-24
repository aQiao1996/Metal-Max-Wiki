"""资料来源、采集目标和候选快照的数据契约。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class VerificationStatus(StrEnum):
    """资料相对于本机 0.99 版本的核验状态。"""

    SOURCE_ONLY = "source_only"
    CROSS_CHECKED = "cross_checked"
    COMPATIBLE_CANDIDATE = "compatible_candidate"
    VERIFIED_0_99 = "verified_0_99"
    CONFLICT = "conflict"


class StrictModel(BaseModel):
    """拒绝清单与快照中的未知字段。"""

    model_config = ConfigDict(extra="forbid")


class Source(StrictModel):
    """外部资料来源及其使用限制。"""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1)
    base_url: HttpUrl
    language: str = Field(min_length=2)
    license: str = Field(min_length=1)
    usage: str = Field(pattern=r"^(primary-data|mechanics-reference|cross-check-only)$")
    attribution: str = Field(min_length=1)
    notes: str = ""


class Target(StrictModel):
    """经过人工许可的单个采集页面。"""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    source_id: str = Field(pattern=r"^[a-z0-9-]+$")
    category: str = Field(min_length=1)
    url: HttpUrl
    output: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*\.json$")
    verification_status: VerificationStatus = VerificationStatus.SOURCE_ONLY
    collect: bool = True


class MergedCell(StrictModel):
    """源表格中跨越多个字段的单元格。"""

    row_index: int = Field(ge=2)
    start_header: str
    end_header: str
    value: str


class ExtractedTable(StrictModel):
    """保留来源字段名称的单个表格。"""

    section: str
    headers: list[str]
    rows: list[dict[str, str]]
    merged_cells: list[MergedCell] = Field(default_factory=list)


class CandidateSnapshot(StrictModel):
    """未通过本机 0.99 核验的资料快照。"""

    schema_version: int = 1
    game: str = "mm2r"
    target_version: str = "0.99"
    source_id: str
    target_id: str
    source_url: HttpUrl
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    license: str
    verification_status: VerificationStatus
    tables: list[ExtractedTable]
    excerpts: list[str]
    warnings: list[str]

    @model_validator(mode="after")
    def reject_unverified_promotion(self) -> CandidateSnapshot:
        """候选数据不得直接声明为本机版本已验证。"""
        if self.verification_status is VerificationStatus.VERIFIED_0_99:
            raise ValueError("candidate snapshot cannot be verified_0_99")
        return self


class CollectedTarget(StrictModel):
    """成功采集目标的数量摘要。"""

    target_id: str
    output: str
    table_count: int = Field(ge=1)
    row_count: int = Field(ge=1)


class FailedTarget(StrictModel):
    """预期采集失败及其上下文。"""

    target_id: str
    url: HttpUrl
    error: str


class CollectionReport(StrictModel):
    """一次串行采集运行的完整摘要。"""

    schema_version: int = 1
    generated_at: datetime
    collected: list[CollectedTarget]
    skipped: list[str]
    failed: list[FailedTarget]
