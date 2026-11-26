"""Command line: replay-check events.jsonl [--legacy legacy.csv] [--shuffles N] [--tolerance 0.00]"""
from __future__ import annotations

import argparse
import json
import random
import sys
from decimal import Decimal

from .diff import diff_balances, load_balances
from .processor import apply_events


def load_events(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def order_independent(events: list[dict], shuffles: int, seed: int = 7) -> bool:
    """Replay in random order; balances must match the original order."""
    base = apply_events(events).balances
    rng = random.Random(seed)
    for _ in range(shuffles):
        copy = events[:]
        rng.shuffle(copy)
        if apply_events(copy).balances != base:
            return False
    return True


def build_report(events: list[dict], legacy: dict[str, Decimal] | None,
                 shuffles: int, tolerance: Decimal) -> tuple[str, bool]:
    ok = True
    good = apply_events(events)
    naive = apply_events(events, idempotent=False)
    lines = ["# replay-check report", "", f"events read: {len(events)}",
             f"accounts: {len(good.balances)}"]
    lines.append(f"duplicate deliveries skipped: {len(good.duplicates)}")
    if good.conflicts:
        ok = False
        lines.append(f"CONFLICTS (same event_id, different payload): {', '.join(good.conflicts)}")
    if good.invalid:
        ok = False
        lines.append(f"INVALID events: {', '.join(good.invalid)}")
    lines.append(f"out-of-order arrivals: {good.out_of_order}")
    doubled = diff_balances(good.balances, naive.balances)
    lines.append(f"accounts a naive (non-idempotent) replay would get wrong: {len(doubled)}")
    for r in doubled:
        lines.append(f"  - {r['account']}: correct {r['old']}, naive {r['new']}")
    if order_independent(events, shuffles):
        lines.append(f"order check: same balances in {shuffles} shuffled replays")
    else:
        ok = False
        lines.append("ORDER CHECK FAILED: balances depend on arrival order")
    if legacy is not None:
        rows = diff_balances(legacy, good.balances, tolerance)
        lines.append(f"legacy comparison: {len(rows)} account(s) differ (tolerance {tolerance})")
        for r in rows:
            lines.append(f"  - {r['account']}: legacy {r['old']}, rebuilt {r['new']}, delta {r['delta']}")
        if rows:
            ok = False
    lines.append("")
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    return "\n".join(lines), ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="replay-check")
    p.add_argument("events")
    p.add_argument("--legacy", help="CSV with columns account,balance")
    p.add_argument("--shuffles", type=int, default=20)
    p.add_argument("--tolerance", default="0")
    a = p.parse_args(argv)
    legacy = load_balances(a.legacy) if a.legacy else None
    text, ok = build_report(load_events(a.events), legacy, a.shuffles, Decimal(a.tolerance))
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
