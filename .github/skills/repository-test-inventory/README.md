# repository-test-inventory

A portable, standard-library-only agent Skill and deterministic Python scanner for discovering automated tests in local repositories. It inventories test files, declared and actively used frameworks, recognized test/suite declarations, test projects, explicit skips/TODOs, static test categories, supporting libraries, evidence, and scan limitations.

The scanner is read-only with respect to the target repository. It never invokes tests, project code, package managers, build tools, or framework CLIs, and it does not connect to the network. Markdown and JSON are generated from the same inventory object. All validation fixtures are created dynamically under temporary directories.

## Installation

For a VS Code workspace, copy this folder to:

```text
.github/skills/repository-test-inventory/
```

The Python scanner requires Python 3.10 or later and has no third-party dependencies. The Skill can be used manually even in agent environments that do not support automatic Skill loading.

## Usage

From the Skill directory, run:

```sh
python3 scripts/scan-repository.py /path/to/repository
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

## Framework coverage

JavaScript/TypeScript frameworks: Playwright, Jest, Cypress, Vitest, Mocha, Jasmine, WebdriverIO, Selenium WebDriver, Puppeteer, Protractor, and TestCafe.

.NET frameworks: NUnit, xUnit, and MSTest.

Supporting libraries include React Testing Library, Angular Testing Library, Enzyme, Moq, NSubstitute, FluentAssertions, Selenium WebDriver for .NET, Microsoft Playwright for .NET, and bUnit. Supporting libraries do not by themselves establish an independent framework.

Unknown test-like assets are retained as suspected files rather than silently dropped or assigned an invented framework. Framework declarations from manifests/configuration are distinct from active test-definition evidence.

## JSON contract

`test-inventory.json` uses schema version `1.0` and these top-level fields:

| Field | Meaning |
|---|---|
| `schema_version` | Contract version (`1.0`) |
| `repository` | Canonical repository path and basename identifier |
| `scan` | UTC timestamp, read-only mode, completion status, options, inspected-file count, encountered excluded paths, and solution files |
| `languages` | Languages with discovered test source assets |
| `frameworks` | Framework identity, language, confidence, declared/active status, evidence, files, and static definition count |
| `supporting_libraries` | Non-framework test-support dependencies and manifest evidence |
| `test_projects` | Detected .NET test project paths and associated files |
| `test_files` | Path, language, framework, category, confidence, static recognized and suspected definition/suite/skip/TODO counts, evidence, project, and suspected status |
| `summary` | Totals and per-primary-category file counts |
| `limitations` | Unreadable/oversized files, malformed manifests, skipped symlinks, and other limitations |

Confidence values are `confirmed`, `probable`, or `unknown`. Test categories are `ui_e2e`, `component`, `unit`, `api`, `integration`, and `unknown`. Per-definition status is `active`, `skipped`, or `todo`.

### Counting rules

- A test definition is a recognized declaration site, not a runtime execution or a parameterized row. A parameterized declaration counts once. Framework-neutral Python/Go/Java/Kotlin/Rust/Ruby patterns are recorded separately as suspected declarations and do not inflate the recognized definition total.
- A suite count includes only recognized JavaScript/TypeScript suite declarations; test classes are not automatically counted as suites.
- Skipped and TODO counts are subsets of recognized test definitions.
- Test-file totals include recognized and suspected source files. Classification totals count files once by their primary category.
- Framework package/config evidence alone does not prove active tests. Categories are based on test implementation indicators, never framework name alone.
- Markdown and JSON values share one model. Reports include repository-relative evidence paths and line numbers for source declarations where available.

## Limitations and safety

This is static lexical analysis, not a language parser. Dynamic aliases, decorators/macros, source generators, unconventional syntax, runner configuration executed at runtime, and complex conditional compilation may reduce detection accuracy. Conditional skip expressions and runner-level excluded test-file patterns are not evaluated or counted. Arbitrary non-JS/.NET frameworks may be surfaced as unknown but are not exhaustively parsed. The scanner deliberately avoids examining arbitrary JSON documents and inspects only source files, `package.json`, selected runner configuration, and .NET project/solution files. Files above 1 MB and symbolic links are skipped and reported.

The scanner contains no repository-specific assumptions, does not require Git metadata, and emits no source snippets, secrets, environment variables, or dependency cache contents.

## Validation

Run synthetic fixture tests with:

```sh
python3 -m unittest discover -s tests -v
```

Tests cover Playwright, Jest, NUnit, xUnit, MSTest, parameterized and skipped definitions, unknown assets, empty inventories, exclusions, nested projects, output safety, invalid inputs, symlink handling, and malformed manifests.

## Extending

Add framework package/config signatures and definition patterns to `scripts/scan-repository.py`, then add synthetic assertions to `tests/test_scan_repository.py`. Document language-specific conventions in a file under `references/`. Keep declarations, framework identity, supporting-library identification, and category inference separate; never increase confidence without adding observable evidence.
