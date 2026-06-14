# bundlemap

Pulls API endpoints out of built JS bundles and prepares fuzzing artifacts. The frontend already knows every address it talks to — they're right there in the source, just need to be extracted and sorted by interest.

Takes a local `dist/` folder or fetches `.js` by URL, parses it, and writes `endpoints.json` (plus `ffuf` wordlists with `--fuzz`). Add `--headless` to also capture live browser requests on top of static analysis. For interpreting the output, see [GUIDE.md](GUIDE.md).

## Install

### Static mode (default, no extra dependencies)

```bash
pip install -e .
```

### Hybrid mode (static + headless browser)

```bash
pip install -e '.[headless]'
python -m playwright install chromium
```

## Usage

```bash
# Local folder, no network, with ffuf artifacts
bundlemap ./dist --out out --fuzz --no-fetch

# Remote target (scope required; fetches HTML and linked .js files)
bundlemap https://app.example.com/ --scope example.com --out out --fuzz

# Only IDOR + BFLA surface, sorted by risk
bundlemap https://app.example.com/ --scope example.com --tag idor --tag bfla

# Hybrid: static bundle analysis + live browser requests merged into one report
bundlemap https://app.example.com/ --scope example.com --headless --out out --fuzz
```

## Flags

| Flag | Description |
|---|---|
| `--scope DOMAIN` | Allowed domain for fetching (repeatable); required for URL input. |
| `--out DIR` | Output directory (default: `out`); created automatically if it doesn't exist. |
| `--fuzz` | Also write `ffuf` wordlists. |
| `--no-fetch` | Local files only, no network. |
| `--min-confidence {low,medium,high}` | Drop endpoints below this confidence level. |
| `--tag CLASS` | Keep only endpoints with this tag, e.g. idor/bfla/ssrf (repeatable). |
| `--method METHOD` | Keep only endpoints with this HTTP method, e.g. GET/POST (repeatable). |
| `--timeout SECONDS` | HTTP request timeout (default: `10.0`). |
| `--quiet` | Suppress stdout table, only write files. |
| `--headless` | Hybrid mode: runs static analysis AND captures live browser requests; requires `.[headless]` extra. |
| `--wait SECONDS` | Extra wait time after page load in headless mode (default: `3.0`). |
| `--version` | Show version and exit. |
