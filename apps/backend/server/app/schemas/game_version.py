from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GameVersionItem(BaseModel):
    """游戏版本列表项。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str
    game: str
    version: str
    short_label: str = Field(serialization_alias="shortLabel")
    status: Literal["available", "planned"]
