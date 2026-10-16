from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate-inventory.py"
SPEC = importlib.util.spec_from_file_location("inventory_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = {
            "path": "scenarios/example/sample.test.js", "identifier": "works",
            "framework": "Jest", "primary_category": "unit", "status": "active",
            "parameterized": False, "scenario": "example",
        }
        self.expected = {"expected_definition_count": 1, "definitions": [self.definition]}
        self.actual = {
            "definitions": [copy.deepcopy(self.definition)],
            "scan": {"status": "completed"}, "unknown_assets": [], "excluded_assets": [],
        }

    def test_matching_report_passes(self) -> None:
        result = validator.validate(self.expected, self.actual)
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["discovery"]["tp"], 1)
        self.assertEqual(validator.exit_code(result), 0)

    def test_all_unverifiable_cannot_pass(self) -> None:
        self.actual["definitions"] = [{"path": self.definition["path"]}]
        result = validator.validate(self.expected, self.actual)
        self.assertFalse(result["results_assessable"])
        self.assertFalse(result["validation_passed"])
        self.assertIsNone(result["discovery"]["tp"])
        self.assertEqual(validator.exit_code(result), 3)

    def test_partial_assessability_cannot_pass(self) -> None:
        del self.actual["definitions"][0]["parameterized"]
        result = validator.validate(self.expected, self.actual)
        self.assertFalse(result["results_assessable"])
        self.assertEqual(validator.exit_code(result), 3)

    def test_false_positive_and_negative_do_not_cancel(self) -> None:
        self.actual["definitions"][0]["identifier"] = "different"
        result = validator.validate(self.expected, self.actual)
        self.assertEqual(result["discovery"]["tp"], 0)
        self.assertEqual(result["discovery"]["fp"], 1)
        self.assertEqual(result["discovery"]["fn"], 1)
        self.assertFalse(result["validation_passed"])

    def test_unknown_is_measured_not_fabricated(self) -> None:
        self.actual["definitions"][0]["primary_category"] = "unknown"
        self.actual["definitions"][0]["parameterized"] = None
        result = validator.validate(self.expected, self.actual)
        self.assertTrue(result["results_assessable"])
        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["dimensions"]["primary_category"]["unknown"], 1)
        self.assertEqual(result["dimensions"]["parameterized"]["unknown"], 1)
        self.assertEqual(validator.exit_code(result), 1)

    def test_additional_unknowns_are_allowed(self) -> None:
        self.expected["unknown_assets"] = [{"path": "ambiguous.js"}]
        self.actual["unknown_assets"] = [{"path": "ambiguous.js"}, {"path": "unsupported.py"}]
        result = validator.validate(self.expected, self.actual)
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["checks"][-1]["additional"], ["unsupported.py"])

    def test_directory_exclusion_and_included_conflict(self) -> None:
        self.expected["excluded_fixtures"] = [{"path": "generated/test.js"}]
        self.actual["excluded_assets"] = [{"path": "generated"}]
        self.assertTrue(validator.validate(self.expected, self.actual)["validation_passed"])
        self.actual["definitions"].append({**self.definition, "path": "generated/test.js"})
        result = validator.validate(self.expected, self.actual)
        self.assertEqual(next(c for c in result["checks"] if c["name"] == "exclusions")["status"], "FAIL")

    def test_adapter_filters_suites_and_suspected_and_normalizes(self) -> None:
        inventory = {
            "schema_version": "1.1", "summary": {"test_definition_count": 1},
            "scan": {"status": "completed", "excluded_paths": ["generated"]},
            "test_files": [{
                "path": self.definition["path"], "suspected": False,
                "definitions": [
                    {"kind": "test", "framework": "mocha", "tools": ["selenium-js"],
                     "name": "works", "category": "ui_e2e", "status": "todo", "parameterized": True},
                    {"kind": "suite"}, {"kind": "suspected_test"},
                ],
            }],
        }
        adapted = validator.adapt_inventory(inventory)
        self.assertEqual(len(adapted["definitions"]), 1)
        definition = adapted["definitions"][0]
        self.assertEqual(definition["framework"], "Mocha + Selenium WebDriver")
        self.assertEqual(definition["primary_category"], "ui")
        self.assertEqual(definition["status"], "pending")
        self.assertEqual(adapted["summary"]["counts_by_category"], {"ui": 1})
        inventory["summary"]["test_definition_count"] = 2
        with self.assertRaisesRegex(ValueError, "reconcile"):
            validator.adapt_inventory(inventory)

    def test_scan_completion_is_not_validation(self) -> None:
        self.actual["scan"]["status"] = "failed"
        result = validator.validate(self.expected, self.actual)
        self.assertFalse(result["scan_completed"])
        self.assertFalse(result["validation_passed"])

    def test_invalid_cli_input_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bad.json"
            path.write_text("{}", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT), "--inventory", str(path),
                "--expected", str(path), "--output-directory", str(root / "output"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("validate-inventory:", result.stderr)

    def test_duplicate_actual_is_a_false_positive(self) -> None:
        self.actual["definitions"].append(copy.deepcopy(self.definition))
        result = validator.validate(self.expected, self.actual)
        self.assertEqual(result["discovery"]["tp"], 1)
        self.assertEqual(result["discovery"]["fp"], 1)

    def test_baseline_id_prefix_matches_without_fixture_specific_rules(self) -> None:
        self.expected["definitions"][0]["test_id"] = "ANY-123"
        self.actual["definitions"][0]["identifier"] = "ANY-123 works with input %s"
        self.assertTrue(validator.validate(self.expected, self.actual)["validation_passed"])
        self.actual["definitions"][0]["identifier"] = "ANY-1234 works"
        self.assertEqual(validator.validate(self.expected, self.actual)["discovery"]["tp"], 0)

    def test_unknown_cannot_be_assigned_a_confirmed_framework(self) -> None:
        self.expected["unknown_assets"] = [{"path": "ambiguous.js"}]
        self.actual["unknown_assets"] = [{"path": "ambiguous.js", "framework": "Jest"}]
        self.assertFalse(validator.validate(self.expected, self.actual)["validation_passed"])

    def test_cli_output_and_exit_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target with spaces"
            target.mkdir()
            inventory = {
                "schema_version": "1.1", "repository": {"path": str(target)},
                "scan": {"status": "completed", "excluded_paths": []},
                "summary": {"test_definition_count": 1},
                "test_files": [{
                    "path": self.definition["path"], "suspected": False,
                    "definitions": [{
                        "kind": "test", "framework": "jest", "name": "works", "category": "unit",
                        "status": "active", "parameterized": False,
                    }],
                }],
            }
            source = root / "inventory.json"
            baseline = root / "expected.json"
            baseline.write_text(json.dumps(self.expected), encoding="utf-8")
            command = [
                sys.executable, str(SCRIPT), "--inventory", str(source),
                "--expected", str(baseline), "--output-directory", str(root / "reports with spaces"),
            ]
            for category, status, exit_status in (("unit", "PASS", 0), ("unknown", "FAIL", 1)):
                inventory["test_files"][0]["definitions"][0]["category"] = category
                source.write_text(json.dumps(inventory), encoding="utf-8")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, exit_status, result.stderr)
                self.assertIn(f"primary_category: {status}", result.stdout)
                self.assertTrue((root / "reports with spaces/adapted-inventory.json").exists())
            del inventory["test_files"][0]["definitions"][0]["category"]
            source.write_text(json.dumps(inventory), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            unsafe = command[:-1] + [str(target / "reports")]
            result = subprocess.run(unsafe, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((target / "reports").exists())


if __name__ == "__main__":
    unittest.main()
