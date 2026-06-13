"""CLI entry point: argument parsing, scan dispatch, and output writing."""

import argparse
import logging
from pathlib import Path

from bundlemap.bases import resolve_bases
from bundlemap.extract import extract_all, normalize
from bundlemap.loader import StdlibFetcher, load
from bundlemap.models import BundlemapError, Confidence, Endpoint, meets
from bundlemap.output import print_summary, write_endpoints_json, write_fuzz_artifacts
from bundlemap.surface import classify

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Return the configured command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="bundlemap",
        description="Static JS-bundle endpoint discovery.",
    )

    parser.add_argument(
        "target",
        help="URL or local path to a bundle / dist directory",
    )

    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        metavar="DOMAIN",
        help="allowed domain for fetching (repeatable); required for URL input",
    )

    parser.add_argument("--out", help="output directory (default: out)")
    parser.add_argument("--fuzz", action="store_true", help="also write ffuf fuzz artifacts")
    parser.add_argument(
        "--no-fetch", action="store_true", help="local files only; never hit the network"
    )

    parser.add_argument(
        "--min-confidence",
        choices=[c.value for c in Confidence],
        default="low",
        help="drop endpoints below this confidence",
    )

    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="CLASS",
        help="keep only endpoints tagged with CLASS, e.g. idor/bfla/ssrf (repeatable)",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="HTTP request timeout in seconds (default: 10.0)",
    )

    parser.add_argument(
        "--method",
        action="append",
        default=[],
        metavar="METHOD",
        help="keep only endpoints with this HTTP method, e.g. GET/POST (repeatable)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress stdout table; only write output files",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the scan from command-line arguments and return the process exit code."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    try:
        return _run_scan(args)
    except BundlemapError as exc:
        log.error("%s", exc)

        return 2


def _run_scan(args: argparse.Namespace) -> int:
    if args.timeout <= 0:
        raise BundlemapError(f"--timeout must be positive, got {args.timeout}")

    sources = load(
        args.target,
        scope=args.scope,
        fetcher=StdlibFetcher(),
        allow_fetch=not args.no_fetch,
        timeout=args.timeout,
    )

    observations = [obs for src in sources for obs in extract_all(src)]

    bases = resolve_bases(
        (obs.path for obs in observations),
        (src.text for src in sources),
    )

    ranked = classify(normalize(observations, bases))
    endpoints = _filter(ranked, args)
    out_dir = Path(args.out or "out")
    out_dir.mkdir(parents=True, exist_ok=True)

    write_endpoints_json(endpoints, out_dir)

    if args.fuzz:
        write_fuzz_artifacts(endpoints, out_dir)

    if not args.quiet:
        print_summary(endpoints)

    return 0


def _filter(endpoints: list[Endpoint], args: argparse.Namespace) -> list[Endpoint]:
    # filters applied in order: confidence -> tags -> methods
    minimum = Confidence(args.min_confidence)
    result = [ep for ep in endpoints if meets(ep.confidence, minimum)]

    if args.tag:
        wanted_tags = set(args.tag)
        result = [ep for ep in result if wanted_tags.intersection(ep.tags)]

    if args.method:
        wanted_methods = {m.upper() for m in args.method}
        result = [ep for ep in result if ep.method in wanted_methods]

    return result


if __name__ == "__main__":
    raise SystemExit(main())
