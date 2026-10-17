# DataPilot

Version 0.3.0 · CPU local tool · MIT

DataPilot profiles local tabular data without a model service. Import CSV or JSON, inspect inferred values, and get missingness, numeric summaries, pairwise correlations and the original rows behind IQR outlier flags. This is deterministic data-quality analysis; it does not claim to generate AI explanations or make business decisions.

## Try the interface

1. Choose a CSV/JSON file or paste CSV and choose **Preview pasted CSV**.
2. Review the first eight rows and the dataset dimensions. CSV inference converts ordinary decimal/exponent numbers, exact `true`/`false`, and empty cells; leading-zero identifiers remain text.
3. Choose **Profile this table** and inspect missing cells, numeric/mixed columns, relationships and outlier rows.
4. Export the input, full report, or column-summary CSV. Spreadsheet-active text in CSV exports is prefixed with an apostrophe; actual negative numeric values remain numeric.

JSON accepts a row-object array or `{ "rows": [...] }`, with primitive cell values or null. JSON numeric strings remain strings; CSV inference can be disabled to preserve all text. Changing source text/inference clears the loaded table and report until you load/preview again. Results clear on import failure as well, so an earlier report cannot be exported as if it applied to new input.

The synthetic sales example contains a missing revenue and an unusual high-value row. It is invented demonstration data, not a real company's records. Imported/edited data has unverified provenance.

## Run locally

Docker (recommended):

```sh
docker compose up --build
```

Open http://localhost:8000. The interface, API reference at `/docs`, and user guide at `/guide` are served by the same app. The host port binds to localhost. Change only the host side of `8000:8000` if another app uses that port. The container runs as a non-root user with a read-only filesystem.

Python 3.12 or later:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Tests and release gates

```sh
python -m pytest -q
node --test tools/test_ui.mjs
python -m bandit -q -r app
python -m pip_audit -r requirements.txt
```

Node 22 is used for browser-independent CSV/export logic tests; it is not needed to serve the application. Python tests include actual core calculations, validation failures and in-process HTTP integration. They do not establish Docker deployment or browser interaction success. Fresh 0.3.0 evidence belongs in `evidence/improvements-0.3/`. `evidence/rebuild/` records the earlier 0.2.0 rebuild; it does not validate this version. CI includes locked dependency installation, test/security gates, image scanning and secret scanning. Branch protection and release publication remain separate operator actions; no publication success is claimed by this README.

MIT licensed. No paid service or new model download is required. Data is processed by this app server when you run an analysis. Inputs/results are not automatically saved by this application. JSON exports may contain the original input and sensitive values; inspect them before sharing. There is no authentication or rate limiter. Keep the localhost binding or supply access controls before exposing the server.

## Methods and operating details

Read [the complete user guide](docs/USER_GUIDE.md) for calculations, input schemas, limitations and troubleshooting. The same guide is served at `/guide`. The API and browser use the same tested computation path.

API example using explicitly synthetic data:

```sh
curl --fail-with-body http://localhost:8000/analyze -H 'Content-Type: application/json' --data-binary @examples/synthetic.json
```

## Duplicates, uniqueness and frequent values (0.3.0)

The report now shows exact duplicate groups, rows participating in duplicate groups, and **redundant rows** beyond the first row in each group. For a group of three identical rows, participating rows=3 and redundant rows=2. Row key order does not matter. Identity is typed: boolean `true`, number `1` and string `"1"` are different. Numbers `1` and `1.0` are equivalent, as are numeric signed zeros. Absent keys differ from explicit null when comparing whole rows. No rows are deleted automatically.

Column profiles add `absent_count`, `null_count`, `unique_present_count`, `unique_fraction` and typed `top_values`. Existing `missing_count` equals absent + null. Uniqueness and frequency counts exclude both missing kinds, and unique fraction is distinct present values / present cells (null when no present cells exist). Frequency ties retain first-seen order. Boolean/number/string identities are separate even in a mixed column. Values are diagnostics, not recommendations to remove rare categories or duplicate business records.

Bounded detail: show at most 100 duplicate groups and the first 100 zero-based row indices per group; exact group/row/redundant counts and truncation flags remain available. Top values show at most 10 distinct values per column, with string previews capped at 120 characters. Counts and uniqueness use original untruncated values. These bounds prevent repeated values from amplifying report size. Other existing 5000-row/50-column/2 MiB limits remain unchanged. JSON preserves absent keys; CSV cannot represent an absent column key per row, so inferred empty CSV cells are explicit nulls.
