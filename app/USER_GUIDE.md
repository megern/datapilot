# DataPilot user guide — 0.4.0

DataPilot profiles local tabular data without a model service. Import CSV or JSON, inspect inferred values, and get missingness, numeric summaries, pairwise correlations and the original rows behind IQR outlier flags. This is deterministic data-quality analysis; it does not claim to generate AI explanations or make business decisions.

## Workflow

1. Choose a CSV/JSON file or paste CSV and choose **Preview pasted CSV**.
2. Review the first eight rows and the dataset dimensions. CSV inference converts ordinary decimal/exponent numbers, exact `true`/`false`, and empty cells; leading-zero identifiers remain text.
3. Choose **Profile this table** and inspect missing cells, numeric/mixed columns, relationships and outlier rows.
4. Export the input, full report, or column-summary CSV. Spreadsheet-active text in CSV exports is prefixed with an apostrophe; actual negative numeric values remain numeric.

JSON accepts a row-object array or `{ "rows": [...] }`, with primitive cell values or null. JSON numeric strings remain strings; CSV inference can be disabled to preserve all text. Changing source text/inference clears the loaded table and report until you load/preview again. Results clear on import failure as well, so an earlier report cannot be exported as if it applied to new input.

The synthetic sales example contains a missing revenue and an unusual high-value row. It is invented demonstration data, not a real company's records. Imported/edited data has unverified provenance.

## Statistical methods

Missingness treats absent keys and null cells as missing. A column is numeric only when all present values are numeric and no value is boolean. Numeric strings and mixed columns receive no numeric summary.

Numeric profiles include mean, median, sample standard deviation (undefined for one observation), min/max and linearly interpolated Q1/Q3. Values outside Q1−1.5×IQR or Q3+1.5×IQR are exploratory outlier flags. They are not automatically invalid data. Original row indices are zero-based.

Pearson r uses pairwise complete rows from two numeric columns. Constant columns or fewer than two pairs yield undefined (`null`). Correlation is descriptive, does not imply causation and can be dominated by outliers. The app does not impute cells, train predictive models, test statistical significance or automatically remove outliers.

## CSV handling and bounds

Quoted commas, escaped quotes, CRLF and embedded newlines are accepted. Headers must be nonempty and unique after trimming; every row must have the same field count. Only blank physical lines are ignored. Explicit delimiter-only records and quoted empty cells are preserved as rows; with CSV inference enabled, empty cells become null. File limit 2 MiB, at most 5000 rows/50 columns, cell strings up to 10000 characters, numeric magnitude at most 1e100. Only the first eight rows are displayed in the preview; all supplied rows are analyzed. Report tables may become large when many values are flagged.

## Troubleshooting

- All columns are non-numeric: ensure CSV inference is enabled, or send actual JSON numbers. Numeric strings are deliberately not coerced by the API.
- CSV field-count error: quote commas/newlines inside cells. Do not use comma as both field delimiter and unquoted thousands separator.
- Leading-zero IDs stay text: intentional to avoid losing identifiers such as 0012.
- Correlation is undefined: check constants and paired nonmissing rows.
- Numeric magnitude rejected: change units before uploading; extreme finite numbers can overflow otherwise.
- Input changed: reload the file or preview pasted CSV before running, then export a fresh report.

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

Node 22 is used for browser-independent CSV/export logic tests; it is not needed to serve the application. Python tests include actual core calculations, validation failures and in-process HTTP integration. They do not establish Docker deployment or browser interaction success. Fresh 0.4.0 evidence belongs in `evidence/improvements-0.4/`. `evidence/rebuild/` records the earlier 0.2.0 rebuild; it does not validate this version. CI includes locked dependency installation, test/security gates, image scanning and secret scanning. Branch protection and release publication remain separate operator actions; no publication success is claimed by this README.

MIT licensed. No paid service or new model download is required. Data is processed by this app server when you run an analysis. Inputs/results are not automatically saved by this application. JSON exports may contain the original input and sensitive values; inspect them before sharing. Optional shared-key API access and per-process compute admission are available; see docs/OPERATIONS.md in the repository. These are not user accounts, distributed quotas or HTTPS. Keep the default localhost binding unless you supply the additional hosting controls.

## Duplicates, uniqueness and frequent values (0.4.0)

The report now shows exact duplicate groups, rows participating in duplicate groups, and **redundant rows** beyond the first row in each group. For a group of three identical rows, participating rows=3 and redundant rows=2. Row key order does not matter. Identity is typed: boolean `true`, number `1` and string `"1"` are different. Numbers `1` and `1.0` are equivalent, as are numeric signed zeros. Absent keys differ from explicit null when comparing whole rows. No rows are deleted automatically.

Column profiles add `absent_count`, `null_count`, `unique_present_count`, `unique_fraction` and typed `top_values`. Existing `missing_count` equals absent + null. Uniqueness and frequency counts exclude both missing kinds, and unique fraction is distinct present values / present cells (null when no present cells exist). Frequency ties retain first-seen order. Boolean/number/string identities are separate even in a mixed column. Values are diagnostics, not recommendations to remove rare categories or duplicate business records.

Bounded detail: show at most 100 duplicate groups and the first 100 zero-based row indices per group; exact group/row/redundant counts and truncation flags remain available. Top values show at most 10 distinct values per column, with string previews capped at 120 characters. Counts and uniqueness use original untruncated values. These bounds prevent repeated values from amplifying report size. Other existing 5000-row/50-column/2 MiB limits remain unchanged. JSON preserves absent keys; CSV cannot represent an absent column key per row, so inferred empty CSV cells are explicit nulls.

## Reusable declarative contracts (0.4)

The contract workspace validates the currently loaded CSV/JSON table. Draft rules from its first non-null values, then review them; a draft is not automatically approved. Each editable column rule declares type(number/string/boolean), required key, nullability, optional numeric bounds, allowed non-null values, uniqueness and maximum missing fraction. Import/export a reusable contract JSON. The synthetic sales contract deliberately fails the synthetic table's missing revenue, unusual revenue and out-of-list region; it is not a real business policy.

`POST /contracts/validate` accepts `{ "rows": [...], "contract": { "name":"...", "allow_extra_columns":true, "columns": {"column":{"type":"number","required":true,"nullable":false,"min_value":0,"max_value":100,"unique":false,"max_missing_fraction":0.1}}}, "detail_limit":100 }`. Type checks do not coerce cells. Required controls absent keys; nullable controls explicit nulls. Blank strings remain present. Optional absent keys can still fail a global missing-fraction threshold, whose denominator is all rows. Numeric bounds are inclusive and apply only to numeric rules. Allowed values must match the declared type and apply to correctly typed non-null cells. Unique checks present non-null typed values; number 1 and 1.0 are equivalent while boolean true/string "1" are distinct. Null/absent values do not collide in uniqueness. Extra columns are allowed unless disabled.

The result distinguishes total rule failures, row-level failures, global failures, distinct violating rows and per-column missing counts. A single row may fail multiple rules. A global missingness violation can fail the contract even when no row has a row-level issue. Detail truncation never changes counts or pass/fail. Limits: existing 5000rows/50table columns/2MiB HTTP bound; 1–50contract columns, names at most 200characters, at most 100 allowed values per rule and 1–200 violation details. Value previews are capped at 120characters; extra-column name previews are capped at 200 with a truncation flag. All data remains unchanged.

CLI, with the same actual validator:

```sh
python -m app.validate_contract examples/synthetic-contract-table.json examples/synthetic-contract.json
```

Exit 0 means the contract passed,1 means valid input with contract violations, and2 means malformed/unreadable input. The synthetic example intentionally returns 1. JSON files are bounded at2MiB each. This is deterministic rule validation, not a regulatory certification, learned anomaly detector or automated data cleaning service.
