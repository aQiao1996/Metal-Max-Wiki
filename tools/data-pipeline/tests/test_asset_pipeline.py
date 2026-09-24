from __future__ import annotations

import fcntl
import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import BinaryIO, cast

import httpx
import pytest
import yaml
from PIL import Image

from mmwiki_data import asset_pipeline
from mmwiki_data.asset_models import AssetLock, LockedAsset
from mmwiki_data.asset_pipeline import (
    MAX_ASSET_BYTES,
    AssetPipelineError,
    _create_http_client,
    audit_assets,
    fetch_assets,
)
from mmwiki_data.cli import main

PIXEL_FIXTURE = Path(__file__).parent / "fixtures" / "pixel.png"
PNG_BYTES = PIXEL_FIXTURE.read_bytes()
PIXEL_SHA256 = "50e1eaeba4ca721aadaa7c7162c2b16b9924940f69aa0aca8e77bf97371e8248"
NORMALIZED_DOMAINS = ("equipment", "items", "quests", "jobs", "skills")


def entry(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "licensed-map",
        "kind": "map",
        "title": "Licensed map",
        "source_page_url": "https://source.example/guide",
        "source_image_url": "https://images.example/map.png",
        "author": "Example Author",
        "license": "CC BY 4.0",
        "rights_status": "reusable",
        "version_scope": ["mm2r-jp"],
        "entity_refs": [],
        "local_path": "files/licensed-map.png",
        "allowed_redirect_hosts": [],
        "alt": "Licensed map",
        "notes": "",
    }
    value.update(changes)
    return value


def create_repo(tmp_path: Path, assets: list[dict[str, object]]) -> Path:
    asset_root = tmp_path / "data/raw/mm2r/0.99/assets"
    (asset_root / "files").mkdir(parents=True)
    manifest = {"schema_version": 1, "assets": assets}
    (asset_root / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    interim_root = tmp_path / "data/interim/mm2r/0.99"
    interim_root.mkdir(parents=True)
    for domain in NORMALIZED_DOMAINS:
        write_normalized_bundle(tmp_path, domain)
    return tmp_path


def write_normalized_bundle(
    repo_root: Path,
    domain: str,
    *,
    records: list[dict[str, object]] | None = None,
) -> Path:
    path = repo_root / f"data/interim/mm2r/0.99/{domain}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_records = records or []
    source_hashes = sorted(
        {
            str(source_ref["content_hash"])
            for record in normalized_records
            for source_ref in cast(list[dict[str, object]], record["source_refs"])
        }
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "game": "mm2r",
                "target_version": "0.99",
                "domain": domain,
                "source_hashes": source_hashes,
                "records": normalized_records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def normalized_record(
    record_id: str,
    domain: str,
    *,
    asset_refs: list[str] | None = None,
) -> dict[str, object]:
    source_hash = "sha256:" + "a" * 64
    return {
        "id": record_id,
        "game": "mm2r",
        "target_version": "0.99",
        "domain": domain,
        "kind": "fixture",
        "names": {"ja": "テスト", "zh_09": None, "zh_099": None, "aliases": []},
        "attributes": {},
        "version_scope": [],
        "verification_status": "source_only",
        "source_refs": [
            {
                "source_id": "fixture",
                "target_id": "fixture",
                "source_url": "https://source.example/fixture",
                "retrieved_at": "2026-09-21T10:00:00+08:00",
                "content_hash": source_hash,
                "table_index": 0,
                "row_index": 0,
            }
        ],
        "source_spans": [],
        "issues": [],
        "asset_refs": asset_refs or [],
    }


def asset_root(repo_root: Path) -> Path:
    return repo_root / "data/raw/mm2r/0.99/assets"


def public_resolver(host: str) -> list[str]:
    assert host
    return ["93.184.216.34"]


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def png_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"Content-Type": "image/png", "Content-Length": str(len(PNG_BYTES))},
        stream=httpx.ByteStream(PNG_BYTES),
        request=request,
    )


def lock_entry(
    *,
    asset_id: str = "licensed-map",
    local_path: str = "files/licensed-map.png",
    data: bytes = PNG_BYTES,
    final_url: str | None = "https://images.example/map.png",
    media_type: str = "image/png",
    width: int = 1,
    height: int = 1,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "final_url": final_url,
        "local_path": local_path,
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "media_type": media_type,
        "byte_size": len(data),
        "width": width,
        "height": height,
    }


def write_lock(repo_root: Path, entries: list[dict[str, object]]) -> Path:
    path = asset_root(repo_root) / "lock.json"
    value = AssetLock.model_validate({"assets": entries})
    path.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")
    path.chmod(0o644)
    return path


def write_asset(repo_root: Path, path: str, data: bytes = PNG_BYTES) -> Path:
    target = asset_root(repo_root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o644)
    return target


def make_image(format_name: str, *, size: tuple[int, int] = (2, 2)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (255, 0, 0)).save(output, format=format_name)
    return output.getvalue()


def make_animated_png() -> bytes:
    output = io.BytesIO()
    first = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    second = Image.new("RGBA", (2, 2), (0, 255, 0, 255))
    first.save(output, format="PNG", save_all=True, append_images=[second], duration=10)
    return output.getvalue()


def test_pixel_fixture_is_the_expected_deterministic_png() -> None:
    assert hashlib.sha256(PNG_BYTES).hexdigest() == PIXEL_SHA256
    with Image.open(PIXEL_FIXTURE) as image:
        assert image.format == "PNG"
        assert image.size == (1, 1)


def test_reference_rejected_and_permission_needed_never_request_network(tmp_path: Path) -> None:
    assets = [
        entry(
            id=f"remote-{status.replace('_', '-')}",
            rights_status=status,
            license="NOASSERTION",
            local_path=None,
            source_image_url=f"https://images.example/{status}.png",
        )
        for status in ("reference_only", "rejected", "permission_needed")
    ]
    repo_root = create_repo(tmp_path, assets)

    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"unexpected request: {request.url}")

    with mock_client(unexpected) as client:
        summary = fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert summary == {"downloaded": 0, "local": 0, "locked": 0}
    assert json.loads((asset_root(repo_root) / "lock.json").read_text()) == {
        "schema_version": 1,
        "assets": [],
    }


def test_asset_fetch_rejects_a_concurrent_process_lock(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [])

    with asset_pipeline._asset_process_lock(repo_root):
        with pytest.raises(AssetPipelineError, match="already running"):
            fetch_assets(repo_root)


def test_audit_waits_for_fetch_lock_and_reads_only_the_committed_tree(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    write_asset(repo_root, "files/licensed-map.png")
    write_lock(repo_root, [lock_entry()])
    in_flight = asset_root(repo_root) / "files/.in-flight.tmp"
    started = threading.Event()

    def run_audit() -> list[str]:
        started.set()
        return audit_assets(repo_root)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with asset_pipeline._asset_process_lock(repo_root):
            in_flight.write_bytes(b"partial")
            future = executor.submit(run_audit)
            assert started.wait(timeout=1)
            with pytest.raises(FutureTimeoutError):
                future.result(timeout=0.2)
            in_flight.unlink()
        assert future.result(timeout=2) == []


def test_asset_lock_release_failure_preserves_primary_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [])

    def fail_release(_descriptor: int, operation: int) -> None:
        if operation == fcntl.LOCK_UN:
            raise OSError("injected unlock failure")

    monkeypatch.setattr(fcntl, "flock", fail_release)

    with pytest.raises(AssetPipelineError) as captured:
        with asset_pipeline._asset_process_lock(repo_root, shared=True, blocking=True):
            raise AssetPipelineError("primary audit failure")

    message = str(captured.value)
    assert "primary audit failure" in message
    assert "injected unlock failure" in message


def test_default_asset_client_ignores_proxy_environment() -> None:
    active_client = httpx.Client(transport=httpx.MockTransport(png_response))
    options: dict[str, object] = {}

    def client_factory(**kwargs: object) -> httpx.Client:
        options.update(kwargs)
        return active_client

    assert _create_http_client(client_factory) is active_client

    assert options["trust_env"] is False
    active_client.close()


def test_valid_png_download_creates_file_and_lock_with_deterministic_metadata(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    with mock_client(png_response) as client:
        summary = fetch_assets(repo_root, client=client, resolver=public_resolver)

    target = asset_root(repo_root) / "files/licensed-map.png"
    lock = AssetLock.model_validate_json((asset_root(repo_root) / "lock.json").read_text())
    assert summary == {"downloaded": 1, "local": 0, "locked": 1}
    assert target.read_bytes() == PNG_BYTES
    assert target.stat().st_mode & 0o777 == 0o644
    assert (asset_root(repo_root) / "lock.json").stat().st_mode & 0o777 == 0o644
    assert lock.assets == [
        LockedAsset.model_validate(
            {
                "asset_id": "licensed-map",
                "final_url": "https://images.example/map.png",
                "local_path": "files/licensed-map.png",
                "sha256": f"sha256:{hashlib.sha256(PNG_BYTES).hexdigest()}",
                "media_type": "image/png",
                "byte_size": len(PNG_BYTES),
                "width": 1,
                "height": 1,
            }
        )
    ]
    assert audit_assets(repo_root) == []


def test_fetch_connects_to_validated_ip_with_original_host_and_sni(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return png_response(request)

    with mock_client(handler) as client:
        fetch_assets(
            repo_root,
            client=client,
            resolver=lambda _host: ["93.184.216.35", "93.184.216.34"],
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.url.host == "93.184.216.34"
    assert request.headers["Host"] == "images.example"
    assert request.extensions["sni_hostname"] == "images.example"


def test_default_client_uses_a_separate_connection_scope_for_each_redirect_host(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [entry(allowed_redirect_hosts=["cdn.example"])])
    requests: list[httpx.Request] = []
    clients: list[httpx.Client] = []
    client_options: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers["Host"] == "images.example":
            return httpx.Response(
                302,
                headers={"Location": "https://cdn.example/final.png"},
                request=request,
            )
        return png_response(request)

    def client_factory(**kwargs: object) -> httpx.Client:
        client_options.append(kwargs)
        created = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(created)
        return created

    summary = fetch_assets(
        repo_root,
        resolver=lambda _host: ["93.184.216.34"],
        client_factory=client_factory,
    )

    assert summary == {"downloaded": 1, "local": 0, "locked": 1}
    assert len(clients) == 2
    assert all(client.is_closed for client in clients)
    assert [request.url.host for request in requests] == [
        "93.184.216.34",
        "93.184.216.34",
    ]
    assert [request.headers["Host"] for request in requests] == [
        "images.example",
        "cdn.example",
    ]
    assert [request.extensions["sni_hostname"] for request in requests] == [
        "images.example",
        "cdn.example",
    ]
    assert all(options["trust_env"] is False for options in client_options)
    assert all(options["http2"] is False for options in client_options)
    assert all("max_connections=1" in repr(options["limits"]) for options in client_options)
    assert all(
        "max_keepalive_connections=0" in repr(options["limits"]) for options in client_options
    )


def test_redirects_require_allowlist_public_dns_and_resolve_every_hop(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry(allowed_redirect_hosts=["cdn.example"])])
    requests: list[tuple[str, str]] = []
    resolutions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), request.headers["Host"]))
        if request.headers["Host"] == "images.example":
            return httpx.Response(
                302,
                headers={"Location": "https://cdn.example/final.png"},
                request=request,
            )
        return png_response(request)

    def resolver(host: str) -> list[str]:
        resolutions.append(host)
        return ["93.184.216.34"]

    with mock_client(handler) as client:
        fetch_assets(repo_root, client=client, resolver=resolver)

    assert requests == [
        ("https://93.184.216.34/map.png", "images.example"),
        ("https://93.184.216.34/final.png", "cdn.example"),
    ]
    assert resolutions == ["images.example", "cdn.example"]
    lock = AssetLock.model_validate_json((asset_root(repo_root) / "lock.json").read_text())
    assert str(lock.assets[0].final_url) == "https://cdn.example/final.png"


def test_unicode_source_and_redirect_share_one_runtime_host_identity(tmp_path: Path) -> None:
    repo_root = create_repo(
        tmp_path,
        [
            entry(
                source_page_url="https://faß.de/guide",
                source_image_url="https://faß.de/map.png",
                allowed_redirect_hosts=["faß.de", "xn--fa-hia.de"],
            )
        ],
    )
    requests: list[httpx.Request] = []
    resolutions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/map.png":
            return httpx.Response(
                302,
                headers={"Location": "https://xn--fa-hia.de/final.png"},
                request=request,
            )
        return png_response(request)

    def resolver(host: str) -> list[str]:
        resolutions.append(host)
        return ["93.184.216.34"]

    with mock_client(handler) as client:
        fetch_assets(repo_root, client=client, resolver=resolver)

    assert resolutions == ["xn--fa-hia.de", "xn--fa-hia.de"]
    assert [request.headers["Host"] for request in requests] == [
        "xn--fa-hia.de",
        "xn--fa-hia.de",
    ]
    assert [request.extensions["sni_hostname"] for request in requests] == [
        "xn--fa-hia.de",
        "xn--fa-hia.de",
    ]


def test_runtime_url_uses_nontransitional_idna_identity() -> None:
    raw_url = "https://faß.de/final.png"

    assert (
        asset_pipeline._validate_request_url(
            raw_url,
            allowed_hosts={"xn--fa-hia.de"},
            asset_id="licensed-map",
        )
        == "xn--fa-hia.de"
    )
    with pytest.raises(AssetPipelineError, match="not an allowed host"):
        asset_pipeline._validate_request_url(
            raw_url,
            allowed_hosts={"fass.de"},
            asset_id="licensed-map",
        )


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://１２７．０．０．１/image.png",
        "https://127。0。0。1/image.png",
    ],
)
def test_runtime_url_rejects_unicode_hosts_that_map_to_ip_literals(raw_url: str) -> None:
    with pytest.raises(AssetPipelineError, match="invalid asset URL hostname"):
        asset_pipeline._validate_request_url(
            raw_url,
            allowed_hosts={"127.0.0.1"},
            asset_id="licensed-map",
        )


@pytest.mark.parametrize(
    ("location", "message"),
    [
        ("https://evil.example/map.png", "allowed host"),
        ("http://images.example/map.png", "HTTPS"),
        ("https://user:pass@images.example/map.png", "userinfo"),
        ("https://images.example/map.png#frag", "fragment"),
    ],
)
def test_redirect_rejects_unsafe_destination(tmp_path: Path, location: str, message: str) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": location}, request=request)

    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match=message):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.1"],
        ["169.254.1.1"],
        ["224.0.0.1"],
        ["192.0.2.1"],
        ["0.0.0.0"],
        ["::1"],
        ["fc00::1"],
        ["fe80::1"],
        ["ff02::1"],
        ["::"],
        ["93.184.216.34", "127.0.0.1"],
    ],
)
def test_fetch_rejects_any_non_public_dns_answer(tmp_path: Path, addresses: list[str]) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    requested = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return png_response(request)

    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match="public"):
        fetch_assets(repo_root, client=client, resolver=lambda _host: addresses)
    assert requested is False


def test_dns_is_rechecked_after_redirect_and_rebinding_fails(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    calls = 0

    def resolver(_host: str) -> list[str]:
        nonlocal calls
        calls += 1
        return ["93.184.216.34"] if calls == 1 else ["127.0.0.1"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://images.example/final.png"},
            request=request,
        )

    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match="public"):
        fetch_assets(repo_root, client=client, resolver=resolver)
    assert calls == 2


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        (
            lambda request: httpx.Response(500, request=request),
            "status 500",
        ),
        (
            lambda request: httpx.Response(302, request=request),
            "Location",
        ),
        (
            lambda request: httpx.Response(
                200,
                headers={
                    "Content-Type": "image/png",
                    "Content-Length": str(MAX_ASSET_BYTES + 1),
                },
                stream=httpx.ByteStream(b""),
                request=request,
            ),
            "Content-Length",
        ),
    ],
)
def test_fetch_reports_status_missing_location_and_oversized_header(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    message: str,
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match=message):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


class OversizedStream(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        yield b"x" * MAX_ASSET_BYTES
        yield b"y"


def test_client_close_failure_cleans_staged_image_and_allows_retry(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    class CloseFailingClient(httpx.Client):
        def close(self) -> None:
            super().close()
            raise OSError("CLIENT CLOSE AFTER SUCCESS")

    def close_failing_client(**_kwargs: object) -> httpx.Client:
        return CloseFailingClient(transport=httpx.MockTransport(png_response))

    with pytest.raises(AssetPipelineError) as captured:
        fetch_assets(
            repo_root,
            client_factory=close_failing_client,
            resolver=public_resolver,
        )

    assert "CLIENT CLOSE AFTER SUCCESS" in str(captured.value)
    assert not (asset_root(repo_root) / "files/licensed-map.png").exists()
    assert list((asset_root(repo_root) / "files").glob(".*.tmp")) == []

    with mock_client(png_response) as client:
        summary = fetch_assets(repo_root, client=client, resolver=public_resolver)
    assert summary == {"downloaded": 1, "local": 0, "locked": 1}


def test_stream_over_limit_fails_without_creating_target(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            stream=OversizedStream(),
            request=request,
        )

    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match="10 MiB"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)
    assert not (asset_root(repo_root) / "files/licensed-map.png").exists()
    assert not list((asset_root(repo_root) / "files").glob(".*.tmp"))


def test_fetch_rejects_compressed_responses_before_decoding(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png", "Content-Encoding": "gzip"},
            stream=httpx.ByteStream(gzip.compress(PNG_BYTES)),
            request=request,
        )

    with (
        mock_client(handler) as client,
        pytest.raises(AssetPipelineError, match="Content-Encoding"),
    ):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


def test_fetch_streams_raw_response_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    class RawPngStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield PNG_BYTES

    def raw_png_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            stream=RawPngStream(),
            request=request,
        )

    def reject_decoded_stream(_response: httpx.Response) -> Iterator[bytes]:
        pytest.fail("iter_bytes must not decode downloaded content")

    monkeypatch.setattr(httpx.Response, "iter_bytes", reject_decoded_stream)
    with mock_client(raw_png_response) as client:
        summary = fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert summary["downloaded"] == 1


def test_http_timeout_has_asset_and_url_context(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("injected timeout", request=request)

    with mock_client(timeout) as client, pytest.raises(AssetPipelineError) as captured:
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert "licensed-map" in str(captured.value)
    assert "https://images.example/map.png" in str(captured.value)
    assert "timeout" in str(captured.value)


@pytest.mark.parametrize(
    ("data", "content_type", "message"),
    [
        (b"<html>not an image</html>", "image/png", "image"),
        (PNG_BYTES[:20], "image/png", "image"),
        (make_image("GIF"), "image/gif", "PNG, JPEG, or WebP"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", "PNG, JPEG, or WebP"),
        (make_animated_png(), "image/png", "animated"),
    ],
)
def test_fetch_rejects_disguised_truncated_unsupported_and_animated_content(
    tmp_path: Path, data: bytes, content_type: str, message: str
) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": content_type},
            stream=httpx.ByteStream(data),
            request=request,
        )

    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match=message):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


def test_fetch_rejects_excessive_dimensions_and_decompression_bomb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    wide_png = make_image("PNG", size=(16_385, 1))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            stream=httpx.ByteStream(wide_png),
            request=request,
        )

    with mock_client(handler) as client, pytest.raises(AssetPipelineError, match="dimensions"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 0)
    with (
        mock_client(png_response) as client,
        pytest.raises(AssetPipelineError, match="decompression bomb"),
    ):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


def test_redirect_limit_and_cycle_are_clear_failures(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def cycle(request: httpx.Request) -> httpx.Response:
        target = "/b.png" if request.url.path.endswith("map.png") else "/map.png"
        return httpx.Response(302, headers={"Location": target}, request=request)

    with mock_client(cycle) as client, pytest.raises(AssetPipelineError, match="cycle"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    counter = 0

    def endless(request: httpx.Request) -> httpx.Response:
        nonlocal counter
        counter += 1
        return httpx.Response(
            302, headers={"Location": f"/redirect-{counter}.png"}, request=request
        )

    with mock_client(endless) as client, pytest.raises(AssetPipelineError, match="five redirects"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


def test_duplicate_download_hashes_fail_and_preserve_old_lock(tmp_path: Path) -> None:
    repo_root = create_repo(
        tmp_path,
        [
            entry(),
            entry(
                id="second-map",
                source_image_url="https://images.example/second.png",
                local_path="files/second-map.png",
            ),
        ],
    )
    old_lock = write_lock(repo_root, [])
    old_bytes = old_lock.read_bytes()
    with mock_client(png_response) as client, pytest.raises(AssetPipelineError, match="duplicate"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)
    assert old_lock.read_bytes() == old_bytes
    assert not (asset_root(repo_root) / "files/licensed-map.png").exists()
    assert not (asset_root(repo_root) / "files/second-map.png").exists()


def test_fetch_aggregates_primary_and_staging_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(
        tmp_path,
        [
            entry(),
            entry(
                id="second-map",
                source_image_url="https://images.example/second.png",
                local_path="files/second-map.png",
            ),
        ],
    )

    def fail_cleanup(_paths: object) -> list[OSError]:
        return [OSError("STAGING CLEANUP FAILURE")]

    monkeypatch.setattr(asset_pipeline, "_cleanup", fail_cleanup)
    with mock_client(png_response) as client, pytest.raises(AssetPipelineError) as captured:
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    message = str(captured.value)
    assert "duplicate asset content" in message
    assert "STAGING CLEANUP FAILURE" in message


def test_fetch_keeps_validation_error_when_temp_unlink_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    original_unlink = Path.unlink
    failed_once = False

    def fail_first_temp_unlink(path: Path, missing_ok: bool = False) -> None:
        nonlocal failed_once
        if path.suffix == ".tmp" and not failed_once:
            failed_once = True
            raise OSError("TEMP UNLINK FAILURE")
        original_unlink(path, missing_ok=missing_ok)

    def invalid_image(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            stream=httpx.ByteStream(b"not an image"),
            request=request,
        )

    monkeypatch.setattr(Path, "unlink", fail_first_temp_unlink)
    with mock_client(invalid_image) as client, pytest.raises(AssetPipelineError) as captured:
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    message = str(captured.value)
    assert "invalid or truncated image" in message
    assert "TEMP UNLINK FAILURE" in message


def test_lock_commit_failure_rolls_back_all_images_and_lock(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    target = write_asset(repo_root, "files/licensed-map.png", b"old-image")
    lock_path = write_lock(repo_root, [])
    old_lock = lock_path.read_bytes()
    calls = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected lock replace failure")
        os.replace(source, destination)

    with (
        mock_client(png_response) as client,
        pytest.raises(OSError, match="injected lock replace failure"),
    ):
        fetch_assets(
            repo_root,
            client=client,
            resolver=public_resolver,
            replace=fail_second_replace,
        )

    assert target.read_bytes() == b"old-image"
    assert lock_path.read_bytes() == old_lock
    residuals = [
        path for path in asset_root(repo_root).rglob(".*") if path.suffix in {".tmp", ".bak"}
    ]
    assert residuals == []


def test_symlink_swap_during_commit_rolls_back_prior_image_and_restores_lock(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    target = write_asset(repo_root, "files/licensed-map.png", b"old-image")
    lock_path = write_lock(repo_root, [])
    old_lock = lock_path.read_bytes()
    external = tmp_path / "external-lock.json"
    external.write_bytes(b"outside-must-not-change")
    calls = 0

    def swap_lock_target_after_image(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        os.replace(source, destination)
        if calls == 1:
            lock_path.unlink()
            lock_path.symlink_to(external)

    with mock_client(png_response) as client, pytest.raises(AssetPipelineError) as captured:
        fetch_assets(
            repo_root,
            client=client,
            resolver=public_resolver,
            replace=swap_lock_target_after_image,
        )

    assert "symlink" in str(captured.value)
    assert target.read_bytes() == b"old-image"
    assert not lock_path.is_symlink()
    assert lock_path.read_bytes() == old_lock
    assert external.read_bytes() == b"outside-must-not-change"
    assert [
        path for path in asset_root(repo_root).rglob("*") if path.suffix in {".tmp", ".bak"}
    ] == []


def test_failed_asset_rollback_keeps_only_the_recovery_backup(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    target = write_asset(repo_root, "files/licensed-map.png", b"old-image")
    lock_path = write_lock(repo_root, [])
    old_lock = lock_path.read_bytes()
    calls = 0

    def fail_commit_and_rollback(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("PRIMARY LOCK REPLACE FAILURE")
        if calls == 3:
            raise OSError("IMAGE ROLLBACK FAILURE")
        os.replace(source, destination)

    with mock_client(png_response) as client, pytest.raises(OSError) as captured:
        fetch_assets(
            repo_root,
            client=client,
            resolver=public_resolver,
            replace=fail_commit_and_rollback,
        )

    message = str(captured.value)
    assert "PRIMARY LOCK REPLACE FAILURE" in message
    assert "IMAGE ROLLBACK FAILURE" in message
    assert target.read_bytes() == PNG_BYTES
    assert lock_path.read_bytes() == old_lock
    backups = [path for path in asset_root(repo_root).rglob("*") if path.suffix == ".bak"]
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old-image"
    assert str(backups[0]) in message
    assert [path for path in asset_root(repo_root).rglob("*") if path.suffix == ".tmp"] == []


def test_lock_staging_failure_cleans_every_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    original_fsync = os.fsync
    calls = 0

    def fail_lock_fsync(file_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected lock fsync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", fail_lock_fsync)
    with (
        mock_client(png_response) as client,
        pytest.raises(OSError, match="injected lock fsync failure"),
    ):
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert not (asset_root(repo_root) / "files/licensed-map.png").exists()
    assert not (asset_root(repo_root) / "lock.json").exists()
    assert [path for path in asset_root(repo_root).rglob("*") if path.suffix == ".tmp"] == []


def test_lock_staging_keeps_fsync_and_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [])
    original_unlink = Path.unlink
    failed_unlink = False

    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("LOCK FSYNC FAILURE")

    def fail_first_unlink(path: Path, missing_ok: bool = False) -> None:
        nonlocal failed_unlink
        if path.suffix == ".tmp" and not failed_unlink:
            failed_unlink = True
            raise OSError("LOCK TEMP CLEANUP FAILURE")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(os, "fsync", fail_fsync)
    monkeypatch.setattr(Path, "unlink", fail_first_unlink)

    with pytest.raises(OSError) as captured:
        fetch_assets(repo_root)

    message = str(captured.value)
    assert "LOCK FSYNC FAILURE" in message
    assert "LOCK TEMP CLEANUP FAILURE" in message
    assert [path for path in asset_root(repo_root).rglob("*") if path.suffix == ".tmp"] == []


def test_backup_failure_cleans_backup_and_preserves_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    target = write_asset(repo_root, "files/licensed-map.png", b"old-image")
    lock_path = write_lock(repo_root, [])
    old_lock = lock_path.read_bytes()

    def fail_backup(_source: object, _destination: object) -> None:
        raise OSError("injected backup failure")

    monkeypatch.setattr(shutil, "copyfileobj", fail_backup)
    with (
        mock_client(png_response) as client,
        pytest.raises(OSError, match="injected backup failure"),
    ):
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert target.read_bytes() == b"old-image"
    assert lock_path.read_bytes() == old_lock
    assert [path for path in asset_root(repo_root).rglob("*") if path.suffix == ".bak"] == []


@pytest.mark.parametrize("root_kind", ["file", "symlink"])
def test_files_root_must_be_a_real_directory(tmp_path: Path, root_kind: str) -> None:
    repo_root = create_repo(tmp_path, [])
    files_root = asset_root(repo_root) / "files"
    files_root.rmdir()
    if root_kind == "file":
        files_root.write_bytes(b"not-a-directory")
    else:
        outside = tmp_path / "outside-files"
        outside.mkdir()
        files_root.symlink_to(outside, target_is_directory=True)
    write_lock(repo_root, [])

    errors = audit_assets(repo_root)

    assert errors
    assert any(
        "files" in error and ("directory" in error or "symlink" in error) for error in errors
    )
    with pytest.raises(AssetPipelineError, match="directory|symlink"):
        fetch_assets(repo_root)


def test_audit_detects_orphan_symlink_permissions_and_lock_mismatch(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    target = write_asset(repo_root, "files/licensed-map.png")
    write_lock(repo_root, [lock_entry()])
    assert audit_assets(repo_root) == []

    orphan = write_asset(repo_root, "files/orphan.png")
    assert any("orphan" in error for error in audit_assets(repo_root))
    orphan.unlink()

    target.chmod(0o600)
    assert any("0644" in error for error in audit_assets(repo_root))
    target.chmod(0o644)

    write_lock(repo_root, [lock_entry(data=b"different")])
    assert any("sha256" in error for error in audit_assets(repo_root))

    target.unlink()
    external = tmp_path / "external.png"
    external.write_bytes(PNG_BYTES)
    target.symlink_to(external)
    assert any("symlink" in error for error in audit_assets(repo_root))


def original_svg_entry(path: str = "files/original-diagrams/map.svg") -> dict[str, object]:
    return entry(
        id="original-map",
        source_page_url=None,
        source_image_url=None,
        author="Metal Max Wiki",
        license="CC BY-NC-SA 4.0",
        rights_status="original_diagram",
        local_path=path,
    )


def test_original_svg_is_audited_locally_and_never_requested(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><path d="M0 0"/></svg>'
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)

    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"unexpected request: {request.url}")

    with mock_client(unexpected) as client:
        summary = fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert summary == {"downloaded": 0, "local": 1, "locked": 1}
    assert audit_assets(repo_root) == []
    lock = AssetLock.model_validate_json((asset_root(repo_root) / "lock.json").read_text())
    assert lock.assets[0].media_type == "image/svg+xml"
    assert lock.assets[0].width == 320
    assert lock.assets[0].height == 180


def test_user_capture_is_locked_locally_and_never_requested(tmp_path: Path) -> None:
    capture = entry(
        id="user-capture",
        source_page_url=None,
        source_image_url=None,
        author="用户",
        license="user-owned-with-project-permission",
        rights_status="user_capture",
        local_path="files/user-captures/menu.png",
    )
    repo_root = create_repo(tmp_path, [capture])
    write_asset(repo_root, "files/user-captures/menu.png")

    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"unexpected request: {request.url}")

    with mock_client(unexpected) as client:
        summary = fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert summary == {"downloaded": 0, "local": 1, "locked": 1}
    assert audit_assets(repo_root) == []


def test_local_asset_size_is_checked_before_reading_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    target = write_asset(
        repo_root,
        "files/original-diagrams/map.svg",
        b"x" * (MAX_ASSET_BYTES + 1),
    )
    original_read_bytes = Path.read_bytes

    def reject_oversized_read(path: Path) -> bytes:
        if path == target:
            pytest.fail("oversized local assets must be rejected before reading")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_oversized_read)
    with pytest.raises(AssetPipelineError, match="size"):
        fetch_assets(repo_root)


def test_oversized_local_png_returns_pipeline_error_before_pydantic(
    tmp_path: Path,
) -> None:
    capture = entry(
        id="user-capture",
        source_page_url=None,
        source_image_url=None,
        author="用户",
        license="user-owned-with-project-permission",
        rights_status="user_capture",
        local_path="files/user-captures/huge.png",
        allowed_redirect_hosts=[],
    )
    repo_root = create_repo(tmp_path, [capture])
    write_asset(
        repo_root,
        "files/user-captures/huge.png",
        b"x" * (MAX_ASSET_BYTES + 1),
    )

    with pytest.raises(AssetPipelineError, match="size"):
        fetch_assets(repo_root)
    write_lock(repo_root, [])
    assert any("size" in error for error in audit_assets(repo_root))


def test_audit_oversized_reusable_with_existing_lock_returns_contextual_error(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    write_asset(
        repo_root,
        "files/licensed-map.png",
        b"x" * (MAX_ASSET_BYTES + 1),
    )
    write_lock(repo_root, [lock_entry()])

    errors = audit_assets(repo_root)

    assert errors
    assert any(
        "licensed-map:" in error and "size limit" in error and "10 MiB" in error for error in errors
    )


def test_audit_converts_per_entry_validation_error_to_contextual_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    write_asset(repo_root, "files/licensed-map.png")
    write_lock(repo_root, [lock_entry()])

    def invalid_dimensions(
        _source: Path | BinaryIO,
        *,
        expected_suffix: str,
        declared_media_type: str | None,
        asset_id: str,
    ) -> tuple[str, int, int]:
        assert expected_suffix == ".png"
        assert declared_media_type is None
        assert asset_id == "licensed-map"
        return "image/png", 0, 1

    monkeypatch.setattr(asset_pipeline, "_validate_raster", invalid_dimensions)

    errors = audit_assets(repo_root)

    assert len(errors) == 1
    assert errors[0].startswith("licensed-map: invalid audited lock metadata:")


def test_audit_converts_local_filesystem_failures_to_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    def fail_manifest(_repo_root: Path) -> object:
        raise OSError("injected local filesystem failure")

    monkeypatch.setattr(asset_pipeline, "load_asset_manifest", fail_manifest)

    assert audit_assets(repo_root) == ["injected local filesystem failure"]


def test_audit_rejects_extra_lock_id_and_final_host(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    write_asset(repo_root, "files/licensed-map.png")
    write_lock(
        repo_root,
        [
            lock_entry(final_url="https://evil.example/map.png"),
            lock_entry(
                asset_id="unknown-map",
                local_path="files/unknown-map.png",
                final_url="https://images.example/unknown.png",
            ),
        ],
    )

    errors = audit_assets(repo_root)

    assert any("allowed host" in error for error in errors)
    assert any("unknown asset id" in error for error in errors)


def test_audit_accepts_bidirectional_manifest_and_normalized_record_refs(
    tmp_path: Path,
) -> None:
    record_id = "equipment-0123456789"
    repo_root = create_repo(tmp_path, [entry(entity_refs=[record_id])])
    write_normalized_bundle(
        repo_root,
        "equipment",
        records=[normalized_record(record_id, "equipment", asset_refs=["licensed-map"])],
    )
    write_asset(repo_root, "files/licensed-map.png")
    write_lock(repo_root, [lock_entry()])

    assert audit_assets(repo_root) == []


def test_audit_reports_dangling_manifest_entity_ref_with_asset_context(
    tmp_path: Path,
) -> None:
    record_id = "equipment-0123456789"
    repo_root = create_repo(tmp_path, [entry(entity_refs=[record_id])])
    write_asset(repo_root, "files/licensed-map.png")
    write_lock(repo_root, [lock_entry()])

    errors = audit_assets(repo_root)

    assert any("licensed-map" in error and record_id in error for error in errors)


def test_audit_reports_dangling_and_one_sided_normalized_asset_refs(tmp_path: Path) -> None:
    linked_id = "equipment-0123456789"
    dangling_id = "equipment-abcdef0123"
    repo_root = create_repo(tmp_path, [entry(entity_refs=[linked_id])])
    write_normalized_bundle(
        repo_root,
        "equipment",
        records=[
            normalized_record(linked_id, "equipment"),
            normalized_record(dangling_id, "equipment", asset_refs=["missing-asset"]),
        ],
    )
    write_asset(repo_root, "files/licensed-map.png")
    write_lock(repo_root, [lock_entry()])

    errors = audit_assets(repo_root)

    assert any(
        "licensed-map" in error and linked_id in error and "bidirectional" in error
        for error in errors
    )
    assert any("missing-asset" in error and dangling_id in error for error in errors)


@pytest.mark.parametrize("bundle_state", ["missing", "invalid"])
def test_audit_reports_missing_or_invalid_normalized_bundle(
    tmp_path: Path, bundle_state: str
) -> None:
    repo_root = create_repo(tmp_path, [])
    equipment_path = repo_root / "data/interim/mm2r/0.99/equipment.json"
    if bundle_state == "missing":
        equipment_path.unlink()
    else:
        equipment_path.write_text("{not-json", encoding="utf-8")
    write_lock(repo_root, [])

    errors = audit_assets(repo_root)

    assert any("equipment.json" in error and bundle_state in error for error in errors)


def test_audit_still_loads_normalized_bundles_when_asset_lock_is_missing(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [])
    (repo_root / "data/interim/mm2r/0.99/equipment.json").unlink()

    errors = audit_assets(repo_root)

    assert any("missing asset lock" in error for error in errors)
    assert any(
        "missing normalized bundle" in error and "equipment.json" in error for error in errors
    )


@pytest.mark.parametrize(
    "payload",
    [
        '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
        '<!ENTITY x "x"><svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><script/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><foreignObject/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" onload="x"/>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<a href="javascript:x"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<image href="data:image/png,x"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<image href="https://evil.example/x.png"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<style>@import "evil.css"</style></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        "<style>.x{fill:url(https://evil.example/x)}</style></svg>",
    ],
)
def test_svg_active_or_external_content_is_rejected(tmp_path: Path, payload: str) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    write_asset(repo_root, "files/original-diagrams/map.svg", payload.encode())
    write_lock(repo_root, [])
    assert any("SVG" in error for error in audit_assets(repo_root))


@pytest.mark.parametrize(
    "payload",
    [
        '<?xml-stylesheet type="text/css" href="https://evil.example/a.css"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<AnImAtE attributeName="x" values="0;1"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:s="urn:evil" '
        'width="1" height="1"><s:animateTransform attributeName="transform"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        "<style>.safe { fill: red; }</style></svg>",
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<g attributeName="XLINK:HREF" to="javascript:alert(1)"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<g src="//evil.example/image.png"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        '<g attributeName="xlink : href" '
        'values="ja&#x0A;vascript:alert(1)"/></svg>',
    ],
)
def test_svg_rejects_processing_smil_namespace_case_and_rewrite_pocs(
    tmp_path: Path, payload: str
) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    write_asset(repo_root, "files/original-diagrams/map.svg", payload.encode())
    write_lock(repo_root, [])

    assert any("SVG" in error for error in audit_assets(repo_root))


def test_asset_fetch_uses_the_same_strict_svg_validator(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    write_asset(
        repo_root,
        "files/original-diagrams/map.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><set/></svg>',
    )

    with pytest.raises(AssetPipelineError, match="SVG element"):
        fetch_assets(repo_root)
    assert not (asset_root(repo_root) / "lock.json").exists()


@pytest.mark.parametrize(
    "payload",
    [
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" '
        r'style="u\72l(https://evil.example/x)"/>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        r'<rect fill="\75\72\6c(https://evil.example/x)"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        r"<handler>evil</handler></svg>",
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        r'<rect unknownAttribute="1"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        r'<use href="other.svg#marker"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" xmlns:evil="urn:evil" '
        r'width="1" height="1"><evil:path d="M0 0"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        r'<rect xml:base="https://evil.example/"/></svg>',
        r'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        r'<rect fill="&#x9;red"/></svg>',
    ],
)
def test_svg_static_whitelist_rejects_review_bypass_pocs(tmp_path: Path, payload: str) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    write_asset(repo_root, "files/original-diagrams/map.svg", payload.encode())
    write_lock(repo_root, [])

    assert any("SVG" in error for error in audit_assets(repo_root))


def test_svg_limits_nesting_elements_attributes_and_text(tmp_path: Path) -> None:
    attributes = [
        "id",
        "class",
        "x",
        "y",
        "width",
        "height",
        "rx",
        "ry",
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-opacity",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-dasharray",
        "stroke-dashoffset",
        "opacity",
        "transform",
        "vector-effect",
        "paint-order",
        "shape-rendering",
        "clip-path",
        "mask",
        "marker-start",
        "marker-mid",
        "marker-end",
        "role",
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
        "tabindex",
        "pathLength",
        "preserveAspectRatio",
        "font-family",
        "font-size",
        "font-weight",
        "text-anchor",
    ]
    attribute_rows = "".join(
        "<rect "
        + " ".join(f'{name}="x{index}"' if name == "id" else f'{name}="1"' for name in attributes)
        + "/>"
        for index in range(205)
    )
    payloads = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        + "<g>" * 33
        + "</g>" * 33
        + "</svg>",
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">' + "<g/>" * 2049 + "</svg>",
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">' + attribute_rows + "</svg>",
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><text>'
        + "x" * (256 * 1024 + 1)
        + "</text></svg>",
    ]

    for index, payload in enumerate(payloads):
        repo_root = create_repo(tmp_path / str(index), [original_svg_entry()])
        write_asset(repo_root, "files/original-diagrams/map.svg", payload.encode())
        write_lock(repo_root, [])
        assert any("SVG" in error for error in audit_assets(repo_root))


def test_safe_static_svg_with_gradient_fragment_and_use_passes_fetch_and_audit(
    tmp_path: Path,
) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"
  role="img" aria-label="MM2R location diagram">
  <title>Location diagram</title>
  <desc>Static guide diagram</desc>
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#fff"/>
      <stop offset="1" stop-color="#09f"/>
    </linearGradient>
    <symbol id="pin" viewBox="0 0 10 10"><path d="M0 0 L10 0 L5 10 Z"/></symbol>
  </defs>
  <rect x="0" y="0" width="640" height="360" fill="url(#sky)"/>
  <use href="#pin" x="20" y="30" width="10" height="10"/>
  <text x="40" y="50" font-size="16"><tspan>玛多</tspan></text>
</svg>""".encode()
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)

    summary = fetch_assets(repo_root)

    assert summary == {"downloaded": 0, "local": 1, "locked": 1}
    assert audit_assets(repo_root) == []


def svg_with_exact_attribute_characters(total: int) -> bytes:
    root_characters = len("width") + len("1") + len("height") + len("1")
    label_names = 2 * len("aria-label")
    value_characters = total - root_characters - label_names
    first_length = min(64 * 1024, value_characters)
    second_length = value_characters - first_length
    assert 0 <= second_length <= 64 * 1024
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        f'<rect aria-label="{"a" * first_length}"/>'
        f'<rect aria-label="{"b" * second_length}"/>'
        "</svg>"
    ).encode()


def test_svg_attribute_character_limit_is_inclusive(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    write_asset(
        repo_root,
        "files/original-diagrams/map.svg",
        svg_with_exact_attribute_characters(128 * 1024),
    )

    summary = fetch_assets(repo_root)

    assert summary == {"downloaded": 0, "local": 1, "locked": 1}
    assert audit_assets(repo_root) == []


def test_svg_rejects_total_attribute_characters_above_limit(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    write_asset(
        repo_root,
        "files/original-diagrams/map.svg",
        svg_with_exact_attribute_characters(128 * 1024 + 1),
    )
    write_lock(repo_root, [])

    assert any("attribute characters" in error for error in audit_assets(repo_root))
    with pytest.raises(AssetPipelineError, match="attribute characters"):
        fetch_assets(repo_root)


def test_svg_rejects_single_attribute_value_above_limit(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        f'<rect aria-label="{"a" * (64 * 1024 + 1)}"/>'
        "</svg>"
    ).encode()
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)
    write_lock(repo_root, [])

    assert any("single attribute value" in error for error in audit_assets(repo_root))
    with pytest.raises(AssetPipelineError, match="single attribute value"):
        fetch_assets(repo_root)


def test_svg_rejects_420kb_path_in_fetch_and_audit(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    path_data = "M0 0 " + "L1 1 " * 84_000
    assert len(path_data) > 420_000
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        f'<path d="{path_data}"/></svg>'
    ).encode()
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)
    write_lock(repo_root, [])

    assert any("single attribute value" in error for error in audit_assets(repo_root))
    with pytest.raises(AssetPipelineError, match="single attribute value"):
        fetch_assets(repo_root)


def test_svg_can_use_integer_viewbox_dimensions(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360"><use href="#marker"/></svg>'
    )
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)
    with mock_client(lambda request: pytest.fail(str(request.url))) as client:
        fetch_assets(repo_root, client=client, resolver=public_resolver)
    assert audit_assets(repo_root) == []


@pytest.mark.parametrize(
    "view_box",
    [
        "NaN 0 640 360",
        "0.5 0 640 360",
        "0 0 640.0 360",
        "0 0 0 360",
        "0 0 -1 360",
        "0,,0,640,360",
        "0 0 640 360 trailing",
    ],
)
def test_svg_viewbox_requires_four_strict_integer_values(tmp_path: Path, view_box: str) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        f'<symbol id="marker" viewBox="{view_box}"/></svg>'
    ).encode()
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)
    write_lock(repo_root, [])

    assert any("viewBox" in error for error in audit_assets(repo_root))
    with pytest.raises(AssetPipelineError, match="viewBox"):
        fetch_assets(repo_root)


@pytest.mark.parametrize("text", ["safe\u200btext", "safe\u2060text", "safe\ufefftext"])
def test_svg_text_rejects_invisible_format_characters(tmp_path: Path, text: str) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry()])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><text>{text}</text></svg>'
    ).encode()
    write_asset(repo_root, "files/original-diagrams/map.svg", svg)
    write_lock(repo_root, [])

    assert any("SVG text" in error for error in audit_assets(repo_root))
    with pytest.raises(AssetPipelineError, match="SVG text"):
        fetch_assets(repo_root)


def test_parent_symlink_is_rejected(tmp_path: Path) -> None:
    repo_root = create_repo(tmp_path, [original_svg_entry("files/original-diagrams/map.svg")])
    files = asset_root(repo_root) / "files"
    outside = tmp_path / "outside"
    outside.mkdir()
    (files / "original-diagrams").symlink_to(outside, target_is_directory=True)
    (outside / "map.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
        encoding="utf-8",
    )
    write_lock(repo_root, [])
    assert any("symlink" in error for error in audit_assets(repo_root))


def test_temp_creation_rechecks_every_ancestor_after_mkdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(
        tmp_path,
        [entry(local_path="files/downloads/licensed-map.png")],
    )
    root = asset_root(repo_root)
    moved_root = tmp_path / "moved-assets"
    outside_root = tmp_path / "outside-assets"
    (outside_root / "files").mkdir(parents=True)
    expected_parent = root / "files/downloads"
    original_mkdir = Path.mkdir
    swapped = False

    def swap_root_during_mkdir(
        path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
    ) -> None:
        nonlocal swapped
        if path == expected_parent and not swapped:
            swapped = True
            root.rename(moved_root)
            root.symlink_to(outside_root, target_is_directory=True)
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    def reject_temp_creation(*_args: object, **_kwargs: object) -> object:
        pytest.fail("temporary file creation followed a swapped ancestor symlink")

    monkeypatch.setattr(Path, "mkdir", swap_root_during_mkdir)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", reject_temp_creation)

    with mock_client(png_response) as client, pytest.raises(AssetPipelineError, match="symlink"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)


def test_download_keeps_open_temp_inode_when_path_is_swapped_to_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = create_repo(tmp_path, [entry()])
    external = tmp_path / "external.png"
    external.write_bytes(b"outside-must-not-change")
    original_stream = asset_pipeline._stream_response
    swapped_path: Path | None = None

    def swap_path_before_stream(
        response: httpx.Response,
        destination: BinaryIO | Path,
        *,
        asset_id: str,
        url: str,
    ) -> tuple[int, str]:
        nonlocal swapped_path
        if isinstance(destination, Path):
            path = destination
        else:
            path = Path(cast(str, destination.name))
        path.unlink()
        path.symlink_to(external)
        swapped_path = path
        return original_stream(
            response,
            cast(BinaryIO, destination),
            asset_id=asset_id,
            url=url,
        )

    monkeypatch.setattr(asset_pipeline, "_stream_response", swap_path_before_stream)

    with mock_client(png_response) as client, pytest.raises(AssetPipelineError, match="symlink"):
        fetch_assets(repo_root, client=client, resolver=public_resolver)

    assert external.read_bytes() == b"outside-must-not-change"
    assert swapped_path is not None
    assert not swapped_path.exists()


def test_cli_labels_asset_failures_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root = create_repo(tmp_path, [entry()])

    assert main(["asset-audit", "--repo-root", str(repo_root)]) == 1
    output = capsys.readouterr().out
    assert output.startswith("asset audit error:")
    assert "Traceback" not in output

    assert main(["asset-fetch", "--repo-root", str(repo_root)]) == 1
    output = capsys.readouterr().out
    assert output.startswith("asset fetch error:")
    assert "Traceback" not in output


def test_repository_manifest_fetches_zero_and_audits_deterministically(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    repository_lock = asset_root(repository_root) / "lock.json"
    original_lock = repository_lock.read_bytes()
    original_mtime_ns = repository_lock.stat().st_mtime_ns
    isolated_repo = tmp_path / "repo"
    shutil.copytree(asset_root(repository_root), asset_root(isolated_repo))
    shutil.copytree(
        repository_root / "data/interim/mm2r/0.99",
        isolated_repo / "data/interim/mm2r/0.99",
    )

    def reject_dns(host: str) -> list[str]:
        pytest.fail(f"repository manifest must not resolve a network host: {host}")

    def reject_client(**_kwargs: object) -> httpx.Client:
        pytest.fail("repository manifest must not create an HTTP client")

    summary = fetch_assets(
        isolated_repo,
        client_factory=reject_client,
        resolver=reject_dns,
    )
    first = (asset_root(isolated_repo) / "lock.json").read_bytes()
    first_audit = audit_assets(isolated_repo)
    summary_again = fetch_assets(
        isolated_repo,
        client_factory=reject_client,
        resolver=reject_dns,
    )
    second = (asset_root(isolated_repo) / "lock.json").read_bytes()
    second_audit = audit_assets(isolated_repo)

    assert summary == summary_again == {"downloaded": 0, "local": 0, "locked": 0}
    assert first == second
    assert first_audit == second_audit == []
    assert repository_lock.read_bytes() == original_lock
    assert repository_lock.stat().st_mtime_ns == original_mtime_ns
