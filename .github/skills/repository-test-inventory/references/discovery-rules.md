# Discovery Rules

## Traversal and safety

- Accept absolute or relative paths, canonicalize the root, and require it to be a readable directory.
- Traverse without Git metadata and sort paths for repeatable results.
- Skip symlinks rather than following them; report that limitation when encountered.
- Default exclusions: `.git`, `node_modules`, `bin`, `obj`, `dist`, `build`, `.next`, `.nuxt`, `coverage`, `vendor`, and common Python caches/virtual environments. Also avoid common lockfiles, generated bundles, and binary files.
- `--no-default-excludes` disables defaults. Explicit exclude patterns are always applied. Include patterns select additional paths and may explicitly include a path otherwise excluded by a default, but never override an explicit exclude.
- Patterns match repository-relative POSIX paths using shell-style matching; a pattern without `/` matches any path component. Include patterns filter source files while package manifests, project/solution files, and runner configuration remain available as framework-detection context.
- The report output directory must not be inside the scanned root. The default is a stable, repository-specific subdirectory of the system temporary directory.
- `.gitignore` and runner include/exclude rules are not traversal rules. Configuration currently provides framework context only. A baseline exclusion needs a supported scanner default or explicit CLI rule; `generated` is not a default.

## Evidence sources

Use static inspection of source files, manifests, project/solution files, and test-runner configuration. A dependency or configuration identifies a declared framework, but does not alone establish active tests. Record active test-definition evidence separately. Do not load configuration by executing it.

Recognize tests from framework APIs/attributes and imports/namespaces, not filename alone. Test-like names and generic test declarations can surface suspected unknown assets, but are not proof of a supported framework. Inspect nested projects independently and associate a source file with its nearest project file.

Malformed manifests and unreadable files must be reported as limitations; continue with other files. Never silently turn an error into an empty successful inventory.

## Static counting

Count syntactically recognized test declaration sites, not data rows, parameter values, runtime cases, or executions. Count one parameterized declaration once. Ignore comments and C# inactive preprocessor branches where recognized. Dynamic aliases, generated code, unusual macros, and complex syntax may prevent a precise count; report limitations rather than guessing.

Use schema 1.1 definition paths/names/IDs/lines for matching, not aggregate totals. Python function patterns remain suspected unsupported declarations and are reported as limitations. JavaScript declaration patterns are not applied to other source languages. Member calls such as regex `.test()` and conventional locally declared helpers are not test API declarations.
