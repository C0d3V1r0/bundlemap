"""Heuristic JS-text extractors and normalisation into Endpoint records."""

import itertools
import re
from collections import defaultdict

from bundlemap.bases import Bases, apply_base
from bundlemap.models import Confidence, Endpoint, Observation, SourceFile, strongest

_ASSET_RE = re.compile(r"\.(?:js|css|png|jpe?g|svg|gif|woff2?|ico|map|json)(?:\?|$)", re.I)
_LITERAL_RE = re.compile(r"""['"`](https?://[^'"`\s]+|/[A-Za-z0-9_\-./:${}]+)['"`]""")
# Options capture is bounded to 2048 non-`}` chars: avoids scanning to a distant or missing `}`.
# TODO: handle $.ajax and dynamic URL construction
_FETCH_RE = re.compile(r"""fetch\(\s*['"`]([^'"`]+)['"`]\s*(?:,\s*\{([^}]{0,2048})\})?""")
_AXIOS_RE = re.compile(r"""axios\.(get|post|put|delete|patch|head)\(\s*['"`]([^'"`]+)['"`]""", re.I)
_XHR_RE = re.compile(r"""\.open\(\s*['"]([A-Za-z]+)['"]\s*,\s*['"`]([^'"`]+)['"`]""")
_METHOD_RE = re.compile(r"""method\s*:\s*['"]([A-Za-z]+)['"]""")
_KEY_RE = re.compile(r"""['"]?([A-Za-z_]\w*)['"]?\s*:""")
# Strip nested headers/params objects before extracting body field keys
_STRIP_NESTED_RE = re.compile(r"\b(?:headers|params)\s*:\s*\{[^}]*\}?", re.I)
_PARAM_RE = re.compile(r"\$\{(\w+)\}|:(\w+)")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_STRIP_VAR_RE = re.compile(r"\$\{[^}]*\}")
_API_RE = re.compile(r"/api(?:/|$|\?)")

# fetch/axios option keys present in the call but not actual request body fields.
_OPTION_KEYS = frozenset(
    {
        "method",
        "headers",
        "body",
        "credentials",
        "mode",
        "cache",
        "signal",
        "redirect",
        "referrer",
        "data",
        "params",
        "url",
        "withcredentials",
    }
)


def extract_all(src: SourceFile) -> list[Observation]:
    """Run every extractor over a source file and return its raw observations."""
    return _extract_urls(src) + _extract_callsites(src)


def normalize(observations: list[Observation], bases: Bases) -> list[Endpoint]:
    """Merge and deduplicate observations into a sorted list of endpoints."""
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)

    for obs in observations:
        if path := apply_base(obs.path, bases):
            groups[(obs.method or "GET", path)].append(obs)

    endpoints = [_merge(method, path, group) for (method, path), group in groups.items()]

    return sorted(_drop_shadowed(endpoints), key=lambda e: (e.path, e.method))


def _extract_urls(src: SourceFile) -> list[Observation]:
    out: list[Observation] = []

    for match in _LITERAL_RE.finditer(src.text):
        literal = match.group(1)

        if _ASSET_RE.search(literal):
            continue

        confidence = _classify(literal)

        if confidence is not None:
            out.append(Observation(None, literal, (), confidence, src.origin))

    return out


def _extract_callsites(src: SourceFile) -> list[Observation]:
    out: list[Observation] = []

    for match in _FETCH_RE.finditer(src.text):
        opts = match.group(2) or ""
        method_match = _METHOD_RE.search(opts)
        method = method_match.group(1).upper() if method_match else "GET"

        out.append(
            Observation(method, match.group(1), _request_fields(opts), Confidence.HIGH, src.origin)
        )

    for match in itertools.chain(_AXIOS_RE.finditer(src.text), _XHR_RE.finditer(src.text)):
        out.append(
            Observation(match.group(1).upper(), match.group(2), (), Confidence.HIGH, src.origin)
        )

    return out


def _request_fields(opts: str) -> tuple[str, ...]:
    if not opts:  # common case: fetch/axios call with no options object
        return ()

    opts = _STRIP_NESTED_RE.sub("", opts)
    keys = dict.fromkeys(_KEY_RE.findall(opts))

    return tuple(key for key in keys if key.lower() not in _OPTION_KEYS)


def _drop_shadowed(endpoints: list[Endpoint]) -> list[Endpoint]:
    by_path: dict[str, list[Confidence]] = defaultdict(list)

    for ep in endpoints:
        by_path[ep.path].append(ep.confidence)

    top = {path: strongest(confs) for path, confs in by_path.items()}

    return [ep for ep in endpoints if ep.confidence == top[ep.path]]


def _merge(method: str, path: str, group: list[Observation]) -> Endpoint:
    fields = tuple(sorted({f for obs in group for f in obs.fields}))

    return Endpoint(
        method=method,
        path=path,
        path_params=_path_params(path),
        query_params=_query_params(path),
        body_fields=fields,
        confidence=strongest(obs.confidence for obs in group),
        origins=tuple(sorted({obs.origin for obs in group})),
    )


def _path_params(path: str) -> tuple[str, ...]:
    return tuple(a or b for a, b in _PARAM_RE.findall(path))


def _query_params(path: str) -> tuple[str, ...]:
    query = path.partition("?")[2]

    return tuple(name for part in query.split("&") if (name := part.split("=")[0]))


def _classify(literal: str) -> Confidence | None:
    if literal.startswith(("http://", "https://")):
        return Confidence.MEDIUM if _API_RE.search(literal) else None
        # otherwise third-party/ns
    if not _ALNUM_RE.search(_STRIP_VAR_RE.sub("", literal)):
        return None  # degenerate: only slashes / template variables ("//", "/${x}")

    return Confidence.MEDIUM if _API_RE.search(literal) else Confidence.LOW
