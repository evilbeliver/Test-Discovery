#!/usr/bin/env python3
"""Scan and validate static definitions, preserving separate outcomes and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--no-default-excludes", action="store_true")
    args = parser.parse_args()
    try:
        root = args.repository.expanduser().resolve(strict=True)
        expected = args.expected.expanduser().resolve(strict=True)
        output = args.output_directory.expanduser().resolve()
        if not root.is_dir() or not expected.is_file():
            raise ValueError("Repository must be a directory and baseline must be a file.")
        if output == root or root in output.parents:
            raise ValueError("Output directory must be outside the scanned repository.")
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError("Use a fresh, empty output directory to preserve prior evidence.")
        scripts = Path(__file__).resolve().parent
        scanner = scripts / "scan-repository.py"
        validator = scripts / "validate-inventory.py"
        scan_command = [
            sys.executable, "-B", str(scanner), str(root),
            "--output-directory", str(output),
        ]
        for option in ("include", "exclude"):
            for pattern in getattr(args, option):
                scan_command.extend([f"--{option}", pattern])
        if args.no_default_excludes:
            scan_command.append("--no-default-excludes")
        validate_command = [
            sys.executable, "-B", str(validator),
            "--inventory", str(output / "test-inventory.json"),
            "--expected", str(expected), "--output-directory", str(output),
        ]
        summary: dict[str, Any] = {
            "schema_version": "repository-test-inventory-workflow/1",
            "repository": str(root), "output_directory": str(output),
            "python_version": sys.version,
            "provenance": {
                "scanner_sha256": _sha256(scanner), "validator_sha256": _sha256(validator),
                "workflow_sha256": _sha256(Path(__file__)), "expected_sha256": _sha256(expected),
                "expected_path": str(expected),
            },
            "stages": [], "scan_completed": False, "results_assessable": False,
            "validation_passed": False,
        }
        output.mkdir(parents=True, exist_ok=True)
        result_code = 2
        for name, command in (("scan", scan_command), ("validation", validate_command)):
            start = perf_counter()
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            summary["stages"].append({
                "name": name, "command": command, "exit_code": completed.returncode,
                "elapsed_seconds": perf_counter() - start,
            })
            if completed.stderr:
                print(completed.stderr, file=sys.stderr, end="")
            if completed.stdout:
                print(completed.stdout, end="")
            result_code = completed.returncode
            if name == "scan":
                if result_code:
                    summary["error"] = "Scanner failed; validation was not attempted."
                    break
                inventory = json.loads((output / "test-inventory.json").read_text(encoding="utf-8"))
                summary["scan_completed"] = inventory["scan"]["status"] in {"completed", "completed_with_limitations"}
                summary["scan"] = inventory["scan"]
                summary["limitations"] = inventory["limitations"]
            elif result_code in {0, 1, 3}:
                result = json.loads((output / "validation-result.json").read_text(encoding="utf-8"))
                for field in ("scan_completed", "results_assessable", "validation_passed",
                              "discovery", "supported_scope", "dimensions", "checks"):
                    summary[field] = result[field]
            else:
                summary["error"] = "Validator failed; see stderr for the input or I/O error."
        summary["exit_code"] = result_code
        summary["reports"] = {
            name: str(output / name) for name in (
                "inventory-report.md", "test-inventory.json", "adapted-inventory.json",
                "validation-report.md", "validation-result.json",
            ) if (output / name).is_file()
        }
        report = output / "workflow-summary.json"
        if report.is_symlink() or (report.exists() and report.stat().st_nlink > 1):
            raise ValueError(f"Refusing to overwrite a linked report file: {report}")
        report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Workflow summary: {report}")
        return result_code
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"scan-and-validate: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
