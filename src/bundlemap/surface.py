"""Bug-class tagging and risk ranking for extracted endpoints."""

import re
from dataclasses import replace

from bundlemap.models import Confidence, Endpoint

_DYN_SEG_RE = re.compile(r"\$\{([^}]*)\}|/:([A-Za-z_]\w*)")  # dynamic segments: ${...} or :name
# word boundaries matter — "website" would match ssrf without them
_PRIV_NS_RE = re.compile(r"/(?:admin|adminka|internal|manage|superuser|backend)(?:/|$)", re.I)
_BFLA_KW_RE = re.compile(r"\b(?:role|permission|grant|impersonate|approve|trigger|scheduler)", re.I)
_SSRF_RE = re.compile(r"\b(?:url|callback|webhook|proxy|fetch|parse|crawl|scrape)", re.I)
_REDIRECT_RE = re.compile(r"redirect|return_?url|\bnext\b|\bgoto\b", re.I)
_UPLOAD_RE = re.compile(
    r"\b(?:upload|attachment|avatar)|/(?:file|media)|(?:^|/)import(?:/|$)", re.I
)
_AUTH_RE = re.compile(
    r"\b(?:login|logout|register|password|oauth|sso|session|otp|2fa|verify|signin|signup)", re.I
)
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ID_NAMES = frozenset({"id", "ids", "uuid", "guid", "slug", "code", "key", "pk"})

# Per-class risk weights; ranking floats privileged/mutating endpoints to the top.
_WEIGHT = {
    "bfla": 5,
    "idor": 4,
    "ssrf": 4,
    "upload": 3,
    "open-redirect": 3,
    "auth": 2,
}

_CONF_BONUS = {Confidence.HIGH: 2, Confidence.MEDIUM: 1, Confidence.LOW: 0}


def _tag(ep: Endpoint) -> tuple[str, ...]:
    """Return the bug-class labels that apply to an endpoint."""
    text = " ".join((ep.path, *ep.query_params, *ep.body_fields, *ep.path_params))
    found: set[str] = set()

    if _has_id_segment(ep.path):
        found.add("idor")

    if _BFLA_KW_RE.search(ep.path) or (ep.method in _MUTATING and _PRIV_NS_RE.search(ep.path)):
        found.add("bfla")

    for klass, pattern in (
        ("ssrf", _SSRF_RE),
        ("open-redirect", _REDIRECT_RE),
        ("upload", _UPLOAD_RE),
        ("auth", _AUTH_RE),
    ):
        if pattern.search(text):
            found.add(klass)

    return tuple(sorted(found))


def classify(endpoints: list[Endpoint]) -> list[Endpoint]:
    """Tag every endpoint and return them ordered from highest to lowest risk."""
    tagged = [replace(ep, tags=_tag(ep)) for ep in endpoints]

    return sorted(tagged, key=lambda e: (-_score(e), e.path, e.method))


def _score(ep: Endpoint) -> int:
    return sum(_WEIGHT.get(t, 0) for t in ep.tags) + _CONF_BONUS[ep.confidence]


def _has_id_segment(path: str) -> bool:
    return any(_is_id_like(brace or colon) for brace, colon in _DYN_SEG_RE.findall(path))


def _is_id_like(name: str) -> bool:

    return (
        name.lower() in _ID_NAMES
        or name.lower().endswith((".id", "_id", ".ids", "_ids"))
        or name.endswith(("Id", "Ids"))  # camelCase userId/logId — case-sensitive, not "valid"
    )
