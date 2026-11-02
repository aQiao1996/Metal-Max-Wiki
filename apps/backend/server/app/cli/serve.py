"""按本地配置启动后端开发服务。"""

import uvicorn

from app.core.config import get_settings


def main() -> None:
    """端口与前端代理共享配置初始化时选择的值。"""
    settings = get_settings()
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.api_port, reload=True)


if __name__ == "__main__":
    main()
