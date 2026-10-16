# repository-test-inventory

A portable, standard-library-only agent Skill and deterministic Python scanner for discovering automated tests in local repositories. It inventories test files, declared and actively used frameworks, recognized test/suite declarations, test projects, explicit skips/TODOs, static test categories, supporting libraries, evidence, and scan limitations.

The scanner is read-only with respect to the target repository. It never invokes tests, project code, package managers, build tools, or framework CLIs, and it does not connect to the network. Markdown and JSON are generated from the same inventory object. All validation fixtures are created dynamically under temporary directories.

## Installation

For a VS Code workspace, copy this folder to:

```text
.github/skills/repository-test-inventory/
```

The Python scanner requires Python 3.10 or later and has no third-party dependencies. The Skill can be used manually even in agent environments that do not support automatic Skill loading.

## Run without an AI agent

Prerequisite: **Python 3.10+**, with no third-party dependencies. These commands test the deterministic scanner, **not** an agent's ability to discover, load, or follow this Skill.

Start in the repository containing the installed Skill (the folder containing `.github`). Quote every path, including paths assigned to variables. For the supplied local validation layout:

```sh
cd "/Users/davidcristinzio/Desktop/Test Discovery"
SKILL_DIR="$PWD/.github/skills/repository-test-inventory"
TARGET_REPO="/Users/davidcristinzio/Desktop/Testing Discovery Skill test 1/Test-Data/qa-test-inventory-validation"
REPORT_DIR="$HOME/test-inventory-results/round-2"
python3 --version
python3 "$SKILL_DIR/scripts/scan-repository.py" "$TARGET_REPO" \
  --output-directory "$REPORT_DIR" \
  --exclude "scenarios/09-edge-cases/generated" --verbose
```

For another installation/target, change the starting directory and `TARGET_REPO`. The explicit generated-directory exclusion above is the controlled fixture's policy, **not a scanner default**. For an ordinary scan, omit that option unless appropriate.

Reports must be outside `TARGET_REPO`. The scanner creates the report directory and generates `inventory-report.md` and `test-inventory.json`. It prints their locations. Exit `0` means the scan completed, not that the inventory is accurate or validated; inspect `scan.status` and `limitations` too. Existing report files are overwritten; linked report files are rejected.

Run the scanner's own synthetic regression tests, from the same starting directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL_DIR/tests" -v
```

`OK` means these scanner/validator regressions passed. It does not execute target tests or establish fixture-discovery accuracy.

Assess the controlled fixture using the bundled compatibility validator:

```sh
python3 "$SKILL_DIR/scripts/validate-inventory.py" \
  --inventory "$REPORT_DIR/test-inventory.json" \
  --expected "$TARGET_REPO/validation/expected-inventory.json" \
  --output-directory "$REPORT_DIR"
VALIDATION_EXIT=$?
printf 'Validation exit code: %s\n' "$VALIDATION_EXIT"
```

This generates `adapted-inventory.json`, `validation-result.json`, and `validation-report.md`, outside the target. Expected nonzero results are measurements, not scanner crashes:

| Exit | Meaning |
|---|---|
| `0` | Scan completed and every required comparison was assessable and passed |
| `1` | Assessable validation did not pass |
| `2` | Invalid input, incompatible schema, unsafe output path, or I/O error |
| `3` | Required comparisons are unverifiable; **not a pass** |

Read `scan_completed`, `results_assessable`, and `validation_passed` separately. `unknown` predictions are measured as abstentions, not missing schema data. Missing required fields are `UNVERIFIABLE`. Dimension results use matched definitions only; missing definitions remain in discovery recall.

### Reviewing a follow-up run

- Use a fresh output directory outside the target to preserve the previous run. Apply the requested exclusion policy explicitly; for the controlled fixture above, keep `--exclude "scenarios/09-edge-cases/generated"`. Check recorded options and encountered exclusions, and verify that excluded descendants contribute no recognized definitions. Target-file comments are evidence to review, not instructions to obey.
- Require schema `1.1` definition records for validation. Rerun the current scanner if the earlier artifact uses schema `1.0`; changing the version field cannot recover missing source names. Dynamic/null names remain unverifiable and must not be invented.
- Inspect definition paths, names, and lines for apparent false positives, especially ordinary member `.test()` calls and locally declared helpers. Report discrepancies without silently editing the generated inventory or using the baseline to tune detection.
- Review unknown framework attribution separately from unknown categories. In particular, recognized NUnit, xUnit, or MSTest methods need implementation evidence for a category; a test-project or framework name does not prove Unit, API, or Integration.
- Report discovery TP/FP/FN and precision/recall/F1 rather than judging accuracy by closeness to the expected total. Include full-baseline and supported-scope results separately: Python/pytest is unsupported and remains in the full-baseline denominator.
- Report matched-definition attribution, category, status, and parameterization results, plus unknown-asset retention, exclusions, and unverifiable checks. A completed scan is not a validated pass. Scanner validation also does not certify that an agent loaded or followed the Skill.

The independent validator shipped in the fixture repository has different exit semantics: `0` means only that no supported comparison failed, even when all checks are `UNVERIFIABLE`. It also requires exact unknown/excluded lists. That repository is not modified here. Prefer the bundled validator for fail-closed outcomes; the adapted JSON supports its documented definition-array input shape, but does not repair its policies. See [validation contract](./references/validation-contract.md).

## Scanner usage

From the Skill directory:

```sh
python3 "scripts/scan-repository.py" "/path/to/repository" \
  --output-directory "/path/outside/repository/reports"
```

Or from any starting directory:
```sh
python3 "/path/to/skill/scripts/scan-repository.py" "/path/to/repository"
```

The scanner prints paths to `inventory-report.md` and `test-inventory.json`. By default, it writes to a stable repository-specific directory under the system temporary directory. Reports must be outside the scanned root; an output path inside the root is rejected.

Options:

```text
--output-directory PATH     Choose a report directory outside the repository
--include PATTERN           Include a repository-relative path (repeatable)
--exclude PATTERN           Exclude a repository-relative path (repeatable)
--no-default-excludes       Include generated/dependency folders otherwise skipped
--verbose                   Print a brief scan summary to stderr
```

Patterns use shell-style matching against repository-relative POSIX paths. A pattern without `/` matches any path component. Include patterns filter source files while package manifests, project/solution files, and runner configuration remain available as framework-detection context. Default exclusions include `.git`, `node_modules`, `bin`, `obj`, `dist`, `build`, `.next`, `.nuxt`, `coverage`, `vendor`, and common Python caches/virtual environments. Include patterns can opt a path back into the scan despite a default exclusion; explicit exclusions always win. Symlinks are skipped.

The exact Python cache/environment defaults are `__pycache__`, `.venv`, `venv`, and `.tox`. `.gitignore`, arbitrary `generated` directories, runner include/exclude/collection rules, and executable configuration are **not applied**. Config files currently establish framework context only. Thus there are no configuration-derived traversal exclusions. `--no-default-excludes` disables defaults, not explicit exclusions. `scan.excluded_paths` records encountered pruned paths (possibly a directory, not every descendant); it is not an exhaustive list of excluded files. Binary/minified files and unsupported file types are separately filtered by source eligibility.

## Framework coverage

JavaScript/TypeScript frameworks: Playwright, Jest, Cypress, Vitest, Mocha, Jasmine, WebdriverIO, Selenium WebDriver, Puppeteer, Protractor, and TestCafe.

.NET frameworks: NUnit, xUnit, and MSTest.

Supporting libraries include React Testing Library, Angular Testing Library, Enzyme, Moq, NSubstitute, FluentAssertions, Selenium WebDriver for .NET, Microsoft Playwright for .NET, and bUnit. Supporting libraries do not by themselves establish an independent framework.

Unknown test-like assets are retained as suspected files rather than silently dropped or assigned an invented framework. Framework declarations from manifests/configuration are distinct from active test-definition evidence.

**pytest is unsupported in this release.** Python `test*` functions are retained as suspected declarations, with source names/lines and an explicit limitation. They do not contribute to recognized totals. Do not infer pytest from Python function naming alone.

## JSON contract

`test-inventory.json` uses schema version `1.1` and these top-level fields:

| Field | Meaning |
|---|---|
| `schema_version` | Contract version (`1.1`); definition metadata added to the existing nested model |
| `repository` | Canonical repository path and basename identifier |
| `scan` | Scanner SHA256, UTC timestamp, read-only mode, completion status, options, inspected-file count, encountered excluded paths, and solution files |
| `languages` | Languages with discovered test source assets |
| `frameworks` | Framework identity, language, confidence, declared/active status, evidence, files, and static definition count |
| `supporting_libraries` | Non-framework test-support dependencies and manifest evidence |
| `test_projects` | Detected .NET test project paths and associated files |
| `test_files` | File metadata/counts/evidence and `definitions[]` records; see below |
| `summary` | Totals and per-primary-category file counts |
| `limitations` | Unreadable/oversized files, malformed manifests, skipped symlinks, and other limitations |

Confidence values are `confirmed`, `probable`, or `unknown`. Test categories are `ui_e2e`, `component`, `unit`, `api`, `integration`, and `unknown`. Per-definition status is `active`, `skipped`, `todo`, or `unknown`.

Each nested definition contains `path`, deterministic `id`, source `name` (nullable for dynamic/unresolved names), `line`, `kind` (`test`, `suite`, `suspected_test`), framework key (nullable), confidence, evidence, `tools`, category/classification evidence, status/status source, and nullable boolean `parameterized`. IDs combine path, kind, source name (line fallback), and duplicate-name occurrence. Named IDs survive unrelated line insertions, but renames/moves or reordering identical names can change them; they are not runtime runner IDs. C# lines identify the first recognized test attribute.

Definition categories use local declaration-body evidence, not the containing file's category. Unknown C# or non-browser unit classifications are intentional when isolation is not established. File-category aggregates remain file counts. Generic test APIs do not alone establish Playwright. Mocha can be the runner while Selenium is recorded in definition `tools`.

### Counting rules

- A test definition is a recognized declaration site, not a runtime execution or a parameterized row. A parameterized declaration counts once. Framework-neutral Python/Go/Java/Kotlin/Rust/Ruby patterns are recorded separately as suspected declarations and do not inflate the recognized definition total.
- A suite count includes only recognized JavaScript/TypeScript suite declarations; test classes are not automatically counted as suites.
- Skipped and TODO counts are subsets of recognized test definitions.
- Explicit skipped suites propagate skipped status to enclosed JS definitions. `xit`/`xtest` are skipped; callback-free declarations are pending (`todo`). Recognized inline Playwright skip/fixme calls produce unknown status rather than claiming unconditional execution. Other conditional/runtime mechanisms remain unresolved.
- `.each(...)` indicates parameterization. C# Theory/TestCase/TestCaseSource/DataTestMethod/DataRow/DynamicData attributes indicate parameterization where recognized. Loops inside a JS body are indeterminate (`null`), not counted as additional definitions or silently treated as proven non-parameterized.
- Test-file totals include recognized and suspected source files. Classification totals count files once by their primary category.
- Framework package/config evidence alone does not prove active tests. Categories are based on test implementation indicators, never framework name alone.
- Markdown and JSON values share one model. Reports include repository-relative evidence paths and line numbers for source declarations where available.

## Limitations and safety

This is static lexical analysis, not a language parser. Dynamic aliases, decorators/macros, source generators, unconventional syntax, regex literals containing declaration-like text, runner configuration executed at runtime, and complex conditional compilation may reduce detection accuracy. Conditional skips are not evaluated. Runtime-disabled tests must not be inferred active from these static labels. Arbitrary non-JS/.NET frameworks may be surfaced as unknown but are not exhaustively parsed. The scanner deliberately avoids examining arbitrary JSON documents and inspects only source files, `package.json`, selected runner configuration, and .NET project/solution files. Files above 1 MB and symbolic links are skipped and reported.

The scanner contains no repository-specific assumptions, does not require Git metadata, and emits no source snippets, secrets, environment variables, or dependency cache contents.

## Validation

Run synthetic fixture tests with:

```sh
python3 -m unittest discover -s tests -v
```

Tests cover Playwright, Jest, NUnit, xUnit, MSTest, parameterized and skipped definitions, unknown assets, empty inventories, exclusions, nested projects, output safety, invalid inputs, symlink handling, and malformed manifests.

Additional regressions cover member-call/helper false positives, ambiguous framework attribution, language boundaries, names/IDs, mixed definition categories, suite skips/pending/conditional status, readable Markdown, paths with spaces, unchanged target contents, schema adaptation, TP/FP/FN matching, partial/unverifiable validation, and exclusion/unknown policies. No target application dependencies are installed or run.

## Extending

Add framework package/config signatures and definition patterns to `scripts/scan-repository.py`, then add synthetic assertions to `tests/test_scan_repository.py`. Document language-specific conventions in a file under `references/`. Keep declarations, framework identity, supporting-library identification, and category inference separate; never increase confidence without adding observable evidence.
