"""Load JS bundles from a local path or URL into SourceFile records."""

import json
import logging
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, build_opener

from bundlemap.models import LoaderError, ScopeError, SourceFile

log = logging.getLogger(__name__)

_SOURCEMAP_MARK = "//# sourceMappingURL="
_DEFAULT_TIMEOUT = 10.0  # seconds — applied to every outbound HTTP request


class Fetcher(Protocol):
    def get(self, url: str, *, timeout: float) -> str: ...


class _NoRedirect(HTTPRedirectHandler):
    """Block redirects — a 3xx response could lead outside the allowed scope (SSRF)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
        return None


_OPENER = build_opener(_NoRedirect)


class StdlibFetcher:
    """urllib-based fetcher: enforces timeout, never follows redirects."""

    def get(self, url: str, *, timeout: float) -> str:
        with _OPENER.open(url, timeout=timeout) as resp:  # noqa: S310
            data: bytes = resp.read()

        return data.decode("utf-8", "replace")


class _ScriptSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()

        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # TODO: also capture inline <script> bodies
        if tag != "script":
            return

        for name, value in attrs:
            if name == "src" and value:
                self.srcs.append(value)


def _in_scope(url: str, scope: list[str]) -> bool:
    """Return True when the URL's hostname belongs to an allowed scope domain."""
    host = urlparse(url).hostname or ""

    return any(host == d or host.endswith("." + d) for d in scope)


def load(
    target: str,
    *,
    scope: list[str],
    fetcher: Fetcher,
    allow_fetch: bool,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[SourceFile]:
    """Load JS source files from a URL or local path into source records."""
    if _is_url(target):
        if not allow_fetch:
            raise LoaderError("URL input requires fetching; remove --no-fetch")

        return _load_url(target, scope=scope, fetcher=fetcher, timeout=timeout)

    return _load_path(Path(target))


def _is_url(target: str) -> bool:
    return urlparse(target).scheme in {"http", "https"}


def _load_url(
    target: str, *, scope: list[str], fetcher: Fetcher, timeout: float
) -> list[SourceFile]:

    if not _in_scope(target, scope):
        raise ScopeError(f"{target} is outside scope {scope}")

    html = fetcher.get(target, timeout=timeout)
    parser = _ScriptSrcParser()
    parser.feed(html)
    sources: list[SourceFile] = []

    for src in parser.srcs:
        url = urljoin(target, src)

        if not url.endswith(".js") or not _in_scope(url, scope):
            continue

        sources.extend(_fetch_js(url, fetcher=fetcher, timeout=timeout))

    return sources


def _fetch_js(url: str, *, fetcher: Fetcher, timeout: float) -> list[SourceFile]:
    try:
        text = fetcher.get(url, timeout=timeout)
    except OSError as exc:
        log.warning("skip %s: %s", url, exc)

        return []

    smap = _try_fetch_map(url, text, fetcher=fetcher, timeout=timeout)

    return _build_sources(url, text, smap)


def _try_fetch_map(url: str, text: str, *, fetcher: Fetcher, timeout: float) -> str | None:
    mark = text.find(_SOURCEMAP_MARK)

    if mark == -1:
        return None

    rest = text[mark + len(_SOURCEMAP_MARK) :].split()
    # relative maps only — absolute or protocol-relative URLs could escape scope

    if not rest or urlparse(rest[0]).scheme or rest[0].startswith("//"):
        return None

    try:
        return fetcher.get(urljoin(url, rest[0]), timeout=timeout)
    except OSError as exc:
        log.warning("skip sourcemap for %s: %s", url, exc)

        return None


def _load_path(root: Path) -> list[SourceFile]:

    if not root.exists():
        raise LoaderError(f"path not found: {root}")

    files = [root] if root.is_file() else sorted(root.rglob("*.js"))
    sources: list[SourceFile] = []

    for js in files:
        try:
            text = js.read_text("utf-8", "replace")
        except OSError as exc:
            log.warning("skip %s: %s", js, exc)

            continue

        sources.extend(_build_sources(str(js), text, _read_sibling_map(js)))

    return sources


def _read_sibling_map(js: Path) -> str | None:
    sibling = js.with_name(js.name + ".map")

    return sibling.read_text("utf-8", "replace") if sibling.is_file() else None


def _build_sources(origin: str, text: str, smap: str | None) -> list[SourceFile]:
    contents = _sourcemap_contents(smap) if smap else []

    if contents:
        return [SourceFile(origin=origin, text=c) for c in contents]

    return [SourceFile(origin=origin, text=text)]


def _sourcemap_contents(smap: str) -> list[str]:
    try:
        data = json.loads(smap)
    except json.JSONDecodeError as exc:
        log.warning("malformed sourcemap ignored: %s", exc)

        return []

    if not isinstance(data, dict):
        return []

    return [c for c in data.get("sourcesContent", []) if isinstance(c, str) and c]
