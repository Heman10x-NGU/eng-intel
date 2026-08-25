#!/usr/bin/env python3
"""Run evals/queries.yaml — assertions on QueryPlan fields, not prose."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_conn
from execute import execute
from plan import build_plan


def _match_plan(actual: dict, expected: dict) -> list[str]:
    errors = []
    for k, v in expected.items():
        av = actual.get(k)
        if k == "filters" and isinstance(v, dict):
            for fk, fv in v.items():
                if (actual.get("filters") or {}).get(fk) != fv:
                    errors.append(f"filters.{fk}: expected {fv}, got {(actual.get('filters') or {}).get(fk)}")
            continue
        if k == "companies" and v:
            for c in v:
                if c not in (av or []):
                    errors.append(f"companies missing {c}")
            continue
        if av != v and not (k == "source_types" and v and av and set(v) <= set(av)):
            if k == "source_types" and v and av and all(x in av for x in v):
                continue
            errors.append(f"{k}: expected {v}, got {av}")
    return errors


def main() -> int:
    cases = yaml.safe_load(Path(__file__).with_name("queries.yaml").read_text())
    passed = 0
    rows = []
    with get_conn() as conn:
        for case in cases:
            plan = build_plan(case["q"])
            actual = plan.to_dict()
            errs = _match_plan(actual, case.get("expect_plan", {}))
            expect = case.get("expect", {})
            if expect.get("refuses"):
                if plan.op != "refuse":
                    errs.append("expected refuse")
            if "total_min" in expect:
                result = execute(conn, plan)
                total = result.aggregates.get("total", 0)
                if total < expect["total_min"]:
                    errs.append(f"total {total} < {expect['total_min']}")
            if "n_min" in expect or "n_max" in expect:
                result = execute(conn, plan)
                n = result.aggregates.get("count", len(result.rows))
                if "n_min" in expect and n < expect["n_min"]:
                    errs.append(f"n {n} < {expect['n_min']}")
                if "n_max" in expect and n > expect["n_max"]:
                    errs.append(f"n {n} > {expect['n_max']}")
            ok = not errs
            if ok:
                passed += 1
            rows.append((case["id"], ok, "; ".join(errs) if errs else "ok"))
    print(f"PASS {passed}/{len(cases)}")
    for rid, ok, msg in rows:
        print(f"{'✓' if ok else '✗'} {rid}: {msg}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
