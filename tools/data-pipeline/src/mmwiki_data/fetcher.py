"""受控获取公开 HTML 页面并生成内容哈希。"""

from dataclasses import dataclass
from hashlib import sha256

import httpx


class FetchError(RuntimeError):
    """目标页面无法按采集约束获取。"""


@dataclass(frozen=True, slots=True)
class FetchResult:
    """单次页面获取结果。"""

    body: bytes
    content_hash: str


def fetch(client: httpx.Client, target_id: str, url: str) -> FetchResult:
    """获取一个 HTML 目标，失败时保留目标与地址上下文。"""
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        raise FetchError(f"{target_id}: HTTP {status} while fetching {url}") from error
    except httpx.HTTPError as error:
        raise FetchError(f"{target_id}: request failed for {url}: {error}") from error

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        raise FetchError(
            f"{target_id}: expected HTML from {url}, received {content_type or 'unknown'}"
        )

    body = response.content
    return FetchResult(body=body, content_hash=f"sha256:{sha256(body).hexdigest()}")
