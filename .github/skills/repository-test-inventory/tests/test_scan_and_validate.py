from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / "scripts" / "scan-and-validate.py"


class WorkflowTests(unittest.TestCase):
    def test_pass_failure_provenance_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repository with spaces"
            root.mkdir()
            (root / "test_sample.py").write_text("import pytest\ndef test_works():\n    assert True\n")
            expected = base / "expected.json"
            baseline = {
                "expected_definition_count": 1,
                "definitions": [{
                    "path": "test_sample.py", "identifier": "test_works", "framework": "pytest",
                    "primary_category": "unit", "status": "active", "parameterized": False,
                }],
            }
            expected.write_text(json.dumps(baseline))
            before = (root / "test_sample.py").read_bytes()

            def run(output: Path) -> subprocess.CompletedProcess[str]:
                return subprocess.run([
                    sys.executable, "-B", str(WORKFLOW), str(root),
                    "--expected", str(expected), "--output-directory", str(output),
                ], capture_output=True, text=True, check=False)

            output = base / "passing output"
            result = run(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output / "workflow-summary.json").read_text())
            self.assertTrue(summary["validation_passed"])
            self.assertTrue(summary["results_assessable"])
            self.assertEqual(summary["discovery"]["tp"], 1)
            self.assertEqual(len(summary["stages"]), 2)
            self.assertTrue(all(stage["elapsed_seconds"] >= 0 for stage in summary["stages"]))
            self.assertEqual(len(summary["provenance"]["expected_sha256"]), 64)
            saved = (output / "workflow-summary.json").read_bytes()
            self.assertEqual(run(output).returncode, 2)
            self.assertEqual(saved, (output / "workflow-summary.json").read_bytes())
            baseline["definitions"][0]["primary_category"] = "api"
            expected.write_text(json.dumps(baseline))
            failed_output = base / "failing output"
            self.assertEqual(run(failed_output).returncode, 1)
            failed = json.loads((failed_output / "workflow-summary.json").read_text())
            self.assertTrue(failed["scan_completed"])
            self.assertTrue(failed["results_assessable"])
            self.assertFalse(failed["validation_passed"])
            expected.write_text("{invalid")
            invalid_output = base / "invalid baseline output"
            self.assertEqual(run(invalid_output).returncode, 2)
            invalid = json.loads((invalid_output / "workflow-summary.json").read_text())
            self.assertIn("Validator failed", invalid["error"])
            self.assertEqual(run(root / "unsafe").returncode, 2)
            self.assertFalse((root / "unsafe").exists())
            self.assertEqual(before, (root / "test_sample.py").read_bytes())

    def test_unverifiable_validation_retains_nonzero_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            (root / "package.json").write_text('{"devDependencies":{"jest":"1"}}')
            (root / "sample.test.js").write_text("test(dynamicTitle, () => {});")
            expected = base / "expected.json"
            expected.write_text(json.dumps({
                "expected_definition_count": 1,
                "definitions": [{
                    "path": "sample.test.js", "identifier": "known title",
                    "framework": "Jest", "primary_category": "unknown",
                    "status": "active", "parameterized": False,
                }],
            }))
            output = base / "output"
            result = subprocess.run([
                sys.executable, "-B", str(WORKFLOW), str(root),
                "--expected", str(expected), "--output-directory", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 3, result.stderr)
            summary = json.loads((output / "workflow-summary.json").read_text())
            self.assertTrue(summary["scan_completed"])
            self.assertFalse(summary["results_assessable"])
            self.assertFalse(summary["validation_passed"])
            self.assertEqual(summary["stages"][-1]["exit_code"], 3)


if __name__ == "__main__":
    unittest.main()
