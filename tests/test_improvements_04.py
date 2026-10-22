import json
import subprocess
import sys
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_declarative_contract_rule_totals_and_rows_are_distinct():
    request = {
        "rows": [
            {"age": 10, "id": "a", "region": "North"},
            {"age": None, "id": "a", "region": "West"},
            {"id": "b", "region": "North"},
            {"age": "11", "id": "c", "region": "North", "extra": 1},
        ],
        "contract": {
            "name": "test",
            "allow_extra_columns": False,
            "columns": {
                "age": {
                    "type": "number",
                    "min_value": 0,
                    "max_value": 100,
                    "max_missing_fraction": 0.25,
                },
                "id": {"type": "string", "unique": True},
                "region": {"type": "string", "allowed_values": ["North"]},
            },
        },
    }
    response = client.post("/contracts/validate", json=request)
    assert response.status_code == 200
    result = response.json()
    assert not result["passed"] and result["violations_total"] == 7
    assert result["global_violation_count"] == 1 and result["row_violation_count"] == 6
    assert result["violating_row_count"] == 3 and result["valid_row_count"] == 1
    assert result["rule_violation_counts"] == {
        "EXTRA_COLUMN": 1,
        "MISSING_FRACTION_EXCEEDED": 1,
        "MISSING_REQUIRED": 1,
        "NOT_UNIQUE": 1,
        "NULL_NOT_ALLOWED": 1,
        "TYPE_MISMATCH": 1,
        "VALUE_NOT_ALLOWED": 1,
    }


def test_optional_missing_nullability_global_threshold_and_typed_uniqueness():
    request = {
        "rows": [{}, {"x": None}],
        "contract": {
            "columns": {
                "x": {
                    "type": "number",
                    "required": False,
                    "nullable": True,
                    "max_missing_fraction": 0,
                }
            }
        },
    }
    result = client.post("/contracts/validate", json=request).json()
    assert (
        not result["passed"]
        and result["valid_row_count"] == 2
        and result["violations_total"] == 1
    )
    request = {
        "rows": [{"x": 1}, {"x": 1.0}, {"x": True}, {"x": "1"}],
        "contract": {"columns": {"x": {"type": "number", "unique": True}}},
    }
    result = client.post("/contracts/validate", json=request).json()
    assert result["rule_violation_counts"] == {"NOT_UNIQUE": 1, "TYPE_MISMATCH": 2}


def test_contract_details_are_bounded_and_invalid_rules_rejected():
    request = {
        "rows": [{"x": None}] * 5000,
        "contract": {"columns": {"x": {"type": "number"}}},
        "detail_limit": 2,
    }
    result = client.post("/contracts/validate", json=request).json()
    assert (
        result["violations_total"] == 5000
        and len(result["violations"]) == 2
        and result["details_truncated"]
    )
    for rule in [
        {"type": "number", "min_value": 2, "max_value": 1},
        {"type": "string", "min_value": 0},
        {"type": "number", "allowed_values": [True]},
    ]:
        request["contract"]["columns"]["x"] = rule
        assert client.post("/contracts/validate", json=request).status_code == 422


def test_contract_cli_exit_codes_are_real(tmp_path):
    table = tmp_path / "rows.json"
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"columns": {"x": {"type": "number", "min_value": 0}}})
    )
    table.write_text(json.dumps({"rows": [{"x": 1}]}))
    result = subprocess.run(
        [sys.executable, "-m", "app.validate_contract", str(table), str(contract)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and json.loads(result.stdout)["passed"]
    table.write_text(json.dumps({"rows": [{"x": -1}]}))
    result = subprocess.run(
        [sys.executable, "-m", "app.validate_contract", str(table), str(contract)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 and not json.loads(result.stdout)["passed"]
    table.write_text("invalid json")
    assert (
        subprocess.run(
            [sys.executable, "-m", "app.validate_contract", str(table), str(contract)],
            capture_output=True,
        ).returncode
        == 2
    )
