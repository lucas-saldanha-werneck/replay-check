"""Compare two balance tables (for example legacy export vs rebuilt system)."""
from __future__ import annotations

import csv
from decimal import Decimal


def load_balances(path: str) -> dict[str, Decimal]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["account"]: Decimal(r["balance"]) for r in csv.DictReader(f)}


def diff_balances(old: dict[str, Decimal], new: dict[str, Decimal],
                  tolerance: Decimal = Decimal("0")) -> list[dict]:
    """Return one row per account that differs by more than tolerance (or is missing)."""
    rows = []
    for acc in sorted(set(old) | set(new)):
        a, b = old.get(acc), new.get(acc)
        if a is None or b is None:
            rows.append({"account": acc, "old": a, "new": b, "delta": None})
        elif abs(a - b) > tolerance:
            rows.append({"account": acc, "old": a, "new": b, "delta": b - a})
    return rows
