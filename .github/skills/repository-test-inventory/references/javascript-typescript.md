# JavaScript and TypeScript Rules

## Framework evidence

Recognized framework packages include Playwright (`@playwright/test`), Jest, Cypress, Vitest, Mocha, Jasmine, WebdriverIO, Selenium WebDriver (`selenium-webdriver`), Puppeteer, Protractor, and TestCafe. Config filenames are supporting evidence. Manifest declarations are recorded separately from active usage.

Common declarations include `test`/`it` and their `skip`, `only`, `todo`, or `each` forms; BDD suite declarations such as `describe`/`context`/`suite`; and Cypress `it`/`specify`. A recognized API use in a candidate test asset is active evidence. A filename or manifest alone does not establish a test definition.

Generic `test` and `expect` identifiers alone do not identify Playwright. Prefer explicit runner imports, then unambiguous local package/config context, then runner-specific APIs. Selenium/Puppeteer imports can identify automation tools without overriding an evidenced runner such as Mocha. Multiple unresolved runner candidates remain unknown at definition level.

Test support packages are separate from frameworks: React Testing Library, Angular Testing Library, Enzyme, and similar libraries are reported as supporting libraries and do not establish an independent framework.

## Candidate files

Inspect JavaScript, TypeScript, JSX, and TSX sources if they contain a recognized declaration or are test-like by path/name. Include framework configuration and `package.json` files as evidence, not as test files unless they themselves contain test declarations.

Ignore member `.test()` calls and locally declared conventional helper functions. Balanced call boundaries and literal source titles provide definition names and body-local classification evidence. Names can be null for dynamic titles; the validator must report those comparisons as unverifiable rather than fabricate identities.

## Limitations

Static pattern recognition cannot resolve arbitrary aliases, dynamic imports, macro-generated tests, or executable configuration. Such evidence is reported as uncertain rather than evaluated by running Node.js or a framework CLI.

`.each(...)` contributes one framework-parameterized declaration. Body loops set
`body_iteration`, not `parameterized`; incidental loops are not proof of
data-driven testing and never add definitions. Dynamic titles may still leave
parameterization indeterminate. Skipped suites propagate skip status;
`xit`/`xtest` are skipped and callback-free declarations are pending.
Inline runtime skip/fixme status is unknown when recognized.
Lexical helper-shadow detection is file-wide rather than a complete scope resolver.

Selenium WebDriver and Puppeteer appear in `automation_tools`, not runner totals.
Their explicit imports are source-use evidence. A tool import alone does not
establish a test runner. Definition `tools` preserves attribution without counting
a Mocha declaration twice.
