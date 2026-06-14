# bundlemap guide

`bundlemap` parses built JS bundles and builds a map of API endpoints: method, path, parameters, body fields, sorted by risk. For installation and flags, see [README.md](README.md); this doc covers how to read the output.

## stdout table

```
METHOD  CONF    TAGS                    PATH
POST    high    bfla                    /api/admin/users/${id}/role
GET     medium  idor                    /api/orders/${orderId}
GET     low                             /app/settings
```

- **METHOD** — HTTP method (defaults to GET if the call site wasn't found).
- **CONF** — confidence level (see below).
- **TAGS** — which attack classes to look at; empty means nothing matched.
- **PATH** — normalized path with path parameters as `${name}`.

Bottom line: `57 endpoint(s). [idor=12, bfla=5, ssrf=3, ...]`

## confidence — where the endpoint came from

Filter with `--min-confidence`; use `medium` for a clean API-only map.

| Level | Source | What it means |
|---|---|---|
| `high` | Live request (headless) or call site (`fetch`/`axios`/`xhr.open`) | Almost certainly a live endpoint — method and body fields are known. |
| `medium` | Bare string literal containing `/api` | Looks like an API path, but no call site visible. |
| `low` | Other bare path literals | Likely frontend routes or constants — noisy. |

## Hybrid mode (`--headless`)

`--headless` runs both pipelines and merges the results:

1. **Static** — parses the JS bundle; finds hidden and auth-gated routes that the browser never requests on a cold load.
2. **Headless** — opens the target in Chromium and intercepts every live network request; captured endpoints get `high` confidence.

Duplicates are merged automatically: if the same `(method, path)` appears in both, the highest confidence wins and body fields are unioned.

```bash
bundlemap https://app.example.com/ --scope example.com --headless --fuzz
```

`--wait` adds extra seconds after `networkidle` to catch deferred requests (default: `3.0`).

Requires the `headless` extra:

```bash
pip install -e '.[headless]'
python -m playwright install chromium
```

## Tags — what to look at

Filter with `--tag`.

| Tag | What it means |
|---|---|
| `idor` | Path has an id-like segment (`${id}`, `:id`). Try swapping it for someone else's — might return their data. |
| `bfla` | Endpoint is under admin/manage/roles and mutates data. Try calling it without privileges. |
| `ssrf` | Parameter accepts a URL (`url`, `webhook`, `callback`). The server might follow your address. |
| `open-redirect` | Parameter controls a redirect (`redirect`, `next`). Could send a user to an external site. |
| `upload` | File upload endpoint. Try uploading something unexpected. |
| `auth` | Login, password, session, OAuth. Look for logic flaws in the auth flow. |

## What's in `out/`

| File | Contents |
|---|---|
| `endpoints.json` | Full list — method, path, params, body fields, confidence, tags, origins. |
| `paths.txt` | One path per line — wordlist for `ffuf -w` (only with `--fuzz`). |
| `params.txt` | Unique parameter names across all endpoints (only with `--fuzz`). |
