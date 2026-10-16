# Classification and Reporting Rules

## Confidence

- **Confirmed**: a supported test declaration or framework-specific test attribute is found in source.
- **Probable**: multiple supporting indicators exist, but no supported declaration is confidently recognized.
- **Unknown**: test-like evidence exists but no framework can be identified.

Report declared frameworks independently from frameworks actively used in recognized test declarations.

## Test category

Assign a primary category only when implementation evidence supports it. Use UI / End-to-End for browser automation, Component for component-testing libraries or component-focused render APIs, API for explicit HTTP/API request tests, Integration for explicit external-system or multi-component integration evidence, Unit for clearly isolated unit-test evidence, otherwise Unknown. A framework name alone does not establish the category. Evidence and category are static heuristics, not quality judgments.

Closed assertions over local values and recognized standard-library operations
can establish Unit; unresolved services, imports, fixture arguments and mocks do
not. JS arrow `beforeEach` hooks can provide bounded, lexically enclosing setup
evidence. Never use a sibling suite's setup. Record `classification_basis` as
`direct`, `inferred_setup`, or `unknown`; this is not transitive dependency
analysis. Pending/body-less definitions remain unknown. Measure category coverage
and wrong predictions separately, rather than maximizing labels at any cost.

Recognized framework assertion APIs may establish Unit only when their operands
are closed local computations. Literal scalar rows from supported inline data
declarations may bound the corresponding test parameters; dynamic data sources,
fixture arguments, and unresolved calls do not. This evidence is static and does
not establish that assertions meaningfully test application behavior.

## Skips and exclusions

Keep explicit skips, TODO/pending declarations, conditional skips, excluded files, and unknown execution status distinct. The current scanner counts explicit declaration-level skip markers and TODO/pending forms; it does not resolve conditional skip logic or runner-level file exclusion patterns. Configuration-based file exclusion is evidence only when it can be read without executing configuration. Never infer that a test is disabled merely because no runner config references it.

Skipped JS suites propagate status to enclosed declarations. `xit` and `xtest` mean skipped, not TODO. Callback-free pending forms use `todo`; recognized runtime Playwright skip/fixme calls produce `unknown` status. Other dynamic status mechanisms remain a limitation. File categories and definition-body categories are separate; never copy a primary file category across mixed test definitions.

## Reports and counts

The Markdown and JSON files are rendered from the same model. Paths are repository-relative. Evidence line numbers refer to the inspected source line. Test-file totals count identified or suspected test source files; definition totals count distinct recognized declaration sites once, including a parameterized declaration once. Suite counts are reported only for recognized suite declarations. Skipped counts are a subset of definitions; TODO/pending counts are reported separately. Classifications count test files by their primary category.

The JSON contract is documented in `README.md`. Stable enum values are lowercase `confirmed`, `probable`, `unknown` for confidence and `ui_e2e`, `component`, `unit`, `api`, `integration`, `unknown` for categories.

Separate recognized/suspected file counts and unknown-framework/unknown-category
counts. These populations overlap and must not be added as disjoint totals.
Report browser tools separately from runners, preserving source evidence without
duplicating definitions. `body_iteration` means syntactic repetition, not proof
of framework parameterization or data-driven testing.

See [validation contract](./validation-contract.md) for independent discovery, attribution, classification, status, and parameterization measurements. Unknown framework and unknown category are different evidence gaps; report them separately.

For baseline-backed reports, include discovery TP/FP/FN and precision/recall/F1, matched-definition dimension results, exclusion checks, unknown-asset retention, and unverifiable checks. Keep full-baseline metrics distinct from supported-scope metrics. Similar observed and expected totals can hide both false positives and false negatives; without assessable definition-level matching, accuracy is not evaluated. Do not repair reported categories or identities from baseline expectations.
