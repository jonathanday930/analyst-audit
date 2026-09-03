import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import trafilatura

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5


class BlogFetchError(RuntimeError):
    pass


def normalized_domain(hostname: str) -> str:
    return hostname.lower().rstrip(".").removeprefix("www.")


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port
    netloc = host if port is None or (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80) else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _validate_public_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BlogFetchError("Blog URL must use http or https.")
    if parsed.username or parsed.password:
        raise BlogFetchError("Blog URLs cannot contain credentials.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise BlogFetchError("Blog URL has an invalid port.") from exc
    if port not in {None, 80, 443}:
        raise BlogFetchError("Blog URL uses a disallowed port.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise BlogFetchError("Blog host could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise BlogFetchError("Blog URL must resolve only to public internet addresses.")


def _html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "Blog post"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip() or "Blog post"


@dataclass
class BlogPost:
    url: str
    domain: str
    title: str
    content: str


def fetch_blog_post(url: str, *, client: httpx.Client | None = None) -> BlogPost:
    current = canonicalize_url(url)
    own_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0), headers={"User-Agent": "AnalystAudit/0.1"})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            _validate_public_http_url(current)
            with http.stream("GET", current, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise BlogFetchError("Blog redirect had no destination.")
                    current = canonicalize_url(urljoin(current, location))
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise BlogFetchError(f"Blog returned HTTP {response.status_code}.") from exc
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    raise BlogFetchError("URL did not return an HTML page.")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise BlogFetchError("Blog page is too large to process.")
                    chunks.append(chunk)
                html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                article = trafilatura.extract(html, include_comments=False, include_tables=False)
                if not article or len(article.strip()) < 40:
                    raise BlogFetchError("Couldn't extract an article body from this page.")
                canonical = canonicalize_url(str(response.url))
                return BlogPost(
                    url=canonical,
                    domain=normalized_domain(urlsplit(canonical).hostname or ""),
                    title=_html_title(html),
                    content=article.strip(),
                )
        raise BlogFetchError("Blog URL redirected too many times.")
    except httpx.RequestError as exc:
        raise BlogFetchError("Couldn't fetch this blog post.") from exc
    finally:
        if own_client:
            http.close()
