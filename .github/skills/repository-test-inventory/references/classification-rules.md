# Classification and Reporting Rules

## Confidence

- **Confirmed**: a supported test declaration or framework-specific test attribute is found in source.
- **Probable**: multiple supporting indicators exist, but no supported declaration is confidently recognized.
- **Unknown**: test-like evidence exists but no framework can be identified.

Report declared frameworks independently from frameworks actively used in recognized test declarations.

## Test category

Assign a primary category only when implementation evidence supports it. Use UI / End-to-End for browser automation, Component for component-testing libraries or component-focused render APIs, API for explicit HTTP/API request tests, Integration for explicit external-system or multi-component integration evidence, Unit for clearly isolated unit-test evidence, otherwise Unknown. A framework name alone does not establish the category. Evidence and category are static heuristics, not quality judgments.

## Skips and exclusions

Keep explicit skips, TODO/pending declarations, conditional skips, excluded files, and unknown execution status distinct. The current scanner counts explicit declaration-level skip markers and TODO/pending forms; it does not resolve conditional skip logic or runner-level file exclusion patterns. Configuration-based file exclusion is evidence only when it can be read without executing configuration. Never infer that a test is disabled merely because no runner config references it.

Skipped JS suites propagate status to enclosed declarations. `xit` and `xtest` mean skipped, not TODO. Callback-free pending forms use `todo`; recognized runtime Playwright skip/fixme calls produce `unknown` status. Other dynamic status mechanisms remain a limitation. File categories and definition-body categories are separate; never copy a primary file category across mixed test definitions.

## Reports and counts

The Markdown and JSON files are rendered from the same model. Paths are repository-relative. Evidence line numbers refer to the inspected source line. Test-file totals count identified or suspected test source files; definition totals count distinct recognized declaration sites once, including a parameterized declaration once. Suite counts are reported only for recognized suite declarations. Skipped counts are a subset of definitions; TODO/pending counts are reported separately. Classifications count test files by their primary category.

The JSON contract is documented in `README.md`. Stable enum values are lowercase `confirmed`, `probable`, `unknown` for confidence and `ui_e2e`, `component`, `unit`, `api`, `integration`, `unknown` for categories.

See [validation contract](./validation-contract.md) for independent discovery, attribution, classification, status, and parameterization measurements. Unknown framework and unknown category are different evidence gaps; report them separately.
