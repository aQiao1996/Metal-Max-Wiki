from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Python 字段使用下划线，对外使用驼峰命名。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
