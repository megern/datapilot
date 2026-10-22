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
let contractReport = null;
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
  contractReport = null;
  clear($("contract-results"));
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
  root.append(el("h3", "Uniqueness and frequent values"));
  table(
    root,
    [
      "Column",
      "Absent keys",
      "Explicit nulls",
      "Unique nonmissing values",
      "Unique fraction",
      "Top values (typed, count)"
    ],
    names.map((name) => {
      const column = r.columns[name];
      return [
        name,
        column.absent_count,
        column.null_count,
        column.unique_present_count,
        percent(column.unique_fraction),
        column.top_values
          .map(
            (entry) =>
              `${entry.type}: ${JSON.stringify(entry.value)}${entry.value_truncated ? "… [truncated]" : ""} × ${entry.count}`
          )
          .join("\n") +
          (column.top_values_truncated
            ? "\n[More distinct values not shown]"
            : "")
      ];
    })
  );
  root.append(el("h3", "Exact duplicate rows"));
  const duplicateMetrics = el("div", undefined, "metrics");
  metric(duplicateMetrics, "Duplicate groups", r.duplicates.group_count);
  metric(
    duplicateMetrics,
    "Rows in those groups",
    r.duplicates.rows_in_duplicate_groups
  );
  metric(
    duplicateMetrics,
    "Redundant rows",
    r.duplicates.redundant_row_count,
    "Rows beyond the first in each group"
  );
  root.append(duplicateMetrics);
  table(
    root,
    ["Group", "Total rows", "Zero-based row indices"],
    r.duplicates.groups.map((group, index) => [
      index + 1,
      group.count,
      group.row_indices.join(", ") +
        (group.indices_truncated ? " … [truncated]" : "")
    ])
  );
  if (r.duplicates.groups_truncated)
    root.append(
      el(
        "p",
        "Only the first 100 duplicate groups are shown; summary counts include all groups.",
        "notice"
      )
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

function invalidateContract() {
  revision++;
  contractReport = null;
  clear($("contract-results"));
}
function contractInput() {
  const entries = [...document.querySelectorAll(".contract-row")].map((row) => {
    const get = (name) => row.querySelector(".contract-" + name);
    const name = get("column").value;
    const rule = {
      type: get("type").value,
      required: get("required").checked,
      nullable: get("nullable").checked,
      unique: get("unique").checked
    };
    for (const key of ["min_value", "max_value", "max_missing_fraction"])
      if (get(key).value !== "") {
        const value = Number(get(key).value);
        if (!Number.isFinite(value))
          throw Error(key + " must be a finite number.");
        rule[key] = value;
      }
    if (get("allowed_values").value.trim())
      rule.allowed_values = JSON.parse(get("allowed_values").value);
    return [name, rule];
  });
  if (
    !entries.length ||
    entries.length > 50 ||
    entries.some(([name]) => !name) ||
    new Set(entries.map(([name]) => name)).size !== entries.length
  )
    throw Error("Use 1–50 rules with unique nonempty column names.");
  return {
    name: $("contract-name").value,
    allow_extra_columns: $("contract-extra").checked,
    columns: Object.fromEntries(entries)
  };
}
function drawContract(contract) {
  clear($("contract-fields"));
  for (const [name, rule] of Object.entries(contract.columns)) {
    const row = el("div", undefined, "editor-row contract-row");
    for (const [key, title, value] of [
      ["column", "Column", name],
      ["type", "Declared type", rule.type],
      ["min_value", "Minimum numeric value", rule.min_value],
      ["max_value", "Maximum numeric value", rule.max_value],
      [
        "max_missing_fraction",
        "Maximum missing fraction (0–1)",
        rule.max_missing_fraction
      ],
      [
        "allowed_values",
        "Allowed non-null values (JSON array, optional)",
        rule.allowed_values === undefined
          ? ""
          : JSON.stringify(rule.allowed_values)
      ]
    ]) {
      const label = el("label", title),
        field = el(
          key === "type"
            ? "select"
            : key === "allowed_values"
              ? "textarea"
              : "input"
        );
      field.className = "contract-" + key;
      if (key === "type")
        for (const kind of ["number", "string", "boolean"]) {
          const option = el("option", kind);
          option.value = kind;
          field.append(option);
        }
      field.value = value ?? "";
      field.oninput = invalidateContract;
      label.append(field);
      row.append(label);
    }
    for (const [key, title, value] of [
      ["required", "Required key", rule.required ?? true],
      ["nullable", "Allow null", rule.nullable ?? false],
      ["unique", "Unique non-null values", rule.unique ?? false]
    ]) {
      const label = el("label", title, "check"),
        field = el("input");
      field.type = "checkbox";
      field.className = "contract-" + key;
      field.checked = value;
      field.oninput = invalidateContract;
      label.append(field);
      row.append(label);
    }
    const remove = el("button", "Remove rule");
    remove.onclick = () => {
      const parent = $("contract-fields");
      parent.replaceChildren(
        ...[...parent.children].filter((child) => child !== row)
      );
      invalidateContract();
    };
    row.append(remove);
    $("contract-fields").append(row);
  }
  $("contract-name").value = contract.name || "table-contract";
  $("contract-extra").checked = contract.allow_extra_columns ?? true;
}
function loadContract(value) {
  const contract = value.contract || value.input?.contract || value;
  if (
    !contract ||
    typeof contract !== "object" ||
    !contract.columns ||
    Array.isArray(contract.columns) ||
    typeof contract.columns !== "object"
  )
    throw Error("Import a contract with a columns object.");
  if (
    Object.keys(contract).some(
      (key) => !["name", "columns", "allow_extra_columns"].includes(key)
    )
  )
    throw Error("Unknown contract field.");
  if (contract.name !== undefined && typeof contract.name !== "string")
    throw Error("Contract name must be text.");
  if (
    contract.allow_extra_columns !== undefined &&
    typeof contract.allow_extra_columns !== "boolean"
  )
    throw Error("allow_extra_columns must be boolean.");
  const keys = Object.keys(contract.columns);
  if (!keys.length || keys.length > 50)
    throw Error("Contract needs 1–50 column rules.");
  for (const rule of Object.values(contract.columns)) {
    if (
      !rule ||
      !["number", "string", "boolean"].includes(rule.type) ||
      Object.keys(rule).some(
        (key) =>
          ![
            "type",
            "required",
            "nullable",
            "min_value",
            "max_value",
            "allowed_values",
            "unique",
            "max_missing_fraction"
          ].includes(key)
      )
    )
      throw Error("Unknown or malformed column rule.");
    for (const key of ["required", "nullable", "unique"])
      if (rule[key] !== undefined && typeof rule[key] !== "boolean")
        throw Error(key + " must be boolean.");
  }
  drawContract(contract);
  invalidateContract();
}
for (const id of ["contract-name", "contract-extra", "contract-limit"])
  $(id).oninput = invalidateContract;
$("contract-generate").onclick = () => {
  try {
    input();
    const columns = Object.fromEntries(
      [...new Set(rows.flatMap((row) => Object.keys(row)))].map((name) => {
        const value = rows.find(
          (row) => row[name] !== null && row[name] !== undefined
        )?.[name];
        return [
          name,
          {
            type:
              typeof value === "number"
                ? "number"
                : typeof value === "boolean"
                  ? "boolean"
                  : "string",
            required: true,
            nullable: rows.some((row) => row[name] === null)
          }
        ];
      })
    );
    loadContract({
      name: "draft-contract",
      allow_extra_columns: true,
      columns
    });
    status(
      "Draft inferred from first non-null values. Review every rule; this is not an approved contract."
    );
  } catch (error) {
    status(error.message, true);
  }
};
$("contract-add").onclick = () => {
  try {
    const current = document.querySelectorAll(".contract-row").length
      ? contractInput()
      : {
          name: $("contract-name").value,
          columns: {},
          allow_extra_columns: $("contract-extra").checked
        };
    let name = "column";
    while (Object.hasOwn(current.columns, name)) name += "_";
    current.columns = Object.fromEntries([
      ...Object.entries(current.columns),
      [name, { type: "string", required: true, nullable: false }]
    ]);
    drawContract(current);
    invalidateContract();
  } catch (error) {
    status(error.message, true);
  }
};
$("contract-sample").onclick = () => {
  loadContract({
    name: "synthetic-sales-contract",
    allow_extra_columns: true,
    columns: {
      region: {
        type: "string",
        required: true,
        nullable: false,
        allowed_values: ["North", "South", "East"]
      },
      revenue: {
        type: "number",
        required: true,
        nullable: false,
        min_value: 0,
        max_value: 500,
        max_missing_fraction: 0
      }
    }
  });
  status(
    "Synthetic sales contract loaded. The synthetic sales table deliberately fails revenue nullability/range/missingness."
  );
};
$("contract-import").onchange = async (event) => {
  invalidateContract();
  const generation = revision;
  try {
    const text = await readFile(event.target.files[0]);
    if (revision !== generation) return;
    loadContract(JSON.parse(text));
    status("Reusable contract imported. No rows were changed.");
  } catch (error) {
    if (revision === generation) status(error.message, true);
  }
};
$("run-contract").onclick = async () => {
  invalidateContract();
  const generation = revision;
  $("run-contract").disabled = true;
  try {
    const request = {
      ...input(),
      contract: contractInput(),
      detail_limit: Number($("contract-limit").value)
    };
    const result = await analyze(request, "/contracts/validate");
    if (revision !== generation) return;
    contractReport = {
      application: "datapilot",
      version: "0.4.0",
      generated_at: new Date().toISOString(),
      source,
      input: request,
      result
    };
    const root = $("contract-results"),
      metrics = el("div", undefined, "metrics");
    metric(metrics, "Contract result", result.passed ? "PASS" : "FAIL");
    metric(metrics, "Rule violations", result.violations_total);
    metric(
      metrics,
      "Rows with row-level issues",
      result.violating_row_count + "/" + result.row_count
    );
    metric(metrics, "Global rule violations", result.global_violation_count);
    root.append(metrics);
    table(
      root,
      ["Rule", "Violation count"],
      Object.entries(result.rule_violation_counts)
    );
    table(
      root,
      ["Column", "Row index", "Rule", "Value preview"],
      result.violations.map((item) => [
        item.column,
        item.row_index === null ? "Global" : item.row_index,
        item.code,
        item.value_preview ?? JSON.stringify(item)
      ])
    );
    if (result.details_truncated)
      root.append(
        el(
          "p",
          "Violation detail was truncated; all summary counts are complete.",
          "notice"
        )
      );
    limitations(root, result.limitations);
    resultDetails(root, result);
    status("Contract validation finished. Rule failures do not mutate data.");
  } catch (error) {
    if (revision === generation) status(error.message, true);
  } finally {
    $("run-contract").disabled = false;
  }
};
$("export-contract").onclick = () => {
  try {
    download(
      "datapilot-contract.json",
      JSON.stringify(contractInput(), null, 2)
    );
  } catch (error) {
    status(error.message, true);
  }
};
$("export-contract-report").onclick = () => {
  if (!contractReport) {
    status("Validate the current table and rules before exporting.", true);
    return;
  }
  download(
    "datapilot-contract-report.json",
    JSON.stringify(contractReport, null, 2)
  );
};
