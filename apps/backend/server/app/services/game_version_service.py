from app.schemas.game_version import GameVersionItem

_GAME_VERSIONS = (
    GameVersionItem(
        slug="mm2r-099",
        game="重装机兵2R",
        version="0.99 汉化版",
        short_label="2R / 0.99",
        status="available",
    ),
    GameVersionItem(
        slug="mm2r-nex",
        game="重装机兵2R NEX",
        version="民间改版",
        short_label="2R NEX",
        status="planned",
    ),
    GameVersionItem(
        slug="mm3",
        game="重装机兵3",
        version="版本待定",
        short_label="MM3",
        status="planned",
    ),
    GameVersionItem(
        slug="mm4",
        game="重装机兵4",
        version="版本待定",
        short_label="MM4",
        status="planned",
    ),
)


def list_game_versions() -> list[GameVersionItem]:
    """返回已开放和计划支持的游戏版本。"""

    return list(_GAME_VERSIONS)
