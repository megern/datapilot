import {
  $,
  el,
  clear,
  metric,
  table,
  analyze,
  status,
  readFile,
  resultDetails,
  limitations,
  setupDownloads,
  number,
  percent,
  parseCSV,
  inferValue,
  csvText,
  download
} from "./common.mjs";
let revision = 0;
let rows = [],
  report = null,
  source = "manual input";
function input() {
  if (!rows.length) throw Error("Load and preview a table before profiling.");
  return { rows };
}
function invalidate() {
  revision++;
  report = null;
  clear($("results"));
  clear($("overview"));
  $("results").append(
    el("p", "Table changed. Profile it to refresh the statistics.")
  );
  $("overview").append(el("p", "No current report."));
}
function validateRows(v) {
  if (!Array.isArray(v) || !v.length || v.length > 5000)
    throw Error("Table needs 1–5000 row objects.");
  if (
    v.some(
      (r) =>
        !r ||
        Array.isArray(r) ||
        typeof r !== "object" ||
        Object.values(r).some(
          (x) =>
            x !== null && !["string", "number", "boolean"].includes(typeof x)
        )
    )
  )
    throw Error(
      "Each row must map column names to numbers, strings, booleans or null."
    );
  const cols = [...new Set(v.flatMap((r) => Object.keys(r)))];
  if (!cols.length || cols.length > 50)
    throw Error("Table needs 1–50 columns.");
  return v;
}
function load(v, label) {
  rows = validateRows(v);
  source = label;
  invalidate();
  clear($("preview"));
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  $("preview").append(
    el(
      "p",
      `${rows.length} rows · ${keys.length} columns · ${source}. Showing the first 8 rows.`
    )
  );
  table(
    $("preview"),
    ["Row index", ...keys],
    rows
      .slice(0, 8)
      .map((r, i) => [
        i,
        ...keys.map((k) =>
          r[k] === undefined ? "Missing" : r[k] === null ? "Null" : r[k]
        )
      ])
  );
}
function csvRows(text) {
  const parsed = parseCSV(text);
  return $("infer").checked
    ? parsed.map((row) =>
        Object.fromEntries(
          Object.entries(row).map(([k, v]) => [k, inferValue(v)])
        )
      )
    : parsed;
}
function discard() {
  rows = [];
  invalidate();
  clear($("preview"));
  $("preview").append(
    el("p", "Input changed. Reload or preview the table before profiling.")
  );
  source = "user-edited input; provenance unverified";
}
function render(r, request) {
  const overview = $("overview");
  clear(overview);
  const metrics = el("div", undefined, "metrics");
  const names = Object.keys(r.columns),
    missing = Object.values(r.columns).reduce((n, c) => n + c.missing_count, 0);
  metric(metrics, "Rows", r.row_count);
  metric(metrics, "Columns", names.length);
  metric(metrics, "Missing cells", missing);
  metric(
    metrics,
    "Missing fraction",
    percent(missing / (r.row_count * names.length))
  );
  overview.append(metrics);
  const mixed = names.filter(
    (k) => r.columns[k].type === "mixed_or_categorical"
  );
  overview.append(
    el(
      "p",
      mixed.length
        ? "Non-numeric columns: " +
            mixed.join(", ") +
            ". Numeric strings or mixed types prevent numeric summaries."
        : "All columns with observed values are numeric."
    )
  );
  const root = $("results");
  clear(root);
  root.classList.remove("empty");
  root.append(el("h3", "Column profiles"));
  table(
    root,
    [
      "Column",
      "Type",
      "Missing",
      "Mean",
      "Median",
      "Sample std",
      "Range",
      "IQR outliers"
    ],
    names.map((k) => {
      const c = r.columns[k];
      return [
        k,
        c.type,
        c.missing_count,
        number(c.mean),
        number(c.median),
        number(c.stddev_sample),
        c.type === "numeric"
          ? number(c.min) + " to " + number(c.max)
          : "Not numeric",
        c.outlier_row_indices?.length ?? "Not numeric"
      ];
    })
  );
  root.append(el("h3", "Pairwise Pearson correlations"));
  if (r.correlations.length)
    table(
      root,
      ["Columns", "Pearson r", "Paired rows"],
      r.correlations.map((c) => [
        c.columns.join(" ↔ "),
        number(c.pearson_r),
        c.paired_rows
      ])
    );
  else
    root.append(
      el(
        "p",
        "At least two numeric columns are needed. Correlation is not calculated for mixed/categorical columns."
      )
    );
  root.append(el("h3", "Outlier row inspection"));
  const outliers = names.flatMap((k) =>
    (r.columns[k].outlier_row_indices || []).map((i) => [
      i,
      k,
      request.rows[i][k],
      JSON.stringify(request.rows[i])
    ])
  );
  if (outliers.length)
    table(
      root,
      ["Zero-based row", "Flagged column", "Value", "Original row"],
      outliers
    );
  else root.append(el("p", "No IQR outlier flags in numeric columns."));
  limitations(root, r.limitations);
  resultDetails(root, r);
}
$("load-csv").onclick = () => {
  discard();
  try {
    load(csvRows($("csv").value), "pasted user CSV; provenance unverified");
    status("CSV parsed and previewed. Review inferred types before profiling.");
  } catch (e) {
    status(e.message, true);
  }
};
$("csv").oninput = discard;
$("infer").onchange = () => {
  discard();
  status(
    "Inference option changed. Reload the file or preview the pasted CSV."
  );
};
$("import").onchange = async (e) => {
  discard();
  const importRevision = revision;
  try {
    const f = e.target.files[0],
      text = await readFile(f);
    if (revision !== importRevision) return;
    const parsed = f.name.toLowerCase().endsWith(".csv")
      ? csvRows(text)
      : JSON.parse(text);
    load(
      Array.isArray(parsed) ? parsed : parsed.rows,
      "imported user data; provenance unverified"
    );
    $("csv").value = "";
    status("Table imported. Review the preview, then profile.");
  } catch (err) {
    if (revision === importRevision) status(err.message, true);
  }
};
$("sample").onclick = () => {
  load(
    [
      { region: "North", revenue: 100, cost: 60 },
      { region: "South", revenue: 120, cost: 70 },
      { region: "North", revenue: 130, cost: 75 },
      { region: "East", revenue: 110, cost: 65 },
      { region: "South", revenue: 140, cost: 80 },
      { region: "East", revenue: null, cost: 90 },
      { region: "North", revenue: 900, cost: 500 }
    ],
    "synthetic example"
  );
  $("csv").value = "";
  status(
    "Synthetic sales table loaded, including a missing revenue and an unusual high-value row."
  );
};
$("run").onclick = async () => {
  invalidate();
  const requestRevision = revision;
  $("run").disabled = true;
  try {
    const request = input();
    status(
      "Calculating missingness, numeric statistics, correlations and outliers…"
    );
    const result = await analyze(request);
    if (revision !== requestRevision)
      throw Error(
        "Inputs changed during the request. Discarded its result; run again for the current setup."
      );
    report = { input: request, source, result };
    render(result, request);
    status(
      "Profiling finished. Outliers are exploratory flags; correlations do not imply causation."
    );
  } catch (e) {
    status(e.message, true);
  } finally {
    $("run").disabled = false;
  }
};
$("export-csv").onclick = () => {
  if (!report) {
    status("Profile the current table before exporting statistics.", true);
    return;
  }
  download(
    "datapilot-column-summary.csv",
    csvText([
      [
        "column",
        "type",
        "missing_count",
        "mean",
        "median",
        "sample_stddev",
        "min",
        "max",
        "outlier_count"
      ],
      ...Object.entries(report.result.columns).map(([k, c]) => [
        k,
        c.type,
        c.missing_count,
        c.mean,
        c.median,
        c.stddev_sample,
        c.min,
        c.max,
        c.outlier_row_indices?.length ?? null
      ])
    ]),
    "text/csv"
  );
};
setupDownloads(input, () => report, "datapilot");
