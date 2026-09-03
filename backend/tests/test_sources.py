import socket

import httpx
import pytest

from app.sources.blog import BlogFetchError, canonicalize_url, fetch_blog_post, normalized_domain
from app.sources.fetcher import detect_source_type


def test_source_detection_does_not_accept_youtube_lookalikes() -> None:
    assert detect_source_type("https://youtube.com/watch?v=dQw4w9WgXcQ") == "video"
    assert detect_source_type("https://youtube.com.evil.test/post") == "blog"


def test_blog_url_normalization() -> None:
    assert canonicalize_url("https://Example.COM:443/post?q=1#frag") == "https://example.com/post?q=1"
    assert normalized_domain("WWW.Example.COM.") == "example.com"


def test_blog_fetch_extracts_body(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    html = "<html><head><title>Market call</title></head><body><article><p>" + ("Useful analysis. " * 20) + "</p></article></body></html>"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=html, request=request))
    with httpx.Client(transport=transport) as client:
        post = fetch_blog_post("https://www.example.com/post#x", client=client)
    assert post.domain == "example.com"
    assert post.title == "Market call"
    assert "Useful analysis" in post.content


def test_blog_fetch_blocks_private_addresses(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(BlogFetchError, match="public"):
        fetch_blog_post("http://localhost/admin")


def test_blog_fetch_rejects_non_html(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf", request=request))
    with httpx.Client(transport=transport) as client, pytest.raises(BlogFetchError, match="HTML"):
        fetch_blog_post("https://example.com/file", client=client)
