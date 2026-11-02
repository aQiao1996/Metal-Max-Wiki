"""战车部件的特性说明与来源事实。"""

from typing import Literal

from pydantic import Field

from mmwiki_data.models import StrictModel
from mmwiki_data.normalization_models import SourceRef


class TraitDescription(StrictModel):
    """项目整理的特性说明，区分指令与被动效果。"""

    name: str = Field(min_length=1)
    activation: Literal["主动指令", "被动生效", "无特性", "效果待确认"]
    effect: str = Field(min_length=1)
    limits: str = Field(min_length=1)


class TraitFact(StrictModel):
    name_ja: str
    effect_ja: str
    limits_ja: str
    source_ref: SourceRef
