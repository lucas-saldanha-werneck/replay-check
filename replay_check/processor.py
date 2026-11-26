"""A toy ledger processor. Events carry an event_id; replays must not change the result."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

SIGN = {"deposit": 1, "withdrawal": -1, "fee": -1, "refund": 1}


@dataclass
class Result:
    balances: dict[str, Decimal] = field(default_factory=dict)
    duplicates: list[str] = field(default_factory=list)  # same id, same payload
    conflicts: list[str] = field(default_factory=list)  # same id, different payload
    invalid: list[str] = field(default_factory=list)
    out_of_order: int = 0


def _payload(e: dict) -> tuple:
    return (e.get("account"), e.get("type"), str(e.get("amount")))


def apply_events(events: list[dict], idempotent: bool = True) -> Result:
    """Fold events into balances (Decimal, never float).

    idempotent=True skips an event_id already seen. A repeated id with a
    different payload is a conflict: the first one wins, the repeat is reported.
    idempotent=False is the naive version, kept to show what a retry does.
    """
    res = Result()
    seen: dict[str, tuple] = {}
    last_ts = None
    for e in events:
        eid = str(e.get("event_id", ""))
        try:
            amount = Decimal(str(e["amount"]))
            sign = SIGN[e["type"]]
            account = e["account"]
        except (KeyError, ArithmeticError):
            res.invalid.append(eid or "<no id>")
            continue
        if amount < 0:
            res.invalid.append(eid)
            continue
        ts = e.get("ts")
        if ts is not None:
            if last_ts is not None and ts < last_ts:
                res.out_of_order += 1
            last_ts = ts if last_ts is None else max(last_ts, ts)
        if idempotent and eid in seen:
            (res.duplicates if seen[eid] == _payload(e) else res.conflicts).append(eid)
            continue
        seen[eid] = _payload(e)
        res.balances[account] = res.balances.get(account, Decimal("0")) + sign * amount
    return res
