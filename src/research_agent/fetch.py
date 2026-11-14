"""Bounded public web page fetching and lightweight text extraction."""

from __future__ import annotations

import ipaddress
import socket
from http.client import HTTPConnection, HTTPSConnection
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPHandler, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .models import FetchedPage


class PageFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


class FetchError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _public_addresses(host: str, port: int):
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("dns_failure", "Could not resolve the page hostname.") from exc
    if not addresses:
        raise FetchError("dns_failure", "The page hostname had no addresses.")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        mapped = getattr(ip, "ipv4_mapped", None)
        if not ip.is_global or (mapped is not None and not mapped.is_global):
            raise FetchError("private_network_blocked", "The URL resolves to a non public address.", retryable=False)
    return addresses


def _connect_public(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    # Use the exact checked numeric address; a second DNS lookup permits rebinding.
    host, port = address
    addresses = _public_addresses(host, port)
    last_error = None
    for family, kind, protocol, _, sockaddr in addresses:
        connection = socket.socket(family, kind, protocol)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(sockaddr)
            return connection
        except OSError as exc:
            last_error = exc
            connection.close()
    raise last_error or OSError("Could not connect to the public page.")


class _PublicHTTPConnection(HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        # Preserve original-host SNI and normal TLS certificate verification.
        return self.do_open(_PublicHTTPSConnection, req, context=self._context)


class _VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {
        "article", "aside", "blockquote", "br", "div", "footer", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "p", "pre",
        "section", "table", "td", "th", "tr",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if not self._skip_depth and tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if not self._skip_depth and tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if not self._skip_depth and not self._in_title:
            self._parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self._title_parts).split())

    @property
    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)


def validate_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FetchError("invalid_scheme", "Only http and https URLs are allowed.", retryable=False)
    if not parts.hostname:
        raise FetchError("invalid_url", "The URL has no hostname.", retryable=False)
    if parts.username or parts.password:
        raise FetchError("credentials_not_allowed", "URLs containing credentials are rejected.", retryable=False)
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("invalid_url", "The URL has an invalid port.", retryable=False) from exc
    _public_addresses(parts.hostname, port)


class SafePageFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: int = 12,
        max_bytes: int = 2_000_000,
        max_chars: int = 24_000,
        max_redirects: int = 3,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.max_chars = max_chars
        self.max_redirects = max_redirects
        self._opener = build_opener(ProxyHandler({}), _NoRedirect(), _PublicHTTPHandler(), _PublicHTTPSHandler())

    def fetch(self, url: str) -> FetchedPage:
        current = url
        for redirect_count in range(self.max_redirects + 1):
            validate_public_url(current)
            request = Request(
                current,
                headers={
                    "User-Agent": "BoundedResearchAgent/1.0 (+educational project)",
                    "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9,*/*;q=0.1",
                },
            )
            try:
                response = self._opener.open(request, timeout=self.timeout_seconds)
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    if not location:
                        raise FetchError("bad_redirect", "Redirect response had no Location header.")
                    if redirect_count >= self.max_redirects:
                        raise FetchError("too_many_redirects", "The page redirected too many times.")
                    current = urljoin(current, location)
                    continue
                raise FetchError("http_error", f"The server returned HTTP {exc.code}.", retryable=exc.code >= 500) from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise FetchError("network_error", f"Could not fetch the page: {exc}") from exc

            with response:
                content_type = response.headers.get_content_type().lower()
                if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                    raise FetchError(
                        "unsupported_content_type",
                        f"Unsupported content type: {content_type}.",
                        retryable=False,
                    )
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > self.max_bytes:
                    raise FetchError("page_too_large", "The page exceeds the download limit.", retryable=False)
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise FetchError("page_too_large", "The page exceeds the download limit.", retryable=False)
                charset = response.headers.get_content_charset() or "utf-8"

            decoded = raw.decode(charset, errors="replace")
            if content_type == "text/plain":
                title = urlsplit(current).hostname or current
                text = "\n".join(line.strip() for line in decoded.splitlines() if line.strip())
            else:
                parser = _VisibleTextParser()
                parser.feed(decoded)
                title = parser.title or urlsplit(current).hostname or current
                text = parser.text

            text = text[: self.max_chars].strip()
            if len(text) < 80:
                raise FetchError("empty_extraction", "The page contained too little extractable text.")
            return FetchedPage(title=title, url=current, text=text)

        raise FetchError("too_many_redirects", "The page redirected too many times.")


class StaticPageFetcher:
    """Deterministic fetcher for tests and offline demonstrations."""

    def __init__(self, pages: dict[str, FetchedPage | FetchError]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> FetchedPage:
        value = self.pages.get(url)
        if value is None:
            raise FetchError("not_found", "No static page was configured for this URL.", retryable=False)
        if isinstance(value, FetchError):
            raise value
        return value
