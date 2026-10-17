from collections import Counter
import math
import statistics
from pydantic import BaseModel, Field, model_validator


class ProfileRequest(BaseModel):
    rows: list[dict[str, str | int | float | bool | None]] = Field(
        min_length=1, max_length=5000
    )

    @model_validator(mode="after")
    def bounded(self):
        if len({k for row in self.rows for k in row}) > 50:
            raise ValueError("maximum 50 columns")
        for row in self.rows:
            for value in row.values():
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and abs(value) > 1e100
                ):
                    raise ValueError("numeric magnitudes must be at most 1e100")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("nonfinite values are not supported")
                if isinstance(value, str) and len(value) > 10000:
                    raise ValueError("cell text too long")
        return self


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def quantile(xs, p):
    i = (len(xs) - 1) * p
    lo = math.floor(i)
    hi = math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def typed_key(value):
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    return ("string", value)


def duplicate_summary(rows):
    groups = {}
    for index, row in enumerate(rows):
        key = tuple((name, typed_key(value)) for name, value in sorted(row.items()))
        groups.setdefault(key, []).append(index)
    duplicates = [indices for indices in groups.values() if len(indices) > 1]
    return {
        "group_count": len(duplicates),
        "rows_in_duplicate_groups": sum(len(indices) for indices in duplicates),
        "redundant_row_count": sum(len(indices) - 1 for indices in duplicates),
        "groups": [
            {
                "count": len(indices),
                "row_indices": indices[:100],
                "indices_truncated": len(indices) > 100,
            }
            for indices in duplicates[:100]
        ],
        "groups_truncated": len(duplicates) > 100,
    }


def analyze(req: ProfileRequest):
    columns = sorted({k for row in req.rows for k in row})
    profiles = {}
    numeric_cols = []
    for col in columns:
        present = [
            (i, row[col]) for i, row in enumerate(req.rows) if row.get(col) is not None
        ]
        nums = [(i, float(v)) for i, v in present if numeric(v)]
        counts = Counter(typed_key(value) for _, value in present)
        top_counts = counts.most_common(10)
        p = {
            "absent_count": sum(col not in row for row in req.rows),
            "null_count": sum(col in row and row[col] is None for row in req.rows),
            "unique_present_count": len(counts),
            "unique_fraction": len(counts) / len(present) if present else None,
            "top_values": [
                {
                    "type": key[0],
                    "value": str(key[1])[:120] if key[0] == "string" else key[1],
                    "count": count,
                    "value_truncated": key[0] == "string" and len(str(key[1])) > 120,
                }
                for key, count in top_counts
            ],
            "top_values_truncated": len(counts) > 10,
            "missing_count": len(req.rows) - len(present),
            "present_count": len(present),
            "numeric_count": len(nums),
        }
        if nums and len(nums) == len(present):
            numeric_cols.append(col)
            xs = sorted(v for _, v in nums)
            q1 = quantile(xs, 0.25)
            q3 = quantile(xs, 0.75)
            iqr = q3 - q1
            p.update(
                type="numeric",
                mean=statistics.mean(xs),
                median=statistics.median(xs),
                stddev_sample=statistics.stdev(xs) if len(xs) > 1 else None,
                min=min(xs),
                max=max(xs),
                q1=q1,
                q3=q3,
                outlier_row_indices=[
                    i for i, v in nums if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr
                ],
            )
        else:
            p["type"] = "mixed_or_categorical" if present else "empty"
        profiles[col] = p
    correlations = []
    for ix, a in enumerate(numeric_cols):
        for b in numeric_cols[ix + 1 :]:
            pairs = [
                (float(row[a]), float(row[b]))
                for row in req.rows
                if numeric(row.get(a)) and numeric(row.get(b))
            ]
            value = None
            if len(pairs) > 1:
                xs, ys = zip(*pairs)
                # Scale raw values before centering so tiny representable variation is not squared away.
                x_scale, y_scale = max(map(abs, xs)), max(map(abs, ys))
                if x_scale and y_scale:
                    normalized_x = [x / x_scale for x in xs]
                    normalized_y = [y / y_scale for y in ys]
                    xm, ym = (
                        statistics.mean(normalized_x),
                        statistics.mean(normalized_y),
                    )
                    dx = [x - xm for x in normalized_x]
                    dy = [y - ym for y in normalized_y]
                    denominator = math.sqrt(math.fsum(x * x for x in dx)) * math.sqrt(
                        math.fsum(y * y for y in dy)
                    )
                    if denominator:
                        value = max(
                            -1.0,
                            min(
                                1.0,
                                math.fsum(x * y for x, y in zip(dx, dy)) / denominator,
                            ),
                        )

            correlations.append(
                {"columns": [a, b], "pearson_r": value, "paired_rows": len(pairs)}
            )
    return {
        "row_count": len(req.rows),
        "columns": profiles,
        "duplicates": duplicate_summary(req.rows),
        "correlations": correlations,
        "limitations": [
            "Numeric strings are categorical; booleans are not numbers.",
            "Duplicate rows use typed values; bool, number and string are distinct. Numeric 1 and 1.0 are equivalent; absent keys differ from explicit null.",
            "Uniqueness excludes absent/null cells. Top values show at most 10 entries, strings capped at 120 characters; counts remain exact.",
            "Duplicate detail is capped at 100 groups and 100 indices per group; summary counts remain exact.",
            "Correlations use pairwise complete rows and do not imply causation.",
            "IQR outliers are exploratory flags, not errors. Row indices are zero-based.",
        ],
    }
