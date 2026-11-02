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
    content: str | None = Field(default=None, max_length=262144)


class _CompletionChoice(BaseModel):
    message: _CompletionMessage
    finish_reason: str | None = None


class _CompletionResponse(BaseModel):
    choices: list[_CompletionChoice] = Field(min_length=1)


class _OllamaResponse(BaseModel):
    message: _CompletionMessage
    done: bool
    done_reason: str | None = None
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)


async def _post[Response: BaseModel](
    url: str, payload: dict[str, object], response_type: type[Response]
) -> Response:
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
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response_type.model_validate_json(response.content)
    except httpx.TimeoutException as error:
        logger.warning("问答模型调用超时：model=%s", settings.ai_model)
        raise BusinessError(504, "模型响应超时，请稍后重试") from error
    except httpx.HTTPStatusError as error:
        logger.warning(
            "问答模型拒绝请求：model=%s status=%s", settings.ai_model, error.response.status_code
        )
        raise BusinessError(502, "模型服务拒绝了请求，请检查模型配置和上下文预算") from error
    except httpx.HTTPError as error:
        logger.exception("问答模型调用失败：model=%s", settings.ai_model)
        raise BusinessError(502, "无法连接问答模型，请检查模型服务和配置") from error
    except ValidationError as error:
        logger.exception("问答模型返回了无效响应：model=%s", settings.ai_model)
        raise BusinessError(502, "模型返回内容不完整，请重试") from error


def _final_answer(content: str | None, finish_reason: str | None) -> str:
    settings = get_settings()
    if finish_reason == "length":
        logger.warning(
            "问答模型输出被截断：model=%s max_output_tokens=%s",
            settings.ai_model,
            settings.ai_max_output_tokens,
        )
        raise BusinessError(
            502, "模型回答达到输出长度限制，未返回完整答案；请缩小问题范围或提高输出预算"
        )
    if finish_reason != "stop":
        logger.warning(
            "问答模型未正常完成：model=%s finish_reason=%s", settings.ai_model, finish_reason
        )
        raise BusinessError(502, "模型未正常完成回答，请重试")
    answer = (content or "").strip()
    # 部分本地模型将推理区间放入正文，展示前只保留最终回答。
    reasoning = re.compile(
        r"^(?:<think>(.*?)</think>|<analysis>(.*?)</analysis>|<unused94>(.*?)<unused95>)",
        re.DOTALL | re.IGNORECASE,
    )
    while match := reasoning.match(answer):
        answer = answer[match.end() :].strip()
    if re.search(r"<unused9[45]>|</?(?:think|analysis)>|<\|[^>]*\|>", answer, re.IGNORECASE):
        raise BusinessError(502, "模型回答包含未完成的内部标记，请重试")
    if not answer:
        raise BusinessError(502, "模型未返回回答，请重试")
    return answer


class CompatibleModelProvider:
    """通过兼容接口调用本地或后续配置的在线模型。"""

    async def complete(self, messages: list[ChatMessage]) -> str:
        """只发送兼容协议参数，超时、协议错误和未完成输出明确失败。"""
        settings = get_settings()
        completion = await _post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            {
                "model": settings.ai_model,
                "messages": [message.model_dump() for message in messages],
                "stream": False,
                "temperature": 0.1,
                "max_tokens": settings.ai_max_output_tokens,
            },
            _CompletionResponse,
        )
        choice = completion.choices[0]
        return _final_answer(choice.message.content, choice.finish_reason)


class OllamaModelProvider:
    """以请求级原生选项固定上下文和输出窗口，不修改已安装模型。"""

    async def complete(self, messages: list[ChatMessage]) -> str:
        """仅显式选择 Ollama 时使用原生上下文参数，不推断 thinking 能力。"""
        settings = get_settings()
        if settings.ai_ollama_context_tokens <= settings.ai_max_output_tokens:
            raise BusinessError(503, "Ollama上下文窗口必须大于输出预算，请检查AI配置")
        base_url = settings.ai_base_url.rstrip("/").removesuffix("/v1")
        completion = await _post(
            f"{base_url}/api/chat",
            {
                "model": settings.ai_model,
                "messages": [message.model_dump() for message in messages],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": settings.ai_max_output_tokens,
                    "num_ctx": settings.ai_ollama_context_tokens,
                },
            },
            _OllamaResponse,
        )
        logger.info(
            "Ollama问答用量：prompt_tokens=%s output_tokens=%s context_tokens=%s",
            completion.prompt_eval_count,
            completion.eval_count,
            settings.ai_ollama_context_tokens,
        )
        return _final_answer(
            completion.message.content, completion.done_reason if completion.done else None
        )


def get_model_provider() -> ModelProvider:
    """业务逻辑只依赖 Provider 契约，供应商由配置显式选择。"""
    return (
        OllamaModelProvider()
        if get_settings().ai_provider == "ollama"
        else CompatibleModelProvider()
    )
