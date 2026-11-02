import logging
import re
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.errors import BusinessError

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class ModelProvider(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> str:
        """调用对话模型，返回完整文本。"""
        ...


class _CompletionMessage(BaseModel):
    content: str = Field(min_length=1, max_length=16000)


class _CompletionChoice(BaseModel):
    message: _CompletionMessage
    finish_reason: str | None = None


class _CompletionResponse(BaseModel):
    choices: list[_CompletionChoice] = Field(min_length=1)


class CompatibleModelProvider:
    """通过兼容接口调用 Ollama 或后续配置的在线模型。"""

    async def complete(self, messages: list[ChatMessage]) -> str:
        """验证模型响应，超时和上游错误保持明确失败。"""
        settings = get_settings()
        if not settings.ai_model.strip():
            raise BusinessError(503, "尚未配置问答模型，请设置 AI_MODEL")
        headers = {}
        if settings.ai_api_key.get_secret_value():
            headers["Authorization"] = f"Bearer {settings.ai_api_key.get_secret_value()}"
        try:
            async with httpx.AsyncClient(
                timeout=settings.ai_timeout_seconds, trust_env=False
            ) as client:
                response = await client.post(
                    f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": settings.ai_model,
                        "messages": [message.model_dump() for message in messages],
                        "stream": False,
                        "temperature": 0.1,
                        "max_tokens": 900,
                    },
                )
                response.raise_for_status()
                completion = _CompletionResponse.model_validate_json(response.content)
        except httpx.TimeoutException as error:
            logger.warning("问答模型调用超时：model=%s", settings.ai_model)
            raise BusinessError(504, "模型响应超时，请稍后重试") from error
        except httpx.HTTPError as error:
            logger.exception("问答模型调用失败：model=%s", settings.ai_model)
            raise BusinessError(502, "无法连接问答模型，请检查模型服务和配置") from error
        except ValidationError as error:
            logger.exception("问答模型返回了无效响应：model=%s", settings.ai_model)
            raise BusinessError(502, "模型返回内容不完整，请重试") from error
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise BusinessError(502, "回答超过长度限制，请缩小问题范围后重试")
        answer = choice.message.content.strip()
        # 部分本地模型将推理区间放入正文，展示前只保留最终回答。
        for opening, closing in (("<unused94>", "<unused95>"), ("<think>", "</think>")):
            if answer.startswith(opening):
                if closing not in answer:
                    raise BusinessError(502, "模型未返回最终回答，请重试")
                answer = answer.split(closing, 1)[1].strip()
        if re.search(r"<unused9[45]>|</?think>", answer):
            raise BusinessError(502, "模型回答包含未完成的内部标记，请重试")
        if not answer:
            raise BusinessError(502, "模型未返回回答，请重试")
        return answer


def get_model_provider() -> ModelProvider:
    """业务逻辑只依赖 Provider 契约。"""
    return CompatibleModelProvider()
