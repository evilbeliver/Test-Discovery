#!/usr/bin/env python3
"""Adapt scanner JSON and compare it with an independent static-definition baseline."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


FRAMEWORKS = {
    "playwright": "Playwright", "jest": "Jest", "vitest": "Vitest",
    "cypress": "Cypress", "mocha": "Mocha", "jasmine": "Jasmine",
    "nunit": "NUnit", "xunit": "xUnit", "mstest": "MSTest",
    "testcafe": "TestCafe", "selenium-js": "Selenium WebDriver",
    "webdriverio": "WebdriverIO", "puppeteer": "Puppeteer", "protractor": "Protractor",
    "pytest": "pytest",
}


def adapt_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    if inventory.get("schema_version") != "1.1":
        raise ValueError("Expected scanner schema_version 1.1; rescan with the updated scanner.")
    files = inventory.get("test_files")
    if not isinstance(files, list):
        raise ValueError("Inventory test_files must be an array.")
    definitions: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for file in files:
        if not isinstance(file, dict) or not isinstance(file.get("definitions"), list):
            raise ValueError("Every test_files entry must contain a definitions array.")
        if file.get("suspected"):
            unknown.append({"path": file["path"], "framework": None})
        for item in file["definitions"]:
            if not isinstance(item, dict):
                raise ValueError("Every definition must be a JSON object.")
            if item.get("kind") != "test":
                continue
            framework = FRAMEWORKS.get(item.get("framework"), "unknown")
            if framework == "Mocha" and "selenium-js" in item.get("tools", []):
                framework = "Mocha + Selenium WebDriver"
            record = {
                "path": file["path"], "identifier": item.get("name"),
                "id": item.get("id"), "line": item.get("line"),
            }
            if "framework" in item:
                record["framework"] = framework
            if "category" in item:
                record["primary_category"] = {"ui_e2e": "ui"}.get(item["category"], item["category"])
            if "status" in item:
                record["status"] = {"todo": "pending"}.get(item["status"], item["status"])
            if "parameterized" in item:
                record["parameterized"] = item["parameterized"]
            if "body_iteration" in item:
                record["body_iteration"] = item["body_iteration"]
            definitions.append(record)
    summary = {
        "total_definitions": len(definitions),
        "counts_by_framework": dict(Counter(d.get("framework", "unknown") for d in definitions)),
        "counts_by_category": dict(Counter(d.get("primary_category", "unknown") for d in definitions)),
        "counts_by_scenario": dict(Counter(
            Path(d["path"]).parts[1] for d in definitions
            if len(Path(d["path"]).parts) > 1 and Path(d["path"]).parts[0] == "scenarios"
        )),
    }
    if inventory.get("summary", {}).get("test_definition_count") != len(definitions):
        raise ValueError("Scanner summary does not reconcile with recognized definition records.")
    return {
        "schema_version": "repository-test-inventory-adapter/1",
        "scan": inventory.get("scan", {}), "definitions": definitions, "summary": summary,
        "unknown_assets": unknown,
        "excluded_assets": [{"path": path} for path in inventory.get("scan", {}).get("excluded_paths", [])],
    }


def _label(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _key(record: dict[str, Any]) -> tuple[str, str]:
    return record["path"], _label(record["identifier"])


def _matches(wanted: dict[str, Any], found: dict[str, Any]) -> bool:
    if not isinstance(found.get("identifier"), str) or found.get("path") != wanted["path"]:
        return False
    if _key(wanted) == _key(found):
        return True
    test_id = wanted.get("test_id")
    if not isinstance(test_id, str) or not test_id or not found["identifier"].strip():
        return False
    return _label(found["identifier"].split(maxsplit=1)[0]) == _label(test_id)


def validate(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    baseline = expected.get("definitions")
    observed = actual.get("definitions")
    if not isinstance(baseline, list) or not isinstance(observed, list):
        raise ValueError("Expected and adapted reports must contain definitions arrays.")
    if any(not isinstance(d, dict) for d in baseline + observed):
        raise ValueError("Every expected and actual definition must be a JSON object.")
    if expected.get("expected_definition_count") != len(baseline):
        raise ValueError("Expected definition count does not reconcile with its records.")
    if any(not isinstance(d.get("path"), str) or not isinstance(d.get("identifier"), str) for d in baseline):
        raise ValueError("Expected definitions require path and identifier strings.")
    if len({_key(d) for d in baseline}) != len(baseline):
        raise ValueError("Expected path/identifier pairs must be unique.")
    checks: list[dict[str, Any]] = []
    complete = all(
        isinstance(d.get("path"), str) and isinstance(d.get("identifier"), str)
        and bool(d["identifier"]) for d in observed
    )
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    remaining = list(observed)
    missing = []
    for definition in baseline:
        index = next((
            i for i, item in enumerate(remaining)
            if _matches(definition, item)
        ), None)
        if index is None:
            missing.append(definition)
        else:
            matched.append((definition, remaining.pop(index)))
    checks.append({
        "name": "discovery",
        "status": "UNVERIFIABLE" if not complete else "FAIL" if missing or remaining else "PASS",
    })
    dimensions: dict[str, Any] = {}
    for field in ("framework", "primary_category", "status", "parameterized"):
        mismatches = []
        unknown_records = []
        unknown = 0
        absent = 0
        for wanted, found in matched:
            if field not in found:
                absent += 1
            elif found[field] is None or found[field] == "unknown":
                unknown += 1
                unknown_records.append({"path": wanted["path"], "identifier": wanted["identifier"], "expected": wanted[field], "actual": found[field]})
            elif found[field] != wanted[field]:
                mismatches.append({
                    "path": wanted["path"], "identifier": wanted["identifier"],
                    "expected": wanted[field], "actual": found[field],
                })
        correct = len(matched) - len(mismatches) - unknown - absent
        dimensions[field] = {
            "matched_denominator": len(matched), "correct": correct,
            "incorrect": len(mismatches), "unknown": unknown, "missing_fields": absent,
            "mismatches": mismatches, "unknown_records": unknown_records,
        }
        checks.append({
            "name": field, "status": "UNVERIFIABLE" if absent or not complete
            else "NOT_APPLICABLE" if not matched
            else "FAIL" if mismatches or unknown else "PASS",
        })
    excluded = [d["path"].rstrip("/") for d in actual.get("excluded_assets", [])]
    expected_excluded = expected.get("excluded_fixtures", [])
    exclusion_failures = [
        d["path"] for d in expected_excluded
        if not any(d["path"] == path or d["path"].startswith(path + "/") for path in excluded)
        or any(item.get("path") == d["path"] for item in observed)
    ]
    checks.append({
        "name": "exclusions", "status": "FAIL" if exclusion_failures else "PASS" if expected_excluded else "NOT_APPLICABLE",
        "failures": exclusion_failures,
    })
    unknown_assets = actual.get("unknown_assets", [])
    unknown_paths = {d["path"] for d in unknown_assets}
    invalid_unknowns = [
        d["path"] for d in unknown_assets if d.get("framework") not in (None, "unknown", "Unknown")
        or any(item.get("path") == d["path"] and item.get("framework") not in (None, "unknown", "Unknown") for item in observed)
    ]
    absent_unknowns = [d["path"] for d in expected.get("unknown_assets", []) if d["path"] not in unknown_paths]
    checks.append({
        "name": "unknown_assets",
        "status": "FAIL" if absent_unknowns or invalid_unknowns else "PASS" if expected.get("unknown_assets") else "NOT_APPLICABLE",
        "missing": absent_unknowns,
        "invalid_framework_assignments": invalid_unknowns,
        "additional": sorted(unknown_paths - {d["path"] for d in expected.get("unknown_assets", [])}),
    })
    tp, fp, fn = len(matched), len(remaining), len(missing)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not baseline else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    assessable = not any(c["status"] == "UNVERIFIABLE" for c in checks)
    scenarios = sorted({d.get("scenario", "unspecified") for d in baseline} | set(expected.get("negative_scenarios", [])))
    scenario_results = []
    for scenario in scenarios:
        prefix = f"scenarios/{scenario}/"
        scenario_results.append({
            "scenario": scenario,
            "expected": sum(d.get("scenario") == scenario for d in baseline),
            "matched": sum(w.get("scenario") == scenario for w, _ in matched),
            "missing": sum(d.get("scenario") == scenario for d in missing),
            "unexpected": sum(d.get("path", "").startswith(prefix) for d in remaining),
        })
    supported = [d for d in baseline if d.get("framework") in set(FRAMEWORKS.values()) | {"Mocha + Selenium WebDriver"}]
    return {
        "schema_version": "repository-test-inventory-validation/1",
        "scan_completed": actual.get("scan", {}).get("status") in {"completed", "completed_with_limitations"},
        "results_assessable": assessable,
        "validation_passed": assessable and all(c["status"] in {"PASS", "NOT_APPLICABLE"} for c in checks)
        and actual.get("scan", {}).get("status") in {"completed", "completed_with_limitations"},
        "checks": checks,
        "discovery": {
            "expected": len(baseline), "observed": len(observed),
            "tp": tp if complete else None, "fp": fp if complete else None, "fn": fn if complete else None,
            "precision": precision if complete else None, "recall": recall if complete else None,
            "f1": 2 * precision * recall / (precision + recall) if complete and precision + recall else None,
        },
        "supported_scope": {
            "expected": len(supported),
            "matched": sum(w in supported for w, _ in matched),
            "recall": sum(w in supported for w, _ in matched) / len(supported) if supported else None,
            "note": "Separate denominator; unsupported definitions remain in full-baseline discovery.",
        },
        "dimensions": dimensions, "scenarios": scenario_results,
        "missing": missing, "unexpected": remaining,
    }


def exit_code(result: dict[str, Any]) -> int:
    if not result["results_assessable"]:
        return 3
    return 0 if result["validation_passed"] else 1


def render(result: dict[str, Any]) -> str:
    lines = ["# Inventory validation", ""]
    for field in ("scan_completed", "results_assessable", "validation_passed"):
        lines.append(f"- {field}: {result[field]}")
    lines.extend(["", "## Checks", ""])
    lines.extend(f"- {c['name']}: {c['status']}" for c in result["checks"])
    lines.extend(["", "## Discovery", "", "```json", json.dumps(result["discovery"], indent=2), "```"])
    lines.extend(["", "## Dimensions (matched definitions only)", ""])
    for name, values in result["dimensions"].items():
        lines.append(f"- {name}: {values['correct']} correct, {values['incorrect']} incorrect, "
                     f"{values['unknown']} unknown, {values['missing_fields']} missing fields / {values['matched_denominator']} matched.")
    lines.extend(["", "## Scenarios", "", "| Scenario | Expected | Matched | Missing | Unexpected |", "|---|---:|---:|---:|---:|"])
    lines.extend(f"| {s['scenario']} | {s['expected']} | {s['matched']} | {s['missing']} | {s['unexpected']} |" for s in result["scenarios"])
    lines.extend(["", "Full discrepancies and additional unknown assets are recorded in validation-result.json.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        expected = json.loads(args.expected.read_text(encoding="utf-8"))
        if not isinstance(inventory, dict) or not isinstance(expected, dict):
            raise ValueError("Inventory and baseline roots must be JSON objects.")
        output = args.output_directory.expanduser().resolve()
        root = Path(inventory["repository"]["path"]).resolve()
        if output == root or root in output.parents:
            raise ValueError("Validation output must be outside the scanned repository.")
        adapted = adapt_inventory(inventory)
        result = validate(expected, adapted)
        result["provenance"] = {
            "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
            "expected_sha256": hashlib.sha256(args.expected.read_bytes()).hexdigest(),
            "scanner_sha256": inventory.get("scan", {}).get("scanner_sha256"),
            "scan": inventory.get("scan"),
        }
        output.mkdir(parents=True, exist_ok=True)
        for name in ("adapted-inventory.json", "validation-result.json", "validation-report.md"):
            report = output / name
            if report.is_symlink() or (report.exists() and report.stat().st_nlink > 1):
                raise ValueError(f"Refusing to overwrite a linked report file: {report}")
        for name, data in (("adapted-inventory.json", adapted), ("validation-result.json", result)):
            (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        (output / "validation-report.md").write_text(render(result), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"validate-inventory: {error}", file=sys.stderr)
        return 2
    print(render(result))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
