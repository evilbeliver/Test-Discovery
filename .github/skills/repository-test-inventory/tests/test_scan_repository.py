from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCANNER = SKILL_DIR / "scripts" / "scan-repository.py"


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repository"
        self.repository.mkdir()
        self.output = self.base / "reports"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def scan(self, *args: str) -> tuple[dict, str]:
        command = [
            sys.executable, str(SCANNER), str(self.repository),
            "--output-directory", str(self.output), *args,
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.output / "test-inventory.json").read_text(encoding="utf-8"))
        markdown = (self.output / "inventory-report.md").read_text(encoding="utf-8")
        return data, markdown

    def test_playwright_parameterized_and_skipped_declarations(self) -> None:
        self.write("package.json", '{"devDependencies":{"@playwright/test":"1"}}')
        self.write("playwright.config.ts", "export default {};")
        self.write("tests/shop.spec.ts", """
import { test } from '@playwright/test';
// test('commented out', () => {});
test.each([1, 2])('opens a page', async ({ page }) => { await page.goto('/'); });
test.skip('disabled', async () => {});
""")
        data, markdown = self.scan()
        self.assertEqual(data["summary"]["test_definition_count"], 2)
        self.assertEqual(data["summary"]["explicitly_skipped_test_count"], 1)
        self.assertEqual(data["test_files"][0]["category"], "ui_e2e")
        self.assertEqual(data["frameworks"][0]["name"], "Playwright")
        self.assertIn("tests/shop.spec.ts", markdown)
        self.assertEqual(data["frameworks"][0]["test_definition_count"], 2)

    def test_cypress_legacy_config_and_browser_test_are_detected(self) -> None:
        self.write("cypress.json", '{"integrationFolder":"cypress/integration"}')
        self.write("package.json", '{"devDependencies":{"cypress":"1"}}')
        self.write("cypress/integration/login_spec.js", "describe('login', () => { it('opens', () => cy.visit('/')); });")
        data, _ = self.scan()
        self.assertEqual(data["frameworks"][0]["name"], "Cypress")
        self.assertEqual(data["test_files"][0]["category"], "ui_e2e")
        self.assertEqual(data["summary"]["test_definition_count"], 1)

    def test_jest_does_not_imply_category_and_comments_or_strings_are_not_tests(self) -> None:
        self.write("package.json", '{"devDependencies":{"jest":"1"}}')
        self.write("src/customer.test.js", """
// test('comment', () => {});
const fixture = "test('string noise', () => {})";
test('customer is valid', () => { expect(true).toBe(true); });
""")
        data, _ = self.scan()
        self.assertEqual(data["summary"]["test_definition_count"], 1)
        self.assertEqual(data["test_files"][0]["category"], "unknown")
        self.assertEqual(data["frameworks"][0]["status"], "active")

    def test_monorepo_frameworks_are_associated_with_nearest_package(self) -> None:
        self.write("packages/one/package.json", '{"devDependencies":{"jest":"1"}}')
        self.write("packages/one/tests/check.test.js", "test('one', () => {});")
        self.write("packages/two/package.json", '{"devDependencies":{"vitest":"1"}}')
        self.write("packages/two/tests/check.test.js", "test('two', () => {});")
        data, _ = self.scan()
        by_file = {item["path"]: item["frameworks"] for item in data["test_files"]}
        self.assertEqual(by_file["packages/one/tests/check.test.js"], ["Jest"])
        self.assertEqual(by_file["packages/two/tests/check.test.js"], ["Vitest"])

    def test_mixed_frameworks_and_conflicting_package_import_evidence(self) -> None:
        self.write("package.json", '{"devDependencies":{"jest":"1","vitest":"1"}}')
        self.write("js/check.test.js", "import { test } from 'vitest'; test('js', () => {});")
        self.write("dotnet/Tests.csproj", '<Project><PackageReference Include="xunit" Version="1" /></Project>')
        self.write("dotnet/BasicTests.cs", "[Fact] public void Dotnet() {}")
        data, _ = self.scan()
        js_file = next(item for item in data["test_files"] if item["path"] == "js/check.test.js")
        self.assertEqual(js_file["frameworks"], ["Vitest"])
        self.assertEqual({item["name"] for item in data["frameworks"] if item["status"] == "active"}, {"Vitest", "xUnit"})
        self.assertEqual(data["summary"]["test_definition_count"], 2)

    def test_custom_filename_pattern_can_be_included(self) -> None:
        self.write("package.json", '{"devDependencies":{"jest":"1"}}')
        self.write("checks/customer.flow.ts", "test('custom name', () => {});")
        data, _ = self.scan("--include", "checks/*.flow.ts")
        self.assertEqual(data["summary"]["test_file_count"], 1)
        self.assertEqual(data["test_files"][0]["path"], "checks/customer.flow.ts")

    def test_nunit_xunit_and_mstest_are_detected(self) -> None:
        cases = {
            "nunit": ("NUnit", "[Test]\npublic void Works() {}\n[TestCase(1)]\n[TestCase(2)] public void Data() {}"),
            "xunit": ("xUnit", "[Fact]\npublic void Works() {}\n[Theory]\n[InlineData(1)] public void Data(int n) {}"),
            "mstest": ("MSTest", "[TestMethod]\npublic void Works() {}\n[DataTestMethod]\n[DataRow(1)] public void Data(int n) {}"),
        }
        for package, (_, attributes) in cases.items():
            self.write(f"tests/{package}/Tests.csproj", f'<Project><ItemGroup><PackageReference Include="{package}" Version="1" /></ItemGroup></Project>')
            self.write(f"tests/{package}/SampleTests.cs", f"public class SampleTests {{ {attributes} }}")
        data, _ = self.scan()
        active = {item["name"] for item in data["frameworks"] if item["status"] == "active"}
        self.assertEqual(active, {"NUnit", "xUnit", "MSTest"})
        self.assertEqual(data["summary"]["test_definition_count"], 6)
        self.assertEqual(data["summary"]["test_project_count"], 3)

    def test_xunit_skip_attribute_is_reported(self) -> None:
        self.write("tests/Tests.csproj", '<Project><PackageReference Include="xunit" Version="1" /></Project>')
        self.write("tests/SkippedTests.cs", '[Fact(Skip = "not ready")]\npublic void NotRun() {}')
        data, _ = self.scan()
        self.assertEqual(data["summary"]["test_definition_count"], 1)
        self.assertEqual(data["summary"]["explicitly_skipped_test_count"], 1)

    def test_unknown_test_assets_are_retained(self) -> None:
        self.write("tests/test_legacy.py", '# def test_commented():\n"""def test_docstring(): pass"""\ndef test_thing():\n    assert True\n')
        data, _ = self.scan()
        self.assertEqual(data["summary"]["test_file_count"], 1)
        self.assertTrue(data["test_files"][0]["suspected"])
        self.assertEqual(data["test_files"][0]["frameworks"], ["Unknown"])
        self.assertEqual(data["test_files"][0]["suspected_definition_count"], 1)
        self.assertEqual(data["summary"]["test_definition_count"], 0)

    def test_zero_test_repository_has_consistent_valid_reports(self) -> None:
        self.write("src/app.js", "export const answer = 42;\n")
        data, markdown = self.scan()
        self.assertEqual(data["summary"]["test_file_count"], 0)
        self.assertIn("No test files identified.", markdown)
        self.assertEqual(data["summary"]["classification_counts"]["unknown"], 0)

    def test_exclusions_can_be_overridden_without_overriding_explicit_excludes(self) -> None:
        self.write("node_modules/demo/test.js", "test('one', () => {});")
        data, _ = self.scan()
        self.assertEqual(data["summary"]["test_file_count"], 0)
        data, _ = self.scan("--include", "node_modules/demo/test.js")
        self.assertEqual(data["summary"]["test_file_count"], 1)
        data, _ = self.scan("--include", "node_modules/demo/test.js", "--exclude", "node_modules")
        self.assertEqual(data["summary"]["test_file_count"], 0)

    def test_nested_project_association_uses_nearest_project(self) -> None:
        self.write("Root.csproj", "<Project />")
        self.write("sub/Inner.csproj", "<Project />")
        self.write("sub/FeatureTests.cs", "[Fact] public void Works() {}")
        data, _ = self.scan()
        self.assertEqual(data["test_files"][0]["test_project"], "sub/Inner.csproj")

    def test_output_inside_repository_is_rejected(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCANNER), str(self.repository), "--output-directory", str(self.repository / "reports")],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the scanned repository", result.stderr)
        self.assertFalse((self.repository / "reports").exists())

    def test_invalid_repository_path_returns_actionable_error(self) -> None:
        missing = self.base / "missing"
        result = subprocess.run([sys.executable, str(SCANNER), str(missing)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not exist", result.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_external_symlink_is_not_followed(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "test.js").write_text("test('secret', () => {});", encoding="utf-8")
        (self.repository / "linked").symlink_to(outside, target_is_directory=True)
        data, _ = self.scan()
        self.assertEqual(data["summary"]["test_file_count"], 0)
        self.assertTrue(any("symbolic link" in value for value in data["limitations"]))

    def test_malformed_manifest_is_reported_without_stopping_scan(self) -> None:
        self.write("package.json", "{ not valid")
        self.write("tests/basic.test.js", "test('works', () => {});")
        data, _ = self.scan()
        self.assertEqual(data["summary"]["test_file_count"], 1)
        self.assertTrue(any("Invalid JSON manifest" in value for value in data["limitations"]))


if __name__ == "__main__":
    unittest.main()
