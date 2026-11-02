from typing import Literal

from pydantic import Field, field_validator

from app.schemas.base import CamelModel


class AskRequest(CamelModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value


class AnswerSource(CamelModel):
    number: int
    chunk_id: str
    title: str
    href: str
    excerpt: str
    verification_status: Literal["source_only", "compatible_candidate"]


class AnswerData(CamelModel):
    answer: str
    sources: list[AnswerSource]
    status: Literal["answered", "insufficient_evidence"]


class ModelStatus(CamelModel):
    configured: bool
    model: str
