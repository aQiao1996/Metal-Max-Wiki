import httpx
import pytest

from mmwiki_data.fetcher import FetchError, fetch


def test_fetch_hashes_html() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><table></table></html>",
            request=request,
        )
    )
    with httpx.Client(transport=transport) as client:
        result = fetch(client, "target", "https://example.com/page")

    assert result.content_hash.startswith("sha256:")
    assert result.body.startswith(b"<html>")


def test_fetch_reports_http_failure() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404, request=request))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(FetchError, match=r"target.*404.*example\.com/page"):
            fetch(client, "target", "https://example.com/page")


def test_fetch_rejects_non_html_content() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF",
            request=request,
        )
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(FetchError, match="expected HTML"):
            fetch(client, "manual", "https://example.com/manual.pdf")
