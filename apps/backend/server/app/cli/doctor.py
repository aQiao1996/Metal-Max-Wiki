"""只读检查本地运行所需的配置、资料、数据库和模型。"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url, text
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.repositories.equipment_repository import load_equipment

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_CLIENT_ROOT = _SERVER_ROOT.parents[1] / "frontend/client"


class _ClientSettings(BaseSettings):
    api_base_url: str = "http://127.0.0.1:8000"
    model_config = SettingsConfigDict(
        env_file=tuple(
            _CLIENT_ROOT / name
            for name in (".env", ".env.development", ".env.local", ".env.development.local")
        ),
        extra="ignore",
    )


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    action: str = ""


class _Model(BaseModel):
    id: str = Field(min_length=1)


class _Models(BaseModel):
    data: list[_Model]


async def check_database(settings: Settings) -> CheckResult:
    """确认可连接、账号表存在且迁移版本与代码一致。"""
    try:
        database_url = make_url(settings.database_url)
    except ArgumentError, ValueError:
        return CheckResult(
            "数据库", False, "DATABASE_URL 格式不正确", "按后端 .env.example 修正连接地址"
        )
    if database_url.drivername != "postgresql+psycopg":
        return CheckResult(
            "数据库", False, "数据库驱动配置不正确", "DATABASE_URL 应使用 postgresql+psycopg"
        )
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )
    try:
        async with asyncio.timeout(6), engine.connect() as connection:
            tables = await connection.execute(
                text(
                    "SELECT to_regclass('public.users'), to_regclass('public.user_sessions'), "
                    "to_regclass('public.alembic_version')"
                )
            )
            if any(value is None for value in tables.one()):
                return CheckResult(
                    "数据库",
                    False,
                    "可以连接，但账号表或迁移记录未就绪",
                    "在后端目录运行 uv run alembic upgrade head",
                )
            revisions = await connection.execute(text("SELECT version_num FROM alembic_version"))
            current = {str(row[0]) for row in revisions}
            expected = set(
                ScriptDirectory.from_config(Config(str(_SERVER_ROOT / "alembic.ini"))).get_heads()
            )
            if current != expected:
                return CheckResult(
                    "数据库",
                    False,
                    "数据库迁移版本与代码不一致",
                    "在后端目录运行 uv run alembic upgrade head",
                )
        return CheckResult("数据库", True, "连接正常，账号表与迁移版本一致")
    except SQLAlchemyError, TimeoutError:
        return CheckResult(
            "数据库",
            False,
            "无法连接本地数据库",
            "启动 Docker 和本项目 db 服务，核对 DATABASE_URL 与数据库凭据",
        )
    finally:
        await engine.dispose()


async def check_model(settings: Settings) -> CheckResult:
    """通过模型列表检查配置，不发起推理或下载模型。"""
    if not settings.ai_model.strip() or settings.ai_model == "your-installed-model":
        return CheckResult(
            "模型", False, "尚未填写实际模型名", "通过 ollama list 核对后设置后端 .env 的 AI_MODEL"
        )
    headers = {}
    if settings.ai_api_key.get_secret_value():
        headers["Authorization"] = f"Bearer {settings.ai_api_key.get_secret_value()}"
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(
                f"{settings.ai_base_url.rstrip('/')}/models", headers=headers
            )
            response.raise_for_status()
            models = _Models.model_validate_json(response.content)
    except httpx.InvalidURL:
        return CheckResult(
            "模型",
            False,
            "AI_BASE_URL 格式不正确",
            "使用兼容接口地址，例如 http://127.0.0.1:11434/v1",
        )
    except httpx.HTTPError:
        return CheckResult(
            "模型",
            False,
            "无法读取模型服务的模型列表",
            "启动 Ollama，或核对 AI_BASE_URL 与 AI_API_KEY",
        )
    except ValidationError:
        return CheckResult(
            "模型",
            False,
            "模型服务返回的列表格式不正确",
            "确认 AI_BASE_URL 指向兼容接口的 /v1 地址",
        )
    if settings.ai_model not in {model.id for model in models.data}:
        return CheckResult(
            "模型", False, "配置的模型不在服务列表中", "通过 ollama list 核对 AI_MODEL 的完整名称"
        )
    return CheckResult("模型", True, "服务可连接，配置的模型已存在")


def check_data() -> CheckResult:
    """复用业务边界校验，避免自检与实际查询采用不同契约。"""
    try:
        records = load_equipment()
    except RuntimeError:
        return CheckResult(
            "资料",
            False,
            "装备文件缺失或校验失败",
            "检查 data/interim/mm2r/0.99/equipment.json，运行 pnpm data:audit",
        )
    return CheckResult("资料", True, f"已通过校验，共 {len(records)} 条装备记录")


def check_frontend(settings: Settings) -> CheckResult:
    """确认浏览器代理与服务端请求指向本项目后端。"""
    try:
        target = urlsplit(_ClientSettings().api_base_url)
        if (
            target.scheme == "http"
            and target.hostname in {"127.0.0.1", "localhost"}
            and target.port == settings.api_port
            and target.path in {"", "/"}
            and not (target.username or target.password or target.query or target.fragment)
        ):
            return CheckResult("用户端代理", True, "代理地址与本地后端端口一致")
    except ValidationError, ValueError:
        return CheckResult(
            "用户端代理", False, "API_BASE_URL 格式不正确", "核对用户端 .env.local 的代理地址"
        )
    return CheckResult(
        "用户端代理",
        False,
        "代理地址与当前本地后端端口不一致",
        "同步前端 API_BASE_URL 与后端 API_PORT，并重启前后端",
    )


async def run_checks() -> list[CheckResult]:
    """汇总独立检查，所有失败都保留明确状态。"""
    if not (_SERVER_ROOT / ".env").is_file():
        return [
            CheckResult("配置", False, "缺少后端 .env", "先在仓库根目录运行 pnpm dev:setup"),
            check_data(),
        ]
    try:
        settings = get_settings()
    except ValidationError:
        return [
            CheckResult(
                "配置", False, "后端环境变量格式不正确", "对照 .env.example 检查字段类型和取值范围"
            )
        ]
    database, model = await asyncio.gather(check_database(settings), check_model(settings))
    return [
        CheckResult("配置", True, "后端环境变量已载入"),
        check_frontend(settings),
        check_data(),
        database,
        model,
    ]


def main() -> int:
    """打印自检结果，检查不通过时以非零状态退出。"""
    results = asyncio.run(run_checks())
    for result in results:
        print(f"[{'通过' if result.ok else '失败'}] {result.name}：{result.detail}")
        if result.action:
            print(f"       {result.action}")
    failures = sum(not result.ok for result in results)
    print(
        f"\n自检未通过：{failures} 项需要处理。"
        if failures
        else "\n基础资源已就绪，可运行 pnpm dev:all。"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
