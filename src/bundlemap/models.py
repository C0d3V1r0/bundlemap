"""Immutable data model, confidence levels, and exception hierarchy."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class Confidence(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def strongest(values: Iterable[Confidence]) -> Confidence:
    """Return the highest confidence level from the given values."""
    return max(values, key=_RANK.__getitem__)


def meets(confidence: Confidence, minimum: Confidence) -> bool:
    """Return True when a confidence is at or above the minimum threshold."""
    return _RANK[confidence] >= _RANK[minimum]


@dataclass(frozen=True, slots=True)
class SourceFile:
    """A single JS source text (bundle or sourcemap-expanded file) with its origin URL/path."""

    origin: str
    text: str


@dataclass(frozen=True, slots=True)
class Observation:
    """Raw extractor finding before deduplication and normalisation into an Endpoint."""

    method: str | None
    path: str
    fields: tuple[str, ...]
    confidence: Confidence
    origin: str


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Normalised endpoint: method, path, parameters, body fields, confidence, and tags."""

    method: str
    path: str
    path_params: tuple[str, ...]
    query_params: tuple[str, ...]
    body_fields: tuple[str, ...]
    confidence: Confidence
    origins: tuple[str, ...]
    tags: tuple[str, ...] = ()  # bug-class candidates (see surface.py); empty until classified


class BundlemapError(Exception):
    """Base for all bundlemap errors."""


class ScopeError(BundlemapError):
    """Raised when a URL falls outside the allowed scope."""


class LoaderError(BundlemapError):
    """Raised when input cannot be loaded into source files."""
