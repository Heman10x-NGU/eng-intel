#!/usr/bin/env python3
"""Run evals/queries.yaml — plan assertions plus optional result checks."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_conn
from execute import execute
from plan import build_plan


def _rendered_ask(conn, question: str):
    from app import render_answer

    plan = build_plan(question)
    result = execute(conn, plan)
    answer, _guard = render_answer(result)
    return answer, result


def _check_expect_rendered(conn, question: str, expect_rendered: dict) -> list[str]:
    errs: list[str] = []
    answer, result = _rendered_ask(conn, question)
    citations = result.citations

    if expect_rendered.get("non_empty") and not answer.strip():
        errs.append("rendered answer empty")
    if expect_rendered.get("no_n_removed") and "[n removed]" in answer.lower():
        errs.append("answer contains [n removed]")
    if expect_rendered.get("no_traceback") and "Traceback" in answer:
        errs.append("answer contains Traceback")
    if expect_rendered.get("no_import_error") and "No module named" in answer:
        errs.append("answer contains No module named")

    if "min_citations" in expect_rendered:
        want = expect_rendered["min_citations"]
        if len(citations) < want:
            errs.append(f"citations {len(citations)} < {want}")

    if "max_citations" in expect_rendered:
        want = expect_rendered["max_citations"]
        if len(citations) > want:
            errs.append(f"citations {len(citations)} > {want}")

    for needle in expect_rendered.get("answer_contains", []):
        if needle not in answer:
            errs.append(f"answer missing {needle!r}")

    for needle in expect_rendered.get("answer_not_contains", []):
        if needle in answer:
            errs.append(f"answer contains forbidden {needle!r}")

    if "min_ranking_nonzero" in expect_rendered:
        ranking = result.aggregates.get("ranking", {})
        nonzero = [c for c, n in ranking.items() if n > 0]
        want = expect_rendered["min_ranking_nonzero"]
        if len(nonzero) < want:
            errs.append(f"ranking has {len(nonzero)} non-zero companies, want {want}")

    return errs


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


def _check_expect_result(conn, expect_result: dict, plan, result) -> list[str]:
    errs: list[str] = []
    if "blog_null_dates" in expect_result:
        n = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_type='blog' AND published_at IS NULL"
        ).fetchone()[0]
        if n != expect_result["blog_null_dates"]:
            errs.append(f"blog_null_dates: expected {expect_result['blog_null_dates']}, got {n}")

    if "total" in expect_result:
        total = result.aggregates.get("total")
        if total != expect_result["total"]:
            errs.append(f"total: expected {expect_result['total']}, got {total}")

    if "by_company" in expect_result:
        got = result.aggregates.get("by_company", {})
        for company, want in expect_result["by_company"].items():
            if got.get(company) != want:
                errs.append(f"by_company.{company}: expected {want}, got {got.get(company)}")

    if "count" in expect_result:
        n = result.aggregates.get("count", len(result.rows))
        if n != expect_result["count"]:
            errs.append(f"count: expected {expect_result['count']}, got {n}")

    if "count_min" in expect_result:
        n = result.aggregates.get("count", len(result.rows))
        if n < expect_result["count_min"]:
            errs.append(f"count {n} < min {expect_result['count_min']}")

    if "showing" in expect_result:
        shown = result.aggregates.get("showing", len(result.rows))
        if shown != expect_result["showing"]:
            errs.append(f"showing: expected {expect_result['showing']}, got {shown}")

    if expect_result.get("all_rows_department"):
        dept = expect_result["all_rows_department"]
        for row in result.rows:
            if row.get("department") != dept:
                errs.append(f"row department expected {dept}, got {row.get('department')}")
                break

    if "ranking_includes" in expect_result:
        ranking = result.aggregates.get("ranking", {})
        caveat = (result.coverage_note or "") + (result.answer or "")
        for company in expect_result["ranking_includes"]:
            if company not in ranking and company not in caveat.lower():
                errs.append(f"ranking missing {company} and no caveat naming it")

    if "ranking_or_caveat" in expect_result:
        ranking = result.aggregates.get("ranking", {})
        caveat = (result.coverage_note or "") + (result.answer or "")
        for company in expect_result["ranking_or_caveat"]:
            if company not in ranking and company not in caveat.lower():
                errs.append(f"{company} absent from ranking and caveat")

    if "timeline_min_companies" in expect_result:
        companies_present = {r.get("company") for r in result.rows}
        for company in expect_result["timeline_min_companies"]:
            if company not in companies_present:
                errs.append(f"timeline missing company {company}")

    return errs


def main() -> int:
    cases = yaml.safe_load(Path(__file__).with_name("queries.yaml").read_text())
    graded = yaml.safe_load(Path(__file__).with_name("graded_render.yaml").read_text())
    cases = cases + graded
    passed = 0
    rows = []
    with get_conn() as conn:
        for case in cases:
            errs: list[str] = []
            expect = case.get("expect", {})
            expect_result = case.get("expect_result", {})
            expect_rendered = case.get("expect_rendered", {})
            result = None
            plan = None

            if "q" in case:
                plan = build_plan(case["q"])
                if case.get("expect_plan"):
                    errs.extend(_match_plan(plan.to_dict(), case.get("expect_plan", {})))
                if expect.get("refuses"):
                    if plan.op != "refuse":
                        errs.append("expected refuse")
                if expect_result or any(k in expect for k in ("total_min", "n_min", "n_max")):
                    result = execute(conn, plan)

            if expect_rendered:
                errs.extend(_check_expect_rendered(conn, case["q"], expect_rendered))

            if expect_result:
                if result is None and "q" in case:
                    result = execute(conn, plan)
                if result is None:
                    result = type("R", (), {"aggregates": {}, "rows": [], "coverage_note": "", "answer": ""})()
                errs.extend(_check_expect_result(conn, expect_result, plan, result))

            if "total_min" in expect and result:
                total = result.aggregates.get("total", 0)
                if total < expect["total_min"]:
                    errs.append(f"total {total} < {expect['total_min']}")
            if ("n_min" in expect or "n_max" in expect) and result:
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
