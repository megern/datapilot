import pytest
from pydantic import ValidationError
from app.contracts import ContractRequest, validate_contract


def test_missing_fraction_boundary_and_rule_counts_survive_detail_cap():
    request = ContractRequest(
        rows=[{}, {"x": None}, {"x": 1}, {"x": 1.0}],
        contract={
            "columns": {
                "x": {
                    "type": "number",
                    "required": False,
                    "nullable": True,
                    "unique": True,
                    "max_missing_fraction": 0.5,
                }
            }
        },
        detail_limit=1,
    )
    result = validate_contract(request)
    assert result["rule_violation_counts"] == {"NOT_UNIQUE": 1}
    assert result["valid_row_count"] == 3
    assert result["columns"]["x"]["missing_fraction"] == 0.5
    request.contract.columns["x"].max_missing_fraction = 0.49
    result = validate_contract(request)
    assert result["global_violation_count"] == 1 and result["violations_total"] == 2
    assert result["valid_row_count"] == 3 and result["details_truncated"]


@pytest.mark.parametrize("value", [True, "1"])
def test_allowed_numeric_identity_does_not_coerce_cells(value):
    result = validate_contract(
        ContractRequest(
            rows=[{"x": value}],
            contract={"columns": {"x": {"type": "number", "allowed_values": [1]}}},
        )
    )
    assert result["rule_violation_counts"] == {"TYPE_MISMATCH": 1}


def test_numeric_allowed_values_accept_equivalent_float_and_empty_set_rejects_all():
    request = ContractRequest(
        rows=[{"x": 1.0}],
        contract={"columns": {"x": {"type": "number", "allowed_values": [1]}}},
    )
    assert validate_contract(request)["passed"]
    request.contract.columns["x"].allowed_values = []
    assert validate_contract(request)["rule_violation_counts"] == {
        "VALUE_NOT_ALLOWED": 1
    }


@pytest.mark.parametrize("value", [float("inf"), float("nan"), 10**200])
def test_contract_unsafe_numeric_inputs_rejected(value):
    with pytest.raises(ValidationError):
        ContractRequest(
            rows=[{"x": value}], contract={"columns": {"x": {"type": "number"}}}
        )
