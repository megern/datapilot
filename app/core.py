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


def analyze(req: ProfileRequest):
    columns = sorted({k for row in req.rows for k in row})
    profiles = {}
    numeric_cols = []
    for col in columns:
        present = [
            (i, row[col]) for i, row in enumerate(req.rows) if row.get(col) is not None
        ]
        nums = [(i, float(v)) for i, v in present if numeric(v)]
        p = {
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
                xm = statistics.mean(xs)
                ym = statistics.mean(ys)
                den = math.sqrt(sum((x - xm) ** 2 for x in xs)) * math.sqrt(
                    sum((y - ym) ** 2 for y in ys)
                )
                if den:
                    value = max(
                        -1.0, min(1.0, sum((x - xm) * (y - ym) for x, y in pairs) / den)
                    )
            correlations.append(
                {"columns": [a, b], "pearson_r": value, "paired_rows": len(pairs)}
            )
    return {
        "row_count": len(req.rows),
        "columns": profiles,
        "correlations": correlations,
        "limitations": [
            "Numeric strings are categorical; booleans are not numbers.",
            "Correlations use pairwise complete rows and do not imply causation.",
            "IQR outliers are exploratory flags, not errors. Row indices are zero-based.",
        ],
    }
