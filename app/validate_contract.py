"""CLI: python -m app.validate_contract input.json contract.json."""

import argparse
import json
from pathlib import Path
from .contracts import ContractRequest, validate_contract


def read_json(path):
    source = Path(path)
    if source.stat().st_size > 2097152:
        raise ValueError("Each JSON file must be at most 2 MiB")
    return json.loads(source.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table")
    parser.add_argument("contract")
    args = parser.parse_args()
    try:
        table, contract = read_json(args.table), read_json(args.contract)
        rows = table if isinstance(table, list) else table["rows"]
        result = validate_contract(ContractRequest(rows=rows, contract=contract))
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        parser.exit(2, "Invalid input: " + str(error) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
