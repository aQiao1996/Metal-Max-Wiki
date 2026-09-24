"""图片资产的权利、来源与本地锁定契约。"""

import ipaddress
import posixpath
import re
import unicodedata
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

import idna
from pydantic import Field, HttpUrl, field_validator, model_validator

from mmwiki_data.models import StrictModel

_ENTITY_REF_PATTERN = re.compile(r"^[a-z0-9-]+-[0-9a-f]{10}$")
_HOST_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_RASTER_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})
_ORIGINAL_SUFFIXES = _RASTER_SUFFIXES | {".svg"}
_DANGEROUS_SUFFIXES = frozenset(
    {
        "app",
        "bat",
        "cmd",
        "com",
        "cpl",
        "dll",
        "dmg",
        "exe",
        "hta",
        "jar",
        "js",
        "jse",
        "lnk",
        "msi",
        "pif",
        "pkg",
        "ps1",
        "psm1",
        "py",
        "pyw",
        "rb",
        "reg",
        "scr",
        "sh",
        "command",
        "desktop",
        "php",
        "pl",
        "apk",
        "vbe",
        "vbs",
        "wsf",
        "wsh",
    }
)
_WINDOWS_DEVICE_NAMES = frozenset({"aux", "clock$", "con", "nul", "prn"})
_LICENSE_PLACEHOLDERS = frozenset(
    {
        "na",
        "noassertion",
        "nolicense",
        "none",
        "notapplicable",
        "permissionpending",
        "tbd",
        "tobedetermined",
        "unknown",
        "unknownlicense",
        "unspecified",
    }
)
_MEDIA_TYPE_SUFFIXES: dict[str, frozenset[str]] = {
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpeg", ".jpg"}),
    "image/webp": frozenset({".webp"}),
    "image/svg+xml": frozenset({".svg"}),
}


class RightsStatus(StrEnum):
    """图片在本项目中的可用状态。"""

    REUSABLE = "reusable"
    USER_CAPTURE = "user_capture"
    ORIGINAL_DIAGRAM = "original_diagram"
    PERMISSION_NEEDED = "permission_needed"
    REFERENCE_ONLY = "reference_only"
    REJECTED = "rejected"


class LicenseBasis(StrEnum):
    """资产可保存的明确权利依据。"""

    STANDARD = "standard"
    WRITTEN_PERMISSION = "written_permission"
    SELF_CREATED = "self_created"
    INVALID = "invalid"


def _validate_local_path(path: str, *, suffixes: frozenset[str]) -> str:
    """校验资产目录内的安全相对路径。"""
    normalized_path = unicodedata.normalize("NFKC", path)
    if (
        not path
        or path != path.strip()
        or "%" in normalized_path
        or "\\" in normalized_path
        or any(character in normalized_path for character in '<>:"|?*')
        or any(unicodedata.category(character) in {"Cc", "Cf"} for character in normalized_path)
    ):
        raise ValueError("local path must be a safe relative path under files")
    raw_parts = path.split("/")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or len(raw_parts) < 2
        or raw_parts[0] != "files"
        or any(not part or part in {".", ".."} for part in raw_parts)
        or parsed.as_posix() != path
        or posixpath.normpath(normalized_path) != normalized_path
        or parsed.suffix.lower() not in suffixes
    ):
        raise ValueError("local path must be a safe relative path under files")
    normalized_parts = normalized_path.split("/")
    for part in normalized_parts:
        folded_part = part.casefold()
        if (
            not part
            or part != part.strip()
            or part.startswith(".")
            or part.endswith(".")
            or ":" in part
        ):
            raise ValueError("local path must not contain hidden or unsafe components")
        name_tokens = folded_part.split(".")
        if any(token != token.strip() for token in name_tokens):
            raise ValueError("local path must not contain ambiguous extension whitespace")
        device_name = name_tokens[0]
        if device_name in _WINDOWS_DEVICE_NAMES or re.fullmatch(r"(?:com|lpt)[1-9]", device_name):
            raise ValueError("local path must not contain Windows device names")
        suffix_tokens = name_tokens[1:]
        if any(token in _DANGEROUS_SUFFIXES for token in suffix_tokens):
            raise ValueError("local path must not contain executable extensions")
    return path


def _path_collision_key(path: str) -> str:
    """以跨平台规则生成路径唯一性键。"""
    normalized = unicodedata.normalize("NFKC", path).casefold()
    return posixpath.normpath(normalized)


def _classify_license(value: str) -> LicenseBasis:
    """以保守白名单识别标准许可、书面授权或自有创作。"""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = re.sub(r"[^a-z0-9]+", "", normalized)
    semantic = "".join(character for character in normalized if character.isalnum())
    normalized_text = " ".join(normalized.split())
    canonical = re.sub(r"[ -]+", "-", normalized_text)
    chinese_denials = (
        "授权待定",
        "待授权",
        "未授权",
        "未知",
        "暂无",
        "不详",
        "版权所有",
        "专有",
        "禁止转载",
        "不可转载",
        "不可复用",
        "禁止复用",
        "版权归作者所有",
        "版权归原作者所有",
        "保留所有权利",
        "禁止复制",
        "不得复制",
        "禁止使用",
        "不得使用",
        "不得转载",
    )
    english_denials = (
        "allrightsbelong",
        "allrightsreserved",
        "copyrightowner",
        "donotredistribute",
        "licencerevoked",
        "licenserevoked",
        "noredistribution",
        "noassertion",
        "nopermission",
        "notlicensed",
        "notpermitted",
        "pending",
        "permissiondenied",
        "permissionnotgranted",
        "proprietary",
        "tobedetermined",
        "unauthorised",
        "unauthorized",
        "unlicensed",
        "unknown",
        "unspecified",
    )
    if (
        not semantic
        or compact in _LICENSE_PLACEHOLDERS
        or compact.startswith("tbd")
        or semantic == "无"
        or any(marker in compact for marker in english_denials)
        or any(marker in semantic for marker in chinese_denials)
        or "?" in normalized_text
        or re.search(
            r"\b(?:maybe|perhaps|possibly|unconfirmed)\b|"
            r"\bto\s+(?:be\s+)?confirm(?:ed)?\b",
            normalized_text,
        )
        or any(marker in normalized_text for marker in ("可能", "也许", "待确认", "未确认", "疑似"))
        or re.search(
            r"未经(?:许可|授权)不得(?:转载|复制|使用|传播|改编|商业使用)",
            semantic,
        )
        or re.search(r"版权归.{0,64}所有", semantic)
    ):
        return LicenseBasis.INVALID

    standard_patterns = (
        r"cc0(?:-1\.0)?",
        r"cc-(?:by|by-nc|by-nd|by-sa|by-nc-nd|by-nc-sa)-(?:1\.0|2\.0|2\.5|3\.0|4\.0)",
        r"mit(?:-license)?",
        r"apache(?:-license)?-2\.0",
        r"bsd-(?:2|3)-clause(?:-license)?",
        r"(?:mpl|mozilla-public-license)-2\.0",
        r"(?:gnu-)?(?:gpl|lgpl|agpl)-?v?(?:1|2|3)(?:\.[01])?(?:-(?:only|or-later))?",
        r"isc(?:-license)?",
        r"(?:the-)?unlicense",
        r"public-domain",
    )
    if re.fullmatch(r"[a-z0-9 .-]+", normalized_text) and any(
        re.fullmatch(pattern, canonical) for pattern in standard_patterns
    ):
        return LicenseBasis.STANDARD

    written_permission_patterns = (
        r"permission (?:is )?granted(?: for (?:reuse|use|this project))?",
        r"authori[sz]ed for reuse",
        r"licensed for reuse",
        r"custom license with page evidence",
        r"user-owned-with-project-permission",
    )
    written_permission_values = frozenset(
        {
            "已获授权本项目使用",
            "作者授权本项目使用",
            "允许本项目复用",
            "授权本项目使用",
        }
    )
    if (
        any(re.fullmatch(pattern, normalized_text) for pattern in written_permission_patterns)
        or normalized_text in written_permission_values
    ):
        return LicenseBasis.WRITTEN_PERMISSION

    self_created_values = frozenset(
        {
            "self-created",
            "self created",
            "user-created",
            "user created",
            "project-original",
            "project original",
            "本人拍摄",
            "本人原创",
            "项目原创",
        }
    )
    if normalized_text in self_created_values:
        return LicenseBasis.SELF_CREATED
    return LicenseBasis.INVALID


def _is_meaningful_author(value: str) -> bool:
    """判断作者或站点署名是否可用于归属。"""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = re.sub(r"[^a-z0-9]+", "", normalized)
    semantic = "".join(character for character in normalized if character.isalnum())
    return (
        bool(semantic)
        and compact not in {"anonymous", "na", "none", "tbd", "unknown"}
        and "anonymous" not in compact
        and "unknown" not in compact
        and not compact.startswith("tbd")
        and semantic != "无"
        and not any(marker in semantic for marker in ("作者不明", "未知", "暂无", "不详"))
    )


def _normalize_public_host(value: str, *, label: str) -> str:
    """将公网域名规范为小写 IDNA，并拒绝本地与 IP 形式。"""
    candidate = value.strip()
    if not candidate or candidate.endswith("."):
        raise ValueError(f"{label} must be a public multi-label hostname")
    ip_candidate = (
        candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    )
    try:
        ipaddress.ip_address(ip_candidate)
    except ValueError:
        pass
    else:
        raise ValueError(f"{label} cannot be an IP literal")
    try:
        candidate = idna.encode(
            candidate,
            uts46=True,
            transitional=False,
            std3_rules=True,
        ).decode("ascii")
    except idna.IDNAError as error:
        raise ValueError(f"{label} must be a valid IDNA hostname") from error
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        raise ValueError(f"{label} cannot be an IP literal")
    if (
        candidate == "localhost"
        or candidate.endswith(".localhost")
        or candidate.endswith(".local")
        or candidate.endswith(".localdomain")
        or "." not in candidate
    ):
        raise ValueError(f"{label} must be a public multi-label hostname")
    if not _HOST_PATTERN.fullmatch(candidate):
        raise ValueError(f"{label} must be a valid hostname")
    return candidate


def _validate_public_url(url: HttpUrl, *, label: str) -> None:
    """拒绝会模糊远程资产边界的 URL 形式。"""
    if url.username is not None or url.password is not None:
        raise ValueError(f"{label} URL cannot contain userinfo")
    if url.fragment is not None:
        raise ValueError(f"{label} URL cannot contain a fragment")
    if url.host is None:
        raise ValueError(f"{label} URL requires a host")
    _normalize_public_host(url.host, label=f"{label} URL host")


def _normalize_redirect_host(value: str) -> str:
    """校验并规范重定向域名。"""
    stripped = value.strip()
    if (
        not stripped
        or stripped != value
        or "://" in stripped
        or any(character in stripped for character in "/:@?#[]")
    ):
        raise ValueError("redirect host must be a hostname without scheme, port, or path")
    return _normalize_public_host(stripped, label="redirect host")


class AssetEntry(StrictModel):
    """人工审核后的单个图片资产来源。"""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    kind: Literal["map", "location", "vehicle", "monster", "equipment", "ui", "guide"]
    title: str = Field(min_length=1)
    source_page_url: HttpUrl | None = None
    source_image_url: HttpUrl | None = None
    author: str = Field(min_length=1)
    license: str = Field(min_length=1)
    rights_status: RightsStatus
    version_scope: list[str]
    entity_refs: list[str] = Field(default_factory=list)
    local_path: str | None = None
    allowed_redirect_hosts: list[str] = Field(default_factory=list)
    alt: str = Field(min_length=1)
    notes: str = ""

    @field_validator("title", "author", "license", "alt", "notes")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """去除文本边界空白以保持输出稳定。"""
        return value.strip()

    @model_validator(mode="after")
    def validate_rights_and_structure(self) -> AssetEntry:
        """校验权利状态与来源、本地文件的组合。"""
        if not self.title:
            raise ValueError("title cannot be blank")
        if not self.author or not _is_meaningful_author(self.author):
            raise ValueError("author attribution must identify an author or site")
        if not self.license:
            raise ValueError("license cannot be blank")
        if not self.alt:
            raise ValueError("alt text cannot be blank")
        if self.source_page_url is not None:
            _validate_public_url(self.source_page_url, label="source page")
        if self.source_image_url is not None:
            _validate_public_url(self.source_image_url, label="source image")

        version_scope = [value.strip() for value in self.version_scope]
        if not version_scope or any(not value for value in version_scope):
            raise ValueError("version scope cannot contain blank values")
        self.version_scope = sorted(set(version_scope))

        entity_refs = [value.strip() for value in self.entity_refs]
        if any(not _ENTITY_REF_PATTERN.fullmatch(value) for value in entity_refs):
            raise ValueError("entity ref must use a normalized record id")
        self.entity_refs = sorted(set(entity_refs))

        redirect_hosts = [_normalize_redirect_host(value) for value in self.allowed_redirect_hosts]
        self.allowed_redirect_hosts = sorted(set(redirect_hosts))

        if self.rights_status is RightsStatus.REUSABLE:
            self._validate_reusable()
        elif self.rights_status is RightsStatus.USER_CAPTURE:
            self._validate_local_creation(_RASTER_SUFFIXES, "user capture")
        elif self.rights_status is RightsStatus.ORIGINAL_DIAGRAM:
            self._validate_local_creation(_ORIGINAL_SUFFIXES, "original diagram")
        else:
            self._validate_reference_state()
        return self

    def _validate_reusable(self) -> None:
        """可复用远程图必须同时具备来源、授权和本地目标。"""
        if _classify_license(self.license) not in {
            LicenseBasis.STANDARD,
            LicenseBasis.WRITTEN_PERMISSION,
        }:
            raise ValueError("reusable asset requires an explicit license")
        if self.source_page_url is None:
            raise ValueError("reusable asset requires a source page")
        if self.source_image_url is None:
            raise ValueError("reusable asset requires a source image")
        if self.source_page_url.scheme != "https" or self.source_image_url.scheme != "https":
            raise ValueError("reusable asset source URLs must use HTTPS")
        if self.local_path is None:
            raise ValueError("reusable asset requires a local file")
        self.local_path = _validate_local_path(self.local_path, suffixes=_RASTER_SUFFIXES)

    def _validate_local_creation(self, suffixes: frozenset[str], label: str) -> None:
        """用户截图与原创图只接受授权明确的本地文件。"""
        if _classify_license(self.license) is LicenseBasis.INVALID:
            raise ValueError(f"{label} requires an explicit license")
        if self.local_path is None:
            raise ValueError(f"{label} requires a local file")
        self.local_path = _validate_local_path(self.local_path, suffixes=suffixes)
        if self.source_image_url is not None:
            raise ValueError(f"{label} cannot declare a remote source image")
        if self.allowed_redirect_hosts:
            raise ValueError(f"{label} cannot declare redirect hosts")

    def _validate_reference_state(self) -> None:
        """引用、待授权和拒绝项只保留外部索引。"""
        labels = {
            RightsStatus.PERMISSION_NEEDED: "permission-needed",
            RightsStatus.REFERENCE_ONLY: "reference-only",
            RightsStatus.REJECTED: "rejected",
        }
        label = labels[self.rights_status]
        if self.local_path is not None:
            raise ValueError(f"{label} asset cannot declare local file")
        if self.allowed_redirect_hosts:
            raise ValueError(f"{label} asset cannot declare redirect hosts")
        if self.source_page_url is None:
            raise ValueError(f"{label} asset requires a source page")


class AssetManifest(StrictModel):
    """人工维护的图片资产权利清单。"""

    schema_version: Literal[1] = 1
    assets: list[AssetEntry]

    @model_validator(mode="after")
    def validate_unique_assets(self) -> AssetManifest:
        """拒绝重复标识和本地路径，并按标识排序。"""
        ids = [asset.id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate asset id")
        local_paths = [
            _path_collision_key(asset.local_path)
            for asset in self.assets
            if asset.local_path is not None
        ]
        if len(local_paths) != len(set(local_paths)):
            raise ValueError("duplicate asset local path")
        self.assets.sort(key=lambda asset: asset.id)
        return self


class LockedAsset(StrictModel):
    """已保存栅格图或本地原创 SVG 的内容指纹与尺寸。"""

    asset_id: str = Field(pattern=r"^[a-z0-9-]+$")
    final_url: HttpUrl | None
    local_path: str
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    media_type: Literal["image/png", "image/jpeg", "image/webp", "image/svg+xml"]
    byte_size: int = Field(gt=0, le=10 * 1024 * 1024)
    width: int = Field(gt=0, le=16_384)
    height: int = Field(gt=0, le=16_384)

    @model_validator(mode="after")
    def validate_locked_source(self) -> LockedAsset:
        """锁定记录只指向格式与后缀一致的安全本地图片。"""
        self.local_path = _validate_local_path(self.local_path, suffixes=_ORIGINAL_SUFFIXES)
        suffix = PurePosixPath(self.local_path).suffix.lower()
        if suffix not in _MEDIA_TYPE_SUFFIXES[self.media_type]:
            raise ValueError("locked asset format must match local path suffix")
        if self.final_url is not None:
            _validate_public_url(self.final_url, label="final")
            if self.final_url.scheme != "https":
                raise ValueError("locked asset final URL must use HTTPS")
        if self.media_type == "image/svg+xml" and self.final_url is not None:
            raise ValueError("locked SVG must be a local original without a final URL")
        return self


class AssetLock(StrictModel):
    """工具生成的本地图片锁定集。"""

    schema_version: Literal[1] = 1
    assets: list[LockedAsset]

    @model_validator(mode="after")
    def validate_unique_assets(self) -> AssetLock:
        """拒绝重复锁定项，并按资产标识排序。"""
        ids = [asset.asset_id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate locked asset id")
        local_paths = [_path_collision_key(asset.local_path) for asset in self.assets]
        if len(local_paths) != len(set(local_paths)):
            raise ValueError("duplicate locked asset local path")
        self.assets.sort(key=lambda asset: asset.asset_id)
        return self
