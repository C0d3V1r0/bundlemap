"""Headless browser loader: captures live network requests via Playwright."""

import json
import logging
import re
from urllib.parse import urlparse

from bundlemap.loader import _in_scope
from bundlemap.models import Confidence, Observation, ScopeError

_ASSET_RE = re.compile(r"\.(?:js|css|png|jpe?g|svg|gif|woff2?|ttf|eot|ico|map)(?:\?|$)", re.I)

log = logging.getLogger(__name__)

_DEFAULT_WAIT = 3.0


def load_headless(
    target: str,
    *,
    scope: list[str],
    wait: float = _DEFAULT_WAIT,
    cookies: list[dict[str, str]] | None = None,
) -> list[Observation]:
    """Open target in a headless browser and return all in-scope requests as observations."""

    if not scope:
        raise ScopeError("--scope is required for headless mode")
    if not _in_scope(target, scope):
        raise ScopeError(f"{target} is outside scope {scope}")

    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("playwright is not installed; run: pip install -e '.[headless]'") from exc

    observations: list[Observation] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()

        def on_request(request: object) -> None:
            url = getattr(request, "url", "")

            if not _in_scope(url, scope):
                return

            parsed = urlparse(url)
            path = parsed.path or "/"

            if _ASSET_RE.search(path):
                return
            method: str = getattr(request, "method", "GET")
            fields: tuple[str, ...] = ()
            post_data: str | None = getattr(request, "post_data", None)

            if post_data:
                try:
                    body = json.loads(post_data)

                    if isinstance(body, dict):
                        fields = tuple(body.keys())

                except (json.JSONDecodeError, ValueError):
                    pass

            observations.append(
                Observation(
                    method=method,
                    path=path,
                    fields=fields,
                    confidence=Confidence.HIGH,
                    origin=target,
                )
            )

        page.on("request", on_request)

        try:
            page.goto(target, wait_until="networkidle", timeout=30_000)
        except Exception as exc:
            log.warning("page load incomplete: %s", exc)

        page.wait_for_timeout(int(wait * 1_000))

        browser.close()

    return observations
