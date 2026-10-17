from app.core import ProfileRequest, analyze
from app.main import app
from fastapi.testclient import TestClient


def test_typed_duplicate_groups_missing_null_and_numeric_equivalence():
    rows = [
        {"a": True},
        {"a": 1},
        {"a": "1"},
        {"a": 1.0},
        {"a": None},
        {},
        {"a": True},
        {},
    ]
    result = analyze(ProfileRequest(rows=rows))
    duplicates = result["duplicates"]
    assert duplicates["group_count"] == 3
    assert duplicates["rows_in_duplicate_groups"] == 6
    assert duplicates["redundant_row_count"] == 3
    assert [group["row_indices"] for group in duplicates["groups"]] == [
        [0, 6],
        [1, 3],
        [5, 7],
    ]
    column = result["columns"]["a"]
    assert column["missing_count"] == 3
    assert column["absent_count"] == 2 and column["null_count"] == 1
    assert column["unique_present_count"] == 3 and column["unique_fraction"] == 3 / 5
    assert column["top_values"] == [
        {"type": "boolean", "value": True, "count": 2, "value_truncated": False},
        {"type": "number", "value": 1, "count": 2, "value_truncated": False},
        {"type": "string", "value": "1", "count": 1, "value_truncated": False},
    ]


def test_duplicate_detail_and_top_categories_are_bounded_without_losing_counts():
    result = analyze(ProfileRequest(rows=[{"x": "same"}] * 5000))
    group = result["duplicates"]["groups"][0]
    assert (
        group["count"] == 5000
        and len(group["row_indices"]) == 100
        and group["indices_truncated"]
    )
    assert result["duplicates"]["redundant_row_count"] == 4999
    result = analyze(
        ProfileRequest(rows=[{"x": str(i)} for i in range(110) for _ in range(2)])
    )
    assert result["duplicates"]["group_count"] == 110
    assert (
        len(result["duplicates"]["groups"]) == 100
        and result["duplicates"]["groups_truncated"]
    )
    assert result["columns"]["x"]["unique_present_count"] == 110
    assert (
        len(result["columns"]["x"]["top_values"]) == 10
        and result["columns"]["x"]["top_values_truncated"]
    )
    result = analyze(ProfileRequest(rows=[{"x": "z" * 500}]))
    assert len(result["columns"]["x"]["top_values"][0]["value"]) == 120
    assert result["columns"]["x"]["top_values"][0]["value_truncated"]


def test_column_order_does_not_affect_duplicates_and_empty_profile_http():
    result = TestClient(app).post(
        "/analyze", json={"rows": [{"a": 1, "b": None}, {"b": None, "a": 1}, {}]}
    )
    assert result.status_code == 200
    assert result.json()["duplicates"]["groups"][0]["row_indices"] == [0, 1]
    empty = analyze(ProfileRequest(rows=[{"a": None}, {}]))
    assert empty["columns"]["a"]["unique_present_count"] == 0
    assert empty["columns"]["a"]["unique_fraction"] is None
    assert empty["columns"]["a"]["top_values"] == []


def test_pearson_handles_subnormal_variation_and_negative_relationship():
    tiny = float.fromhex("0x0.0000000000001p-1022")
    rows = [{"x": 0.0, "y": tiny}, {"x": tiny, "y": 0.0}]
    result = analyze(ProfileRequest(rows=rows))
    assert abs(result["correlations"][0]["pearson_r"] + 1.0) < 1e-12
    rows = [{"x": i * 1e-200, "y": i * 2e-200} for i in range(5)]
    result = analyze(ProfileRequest(rows=rows))
    assert abs(result["correlations"][0]["pearson_r"] - 1.0) < 1e-12
