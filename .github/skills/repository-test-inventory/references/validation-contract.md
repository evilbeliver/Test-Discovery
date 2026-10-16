# Validation contract

## Boundaries and versions

Scanner JSON `1.1` retains `test_files[].definitions`. The bundled validator reads that contract and an independent baseline containing `expected_definition_count`, `definitions`, and optional `excluded_fixtures`, `unknown_assets`, and `negative_scenarios`. It does not import or execute code from the baseline repository. Only full repository-relative baselines are supported; scanning a scenario root against a full-root baseline requires rebasing paths and selecting expected records explicitly.

The adapter emits `repository-test-inventory-adapter/1` with top-level `definitions`, definition-level aggregates in `summary`, `unknown_assets`, and `excluded_assets`. It never uses expected counts or fixture names to change scanner detection.

## Field transformations

| Scanner | Adapted comparison field |
|---|---|
| `kind == test` | One confirmed-syntax definition; suites/suspected declarations are not included |
| Containing file `path` | Repository-relative `path` |
| Source `name` | `identifier`; no fabricated name when null |
| `id`, `line` | Retained as identity/location evidence |
| Framework key | Canonical framework display label; null becomes `unknown` |
| Mocha runner plus explicit Selenium import tool | `Mocha + Selenium WebDriver` |
| `category == ui_e2e` | `primary_category == ui` |
| Other category | Unchanged, including `unknown` |
| `status == todo` | `pending` |
| Other status | Unchanged, including `unknown` |
| `parameterized` | Boolean or null (indeterminate) |
| `body_iteration` | Optional additive syntactic iteration evidence; retained separately, never coerced into parameterization |
| Suspected file | Structured unknown asset |
| Encountered excluded path | Structured excluded asset; directory pruning covers descendants |

Aggregates are calculated from adapted test definitions, not file-level classifications. Scanner totals must reconcile with the number of recognized definition records.

## Matching

Match each expected definition to at most one observed definition, requiring the same repository-relative POSIX path. Compare case/punctuation-normalized source names, or an explicitly supplied baseline `test_id` against the first whitespace-delimited source-title token. This supports independently cataloged title prefixes without hardcoding ID formats or interpreting them in the scanner. A matching ID does not establish classification/framework/status correctness; these are assessed separately. Duplicate observed definitions remain false positives.

Missing source names make discovery unverifiable, not an empty successful inventory. Normalization can conflate names differing only in case/punctuation; duplicate normalized expected path/name pairs are rejected rather than silently matched. Renamed IDs or ambiguous catalog entries need manual baseline review.

## Assessment policy

- Discovery reports TP/FP/FN and precision/recall/F1 for the complete baseline.
- Unsupported frameworks remain false negatives in full-baseline metrics. A separate supported-scope denominator is reported; it never replaces full-baseline results.
- Supported framework scope includes pytest. Python without explicit pytest evidence remains suspected, not automatically supported by naming.
- Framework, category, status, and parameterization comparisons use matched definitions only. Missing definitions are not counted as correctly classified.
- Unknown/null predictions are measured abstentions and fail an exact required comparison. Absent fields make it unverifiable.
- With no matches, dimension checks are not applicable if discovery is assessable; they are not evidence of successful attribution.
- Every baseline unknown asset must be retained without confirmed framework attribution. Additional legitimate unknown assets are reported, not rejected merely for being additional.
- Expected excluded assets must be covered by an encountered exclusion and absent from recognized definitions. Additional exclusions are allowed and remain visible in the inventory.
- A completed scan, assessable data, and passed validation are separate booleans. All-unverifiable or partially unverifiable outcomes cannot pass.
- Exit codes: 0 pass; 1 assessable non-pass; 2 input/I/O/contract error; 3 unverifiable required checks.

## Combined workflow

`scripts/scan-and-validate.py` accepts a repository, `--expected`, a fresh external
`--output-directory`, and scanner include/exclude options. It invokes only the
bundled scanner and validator, never target code. `workflow-summary.json` retains
stage commands, exit codes, elapsed timings, Python version, script/baseline
hashes, source scan provenance, report paths and validation metrics. It refuses
to overwrite nonempty output directories. Scanner failure stops validation;
validator non-pass and unverifiable results keep their distinct nonzero exits.
Input/I/O errors are explicit errors, not successful empty inventories.

Framework parameterization is declaration-driven. A baseline treating a body
loop as parameterization can therefore disagree with the scanner's false
prediction even while `body_iteration` is true. Preserve and explain that
semantic disagreement; do not edit the independent baseline or normalize it
away to get a pass. Body iteration is not a required comparison in legacy baselines.

## Independent validator limitations

The original fixture validator is unchanged. It accepts the adapted array shape but:

- Its exit 0 can mean no comparisons were assessable.
- Its exact unknown-asset equality can reject legitimate unsupported assets.
- Its exact excluded-path equality does not recognize directory-pruning evidence.
- Its framework/category expectations require normalization; its matching policy is more permissive than the bundled validator.

Use the bundled validator for the documented policies. Do not treat the original validator's exit status as certification. Neither validator establishes runtime test execution, coverage, or agent skill-loading behavior.
