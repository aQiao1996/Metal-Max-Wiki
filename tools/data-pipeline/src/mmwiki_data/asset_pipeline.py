"""图片资产的安全获取、内容验证与本地一致性审计。"""

from __future__ import annotations

import fcntl
import hashlib
import io
import ipaddress
import os
import re
import shutil
import socket
import stat
import tempfile
import unicodedata
import warnings
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, NoReturn, cast
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from mmwiki_data.asset_models import (
    AssetEntry,
    AssetLock,
    AssetManifest,
    LockedAsset,
    RightsStatus,
    _normalize_public_host,
)
from mmwiki_data.normalization_models import NormalizedBundle, NormalizedRecord
from mmwiki_data.storage import sync_directory

MAX_ASSET_BYTES = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 16_384
MAX_IMAGE_PIXELS = 40_000_000
MAX_REDIRECTS = 5
MAX_SVG_ELEMENTS = 2_048
MAX_SVG_DEPTH = 32
MAX_SVG_ATTRIBUTES = 8_192
MAX_SVG_ATTRIBUTE_CHARS = 128 * 1024
MAX_SVG_ATTRIBUTE_VALUE_CHARS = 64 * 1024
MAX_SVG_TEXT_CHARS = 256 * 1024
USER_AGENT = "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

Resolver = Callable[[str], Sequence[str]]
Replace = Callable[[Path, Path], None]
ClientFactory = Callable[..., httpx.Client]
RasterMediaType = Literal["image/png", "image/jpeg", "image/webp"]

_RASTER_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_FORMAT_MEDIA_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_MEDIA_SUFFIXES = {
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/webp": frozenset({".webp"}),
}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_IGNORED_LOCAL_NAMES = frozenset({".gitkeep"})
_SVG_UNSAFE_DECLARATION = re.compile(r"<!\s*(?:doctype|entity)\b", re.IGNORECASE)
_SVG_URL = re.compile(r"url\(\s*([^)]*?)\s*\)", re.IGNORECASE)
_SVG_LENGTH = re.compile(r"^([0-9]+)\s*(?:px)?$", re.IGNORECASE)
_SVG_VIEWBOX = re.compile(
    r"^\s*([+-]?[0-9]+)(?:\s*,\s*|\s+)"
    r"([+-]?[0-9]+)(?:\s*,\s*|\s+)"
    r"([+-]?[0-9]+)(?:\s*,\s*|\s+)"
    r"([+-]?[0-9]+)\s*$"
)
_SVG_FRAGMENT = re.compile(r"^#[A-Za-z_][A-Za-z0-9_.-]*$")
_SVG_LOCAL_IRI = re.compile(r"^url\(\s*#[A-Za-z_][A-Za-z0-9_.-]*\s*\)$", re.IGNORECASE)
_SVG_ALLOWED_ELEMENTS = frozenset(
    {
        "circle",
        "clipPath",
        "defs",
        "desc",
        "ellipse",
        "g",
        "line",
        "linearGradient",
        "marker",
        "mask",
        "path",
        "polygon",
        "polyline",
        "radialGradient",
        "rect",
        "stop",
        "svg",
        "symbol",
        "text",
        "title",
        "tspan",
        "use",
    }
)
_SVG_ALLOWED_ATTRIBUTES = frozenset(
    {
        "alignment-baseline",
        "aria-describedby",
        "aria-label",
        "aria-labelledby",
        "baseline-shift",
        "class",
        "clip-path",
        "clip-rule",
        "clipPathUnits",
        "color",
        "cx",
        "cy",
        "d",
        "direction",
        "display",
        "dominant-baseline",
        "dx",
        "dy",
        "fill",
        "fill-opacity",
        "fill-rule",
        "font-family",
        "font-size",
        "font-stretch",
        "font-style",
        "font-variant",
        "font-weight",
        "fr",
        "fx",
        "fy",
        "gradientTransform",
        "gradientUnits",
        "height",
        "href",
        "id",
        "lengthAdjust",
        "letter-spacing",
        "marker-end",
        "marker-mid",
        "marker-start",
        "markerHeight",
        "markerUnits",
        "markerWidth",
        "mask",
        "maskContentUnits",
        "maskUnits",
        "offset",
        "opacity",
        "orient",
        "overflow",
        "paint-order",
        "pathLength",
        "points",
        "preserveAspectRatio",
        "r",
        "refX",
        "refY",
        "role",
        "rotate",
        "rx",
        "ry",
        "shape-rendering",
        "spreadMethod",
        "stop-color",
        "stop-opacity",
        "stroke",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-opacity",
        "stroke-width",
        "tabindex",
        "text-anchor",
        "text-decoration",
        "text-rendering",
        "textLength",
        "transform",
        "unicode-bidi",
        "vector-effect",
        "viewBox",
        "visibility",
        "width",
        "word-spacing",
        "writing-mode",
        "x",
        "x1",
        "x2",
        "y",
        "y1",
        "y2",
    }
)
_SVG_IRI_ATTRIBUTES = frozenset(
    {"clip-path", "fill", "marker-end", "marker-mid", "marker-start", "mask", "stroke"}
)
_SVG_ALLOWED_XML_ATTRIBUTES = frozenset({"lang", "space"})
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_NORMALIZED_DOMAINS = ("equipment", "items", "quests", "jobs", "skills")


class AssetPipelineError(ValueError):
    """图片清单、网络内容或本地资产不符合安全契约。"""


def _asset_root(repo_root: Path) -> Path:
    return repo_root / "data" / "raw" / "mm2r" / "0.99" / "assets"


def _create_http_client(client_factory: ClientFactory = httpx.Client) -> httpx.Client:
    """创建不读取代理、不复用跨请求连接的资产客户端。"""
    return client_factory(
        follow_redirects=False,
        timeout=30.0,
        trust_env=False,
        http2=False,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    )


@contextmanager
def _request_client(
    client: httpx.Client | None, client_factory: ClientFactory
) -> Iterator[httpx.Client]:
    """注入客户端由调用方管理；默认客户端每跳独立创建与关闭。"""
    if client is not None:
        yield client
        return

    active_client = _create_http_client(client_factory)
    try:
        yield active_client
    except BaseException as primary_error:
        try:
            active_client.close()
        except Exception as close_error:
            raise AssetPipelineError(
                f"{primary_error}; HTTP client close failure: {close_error}"
            ) from primary_error
        raise
    try:
        active_client.close()
    except Exception as close_error:
        raise AssetPipelineError(f"HTTP client close failure: {close_error}") from close_error


@contextmanager
def _asset_process_lock(
    repo_root: Path,
    *,
    shared: bool = False,
    blocking: bool = False,
) -> Iterator[None]:
    """以资产目录文件描述符协调获取与审计。"""
    asset_root = _asset_root(repo_root)
    _reject_symlink(asset_root, repo_root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(asset_root, flags)
    except OSError as error:
        raise AssetPipelineError(f"cannot open asset directory lock: {error}") from error
    operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    if not blocking:
        operation |= fcntl.LOCK_NB
    try:
        fcntl.flock(descriptor, operation)
    except BlockingIOError as error:
        close_errors: list[OSError] = []
        try:
            os.close(descriptor)
        except OSError as close_error:
            close_errors.append(close_error)
        message = "asset fetch is already running"
        if close_errors:
            message += "; lock close failures: " + "; ".join(
                str(close_error) for close_error in close_errors
            )
        raise AssetPipelineError(message) from error
    except OSError as error:
        try:
            os.close(descriptor)
        except OSError as close_error:
            raise AssetPipelineError(
                f"cannot acquire asset directory lock: {error}; lock close failure: {close_error}"
            ) from error
        raise AssetPipelineError(f"cannot acquire asset directory lock: {error}") from error

    try:
        yield
    except BaseException as primary_error:
        release_errors = _release_asset_process_lock(descriptor)
        if release_errors:
            message = f"{primary_error}; lock release failures: " + "; ".join(
                str(error) for error in release_errors
            )
            if isinstance(primary_error, AssetPipelineError):
                raise AssetPipelineError(message) from primary_error
            if isinstance(primary_error, OSError):
                raise OSError(message) from primary_error
            raise AssetPipelineError(message) from primary_error
        raise
    release_errors = _release_asset_process_lock(descriptor)
    if release_errors:
        raise AssetPipelineError(
            "lock release failures: " + "; ".join(str(error) for error in release_errors)
        )


def _release_asset_process_lock(descriptor: int) -> list[OSError]:
    """释放跨进程锁，并保留解锁与关闭的所有错误。"""
    errors: list[OSError] = []
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError as error:
        errors.append(error)
    try:
        os.close(descriptor)
    except OSError as error:
        errors.append(error)
    return errors


def _load_yaml_mapping(path: Path, *, boundary: Path) -> Mapping[str, object]:
    """读取单个 YAML 映射，并统一报告清单上下文。"""
    _reject_symlink(path, boundary)
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise AssetPipelineError(f"cannot load asset manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise AssetPipelineError(f"asset manifest must be a mapping: {path}")
    return cast(Mapping[str, object], value)


def load_asset_manifest(repo_root: Path) -> AssetManifest:
    """读取并严格验证人工维护的资产清单。"""
    path = _asset_root(repo_root) / "manifest.yaml"
    try:
        return AssetManifest.model_validate(_load_yaml_mapping(path, boundary=repo_root))
    except ValidationError as error:
        raise AssetPipelineError(f"invalid asset manifest {path}: {error}") from error


def _load_asset_lock(repo_root: Path, *, required: bool) -> AssetLock | None:
    path = _asset_root(repo_root) / "lock.json"
    try:
        path.lstat()
    except FileNotFoundError:
        if required:
            raise AssetPipelineError(f"missing asset lock: {path}") from None
        return None
    except OSError as error:
        raise AssetPipelineError(f"cannot inspect asset lock {path}: {error}") from error
    _reject_symlink(path, repo_root)
    try:
        return AssetLock.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise AssetPipelineError(f"invalid asset lock {path}: {error}") from error


def _default_resolver(host: str) -> list[str]:
    """解析主机的全部 A/AAAA 结果，供每次请求前重新校验。"""
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise AssetPipelineError(f"cannot resolve asset host {host}: {error}") from error
    return sorted({str(answer[4][0]) for answer in answers})


def _normalize_hostname(host: str) -> str:
    try:
        return _normalize_public_host(host, label="asset URL hostname")
    except ValueError as error:
        raise AssetPipelineError(f"invalid asset URL hostname: {host}") from error


def _validate_request_url(raw_url: str, *, allowed_hosts: set[str], asset_id: str) -> str:
    """校验每个初始地址和跳转地址，不信任前一跳的结论。"""
    parts = urlsplit(raw_url)
    if parts.scheme.casefold() != "https":
        raise AssetPipelineError(f"{asset_id}: asset URL must use HTTPS: {raw_url}")
    if parts.username is not None or parts.password is not None:
        raise AssetPipelineError(f"{asset_id}: asset URL cannot contain userinfo: {raw_url}")
    if "#" in raw_url:
        raise AssetPipelineError(f"{asset_id}: asset URL cannot contain a fragment: {raw_url}")
    if parts.hostname is None:
        raise AssetPipelineError(f"{asset_id}: asset URL requires a host: {raw_url}")
    try:
        _port = parts.port
    except ValueError as error:
        raise AssetPipelineError(f"{asset_id}: invalid asset URL port: {raw_url}") from error
    host = _normalize_hostname(parts.hostname)
    if host not in allowed_hosts:
        raise AssetPipelineError(f"{asset_id}: redirect host is not an allowed host: {host}")
    return host


def _validate_public_dns(
    host: str, *, resolver: Resolver, asset_id: str, url: str
) -> tuple[str, ...]:
    try:
        answers = list(resolver(host))
    except AssetPipelineError:
        raise
    except Exception as error:
        raise AssetPipelineError(f"{asset_id}: DNS resolution failed for {url}: {error}") from error
    if not answers:
        raise AssetPipelineError(f"{asset_id}: DNS returned no addresses for {url}")
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for answer in answers:
        try:
            address = ipaddress.ip_address(answer.split("%", 1)[0])
        except ValueError as error:
            raise AssetPipelineError(
                f"{asset_id}: DNS returned an invalid address for {url}: {answer}"
            ) from error
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise AssetPipelineError(
                f"{asset_id}: DNS answers must all be public for {url}: {answer}"
            )
        addresses.append(address)
    return tuple(str(address) for address in sorted(set(addresses), key=lambda item: item.packed))


def _connection_url(raw_url: str, address: str) -> str:
    """将经验证的 IP 绑定到实际连接地址。"""
    return str(httpx.URL(raw_url).copy_with(host=address))


def _host_header(raw_url: str, host: str) -> str:
    """为 IP 连接保留原始 HTTP Host。"""
    port = urlsplit(raw_url).port
    return host if port in {None, 443} else f"{host}:{port}"


def _reject_symlink(path: Path, boundary: Path) -> None:
    """拒绝边界内任意父级或目标符号链接。"""
    current = path
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            metadata = None
        except OSError as error:
            raise AssetPipelineError(f"cannot inspect asset path {current}: {error}") from error
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            raise AssetPipelineError(f"symlink is not allowed in asset paths: {current}")
        if current == boundary:
            return
        if boundary not in current.parents:
            raise AssetPipelineError(f"asset path escapes its boundary: {path}")
        current = current.parent


def _target_path(asset_root: Path, entry: AssetEntry) -> Path:
    if entry.local_path is None:
        raise AssetPipelineError(f"{entry.id}: local path is required")
    target = asset_root / PurePosixPath(entry.local_path)
    _reject_symlink(target, asset_root)
    return target


def _raise_with_cleanup_failures(
    primary_error: Exception,
    *,
    label: str,
    cleanup_errors: Sequence[OSError],
) -> NoReturn:
    """合并主失败与清理失败，避免丢失根因。"""
    message = f"{primary_error}; {label}: " + "; ".join(str(error) for error in cleanup_errors)
    if isinstance(primary_error, AssetPipelineError):
        raise AssetPipelineError(message) from primary_error
    raise OSError(message) from primary_error


def _temporary_file(parent: Path, *, prefix: str, boundary: Path) -> tuple[Path, BinaryIO]:
    _reject_symlink(parent, boundary)
    parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink(parent, boundary)
    handle = tempfile.NamedTemporaryFile(
        mode="w+b", dir=parent, prefix=prefix, suffix=".tmp", delete=False
    )
    temporary_path = Path(handle.name)
    try:
        _reject_symlink(temporary_path, boundary)
        os.fchmod(handle.fileno(), 0o644)
        return temporary_path, cast(BinaryIO, handle)
    except Exception as error:
        close_errors: list[OSError] = []
        try:
            handle.close()
        except OSError as close_error:
            close_errors.append(close_error)
        cleanup_errors = [*close_errors, *_cleanup_with_retry([temporary_path])]
        if cleanup_errors:
            _raise_with_cleanup_failures(
                error,
                label="temporary file cleanup failures",
                cleanup_errors=cleanup_errors,
            )
        raise


def _content_type(response: httpx.Response, *, asset_id: str, url: str) -> RasterMediaType:
    media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
    if media_type not in _RASTER_MEDIA_TYPES:
        raise AssetPipelineError(
            f"{asset_id}: response must be PNG, JPEG, or WebP at {url}; "
            f"Content-Type={media_type or '<missing>'}"
        )
    return cast(RasterMediaType, media_type)


def _validate_content_encoding(response: httpx.Response, *, asset_id: str, url: str) -> None:
    """拒绝会让响应字节数与哈希语义模糊的压缩编码。"""
    encoding = response.headers.get("Content-Encoding", "").strip().casefold()
    if encoding not in {"", "identity"}:
        raise AssetPipelineError(
            f"{asset_id}: Content-Encoding must be identity at {url}: {encoding}"
        )


def _stream_response(
    response: httpx.Response, destination: BinaryIO, *, asset_id: str, url: str
) -> tuple[int, str]:
    raw_length = response.headers.get("Content-Length")
    if raw_length is not None:
        try:
            declared_length = int(raw_length)
        except ValueError as error:
            raise AssetPipelineError(
                f"{asset_id}: invalid Content-Length at {url}: {raw_length!r}"
            ) from error
        if declared_length < 0 or declared_length > MAX_ASSET_BYTES:
            raise AssetPipelineError(
                f"{asset_id}: Content-Length exceeds 10 MiB at {url}: {declared_length}"
            )

    digest = hashlib.sha256()
    size = 0
    destination.seek(0)
    destination.truncate(0)
    os.fchmod(destination.fileno(), 0o644)
    for chunk in response.iter_raw():
        size += len(chunk)
        if size > MAX_ASSET_BYTES:
            raise AssetPipelineError(f"{asset_id}: response exceeds 10 MiB at {url}")
        destination.write(chunk)
        digest.update(chunk)
    destination.flush()
    os.fsync(destination.fileno())
    if size == 0:
        raise AssetPipelineError(f"{asset_id}: empty image response at {url}")
    return size, f"sha256:{digest.hexdigest()}"


def _validate_raster(
    source: Path | BinaryIO,
    *,
    expected_suffix: str,
    declared_media_type: str | None,
    asset_id: str,
) -> tuple[RasterMediaType, int, int]:
    """通过两次 Pillow 打开校验格式、完整性、帧数和像素边界。"""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            if not isinstance(source, Path):
                source.seek(0)
            with Image.open(source) as image:
                image_format = image.format
                width, height = image.size
                if getattr(image, "n_frames", 1) != 1 or getattr(image, "is_animated", False):
                    raise AssetPipelineError(f"{asset_id}: animated images are not allowed")
                image.verify()
            if not isinstance(source, Path):
                source.seek(0)
            with Image.open(source) as decoded:
                if getattr(decoded, "n_frames", 1) != 1 or getattr(decoded, "is_animated", False):
                    raise AssetPipelineError(f"{asset_id}: animated images are not allowed")
                decoded.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise AssetPipelineError(
            f"{asset_id}: image decompression bomb rejected: {error}"
        ) from error
    except AssetPipelineError:
        raise
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as error:
        raise AssetPipelineError(f"{asset_id}: invalid or truncated image: {error}") from error

    media_type = _FORMAT_MEDIA_TYPES.get(image_format or "")
    if media_type is None:
        raise AssetPipelineError(f"{asset_id}: actual image format must be PNG, JPEG, or WebP")
    if expected_suffix not in _MEDIA_SUFFIXES[media_type]:
        raise AssetPipelineError(
            f"{asset_id}: actual image format {media_type} does not match {expected_suffix}"
        )
    if declared_media_type is not None and declared_media_type != media_type:
        raise AssetPipelineError(
            f"{asset_id}: Content-Type {declared_media_type} does not match {media_type}"
        )
    if width <= 0 or height <= 0 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise AssetPipelineError(f"{asset_id}: image dimensions are outside the allowed range")
    return cast(RasterMediaType, media_type), width, height


def _verify_staged_inode(
    path: Path,
    *,
    descriptor_metadata: os.stat_result,
    boundary: Path,
    asset_id: str,
) -> None:
    """关闭下载句柄后确认提交路径仍指向原始普通文件。"""
    _reject_symlink(path, boundary)
    try:
        path_metadata = path.lstat()
    except OSError as error:
        raise AssetPipelineError(
            f"{asset_id}: cannot inspect staged image {path}: {error}"
        ) from error
    if not stat.S_ISREG(path_metadata.st_mode):
        raise AssetPipelineError(f"{asset_id}: staged image must be a regular file: {path}")
    if (path_metadata.st_dev, path_metadata.st_ino) != (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
    ):
        raise AssetPipelineError(f"{asset_id}: staged image path was replaced: {path}")


def _redirect_target(response: httpx.Response, *, asset_id: str, current_url: str) -> str:
    location = response.headers.get("Location")
    if not location:
        raise AssetPipelineError(
            f"{asset_id}: redirect response is missing Location at {current_url}"
        )
    return cast(str, urljoin(current_url, location))


def _fetch_one(
    entry: AssetEntry,
    *,
    asset_root: Path,
    client: httpx.Client | None,
    client_factory: ClientFactory,
    resolver: Resolver,
) -> tuple[Path, Path, LockedAsset]:
    if entry.source_image_url is None:
        raise AssetPipelineError(f"{entry.id}: reusable asset has no source image URL")
    target = _target_path(asset_root, entry)
    source_url = str(entry.source_image_url)
    source_host = _normalize_hostname(urlsplit(source_url).hostname or "")
    allowed_hosts = {source_host, *entry.allowed_redirect_hosts}
    current_url = source_url
    seen: set[str] = set()
    redirects = 0

    while True:
        if current_url in seen:
            raise AssetPipelineError(f"{entry.id}: redirect cycle detected at {current_url}")
        seen.add(current_url)
        request_url = current_url
        host = _validate_request_url(current_url, allowed_hosts=allowed_hosts, asset_id=entry.id)
        addresses = _validate_public_dns(
            host, resolver=resolver, asset_id=entry.id, url=current_url
        )
        connect_url = _connection_url(current_url, addresses[0])
        temporary_path: Path | None = None
        raw_handle: BinaryIO | None = None
        result: tuple[Path, Path, LockedAsset] | None = None
        try:
            with _request_client(client, client_factory) as active_client:
                with active_client.stream(
                    "GET",
                    connect_url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "image/png,image/jpeg,image/webp",
                        "Accept-Encoding": "identity",
                        "Host": _host_header(current_url, host),
                    },
                    follow_redirects=False,
                    timeout=30.0,
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        if redirects >= MAX_REDIRECTS:
                            raise AssetPipelineError(
                                f"{entry.id}: more than five redirects at {current_url}"
                            )
                        current_url = _redirect_target(
                            response, asset_id=entry.id, current_url=current_url
                        )
                        redirects += 1
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise AssetPipelineError(
                            f"{entry.id}: HTTP status {response.status_code} at {current_url}"
                        )
                    _validate_content_encoding(response, asset_id=entry.id, url=current_url)
                    declared_media_type = _content_type(
                        response, asset_id=entry.id, url=current_url
                    )
                    temporary_path, raw_handle = _temporary_file(
                        target.parent,
                        prefix=f".{target.name}.",
                        boundary=asset_root,
                    )
                    descriptor_metadata = os.fstat(raw_handle.fileno())
                    byte_size, digest = _stream_response(
                        response,
                        raw_handle,
                        asset_id=entry.id,
                        url=current_url,
                    )
                    media_type, width, height = _validate_raster(
                        raw_handle,
                        expected_suffix=target.suffix.casefold(),
                        declared_media_type=declared_media_type,
                        asset_id=entry.id,
                    )
                    raw_handle.close()
                    _verify_staged_inode(
                        temporary_path,
                        descriptor_metadata=descriptor_metadata,
                        boundary=asset_root,
                        asset_id=entry.id,
                    )
                    result = (
                        temporary_path,
                        target,
                        LockedAsset.model_validate(
                            {
                                "asset_id": entry.id,
                                "final_url": current_url,
                                "local_path": entry.local_path,
                                "sha256": digest,
                                "media_type": media_type,
                                "byte_size": byte_size,
                                "width": width,
                                "height": height,
                            }
                        ),
                    )
        except Exception as error:
            close_errors: list[OSError] = []
            if raw_handle is not None and not raw_handle.closed:
                try:
                    raw_handle.close()
                except OSError as close_error:
                    close_errors.append(close_error)
            cleanup_errors = [
                *close_errors,
                *_cleanup_with_retry([temporary_path] if temporary_path is not None else []),
            ]
            if cleanup_errors:
                _raise_with_cleanup_failures(
                    error,
                    label="temporary image cleanup failures",
                    cleanup_errors=cleanup_errors,
                )
            if isinstance(error, AssetPipelineError):
                raise
            if isinstance(error, httpx.HTTPError):
                raise AssetPipelineError(
                    f"{entry.id}: HTTP request failed at {request_url}: {error}"
                ) from error
            raise
        if result is None:
            raise AssetPipelineError(f"{entry.id}: asset request produced no result")
        return result


def _svg_dimension(value: str, *, asset_id: str) -> int:
    match = _SVG_LENGTH.fullmatch(value.strip())
    if match is None:
        raise AssetPipelineError(f"{asset_id}: SVG dimensions must use integer px values")
    numeric = int(match.group(1))
    if numeric <= 0 or numeric > MAX_IMAGE_DIMENSION:
        raise AssetPipelineError(f"{asset_id}: SVG dimensions are outside the allowed range")
    return numeric


def _parse_svg_viewbox(value: str, *, asset_id: str) -> tuple[int, int, int, int]:
    """严格解析四个整数组成的 viewBox。"""
    match = _SVG_VIEWBOX.fullmatch(value)
    if match is None:
        raise AssetPipelineError(f"{asset_id}: SVG viewBox must contain four integer values")
    origin_x, origin_y, width, height = (int(token) for token in match.groups())
    if abs(origin_x) > 2_147_483_647 or abs(origin_y) > 2_147_483_647:
        raise AssetPipelineError(f"{asset_id}: SVG viewBox origin is outside the allowed range")
    if width <= 0 or height <= 0 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise AssetPipelineError(
            f"{asset_id}: SVG viewBox dimensions are outside the allowed range"
        )
    return origin_x, origin_y, width, height


def _validate_svg_text(value: str | None, *, asset_id: str) -> None:
    """拒绝文本节点中可隐藏内容的控制与格式字符。"""
    if value is None:
        return
    for character in unicodedata.normalize("NFKC", value):
        category = unicodedata.category(character)
        if category == "Cf" or (category == "Cc" and character not in "\t\n\r"):
            raise AssetPipelineError(f"{asset_id}: SVG text contains control characters")


def _validate_svg_attribute(name: str, value: str, *, asset_id: str) -> None:
    """只允许静态属性值及严格的同文档片段引用。"""
    normalized_value = unicodedata.normalize("NFKC", value)
    if "\\" in normalized_value or any(
        unicodedata.category(character) in {"Cc", "Cf"} for character in normalized_value
    ):
        raise AssetPipelineError(
            f"{asset_id}: SVG attribute {name} contains escapes or control characters"
        )
    normalized_value = normalized_value.strip()
    compact_value = re.sub(r"\s+", "", normalized_value).casefold()
    if (
        "@import" in compact_value
        or "expression(" in compact_value
        or re.search(r"(?:javascript|data|https?):", compact_value)
        or "//" in compact_value
    ):
        raise AssetPipelineError(
            f"{asset_id}: SVG attribute {name} contains active or external content"
        )
    if name == "href" and _SVG_FRAGMENT.fullmatch(normalized_value) is None:
        raise AssetPipelineError(f"{asset_id}: SVG href must be a safe same-document fragment")
    if name == "viewBox":
        _parse_svg_viewbox(normalized_value, asset_id=asset_id)
    if _SVG_URL.search(normalized_value):
        if name not in _SVG_IRI_ATTRIBUTES or _SVG_LOCAL_IRI.fullmatch(normalized_value) is None:
            raise AssetPipelineError(
                f"{asset_id}: SVG attribute {name} has an unsafe or mixed url() value"
            )


def _split_xml_name(value: str) -> tuple[str | None, str]:
    """拆分 ElementTree 的 Clark 名称。"""
    if value.startswith("{"):
        namespace, separator, local_name = value[1:].partition("}")
        if not separator or not namespace or not local_name:
            return None, ""
        return namespace, local_name
    return None, value


def _validated_attribute_name(attribute: str, *, asset_id: str) -> str:
    """将允许的无命名空间、xlink 和 xml 属性规范为校验名称。"""
    namespace, local_name = _split_xml_name(attribute)
    if local_name.casefold().startswith("on") or local_name == "style":
        raise AssetPipelineError(f"{asset_id}: SVG active attribute {local_name} is not allowed")
    if namespace is None:
        if local_name not in _SVG_ALLOWED_ATTRIBUTES:
            raise AssetPipelineError(
                f"{asset_id}: SVG attribute {local_name or '<invalid>'} is not allowed"
            )
        return local_name
    if namespace == _XLINK_NS and local_name == "href":
        return "href"
    if namespace == _XML_NS and local_name in _SVG_ALLOWED_XML_ATTRIBUTES:
        return f"xml:{local_name}"
    raise AssetPipelineError(
        f"{asset_id}: SVG namespaced attribute {local_name or '<invalid>'} is not allowed"
    )


def _validated_element_name(tag: str, *, asset_id: str) -> str:
    """只接受 SVG 命名空间或无命名空间中的固定静态元素。"""
    namespace, local_name = _split_xml_name(tag)
    if namespace not in {None, _SVG_NS}:
        raise AssetPipelineError(f"{asset_id}: SVG element namespace is not allowed: {namespace}")
    if local_name not in _SVG_ALLOWED_ELEMENTS:
        raise AssetPipelineError(
            f"{asset_id}: SVG element {local_name or '<invalid>'} is not allowed"
        )
    return local_name


def _validate_svg(path: Path, *, asset_id: str) -> tuple[str, int, int, Literal["image/svg+xml"]]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise AssetPipelineError(f"{asset_id}: cannot read SVG {path}: {error}") from error
    if not data or len(data) > MAX_ASSET_BYTES:
        raise AssetPipelineError(f"{asset_id}: SVG size must be between 1 byte and 10 MiB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AssetPipelineError(f"{asset_id}: SVG must be UTF-8") from error
    if _SVG_UNSAFE_DECLARATION.search(text):
        raise AssetPipelineError(f"{asset_id}: SVG DOCTYPE and ENTITY are not allowed")
    try:
        if next(ElementTree.iterparse(io.StringIO(text), events=("pi",)), None) is not None:
            raise AssetPipelineError(f"{asset_id}: SVG processing instructions are not allowed")
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise AssetPipelineError(f"{asset_id}: invalid SVG XML: {error}") from error
    if _validated_element_name(root.tag, asset_id=asset_id) != "svg":
        raise AssetPipelineError(f"{asset_id}: SVG root element is required")
    element_count = 0
    attribute_count = 0
    attribute_character_count = 0
    text_count = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        element_count += 1
        attribute_count += len(element.attrib)
        for attribute, value in element.attrib.items():
            if len(value) > MAX_SVG_ATTRIBUTE_VALUE_CHARS:
                raise AssetPipelineError(
                    f"{asset_id}: SVG single attribute value exceeds "
                    f"{MAX_SVG_ATTRIBUTE_VALUE_CHARS} characters: {attribute}"
                )
            attribute_character_count += len(attribute) + len(value)
        _validate_svg_text(element.text, asset_id=asset_id)
        _validate_svg_text(element.tail, asset_id=asset_id)
        text_count += len(element.text or "") + len(element.tail or "")
        if depth > MAX_SVG_DEPTH:
            raise AssetPipelineError(f"{asset_id}: SVG nesting depth exceeds {MAX_SVG_DEPTH}")
        if element_count > MAX_SVG_ELEMENTS:
            raise AssetPipelineError(f"{asset_id}: SVG element count exceeds {MAX_SVG_ELEMENTS}")
        if attribute_count > MAX_SVG_ATTRIBUTES:
            raise AssetPipelineError(
                f"{asset_id}: SVG attribute count exceeds {MAX_SVG_ATTRIBUTES}"
            )
        if attribute_character_count > MAX_SVG_ATTRIBUTE_CHARS:
            raise AssetPipelineError(
                f"{asset_id}: SVG attribute characters exceed {MAX_SVG_ATTRIBUTE_CHARS}"
            )
        if text_count > MAX_SVG_TEXT_CHARS:
            raise AssetPipelineError(
                f"{asset_id}: SVG text exceeds {MAX_SVG_TEXT_CHARS} characters"
            )
        _validated_element_name(element.tag, asset_id=asset_id)
        for attribute, value in element.attrib.items():
            name = _validated_attribute_name(attribute, asset_id=asset_id)
            _validate_svg_attribute(name, value, asset_id=asset_id)
        children = list(element)
        stack.extend((child, depth + 1) for child in reversed(children))

    width_value = root.attrib.get("width")
    height_value = root.attrib.get("height")
    if width_value is not None and height_value is not None:
        width = _svg_dimension(width_value, asset_id=asset_id)
        height = _svg_dimension(height_value, asset_id=asset_id)
    else:
        view_box = root.attrib.get("viewBox")
        if view_box is None:
            raise AssetPipelineError(f"{asset_id}: SVG requires width/height or an integer viewBox")
        _origin_x, _origin_y, width, height = _parse_svg_viewbox(view_box, asset_id=asset_id)
    return f"sha256:{hashlib.sha256(data).hexdigest()}", width, height, "image/svg+xml"


def _permission_error(path: Path) -> str | None:
    try:
        metadata = path.lstat()
    except OSError as error:
        return f"cannot stat local asset {path}: {error}"
    if stat.S_ISLNK(metadata.st_mode):
        return f"symlink is not allowed in asset paths: {path}"
    mode = metadata.st_mode & 0o777
    if mode != 0o644:
        return f"local asset must use mode 0644: {path} has {mode:04o}"
    return None


def _local_file_metadata(path: Path, *, asset_id: str) -> os.stat_result:
    """先用 lstat 确认普通文件与体积，再进入内容解析。"""
    try:
        metadata = path.lstat()
    except OSError as error:
        raise AssetPipelineError(
            f"{asset_id}: cannot inspect local asset {path}: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode):
        raise AssetPipelineError(f"{asset_id}: symlink is not allowed: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise AssetPipelineError(f"{asset_id}: local asset must be a regular file: {path}")
    if metadata.st_size <= 0 or metadata.st_size > MAX_ASSET_BYTES:
        raise AssetPipelineError(
            f"{asset_id}: local asset size limit is 10 MiB: {metadata.st_size} bytes"
        )
    return metadata


def _lock_local_entry(asset_root: Path, entry: AssetEntry) -> LockedAsset:
    target = _target_path(asset_root, entry)
    metadata = _local_file_metadata(target, asset_id=entry.id)
    permission_error = _permission_error(target)
    if permission_error:
        raise AssetPipelineError(permission_error)
    suffix = target.suffix.casefold()
    media_type: Literal["image/png", "image/jpeg", "image/webp", "image/svg+xml"]
    if suffix == ".svg":
        if entry.rights_status is not RightsStatus.ORIGINAL_DIAGRAM:
            raise AssetPipelineError(f"{entry.id}: SVG is only allowed for original diagrams")
        digest, width, height, media_type = _validate_svg(target, asset_id=entry.id)
    else:
        media_type, width, height = _validate_raster(
            target,
            expected_suffix=suffix,
            declared_media_type=None,
            asset_id=entry.id,
        )
        digest = f"sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}"
    byte_size = metadata.st_size
    return LockedAsset.model_validate(
        {
            "asset_id": entry.id,
            "final_url": None,
            "local_path": entry.local_path,
            "sha256": digest,
            "media_type": media_type,
            "byte_size": byte_size,
            "width": width,
            "height": height,
        }
    )


def _tree_errors(asset_root: Path, manifest: AssetManifest) -> list[str]:
    files_root = asset_root / "files"
    errors: list[str] = []
    try:
        _reject_symlink(files_root, asset_root)
        files_metadata = files_root.lstat()
    except FileNotFoundError:
        errors.append(f"missing asset files directory: {files_root}")
        return errors
    except AssetPipelineError as error:
        errors.append(str(error))
        return errors
    except OSError as error:
        errors.append(f"cannot inspect asset files directory {files_root}: {error}")
        return errors
    if not stat.S_ISDIR(files_metadata.st_mode):
        errors.append(f"asset files root must be a real directory: {files_root}")
        return errors
    declared = {asset.local_path for asset in manifest.assets if asset.local_path is not None}
    try:
        paths = sorted(files_root.rglob("*"))
    except OSError as error:
        return [f"cannot enumerate asset files: {error}"]
    for path in paths:
        try:
            relative = path.relative_to(asset_root).as_posix()
            if path.is_symlink():
                errors.append(f"symlink is not allowed in asset paths: {path}")
                continue
            if path.is_dir():
                continue
            if path.name in _IGNORED_LOCAL_NAMES:
                continue
            if relative not in declared:
                errors.append(f"orphan local asset is not declared: {path}")
        except OSError as error:
            errors.append(f"cannot inspect local asset {path}: {error}")
    return errors


def _lock_difference(expected: LockedAsset, actual: LockedAsset) -> list[str]:
    expected_values = expected.model_dump(mode="json")
    actual_values = actual.model_dump(mode="json")
    return [field for field in expected_values if expected_values[field] != actual_values[field]]


def _load_normalized_record_index(
    repo_root: Path,
) -> tuple[dict[str, NormalizedRecord], list[str]]:
    """严格加载资产引用所覆盖的标准化数据。"""
    interim_root = repo_root / "data/interim/mm2r/0.99"
    records: dict[str, NormalizedRecord] = {}
    errors: list[str] = []
    for domain in _NORMALIZED_DOMAINS:
        path = interim_root / f"{domain}.json"
        try:
            _reject_symlink(path, repo_root)
            bundle = NormalizedBundle.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append(f"missing normalized bundle: {path}")
            continue
        except (AssetPipelineError, OSError, UnicodeError, ValidationError) as error:
            errors.append(f"invalid normalized bundle {path}: {error}")
            continue
        if bundle.domain != domain:
            errors.append(
                f"invalid normalized bundle {path}: domain {bundle.domain!r} "
                f"does not match {domain!r}"
            )
            continue
        for record in bundle.records:
            if record.id in records:
                errors.append(f"duplicate normalized record id across bundles: {record.id}")
                continue
            records[record.id] = record
    return records, errors


def _entity_reference_errors(
    manifest: AssetManifest, records: Mapping[str, NormalizedRecord]
) -> list[str]:
    """验证清单与标准化记录的双向资产引用。"""
    errors: list[str] = []
    manifest_by_id = {entry.id: entry for entry in manifest.assets}
    for entry in manifest.assets:
        for record_id in entry.entity_refs:
            record = records.get(record_id)
            if record is None:
                errors.append(f"{entry.id}: entity_ref does not exist: {record_id}")
            elif entry.id not in record.asset_refs:
                errors.append(
                    f"{entry.id}: entity_ref is not bidirectional with {record_id} asset_refs"
                )
    for record in records.values():
        for asset_id in record.asset_refs:
            referenced_entry = manifest_by_id.get(asset_id)
            if referenced_entry is None:
                errors.append(f"{record.id}: asset_ref does not exist in manifest: {asset_id}")
            elif record.id not in referenced_entry.entity_refs:
                errors.append(
                    f"{record.id}: asset_ref is not bidirectional with {asset_id} entity_refs"
                )
    return errors


def _audit_assets_locked(repo_root: Path) -> list[str]:
    """在调用方已持有共享锁时审计资产一致性。"""
    try:
        manifest = load_asset_manifest(repo_root)
    except (AssetPipelineError, OSError) as error:
        return [str(error)]
    records, normalized_errors = _load_normalized_record_index(repo_root)
    errors = [*normalized_errors, *_entity_reference_errors(manifest, records)]
    try:
        lock = _load_asset_lock(repo_root, required=True)
    except (AssetPipelineError, OSError) as error:
        errors.append(str(error))
        return sorted(set(errors))
    assert lock is not None
    asset_root = _asset_root(repo_root)
    errors.extend(_tree_errors(asset_root, manifest))
    lock_by_id = {asset.asset_id: asset for asset in lock.assets}
    manifest_by_id = {asset.id: asset for asset in manifest.assets}

    lock_path = asset_root / "lock.json"
    permission_error = _permission_error(lock_path)
    if permission_error:
        errors.append(permission_error)

    hashes: dict[str, str] = {}
    for lock_item in lock.assets:
        prior_id = hashes.get(lock_item.sha256)
        if prior_id is not None and prior_id != lock_item.asset_id:
            errors.append(
                f"duplicate local asset hash for {prior_id} and {lock_item.asset_id}: "
                f"{lock_item.sha256}"
            )
        hashes[lock_item.sha256] = lock_item.asset_id
        entry = manifest_by_id.get(lock_item.asset_id)
        if entry is None:
            errors.append(f"lock references unknown asset id: {lock_item.asset_id}")
        elif entry.local_path != lock_item.local_path:
            errors.append(
                f"{lock_item.asset_id}: lock local_path does not match manifest: "
                f"{lock_item.local_path}"
            )

    for entry in manifest.assets:
        locked = lock_by_id.get(entry.id)
        if entry.local_path is None:
            if locked is not None:
                errors.append(f"{entry.id}: non-local asset must not have a lock entry")
            continue
        try:
            if entry.rights_status is RightsStatus.REUSABLE:
                target = _target_path(asset_root, entry)
                metadata = _local_file_metadata(target, asset_id=entry.id)
                permission_error = _permission_error(target)
                if permission_error:
                    raise AssetPipelineError(permission_error)
                media_type, width, height = _validate_raster(
                    target,
                    expected_suffix=target.suffix.casefold(),
                    declared_media_type=None,
                    asset_id=entry.id,
                )
                if locked is None:
                    errors.append(f"{entry.id}: missing lock entry")
                    continue
                if locked.final_url is None:
                    raise AssetPipelineError(f"{entry.id}: reusable lock requires final URL")
                source_host = _normalize_hostname(
                    urlsplit(str(entry.source_image_url)).hostname or ""
                )
                _validate_request_url(
                    str(locked.final_url),
                    allowed_hosts={source_host, *entry.allowed_redirect_hosts},
                    asset_id=entry.id,
                )
                data = target.read_bytes()
                expected = LockedAsset.model_validate(
                    {
                        "asset_id": entry.id,
                        "final_url": locked.final_url,
                        "local_path": entry.local_path,
                        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
                        "media_type": media_type,
                        "byte_size": metadata.st_size,
                        "width": width,
                        "height": height,
                    }
                )
            else:
                expected = _lock_local_entry(asset_root, entry)
            if locked is None:
                errors.append(f"{entry.id}: missing lock entry")
                continue
            differences = _lock_difference(expected, locked)
            if differences:
                errors.append(f"{entry.id}: lock metadata mismatch for {', '.join(differences)}")
        except ValidationError as error:
            errors.append(f"{entry.id}: invalid audited lock metadata: {error}")
        except (AssetPipelineError, OSError) as error:
            errors.append(str(error))
    return sorted(set(errors))


def audit_assets(repo_root: Path) -> list[str]:
    """在共享锁内审计清单、锁记录与本地文件。"""
    try:
        with _asset_process_lock(repo_root, shared=True, blocking=True):
            return _audit_assets_locked(repo_root)
    except (AssetPipelineError, OSError) as error:
        return [str(error)]


def _write_lock_temp(asset_root: Path, lock: AssetLock) -> Path:
    path = asset_root / "lock.json"
    temporary_path, raw_handle = _temporary_file(
        path.parent,
        prefix=f".{path.name}.",
        boundary=asset_root,
    )
    payload = (lock.model_dump_json(indent=2) + "\n").encode("utf-8")
    try:
        raw_handle.write(payload)
        raw_handle.flush()
        os.fsync(raw_handle.fileno())
    except OSError as error:
        close_errors: list[OSError] = []
        try:
            raw_handle.close()
        except OSError as close_error:
            close_errors.append(close_error)
        cleanup_errors = [*close_errors, *_cleanup_with_retry([temporary_path])]
        if cleanup_errors:
            _raise_with_cleanup_failures(
                error,
                label="lock staging cleanup failures",
                cleanup_errors=cleanup_errors,
            )
        raise
    finally:
        if not raw_handle.closed:
            raw_handle.close()
    return temporary_path


def _backup(path: Path, *, boundary: Path) -> tuple[Path, int]:
    _reject_symlink(path, boundary)
    mode = path.stat().st_mode & 0o777
    handle = tempfile.NamedTemporaryFile(
        mode="w+b", dir=path.parent, prefix=f".{path.name}.", suffix=".bak", delete=False
    )
    backup = Path(handle.name)
    try:
        _reject_symlink(backup, boundary)
        os.fchmod(handle.fileno(), mode)
        with path.open("rb") as source:
            shutil.copyfileobj(source, handle)
        handle.flush()
        os.fsync(handle.fileno())
    except OSError as error:
        close_errors: list[OSError] = []
        try:
            handle.close()
        except OSError as close_error:
            close_errors.append(close_error)
        cleanup_errors = [*close_errors, *_cleanup_with_retry([backup])]
        if cleanup_errors:
            _raise_with_cleanup_failures(
                error,
                label="backup cleanup failures",
                cleanup_errors=cleanup_errors,
            )
        raise
    finally:
        if not handle.closed:
            handle.close()
    return backup, mode


def _cleanup(paths: Iterable[Path]) -> list[OSError]:
    errors: list[OSError] = []
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            errors.append(error)
    return errors


def _cleanup_with_retry(paths: Iterable[Path]) -> list[OSError]:
    """清理未入队的暂存文件，首次失败后重试一次。"""
    pending = list(paths)
    errors = _cleanup(pending)
    if errors:
        errors.extend(_cleanup(pending))
    return errors


def _commit_files(
    replacements: Sequence[tuple[Path, Path]], *, asset_root: Path, replace: Replace
) -> None:
    """以备份回滚处理图片与锁文件的可恢复提交失败。"""
    backups: dict[Path, Path] = {}
    original_identities: dict[Path, tuple[int, int] | None] = {}
    replaced: list[Path] = []
    primary_error: Exception | None = None
    rollback_errors: list[Exception] = []
    recovery_backups: set[Path] = set()
    try:
        for _source, target in replacements:
            _reject_symlink(target, asset_root)
            try:
                metadata = target.lstat()
            except FileNotFoundError:
                original_identities[target] = None
            else:
                original_identities[target] = (metadata.st_dev, metadata.st_ino)
                backups[target] = _backup(target, boundary=asset_root)[0]
        for source, target in replacements:
            _reject_symlink(source, asset_root)
            _reject_symlink(target, asset_root)
            replace(source, target)
            replaced.append(target)
        for directory in sorted({target.parent for _source, target in replacements}):
            sync_directory(directory)
    except Exception as error:
        primary_error = error
        rolled_back: set[Path] = set()
        for target in reversed(replaced):
            backup = backups.get(target)
            try:
                _reject_symlink(target.parent, asset_root)
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    replace(backup, target)
                rolled_back.add(target)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
                if backup is not None:
                    recovery_backups.add(backup)
        for target, original_identity in original_identities.items():
            if target in rolled_back or target in replaced:
                continue
            backup = backups.get(target)
            try:
                try:
                    metadata = target.lstat()
                except FileNotFoundError:
                    current_identity = None
                else:
                    current_identity = (metadata.st_dev, metadata.st_ino)
                if current_identity == original_identity:
                    continue
                _reject_symlink(target.parent, asset_root)
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    replace(backup, target)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
                if backup is not None:
                    recovery_backups.add(backup)
        for directory in sorted({target.parent for _source, target in replacements}):
            try:
                sync_directory(directory)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
    finally:
        cleanup_errors = _cleanup(
            [source for source, _target in replacements]
            + [backup for backup in backups.values() if backup not in recovery_backups]
        )
    if primary_error is not None:
        details = [str(primary_error)]
        if rollback_errors:
            details.append(
                "rollback failures: " + "; ".join(str(error) for error in rollback_errors)
            )
        if recovery_backups:
            details.append(
                "recovery backups: " + ", ".join(str(path) for path in sorted(recovery_backups))
            )
        if cleanup_errors:
            details.append("cleanup failures: " + "; ".join(str(error) for error in cleanup_errors))
        message = "asset batch commit failed: " + "; ".join(details)
        if isinstance(primary_error, AssetPipelineError):
            raise AssetPipelineError(message) from primary_error
        if isinstance(primary_error, OSError):
            raise OSError(message) from primary_error
        raise AssetPipelineError(message) from primary_error
    if cleanup_errors:
        raise OSError(
            "asset batch committed but cleanup failed: "
            + "; ".join(str(error) for error in cleanup_errors)
        )


def _fetch_assets_locked(
    repo_root: Path,
    *,
    client: httpx.Client | None = None,
    client_factory: ClientFactory = httpx.Client,
    resolver: Resolver = _default_resolver,
    replace: Replace = os.replace,
) -> dict[str, int]:
    """获取明确授权的远程栅格图，并批次提交图片和锁记录。"""
    manifest = load_asset_manifest(repo_root)
    asset_root = _asset_root(repo_root)
    tree_errors = _tree_errors(asset_root, manifest)
    if tree_errors:
        raise AssetPipelineError("; ".join(tree_errors))

    staged: list[tuple[Path, Path]] = []
    locked: list[LockedAsset] = []
    downloaded = 0
    local_count = 0
    primary_error: Exception | None = None
    cleanup_errors: list[OSError] = []
    try:
        for entry in manifest.assets:
            if entry.rights_status is RightsStatus.REUSABLE:
                temporary_path, target, lock_entry = _fetch_one(
                    entry,
                    asset_root=asset_root,
                    client=client,
                    client_factory=client_factory,
                    resolver=resolver,
                )
                staged.append((temporary_path, target))
                locked.append(lock_entry)
                downloaded += 1
            elif entry.rights_status in {
                RightsStatus.USER_CAPTURE,
                RightsStatus.ORIGINAL_DIAGRAM,
            }:
                locked.append(_lock_local_entry(asset_root, entry))
                local_count += 1

        hashes: dict[str, str] = {}
        for lock_entry in locked:
            prior_id = hashes.get(lock_entry.sha256)
            if prior_id is not None and prior_id != lock_entry.asset_id:
                raise AssetPipelineError(
                    f"duplicate asset content for {prior_id} and {lock_entry.asset_id}: "
                    f"{lock_entry.sha256}"
                )
            hashes[lock_entry.sha256] = lock_entry.asset_id

        lock = AssetLock(assets=locked)
        lock_path = asset_root / "lock.json"
        lock_temp = _write_lock_temp(asset_root, lock)
        staged.append((lock_temp, lock_path))
        _commit_files(staged, asset_root=asset_root, replace=replace)
        staged.clear()
    except Exception as error:
        primary_error = error
    finally:
        cleanup_errors = _cleanup(source for source, _target in staged)
    if primary_error is not None:
        details = [str(primary_error)]
        if cleanup_errors:
            details.append(
                "staging cleanup failures: " + "; ".join(str(error) for error in cleanup_errors)
            )
        message = "; ".join(details)
        if isinstance(primary_error, AssetPipelineError):
            raise AssetPipelineError(message) from primary_error
        if isinstance(primary_error, OSError):
            raise OSError(message) from primary_error
        raise AssetPipelineError(message) from primary_error
    if cleanup_errors:
        raise OSError(
            "asset staging cleanup failed: " + "; ".join(str(error) for error in cleanup_errors)
        )
    return {"downloaded": downloaded, "local": local_count, "locked": len(locked)}


def fetch_assets(
    repo_root: Path,
    *,
    client: httpx.Client | None = None,
    client_factory: ClientFactory = httpx.Client,
    resolver: Resolver = _default_resolver,
    replace: Replace = os.replace,
) -> dict[str, int]:
    """在跨进程独占锁内获取并提交资产。

    ``client`` 仅供测试注入；调用方负责其 transport 隔离与生命周期。
    """
    with _asset_process_lock(repo_root):
        return _fetch_assets_locked(
            repo_root,
            client=client,
            client_factory=client_factory,
            resolver=resolver,
            replace=replace,
        )
