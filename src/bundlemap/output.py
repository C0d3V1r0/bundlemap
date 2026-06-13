"""Reporters: canonical JSON, ffuf fuzzing artifacts, and stdout summary."""

import json
from collections import Counter
from pathlib import Path

from bundlemap.models import Endpoint

_W_METHOD = 6
_W_CONF = 6
_W_TAGS = 22


def write_endpoints_json(endpoints: list[Endpoint], out_dir: Path) -> None:
    """Save the endpoints as endpoints.json in the output directory."""
    payload = [_to_dict(ep) for ep in endpoints]

    (out_dir / "endpoints.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_fuzz_artifacts(endpoints: list[Endpoint], out_dir: Path) -> None:
    """Save paths.txt and params.txt wordlists for ffuf in the output directory."""
    paths = sorted({ep.path for ep in endpoints})
    params = sorted(
        {p for ep in endpoints for p in (*ep.path_params, *ep.query_params, *ep.body_fields)}
    )

    (out_dir / "paths.txt").write_text("\n".join(paths) + "\n" if paths else "", encoding="utf-8")
    (out_dir / "params.txt").write_text(
        "\n".join(params) + "\n" if params else "", encoding="utf-8"
    )


def print_summary(endpoints: list[Endpoint]) -> None:
    """Print the ranked endpoint table and per-tag counts to stdout."""
    print(f"{'METHOD':{_W_METHOD}}  {'CONF':{_W_CONF}}  {'TAGS':{_W_TAGS}}  PATH")

    for ep in endpoints:
        print(
            f"{ep.method:{_W_METHOD}}  {ep.confidence.value:{_W_CONF}}"
            f"  {','.join(ep.tags):{_W_TAGS}}  {ep.path}"
        )

    counts = Counter(t for ep in endpoints for t in ep.tags)
    by_class = ", ".join(f"{t}={n}" for t, n in counts.most_common())

    print(f"\n{len(endpoints)} endpoint(s)." + (f"  [{by_class}]" if by_class else ""))


def _to_dict(ep: Endpoint) -> dict[str, object]:

    return {
        "method": ep.method,
        "path": ep.path,
        "path_params": list(ep.path_params),
        "query_params": list(ep.query_params),
        "body_fields": list(ep.body_fields),
        "confidence": ep.confidence.value,
        "tags": list(ep.tags),
        "origins": list(ep.origins),
    }
