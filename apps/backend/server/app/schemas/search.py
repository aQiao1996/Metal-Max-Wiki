from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.response import PaginationMeta


class LibrarySearchResult(CamelModel):
    id: str
    kind: Literal["entity", "guide"] = "entity"
    name: str = Field(min_length=1)
    summary: str
    aliases: list[str]
    href: str = Field(pattern=r"^/(?:wiki|guides)/[a-z0-9/-]+$")
    category_label: str
    verification_status: Literal["source_only", "compatible_candidate"]
    name_source: Literal["zh_099", "zh_09", "zh_reference", "ja"]


class LibrarySearchPage(CamelModel):
    list: list[LibrarySearchResult]
    pagination: PaginationMeta
