# JavaScript and TypeScript Rules

## Framework evidence

Recognized framework packages include Playwright (`@playwright/test`), Jest, Cypress, Vitest, Mocha, Jasmine, WebdriverIO, Selenium WebDriver (`selenium-webdriver`), Puppeteer, Protractor, and TestCafe. Config filenames are supporting evidence. Manifest declarations are recorded separately from active usage.

Common declarations include `test`/`it` and their `skip`, `only`, `todo`, or `each` forms; BDD suite declarations such as `describe`/`context`/`suite`; and Cypress `it`/`specify`. A recognized API use in a candidate test asset is active evidence. A filename or manifest alone does not establish a test definition.

Test support packages are separate from frameworks: React Testing Library, Angular Testing Library, Enzyme, and similar libraries are reported as supporting libraries and do not establish an independent framework.

## Candidate files

Inspect JavaScript, TypeScript, JSX, and TSX sources if they contain a recognized declaration or are test-like by path/name. Include framework configuration and `package.json` files as evidence, not as test files unless they themselves contain test declarations.

## Limitations

Static pattern recognition cannot resolve arbitrary aliases, dynamic imports, macro-generated tests, or executable configuration. Such evidence is reported as uncertain rather than evaluated by running Node.js or a framework CLI.
