import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from replay_check.cli import build_report, load_events, main, order_independent
from replay_check.diff import diff_balances, load_balances
from replay_check.processor import apply_events

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"


def ev(i, acc="A", typ="deposit", amt="10.00", ts=None):
    e = {"event_id": f"E{i}", "account": acc, "type": typ, "amount": amt}
    if ts is not None:
        e["ts"] = ts
    return e


def test_basic_balances_use_decimal():
    r = apply_events([ev(1, amt="0.10"), ev(2, amt="0.20"), ev(3, typ="fee", amt="0.30")])
    assert r.balances["A"] == Decimal("0.00")


def test_duplicate_delivery_is_skipped():
    r = apply_events([ev(1), ev(1), ev(2)])
    assert r.balances["A"] == Decimal("20.00")
    assert r.duplicates == ["E1"]


def test_naive_replay_double_counts():
    r = apply_events([ev(1), ev(1)], idempotent=False)
    assert r.balances["A"] == Decimal("20.00")


def test_conflicting_payload_first_wins_and_is_reported():
    r = apply_events([ev(1, amt="10.00"), ev(1, amt="99.00")])
    assert r.balances["A"] == Decimal("10.00")
    assert r.conflicts == ["E1"]


def test_invalid_events_are_reported_not_applied():
    bad = [{"event_id": "X1", "account": "A", "type": "bogus", "amount": "1"},
           ev(2, amt="-5"), {"event_id": "X3", "account": "A", "type": "deposit", "amount": "abc"}]
    r = apply_events(bad)
    assert r.balances == {}
    assert len(r.invalid) == 3


def test_out_of_order_counted():
    r = apply_events([ev(1, ts=20), ev(2, ts=10), ev(3, ts=30)])
    assert r.out_of_order == 1


def test_order_independence_with_duplicates():
    events = [ev(i, typ=t, amt=f"{i}.50") for i, t in enumerate(["deposit", "fee", "refund", "withdrawal"] * 5)]
    events += events[:3]
    assert order_independent(events, shuffles=25)


def test_diff_tolerance_and_missing():
    old = {"A": Decimal("1.00"), "B": Decimal("2.00"), "C": Decimal("3.00")}
    new = {"A": Decimal("1.01"), "B": Decimal("2.00"), "D": Decimal("4.00")}
    rows = diff_balances(old, new, Decimal("0.01"))
    assert {r["account"] for r in rows} == {"C", "D"}
    assert len(diff_balances(old, new)) == 3


def test_example_data_matches_expected_findings():
    events = load_events(str(EX / "events.jsonl"))
    good = apply_events(events)
    assert len(events) == 43 and len(good.duplicates) == 3
    legacy = load_balances(str(EX / "legacy_balances.csv"))
    rows = diff_balances(legacy, good.balances)
    assert [r["account"] for r in rows] == ["ACC-001", "ACC-004"]
    # the two differing accounts are exactly the ones that received a retried event
    retried = {e["account"] for e in events[:]
               if [x["event_id"] for x in events].count(e["event_id"]) > 1}
    assert retried == {"ACC-001", "ACC-004"}


def test_report_passes_on_clean_data():
    events = [ev(1), ev(2, typ="fee", amt="1.00")]
    text, ok = build_report(events, {"A": Decimal("9.00")}, 5, Decimal("0"))
    assert ok and "RESULT: PASS" in text


def test_report_fails_on_legacy_mismatch():
    text, ok = build_report([ev(1)], {"A": Decimal("11.00")}, 5, Decimal("0"))
    assert not ok and "delta -1.00" in text


def test_cli_exit_codes(tmp_path, capsys):
    p = tmp_path / "e.jsonl"
    p.write_text(json.dumps(ev(1)) + "\n")
    assert main([str(p)]) == 0
    assert main([str(EX / "events.jsonl"), "--legacy", str(EX / "legacy_balances.csv")]) == 1
    assert "RESULT: FAIL" in capsys.readouterr().out


def test_module_entrypoint_runs():
    out = subprocess.run([sys.executable, "-m", "replay_check", str(EX / "events.jsonl")],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0
    assert "duplicate deliveries skipped: 3" in out.stdout
