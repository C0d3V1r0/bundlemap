"""Resolve and substitute base-URL placeholders at the start of extracted paths."""

import re
from collections.abc import Iterable

Bases = dict[str, str]  # base-URL variable name -> its string literal value from the bundle

_LEADING_VAR_RE = re.compile(r"^\$\{([^}]+)\}")  # leading ${...} segment -> base-URL placeholder
_CLEAN_BASE_RE = re.compile(r"^[\w\-./:%@~+]*$")  # base must be URL-safe (no CR/LF/spaces)
_MAX_BASES = 64


def resolve_bases(paths: Iterable[str], texts: Iterable[str]) -> Bases:
    """Map each leading base variable to the string literal assigned to it in the bundle texts."""

    names = {m[1] for p in paths if (m := _LEADING_VAR_RE.match(p)) and "." not in m[1]}
    all_texts = list(texts)

    bases: Bases = {}

    for name in sorted(names)[:_MAX_BASES]:
        assign = re.compile(rf"\b{re.escape(name)}\s*[:=]\s*['\"]([^'\"]*)['\"]")
        hit = next((m[1] for t in all_texts if (m := assign.search(t))), None)

        if hit is not None and _CLEAN_BASE_RE.match(hit):
            bases[name] = hit

    return bases


def apply_base(path: str, bases: Bases) -> str:
    """Substitute leading ${base} placeholders; inner path params are untouched."""

    while path.startswith("${") and (match := _LEADING_VAR_RE.match(path)):
        path = bases.get(match.group(1), "").rstrip("/") + path[match.end() :]

    return path
