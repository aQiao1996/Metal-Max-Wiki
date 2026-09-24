"""图片资产契约的行为测试。"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from mmwiki_data.asset_models import (
    AssetEntry,
    AssetLock,
    AssetManifest,
    LockedAsset,
    RightsStatus,
)


def asset_entry(**changes: object) -> dict[str, object]:
    """构造可复用的远程图片资产。"""
    value: dict[str, object] = {
        "id": "reusable-map",
        "kind": "map",
        "title": "Reusable map",
        "source_page_url": "https://example.com/guide",
        "source_image_url": "https://cdn.example.com/map.png",
        "author": "Example author",
        "license": "CC-BY-4.0",
        "rights_status": RightsStatus.REUSABLE,
        "version_scope": ["mm2r-jp"],
        "entity_refs": ["main-cannon-0123456789"],
        "local_path": "files/map.png",
        "allowed_redirect_hosts": ["images.example.com", "cdn.example.com"],
        "alt": "MM2R 地图",
        "notes": "来源页面明确标注许可。",
    }
    value.update(changes)
    return value


def locked_asset(**changes: object) -> dict[str, object]:
    """构造有效的本地图片锁定记录。"""
    value: dict[str, object] = {
        "asset_id": "reusable-map",
        "final_url": "https://cdn.example.com/map.png",
        "local_path": "files/map.png",
        "sha256": "sha256:" + "a" * 64,
        "media_type": "image/png",
        "byte_size": 128,
        "width": 32,
        "height": 24,
    }
    value.update(changes)
    return value


def test_reference_only_asset_cannot_have_local_path() -> None:
    with pytest.raises(ValidationError, match="reference-only asset cannot declare local file"):
        AssetEntry.model_validate(
            asset_entry(
                rights_status=RightsStatus.REFERENCE_ONLY,
                license="NOASSERTION",
            )
        )


def test_rejected_and_permission_needed_assets_cannot_have_local_path() -> None:
    for status in (RightsStatus.REJECTED, RightsStatus.PERMISSION_NEEDED):
        with pytest.raises(ValidationError, match="cannot declare local file"):
            AssetEntry.model_validate(asset_entry(rights_status=status, license="NOASSERTION"))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"license": "NOASSERTION"}, "explicit license"),
        ({"license": "no assertion provided"}, "explicit license"),
        ({"license": "unknown license"}, "explicit license"),
        ({"license": "permission pending"}, "explicit license"),
        ({"license": "unspecified license"}, "explicit license"),
        ({"license": "TBD later"}, "explicit license"),
        ({"license": "N/A"}, "explicit license"),
        ({"license": "to be determined"}, "explicit license"),
        ({"license": "授权待定"}, "explicit license"),
        ({"license": "待授权"}, "explicit license"),
        ({"license": "未知"}, "explicit license"),
        ({"license": "无"}, "explicit license"),
        ({"license": "暂无"}, "explicit license"),
        ({"license": "不详"}, "explicit license"),
        ({"license": "All rights reserved"}, "explicit license"),
        ({"license": "版权所有"}, "explicit license"),
        ({"license": "Proprietary"}, "explicit license"),
        ({"license": "专有"}, "explicit license"),
        ({"license": "not licensed for reuse"}, "explicit license"),
        ({"license": "permission denied"}, "explicit license"),
        ({"license": "no permission granted"}, "explicit license"),
        ({"license": "do not redistribute"}, "explicit license"),
        ({"license": "未授权"}, "explicit license"),
        ({"license": "禁止转载"}, "explicit license"),
        ({"license": "不可复用"}, "explicit license"),
        ({"license": "版权归作者所有"}, "explicit license"),
        ({"license": "版权归原作者所有"}, "explicit license"),
        ({"license": "保留所有权利"}, "explicit license"),
        ({"license": "未经许可不得转载"}, "explicit license"),
        ({"license": "未经授权不得复制"}, "explicit license"),
        ({"license": "——"}, "explicit license"),
        ({"license": "🎮"}, "explicit license"),
        ({"source_page_url": None}, "source page"),
        ({"source_image_url": None}, "source image"),
        ({"local_path": None}, "local file"),
        ({"author": "  "}, "author"),
        ({"source_image_url": "http://example.com/map.png"}, "HTTPS"),
    ],
)
def test_reusable_remote_asset_requires_attribution_sources_and_path(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        AssetEntry.model_validate(asset_entry(**changes))


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/map.png",
        "../map.png",
        "files/../map.png",
        "files\\..\\map.png",
        "other/map.png",
        "files/map.exe",
        "files/map.html",
        "files/map.svg",
    ],
)
def test_remote_raster_path_must_be_safe(path: str) -> None:
    with pytest.raises(ValidationError, match="local path"):
        AssetEntry.model_validate(asset_entry(local_path=path))


@pytest.mark.parametrize(
    "path",
    [
        "files/map%2e%2e.png",
        "files/.hidden/map.png",
        "files/map/.hidden.png",
        "files/CON.png",
        "files/sub/prn.png",
        "files/COM1.webp",
        "files/LPT9/map.png",
        "files/map:stream.png",
        "files/map.exe.png",
        "files/map.exe .png",
        "files/map.cmd.webp",
        "files/sub.sh/map.png",
        "files/map\x01.png",
        "files/map\u202e.png",
    ],
)
def test_local_path_rejects_cross_platform_and_disguised_file_probes(path: str) -> None:
    with pytest.raises(ValidationError, match="local path"):
        AssetEntry.model_validate(asset_entry(local_path=path))


@pytest.mark.parametrize(
    "path",
    [
        "files/map％.png",
        "files/map＜name.png",
        "files/map＞name.png",
        'files/map"name.png',
        "files/map|name.png",
        "files/map?name.png",
        "files/map*name.png",
        "files/map.py.png",
        "files/map.pyw.png",
        "files/map.command.png",
        "files/map.desktop.png",
        "files/map.php.png",
        "files/map.pl.png",
        "files/map.rb.png",
        "files/map.app.png",
        "files/map.apk.png",
        "files/map.msi.png",
        "files/map.dmg.png",
        "files/map.pkg.png",
    ],
)
def test_local_path_rejects_nfkc_and_additional_script_probes(path: str) -> None:
    with pytest.raises(ValidationError, match="local path"):
        AssetEntry.model_validate(asset_entry(local_path=path))


def test_original_diagram_accepts_safe_svg_but_rejects_executable_path() -> None:
    diagram = AssetEntry.model_validate(
        asset_entry(
            id="original-map",
            source_page_url=None,
            source_image_url=None,
            author="Metal Max Wiki",
            license="CC-BY-NC-SA-4.0",
            rights_status=RightsStatus.ORIGINAL_DIAGRAM,
            local_path="files/original-map.svg",
            allowed_redirect_hosts=[],
        )
    )

    assert diagram.local_path == "files/original-map.svg"
    with pytest.raises(ValidationError, match="local path"):
        AssetEntry.model_validate(
            asset_entry(
                id="original-map",
                source_page_url=None,
                source_image_url=None,
                rights_status=RightsStatus.ORIGINAL_DIAGRAM,
                local_path="files/original-map.js",
                allowed_redirect_hosts=[],
            )
        )


def test_user_capture_requires_explicit_license_and_local_raster() -> None:
    capture = AssetEntry.model_validate(
        asset_entry(
            id="user-capture",
            source_page_url=None,
            source_image_url=None,
            author="用户",
            license="user-owned-with-project-permission",
            rights_status=RightsStatus.USER_CAPTURE,
            local_path="files/user-capture.webp",
            allowed_redirect_hosts=[],
        )
    )

    assert capture.source_image_url is None
    with pytest.raises(ValidationError, match="explicit license"):
        AssetEntry.model_validate(
            asset_entry(
                id="user-capture",
                source_page_url=None,
                source_image_url=None,
                author="用户",
                license="NOASSERTION",
                rights_status=RightsStatus.USER_CAPTURE,
                local_path="files/user-capture.png",
                allowed_redirect_hosts=[],
            )
        )


@pytest.mark.parametrize(
    "license_name",
    [
        "CC0 1.0",
        "CC BY 4.0",
        "CC BY-NC 4.0",
        "CC-BY-NC-SA-3.0",
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "MPL-2.0",
        "GPL-3.0-only",
        "GPLv3",
        "GNU GPL v3",
        "LGPL-2.1-or-later",
        "AGPL-3.0",
        "ISC",
        "Unlicense",
        "Public Domain",
        "permission granted for reuse",
        "authorized for reuse",
        "licensed for reuse",
        "custom license with page evidence",
        "已获授权本项目使用",
        "作者授权本项目使用",
        "授权本项目使用",
        "允许本项目复用",
    ],
)
def test_reusable_asset_accepts_explicit_license_evidence(license_name: str) -> None:
    entry = AssetEntry.model_validate(asset_entry(license=license_name))

    assert entry.license == license_name


@pytest.mark.parametrize(
    "license_name",
    [
        "foo",
        "unauthorized",
        "unauthorised",
        "not permitted",
        "permission not granted",
        "license revoked",
        "no redistribution",
        "CC BY 4.0; no redistribution",
        "禁止复制",
        "不得转载",
        "禁止使用",
        "copyright owner",
        "all rights belong to author",
        "GPL",
        "未获授权本项目使用",
        "没有允许复用",
        "作者不允许复用",
        "仅供查看，允许复用吗",
        "已获授权但随后撤销",
        "permission granted?",
        "authorized for reuse?",
        "licensed for reuse?",
        "CC BY 4.0?",
        "MIT?",
        "MIT!",
        "CC BY 4.0,",
        "permission granted.",
        "maybe MIT",
        "perhaps CC BY 4.0",
        "possibly Apache-2.0",
        "unconfirmed MIT",
        "license to confirm",
        "license to be confirmed",
        "可能是 CC BY 4.0",
        "也许已获授权本项目使用",
        "待确认 MIT",
        "未确认 CC BY 4.0",
        "疑似授权本项目使用",
    ],
)
def test_reusable_asset_rejects_unknown_or_conflicting_license_claims(
    license_name: str,
) -> None:
    with pytest.raises(ValidationError, match="explicit license"):
        AssetEntry.model_validate(asset_entry(license=license_name))


@pytest.mark.parametrize(
    "license_name",
    [
        "self-created",
        "project-original",
        "user-owned-with-project-permission",
        "本人拍摄",
        "本人原创",
        "项目原创",
    ],
)
def test_local_creation_accepts_explicit_self_created_basis(license_name: str) -> None:
    entry = AssetEntry.model_validate(
        asset_entry(
            id="user-capture",
            source_page_url=None,
            source_image_url=None,
            author="用户",
            license=license_name,
            rights_status=RightsStatus.USER_CAPTURE,
            local_path="files/user-capture.png",
            allowed_redirect_hosts=[],
        )
    )

    assert entry.license == license_name


@pytest.mark.parametrize(
    "license_name",
    [
        "非本人拍摄",
        "不是项目原创",
        "冒充项目原创",
        "project original?",
        "self-created?",
        "project-original!",
        "项目原创？",
        "本人拍摄?",
        "项目原创。",
    ],
)
def test_local_creation_rejects_negated_or_qualified_self_created_claims(
    license_name: str,
) -> None:
    with pytest.raises(ValidationError, match="explicit license"):
        AssetEntry.model_validate(
            asset_entry(
                id="user-capture",
                source_page_url=None,
                source_image_url=None,
                author="用户",
                license=license_name,
                rights_status=RightsStatus.USER_CAPTURE,
                local_path="files/user-capture.png",
                allowed_redirect_hosts=[],
            )
        )


def test_license_denial_markers_do_not_reject_a_meaningful_author_name() -> None:
    entry = AssetEntry.model_validate(asset_entry(author="版权所有者攻略组"))

    assert entry.author == "版权所有者攻略组"


@pytest.mark.parametrize(
    "author",
    [
        "unknown",
        "N/A",
        "TBD",
        "anonymous",
        "作者不明",
        "未知",
        "暂无",
        "不详",
        "无",
        "——",
        "🎮",
    ],
)
def test_asset_entry_rejects_placeholder_or_symbol_only_author(author: str) -> None:
    with pytest.raises(ValidationError, match="author attribution"):
        AssetEntry.model_validate(asset_entry(author=author))


@pytest.mark.parametrize(
    ("field", "url"),
    [
        ("source_page_url", "https://user:pass@example.com/guide"),
        ("source_page_url", "https://example.com/guide#section"),
        ("source_page_url", "https://localhost/guide"),
        ("source_page_url", "https://foo.localhost/guide"),
        ("source_page_url", "https://localhost.localdomain/guide"),
        ("source_page_url", "https://api.localhost.localdomain/guide"),
        ("source_page_url", "https://printer.local/guide"),
        ("source_page_url", "https://example/guide"),
        ("source_page_url", "https://127.0.0.1/guide"),
        ("source_image_url", "https://[::1]/map.png"),
    ],
)
def test_asset_urls_reject_credentials_fragments_and_private_host_forms(
    field: str, url: str
) -> None:
    with pytest.raises(ValidationError, match="URL"):
        AssetEntry.model_validate(asset_entry(**{field: url}))


def test_asset_entry_normalizes_ordered_collections_and_text() -> None:
    entry = AssetEntry.model_validate(
        asset_entry(
            title="  Reusable map  ",
            version_scope=["zh-patch-0.99", "mm2r-jp", "zh-patch-0.99"],
            entity_refs=["vehicle-abcdef0123", "main-cannon-0123456789"],
            allowed_redirect_hosts=[
                "CDN.EXAMPLE.COM",
                "images.example.com",
                "cdn.example.com",
                "例子.测试",
            ],
            alt="  MM2R 地图  ",
            notes="  已核对授权。  ",
        )
    )

    assert entry.title == "Reusable map"
    assert entry.version_scope == ["mm2r-jp", "zh-patch-0.99"]
    assert entry.entity_refs == ["main-cannon-0123456789", "vehicle-abcdef0123"]
    assert entry.allowed_redirect_hosts == [
        "cdn.example.com",
        "images.example.com",
        "xn--fsqu00a.xn--0zwm56d",
    ]
    assert entry.alt == "MM2R 地图"
    assert entry.notes == "已核对授权。"


def test_asset_hosts_use_nontransitional_uts46_identity() -> None:
    entry = AssetEntry.model_validate(
        asset_entry(
            source_page_url="https://faß.de/guide",
            source_image_url="https://faß.de/map.png",
            allowed_redirect_hosts=["faß.de", "xn--fa-hia.de"],
        )
    )

    assert entry.source_page_url is not None
    assert entry.source_image_url is not None
    assert entry.source_page_url.host == "xn--fa-hia.de"
    assert entry.source_image_url.host == "xn--fa-hia.de"
    assert entry.allowed_redirect_hosts == ["xn--fa-hia.de"]


@pytest.mark.parametrize(
    "host",
    [
        "１２７．０．０．１",
        "127。0。0。1",
        "：：１",
        "：：ffff：１２７．０．０．１",
    ],
)
def test_redirect_host_rejects_unicode_forms_that_map_to_ip_literals(host: str) -> None:
    with pytest.raises(ValidationError, match="redirect host"):
        AssetEntry.model_validate(asset_entry(allowed_redirect_hosts=[host]))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"version_scope": []}, "version scope"),
        ({"version_scope": [" "]}, "version scope"),
        ({"entity_refs": ["not-a-record-id"]}, "entity ref"),
        ({"allowed_redirect_hosts": ["https://cdn.example.com"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["cdn.example.com/path"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["localhost"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["foo.localhost"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["localhost.localdomain"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["printer.local"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["example"]}, "redirect host"),
        ({"allowed_redirect_hosts": ["127.0.0.1"]}, "redirect host"),
        ({"alt": "  "}, "alt"),
    ],
)
def test_asset_entry_rejects_invalid_structural_values(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        AssetEntry.model_validate(asset_entry(**changes))


def test_asset_entry_rejects_unknown_rights_state() -> None:
    with pytest.raises(ValidationError):
        AssetEntry.model_validate(asset_entry(rights_status="free-to-use"))


def test_manifest_rejects_duplicate_ids_and_local_paths() -> None:
    with pytest.raises(ValidationError, match="duplicate asset id"):
        AssetManifest.model_validate({"assets": [asset_entry(), asset_entry(title="Duplicate ID")]})
    with pytest.raises(ValidationError, match="duplicate asset local path"):
        AssetManifest.model_validate(
            {
                "assets": [
                    asset_entry(),
                    asset_entry(id="second-map", title="Second map"),
                ]
            }
        )


def test_manifest_sorts_assets_by_id() -> None:
    manifest = AssetManifest.model_validate(
        {
            "assets": [
                asset_entry(id="z-map", local_path="files/z-map.png"),
                asset_entry(id="a-map", local_path="files/a-map.png"),
            ]
        }
    )

    assert [asset.id for asset in manifest.assets] == ["a-map", "z-map"]


def test_manifest_rejects_casefolded_and_unicode_normalized_path_collisions() -> None:
    with pytest.raises(ValidationError, match="duplicate asset local path"):
        AssetManifest.model_validate(
            {
                "assets": [
                    asset_entry(id="upper-map", local_path="files/Map.png"),
                    asset_entry(id="lower-map", local_path="files/map.png"),
                ]
            }
        )
    with pytest.raises(ValidationError, match="duplicate asset local path"):
        AssetManifest.model_validate(
            {
                "assets": [
                    asset_entry(id="nfc-map", local_path="files/café.png"),
                    asset_entry(id="nfd-map", local_path="files/cafe\u0301.png"),
                ]
            }
        )


def test_locked_asset_validates_limits_and_safe_path() -> None:
    lock_entry = LockedAsset.model_validate(locked_asset())

    assert lock_entry.width == 32
    with pytest.raises(ValidationError, match="local path"):
        LockedAsset.model_validate(locked_asset(local_path="../map.png"))
    with pytest.raises(ValidationError):
        LockedAsset.model_validate(locked_asset(byte_size=10 * 1024 * 1024 + 1))
    with pytest.raises(ValidationError):
        LockedAsset.model_validate(locked_asset(width=16_385))


def test_locked_asset_supports_original_svg_and_requires_matching_format() -> None:
    locked_svg = LockedAsset.model_validate(
        locked_asset(
            asset_id="original-map",
            final_url=None,
            local_path="files/original-map.svg",
            media_type="image/svg+xml",
        )
    )

    assert locked_svg.media_type == "image/svg+xml"
    lock = AssetLock.model_validate({"assets": [locked_svg]})
    assert lock.assets[0].local_path == "files/original-map.svg"
    for local_path, media_type in (
        ("files/map.jpg", "image/png"),
        ("files/map.png", "image/jpeg"),
        ("files/map.svg", "image/webp"),
        ("files/map.png", "image/svg+xml"),
    ):
        with pytest.raises(ValidationError, match="format"):
            LockedAsset.model_validate(locked_asset(local_path=local_path, media_type=media_type))
    with pytest.raises(ValidationError, match="local original"):
        LockedAsset.model_validate(
            locked_asset(local_path="files/map.svg", media_type="image/svg+xml")
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com/map.png",
        "https://example.com/map.png#fragment",
        "https://localhost/map.png",
        "https://127.0.0.1/map.png",
    ],
)
def test_locked_asset_final_url_uses_the_same_safe_url_rules(url: str) -> None:
    with pytest.raises(ValidationError, match="URL"):
        LockedAsset.model_validate(locked_asset(final_url=url))


def test_asset_lock_rejects_duplicate_ids_and_paths_and_sorts_entries() -> None:
    with pytest.raises(ValidationError, match="duplicate locked asset id"):
        AssetLock.model_validate(
            {"assets": [locked_asset(), locked_asset(local_path="files/other.png")]}
        )
    with pytest.raises(ValidationError, match="duplicate locked asset local path"):
        AssetLock.model_validate({"assets": [locked_asset(), locked_asset(asset_id="other-map")]})

    lock = AssetLock.model_validate(
        {
            "assets": [
                locked_asset(asset_id="z-map", local_path="files/z-map.png"),
                locked_asset(asset_id="a-map", local_path="files/a-map.png"),
            ]
        }
    )
    assert [asset.asset_id for asset in lock.assets] == ["a-map", "z-map"]


def test_asset_lock_rejects_cross_platform_path_collisions() -> None:
    with pytest.raises(ValidationError, match="duplicate locked asset local path"):
        AssetLock.model_validate(
            {
                "assets": [
                    locked_asset(asset_id="upper-map", local_path="files/Map.png"),
                    locked_asset(asset_id="lower-map", local_path="files/map.png"),
                ]
            }
        )
    with pytest.raises(ValidationError, match="duplicate locked asset local path"):
        AssetLock.model_validate(
            {
                "assets": [
                    locked_asset(asset_id="nfc-map", local_path="files/café.png"),
                    locked_asset(asset_id="nfd-map", local_path="files/cafe\u0301.png"),
                ]
            }
        )


def test_repository_manifest_is_valid_and_keeps_unlicensed_images_remote() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest_path = repo_root / "data/raw/mm2r/0.99/assets/manifest.yaml"
    manifest = AssetManifest.model_validate(
        yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    )

    assert len(manifest.assets) == 3
    assert [asset.rights_status for asset in manifest.assets] == [
        RightsStatus.REFERENCE_ONLY,
        RightsStatus.REJECTED,
        RightsStatus.REJECTED,
    ]
    assert all(asset.local_path is None for asset in manifest.assets)
