"""Declarative, bounded table validation without coercion or code execution."""

import json
import math
from collections import Counter
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .core import ProfileRequest, numeric, typed_key


def matches(value, kind):
    return (
        numeric(value)
        if kind == "number"
        else isinstance(value, str)
        if kind == "string"
        else isinstance(value, bool)
    )


class ColumnRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["number", "string", "boolean"] = Field(alias="type")
    required: bool = True
    nullable: bool = False
    min_value: float | None = Field(
        default=None, ge=-1e100, le=1e100, allow_inf_nan=False
    )
    max_value: float | None = Field(
        default=None, ge=-1e100, le=1e100, allow_inf_nan=False
    )
    allowed_values: list[str | int | float | bool] | None = Field(
        default=None, max_length=100
    )
    unique: bool = False
    max_missing_fraction: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def valid_rules(self):
        if self.kind != "number" and (
            self.min_value is not None or self.max_value is not None
        ):
            raise ValueError("Range rules apply only to numeric columns")
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value must not exceed max_value")
        if self.allowed_values is not None:
            for value in self.allowed_values:
                if not matches(value, self.kind):
                    raise ValueError(
                        "Allowed values must match the declared type; nullability is separate"
                    )
                if numeric(value) and (abs(value) > 1e100 or not math.isfinite(value)):
                    raise ValueError(
                        "Allowed numbers must be finite with magnitude at most 1e100"
                    )
                if isinstance(value, str) and len(value) > 10000:
                    raise ValueError("Allowed strings must not exceed 10000 characters")
        return self


class DataContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="table-contract", min_length=1, max_length=100)
    columns: dict[str, ColumnRule] = Field(min_length=1, max_length=50)
    allow_extra_columns: bool = True

    @model_validator(mode="after")
    def valid_columns(self):
        if any(not name or len(name) > 200 for name in self.columns):
            raise ValueError("Contract column names need 1–200 characters")
        return self


class ContractRequest(ProfileRequest):
    model_config = ConfigDict(extra="forbid")
    contract: DataContract
    detail_limit: int = Field(default=100, ge=1, le=200)


def validate_contract(request: ContractRequest):
    counts = Counter()
    details = []
    invalid_rows = set()
    global_count = 0
    summaries = {}

    def add(code, column, row_index=None, value=None, extra=None):
        nonlocal global_count
        counts[code] += 1
        if row_index is None:
            global_count += 1
        else:
            invalid_rows.add(row_index)
        if len(details) < request.detail_limit:
            detail = {"code": code, "column": column, "row_index": row_index}
            if row_index is not None:
                rendered = json.dumps(value, ensure_ascii=False)
                detail.update(
                    value_preview=rendered[:120], value_truncated=len(rendered) > 120
                )
            if extra:
                detail.update(extra)
            details.append(detail)

    for column, rule in request.contract.columns.items():
        missing = absent = nulls = 0
        seen = {}
        allowed = (
            None
            if rule.allowed_values is None
            else {typed_key(value) for value in rule.allowed_values}
        )
        violations_before = sum(counts.values())
        for index, row in enumerate(request.rows):
            if column not in row:
                missing += 1
                absent += 1
                if rule.required:
                    add("MISSING_REQUIRED", column, index)
                continue
            value = row[column]
            if value is None:
                missing += 1
                nulls += 1
                if not rule.nullable:
                    add("NULL_NOT_ALLOWED", column, index)
                continue
            token = typed_key(value)
            if not matches(value, rule.kind):
                add("TYPE_MISMATCH", column, index, value)
            else:
                if rule.kind == "number" and (
                    (rule.min_value is not None and value < rule.min_value)
                    or (rule.max_value is not None and value > rule.max_value)
                ):
                    add("OUT_OF_RANGE", column, index, value)
                if allowed is not None and token not in allowed:
                    add("VALUE_NOT_ALLOWED", column, index, value)
            if rule.unique:
                if token in seen:
                    add(
                        "NOT_UNIQUE",
                        column,
                        index,
                        value,
                        {"first_row_index": seen[token]},
                    )
                else:
                    seen[token] = index
        fraction = missing / len(request.rows)
        if (
            rule.max_missing_fraction is not None
            and fraction > rule.max_missing_fraction
        ):
            add(
                "MISSING_FRACTION_EXCEEDED",
                column,
                extra={
                    "missing_fraction": fraction,
                    "maximum": rule.max_missing_fraction,
                },
            )
        summaries[column] = {
            "missing_count": missing,
            "absent_count": absent,
            "null_count": nulls,
            "missing_fraction": fraction,
            "violation_count": sum(counts.values()) - violations_before,
        }
    if not request.contract.allow_extra_columns:
        for index, row in enumerate(request.rows):
            for column in row.keys() - request.contract.columns.keys():
                add(
                    "EXTRA_COLUMN",
                    column[:200],
                    index,
                    row[column],
                    {"column_truncated": len(column) > 200},
                )
    total = sum(counts.values())
    return {
        "contract_name": request.contract.name,
        "row_count": len(request.rows),
        "passed": total == 0,
        "violations_total": total,
        "global_violation_count": global_count,
        "row_violation_count": total - global_count,
        "violating_row_count": len(invalid_rows),
        "valid_row_count": len(request.rows) - len(invalid_rows),
        "rule_violation_counts": dict(sorted(counts.items())),
        "columns": summaries,
        "violations": details,
        "detail_limit": request.detail_limit,
        "details_truncated": total > len(details),
        "limitations": [
            "No type coercion or data mutation. Missing means absent keys or explicit null; blank strings are present values.",
            "Required controls key presence; nullable controls explicit null. Optional absent keys are allowed unless max_missing_fraction is exceeded.",
            "Range/allowed values apply to correctly typed, non-null cells. Unique checks all present non-null values using typed identity; numeric 1 and 1.0 are equivalent.",
            "Global missing-fraction failures can fail the contract even when every row satisfies its per-row rules. Violation totals count rule failures, not unique rows.",
            "Only violation detail is truncated. Counts cover the full supplied table; this is not a statistical or regulatory certification.",
        ],
    }
