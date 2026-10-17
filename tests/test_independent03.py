import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_independent_duplicate_identity_and_missingness_are_typed():
    rows = [{"x": True}, {"x": 1}, {"x": "1"}, {"x": 1.0}, {}, {"x": None}, {}]
    response = TestClient(app).post("/analyze", json={"rows": rows})
    assert response.status_code == 200
    result = response.json()
    column = result["columns"]["x"]
    duplicates = result["duplicates"]
    assert duplicates["group_count"] == 2 and duplicates["redundant_row_count"] == 2
    assert duplicates["rows_in_duplicate_groups"] == 4
    assert (
        column["absent_count"] == 2
        and column["null_count"] == 1
        and column["missing_count"] == 3
    )
    assert column["unique_present_count"] == 3 and column["unique_fraction"] == 0.75
    top = {
        (row["type"], str(row["value"])): row["count"] for row in column["top_values"]
    }
    assert (
        top[("boolean", "True")] == 1
        and top[("number", "1")] == 2
        and top[("string", "1")] == 1
    )


def test_independent_truncated_strings_keep_exact_counts_and_identity():
    prefix = "synthetic" * 20
    rows = [{"name": prefix + "a"}] * 120 + [{"name": prefix + "b"}] * 3
    response = TestClient(app).post("/analyze", json={"rows": rows})
    assert response.status_code == 200
    result = response.json()
    column = result["columns"]["name"]
    duplicates = result["duplicates"]
    assert column["unique_present_count"] == 2
    assert [entry["count"] for entry in column["top_values"]] == [120, 3]
    assert all(entry["value_truncated"] for entry in column["top_values"])
    assert len(duplicates["groups"][0]["row_indices"]) == 100
    assert duplicates["groups"][0]["indices_truncated"] is True
    assert duplicates["redundant_row_count"] == 121


def test_independent_small_scale_perfect_correlation_remains_defined():
    response = TestClient(app).post(
        "/analyze",
        json={
            "rows": [{"x": i * 1e-200, "y": 2 * i * 1e-200} for i in [-2, -1, 0, 1, 2]]
        },
    )
    assert response.status_code == 200
    correlation = response.json()["correlations"][0]
    assert correlation["paired_rows"] == 5
    assert correlation["pearson_r"] == pytest.approx(1)
